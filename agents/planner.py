"""Action Planner Agent — a verified plan in, a dated schedule and a cost band out.

    from agents.planner import run_planner, planner_summary
    run_planner(state)     # writes state.schedule, state.cost_estimate, state.rescan_date

`plan_draft` is prose; a schedule is a timeline the UI draws nodes on, and the two have to
agree — a schedule telling the farmer to do something the plan never verified is worse than
no schedule. So this agent does not decide *what* to do, only turns the dates, products and
doses the plan already states into `{day_offset, action, note}` entries, plan order preserved.

**Parsing, not another LLM call.** Every sentence in `plan_draft` is already grounded and
Verifier-checked; summarising it with a model risks paraphrasing a dose or an interval — the
one place here where a paraphrase is a safety issue, not a style one. Regex over the plan's
markdown (one sentence per line, under exactly three headings, enforced by `AGRONOMIST_SYSTEM`
and mirrored by `draft_extractive`) can only reorder sentences that already passed grounding,
never invent a fact. The LLM, when available, touches exactly one thing with no factual risk:
rewording the short action *labels* — never `note`, which is where the doses live.

**The chemical vocabulary matches `treatment_costs.json`.** Both are built from the same
source: every product name in `agents/rag/corpus/`. A plan can only ever name a chemical that
appears in a retrieved passage — the Agronomist's own grounding rule — so the set this agent
needs to recognise is closed and known in advance, not guessed at from free text.

**The interval is read, not assumed.** Every disease document gives its own re-inspection
window — 7 days for tomato and potato blights, 14-21 for corn at tasselling — so a hardcoded
number would be right for some diseases and quietly wrong for others. `find_interval` reads
whatever the plan's own Follow-up section states and falls back to 7, the corpus's modal
value, only when no interval is stated.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from agents import llm
from agents.state import RunState

COSTS_PATH = Path(__file__).resolve().parent / "treatment_costs.json"

HEADING_IMMEDIATE = "Immediate action (next 48 hours)"
HEADING_FOLLOWUP = "Follow-up"

MARKER_RE = re.compile(r"\s*\[doc_\d+#p\d+\]\s*$")

# Matches are resolved by leftmost position in the sentence, not by tuple order, so "cymoxanil
# 8 percent plus mancozeb 64 percent" reads as the combo product, not plain mancozeb — the word
# "cymoxanil" simply appears first. _CHEM lists (key, bare regex body); compiled once below.
_CHEM = [
    ("cymoxanil_mancozeb_combo", r"cymoxanil"), ("metalaxyl_mancozeb_combo", r"metalaxyl"),
    ("mancozeb", r"mancozeb"), ("chlorothalonil", r"chlorothalonil"),
    ("copper_oxychloride", r"copper oxychloride"), ("azoxystrobin", r"azoxystrobin"),
    ("difenoconazole", r"difenoconazole"), ("propiconazole", r"propiconazole"),
    ("tebuconazole", r"tebuconazole"), ("pyraclostrobin", r"pyraclostrobin"),
    ("imidacloprid", r"imidacloprid"), ("thiamethoxam", r"thiamethoxam"), ("neem_oil", r"neem oil"),
]
CHEMICAL_PATTERNS: tuple[tuple[str, re.Pattern], ...] = tuple(
    (key, re.compile(rf"\b{body}\b", re.I)) for key, body in _CHEM
)

# Checked in order, first match wins — unlike chemicals these are mutually exclusive verbs
# describing the same kind of step, not alternative products in the same sentence.
REMOVAL_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("Remove infected plants", re.compile(r"\brogu\w*\b", re.I)),
    ("Stop overhead irrigation", re.compile(r"\bstop\b[^.]{0,40}\birrigation\b", re.I)),
    ("Remove infected foliage", re.compile(r"\bremove\b|\bdestroy\w*\b", re.I)),
    ("Prune affected foliage", re.compile(r"\bprune\w*\b", re.I)),
)

# Application-practice sentences (timing, coverage, calibration) describe *how* to carry out the
# spray just scheduled, not a new dated action — folded into that spray's note instead of
# becoming a redundant timeline node.
TIMING_RE = re.compile(
    r"\b(morning|evening|underside|coverage|drift|calibrat\w*|litres? of (spray|water)|run-?off|wet\w* for)\b",
    re.I,
)
RESISTANCE_RE = re.compile(r"\bresistan\w*\b|\bmode of action\b|\brotat\w*\b", re.I)
RESCAN_RE = re.compile(r"re-?inspect|re-?scan|scan the field|compare the proportion", re.I)
REPEAT_RE = re.compile(r"\brepeat\w*\b|\bagain\b|\bsecond\b|\bcontinu\w*\b", re.I)

NUMBER_WORDS = {
    "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "fourteen": 14, "twenty-one": 21,
}
INTERVAL_RE = re.compile(
    r"\b(\d+|three|four|five|six|seven|eight|nine|ten|fourteen|twenty-one)\b[\s-]*(?:to\s+\S+\s+)?days?", re.I,
)
DEFAULT_INTERVAL_DAYS = 7


@lru_cache(maxsize=1)
def cost_table() -> dict:
    return json.loads(COSTS_PATH.read_text(encoding="utf-8"))


def strip_marker(line: str) -> str:
    return MARKER_RE.sub("", line).strip()


def sections_of(plan_draft: str) -> dict[str, list[str]]:
    """{heading: [sentence, ...]}, markers stripped — keyed on the plan's own `## ` headings,
    fixed to exactly three by AGRONOMIST_SYSTEM and mirrored by draft_extractive."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in plan_draft.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(strip_marker(line))
    return sections


def find_chemical(sentence: str) -> str | None:
    best_key, best_pos = None, None
    for key, pattern in CHEMICAL_PATTERNS:
        match = pattern.search(sentence)
        if match and (best_pos is None or match.start() < best_pos):
            best_key, best_pos = key, match.start()
    return best_key


def find_removal(sentence: str) -> str | None:
    for label, pattern in REMOVAL_PATTERNS:
        if pattern.search(sentence):
            return label
    return None


def find_interval(text: str, default: int = DEFAULT_INTERVAL_DAYS) -> int:
    match = INTERVAL_RE.search(text)
    if not match:
        return default
    token = match.group(1).lower()
    return int(token) if token.isdigit() else NUMBER_WORDS.get(token, default)


def fallback_action_label(_sentence: str) -> str:
    """Rare: the corpus's own section templates cover almost every Immediate-action sentence.
    A fixed, honest label rather than truncating the sentence into a word fragment — a title
    like "The decision to spray maize" reads as a claim the sentence never quite finishes, and
    the full sentence is still on `note` for whoever expands the step."""
    return "Follow plan guidance"


def _build_items(state: RunState) -> list[dict]:
    """Internal items carry `chem_key` for the cost pass; schema-forbidden on the public dicts,
    so `run_planner` strips it before the state is written."""
    sections = sections_of(state.plan_draft or "")
    immediate = sections.get(HEADING_IMMEDIATE, [])
    followup = sections.get(HEADING_FOLLOWUP, [])
    table = cost_table()["products"]

    items: list[dict] = []
    for sentence in immediate:
        chem = find_chemical(sentence)
        if chem:
            label = table.get(chem, cost_table()["_default_product"])["label"]
            items.append({"day_offset": 0, "action": f"Apply {label}", "note": sentence,
                          "kind": "spray", "chem_key": chem})
            continue
        removal = find_removal(sentence)
        if removal:
            items.append({"day_offset": 0, "action": removal, "note": sentence, "kind": "other"})
            continue
        if TIMING_RE.search(sentence) and items and items[-1]["kind"] == "spray" and items[-1]["day_offset"] == 0:
            items[-1]["note"] += " " + sentence
            continue
        items.append({"day_offset": 0, "action": fallback_action_label(sentence), "note": sentence, "kind": "other"})

    interval = find_interval(" ".join(followup) or " ".join(immediate))
    resistance_sentence, rescan_sentence = None, None
    for sentence in followup:
        chem = find_chemical(sentence)
        if chem and REPEAT_RE.search(sentence):
            label = table.get(chem, cost_table()["_default_product"])["label"]
            items.append({"day_offset": interval, "action": f"Second {label} application (if needed)",
                          "note": sentence, "kind": "spray", "chem_key": chem})
        elif RESISTANCE_RE.search(sentence):
            resistance_sentence = sentence
        elif RESCAN_RE.search(sentence):
            rescan_sentence = sentence
    if resistance_sentence:
        for item in reversed(items):
            if item["kind"] == "spray":
                item["note"] += " " + resistance_sentence
                break
    items.append({
        "day_offset": interval,
        "action": "Re-scan field",
        "note": rescan_sentence or "Run a fresh scan and compare the affected percentage against this one.",
        "kind": "rescan",
    })
    return items


def _estimate_cost(items: list[dict]) -> dict:
    table = cost_table()
    products, default = table["products"], table["_default_product"]
    low = high = 0.0
    removal_seen = False
    for item in items:
        if item["kind"] == "spray":
            info = products.get(item.get("chem_key"), default)
            low += info["low"]
            high += info["high"]
        elif item["kind"] == "other":
            removal_seen = True
    note = "Rough estimate: per-acre product plus application labour for each scheduled spray"
    if removal_seen:
        labour = table["labour"]["sanitation_removal"]
        low += labour["low"]
        high += labour["high"]
        note += ", plus a flat removal and sanitation labour charge"
    note += ". Local prices vary — a triage figure, not a quote."
    return {"currency": "INR", "low": round(low), "high": round(high), "note": note}


def _rescan_date(state: RunState, interval_days: int) -> str:
    base = None
    if state.started_at:
        try:
            base = datetime.fromisoformat(state.started_at.replace("Z", "+00:00")).date()
        except ValueError:
            base = None
    base = base or datetime.now(timezone.utc).date()
    return (base + timedelta(days=interval_days)).isoformat()


def _polish_actions(schedule: list[dict]) -> list[dict]:
    """Cosmetic pass over `action` labels only, never `note` where the dose facts live. Any
    response failing validation (wrong length, a stray digit, an empty string) is discarded
    and the deterministic label ships — silent on no key or failure, like llm.complete itself."""
    if not schedule or not llm.available():
        return schedule
    labels = [item["action"] for item in schedule]
    result = llm.complete(
        system="You rewrite short farm task labels. Reply with a JSON array of strings and nothing else.",
        user=(
            "Rewrite each label below as a plainer imperative phrase a farmer would recognise, "
            "at most 5 words, no digits, no punctuation besides spaces. Return ONLY a JSON "
            f"array of strings, same length and order as the input.\n\n{json.dumps(labels)}"
        ),
    )
    if not result.ok:
        return schedule
    try:
        polished = json.loads(result.text)
    except json.JSONDecodeError:
        return schedule
    if not isinstance(polished, list) or len(polished) != len(labels):
        return schedule
    if any(not isinstance(p, str) or not p.strip() or re.search(r"\d", p) or len(p) > 60 for p in polished):
        return schedule
    for item, new_label in zip(schedule, polished):
        item["action"] = new_label.strip()
    return schedule


def run_planner(state: RunState) -> RunState:
    """Turn the verified plan into a dated schedule, a cost band, and a re-scan date."""
    if not state.plan_draft:
        # BLOCK, clean field or insufficient context all leave plan_draft null with nothing for
        # a schedule to be about. Defensive rather than trusting the orchestrator's own BLOCK
        # check, because this function has to be safe to call on its own.
        state.apply("planner.skipped.no_plan")
        return state

    items = _build_items(state)
    interval = next((i["day_offset"] for i in items if i["kind"] == "rescan"), DEFAULT_INTERVAL_DAYS)
    cost = _estimate_cost(items)
    rescan_date = _rescan_date(state, interval)
    schedule = _polish_actions([
        {"day_offset": i["day_offset"], "action": i["action"], "note": i["note"], "kind": i["kind"]}
        for i in items
    ])
    sprays = sum(1 for i in items if i["kind"] == "spray")
    state.apply(f"planner.schedule.{len(schedule)}_steps.{sprays}_sprays")
    state.apply(f"planner.cost_estimate.INR_{cost['low']}_{cost['high']}")
    state.apply("planner.done", schedule=schedule, cost_estimate=cost, rescan_date=rescan_date)
    return state


def planner_summary(state: RunState) -> str:
    if not state.schedule:
        reason = "no verified plan" if not state.plan_draft else "not planned"
        return f"no schedule — {reason}"
    cost = state.cost_estimate or {}
    sprays = sum(1 for s in state.schedule if s.get("kind") == "spray")
    return (
        f"{len(state.schedule)} step(s), {sprays} spray | "
        f"{cost.get('currency', 'INR')} {cost.get('low', '?')}-{cost.get('high', '?')} | "
        f"re-scan {state.rescan_date}"
    )

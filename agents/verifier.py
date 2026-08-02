"""Verifier Agent — the only agent that can overrule another one.

    from agents.verifier import run_verifier
    run_verifier(state, attempt)      # writes state.verification, may clear state.plan_draft

Everything upstream of here is trying to produce an answer. This agent's job is to be willing
to end the run without one. It reads `plan_draft` and the chunks it was drafted from, and
returns one of three rulings:

- **PASS** — every sentence traces to a retrieved chunk, every chemical is on the allowlist,
  every dose is inside the range its source states.
- **REWRITE** — some sentences do not trace. The Agronomist is asked again, at most
  MAX_REWRITES times; after that the offending sentences are stripped and it PASSes with
  `unsupported_claims` still populated, so the UI can say the plan was revised rather than
  quietly showing a shortened plan.
- **BLOCK** — a chemical or a dose the corpus does not support. Nothing ships. `plan_draft` is
  cleared and a refusal brief replaces it.

**Why a violation blocks instead of being rewritten.** An ungrounded sentence is a claim the
system could not back up, and dropping it leaves a shorter, still-correct plan. A chemical the
corpus never names, or a dose outside the range it states, is different in kind: something
generated the name of a pesticide and a number of grams per litre out of nothing, and that
number is the one part of the plan a farmer will act on most literally. The failure mode is
not an embarrassing sentence, it is a person mixing the wrong thing into a sprayer. There is
no version of that worth rewriting toward.

**The allowlist is a separate authority, not a summary of the corpus.** agents/allowlist.json
is committed rather than derived at run time, so a corpus edit cannot silently widen what may
be recommended. See the note in that file.

**On clearing plan_draft.** A BLOCK that left the draft in the response would not be a block —
the API returns that field and the UI would have it. Deleting the evidence is a real cost, so
the event log keeps the ruling and `verification.block_reason` keeps the reason in plain words.

**The Verifier does not check whether the advice is good agronomy.** It checks that every
claim came from somewhere and that the numbers were not altered in transit. A corpus that is
wrong produces a plan that is wrong and passes; that risk sits with the corpus, and the source
drawer showing the chunk verbatim is what lets a human find it.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from agents.claims import (
    GROUNDING_MIN,
    Claim,
    containment,
    doses,
    is_scan_statement,
    mentioned,
    names_disease,
    parse_claims,
    unknown_actives,
)
from agents.refusal import refusal_report
from agents.state import RunState

ALLOWLIST_PATH = Path(__file__).resolve().parent / "allowlist.json"

# Two redrafts, then strip. Set here and nowhere else — the orchestrator reads it rather than
# keeping a count of its own, because two components each believing they own the budget is how
# a plan gets rewritten five times.
MAX_REWRITES = 2



@lru_cache(maxsize=1)
def allowlist() -> dict:
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))


def approved() -> list[str]:
    return sorted(allowlist()["chemicals"])


# --- the three checks --------------------------------------------------------------------


def ungrounded(claims: list[Claim], chunks: dict[str, dict], state: RunState) -> list[str]:
    """Sentences that do not trace back to the chunk they cite. Returns the original lines.

    Three distinct failures, all of them ungrounded and only the first of them obvious: no
    marker at all; a marker naming a chunk that was never retrieved (an invented id, which is
    worse than none because it looks checked); and a marker naming a real chunk that does not
    actually contain the sentence.
    """
    disease = dominant_label(state)
    out = []
    for claim in claims:
        chunk = chunks.get(claim.marker or "")
        if chunk is None:
            out.append(claim.line)
        elif is_scan_statement(claim.text, state.spread):
            # Its numbers came from the Spread Analyst and are in no passage. What its source
            # has to back is the other half of the sentence — that this field has this disease.
            if not names_disease(claim.text, chunk, disease):
                out.append(claim.line)
        elif containment(claim.text, chunk) < GROUNDING_MIN:
            out.append(claim.line)
    return out


def chemical_violations(claims: list[Claim]) -> list[tuple[str, str]]:
    """(sentence, reason) for banned actives and anything not on the allowlist."""
    banned = allowlist()["banned"]
    known = approved()
    problems = []
    for claim in claims:
        for name in mentioned(claim.text, banned):
            problems.append((claim.text, f"{name} is banned or severely restricted for agricultural use"))
        for name in unknown_actives(claim.text, known):
            if name not in banned:
                problems.append((claim.text, f"{name} is not a chemical any source document names"))
    return problems


def dose_violations(claims: list[Claim]) -> list[tuple[str, str]]:
    """(sentence, reason) for doses outside the stated range, in the wrong unit, or unattached.

    A dose in the wrong unit is its own failure and not a rounding matter: 3 grams per litre of
    a wettable powder and 3 millilitres per litre of a concentrate are different amounts of
    active ingredient, and the mistake is invisible in a sentence that otherwise reads well.
    """
    table = allowlist()["chemicals"]
    known = approved()
    problems = []
    for claim in claims:
        # Unapproved actives are included when attributing doses, purely so the number lands on
        # the right name. Without them, "carbendazim ... at 4.0 grams per litre" reported a
        # dose "with no chemical named" — true of the allowlist, and baffling to read next to a
        # sentence that plainly names one. The chemical itself is already a violation above;
        # this loop only has to avoid describing it wrongly.
        for name, low, high, unit in doses(claim.text, known + unknown_actives(claim.text, known)):
            if name is None:
                problems.append((claim.text, f"a dose of {low} {unit} is given with no chemical named"))
            elif name not in table:
                continue
            elif unit != table[name]["unit"]:
                problems.append(
                    (claim.text, f"{name} is dosed in {unit}, but its source states {table[name]['unit']}")
                )
            elif low < table[name]["low"] or high > table[name]["high"]:
                problems.append((
                    claim.text,
                    f"{name} at {low}-{high} {unit} is outside the supported "
                    f"{table[name]['low']}-{table[name]['high']} {unit}",
                ))
    return problems


# --- the ruling ---------------------------------------------------------------------------


def dominant_label(state: RunState) -> str:
    """The disease the plan is about, as words. Read off the event log the Agronomist wrote,
    so the Verifier does not re-derive it from tiles and reach a different answer."""
    prefix = "agronomist.disease."
    for event in reversed(state.events):
        if event.startswith(prefix):
            return event[len(prefix):].rsplit(".", 1)[0].replace("_", " ")
    return ""


def strip(draft: str, offenders: list[str]) -> str:
    """Remove the failing lines, then collapse any heading left with nothing under it."""
    kept = [ln for ln in draft.splitlines() if ln.strip() not in offenders]
    out: list[str] = []
    for i, line in enumerate(kept):
        rest = [ln for ln in kept[i + 1:] if ln.strip()]
        if line.startswith("#") and (not rest or rest[0].startswith("#")):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _ruling(state: RunState, status: str, claims: list[str], reason: str | None = None) -> dict:
    return {
        "status": status,
        "unsupported_claims": claims,
        # Published here for the first time. The Agronomist keeps its retrieved chunks in an
        # internal field that never reaches the API, so until this line runs the UI has a plan
        # full of [doc_04#p4] markers and nothing to resolve them against.
        "sources": list(state.sources),
        "block_reason": reason,
    }


def block(state: RunState, reason: str, detail: list[str], plainly: str) -> RunState:
    """`reason` is the technical explanation on the refusal card; `plainly` is the clause the
    farmer brief uses. They are separate because the person holding the phone in a field does
    not need to be told which active ingredient failed an allowlist — they need to be told
    that nobody is going to give them a spray recommendation today, and why not, in one line.
    """
    state.apply(f"verify.block.{len(detail)}_violations")
    state.apply(
        "verify.block",
        verification=_ruling(state, "BLOCK", detail, reason),
        plan_draft=None,
        report=refusal_report(
            state.crop, dominant_label(state) or "a disease",
            (state.spread or {}).get("pct_affected", 0.0), plainly,
        ),
        status="blocked",
    )
    return state


def run_verifier(state: RunState, attempt: int = 0) -> RunState:
    """Rule on the current draft. `attempt` is how many redrafts have already been spent."""
    if not state.plan_draft:
        if "agronomist.insufficient_context" in state.events:
            # The Agronomist declined because the corpus does not cover this disease. That is a
            # refusal the farmer has to see, not an empty panel, so it is ruled a BLOCK here
            # rather than left as a null the UI has to interpret.
            return block(
                state,
                "No plan was drafted. The reference corpus contains nothing covering this "
                "disease on this crop, and a plan assembled from loosely related documents "
                "would arrive with citations attached and therefore look checked.",
                ["No treatment plan could be grounded in the available source documents."],
                "our reference documents do not cover this disease on your crop",
            )
        state.apply("verify.skipped.no_plan")
        return state

    claims = parse_claims(state.plan_draft)
    chunks = {s["id"]: s for s in state.sources}

    violations = chemical_violations(claims) + dose_violations(claims)
    if violations:
        reasons = sorted({reason for _, reason in violations})
        return block(
            state,
            # Plain language, because this string is the whole explanation on the refusal card.
            f"The drafted plan did not survive safety checking: {'; '.join(reasons)}. "
            "Treatment advice was withheld rather than issued unverified.",
            [f"{sentence} — {reason}" for sentence, reason in violations],
            "the spray it suggested could not be confirmed against our verified sources",
        )

    offenders = ungrounded(claims, chunks, state)
    if not offenders:
        state.apply("verify.pass", verification=_ruling(state, "PASS", []))
        return state

    if attempt < MAX_REWRITES:
        # Counted event first for the log, then the bare name the UI keys on — same shape as
        # the block path, so a reader of the event stream sees detail then ruling both times.
        state.apply(f"verify.rewrite.{len(offenders)}_unsupported")
        state.apply("verify.rewrite", verification=_ruling(state, "REWRITE", offenders))
        return state

    # Budget spent. Strip and pass — with the claims still listed, because a plan that quietly
    # lost two sentences and a plan that never had them look identical otherwise.
    state.apply(f"verify.stripped.{len(offenders)}_sentences")
    state.apply(
        "verify.pass",
        verification=_ruling(state, "PASS", offenders),
        plan_draft=strip(state.plan_draft, offenders),
    )
    return state


def verifier_summary(state: RunState) -> str:
    v = state.verification
    if not v:
        return "not verified — no plan to rule on"
    claims = len(v["unsupported_claims"])
    if v["status"] == "BLOCK":
        return f"BLOCK — {v['block_reason']} | {claims} violation(s)"
    revised = f", {claims} sentence(s) stripped" if claims else ""
    return f"{v['status']} | {len(v['sources'])} source(s){revised}"

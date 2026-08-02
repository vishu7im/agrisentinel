"""Reporter Agent — a verified plan and a computed schedule in, a farmer brief out.

    from agents.reporter import run_reporter, reporter_summary
    run_reporter(state)     # writes state.report = {"en": ..., "hi": ...}

Six sentences, plain words, in two languages. The English half is built from facts already on
the state — the disease, `state.spread`, and `state.schedule`'s own day-0 and re-scan entries —
so it never restates a number the pipeline has not already computed and checked.

**Why report.hi is a phrase table, not a translation.** Machine-translating the English brief
at run time would mean the one farmer-facing artefact whose accuracy nobody re-checks is
produced by the component least equipped to guarantee it: a live translation call, on a run
with unpredictable venue wifi, of a sentence that may name a dose. Runtime translation is
refused everywhere else in this pipeline for the same reason the Agronomist refuses free
composition — so Hindi is built the same way plan_draft is on the extractive path: fixed,
reviewed text, filled in with numbers. `DISEASE_NAME_HI` is keyed on the disease; the first and
second action lines try an exact match against the schedule step's own action text first
(`ACTION_LABEL_HI`, the Planner's closed removal/rescan vocabulary), then a product-name
substring match (`PRODUCT_LABEL_HI`), and only fall back to a generic, non-specific phrase
keyed on `kind` when neither matches — never guessing at what an unclassified step actually
said. Severity buckets the field's own percentage into mild/moderate/severe, which is what
ties the Hindi brief to how bad the scan says the problem is.

**Reporter never imports planner.** Both read `state.schedule`, which the orchestrator's
running order guarantees is already written when the Reporter runs — that is a RunState
contract, not a call between two agents. If Reporter ever runs before Planner (a standalone
test, say), the fallback below reads `plan_draft`'s own Immediate-action sentence directly, so
the brief degrades gracefully instead of describing a schedule that is not there.
"""

from __future__ import annotations

import re
from collections import Counter

from agents.claims import DOSE_RE
from agents.state import RunState

MARKER_RE = re.compile(r"\s*\[doc_\d+#p\d+\]\s*$")
MAX_SENTENCES = 6

CROP_HI = {"tomato": "टमाटर", "potato": "आलू", "corn": "मक्का"}

COMPASS_EN = {
    "N": "north", "NE": "north-east", "E": "east", "SE": "south-east",
    "S": "south", "SW": "south-west", "W": "west", "NW": "north-west",
}
COMPASS_HI = {
    "N": "उत्तर", "NE": "उत्तर-पूर्व", "E": "पूर्व", "SE": "दक्षिण-पूर्व",
    "S": "दक्षिण", "SW": "दक्षिण-पश्चिम", "W": "पश्चिम", "NW": "उत्तर-पश्चिम",
}

# Keyed on the bare disease label (crop-independent — Phytophthora infestans is "late blight"
# on both tomato and potato, and the corpus names it identically), matching Tile.label exactly.
#  Deliberately without the word "रोग" (disease) in the value — the sentence template below
#  supplies it once ("... रोग है"), and a name that also carried it produced a doubled
#  "रोग रोग है" for every entry that did (caught by running the corn fixture through this file).
DISEASE_NAME_HI = {
    "early_blight": "अगेती झुलसा (अर्ली ब्लाइट)",
    "late_blight": "पछेती झुलसा (लेट ब्लाइट)",
    "bacterial_spot": "जीवाणु धब्बा (बैक्टीरियल स्पॉट)",
    "septoria_leaf_spot": "सेप्टोरिया पत्ती धब्बा",
    "leaf_mold": "पत्ती फफूंद (लीफ मोल्ड)",
    "yellow_leaf_curl_virus": "पीत शिरा मोड़क विषाणु (यलो लीफ कर्ल वायरस)",
    "common_rust": "सामान्य रतुआ (कॉमन रस्ट)",
    "gray_leaf_spot": "ग्रे लीफ स्पॉट",
    "northern_leaf_blight": "उत्तरी पत्ती झुलसा",
}

# Best-effort match against the schedule's own action text (e.g. "Apply Mancozeb"), keyed on
# the same product labels treatment_costs.json uses. A miss — the LLM polish step in the
# Planner rewrote the label, say — falls through to GENERIC_KIND_HI, never to a runtime guess.
PRODUCT_LABEL_HI = {
    "Mancozeb": "मैंकोजेब", "Chlorothalonil": "क्लोरोथैलोनिल",
    "Copper oxychloride": "कॉपर ऑक्सीक्लोराइड",
    "Cymoxanil + mancozeb (systemic)": "साइमोक्सानिल + मैंकोजेब",
    "Metalaxyl + mancozeb (systemic)": "मेटालैक्सिल + मैंकोजेब",
    "Azoxystrobin": "एज़ोक्सिस्ट्रोबिन", "Difenoconazole": "डाइफेनोकोनाज़ोल",
    "Propiconazole": "प्रोपिकोनाज़ोल", "Tebuconazole": "टेबुकोनाज़ोल",
    "Pyraclostrobin": "पायराक्लोस्ट्रोबिन", "Imidacloprid": "इमिडाक्लोप्रिड",
    "Thiamethoxam": "थायामेथोक्साम", "Neem oil": "नीम तेल",
}

# Exact match against the schedule's action text, for the small closed vocabulary the Planner
# actually emits for non-spray steps (see REMOVAL_PATTERNS in planner.py). Deliberately exact,
# not substring: "kind" alone is not proof of *what* the other-kind step is — the Planner's
# own fallback bucket also uses "other" for a sentence it could not classify at all (a corn
# crop-rotation note, say), and claiming that was a removal instruction would be a fabrication
# this table exists specifically to avoid. Anything not in this dict falls through to the
# honest, non-specific GENERIC_KIND_HI phrase instead of guessing.
ACTION_LABEL_HI = {
    "Remove infected plants": "रोगग्रस्त पौधों को जड़ सहित उखाड़कर खेत से दूर नष्ट कर दें।",
    "Stop overhead irrigation": "ऊपर से पानी देना (स्प्रिंकलर) तुरंत बंद कर दें।",
    "Remove infected foliage": "रोगग्रस्त पत्तियाँ तोड़कर खेत से दूर जला दें।",
    "Prune affected foliage": "प्रभावित पत्तियाँ काटकर हटा दें।",
    "Re-scan field": "खेत की दोबारा जाँच करवाएँ।",
}

#  No lead-in word baked in here (contrast ACTION_LABEL_HI's fuller sentences) — _hi_action_
#  sentence always prepends "आज ही"/"फिर", and a phrase repeating "आज ही" inside itself as well
#  reads as a stutter in Hindi.
GENERIC_KIND_HI = {
    "spray": "अनुशंसित दवा का छिड़काव करें।",
    "other": "योजना में दी गई सलाह के अनुसार उचित कदम उठाएँ।",
    "monitor": "खेत की बारीकी से निगरानी करें।",
    "rescan": "खेत की दोबारा जाँच करवाएँ।",
}


def dominant_disease(state: RunState) -> str | None:
    """Same rule the Agronomist uses — most common non-healthy tile label — kept local rather
    than imported so Reporter's only dependency stays the shared RunState."""
    labels = [t.label for t in state.scored_tiles if t.label != "healthy"]
    return Counter(labels).most_common(1)[0][0] if labels else None


def severity_band(pct: float) -> tuple[str, str]:
    """(english, hindi). What ties the Hindi brief to severity rather than just the raw number."""
    if pct >= 50:
        return "severe", "गंभीर"
    if pct >= 20:
        return "moderate", "मध्यम"
    return "mild", "हल्का"


def _first_immediate_sentence(plan_draft: str) -> str | None:
    """Fallback for when state.schedule is empty — reads plan_draft directly so the brief still
    has a first action if Reporter is ever exercised before the Planner has run."""
    in_section = False
    for raw in plan_draft.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            in_section = line.startswith("## Immediate action")
            continue
        if in_section and line:
            return MARKER_RE.sub("", line).strip()
    return None


def _rescan_days(state: RunState) -> int:
    for item in state.schedule or []:
        if item.get("kind") == "rescan":
            return int(item["day_offset"])
    return 7


def _hi_action_sentence(item: dict, lead: str) -> str:
    action = (item or {}).get("action", "")
    if action in ACTION_LABEL_HI:
        return f"{lead} {ACTION_LABEL_HI[action]}"
    for label, hi_name in PRODUCT_LABEL_HI.items():
        if label in action:
            return f"{lead} {hi_name} का छिड़काव करें।"
    return f"{lead} {GENERIC_KIND_HI.get((item or {}).get('kind'), GENERIC_KIND_HI['other'])}"


def _en_action_sentence(item: dict, lead: str, fallback: str | None = None) -> str | None:
    """A day-0 step as one short sentence, with the dose but not the reasoning.

    The Planner's `note` is the grounded corpus sentence, and pasting it here was the first
    version of this brief: it produced nine sentences containing "gives curative action on
    tissue already infected" and "because treated surfaces are recontaminated by sporulating
    tissue left in place". Both are true, both are cited, and neither belongs in a six-sentence
    brief for someone who wants to know what to do this morning — the plan panel above already
    carries the full sentence and its source. The Hindi brief was built from short phrases from
    the start; this makes the English match rather than the other way round.

    The dose is kept, because it is the one number the farmer has to get right, and dropping it
    would make the brief say "spray this" without saying how much.
    """
    action = (item or {}).get("action", "").strip()
    if not action:
        return f"{lead} {fallback}" if fallback else None
    # Lower-cased because it follows "Today," mid-sentence. Only the first character, so a
    # product name keeps its capital: "Then, apply Cymoxanil + mancozeb".
    action = action[0].lower() + action[1:]
    dose = DOSE_RE.search((item or {}).get("note", "") or "")
    if dose:
        amount = f"{dose.group(1)} to {dose.group(2)}" if dose.group(2) else dose.group(1)
        unit = "grams" if dose.group(3).lower().startswith("g") else "millilitres"
        return f"{lead} {action}, {amount} {unit} per litre of water."
    return f"{lead} {action}."


def _is_specific(item: dict) -> bool:
    """Can this step be described as a particular thing to do, rather than a gesture at the plan?

    A step the Planner could not classify carries a deliberately vague label, and two of them
    in a row turned the corn brief into "Today, follow plan guidance. Then, follow plan
    guidance." — six sentences of which two said nothing. The step is not wrong and its real
    sentence is still in the schedule note and the plan; it just cannot be summarised, and a
    brief this short should spend its two action lines on the ones that can be.
    """
    action = item.get("action", "")
    return action in ACTION_LABEL_HI or any(label in action for label in PRODUCT_LABEL_HI)


def _schedule_day0(state: RunState) -> list[dict]:
    """Day-0 steps, in plan order, preferring the ones that can be stated specifically."""
    day0 = [i for i in (state.schedule or []) if i.get("day_offset") == 0]
    return [i for i in day0 if _is_specific(i)] or day0


def run_reporter(state: RunState) -> RunState:
    """Write the English and Hindi farmer briefs from facts already on the state."""
    if not state.plan_draft:
        # Mirrors the Planner's own defensive contract: BLOCK, clean field and insufficient
        # context all leave plan_draft null, and this function must be safe to call regardless
        # of which one it was, without re-deriving why.
        state.apply("reporter.skipped.no_plan")
        return state

    disease_label = dominant_disease(state)
    spread = state.spread or {}
    pct = float(spread.get("pct_affected") or 0.0)
    clusters = int(spread.get("clusters") or 0)
    direction = spread.get("direction")
    crop = state.crop
    disease_en = (disease_label or "a crop disease").replace("_", " ")
    band_en, band_hi = severity_band(pct)

    day0 = _schedule_day0(state)
    first_item = day0[0] if day0 else {}
    first_note = first_item.get("note") or _first_immediate_sentence(state.plan_draft)
    second_item = day0[1] if len(day0) > 1 else None
    rescan_days = _rescan_days(state)

    en = [
        f"Your {crop} field has {disease_en}.",
        f"About {round(pct)} out of every 100 plants we checked are affected"
        + (f", spread across {clusters} patch{'es' if clusters != 1 else ''}." if clusters else "."),
    ]
    if direction:
        en.append(f"The disease is moving toward the {COMPASS_EN.get(direction, direction)} side of the field.")
    en.append(
        _en_action_sentence(first_item, "Today,", fallback=first_note)
        or "Today, treat the affected area as the plan advises."
    )
    if second_item:
        en.append(_en_action_sentence(second_item, "Then,"))
    en.append(f"Check the field again in {rescan_days} days.")
    en = [s for s in en if s][:MAX_SENTENCES]

    hi = [
        f"आपके {CROP_HI.get(crop, crop)} खेत में {band_hi} {DISEASE_NAME_HI.get(disease_label, 'पौधों की बीमारी')} रोग है।",
        f"जाँचे गए हर 100 पौधों में से लगभग {round(pct)} पौधे प्रभावित हैं"
        + (f", जो {clusters} जगह फैले हैं।" if clusters else "।"),
    ]
    if direction:
        hi.append(f"रोग खेत के {COMPASS_HI.get(direction, direction)} की ओर बढ़ रहा है।")
    hi.append(_hi_action_sentence(first_item, "आज ही"))
    if second_item:
        hi.append(_hi_action_sentence(second_item, "फिर"))
    hi.append(f"{rescan_days} दिन बाद खेत की दोबारा जाँच करें।")
    hi = [s for s in hi if s][:MAX_SENTENCES]

    report = {"en": " ".join(en), "hi": " ".join(hi)}
    state.apply(f"reporter.brief.{band_en}.{len(en)}_en_{len(hi)}_hi_sentences", report=report)
    state.apply("reporter.done")
    return state


def reporter_summary(state: RunState) -> str:
    if not state.report or not state.report.get("en"):
        return "no report — no verified plan"
    en, hi = state.report.get("en", ""), state.report.get("hi", "")
    return f"en: {en.count('.')} sentence(s), {len(en)} chars | hi: {hi.count('।')} sentence(s), {len(hi)} chars"

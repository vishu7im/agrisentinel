"""Agronomist Agent — retrieved passages in, a cited treatment plan out.

    from agents.agronomist import run_agronomist
    run_agronomist(state)      # writes state.plan_draft and state.sources

Reads the disease and severity the earlier agents wrote, retrieves from the corpus, and drafts
a plan in which every sentence carries the id of the passage backing it. It writes no advice
of its own, and this is the phase where that stops being a slogan: the LLM being prompted here
knows a great deal of agronomy, and almost all of it has to be refused.

**Three outcomes, and the two that are not a plan matter most.**

- *No infection* — nothing to treat. A clean field gets no plan, not a plan that says the
  field is clean. Emits `agronomist.skipped.clean_field`.
- *Not covered* — the corpus does not discuss this disease. Emits
  `agronomist.insufficient_context` and leaves plan_draft null for the Verifier to BLOCK on.
  A plan assembled from loosely related passages is worse than no plan, because it arrives
  with citations attached and therefore looks checked.
- *Drafted* — plan_draft is markdown, one sentence per line, each ending in a marker.

**Coverage is a containment test, not a score threshold.** The obvious design is to refuse
when the best retrieval score falls below some floor. It does not work on this corpus, and the
numbers are in agents/rag/retrieve.py: in-domain queries bottom out at 0.110 and out-of-domain
queries reach 0.104, so the populations overlap and no cut separates them. What does separate
them is that a corpus covering a disease says its name. So the test is whether the retrieved
passages actually contain the disease phrase the Diagnostician handed us.

**The LLM is optional.** With no GEMINI_API_KEY, or on a timeout, `draft_extractive` composes
the plan from the retrieved sentences themselves. That output is grounded by construction —
every line is a sentence lifted from the passage it cites — so the fallback is not a degraded
mode in the way that matters here. It is less fluent, and completely honest.

**One thing A7 must know:** the diagnosis line states the affected percentage and cluster
count, which come from the field scan and appear in no passage. Its citation backs the
description of the disease, not the numbers. A grounding check that demands corpus support for
"18.4%" will flag a sentence that is true and correctly sourced.
"""

from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from agents import llm
from agents.drafting import (
    MARKER_RE,
    cited_lines,
    draft_extractive,
    draft_llm,
    unmarked_lines,
    valid_markers,
)
from agents.dispute import dispute
from agents.prompts import INSUFFICIENT
from agents.rag.retrieve import retriever, to_sources
from agents.state import RunState

# One query per section the plan will have, because no single string reaches all of them: the
# disease document, the spray-practice note and the resistance guidance share almost no
# vocabulary. Asked once for "late blight", the plan would have had nothing to say about how
# to apply what it recommends.
#
# The third element is whether the section must be about *this disease*. Where it is true, the
# retriever is required to return only chunks naming the disease, and an empty result is a
# correct result. Where it is false — how to hold a sprayer, why to rotate a mode of action —
# the advice is the same whatever is growing, and demanding the disease name would reject
# every document that gives it.
SECTIONS: tuple[tuple[str, str, bool], ...] = (
    ("identification", "{disease} identification symptoms appearance lesions", True),
    ("first_response", "{disease} first response remove destroy infected foliage sanitation", True),
    ("chemical", "{disease} chemical control fungicide grams per litre of water", True),
    ("application", "spray timing early morning evening rain wind coverage leaf underside", False),
    ("followup", "{disease} follow-up re-inspect seven days after application", True),
    ("resistance", "fungicide resistance rotation mode of action repeated use", False),
)

K_PER_QUERY = 2

# The classifier's own class list is the authority on what diseases exist. Reading it here
# rather than hardcoding eleven strings means retraining on a twelfth disease cannot leave
# this file quietly disagreeing with the model about what the model can say.
CLASSES_PATH = Path(__file__).resolve().parent.parent / "ml" / "artifacts" / "model_classes.json"


def disease_phrase(label: str) -> str:
    """Tile label -> the words a document would use. `yellow_leaf_curl_virus` -> that phrase."""
    return label.replace("_", " ").strip().lower()


def dominant_disease(state: RunState) -> tuple[str | None, int]:
    """The most common non-healthy label among scored tiles, and how many tiles carry it.

    One disease, not all of them. A field with 30 late blight tiles and one septoria tile has
    late blight; drafting for both would produce a plan whose first recommendation is for a
    problem the farmer does not have, and the farmer reads from the top.
    """
    labels = [t.label for t in state.scored_tiles if t.label != "healthy"]
    if not labels:
        return None, 0
    label, count = Counter(labels).most_common(1)[0]
    return label, count


@lru_cache(maxsize=1)
def disease_vocabulary() -> tuple[str, ...]:
    """Every disease the classifier can emit, as the phrase a document would use."""
    keys = json.loads(CLASSES_PATH.read_text(encoding="utf-8"))["class_keys"]
    return tuple(sorted({disease_phrase(k.split("__", 1)[1]) for k in keys if "healthy" not in k}))


def other_diseases(disease: str) -> tuple[str, ...]:
    """The disease phrases that are not this one — passed to the retriever as `exclude`.

    Substring-overlapping names are dropped from the exclusion set rather than trusted to a
    string comparison, so a future class like "late blight (tuber)" cannot end up excluding
    the very sections it belongs to.
    """
    return tuple(d for d in disease_vocabulary() if d != disease and d not in disease and disease not in d)


def retrieve_sections(disease: str, crop: str) -> dict[str, list]:
    """{section: hits}. Retrieval is done once, per section, and reused by both drafters."""
    index = retriever()
    exclude = other_diseases(disease)
    return {
        name: index.search(
            template.format(disease=disease),
            k=K_PER_QUERY,
            crop=crop,
            require=disease if scoped else None,
            exclude=exclude,
            # A section that is not about the disease is about general practice, and general
            # practice comes from the documents written for it, not from another disease's
            # monograph that happens to share a phrase.
            agnostic_only=not scoped,
        )
        for name, template, scoped in SECTIONS
    }


def collect_sources(sections: dict[str, list]) -> list[dict]:
    """Every retrieved chunk, deduplicated, in verification.sources shape."""
    best = {}
    for hits in sections.values():
        for hit in hits:
            if hit.id not in best or hit.score > best[hit.id].score:
                best[hit.id] = hit
    return to_sources(list(best.values()))


def covers(sections: dict[str, list]) -> bool:
    """Does the corpus actually describe this disease?

    The disease-scoped searches already refuse anything that does not name it, so an empty
    identification section means the corpus has nothing on this disease at all. That is the
    coverage test — a containment check, not the score threshold the obvious design reaches
    for and which the measurements in retrieve.py show cannot work here.
    """
    return bool(sections.get("identification"))


def rewrite_feedback(state: RunState) -> list[str]:
    """The sentences the Verifier rejected, if its last ruling was REWRITE. Empty otherwise."""
    verification = state.verification or {}
    if verification.get("status") != "REWRITE":
        return []
    return list(verification.get("unsupported_claims") or [])


def rejected_chunks(rejected: list[str]) -> set[str]:
    """The chunk ids the rejected sentences cited, so the extractive drafter can move past them.

    A rejected sentence with no marker names no chunk and contributes nothing here, which is
    correct: there is no passage to move past, and the extractive drafter could not have
    produced an unmarked line in the first place.
    """
    return {m.group(1) for m in (MARKER_RE.search(line) for line in rejected) if m}


# --- the agent ---------------------------------------------------------------------------

def run_agronomist(state: RunState) -> RunState:
    """Draft a grounded treatment plan, or decline and say why."""
    # The Consensus agent found the two models describing different fields — most often the
    # classifier reporting disease across a canopy a whole-image model reads as clean. Declined
    # here, before retrieval, because drafting a plan just so the Verifier can throw it away
    # spends a retrieval and an LLM round trip to arrive somewhere already known.
    #
    # Checked before the clean-field branch on purpose: a not-a-crop-photo run has had every
    # scored tile rewritten to `skipped_not_crop`, so it would otherwise fall through as a clean
    # field and produce silence instead of a refusal.
    if dispute(state):
        state.apply("agronomist.skipped.contested")
        state.apply("agronomist.done")
        return state

    disease_label, tile_count = dominant_disease(state)
    if disease_label is None:
        state.apply("agronomist.skipped.clean_field")
        state.apply("agronomist.done")
        return state

    # The Spread Analyst is the authority on how much of the field is affected, and this agent
    # obeys it rather than re-deriving the answer from tile labels. They disagree in exactly
    # one case, and it is the case that matters: a photograph of bare soil where a single tile
    # survived the Scout's mask and was labelled at 0.10 confidence. Spread already declines
    # that one — below MIN_SCORED_TILES there is no field to take a ratio over — and reports
    # 0% affected. Reading the tiles directly instead, this agent drafted a full treatment
    # plan for yellow leaf curl virus off that one tile, cited and fluent, for a picture of
    # dirt. Same failure as A5's, one stage later: an honest "I could not measure this" is
    # only worth anything if the next consumer reads it.
    if not (state.spread or {}).get("pct_affected"):
        state.apply("agronomist.skipped.no_measurable_field")
        state.apply("agronomist.done")
        return state

    disease = disease_phrase(disease_label)
    sections = retrieve_sections(disease, state.crop)
    sources = collect_sources(sections)
    state.apply(f"agronomist.retrieved.{len(sources)}_chunks", sources=sources)

    if not covers(sections):
        # Sources are still published: "we searched and found nothing that covers this" is a
        # more useful thing for the UI to show than an empty drawer, and A7 needs to see the
        # same evidence to rule on it.
        state.apply("agronomist.insufficient_context")
        state.apply("agronomist.done")
        return state

    state.apply(f"agronomist.disease.{disease_label}.{tile_count}_tiles")

    # A rewrite arrives the same way everything else does — as something already written into
    # the run state. The Verifier does not call this function and this function does not call
    # the Verifier; it just notices that the last ruling on the board was REWRITE and reads the
    # sentences that failed. That is what keeps the retry loop inspectable: the reason for the
    # second draft is on the event log and in verification.unsupported_claims, not in a
    # parameter passed between two agents behind the log's back.
    rejected = rewrite_feedback(state)
    if rejected:
        state.apply(f"agronomist.redraft.{len(rejected)}_rejected")

    draft = None
    if llm.available():
        draft, note = draft_llm(state, disease, sources, rejected)
        if note == INSUFFICIENT:
            # The model read the passages and said they do not cover this. That is a judgement
            # about the evidence, and the extractive drafter is in no position to overrule it:
            # it cannot assess coverage at all, it assembles whatever retrieval returned. So a
            # refusal ends the agent rather than falling through to a plan, which would mean
            # the one component that actually looked at the passages gets ignored whenever it
            # says no. Transport failures below are different — there, nothing was judged.
            state.apply("agronomist.llm_refused")
            state.apply("agronomist.insufficient_context")
            state.apply("agronomist.done")
            return state
        if draft is None:
            state.apply("agronomist.llm_unavailable")
        elif not cited_lines(draft, valid_markers(sources)):
            # Not one usable citation in the whole draft — see `cited_lines`. Dropped for the
            # extractive one below, which is grounded by construction.
            state.apply("agronomist.llm_uncited")
            draft = None

    if draft is None:
        queries = {name: template.format(disease=disease) for name, template, _ in SECTIONS}
        draft = draft_extractive(state, disease, sections, queries, rejected_chunks(rejected))
        state.apply("agronomist.drafted.extractive")
    else:
        state.apply("agronomist.drafted.llm")

    remaining = unmarked_lines(draft, valid_markers(sources))
    if remaining:
        # Left in the draft deliberately, not stripped. These are exactly the sentences the
        # Verifier exists to catch, and pre-filtering them would hand A7 a clean plan and hide
        # the failure it is supposed to report.
        state.apply(f"agronomist.unmarked.{len(remaining)}_sentences")

    state.apply("agronomist.done", plan_draft=draft)
    return state


REASONS = {
    "agronomist.skipped.clean_field": "clean field, nothing to treat",
    "agronomist.skipped.no_measurable_field": "too little crop in frame to measure",
    "agronomist.insufficient_context": "corpus does not cover this disease",
}


def agronomist_summary(state: RunState) -> str:
    if not state.plan_draft:
        reason = next((why for event, why in REASONS.items() if event in state.events), "not drafted")
        return f"no plan — {reason} | {len(state.sources)} chunk(s) retrieved"
    lines = [ln for ln in state.plan_draft.splitlines() if ln.strip() and not ln.startswith("#")]
    cited = len(lines) - len(unmarked_lines(state.plan_draft, valid_markers(state.sources)))
    return (
        f"plan: {len(lines)} sentence(s), {cited} cited | "
        f"{len(state.sources)} source(s) | {len({s['id'].split('#')[0] for s in state.sources})} document(s)"
    )

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

import re
from collections import Counter

from agents import llm
from agents.prompts import (
    AGRONOMIST_REPAIR,
    AGRONOMIST_SYSTEM,
    AGRONOMIST_USER,
    INSUFFICIENT,
    format_passages,
)
from agents.rag.retrieve import retriever, to_sources
from agents.state import RunState

MARKER_RE = re.compile(r"\[(doc_\d+#p\d+)\]\s*$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

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


def retrieve_sections(disease: str, crop: str) -> dict[str, list]:
    """{section: hits}. Retrieval is done once, per section, and reused by both drafters."""
    index = retriever()
    return {
        name: index.search(
            template.format(disease=disease),
            k=K_PER_QUERY,
            crop=crop,
            require=disease if scoped else None,
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


def valid_markers(sources: list[dict]) -> set[str]:
    return {s["id"] for s in sources}


def unmarked_lines(draft: str, allowed: set[str]) -> list[str]:
    """Content lines that do not end with a marker drawn from the retrieved set."""
    offenders = []
    for line in draft.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = MARKER_RE.search(line)
        if not match or match.group(1) not in allowed:
            offenders.append(line)
    return offenders


# --- drafting ----------------------------------------------------------------------------


def _best_sentence(text: str, query: str) -> str:
    """The sentence in a passage that most covers the query terms, preferring earlier ones.

    Deterministic and dull on purpose — this runs when the LLM is unavailable, which is when
    surprises are least affordable.
    """
    terms = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 3}
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if len(s.strip()) > 40]
    if not sentences:
        return text.strip()
    scored = [
        (sum(t in s.lower() for t in terms), -i, s) for i, s in enumerate(sentences)
    ]
    return max(scored)[2]


def draft_extractive(state: RunState, disease: str, sources: list[dict]) -> str:
    """Compose the plan from the retrieved sentences themselves. Grounded by construction.

    Each line is a sentence copied out of the passage whose id it carries, so the marker is
    not an assertion about where the claim came from — it is where the claim came from.
    """
    by_id = {s["id"]: s for s in sources}
    spread = state.spread or {}
    used: set[str] = set()

    def line(section: str) -> str | None:
        query = SECTION_QUERIES[section].format(disease=disease)
        hits = retriever().search(query, k=3, crop=state.crop)
        for hit in hits:
            if hit.id in by_id and hit.id not in used:
                used.add(hit.id)
                return f"{_best_sentence(by_id[hit.id]['text'], query)} [{hit.id}]"
        return None

    identification = line("identification")
    # The diagnosis sentence is built from the scan, and cited to whichever passage describes
    # the disease — see the note in the module docstring about what A7 should not flag.
    anchor = MARKER_RE.search(identification).group(1) if identification else sources[0]["id"]
    direction = spread.get("direction")
    heading = (
        f"{disease.capitalize()} is present across {spread.get('pct_affected', 0.0)}% of the "
        f"scanned field in {spread.get('clusters', 0)} cluster(s)"
        + (f", trending {direction}." if direction else ", with no dominant direction.")
        + f" [{anchor}]"
    )

    blocks = [
        ("## Diagnosis summary", [heading, identification]),
        ("## Immediate action (next 48 hours)", [line("first_response"), line("chemical"), line("application")]),
        ("## Follow-up", [line("followup"), line("resistance")]),
    ]
    parts = []
    for title, lines in blocks:
        body = [ln for ln in lines if ln]
        if body:
            parts.append(title + "\n\n" + "\n".join(body))
    return "\n\n".join(parts)


def draft_llm(state: RunState, disease: str, sources: list[dict]) -> tuple[str | None, str]:
    """(draft, note). draft is None when the model refused or the call failed."""
    spread = state.spread or {}
    user = AGRONOMIST_USER.format(
        crop=state.crop,
        disease=disease,
        pct_affected=spread.get("pct_affected", 0.0),
        clusters=spread.get("clusters", 0),
        direction=spread.get("direction") or "no dominant direction",
        passages=format_passages(sources),
    )
    result = llm.complete(AGRONOMIST_SYSTEM, user)
    if not result.ok:
        return None, result.error or "llm unavailable"
    if INSUFFICIENT in result.text:
        return None, INSUFFICIENT

    draft = result.text.strip()
    offenders = unmarked_lines(draft, valid_markers(sources))
    if offenders:
        # One repair attempt only. The Verifier in A7 owns the retry loop and has veto power;
        # duplicating it here would mean two independent retry budgets and a plan that could
        # be rewritten five times while each component believed it had allowed two.
        repair = llm.complete(
            AGRONOMIST_SYSTEM,
            AGRONOMIST_REPAIR.format(offenders="\n".join(offenders), draft=draft),
        )
        if repair.ok and INSUFFICIENT not in repair.text:
            draft = repair.text.strip()
    return draft, result.provider


# --- the agent ---------------------------------------------------------------------------


def run_agronomist(state: RunState) -> RunState:
    """Draft a grounded treatment plan, or decline and say why."""
    disease_label, tile_count = dominant_disease(state)
    if disease_label is None:
        state.apply("agronomist.skipped.clean_field")
        state.apply("agronomist.done")
        return state

    disease = disease_phrase(disease_label)
    sources = retrieve_for(disease, state.crop)
    state.apply(f"agronomist.retrieved.{len(sources)}_chunks", sources=sources)

    if not sources or not covers(sources, disease):
        # Sources are still published: "we searched and found nothing that covers this" is a
        # more useful thing for the UI to show than an empty drawer, and A7 needs to see the
        # same evidence to rule on it.
        state.apply("agronomist.insufficient_context")
        state.apply("agronomist.done")
        return state

    state.apply(f"agronomist.disease.{disease_label}.{tile_count}_tiles")

    draft, note = (None, "llm not configured")
    if llm.available():
        draft, note = draft_llm(state, disease, sources)
        if draft is None:
            state.apply("agronomist.llm_unavailable" if note != INSUFFICIENT else "agronomist.llm_refused")

    if draft is None:
        draft = draft_extractive(state, disease, sources)
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


def agronomist_summary(state: RunState) -> str:
    if not state.plan_draft:
        reason = "no plan — " + (
            "clean field" if "agronomist.skipped.clean_field" in state.events else "insufficient context"
        )
        return f"{reason} | {len(state.sources)} chunk(s) retrieved"
    lines = [ln for ln in state.plan_draft.splitlines() if ln.strip() and not ln.startswith("#")]
    cited = len(lines) - len(unmarked_lines(state.plan_draft, valid_markers(state.sources)))
    return (
        f"plan: {len(lines)} sentence(s), {cited} cited | "
        f"{len(state.sources)} source(s) | {len({s['id'].split('#')[0] for s in state.sources})} document(s)"
    )

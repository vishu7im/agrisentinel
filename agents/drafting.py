"""How a plan gets written — the two drafters, and the marker check that judges both.

Split out of agronomist.py so that file reads as the agent's decisions (which disease, is it
covered, whose answer wins) rather than as prose assembly. Both drafters here take retrieved
passages and return markdown; neither decides whether a plan should exist at all.

**Two drafters, one guarantee.** `draft_llm` asks Gemini and is fluent but has to be policed —
`unmarked_lines` is what polices it. `draft_extractive` copies sentences out of the passages
themselves, so its markers cannot be wrong: the citation is not a claim about where the text
came from, it is where the text came from. The extractive path runs whenever there is no key
or the call fails, which at a venue with no wifi is the normal case, not the sad path.
"""

from __future__ import annotations

import re

from agents import llm
from agents.claims import DOSE_RE
from agents.prompts import (
    AGRONOMIST_REPAIR,
    AGRONOMIST_SYSTEM,
    AGRONOMIST_USER,
    INSUFFICIENT,
    VERIFIER_REWRITE,
    format_passages,
)
from agents.state import RunState

MARKER_RE = re.compile(r"\[(doc_\d+#p\d+)\]\s*$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# A sentence shorter than this is a fragment of a split, not a claim worth quoting.
MIN_SENTENCE_CHARS = 40

# Quoted from doc_04#p4, not decided here — see the note in draft_extractive.
SYSTEMIC_THRESHOLD_PCT = 25.0


def valid_markers(sources: list[dict]) -> set[str]:
    return {s["id"] for s in sources}


def unmarked_lines(draft: str, allowed: set[str]) -> list[str]:
    """Content lines that do not end with a marker drawn from the retrieved set.

    Both halves matter. A line with no marker is an uncited claim; a line whose marker is not
    in `allowed` is worse, because the model invented a plausible-looking id and the citation
    now points at nothing while looking exactly like one that points at something.
    """
    offenders = []
    for line in draft.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = MARKER_RE.search(line)
        if not match or match.group(1) not in allowed:
            offenders.append(line)
    return offenders


def cited_lines(draft: str, allowed: set[str]) -> int:
    """How many content lines carry a marker from the retrieved set.

    Zero means the model ignored rule 2 wholesale rather than slipping on a sentence, and that
    is a different condition from a draft with two bad lines in it. Measured, and it is not
    hypothetical: with the 2.5-flash quota exhausted the fall-through in `llm.complete_first`
    reached a model that returned eleven fluent, correct, entirely unmarked sentences three
    times in a row, repair pass included. The Verifier did exactly its job and stripped all
    eleven, and the run finished `status: complete` with no plan, no schedule and no farmer
    brief — strictly worse than the extractive draft that same run would have produced offline.

    So the caller checks this and falls back. It does not weaken the Verifier: a draft with
    *some* unmarked lines still goes to it untouched, because those are the sentences it exists
    to catch. This is only the case where there is nothing to check.
    """
    return sum(
        1
        for line in draft.splitlines()
        if (stripped := line.strip())
        and not stripped.startswith("#")
        and (match := MARKER_RE.search(stripped))
        and match.group(1) in allowed
    )


def best_sentence(text: str, query: str, must_dose: bool = False) -> str:
    """The sentence in a passage that best covers the query terms, preferring earlier ones.

    Deterministic and dull on purpose — this runs when the LLM is unavailable, which is when
    surprises are least affordable.

    `must_dose` outranks word overlap, and exists because word overlap alone got the corn plan
    wrong. Asked for chemical control of northern leaf blight, it picked the first sentence of
    the chemical section — "The decision to spray maize is economic and depends on growth
    stage..." — which shares more query terms than the sentence immediately after it that names
    propiconazole at 1.0 millilitre per litre. Nothing downstream could recover from that: the
    Planner had no product to schedule and no dose to cost, so it emitted "Follow plan
    guidance" and the farmer brief said "Today, follow plan guidance. Then, follow plan
    guidance." A section headed "Chemical control" is being asked what to spray and how much,
    and a sentence that answers neither is not the best sentence in it however it scores.
    """
    terms = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 3}
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if len(s.strip()) > MIN_SENTENCE_CHARS]
    if not sentences:
        return text.strip()
    dosed = [s for s in sentences if DOSE_RE.search(s)] if must_dose else []
    candidates = dosed or sentences
    return max((sum(t in s.lower() for t in terms), -i, s) for i, s in enumerate(candidates))[2]


def draft_extractive(
    state: RunState,
    disease: str,
    sections: dict[str, list],
    queries: dict[str, str],
    avoid: set[str] = frozenset(),
) -> str:
    """Compose the plan from the retrieved sentences themselves. Grounded by construction.

    `avoid` holds chunk ids the Verifier rejected on a previous pass. Marking them used rather
    than filtering them out means each section falls through to its next-best passage, so a
    rewrite produces a different plan instead of the same one again — which is the only thing
    that makes the retry budget worth spending.
    """
    spread = state.spread or {}
    used: set[str] = set(avoid)
    queries = dict(queries)

    # A chemical section usually holds two recommendations — a protectant for localised
    # infection, a systemic for a field past that — and picking by word overlap alone returned
    # "a protectant is sufficient" for a field 50% affected. The threshold and the wording
    # below are quoted from the corpus, not decided here: doc_04#p4 says "Where infection
    # exceeds roughly 25 percent of the scanned area ... a systemic combination". This steers
    # which of the passage's own sentences is selected; it adds no advice, because whichever
    # sentence wins is still copied verbatim out of the passage that is cited.
    if float(spread.get("pct_affected") or 0.0) >= SYSTEMIC_THRESHOLD_PCT:
        queries["chemical"] += " systemic where infection exceeds continuing wet weather"

    def line(section: str) -> str | None:
        for hit in sections.get(section, []):
            if hit.id in used:
                continue
            used.add(hit.id)
            sentence = best_sentence(hit.text, queries[section], must_dose=section == "chemical")
            return f"{sentence} [{hit.id}]"
        return None

    # The diagnosis sentence is built from the scan and cited to the passage describing the
    # disease — see the note in agronomist.py about what A7 should not flag. The anchor comes
    # from the identification section specifically, so a plan for late blight can never cite
    # the early blight document for what the disease is.
    direction = spread.get("direction")
    diagnosis = (
        f"{disease.capitalize()} is present across {spread.get('pct_affected', 0.0)}% of the "
        f"scanned field in {spread.get('clusters', 0)} cluster(s)"
        + (f", trending {direction}." if direction else ", with no dominant direction.")
        + f" [{sections['identification'][0].id}]"
    )

    blocks = [
        ("## Diagnosis summary", [diagnosis, line("identification")]),
        ("## Immediate action (next 48 hours)", [line("first_response"), line("chemical"), line("application")]),
        ("## Follow-up", [line("followup"), line("resistance")]),
    ]
    parts = [
        title + "\n\n" + "\n".join(body)
        for title, lines in blocks
        if (body := [ln for ln in lines if ln])
    ]
    return "\n\n".join(parts)


def draft_llm(
    state: RunState, disease: str, sources: list[dict], rejected: list[str] = ()
) -> tuple[str | None, str]:
    """(draft, note). draft is None when the model refused or the call failed.

    The caller must tell those two apart: `note == INSUFFICIENT` means the model read the
    passages and judged them insufficient, and anything else means no judgement happened.
    """
    spread = state.spread or {}
    user = AGRONOMIST_USER.format(
        crop=state.crop,
        disease=disease,
        pct_affected=spread.get("pct_affected", 0.0),
        clusters=spread.get("clusters", 0),
        direction=spread.get("direction") or "no dominant direction",
        passages=format_passages(sources),
    )
    if rejected:
        # The Verifier's ruling is appended to the same request rather than sent as a follow-up
        # turn, because the model is stateless here and a repair prompt on its own would have
        # to re-send the passages anyway. Naming the rejected sentences is the whole content of
        # the retry: told only "try again", a model rewrites the parts that were already fine.
        user += "\n\n" + VERIFIER_REWRITE.format(rejected="\n".join(rejected))
    result = llm.complete_first(AGRONOMIST_SYSTEM, user)
    if not result.ok:
        return None, result.error or "llm unavailable"
    if INSUFFICIENT in result.text:
        return None, INSUFFICIENT

    draft = result.text.strip()
    offenders = unmarked_lines(draft, valid_markers(sources))
    if offenders:
        # One repair attempt only. The Verifier in A7 owns the retry loop and has veto power;
        # a second budget here would mean a plan could be rewritten five times while each
        # component believed it had allowed two.
        repair = llm.complete_first(
            AGRONOMIST_SYSTEM,
            AGRONOMIST_REPAIR.format(offenders="\n".join(offenders), draft=draft),
        )
        if repair.ok and INSUFFICIENT not in repair.text:
            draft = repair.text.strip()
    return draft, result.provider

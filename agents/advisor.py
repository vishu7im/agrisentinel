"""Advisor Agent — the farmer's follow-up question, answered from the same corpus as the plan.

    from agents.advisor import answer
    answer(state, "Can I spray before rain?")

The farmer brief is six sentences and then the conversation stops. This is the rest of it: one
question at a time, about *this* run, grounded in the ten documents the plan was drafted from,
and cited the same way — so an answer can be checked the same way too.

**It is the Agronomist's discipline pointed at a conversational turn**, which is where a model
is most tempted to be helpful from its own knowledge. Retrieval, the drafting rules, the
allowlist and the dose table are all the existing ones; nothing here re-implements a check that
already exists somewhere else in this pipeline.

**Coverage is judged by the model, and by nothing else.** The obvious design is a relevance or
containment floor, and it does not work on this corpus — the same finding `rag/retrieve.py`
records for retrieval scores. Measured over 12 in-domain and 9 out-of-domain questions:

    retrieval score      in 0.134-0.310      out 0.140-0.198
    question containment in 0.000-1.000      out 0.000-0.333

Both populations overlap in both directions. "How does this spread?" repeats no word of the
passage that answers it; "What is the price of tomatoes in Delhi?" scores 0.333 because the
corpus is full of the word tomato. There is no cut here, and picking one anyway would produce a
threshold that looked principled and was worth nothing. So the model reads the passages and
answers INSUFFICIENT_CONTEXT, exactly as the Agronomist does — and `keep_grounded` is the net
under it, because a model answering from its own knowledge writes a sentence no passage contains.

**The offline path does not pretend to have judged.** With no key nothing can assess coverage,
so the extractive answer says so and quotes the closest passage verbatim instead of claiming to
have answered. The chat then still does something real at a venue with no wifi, which is the
normal case here rather than the sad path.

**A blocked run answers from the ruling, not the corpus.** The Verifier has veto power over the
plan, and a chat that recommended a spray it had just withheld would be a way around it. Every
question on a BLOCK or a contested run gets the refusal and its reason, with no network at all.
"""

from __future__ import annotations

import re

from agents import llm
from agents.checks import chemical_violations, dominant_label, dose_violations
from agents.claims import GROUNDING_MIN, containment, parse_claims
from agents.agronomist import disease_phrase, dominant_disease, other_diseases
from agents.dispute import dispute, dispute_parts
from agents.drafting import best_sentence
from agents.prompts import ADVISOR_SYSTEM, ADVISOR_USER, INSUFFICIENT, format_history, format_passages
from agents.rag.retrieve import retriever, to_sources
from agents.state import RunState

# Four passages, the same budget the Agronomist gives a whole plan section. A chat answer is
# three sentences; more context buys nothing but a longer prompt and more places to wander.
K = 4

# The reply is short by construction — see rule 3 in ADVISOR_SYSTEM. This is the transport
# ceiling, not the target, and it is small enough that a model which starts writing an essay
# runs out and fails loudly rather than shipping one.
MAX_TOKENS = 500

# Long enough for a real question, short enough that the field cannot be used to smuggle a
# prompt. Enforced at the endpoint too — this is the agent's own floor, not the only one.
MAX_QUESTION_CHARS = 600

# Any marker, anywhere in a line — not `claims.MARKER_RE`, which anchors to the end because
# that is where a well-formed plan line puts it. See keep_grounded.
MARKER_ANYWHERE_RE = re.compile(r"\s*\[doc_\d+#p\d+\]")

# What a refusal says. Names what the corpus *is*, because "I can't answer that" leaves the
# farmer guessing at where the edge is and asking three more questions outside it.
NOT_COVERED = (
    "Our reference set does not cover that. It is ten agronomy documents on tomato, potato and "
    "corn diseases — how to identify them, what to spray, when to spray it and what to do "
    "afterwards. Ask me something inside that and I will answer from the documents and show "
    "you the source."
)


def run_disease(state: RunState) -> str:
    """The disease this run is about, as the words a document would use.

    `checks.dominant_label` first, because that reads the Agronomist's own
    `agronomist.disease.*` event and is therefore the *fused* label — the one the plan was
    written about, after the Consensus agent had its say. Falling back to the tiles is for runs
    that never reached the Agronomist, where there is no plan to be consistent with anyway.
    """
    label = dominant_label(state)
    if label:
        return label
    tile_label, _ = dominant_disease(state)
    return disease_phrase(tile_label) if tile_label else ""


def search(state: RunState, question: str) -> list:
    """Passages for this question: some about this disease, some about general practice.

    Two searches, not one, for the reason `agronomist.SECTIONS` already splits its queries.
    Prefixing the crop and disease is what keeps a chat answer about the field on the screen —
    but those words then dominate the ranking, and measured on "What time of day should I
    spray?" a single query returned four chunks of the late blight monograph and never reached
    the document on spray practice, so the model correctly answered that it could not see the
    answer. Half the budget is therefore reserved for the crop-agnostic documents that exist to
    answer exactly the questions a farmer asks next.

    `exclude` keeps another disease's dosing advice out of an answer about this one — the same
    failure `retrieve.py` documents for the plan, and a worse one here, because a chat answer
    arrives with no headings around it to say what it is about.
    """
    index = retriever()
    disease = run_disease(state)
    exclude = other_diseases(disease) if disease else ()
    scoped = index.search(
        " ".join(part for part in (state.crop, disease, question) if part),
        k=K - K // 2,
        crop=state.crop,
        exclude=exclude,
    )
    practice = index.search(question, k=K // 2, agnostic_only=True)
    merged = {hit.id: hit for hit in scoped + practice}
    return sorted(merged.values(), key=lambda h: -h.score)[:K]


def refusal(reason: str, text: str, sources: list[dict] | None = None) -> dict:
    return {"answer": text, "grounded": True, "provider": "advisor", "refused": reason,
            "sources": sources or []}


def withheld_answer(state: RunState) -> dict:
    """What a blocked run says to every question. No corpus, no network, no exceptions."""
    contested = dispute(state)
    why = (state.verification or {}).get("block_reason") or ""

    if contested and dispute_parts(contested)[0] == "not_crop":
        text = (
            "This photograph does not appear to show a growing crop, so there is no diagnosis "
            "to discuss. Take a photograph standing in the field, looking down at the plants, "
            "and scan again."
        )
    elif contested:
        _, label, pct = dispute_parts(contested)
        named = (label or "disease").replace("_", " ")
        text = (
            f"I cannot answer treatment questions for this scan. Our tile scanner read "
            f"{named} across {pct:g}% of the field and the whole-image cross-check disagreed, "
            "so the system withheld its advice rather than pick a side. "
            + (f"The cross-check reported: {why} " if why else "")
            + "Walk the field yourself and show this scan to your agriculture extension "
            "officer before you spray anything."
        )
    else:
        text = (
            "I cannot answer treatment questions for this scan. The safety check refused to "
            "pass the plan"
            + (f", because {why}" if why else "")
            + ". Please show this scan to your local agriculture extension officer."
        )
    return refusal("withheld", text)


def attribute(sentence: str, sources: list[dict]) -> tuple[str | None, float]:
    """The retrieved passage this sentence actually came from, and how much of it is there.

    **The marker the model wrote is a claim about provenance; this is a measurement of it.** The
    Agronomist can afford to treat a missing marker as a failure because a plan is a document
    that has to be auditable line by line, and it has a repair prompt and a rewrite loop to get
    one. A chat turn has neither, and measured on the first live question the model returned a
    near-verbatim quotation of doc_07#p2 with no marker at all — a correct, checkable, fully
    grounded sentence that would have been thrown away for a formatting slip.

    So the citation is computed from the evidence rather than taken on trust. This is strictly
    stronger than believing the model: a sentence it marked correctly still has to score against
    that passage, and one it marked wrongly is re-attributed to the passage that does contain it
    or dropped entirely.
    """
    best_id, best_score = None, 0.0
    for chunk in sources:
        score = containment(sentence, chunk)
        if score > best_score:
            best_id, best_score = chunk["id"], score
    return best_id, best_score


def keep_grounded(draft: str, sources: list[dict]) -> tuple[list[str], list[str]]:
    """(sentences that trace back to a retrieved passage, the ones that do not).

    Sentence-level rather than all-or-nothing, because a three-sentence answer where the third
    sentence wandered is still two useful sentences — and unlike the plan, there is no rewrite
    loop here to send it back to. The chemical and dose checks are all-or-nothing, and that
    difference is the point: an unsupported sentence is noise, a wrong dose is harm.
    """
    kept, dropped = [], []
    for claim in parse_claims(draft):
        # Every marker the model wrote is stripped, not just the trailing one `parse_claims`
        # recognises. It writes them mid-line as often as not — "…is wasted [doc_07#p2]." with
        # the full stop after the bracket — and since the citation is recomputed below, the
        # model's are decoration. Leaving them produced "…is wasted [doc_07#p2]. [doc_07#p2]".
        text = MARKER_ANYWHERE_RE.sub("", claim.text).strip()
        marker, score = attribute(text, sources)
        if text and marker is not None and score >= GROUNDING_MIN:
            kept.append(f"{text} [{marker}]")
        else:
            dropped.append(claim.line)
    return kept, dropped


def unsafe(draft: str) -> list[str]:
    """Reasons this answer must not ship at all. The Verifier's own two checks, reused."""
    claims = parse_claims(draft)
    return [why for _, why in chemical_violations(claims) + dose_violations(claims)]


def extractive_answer(question: str, hits: list, sources: list[dict]) -> dict:
    """The closest thing the corpus says, quoted verbatim, when there is no model to ask.

    It does not claim to have answered. Nothing offline can judge whether these passages cover
    the question — see the module docstring — so the framing says what it is: the nearest
    passage, cited, in the corpus's own words.
    """
    best = hits[0]
    sentence = best_sentence(best.text, question)
    return {
        "answer": (
            "I could not reach the language model, so I cannot answer this in my own words. "
            f"This is the closest thing our reference set says:\n\n{sentence} [{best.id}]"
        ),
        "grounded": True,
        "provider": "extractive",
        "refused": None,
        "sources": sources,
    }


def answer(state: RunState, question: str, history: list[dict] | None = None) -> dict:
    """One grounded answer about this run. Never raises.

    Returns `{answer, sources, grounded, refused, provider}`. `refused` is None, or one of
    `no_question` / `withheld` / `not_covered` / `unsafe` — a short token, so the UI can style
    a refusal without parsing prose.
    """
    question = (question or "").strip()[:MAX_QUESTION_CHARS]
    if not question:
        return refusal("no_question", "Ask me something about this scan.")

    if dispute(state) or (state.verification or {}).get("status") == "BLOCK":
        return withheld_answer(state)

    hits = search(state, question)
    if not hits:
        return refusal("not_covered", NOT_COVERED)
    sources = to_sources(hits)

    if not llm.available():
        return extractive_answer(question, hits, sources)

    spread = state.spread or {}
    result = llm.complete_first(
        ADVISOR_SYSTEM,
        ADVISOR_USER.format(
            crop=state.crop,
            disease=run_disease(state) or "no disease found",
            pct=spread.get("pct_affected", 0.0),
            recent=format_history(history or []),
            passages=format_passages(sources),
            question=question,
        ),
        max_tokens=MAX_TOKENS,
    )
    if not result.ok:
        return extractive_answer(question, hits, sources)
    if INSUFFICIENT in result.text:
        # The model read the passages and said they do not answer this. That judgement stands:
        # the extractive path cannot assess coverage at all, so falling through to it would
        # mean the one component that actually looked at the passages gets ignored when it
        # says no. A transport failure above is different — there, nothing was judged.
        return refusal("not_covered", NOT_COVERED, sources)

    draft = result.text.strip()
    if unsafe(draft):
        # A chemical off the allowlist or a dose outside its supported range. The whole answer
        # goes, not the offending sentence: this is the Verifier's BLOCK threshold, and there is
        # no reason to trust the rest of a reply that produced one.
        return extractive_answer(question, hits, sources)

    kept, dropped = keep_grounded(draft, sources)
    if not kept:
        return extractive_answer(question, hits, sources)
    return {
        "answer": "\n".join(kept),
        "grounded": not dropped,
        "provider": result.provider,
        "refused": None,
        "sources": sources,
    }



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

from agents.checks import (
    chemical_violations,
    dominant_label,
    dose_violations,
    ungrounded,
)
from agents.claims import parse_claims
from agents.dispute import dispute, dispute_parts
from agents.observer import vision_verdict
from agents.refusal import contested_report, not_field_report, refusal_report
from agents.state import RunState

# Two redrafts, then strip. Set here and nowhere else — the orchestrator reads it rather than
# keeping a count of its own, because two components each believing they own the budget is how
# a plan gets rewritten five times.
MAX_REWRITES = 2

# --- the ruling ---------------------------------------------------------------------------


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


def block(
    state: RunState,
    reason: str,
    detail: list[str],
    plainly: str,
    report: dict | None = None,
) -> RunState:
    """`reason` is the technical explanation on the refusal card; `plainly` is the clause the
    farmer brief uses. They are separate because the person holding the phone in a field does
    not need to be told which active ingredient failed an allowlist — they need to be told
    that nobody is going to give them a spray recommendation today, and why not, in one line.

    `report` overrides the standard brief, and exists for exactly one caller. `refusal_report`
    opens "Your potato field shows signs of late blight across 69.2% of the scanned area" —
    stating as fact the one claim a contested run has just decided it cannot stand behind. On
    that path the brief has to be about the disagreement, so the caller supplies it and
    `plainly` goes unused.
    """
    state.apply(f"verify.block.{len(detail)}_violations")
    state.apply(
        "verify.block",
        verification=_ruling(state, "BLOCK", detail, reason),
        plan_draft=None,
        report=report
        or refusal_report(
            state.crop, dominant_label(state) or "a disease",
            (state.spread or {}).get("pct_affected", 0.0), plainly,
        ),
        status="blocked",
    )
    return state


def contested_block(state: RunState) -> RunState:
    """Rule on a run the Consensus agent found in dispute.

    The Verifier's usual question is "is this plan supported by its sources", and on this path
    there is no plan and the answer would be irrelevant if there were: a plan for late blight
    can be perfectly grounded in the late-blight documents while the field has no late blight.
    That is the hole this whole phase was built to close, and the reason it is ruled here rather
    than left to the Agronomist is that BLOCK is the only state the contract has for "nothing
    ships", and the Verifier is the only agent allowed to enter it.
    """
    event = dispute(state) or ""
    kind, label, pct = dispute_parts(event)
    seen = vision_verdict(state)
    # The vision model's own sentence, verbatim. This is the single most convincing line on a
    # refusal card — "a wide field of young potato plants in rows of reddish-brown soil, no
    # lesions visible" is an argument a reader can check against the photograph on screen.
    observed = f' The second check reported: "{seen.visible}"' if seen.visible else ""

    if kind == "not_crop":
        return block(
            state,
            "This photograph does not show a growing crop. A whole-image check identified the "
            "subject as something other than a crop field, so the tile grid is measuring "
            "texture rather than plant health." + observed,
            ["The image was not identified as a photograph of a growing crop."],
            "the photograph does not appear to show a growing crop",
            report=not_field_report(),
        )

    disease = (label or "a disease").replace("_", " ")
    return block(
        state,
        f"Two independent checks disagree about this field. The tile classifier reports "
        f"{disease} across {pct:g}% of the scanned area; a whole-image check of the same "
        f"photograph reports no disease. Treatment advice was withheld rather than issued on "
        f"the strength of one of them." + observed,
        [
            f"Tile classifier: {disease} across {pct:g}% of the field.",
            f"Whole-image check: no disease "
            f"({seen.pct_affected}% of visible tissue, {seen.confidence}% confident).",
        ],
        "our two checks disagreed about whether this field is diseased",
        report=contested_report(state.crop, disease, pct),
    )


def run_verifier(state: RunState, attempt: int = 0) -> RunState:
    """Rule on the current draft. `attempt` is how many redrafts have already been spent."""
    if not state.plan_draft:
        if "agronomist.skipped.contested" in state.events:
            return contested_block(state)
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

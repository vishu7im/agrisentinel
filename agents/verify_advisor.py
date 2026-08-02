"""The Advisor's decision table, asserted offline.

    .venv/bin/python agents/verify_advisor.py

No network, no ONNX, no PIL. Same shape and same reason as `agents/verify_consensus.py`: what
this asserts is not "does it run" but the exact outcome of each row — whether the answer ships,
which refusal token it carries, and whether every sentence in it ends up cited.

The rows that matter are the ones where the model misbehaves. A stub `llm.complete_first` is
substituted, so a reply naming a banned chemical, a reply that quietly doubles a dose, and a
reply invented out of the model's own knowledge are all reproducible in milliseconds instead of
being things we hope never happen. Those are exactly the inputs a live demo will not produce
and a hostile judge will.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents import advisor, llm  # noqa: E402
from agents.state import RunState, Tile  # noqa: E402

PASSES = 0
FAILURES: list[str] = []


def field(disease: str = "late_blight", crop: str = "tomato", pct: float = 50.0) -> RunState:
    """A finished, unblocked run of `crop` with `disease` across `pct` of it."""
    state = RunState(crop=crop)
    state.tiles = [Tile(id=f"t_0{i}_00", x=i, y=0, label=disease, confidence=0.9) for i in range(8)]
    state.spread = {"pct_affected": pct, "clusters": 2, "direction": "W"}
    state.events = [f"agronomist.disease.{disease}.8_tiles"]
    state.verification = {"status": "PASS", "unsupported_claims": [], "sources": []}
    return state


def contested_field() -> RunState:
    state = field()
    state.events.append("consensus.contested.healthy_dispute.early_blight.69pct")
    state.verification = {
        "status": "BLOCK",
        "unsupported_claims": [],
        "sources": [],
        "block_reason": "the whole-image check reported: a wide field of healthy green plants",
    }
    state.plan_draft = None
    return state


class Stub:
    """Stands in for `llm.complete_first`. `reply=None` means the transport failed."""

    def __init__(self, reply: str | None):
        self.reply = reply
        self.calls = 0

    def __call__(self, system, user, **kwargs):
        self.calls += 1
        if self.reply is None:
            return llm.LLMResult("", False, "stub", "timeout: stubbed")
        return llm.LLMResult(self.reply, True, "stub")


def check(name: str, result: dict, *, refused=..., provider=None, must=(), must_not=()) -> None:
    """One row. `refused` is compared exactly when given; `...` means "do not care"."""
    global PASSES
    problems = []
    if refused is not ... and result["refused"] != refused:
        problems.append(f"refused={result['refused']!r}, expected {refused!r}")
    if provider is not None and result["provider"] != provider:
        problems.append(f"provider={result['provider']!r}, expected {provider!r}")
    for needle in must:
        if needle.lower() not in result["answer"].lower():
            problems.append(f"answer is missing {needle!r}")
    for needle in must_not:
        if needle.lower() in result["answer"].lower():
            problems.append(f"answer must not contain {needle!r}")
    if problems:
        FAILURES.append(name)
        print(f"FAIL {name}")
        for problem in problems:
            print(f"       {problem}")
        print(f"       answer: {result['answer'][:160]!r}")
    else:
        PASSES += 1
        print(f"ok   {name}")


def run(state, question, reply, history=None, *, no_key: bool = False) -> dict:
    """Answer one question with the transport stubbed out."""
    stub = Stub(reply)
    real_complete, real_available = llm.complete_first, llm.available
    advisor.llm.complete_first = stub
    advisor.llm.available = lambda: not no_key
    try:
        return advisor.answer(state, question, history)
    finally:
        advisor.llm.complete_first, advisor.llm.available = real_complete, real_available


GOOD = "Do not spray if rain is expected within four hours, because an unbound protectant washes off and the application is wasted. [doc_07#p2]"
BANNED = "Apply monocrotophos at 2.0 grams per litre of water. [doc_04#p4]"
OVERDOSE = "Apply mancozeb 75 percent WP at 9.0 grams per litre of water. [doc_04#p4]"
INVENTED = "Late blight is best managed by planting marigolds along the field boundary every spring. [doc_04#p3]"
UNMARKED = "Do not spray if rain is expected within four hours, because an unbound protectant washes off and the application is wasted."


def main() -> int:
    # --- the ordinary path -----------------------------------------------------------------
    check(
        "1  a covered question is answered and cited",
        run(field(), "Can I spray before rain?", GOOD),
        refused=None,
        provider="stub",
        must=["four hours", "[doc_07#p2]"],
    )
    check(
        "1b a marker the model omitted is recovered from the evidence",
        run(field(), "Can I spray before rain?", UNMARKED),
        refused=None,
        provider="stub",
        must=["[doc_07#p2]"],
    )
    check(
        "1c a marker written mid-sentence is not doubled",
        run(field(), "Can I spray before rain?", GOOD.replace(" [doc_07#p2]", " [doc_07#p2].")),
        refused=None,
        must=["[doc_07#p2]"],
        must_not=["[doc_07#p2]. [doc_07#p2]"],
    )

    # --- refusals ---------------------------------------------------------------------------
    check("2  an empty question is refused", run(field(), "   ", GOOD), refused="no_question")
    check(
        "2b the model's INSUFFICIENT_CONTEXT is obeyed, not overridden",
        run(field(), "What fertiliser for wheat?", "INSUFFICIENT_CONTEXT"),
        refused="not_covered",
        must=["ten agronomy documents"],
    )
    # A crop the corpus has never heard of is not a refusal, and should not be. The
    # disease-scoped half of the search is filtered out by crop and returns nothing; the
    # crop-agnostic half still answers, because how to hold a sprayer does not depend on what
    # is planted. What must not happen is tomato's dosing advice arriving for a banana field.
    banana = run(field(crop="banana"), "What should I spray?", GOOD)
    check("2c a crop outside the corpus still gets general practice", banana, refused=None)
    # doc_07 and doc_19 are the two documents with no `crops` list — application practice and
    # resistance management. Anything else in `sources` is written for a specific crop.
    scoped = [s["id"] for s in banana["sources"] if not s["id"].startswith(("doc_07", "doc_19"))]
    check(
        "2d ...and never a crop-specific passage",
        {"answer": " ".join(scoped), "provider": "", "refused": None},
        refused=None,
        must_not=["doc_"],
    )

    # --- the Verifier's veto reaches the chat ------------------------------------------------
    contested = contested_field()
    check(
        "3  a contested run refuses every question",
        run(contested, "What should I spray?", GOOD),
        refused="withheld",
        must=["extension officer", "69%"],
        must_not=["spray if rain"],
    )
    check(
        "3b a contested run quotes the cross-check's own words",
        run(contested, "Why?", GOOD),
        refused="withheld",
        must=["a wide field of healthy green plants"],
    )
    withheld = run(contested, "How much mancozeb?", GOOD)
    check("3c a contested run never reaches the model", withheld, refused="withheld")

    not_crop = field()
    not_crop.events.append("consensus.not_crop")
    check(
        "3d a not-a-crop run says to take a different photograph",
        run(not_crop, "What is wrong with my plants?", GOOD),
        refused="withheld",
        must=["does not appear to show a growing crop"],
    )

    blocked = field()
    blocked.verification = {
        "status": "BLOCK",
        "unsupported_claims": [],
        "sources": [],
        "block_reason": "the draft named a chemical no source document supports",
    }
    check(
        "3e a BLOCK with no dispute still withholds",
        run(blocked, "What should I spray?", GOOD),
        refused="withheld",
        must=["safety check"],
    )

    # --- the model misbehaving ----------------------------------------------------------------
    check(
        "4  a banned chemical discards the whole answer",
        run(field(), "What should I spray?", BANNED),
        provider="extractive",
        must_not=["monocrotophos"],
    )
    check(
        "4b a dose outside the supported range discards the whole answer",
        run(field(), "How much mancozeb?", OVERDOSE),
        provider="extractive",
        must_not=["9.0 grams"],
    )
    check(
        "4c an answer from the model's own knowledge is not shipped",
        run(field(), "How do I manage this?", INVENTED),
        provider="extractive",
        must_not=["marigold"],
    )
    check(
        "4d one wandering sentence is dropped, the grounded one is kept",
        run(field(), "Can I spray before rain?", f"{GOOD}\n{INVENTED}"),
        refused=None,
        provider="stub",
        must=["four hours"],
        must_not=["marigold"],
    )

    # --- degradation --------------------------------------------------------------------------
    check(
        "5  a transport failure falls back to the corpus, verbatim and cited",
        run(field(), "Can I spray before rain?", None),
        refused=None,
        provider="extractive",
        must=["could not reach the language model", "[doc_07#p2]"],
    )
    check(
        "5b with no key at all the model is never called",
        run(field(), "Can I spray before rain?", GOOD, no_key=True),
        refused=None,
        provider="extractive",
    )

    # --- inputs nobody produces by accident ---------------------------------------------------
    check(
        "6  a 5,000-character question is truncated, not passed through",
        run(field(), "spray " * 1000, GOOD),
        refused=None,
    )
    check(
        "6b a run with no plan and no disease still answers from the corpus",
        run(RunState(crop="tomato"), "How should I spray?", GOOD),
        refused=None,
    )
    history = [{"role": "user", "text": "hi"}, {"role": "advisor", "text": "hello"}] * 20
    check(
        "6c a long history does not break the request",
        run(field(), "Can I spray before rain?", GOOD, history),
        refused=None,
        provider="stub",
    )

    print()
    total = PASSES + len(FAILURES)
    if FAILURES:
        print(f"{len(FAILURES)} of {total} advisor cases FAILED: {', '.join(FAILURES)}")
        return 1
    print(f"all {total} advisor cases pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

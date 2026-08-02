"""Observer Agent — one whole-image look, from a model that never saw the CNN's answer.

    from agents.observer import run_observer
    run_observer(state, img)

The Diagnostician reads forty tiles of 224x224 pixels and is very good at studio photographs of
detached leaves, because that is what it was trained on. On a real field photograph it is not:
measured by hand, a healthy potato field came back 69.2% affected and a healthy maize field
56.7%, each with a confident disease name and a spray schedule attached, and the crop probe got
four of four real photographs wrong. The Verifier cannot catch any of that — the plan is
correctly grounded advice for a disease the field does not have, and every check it owns passes.

So this agent asks a different kind of model a different question: not "what is in this tile"
forty times, but "what is in this photograph" once. It contributes three things, in descending
order of what they are worth:

**Whether anything is actually wrong.** The cross-check that matters. A whole-image model
looking at a uniform green canopy says so, and `agents/consensus.py` turns the disagreement
into a refusal.

**Which crop this is.** Only when the caller sent `auto`. The probe vote in `crop_vote.py`
scores 0.91-0.99 on the synthetic mosaics and got every real photograph wrong; this does not.
It is written to `state.crop` before the Diagnostician runs, so `resolve_crop` reads it exactly
as it would read a human's answer and neither that file nor the Diagnostician changes at all.

**Which disease.** Least reliable of the three and treated that way — the Consensus agent takes
the name and keeps the CNN's tile map, because knowing *where* is what a 40-tile grid is for.

**Independence is the whole product.** The prompt does not mention the classifier, the declared
crop, or any prior answer, and this agent runs before the Diagnostician partly so that it
cannot be told. An agreeing second opinion that was shown the first one is worth nothing.

**Failing is free.** No key, an exhausted quota, a timeout, a malformed body, a class outside
the enum — every path writes an event, leaves a verdict with `ok=False` on `state.vision`, and
the run proceeds exactly as it did before this agent existed. With no key the only trace is
three events. That is deliberate: the offline path is the demo path, not the sad path.

The response contract and its parser live in `agents/vision_verdict.py`.
"""

from __future__ import annotations

from PIL import Image

from agents import llm
from agents.imaging import inline_image
from agents.prompts import OBSERVER_SYSTEM, OBSERVER_USER, format_class_list
from agents.scout import has_subject
from agents.state import RunState
from agents.vision_verdict import (
    UNKNOWN,
    VisionVerdict,
    class_keys,
    parse_verdict,
    verdict_schema,
)

# Measured, not guessed. A successful vision call on a 180-200 KB field photograph takes 12.0,
# 12.2, 12.5 and 12.9 seconds on this connection — remarkably consistent, and far more than the
# 0.46 s the entire offline pipeline costs. The first version of this file used 10 s and timed
# out on all five fixtures while the model was still answering, which is the worst of both
# worlds: the full wait and none of the benefit.
#
# 25 s leaves real headroom over the measured spread without waiting on something that has
# plainly gone wrong. A rate limit does not cost the wait — it comes back in 0.7 s with a 429 —
# so the only way to spend the full budget is a genuinely stalled connection, and the run then
# produces exactly what it produces today.
VISION_TIMEOUT = 25.0

# Explicitly zero rather than left to the per-model default. `llm._payload` defaults the 2.5
# family to no thinking and everything else to the model's own default, and measured on
# gemini-3-flash-preview that default spends the output budget thinking and the JSON arrives
# truncated at MAX_TOKENS. Setting it here makes the behaviour the same on any model.
VISION_THINKING = 0

# Small on purpose. The reply is six short fields; a larger budget only buys room for the
# failure mode where the model writes an essay into `visible`.
VISION_MAX_TOKENS = 700

# Below this the vision crop is not adopted even when nobody declared one. A weak read still
# beats a hardcoded constant, but not by enough to silently steer a whole run.
#
# Lowered from 60 after measuring what it actually displaces, which is not "nothing" — it is
# the tile probe vote, and that vote is wrong on 4 of 4 real photographs (the numbers are in
# `crop_vote.py`, and one of them is confidently wrong at 0.754). The vision crop is right on
# 4 of 5 (`ml/artifacts/vision_crosscheck.md`). A 55%-confident read from the better instrument
# is a better answer than a confident read from the worse one, and the run says which it used.
CROP_MIN_CONFIDENCE = 50


def enabled() -> bool:
    """The stage kill switch. `AGRISENTINEL_OBSERVER=0` turns the cross-check off without
    touching code, which is what makes the before/after measurement one command."""
    return llm.setting("AGRISENTINEL_OBSERVER", "1").strip().lower() not in {"0", "false", "no"}


def vision_models() -> list[str]:
    """The models to try, in order. Comma-separated in `GEMINI_VISION_MODEL`."""
    return llm.models("GEMINI_VISION_MODEL", llm.DEFAULT_VISION_MODELS)


def ask(img: Image.Image, keys: tuple[str, ...]) -> VisionVerdict:
    """One verdict, from the first model that will answer. Never raises.

    The fall-through-on-a-rate-limit policy this agent needed first now lives in
    `llm.complete_first`, because every other LLM path in the system has the same problem:
    free-tier quota is per-model, and one exhausted bucket should not take a whole capability
    down for the afternoon.
    """
    part = inline_image(img)
    if part is None:
        return VisionVerdict(ok=False, error="too_large")

    result = llm.complete_first(
        OBSERVER_SYSTEM,
        OBSERVER_USER.format(class_list=format_class_list(list(keys))),
        setting_name="GEMINI_VISION_MODEL",
        default=llm.DEFAULT_VISION_MODELS,
        timeout=VISION_TIMEOUT,
        image=part,
        response_schema=verdict_schema(keys),
        thinking=VISION_THINKING,
        max_tokens=VISION_MAX_TOKENS,
    )
    if result.ok:
        return parse_verdict(result.text, keys)
    return VisionVerdict(ok=False, error=llm.failure_kind(result))


def observe(img: Image.Image) -> VisionVerdict:
    """The whole agent's work, with no run state anywhere near it.

    Split from `record_observation` so the network call can run on a background thread while
    the Diagnostician scores tiles — see `orchestrator.start_observer`. A function that touches
    only its argument is safe to run concurrently by inspection; one that appends to
    `state.events` from two threads produces a log whose order depends on the weather.
    """
    if not enabled():
        return VisionVerdict(ok=False, error="disabled")
    if not llm.available():
        return VisionVerdict(ok=False, error="no_key")
    return ask(img, class_keys())


def record_observation(state: RunState, verdict: VisionVerdict) -> RunState:
    """Write a verdict into the run state. Pure bookkeeping — no network, no image."""
    if not verdict.ok:
        reason = verdict.error or "failed"
        state.apply(f"observer.unavailable.{reason}", vision=verdict.to_dict())
        state.apply("observer.done")
        return state

    state.apply("observer.verdict", vision=verdict.to_dict())

    if verdict.visible:
        # The one event carrying free text. Everything a parser needs is in the slug-only
        # events below; this is for the human reading the log, and for the refusal card, where
        # it is the most convincing line on screen.
        state.apply(f"observer.note|{verdict.visible}")
    if not verdict.is_crop_field:
        state.apply("observer.not_crop_photo")
    if verdict.off_enum:
        state.apply(f"observer.off_enum.{verdict.off_enum}")

    state.apply(f"observer.sees.{verdict.class_key or UNKNOWN}")
    if verdict.pct_affected is not None:
        state.apply(f"observer.pct.{verdict.pct_affected}pct")

    _adopt_crop(state, verdict)
    state.apply("observer.done")
    return state


def run_observer(state: RunState, img: Image.Image) -> RunState:
    """Look at the whole photograph once and write down what was seen.

    The sequential form: call, then record. The orchestrator uses the two halves separately so
    the call can overlap tile scoring, but this is what `agents/run.py` and any future caller
    should reach for, and it is the definition the two halves have to add up to.
    """
    state.apply("observer.requested")
    return record_observation(state, observe(img))


def _adopt_crop(state: RunState, verdict: VisionVerdict) -> None:
    """Adopt the vision crop, but only in the one case where nobody has already answered.

    A crop a person chose is never overruled. That is `crop_vote.py`'s policy, and the argument
    there is about authority rather than accuracy, so better evidence does not change it — the
    disagreement is logged and the UI can ask about it, which is the right way to spend it.

    **`is_crop_field` is not a veto here, and the first version of this function had it as one.**
    That cost a whole run, measured: a photograph of one detached tomato leaf came back
    `crop: tomato` at 90% confidence with `is_crop_field: false` — correctly, it is a leaf on a
    bench, not a field — and the crop was thrown away for it. The probe vote then said corn, the
    Diagnostician masked its logits to corn, the classifier returned northern leaf blight, and
    the Consensus agent dropped the vision model's correct `tomato__late_blight` as belonging to
    the wrong crop. The brief read "Your corn field has northern leaf blight." Four stages wrong,
    from one condition, on a photograph where the second opinion had the right answer all along.

    So the test is the same two-signal one `agents/consensus.py` already uses for the harder
    question of whether to stop a run: only when the Scout *also* finds no plant tissue in frame
    is there no subject to name a crop for. A photograph with nothing in it is heading for
    `consensus.not_crop` regardless, so nothing is lost by declining there.
    """
    from agents.crop_vote import AUTO

    if verdict.crop is None:
        return
    if state.crop != AUTO:
        if verdict.crop != state.crop:
            state.apply(f"observer.crop_mismatch.{verdict.crop}")
        return
    if not verdict.is_crop_field and not has_subject(state):
        # Both signals agree the frame holds no plant tissue. Naming a crop for it would be the
        # system playing along with a premise it is about to reject.
        state.apply(f"observer.crop_no_subject.{verdict.crop}")
        return
    if verdict.confidence < CROP_MIN_CONFIDENCE:
        state.apply(f"observer.crop_uncertain.{verdict.crop}.{verdict.confidence}pct")
        return
    # Written into state.crop, so resolve_crop() reads it as a declared crop and the probe vote
    # stands down. The probe still runs and still logs diagnose.crop_mismatch.*, which makes
    # every run a free measurement of the probe against this.
    state.apply(f"observer.crop.{verdict.crop}", crop=verdict.crop)


def vision_verdict(state: RunState) -> VisionVerdict:
    """`state.vision` back as a verdict. The Consensus agent's only reader."""
    return VisionVerdict.from_dict(state.vision)


def observer_summary(state: RunState) -> str:
    verdict = vision_verdict(state)
    if not verdict.ok:
        return f"no vision cross-check ({verdict.error})"
    return (
        f"sees {verdict.class_key or UNKNOWN} at {verdict.confidence}% | "
        f"{verdict.pct_affected}% of visible tissue | crop {verdict.crop or 'other'} | "
        f"{'a field' if verdict.is_crop_field else 'NOT a field photo'}"
    )

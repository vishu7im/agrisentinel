"""Consensus Agent — what to do when the two models disagree.

    from agents.consensus import run_consensus, dispute
    run_consensus(state)

The Diagnostician reads forty tiles and the Observer reads the whole photograph. This decides
what the run believes. It is pure: no network, no image, no model, no `llm` import. It reads
`state.tiles`, `state.crop` and `state.vision`, and it runs in well under a millisecond, which
means the policy can be exercised against a hand-written run state and a hand-written verdict
with none of the machinery that produced them — see `agents/verify_consensus.py`.

**The division of labour is that the CNN knows *where* and the vision model knows *what*.** A
40-tile grid with DBSCAN clustering is real spatial information; a single whole-image verdict is
not. So a relabel changes the name attached to the infected tiles and never which tiles are
infected, and `spread.pct_affected` stays the CNN's measurement — the vision model's percentage
is an eyeball estimate and is recorded as a comparison, not a correction.

**Three things are never rewritten.** `Tile.confidence`, because the 0.75 escalation gate was
calibrated against the unrestricted 14-way softmax and substituting a self-reported number from
a different model would make the threshold describe a quantity nobody measured. `Tile.escalated`,
because `second_opinion_summary` computes a mean confidence over exactly those tiles and would
start averaging two different things. And the infected/healthy partition, per the paragraph
above.

**Disagreement about the disease fuses. Disagreement about whether there *is* one refuses.**
Those are different in kind. Getting the name wrong produces a plan for the wrong disease, which
is bad; inventing a disease in a healthy field produces a spray schedule for a farmer who does
not need one, which is the failure this whole phase exists to stop. The measured case: a healthy
potato field scored 69.2% affected with a confident disease name attached.

**What makes a field "clean" is the percentage, not the label.** Measured, and it changed the
design: shown a healthy maize field the vision model answered `class_key: unknown` — honestly,
because the plants were too young to identify — but `pct_affected: 0`. Keying the refusal on the
class name would have missed it. "I cannot tell you what this crop is, but nothing is wrong with
it" is exactly as strong a contradiction of a 56.7%-infected reading as a named healthy class,
and both now count.
"""

from __future__ import annotations

from collections import Counter

from agents.observer import vision_verdict
from agents.vision_verdict import UNKNOWN, VisionVerdict
from agents.dispute import CONTESTED_EVENT, NOT_CROP_EVENT, dispute
from agents.scout import has_subject
from agents.state import RunState

# At or below this, the vision model is saying there are no symptoms. Not zero: the difference
# between "0%" and "2% of the tissue has something on it" is not a difference either model can
# resolve, and a farmer does not spray a field for it.
VISION_CLEAN_PCT = 5

# Below this the vision model does not get to contest anything or rename anything. An uncertain
# second opinion is still worth logging and worth showing; it is not worth acting on.
VISION_MIN_CONFIDENCE = 60

# How much of the field the CNN must call infected before a disagreement is worth refusing over.
# This is `reporter.severity_band`'s own boundary between "mild" and "moderate", reused rather
# than invented: below it the CNN is reporting a few scattered tiles, which a whole-image model
# looking at the whole canopy at once can plausibly miss. Above it the two models are describing
# different fields.
CONTEST_MIN_PCT = 20.0

# Gap between the two independent percentage estimates worth remarking on. Purely a note — it
# never changes an outcome, because there is no reason to think an eyeball estimate is the
# better of the two numbers.
PCT_GAP_NOTE = 30.0

# `has_subject` — whether the Scout kept enough of the grid to say there is plant tissue in
# frame — is the second signal against the vision model's `is_crop_field`, and it is imported
# from the agent that measures it rather than redefined here. The reason there has to be a
# second signal, and the numbers behind the threshold, are in `agents/scout.py`.

HEALTHY = "healthy"


def dominant_disease(state: RunState) -> tuple[str | None, int]:
    """The most common non-healthy label among scored tiles, and how many tiles carry it.

    A local copy rather than an import from the Agronomist, following the convention the
    Reporter already set: three agents deriving the same thing independently is the property
    that lets any of them be re-run against a stored state.
    """
    labels = Counter(t.label for t in state.scored_tiles if t.label != HEALTHY)
    if not labels:
        return None, 0
    return labels.most_common(1)[0]


def cnn_pct(state: RunState) -> float:
    """Share of scored tiles the classifier called something other than healthy."""
    scored = state.scored_tiles
    if not scored:
        return 0.0
    infected = sum(1 for t in scored if t.label != HEALTHY)
    return round(100.0 * infected / len(scored), 1)


def sees_symptoms(verdict: VisionVerdict) -> bool | None:
    """Whether the vision model reports anything wrong. None when it did not say.

    Deliberately not "did it name a disease". A named healthy class and an unnamed 0% are the
    same statement about the field, and the second one is the case that came up first in
    testing.
    """
    if verdict.pct_affected is not None:
        return verdict.pct_affected > VISION_CLEAN_PCT
    if verdict.class_key:
        return not verdict.class_key.endswith(f"__{HEALTHY}")
    return None


def vision_disease(verdict: VisionVerdict) -> tuple[str, str] | None:
    """`(crop, disease)` when the vision model named an actual disease, else None."""
    if not verdict.class_key or verdict.class_key.endswith(f"__{HEALTHY}"):
        return None
    crop, _, disease = verdict.class_key.partition("__")
    return (crop, disease) if disease else None


def run_consensus(state: RunState) -> RunState:
    """Reconcile the two readings and write the outcome to the tiles and the event log."""
    verdict = vision_verdict(state)
    if not verdict.ok:
        state.apply("consensus.skipped.no_vision")
        state.apply("consensus.done")
        return state

    if not verdict.is_crop_field:
        if has_subject(state):
            # The vision model says this is not a field and the Scout says the frame is full of
            # plant tissue. Both are usually right: a mosaic of detached leaves, a laboratory
            # photograph, a close-up of one plant on a bench. Not a field, and still something
            # a plant pathologist can read, so the run continues on the classifier's evidence
            # and the disagreement is left on the log where the UI can surface it.
            state.apply("consensus.not_field_but_foliage")
        else:
            # Both agree there is nothing here. The tiles are rewritten so nothing downstream
            # treats them as a measurement — silently, unlike the relabel path below, because
            # there every tile changes to something different and here they all change to the
            # same thing; forty identical events would be the loudest moment in a log whose
            # whole job is being readable.
            cleared = state.scored_tiles
            for tile in cleared:
                tile.label = "skipped_not_crop"
            # Counted event first, then the bare name — the same shape the Verifier's block
            # path uses, so a reader of the stream sees detail then ruling both times.
            if cleared:
                state.apply(f"{NOT_CROP_EVENT}.{len(cleared)}_tiles")
            state.apply(NOT_CROP_EVENT)
            state.apply("consensus.done")
            return state

    label, _ = dominant_disease(state)
    pct = cnn_pct(state)
    # Emitted before anything is rewritten: after a relabel the classifier's original claim is
    # not recoverable from the tiles, and it is half of what the UI puts on screen.
    state.apply(f"consensus.cnn.{label or HEALTHY}.{round(pct)}pct")

    _decide(state, verdict, label, pct)

    if verdict.pct_affected is not None and abs(pct - verdict.pct_affected) >= PCT_GAP_NOTE:
        state.apply(f"consensus.pct_gap.{round(abs(pct - verdict.pct_affected))}pp")
    state.apply("consensus.done")
    return state


def _decide(state: RunState, verdict: VisionVerdict, label: str | None, pct: float) -> None:
    """The decision table. Exactly one outcome event is emitted by every path."""
    symptoms = sees_symptoms(verdict)
    confident = verdict.confidence >= VISION_MIN_CONFIDENCE

    if symptoms is False:
        if label is None:
            state.apply("consensus.agree.healthy")
        elif not confident:
            # The models disagree and the one contradicting the scan is unsure. Logged so the
            # timeline shows it happened; not acted on, because withholding a farmer's plan
            # needs better evidence than this.
            state.apply(f"consensus.low_confidence_vision.clean.{verdict.confidence}pct")
        elif pct >= CONTEST_MIN_PCT:
            # The one that matters. The tile labels are left exactly as the classifier wrote
            # them — the heatmap goes on showing what it saw, because that is evidence and
            # hiding it would be the same dishonesty pointing the other way. What gets withheld
            # is the advice, and the Agronomist reads this event and declines.
            state.apply(f"consensus.contested.healthy_dispute.{label}.{round(pct)}pct")
        else:
            # A few scattered tiles against a whole-image read of a clean field. Well within
            # what a single wide shot can miss, so the plan stands and the note is the record.
            state.apply(f"consensus.vision_clean.minor.{round(pct)}pct")
        return

    named = vision_disease(verdict)
    if named is None:
        # It sees something and cannot name it — an off-enum answer, or `unknown` with a
        # non-zero percentage. Honest, and the correct answer for a disease outside the
        # fourteen classes, but there is nothing here to fuse.
        state.apply(f"consensus.no_disease_opinion.{verdict.off_enum or UNKNOWN}")
        return

    crop, disease = named
    if crop != state.crop:
        # It named a disease of a different crop than the run is scanning. Fusing would write a
        # label with no severity weight, no corpus coverage and no Hindi phrase, so the opinion
        # is recorded and dropped. The crop disagreement itself was already logged by the
        # Observer, and that is the more useful signal.
        state.apply(f"consensus.crop_scoped_out.{crop}.{disease}")
        return

    if label is None:
        # The classifier found nothing. A clean run ships no plan today, so there is no unsafe
        # output to withhold and nothing to fuse into — one vision false positive must not be
        # able to turn a correct clean scan into a refusal.
        state.apply(f"consensus.vision_only.{disease}")
        return

    if disease == label:
        state.apply(f"consensus.agree.{disease}")
        return

    if not confident:
        state.apply(f"consensus.low_confidence_vision.{disease}.{verdict.confidence}pct")
        return

    # Both models see disease, in the same crop, and disagree about which one. The vision model
    # takes the name; the classifier keeps the map. This never refuses: the fused label is in
    # the enum and the crop matches, so the severity weights, the corpus and the Hindi phrase
    # table all resolve, and the run produces a better plan rather than no plan.
    # Counted as they are rewritten, not taken from `tile_count`. Those are two different
    # numbers whenever the grid holds a minority label as well: `tile_count` is how many tiles
    # carry the *dominant* disease, and this loop renames every infected tile. Measured on a
    # real photograph the log claimed 7 tiles while 23 changed, and that sentence is rendered
    # verbatim in the UI.
    renamed = 0
    for tile in state.scored_tiles:
        if tile.label != HEALTHY:
            state.update_tile(tile.id, f"consensus.tile.{tile.id}", label=disease)
            renamed += 1
    state.apply(f"consensus.relabel.{label}_to_{disease}.{renamed}_tiles")


def consensus_summary(state: RunState) -> str:
    verdict = vision_verdict(state)
    if not verdict.ok:
        return f"no cross-check ({verdict.error})"
    outcome = next(
        (e for e in state.events if e.startswith("consensus.") and not e.endswith(".done")),
        "consensus.none",
    )
    return (
        f"cnn {cnn_pct(state)}% vs vision {verdict.pct_affected}% | "
        f"{outcome.removeprefix('consensus.')}"
    )

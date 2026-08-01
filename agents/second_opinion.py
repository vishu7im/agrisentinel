"""Second-Opinion Agent — a slower, more careful look at the tiles the model was unsure of.

    from agents.second_opinion import low_confidence_tiles, run_second_opinion
    run_second_opinion(state, img, classifier)     # writes tiles, emits second_opinion.done

The Diagnostician scores every tile once, cheaply. Some of those scores are near-guesses, and
`ml/eval.py` says exactly how many: at a 0.75 confidence gate, 15.8% of held-out tiles fall
below it. Escalating that 15.8% to a four-view pass costs four ONNX runs on a sixth of the
grid — about 15% more inference on the whole scan.

**Measured on the 2,399-image held-out split, on the sub-population the gate actually
selects** (n=379, the only tiles this agent ever sees):

    accuracy      single-view 75.73%   ->   4-view TTA 78.36%   (+2.6 pp)
    of those 379: 32 fixed, 22 broken, net +10
    confidence    mean 0.582           ->   0.611, 65 tiles lifted clear of the gate
    overall split 95.58%               ->   96.00%

Two things in there are worth not glossing over. TTA **breaks 22 tiles it previously got
right** — the net gain is +10, not +32, and any claim that a second opinion only ever helps
is wrong. And on the confident majority (n=2,020) accuracy is 99.31% either way, unchanged to
two decimals, which is the empirical case for gating at all: running TTA on everything would
quadruple inference to move a number that does not move.

**Test-time augmentation, averaged over probabilities.** The four views are identity, hflip,
vflip and rot180. They are the flips that preserve the tile's aspect ratio: a 90-degree
rotation of a non-square tile resizes into the network differently from anything in training,
so it would measure the preprocessing rather than the leaf. The probabilities are averaged
*before* the argmax, not after — decoding each view and taking a majority vote would collapse
four calibrated distributions into four hard labels and throw away the disagreement that is
the entire signal here.

**Escalated tiles are not re-gated.** The gate is applied once, to the Diagnostician's
single-view confidence, because that is the quantity the 0.75 threshold was measured against
in A2. A TTA-averaged confidence is a different number — measurably so, mean 0.611 against
0.582 on the same tiles — so feeding it back into the same threshold would compare two
quantities that were never calibrated together, and would loop on the ones still below it.
(I expected averaging to *lower* the peak, the way smoothing usually does. It does not here:
the four views mostly agree, and agreement concentrates the mean rather than flattening it.
The threshold argument holds either way, but the reason is the opposite of the assumed one.)

**escalated stays true whether or not the label changed.** It records that a tile got the
expensive treatment, which is what the UI badge means and what makes the count on screen
match `orchestrator.escalate.<n>_tiles`. A tile the second pass confirms is still a tile the
system spent extra effort on, and hiding that would understate the work.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from agents.diagnostician import BATCH_SIZE, Classifier
from agents.preprocess import TTA_VIEWS, apply_tta, preprocess_batch, softmax
from agents.state import RunState
from agents.tiling import DEFAULT_COLS, DEFAULT_ROWS, crop_tiles

# Below this the Diagnostician's answer is treated as a guess worth checking. Chosen in A2
# from the held-out confidence distribution: it sits in the trough between the confident mass
# and the tail, and catches 3 of the 4 known tile errors on the A3/A4 fixtures.
CONFIDENCE_GATE = 0.75


def low_confidence_tiles(state: RunState, gate: float = CONFIDENCE_GATE) -> list:
    """The escalation set, derived from the run state alone.

    Both this agent and the orchestrator need it — the orchestrator to announce the count
    before any work happens, this agent to do the work — and neither may call the other, so
    it is a pure function of the state that both read.
    """
    return [t for t in state.scored_tiles if (t.confidence or 0.0) < gate]


def tta_probs(
    classifier: Classifier,
    images: list[Image.Image],
    batch_size: int = BATCH_SIZE,
) -> np.ndarray:
    """(N, C) mean softmax across the four TTA views.

    Preprocessing happens once per chunk and the flips are applied to the resulting array, so
    a four-view pass costs four ONNX runs but only one decode, resize and normalise.
    """
    if not images:
        return np.empty((0, len(classifier.class_keys)), dtype=np.float32)

    rows = []
    for start in range(0, len(images), batch_size):
        batch = preprocess_batch(images[start : start + batch_size], classifier.img_size)
        total = sum(softmax(classifier.logits(apply_tta(batch, view))) for view in TTA_VIEWS)
        rows.append(total / len(TTA_VIEWS))
    return np.concatenate(rows, axis=0)


def run_second_opinion(
    state: RunState,
    img: Image.Image,
    classifier: Classifier,
    gate: float = CONFIDENCE_GATE,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
    batch_size: int = BATCH_SIZE,
) -> RunState:
    """Re-score every tile under the gate with TTA and write the revised answers back."""
    targets = low_confidence_tiles(state, gate)
    if not targets:
        # Nothing to do, but still say so. A silent no-op agent is indistinguishable on the
        # timeline from an agent that crashed.
        state.apply("second_opinion.done")
        return state

    crops = crop_tiles(img, cols, rows)
    probs = tta_probs(classifier, [crops[t.id] for t in targets], batch_size)
    crop_filter = state.crop if classifier.crop_mask(state.crop) is not None else None

    revised = 0
    for tile, row in zip(targets, probs):
        result = classifier.decode(row, crop_filter)
        if result["label"] != tile.label:
            revised += 1
        state.update_tile(
            tile.id,
            f"second_opinion.tile.{tile.id}",
            label=result["label"],
            confidence=result["confidence"],
            escalated=True,
        )

    if revised:
        state.apply(f"second_opinion.revised.{revised}_tiles")
    state.apply("second_opinion.done")
    return state


def second_opinion_summary(state: RunState, gate: float = CONFIDENCE_GATE) -> str:
    """Read after the run, so every number here is the *post*-TTA state.

    That is worth saying out loud, because the tiles this agent touched are exactly the ones
    whose confidence it overwrote: a count of "tiles under the gate" taken afterwards is not
    the count that triggered escalation, and the two differ whenever TTA lifts a tile clear.
    """
    escalated = [t for t in state.tiles if t.escalated]
    if not escalated:
        return "no tiles below the gate — nothing escalated"
    mean_conf = sum(t.confidence or 0.0 for t in escalated) / len(escalated)
    lifted = sum(1 for t in escalated if (t.confidence or 0.0) >= gate)
    return (
        f"{len(escalated)} tile(s) re-scored with 4-view TTA | mean confidence now "
        f"{mean_conf:.2f} | {lifted} lifted above the gate"
    )

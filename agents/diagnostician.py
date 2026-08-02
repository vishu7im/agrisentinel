"""Diagnostician Agent — ONNX inference over every tile the Scout kept.

    from agents.diagnostician import Classifier, run_diagnostician
    run_diagnostician(state, img, Classifier())

CPU-only, batched, no torch anywhere. The model is `ml/artifacts/model.onnx` (EfficientNet-B0,
0.947 macro-F1 on the held-out split) and its class list and preprocessing recipe travel
alongside it in `model_classes.json` — see `agents/preprocess.py` for why that recipe has to
be reimplemented rather than imported.

Three decisions worth knowing about before reading the code:

**Predictions are restricted to the run's crop.** The model has 14 classes across tomato,
potato and corn, but a field is one crop, and `POST /api/run` already carries which one. Left
unrestricted, one odd tile in a tomato field comes back `corn__common_rust`, which then flows
into A4's per-disease severity weights and A6's retrieval as if it were real. Masking the
logits to the declared crop turns an impossible answer into a merely uncertain one.

**Nobody declaring a crop is different from someone declaring the wrong one.** `crop` used to
default to `tomato` at every layer — the form field, `new_run()`, the frontend's own call — and
there was no crop picker, so the default was never overridden by anything and masking made it
unrecoverable: a corn field came back as tomato diseases at near-zero confidence, reporting
94.4% infected and ~49.9% yield at risk against a true 30.6% and 9.2%. The caller now sends
`auto` when no human has chosen, and a probe pass reads the first tiles unmasked and votes.

**Detection does not overrule a person, and the measurements are why.** On the synthetic
mosaics the winning crop takes 0.91-0.99 of the probability mass and this is easy. On four real
photographs downloaded from Wikimedia Commons it is not: a corn field split tomato 0.502 / corn
0.483, a potato leaf came back corn 0.438, and a tomato plant went corn 0.754 — confidently,
wrongly, and by enough to have overruled a correct declaration. That is the lab-to-field gap in
`ml/artifacts/lab_vs_field.md` arriving here. So an explicit crop is obeyed and a disagreement
is only logged (`diagnose.crop_mismatch.*`); the vote decides only when the answer was `auto`.

**Confidence stays the unrestricted softmax.** It would be easy to renormalise over the
crop's classes and report a flattering number, but `ml/eval.py` measured the 0.75 escalation
gate against the full 14-way softmax. Reporting anything else would make that threshold — and
the 15.8% escalation rate it was chosen from — describe a different quantity than the one the
UI acts on. The restricted class can therefore carry a confidence below the unrestricted max,
which is correct: that tile genuinely is uncertain and A5 should escalate it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from agents.crop_vote import AUTO, CROP_PROBE_TILES, FALLBACK_CROP, resolve_crop
from agents.preprocess import preprocess_batch, softmax
from agents.state import RunState
from agents.tiling import DEFAULT_COLS, DEFAULT_ROWS, crop_tiles

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = REPO_ROOT / "ml" / "artifacts" / "model.onnx"
DEFAULT_CLASSES = REPO_ROOT / "ml" / "artifacts" / "model_classes.json"

# Tiles per ONNX call. The graph has a dynamic batch axis, so this is free to tune — and
# measuring it was worth the five minutes, because the intuition is backwards. On this CPU a
# 38-tile scan costs 273 ms at batch 1, 295 ms at batch 4, 414 ms at batch 16 and 523 ms at
# batch 38: bigger batches are steadily *slower*. ONNX Runtime's CPU provider already spreads
# a single 224x224 convolution across every core, so batching adds memory traffic without
# adding parallelism. 4 is the compromise — within 8% of the measured optimum, still a real
# batch, and it hedges against a venue laptop with fewer cores where per-call overhead
# matters more than it does here.
BATCH_SIZE = 4


class Classifier:
    """The ONNX session plus everything needed to turn its logits into contract labels.

    Constructed once and reused. Building an InferenceSession costs far more than running
    one, so A5 holds a single instance for the process rather than one per run.
    """

    def __init__(
        self,
        model_path: Path = DEFAULT_MODEL,
        classes_path: Path = DEFAULT_CLASSES,
        threads: int = 0,
    ):
        if not model_path.exists():
            raise SystemExit(
                f"{model_path} missing — run `.venv/bin/python ml/export_onnx.py` first."
            )
        meta = json.loads(classes_path.read_text())
        self.class_keys: list[str] = meta["class_keys"]
        self.img_size: int = meta.get("img_size", 224)

        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        # CPUExecutionProvider on purpose: venue GPUs cannot be relied on, and at 4.9 ms per
        # tile a 40-tile scan is 0.2 s of inference. There is nothing here worth a GPU.
        self.session = ort.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name

    # --- class bookkeeping ------------------------------------------------------------

    @staticmethod
    def split_key(key: str) -> tuple[str, str]:
        """'tomato__late_blight' -> ('tomato', 'late_blight').

        The class key format is set by ml/data/classes.py and the second half is what lands
        in tiles[].label. Splitting here rather than importing from /ml keeps the backend
        free of any dependency on the training tree.
        """
        crop, _, label = key.partition("__")
        return crop, label

    @property
    def crops(self) -> list[str]:
        return sorted({self.split_key(k)[0] for k in self.class_keys})

    def crop_mask(self, crop: str) -> np.ndarray | None:
        """Boolean mask over class_keys for one crop, or None if the crop is unknown."""
        mask = np.array([self.split_key(k)[0] == crop for k in self.class_keys])
        return mask if mask.any() else None

    # --- inference --------------------------------------------------------------------

    def logits(self, batch: np.ndarray) -> np.ndarray:
        return self.session.run(None, {self.input_name: batch})[0]

    def probabilities(self, images: list[Image.Image]) -> np.ndarray:
        """One softmax row per image, undecoded. Separate from `predict` because the crop
        probe has to read the distribution before it knows which crop to decode against."""
        if not images:
            return np.empty((0, len(self.class_keys)), dtype=np.float32)
        return softmax(self.logits(preprocess_batch(images, self.img_size)))

    def predict(self, images: list[Image.Image], crop: str | None = None) -> list[dict]:
        """[{label, confidence, class_key}] — one entry per image, in input order."""
        return [self.decode(row, crop) for row in self.probabilities(images)]

    def crop_shares(self, probs: np.ndarray) -> dict[str, float]:
        """Mean probability mass each crop attracts across these tiles.

        Mass rather than a vote over argmax labels: a tile that is 40% one corn disease and 40%
        another is strong evidence of corn, and counting argmax winners throws that away. It
        also degrades gracefully on the tiles this matters most for — the uncertain ones.
        """
        if not len(probs):
            return {}
        return {
            crop: float(probs[:, mask].sum(axis=1).mean())
            for crop in self.crops
            if (mask := self.crop_mask(crop)) is not None
        }

    def decode(self, probs: np.ndarray, crop: str | None) -> dict:
        """One probability row -> a contract label. Public because the Second-Opinion agent
        averages probabilities across TTA views and needs to decode the mean, not each view —
        decoding per view and voting would throw away exactly the uncertainty it is measuring.
        """
        mask = self.crop_mask(crop) if crop else None
        if mask is None:
            index = int(probs.argmax())
        else:
            # Pick the best class *within the crop*, but report its own probability from the
            # unrestricted distribution — see the module docstring.
            index = int(np.where(mask)[0][probs[mask].argmax()])
        key = self.class_keys[index]
        return {
            "class_key": key,
            "label": self.split_key(key)[1],
            "confidence": float(probs[index]),
        }



def run_diagnostician(
    state: RunState,
    img: Image.Image,
    classifier: Classifier,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
    batch_size: int = BATCH_SIZE,
) -> RunState:
    """Score every non-skipped tile and write label + confidence back into the run state.

    Re-crops the image from the same geometry the Scout used rather than being handed the
    crops. That is a few milliseconds of PIL work in exchange for the agents staying
    genuinely decoupled: the Diagnostician's only input from the Scout is what is written in
    the run state.
    """
    crops = crop_tiles(img, cols, rows)
    pending = [t for t in state.tiles if not t.skipped]

    if not pending:
        # Every tile was soil or sky. Not an error — a photo of a footpath is a valid thing
        # to hand the system, and A4 must be able to report an empty field rather than crash.
        if state.crop == AUTO:
            # There is nothing to vote on, and `auto` must not reach the response: the contract
            # says crop is a crop, and the UI would render the word "auto" at a farmer.
            state.apply(f"diagnose.crop_unresolved.{FALLBACK_CROP}", crop=FALLBACK_CROP)
        state.apply("diagnose.empty_field")
        state.apply("diagnose.done")
        return state

    # The probe reads the first few tiles unmasked and settles the crop question before any
    # label is written. Its rows are kept and decoded below, so this costs no extra inference —
    # only the first `diagnose.tile.*` event arriving a couple of batches late, which is a
    # cheaper thing to spend than scanning a corn field as a tomato one.
    probe = pending[:CROP_PROBE_TILES]
    probe_probs = classifier.probabilities([crops[t.id] for t in probe])
    crop_filter = resolve_crop(state, classifier, probe_probs)

    def write(chunk: list, rows: np.ndarray) -> None:
        for tile, row in zip(chunk, rows):
            result = classifier.decode(row, crop_filter)
            state.update_tile(
                tile.id,
                f"diagnose.tile.{tile.id}",
                label=result["label"],
                confidence=result["confidence"],
            )

    write(probe, probe_probs)
    for start in range(len(probe), len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        write(chunk, classifier.probabilities([crops[t.id] for t in chunk]))

    state.apply("diagnose.done")
    return state


def diagnose_summary(state: RunState) -> str:
    scored = state.scored_tiles
    if not scored:
        return "no tiles scored — the whole frame was soil or sky"
    infected = [t for t in scored if t.label != "healthy"]
    low = [t for t in scored if (t.confidence or 0) < 0.75]
    worst = min(scored, key=lambda t: t.confidence or 0)
    return (
        f"{len(scored)} scored | {len(infected)} not healthy | "
        f"{len(low)} below the 0.75 gate | lowest {worst.id} at {worst.confidence:.2f}"
    )

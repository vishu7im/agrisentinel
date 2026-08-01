"""Prove agents/preprocess.py is byte-identical to the torchvision transform it replaces.

    .venv/bin/python agents/verify_preprocess.py --n 200

**Dev tool. It imports torchvision, and nothing at runtime may import it.** That is the whole
point: this is the one place the two worlds are allowed to meet, so that everywhere else the
backend can stay torch-free and still be trusted.

Run it whenever agents/preprocess.py or ml/data/augment.py changes. The failure it exists to
catch does not announce itself — a one-pixel crop offset produces a working pipeline whose
predictions still mostly agree, and it cost an afternoon the first time. Prediction agreement
alone is NOT sufficient evidence; that is why max |diff| is reported first and separately.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.preprocess import preprocess_tile  # noqa: E402

DEFAULT_DIR = REPO_ROOT / "ml" / "data" / "processed" / "test"


def sample_images(root: Path, n: int, seed: int) -> list[Path]:
    paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not paths:
        raise SystemExit(f"no images under {root} — run ml/data/prepare.py first")
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(paths), size=min(n, len(paths)), replace=False)
    return [paths[int(i)] for i in picks]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--model", type=Path, default=REPO_ROOT / "ml" / "artifacts" / "model.onnx")
    args = p.parse_args()

    try:
        from ml.data.augment import build_eval_transform
    except ImportError:
        sys.path.insert(0, str(REPO_ROOT / "ml"))
        from data.augment import build_eval_transform

    transform = build_eval_transform()
    paths = sample_images(args.dir, args.n, args.seed)
    print(f"comparing {len(paths)} images from {args.dir}")

    ours, theirs = [], []
    worst = 0.0
    for path in paths:
        img = Image.open(path).convert("RGB")
        mine = preprocess_tile(img)
        reference = transform(img).numpy()
        worst = max(worst, float(np.abs(mine - reference).max()))
        ours.append(mine)
        theirs.append(reference)

    print(f"  max |diff| over all pixels: {worst:.2e}")
    if worst > 0:
        print("  FAIL — the two pipelines disagree. Do not ship this.")
        return 1
    print("  identical.")

    # Agreement on the actual model is the second, weaker check: it confirms the arrays are
    # not just equal to each other but equal in a way onnxruntime accepts.
    if args.model.exists():
        import onnxruntime as ort

        session = ort.InferenceSession(str(args.model), providers=["CPUExecutionProvider"])
        name = session.get_inputs()[0].name
        mine = session.run(None, {name: np.stack(ours)})[0].argmax(axis=1)
        ref = session.run(None, {name: np.stack(theirs)})[0].argmax(axis=1)
        print(f"  ONNX prediction agreement: {int((mine == ref).sum())}/{len(mine)}")
        return 0 if (mine == ref).all() else 1

    print(f"  (skipped the ONNX check — {args.model} not found)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

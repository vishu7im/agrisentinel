"""Eyeball check on the prepared dataset: a per-class count table and a 4x4 sample grid.

    .venv/bin/python ml/data/inspect.py

The grid is laid out so it answers the one question worth asking of an augmentation
pipeline — *is it too aggressive?* Each column is one source image. The top row is the
original; the three rows below are three independent draws from the training transform. If
a column's lower rows no longer look like the disease in its top row, the augmentation has
started destroying the label and the parameters in augment.py need pulling back.

Writes ml/artifacts/augmented_samples.png. That directory is committed on purpose — this
image is a slide.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# This must happen before `import torch`, and it is the whole reason ml/data is a package.
# Python puts a script's own directory at sys.path[0], so *this file* becomes the module
# torch resolves when it does `import inspect` — and it then dies on
# "module 'inspect' has no attribute 'signature'". Drop that entry, add ml/ instead.
_HERE = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _HERE]
sys.path.insert(0, str(_HERE.parent))

import torch  # noqa: E402
from PIL import Image  # noqa: E402
from torchvision import transforms  # noqa: E402
from torchvision.utils import make_grid  # noqa: E402

from data.augment import build_train_transform  # noqa: E402

ML_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PROCESSED = ML_DIR / "data" / "processed"
DEFAULT_OUT = ML_DIR / "artifacts" / "augmented_samples.png"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}  # compared case-insensitively
GRID_COLS = 4
GRID_ROWS = 4  # row 0 = original, rows 1..3 = augmented
CELL = 224


def count_split(split_dir: Path) -> dict[str, int]:
    if not split_dir.is_dir():
        return {}
    return {
        d.name: sum(1 for p in d.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        for d in sorted(split_dir.iterdir())
        if d.is_dir()
    }


def print_table(counts: dict[str, dict[str, int]], class_map: dict | None) -> bool:
    """Print per-class counts. Returns False if the tree disagrees with class_map.json."""
    keys = sorted({k for split in counts.values() for k in split})
    width = max(len(k) for k in keys)
    header = f"{'class':<{width}}  {'train':>6} {'val':>5} {'test':>5} {'total':>6}"
    print(header)
    print("-" * len(header))

    totals = {"train": 0, "val": 0, "test": 0}
    for key in keys:
        row = {s: counts.get(s, {}).get(key, 0) for s in totals}
        for s in totals:
            totals[s] += row[s]
        print(
            f"{key:<{width}}  {row['train']:>6,} {row['val']:>5,} "
            f"{row['test']:>5,} {sum(row.values()):>6,}"
        )
    print("-" * len(header))
    grand = sum(totals.values())
    print(
        f"{'TOTAL':<{width}}  {totals['train']:>6,} {totals['val']:>5,} "
        f"{totals['test']:>5,} {grand:>6,}"
    )

    if class_map is None:
        return True

    # Cross-check against class_map.json rather than trusting it. A stale class_map is the
    # kind of thing that silently mislabels every prediction in A2.
    expected = {c["key"]: c["counts"] for c in class_map["classes"]}
    mismatches = [
        f"  {key}: on disk {counts.get(s, {}).get(key, 0)}, class_map says {expected[key][s]}"
        for key in keys
        if key in expected
        for s in ("train", "val", "test")
        if counts.get(s, {}).get(key, 0) != expected[key][s]
    ]
    missing = sorted(set(expected) ^ set(keys))
    if mismatches or missing:
        print("\nFAIL: processed tree disagrees with class_map.json")
        for line in mismatches:
            print(line)
        for key in missing:
            print(f"  {key}: present in one of tree/class_map but not the other")
        print("Re-run ml/data/prepare.py.")
        return False

    print("\nOK: on-disk counts match class_map.json")
    return True


def build_grid(train_dir: Path, out_path: Path, seed: int) -> None:
    rng = random.Random(seed)
    class_dirs = [d for d in sorted(train_dir.iterdir()) if d.is_dir()]
    if len(class_dirs) < GRID_COLS:
        raise SystemExit(f"need at least {GRID_COLS} classes to build the grid")

    picks: list[tuple[str, Path]] = []
    for class_dir in rng.sample(class_dirs, GRID_COLS):
        images = [p for p in class_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES]
        picks.append((class_dir.name, rng.choice(images)))

    augment = build_train_transform(normalize=False)  # unnormalised: viewable pixels
    plain = transforms.Compose(
        [transforms.Resize(CELL), transforms.CenterCrop(CELL), transforms.ToTensor()]
    )

    # make_grid fills row-major, so build the tensor list row by row: originals first,
    # then one augmented pass per remaining row.
    originals = [Image.open(path).convert("RGB") for _, path in picks]
    cells: list[torch.Tensor] = [plain(img) for img in originals]
    for _ in range(GRID_ROWS - 1):
        cells.extend(augment(img) for img in originals)

    grid = make_grid(cells, nrow=GRID_COLS, padding=4, pad_value=1.0)
    array = (grid.clamp(0, 1) * 255).byte().permute(1, 2, 0).numpy()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array).save(out_path)

    print(f"\nwrote {out_path}  ({array.shape[1]}x{array.shape[0]})")
    print("  row 1 = original, rows 2-4 = independent draws from the train transform")
    for i, (key, path) in enumerate(picks, start=1):
        print(f"  column {i}: {key}  ({path.name})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    processed: Path = args.processed_dir
    if not processed.is_dir():
        print(f"ERROR: {processed} missing. Run ml/data/prepare.py first.", file=sys.stderr)
        return 1

    counts = {split: count_split(processed / split) for split in ("train", "val", "test")}
    if not counts["train"]:
        print(f"ERROR: {processed / 'train'} is empty.", file=sys.stderr)
        return 1

    map_path = processed / "class_map.json"
    class_map = json.loads(map_path.read_text()) if map_path.exists() else None
    if class_map is None:
        print(f"WARNING: {map_path} missing, skipping cross-check\n")

    ok = print_table(counts, class_map)
    build_grid(processed / "train", args.out, args.seed)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Turn ml/data/raw/ into a capped, stratified train/val/test tree plus class_map.json.

    .venv/bin/python ml/data/prepare.py

Two things happen here that matter to the final numbers:

**Capping.** PlantVillage is badly imbalanced — Tomato Yellow Leaf Curl Virus has ~5,300
images, Potato healthy has 152, a 35x spread. Left alone the model learns to answer
"yellow leaf curl" and still scores well, which is exactly the kind of accuracy that
collapses on a real field photo. Every class is capped at 1.5x the median class size. We
cap rather than oversample the small classes because duplicating 152 potato images 10x
teaches the model those 152 images, not potato.

**Stratified splitting.** The 70/15/15 split is drawn per class, so every class appears in
all three splits in proportion. A global shuffle would leave the small classes with a
handful of test images and a meaningless per-class recall in A2's metrics table.

Both are seeded, so re-running gives byte-identical splits and a checkpoint stays
comparable to the eval that was run against it.

Output images are hardlinks into raw/, so the processed tree costs no extra disk.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# See ml/data/__init__.py — inspect.py in this directory shadows the stdlib module.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _HERE]
sys.path.insert(0, str(_HERE.parent))
from data.classes import CLASSES  # noqa: E402

ML_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ML_DIR / "data" / "raw"
DEFAULT_OUT = ML_DIR / "data" / "processed"

SEED = 42
SPLITS = (("train", 0.70), ("val", 0.15), ("test", 0.15))
CAP_MULTIPLIER = 1.5
# Case-insensitive: PlantVillage is mostly .JPG, with some .jpg and a single .jpeg.
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def list_images(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def split_sizes(n: int) -> dict[str, int]:
    """Split n into train/val/test. Remainder goes to train so nothing is dropped."""
    val = int(n * dict(SPLITS)["val"])
    test = int(n * dict(SPLITS)["test"])
    return {"train": n - val - test, "val": val, "test": test}


def link(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--cap-multiplier",
        type=float,
        default=CAP_MULTIPLIER,
        help="cap each class at this multiple of the median class size (0 disables)",
    )
    args = parser.parse_args()

    raw_dir: Path = args.raw_dir
    out_dir: Path = args.out_dir

    # --- gather ------------------------------------------------------------------
    available: dict[str, list[Path]] = {}
    for cls in CLASSES:
        folder = raw_dir / cls.folder
        if not folder.is_dir():
            print(
                f"ERROR: {folder} is missing. Run ml/data/download.py first.",
                file=sys.stderr,
            )
            return 1
        images = list_images(folder)
        if not images:
            print(f"ERROR: {folder} contains no images.", file=sys.stderr)
            return 1
        available[cls.key] = images

    sizes = [len(v) for v in available.values()]
    median = statistics.median(sizes)
    cap = int(median * args.cap_multiplier) if args.cap_multiplier > 0 else max(sizes)
    print(
        f"{len(CLASSES)} classes, {sum(sizes):,} images available\n"
        f"class sizes: min {min(sizes):,}  median {median:,.0f}  max {max(sizes):,}\n"
        f"cap = {args.cap_multiplier} x median = {cap:,} images per class\n"
    )

    # --- cap + split -------------------------------------------------------------
    if out_dir.exists():
        print(f"clearing {out_dir}")
        shutil.rmtree(out_dir)

    rng = random.Random(args.seed)
    rows: list[dict] = []
    totals = {name: 0 for name, _ in SPLITS}

    # Index order follows the sorted class keys, which is also the order torchvision's
    # ImageFolder will assign when it scans the output directories. train.py asserts this.
    for index, cls in enumerate(sorted(CLASSES, key=lambda c: c.key)):
        images = list(available[cls.key])
        n_available = len(images)

        rng.shuffle(images)  # shuffle before capping so the cap is not "the first N by name"
        kept = images[:cap]

        counts = split_sizes(len(kept))
        cursor = 0
        for split_name, _ in SPLITS:
            n = counts[split_name]
            dest = out_dir / split_name / cls.key
            dest.mkdir(parents=True, exist_ok=True)
            for src in kept[cursor : cursor + n]:
                link(src, dest / src.name)
            cursor += n
            totals[split_name] += n

        rows.append(
            {
                "index": index,
                "key": cls.key,
                "crop": cls.crop,
                "tile_label": cls.tile_label,
                "folder": cls.folder,
                "available": n_available,
                "kept": len(kept),
                "capped": len(kept) < n_available,
                "counts": counts,
            }
        )

    # --- class_map.json ----------------------------------------------------------
    class_map = {
        "seed": args.seed,
        "cap_multiplier": args.cap_multiplier,
        "cap": cap,
        "split_ratios": {name: ratio for name, ratio in SPLITS},
        # tiles[].label in contract/run_state.schema.json is the tile_label, not the key.
        "note": "index order == sorted(key) == torchvision ImageFolder order",
        "classes": rows,
        "totals": totals,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "class_map.json").write_text(json.dumps(class_map, indent=2) + "\n")

    # --- report ------------------------------------------------------------------
    width = max(len(r["key"]) for r in rows)
    print(f"{'class':<{width}}  {'avail':>6} {'kept':>6} {'train':>6} {'val':>5} {'test':>5}")
    print(f"{'-' * width}  {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 5} {'-' * 5}")
    for r in rows:
        flag = " *" if r["capped"] else ""
        c = r["counts"]
        print(
            f"{r['key']:<{width}}  {r['available']:>6,} {r['kept']:>6,} "
            f"{c['train']:>6,} {c['val']:>5,} {c['test']:>5,}{flag}"
        )
    print(f"{'-' * width}  {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 5} {'-' * 5}")
    grand = sum(totals.values())
    print(
        f"{'TOTAL':<{width}}  {sum(sizes):>6,} {grand:>6,} "
        f"{totals['train']:>6,} {totals['val']:>5,} {totals['test']:>5,}"
    )
    print("\n* = capped")
    print(f"\nwrote {out_dir / 'class_map.json'}")
    print("next: .venv/bin/python ml/data/inspect.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

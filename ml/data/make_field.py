"""Stitch a synthetic field mosaic out of the test split, for exercising /agents.

    .venv/bin/python ml/data/make_field.py --crop tomato --disease late_blight

Lives in /ml because it draws from the processed dataset, and writes into agents/testdata/
because that is the only thing that consumes it.

**Be honest about what this is.** It is a harness for the tiling, skip-mask and batched
inference path — a grid where we know the ground truth of every cell, so a wrong answer is
obvious. It is NOT a lab-to-field test: the tiles are still studio photographs of detached
leaves on a neutral background, so a good score here says nothing about a real phone photo of
a real field. That measurement needs demo/field_photos/, and it belongs to A9.

The default layout mirrors contract/mock_run.json — 8x5, two soil cells, seven infected cells
in three clusters — so a real run and the frontend's mock render the same shape and any
difference is a genuine difference.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

_HERE = Path(__file__).resolve().parent
# Drop this script's own directory from sys.path — inspect.py next door shadows the stdlib
# `inspect` module, which numpy and PIL both need. See ml/data/__init__.py.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _HERE]

REPO_ROOT = _HERE.parent.parent
DEFAULT_PROCESSED = REPO_ROOT / "ml" / "data" / "processed"
DEFAULT_OUT = REPO_ROOT / "agents" / "testdata" / "field_tomato_late_blight.jpg"

# The mock run's layout, so the two are comparable cell for cell.
DEFAULT_INFECTED = "5,0 6,0 6,1 2,1 3,1 3,3 4,3"
DEFAULT_SOIL = "0,4 7,4"


def parse_cells(spec: str) -> set[tuple[int, int]]:
    return {
        (int(part.split(",")[0]), int(part.split(",")[1]))
        for part in spec.split()
        if part.strip()
    }


def pool(processed: Path, split: str, class_key: str) -> list[Path]:
    folder = processed / split / class_key
    if not folder.is_dir():
        available = sorted(p.name for p in (processed / split).iterdir()) if (processed / split).is_dir() else []
        raise SystemExit(f"no class {class_key!r} under {processed / split}\navailable: {available}")
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not files:
        raise SystemExit(f"{folder} is empty — run ml/data/prepare.py first")
    return files


def soil_tile(size: int, rng: random.Random) -> Image.Image:
    """Procedural dry-earth texture. Brown, low saturation, coarse grain — the thing the
    Scout's Excess Green mask has to reject."""
    gen = np.random.default_rng(rng.randrange(2**31))
    base = np.array([132, 104, 76], dtype=np.float32)  # dry loam, red > green > blue
    # Two noise scales: clods and grit. One alone reads as flat paper.
    clods = gen.normal(0, 26, (max(size // 8, 2), max(size // 8, 2))).astype(np.float32)
    clods = np.asarray(Image.fromarray(clods, mode="F").resize((size, size), Image.BICUBIC))
    grit = gen.normal(0, 9, (size, size)).astype(np.float32)
    arr = base + (clods + grit)[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def sky_tile(size: int, rng: random.Random) -> Image.Image:
    """Bright blue vertical gradient — the other thing above the horizon that is not crop."""
    top = np.array([120, 160, 215], dtype=np.float32)
    bottom = np.array([196, 214, 235], dtype=np.float32)
    ramp = np.linspace(0, 1, size, dtype=np.float32)[:, None, None]
    arr = top + (bottom - top) * ramp
    arr = arr + np.random.default_rng(rng.randrange(2**31)).normal(0, 4, (size, size, 3))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def leaf_tile(path: Path, size: int, rng: random.Random) -> Image.Image:
    """One dataset image, squared off, with light lighting jitter so the mosaic is not a
    flat grid of identically-exposed thumbnails."""
    img = Image.open(path).convert("RGB").resize((size, size), Image.BILINEAR)
    if rng.random() < 0.5:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    img = img.rotate(rng.choice([0, 90, 180, 270]))
    gain = rng.uniform(0.85, 1.15)
    arr = np.clip(np.asarray(img, dtype=np.float32) * gain, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED)
    p.add_argument("--split", default="test", help="draw from the held-out split by default")
    p.add_argument("--crop", default="tomato")
    p.add_argument("--disease", default="late_blight")
    p.add_argument("--cols", type=int, default=8)
    p.add_argument("--rows", type=int, default=5)
    p.add_argument("--tile-px", type=int, default=256)
    p.add_argument("--infected", default=DEFAULT_INFECTED, help='"x,y x,y ..." cells')
    p.add_argument("--soil", default=DEFAULT_SOIL, help='"x,y ..." cells painted as bare earth')
    p.add_argument("--sky", default="", help='"x,y ..." cells painted as sky')
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--quality", type=int, default=88, help="JPEG quality; the field photo is compressed too")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    rng = random.Random(args.seed)
    infected = parse_cells(args.infected)
    soil = parse_cells(args.soil)
    sky = parse_cells(args.sky)
    if overlap := (infected & soil) | (infected & sky) | (soil & sky):
        raise SystemExit(f"cells claimed twice: {sorted(overlap)}")

    healthy_pool = pool(args.processed_dir, args.split, f"{args.crop}__healthy")
    disease_pool = pool(args.processed_dir, args.split, f"{args.crop}__{args.disease}")

    size = args.tile_px
    canvas = Image.new("RGB", (args.cols * size, args.rows * size))
    truth: dict[tuple[int, int], str] = {}

    for y in range(args.rows):
        for x in range(args.cols):
            if (x, y) in soil:
                tile, label = soil_tile(size, rng), "skipped_soil"
            elif (x, y) in sky:
                tile, label = sky_tile(size, rng), "skipped_sky"
            elif (x, y) in infected:
                tile, label = leaf_tile(rng.choice(disease_pool), size, rng), args.disease
            else:
                tile, label = leaf_tile(rng.choice(healthy_pool), size, rng), "healthy"
            canvas.paste(tile, (x * size, y * size))
            truth[(x, y)] = label

    args.out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.out, format="JPEG", quality=args.quality)

    counts: dict[str, int] = {}
    for label in truth.values():
        counts[label] = counts.get(label, 0) + 1
    print(f"wrote {args.out}  {canvas.size[0]}x{canvas.size[1]}  ({args.out.stat().st_size / 1024:.0f} KB)")
    print(f"grid {args.cols}x{args.rows} = {len(truth)} cells, ground truth:")
    for label, count in sorted(counts.items()):
        print(f"  {label:<16} {count}")

    truth_path = args.out.with_suffix(".truth.txt")
    truth_path.write_text(
        "\n".join(f"t_{x:02d}_{y:02d} {truth[(x, y)]}" for y in range(args.rows) for x in range(args.cols)) + "\n"
    )
    print(f"wrote {truth_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

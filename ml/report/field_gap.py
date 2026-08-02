"""The lab-to-field gap — how much of the test-split number survives a real photograph.

    .venv/bin/python ml/report/field_gap.py

This is the honest chart in the pack. Every other number in ml/artifacts/ is measured on
PlantVillage, and PlantVillage is studio photography: one detached leaf, flat light, plain grey
background, sharp focus. AgriSentinel feeds the model 224px crops of a phone photo of a field.
A 95% test accuracy that becomes 60% on the demo image is not a good model, it is a good
number, and the difference is the whole risk in this project.

**What this measures, and what it does not.** Three bars:

- *test split, clean* — the headline accuracy. What the slides would say if nobody asked.
- *simulated field conditions* — the same images, same labels, pushed through blur, JPEG
  re-encoding, harsh light, rotation and a downscale-upscale round trip. Deterministic per
  image, so the bar is reproducible.
- *real field photos* — from demo/field_photos/, when they exist.

The middle bar is a **lower bound on the gap, not the gap**. It degrades image *quality* and
leaves image *content* alone: still one leaf, still centred, still nothing else in frame. The
real gap also includes composition — overlapping plants, soil, hands, shadow, a leaf at 40
degrees to the camera, a disease at a stage the dataset never photographed. No transform
produces those. Only photographs do.

So when demo/field_photos/ is empty the third bar is drawn as an empty hatched slot rather than
dropped, because a missing measurement that is visible on the slide is worth something and a
missing measurement nobody notices is worth less than nothing. Drop 30-50 labelled photos into
demo/field_photos/<class_key>/ and re-run; the bar fills itself in.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image, ImageEnhance, ImageFilter  # noqa: E402
from torch.utils.data import Dataset  # noqa: E402
from torchvision.datasets import ImageFolder  # noqa: E402

ML_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_DIR))
from data.augment import build_eval_transform  # noqa: E402
from datasets import DEFAULT_PROCESSED, build_loader, describe_device, pick_device  # noqa: E402
from engine import accuracy, evaluate, macro_f1  # noqa: E402
from eval import ESCALATION_THRESHOLD, load_checkpoint  # noqa: E402

ARTIFACTS = ML_DIR / "artifacts"
REPO_ROOT = ML_DIR.parent
FIELD_PHOTOS = REPO_ROOT / "demo" / "field_photos"

# Each preset is one plausible photograph, not a worst case. "field" is a phone held at arm's
# length over a row on a bright day; "mild" is the same phone on an overcast one.
SEVERITIES: dict[str, dict] = {
    "mild": {"blur": (0.0, 0.8), "jpeg": (55, 85), "bright": (0.85, 1.20), "rotate": 8, "scale": (0.70, 1.0)},
    "field": {"blur": (0.4, 1.6), "jpeg": (25, 55), "bright": (0.65, 1.45), "rotate": 20, "scale": (0.40, 0.85)},
}


def degrade(img: Image.Image, rng: random.Random, preset: dict) -> Image.Image:
    """One deterministic pass of field-photograph damage. Order matters: the JPEG goes last
    because ours is the second re-encode a tile suffers, after the phone's own."""
    w, h = img.size
    scale = rng.uniform(*preset["scale"])
    if scale < 0.99:  # distance and sensor limits, not a resize for speed
        small = img.resize((max(int(w * scale), 16), max(int(h * scale), 16)), Image.BILINEAR)
        img = small.resize((w, h), Image.BILINEAR)

    img = img.rotate(rng.uniform(-preset["rotate"], preset["rotate"]), resample=Image.BILINEAR, fillcolor=(124, 116, 104))
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(*preset["bright"]))
    img = ImageEnhance.Color(img).enhance(rng.uniform(0.75, 1.25))

    radius = rng.uniform(*preset["blur"])
    if radius > 0.05:
        img = img.filter(ImageFilter.GaussianBlur(radius))

    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=rng.randint(*preset["jpeg"]))
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


class DegradedFolder(Dataset):
    """An ImageFolder whose images are damaged before the eval transform sees them.

    Seeded by sample index rather than globally, so the same image is damaged the same way on
    every run whatever the worker count — a chart that moves by half a point between runs is a
    chart nobody can quote.
    """

    def __init__(self, base: ImageFolder, preset: dict, img_size: int = 224, seed: int = 0):
        self.samples = base.samples
        self.classes = base.classes
        self.preset = preset
        self.seed = seed
        self.transform = build_eval_transform(img_size)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, i: int):
        path, target = self.samples[i]
        img = Image.open(path).convert("RGB")
        return self.transform(degrade(img, random.Random(self.seed * 1_000_003 + i), self.preset)), target


def score(model, dataset, device, class_keys, batch_size: int, num_workers: int, label: str) -> dict:
    result = evaluate(model, build_loader(dataset, batch_size, False, num_workers), None, device, prefix=f"{label} ")
    y_true, y_pred, y_prob = result["y_true"], result["y_pred"], result["y_prob"]
    confidence = y_prob.max(axis=1)
    return {
        "label": label,
        "n": int(len(y_true)),
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(y_true, y_pred, len(class_keys)),
        "mean_confidence": float(confidence.mean()),
        "escalation_rate": float((confidence < ESCALATION_THRESHOLD).mean()),
    }


def real_photo_dataset(class_keys: list[str], img_size: int) -> ImageFolder | None:
    """demo/field_photos/<class_key>/*.jpg, if anyone has collected any.

    Read-only: demo/ belongs to Dev B. Unknown subdirectories are refused rather than guessed
    at, because a folder named "tomato_blight" silently scored against class index 4 is a wrong
    bar on a slide that looks exactly like a right one.
    """
    if not FIELD_PHOTOS.is_dir():
        return None
    subdirs = sorted(p.name for p in FIELD_PHOTOS.iterdir() if p.is_dir())
    if not subdirs:
        return None
    unknown = [d for d in subdirs if d not in class_keys]
    if unknown:
        print(f"demo/field_photos/: ignoring {unknown} — not class keys the model knows")
        return None
    dataset = ImageFolder(str(FIELD_PHOTOS), transform=build_eval_transform(img_size))
    # ImageFolder indexes only the classes present; remap to the model's full class order.
    remap = {i: class_keys.index(name) for i, name in enumerate(dataset.classes)}
    dataset.samples = [(p, remap[t]) for p, t in dataset.samples]
    dataset.targets = [t for _, t in dataset.samples]
    dataset.classes = class_keys
    return dataset if dataset.samples else None


def plot(rows: list[dict], missing: list[str], out: Path) -> None:
    labels = [r["label"] for r in rows] + missing
    # A missing measurement is drawn as an empty dashed frame the full height of the axis, not
    # as a zero-height bar: zero would read as "scored 0%", and an absent bar reads as nothing
    # at all. An empty slot is the only one of the three that says what is actually true.
    values = [r["accuracy"] * 100 for r in rows] + [100.0] * len(missing)
    colours = ["#2f6f4e", "#5c9b6f", "#9ec7a4"][: len(rows)] + ["none"] * len(missing)

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, values, color=colours, edgecolor="#333", linewidth=0.8)
    for bar in bars[len(rows):]:
        bar.set(edgecolor="#b0b0b0", linestyle="--", hatch="//", linewidth=1.0)
    for bar, row in zip(bars, rows):
        ax.text(bar.get_x() + bar.get_width() / 2, row["accuracy"] * 100 + 1.2,
                f"{row['accuracy'] * 100:.1f}%\nn={row['n']:,}", ha="center", fontsize=9)
    for bar in bars[len(rows):]:
        ax.text(bar.get_x() + bar.get_width() / 2, 50, "not\ncollected", ha="center",
                va="center", fontsize=10, color="#777")

    if len(rows) > 1:
        drop = (rows[0]["accuracy"] - rows[-1]["accuracy"]) * 100
        ax.set_title(f"AgriSentinel — accuracy from lab to field  (−{drop:.1f} pts simulated)")
    else:
        ax.set_title("AgriSentinel — accuracy from lab to field")
    ax.set_ylabel("top-1 accuracy (%)")
    ax.set_ylim(0, 105)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def render_md(rows: list[dict], has_real: bool) -> str:
    head = "| condition | n | accuracy | macro-F1 | mean conf | escalated @0.75 |\n|---|---:|---:|---:|---:|---:|"
    body = "\n".join(
        f"| {r['label']} | {r['n']:,} | {r['accuracy']:.4f} | {r['macro_f1']:.4f} | "
        f"{r['mean_confidence']:.3f} | {r['escalation_rate']:.1%} |"
        for r in rows
    )
    drop = (rows[0]["accuracy"] - rows[-1]["accuracy"]) * 100
    caveat = (
        "No real field photographs have been collected, so the third bar is empty. The "
        "simulated number is a **lower bound on the gap**: it degrades image quality and leaves "
        "image content alone — one leaf, centred, nothing else in frame. Overlapping plants, "
        "soil, shadow and oblique angles are not simulated and are most of what makes a field "
        "photo hard. Treat the drop above as the floor."
        if not has_real else
        "The real-photo bar is the one to quote. The simulated bar is kept beside it to show how "
        "much of the gap is image quality alone."
    )
    return (
        "# Lab to field\n\n"
        f"{head}\n{body}\n\n"
        f"Simulated field conditions cost **{drop:.1f} accuracy points** against the clean test "
        f"split, and push the escalation rate from {rows[0]['escalation_rate']:.1%} to "
        f"{rows[-1]['escalation_rate']:.1%} — the Second-Opinion agent exists for exactly that "
        "second number.\n\n"
        f"{caveat}\n"
    )


def build(
    checkpoint: Path,
    processed_dir: Path = DEFAULT_PROCESSED,
    split: str = "test",
    batch_size: int = 64,
    num_workers: int = 4,
    device: str = "auto",
    limit: int = 0,
) -> list[dict]:
    device_t = pick_device(device)
    print(f"device: {describe_device(device_t)}")
    model, class_keys, ckpt = load_checkpoint(checkpoint, device_t)
    img_size = ckpt.get("img_size", 224)

    clean = ImageFolder(str(processed_dir / split), transform=build_eval_transform(img_size))
    if limit:  # a sampled sweep while iterating; the committed chart uses the whole split
        keep = random.Random(0).sample(range(len(clean.samples)), min(limit, len(clean.samples)))
        clean.samples = [clean.samples[i] for i in sorted(keep)]
        clean.targets = [t for _, t in clean.samples]

    rows = [score(model, clean, device_t, class_keys, batch_size, num_workers, "test split, clean")]
    for name, preset in SEVERITIES.items():
        degraded = DegradedFolder(clean, preset, img_size)
        rows.append(score(model, degraded, device_t, class_keys, batch_size, num_workers, f"simulated: {name}"))

    real = real_photo_dataset(class_keys, img_size)
    if real is not None:
        rows.append(score(model, real, device_t, class_keys, batch_size, num_workers, "real field photos"))

    plot(rows, [] if real is not None else ["real field photos"], ARTIFACTS / "lab_vs_field.png")
    (ARTIFACTS / "lab_vs_field.md").write_text(render_md(rows, real is not None), encoding="utf-8")
    (ARTIFACTS / "lab_vs_field.json").write_text(
        json.dumps({"rows": rows, "real_photos": real is not None, "severities": SEVERITIES}, indent=2) + "\n"
    )
    print(f"\nwrote {ARTIFACTS}/lab_vs_field.png, .md, .json")
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--checkpoint", type=Path, default=ML_DIR / "checkpoints" / "best.pt")
    p.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED)
    p.add_argument("--split", default="test")
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--num-workers", type=int, default=4)
    p.add_argument("--device", default="auto")
    p.add_argument("--limit", type=int, default=0, help="sample N images per condition (0 = all)")
    args = p.parse_args()

    rows = build(args.checkpoint, args.processed_dir, args.split, args.batch_size,
                 args.num_workers, args.device, args.limit)
    print()
    for row in rows:
        print(f"  {row['label']:<24} acc {row['accuracy']:.4f}  escalated {row['escalation_rate']:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

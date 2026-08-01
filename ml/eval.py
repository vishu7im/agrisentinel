"""Evaluate the best checkpoint on the held-out test split.

    .venv/bin/python ml/eval.py

Produces the numbers A9 puts on a slide: accuracy, macro-F1, a per-class
precision/recall/support table, and a normalised confusion matrix PNG.

It also reports the **confidence distribution**, which is not a standard eval output but is
the one this project actually needs. A5's orchestrator escalates any tile below 0.75
confidence to the Second-Opinion agent. If the model turns out to answer above 0.75 on
essentially everything, that escalation path never fires and one of the agents in the
architecture diagram is decorative. The escalation-rate line below is how we find that out
before demo day rather than during it.

Writes ml/artifacts/{metrics.json, confusion_matrix.png, per_class_table.md}.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: this runs over SSH and in CI, never in a window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datasets import (  # noqa: E402
    DEFAULT_PROCESSED,
    build_dataset,
    build_loader,
    describe_device,
    pick_device,
)
from engine import accuracy, evaluate, macro_f1  # noqa: E402
from model import SmallCNN, build_efficientnet  # noqa: E402

ML_DIR = Path(__file__).resolve().parent
ARTIFACTS = ML_DIR / "artifacts"
DEFAULT_CKPT = ML_DIR / "checkpoints" / "best.pt"

ESCALATION_THRESHOLD = 0.75  # must match agents/orchestrator.py in A5


def load_checkpoint(path: Path, device: torch.device):
    if not path.exists():
        raise SystemExit(f"{path} missing. Run ml/train.py first.")
    ckpt = torch.load(path, map_location=device, weights_only=False)
    class_keys = ckpt["class_keys"]
    arch = ckpt.get("arch", "efficientnet_b0")
    if arch == "small_cnn":
        model = SmallCNN(len(class_keys))
    else:
        model = build_efficientnet(len(class_keys), pretrained=False)
    model.load_state_dict(ckpt["state_dict"])
    return model.to(device).eval(), class_keys, ckpt


def plot_confusion_matrix(cm: np.ndarray, class_keys: list[str], out_path: Path) -> None:
    """Row-normalised, so the small classes are readable next to the big ones."""
    with np.errstate(invalid="ignore", divide="ignore"):
        norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)
    norm = np.nan_to_num(norm)

    fig, ax = plt.subplots(figsize=(11, 9))
    im = ax.imshow(norm, cmap="viridis", vmin=0, vmax=1)
    ax.set_xticks(range(len(class_keys)), class_keys, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(class_keys)), class_keys, fontsize=8)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title("AgriSentinel — test-split confusion matrix (row-normalised)")

    for i in range(len(class_keys)):
        for j in range(len(class_keys)):
            if cm[i, j] == 0:
                continue
            ax.text(
                j, i, f"{norm[i, j]:.2f}", ha="center", va="center", fontsize=7,
                color="white" if norm[i, j] < 0.6 else "black",
            )

    fig.colorbar(im, ax=ax, fraction=0.046, label="fraction of true class")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def per_class_rows(y_true, y_pred, class_keys) -> list[dict]:
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=range(len(class_keys)), zero_division=0
    )
    return [
        {
            "class": key,
            "precision": float(precision[i]),
            "recall": float(recall[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
        for i, key in enumerate(class_keys)
    ]


def render_table(rows: list[dict]) -> str:
    width = max(len(r["class"]) for r in rows)
    lines = [
        f"| {'class':<{width}} | precision | recall |    f1 | support |",
        f"|{'-' * (width + 2)}|----------:|-------:|------:|--------:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['class']:<{width}} |     {r['precision']:.3f} |  {r['recall']:.3f} | "
            f"{r['f1']:.3f} | {r['support']:>7,} |"
        )
    return "\n".join(lines)


def run_eval(
    checkpoint: Path,
    processed_dir: Path = DEFAULT_PROCESSED,
    split: str = "test",
    batch_size: int = 64,
    num_workers: int = 4,
    device: str = "auto",
    tag: str = "",
) -> dict:
    """Evaluate a checkpoint and write every artifact for it. Returns the metrics dict.

    baseline.py calls this too, rather than computing its own numbers. One code path means
    metrics.json and metrics_baseline.json cannot end up with different schemas depending
    on which script wrote them last — which is exactly what happened the first time these
    were separate.
    """
    device_t = pick_device(device)
    print(f"device: {describe_device(device_t)}")

    model, class_keys, ckpt = load_checkpoint(checkpoint, device_t)
    print(
        f"checkpoint: {checkpoint} ({ckpt.get('arch')}, stage {ckpt.get('stage')} "
        f"epoch {ckpt.get('epoch')}, val_macro_f1 {ckpt.get('val_macro_f1', float('nan')):.4f})"
    )

    dataset = build_dataset(processed_dir, split, False, ckpt.get("img_size", 224))
    loader = build_loader(dataset, batch_size, False, num_workers)
    print(f"{split} split: {len(dataset):,} images over {len(class_keys)} classes\n")

    result = evaluate(model, loader, None, device_t, prefix=f"{split} ")
    y_true, y_pred, y_prob = result["y_true"], result["y_pred"], result["y_prob"]

    acc = accuracy(y_true, y_pred)
    f1 = macro_f1(y_true, y_pred, len(class_keys))
    rows = per_class_rows(y_true, y_pred, class_keys)

    confidence = y_prob.max(axis=1)
    below = confidence < ESCALATION_THRESHOLD
    escalation_rate = float(below.mean())
    correct_when_confident = float((y_true == y_pred)[~below].mean()) if (~below).any() else 0.0
    correct_when_unsure = float((y_true == y_pred)[below].mean()) if below.any() else 0.0

    suffix = f"_{tag}" if tag else ""
    cm = confusion_matrix(y_true, y_pred, labels=range(len(class_keys)))
    plot_confusion_matrix(cm, class_keys, ARTIFACTS / f"confusion_matrix{suffix}.png")

    table = render_table(rows)
    print(f"\n{table}\n")
    print(f"accuracy        {acc:.4f}")
    print(f"macro-F1        {f1:.4f}")
    print(f"mean confidence {confidence.mean():.4f}   median {np.median(confidence):.4f}")
    print(
        f"below {ESCALATION_THRESHOLD} conf   {below.sum():,}/{len(below):,} "
        f"({escalation_rate:.1%}) — these are the tiles A5 escalates"
    )
    print(f"  accuracy when confident {correct_when_confident:.4f}")
    print(f"  accuracy when unsure    {correct_when_unsure:.4f}")

    metrics = {
        "checkpoint": str(checkpoint),
        "arch": ckpt.get("arch"),
        "split": split,
        "n_images": int(len(y_true)),
        "n_classes": len(class_keys),
        "params": sum(p.numel() for p in model.parameters()),
        "epochs": ckpt.get("epoch"),
        "val_macro_f1": ckpt.get("val_macro_f1"),
        "accuracy": acc,
        "macro_f1": f1,
        "per_class": rows,
        "confidence": {
            "mean": float(confidence.mean()),
            "median": float(np.median(confidence)),
            "escalation_threshold": ESCALATION_THRESHOLD,
            "escalation_rate": escalation_rate,
            "accuracy_when_confident": correct_when_confident,
            "accuracy_when_unsure": correct_when_unsure,
        },
        "confusion_matrix": cm.tolist(),
        "class_keys": class_keys,
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / f"metrics{suffix}.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (ARTIFACTS / f"per_class_table{suffix}.md").write_text(
        f"# Per-class results — {ckpt.get('arch')} on the {split} split\n\n"
        f"{table}\n\naccuracy {acc:.4f} · macro-F1 {f1:.4f}\n"
    )

    print(f"\nwrote {ARTIFACTS}/metrics{suffix}.json")
    print(f"wrote {ARTIFACTS}/confusion_matrix{suffix}.png")
    print(f"wrote {ARTIFACTS}/per_class_table{suffix}.md")
    return metrics


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED)
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    p.add_argument("--split", default="test")
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--num-workers", type=int, default=4)
    p.add_argument("--device", default="auto")
    p.add_argument("--tag", default="", help="suffix for artifact filenames, e.g. 'baseline'")
    args = p.parse_args()

    run_eval(
        checkpoint=args.checkpoint,
        processed_dir=args.processed_dir,
        split=args.split,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        device=args.device,
        tag=args.tag,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

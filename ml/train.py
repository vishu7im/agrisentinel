"""Two-stage fine-tune of EfficientNet-B0 on the prepared PlantVillage split.

    .venv/bin/python ml/train.py

Stage 1 (3 epochs, frozen backbone) trains only the new classification head. Stage 2
(5 epochs, last two feature blocks unfrozen, 10x lower LR) adapts the late features to leaf
texture. Doing it in one stage instead lets the randomly-initialised head's early gradients
wreck the pretrained backbone in the first few hundred steps.

The best checkpoint is chosen by **validation macro-F1, not accuracy**. Accuracy is
dominated by the large tomato classes; macro-F1 is the number that notices when potato
healthy is being ignored.

Writes ml/checkpoints/best.pt and appends per-epoch rows to ml/artifacts/train_log.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datasets import (  # noqa: E402
    DEFAULT_PROCESSED,
    build_dataset,
    build_loader,
    describe_device,
    load_class_keys,
    pick_device,
)
from engine import accuracy, evaluate, macro_f1, train_one_epoch  # noqa: E402
from model import build_efficientnet, count_parameters, set_stage  # noqa: E402

ML_DIR = Path(__file__).resolve().parent
DEFAULT_CKPT = ML_DIR / "checkpoints" / "best.pt"
DEFAULT_LOG = ML_DIR / "artifacts" / "train_log.csv"

LOG_FIELDS = [
    "stage", "epoch", "lr", "train_loss", "val_loss", "val_acc", "val_macro_f1", "seconds"
]


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED)
    p.add_argument("--out", type=Path, default=DEFAULT_CKPT)
    p.add_argument("--log", type=Path, default=DEFAULT_LOG)
    p.add_argument("--epochs-stage1", type=int, default=3)
    p.add_argument("--epochs-stage2", type=int, default=5)
    p.add_argument("--batch-size", type=int, default=32, help="32 fits a 4 GB card with AMP")
    p.add_argument("--lr-head", type=float, default=1e-3)
    p.add_argument("--lr-finetune", type=float, default=1e-4)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--img-size", type=int, default=224)
    p.add_argument("--num-workers", type=int, default=4)
    p.add_argument("--device", default="auto")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--no-amp", action="store_true", help="disable mixed precision")
    return p.parse_args()


def run_stage(
    *,
    stage: int,
    epochs: int,
    lr: float,
    model: nn.Module,
    train_loader,
    val_loader,
    criterion: nn.Module,
    device: torch.device,
    args: argparse.Namespace,
    scaler: torch.amp.GradScaler | None,
    class_keys: list[str],
    writer: csv.DictWriter,
    log_file,
    best: dict,
) -> None:
    params = set_stage(model, stage)
    total, trainable = count_parameters(model)
    print(
        f"\n=== stage {stage}: {epochs} epochs, lr {lr:g} — "
        f"{trainable:,}/{total:,} params trainable ({trainable / total:.1%}) ==="
    )

    optimizer = torch.optim.AdamW(params, lr=lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=max(epochs * len(train_loader), 1)
    )

    for epoch in range(1, epochs + 1):
        started = time.time()
        print(f"\nstage {stage} epoch {epoch}/{epochs}")
        train_loss = train_one_epoch(
            model, train_loader, criterion, optimizer, device, scaler, scheduler
        )
        result = evaluate(model, val_loader, criterion, device, prefix="val  ")

        val_acc = accuracy(result["y_true"], result["y_pred"])
        val_f1 = macro_f1(result["y_true"], result["y_pred"], len(class_keys))
        seconds = time.time() - started
        print(
            f"  train_loss {train_loss:.4f} | val_loss {result['loss']:.4f} | "
            f"val_acc {val_acc:.4f} | val_macro_f1 {val_f1:.4f} | {seconds:.0f}s"
        )

        writer.writerow(
            {
                "stage": stage,
                "epoch": epoch,
                "lr": optimizer.param_groups[0]["lr"],
                "train_loss": round(train_loss, 6),
                "val_loss": round(result["loss"], 6),
                "val_acc": round(val_acc, 6),
                "val_macro_f1": round(val_f1, 6),
                "seconds": round(seconds, 1),
            }
        )
        log_file.flush()

        if val_f1 > best["val_macro_f1"]:
            best.update(
                {"val_macro_f1": val_f1, "val_acc": val_acc, "stage": stage, "epoch": epoch}
            )
            args.out.parent.mkdir(parents=True, exist_ok=True)
            torch.save(
                {
                    "arch": "efficientnet_b0",
                    "state_dict": model.state_dict(),
                    "class_keys": class_keys,
                    "img_size": args.img_size,
                    "val_macro_f1": val_f1,
                    "val_acc": val_acc,
                    "stage": stage,
                    "epoch": epoch,
                    "seed": args.seed,
                },
                args.out,
            )
            print(f"  ^ new best macro-F1, saved {args.out}")


def main() -> int:
    args = parse_args()
    seed_everything(args.seed)

    device = pick_device(args.device)
    use_amp = device.type == "cuda" and not args.no_amp
    print(f"device: {describe_device(device)}   amp: {use_amp}")

    class_keys = load_class_keys(args.processed_dir)
    train_ds = build_dataset(args.processed_dir, "train", True, args.img_size)
    val_ds = build_dataset(args.processed_dir, "val", False, args.img_size)
    train_loader = build_loader(train_ds, args.batch_size, True, args.num_workers)
    val_loader = build_loader(val_ds, args.batch_size, False, args.num_workers)
    print(
        f"{len(class_keys)} classes | train {len(train_ds):,} | val {len(val_ds):,} | "
        f"batch {args.batch_size}"
    )

    model = build_efficientnet(len(class_keys), pretrained=True).to(device)
    # Light label smoothing. Not for accuracy — for calibration. The A5 orchestrator
    # escalates any tile below 0.75 confidence, and an uncalibrated model that answers 0.999
    # to everything makes that gate dead code.
    criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
    scaler = torch.amp.GradScaler("cuda") if use_amp else None

    args.log.parent.mkdir(parents=True, exist_ok=True)
    best = {"val_macro_f1": -1.0, "val_acc": 0.0, "stage": 0, "epoch": 0}
    started = time.time()

    with args.log.open("w", newline="") as log_file:
        writer = csv.DictWriter(log_file, fieldnames=LOG_FIELDS)
        writer.writeheader()
        for stage, epochs, lr in (
            (1, args.epochs_stage1, args.lr_head),
            (2, args.epochs_stage2, args.lr_finetune),
        ):
            if epochs <= 0:
                continue
            run_stage(
                stage=stage, epochs=epochs, lr=lr, model=model, train_loader=train_loader,
                val_loader=val_loader, criterion=criterion, device=device, args=args,
                scaler=scaler, class_keys=class_keys, writer=writer, log_file=log_file,
                best=best,
            )

    if best["stage"] == 0:
        print("no epochs ran", file=sys.stderr)
        return 1

    print(
        f"\ndone in {(time.time() - started) / 60:.1f} min\n"
        f"best: stage {best['stage']} epoch {best['epoch']} — "
        f"val_macro_f1 {best['val_macro_f1']:.4f}, val_acc {best['val_acc']:.4f}"
    )
    print(f"checkpoint: {args.out}\nlog: {args.log}")
    print(json.dumps(best, indent=2))
    print("\nnext: .venv/bin/python ml/eval.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The train and inference loops. Shared by train.py, baseline.py and eval.py.

Three scripts need the exact same forward pass; three copies of it is three places for the
normalisation or the argmax to drift. Everything here is model-agnostic.
"""

from __future__ import annotations

import time

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader


def _progress(prefix: str, step: int, total: int, loss: float, started: float) -> None:
    """Single rewriting line — a training run that prints nothing looks like a hang."""
    elapsed = time.time() - started
    rate = step / elapsed if elapsed > 0 else 0.0
    eta = (total - step) / rate if rate > 0 else 0.0
    print(
        f"\r  {prefix} {step:>4}/{total}  loss {loss:.4f}  "
        f"{rate:4.1f} it/s  eta {eta:5.0f}s",
        end="",
        flush=True,
    )


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    scaler: torch.amp.GradScaler | None = None,
    scheduler: torch.optim.lr_scheduler.LRScheduler | None = None,
    prefix: str = "train",
) -> float:
    """One pass over the training set. Returns mean loss."""
    model.train()
    total_loss = 0.0
    total_seen = 0
    started = time.time()

    for step, (images, targets) in enumerate(loader, start=1):
        images = images.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)
        if scaler is not None:
            with torch.amp.autocast("cuda"):
                loss = criterion(model(images), targets)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            loss = criterion(model(images), targets)
            loss.backward()
            optimizer.step()

        if scheduler is not None:
            scheduler.step()

        batch = targets.size(0)
        total_loss += loss.item() * batch
        total_seen += batch
        if step % 10 == 0 or step == len(loader):
            _progress(prefix, step, len(loader), total_loss / total_seen, started)

    print()
    return total_loss / max(total_seen, 1)


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module | None,
    device: torch.device,
    prefix: str = "eval",
) -> dict:
    """One pass with no gradients.

    Returns loss, the true and predicted label arrays, and the full softmax matrix. eval.py
    needs the probabilities for confidence analysis; train.py only reads y_true/y_pred.
    """
    model.eval()
    total_loss = 0.0
    total_seen = 0
    y_true: list[np.ndarray] = []
    y_pred: list[np.ndarray] = []
    y_prob: list[np.ndarray] = []
    started = time.time()

    for step, (images, targets) in enumerate(loader, start=1):
        images = images.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)

        logits = model(images)
        if criterion is not None:
            loss = criterion(logits, targets)
            total_loss += loss.item() * targets.size(0)
        total_seen += targets.size(0)

        probs = torch.softmax(logits.float(), dim=1)
        y_true.append(targets.cpu().numpy())
        y_pred.append(probs.argmax(dim=1).cpu().numpy())
        y_prob.append(probs.cpu().numpy())

        if step % 10 == 0 or step == len(loader):
            _progress(prefix, step, len(loader), total_loss / max(total_seen, 1), started)

    print()
    return {
        "loss": total_loss / max(total_seen, 1) if criterion is not None else float("nan"),
        "y_true": np.concatenate(y_true),
        "y_pred": np.concatenate(y_pred),
        "y_prob": np.concatenate(y_prob),
    }


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, num_classes: int) -> float:
    """Unweighted mean per-class F1.

    Macro rather than accuracy or micro-F1 because the classes are still uneven after
    capping, and a model that ignores potato_healthy entirely should not be allowed to look
    good on the strength of the tomato classes.
    """
    f1s = []
    for c in range(num_classes):
        tp = int(np.sum((y_pred == c) & (y_true == c)))
        fp = int(np.sum((y_pred == c) & (y_true != c)))
        fn = int(np.sum((y_pred != c) & (y_true == c)))
        denom = 2 * tp + fp + fn
        f1s.append(2 * tp / denom if denom else 0.0)
    return float(np.mean(f1s))


def accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(y_true == y_pred))

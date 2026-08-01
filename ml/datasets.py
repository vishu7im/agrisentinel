"""DataLoader construction, shared by train.py, eval.py and baseline.py.

The one thing worth reading here is `load_class_keys`, which asserts that the class order
torchvision assigns matches the order recorded in class_map.json. If those ever diverge,
every prediction the system makes is silently mislabelled — the model is still 97% accurate
and every answer is wrong. It is a cheap assert against an expensive afternoon.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder

# ml/, not ml/data — putting ml/data on sys.path would shadow the stdlib `inspect` module
# with ml/data/inspect.py and break torch. See ml/data/__init__.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data.augment import build_eval_transform, build_train_transform  # noqa: E402

ML_DIR = Path(__file__).resolve().parent
DEFAULT_PROCESSED = ML_DIR / "data" / "processed"


def load_class_map(processed_dir: Path = DEFAULT_PROCESSED) -> dict:
    path = processed_dir / "class_map.json"
    if not path.exists():
        raise SystemExit(f"{path} missing. Run ml/data/prepare.py first.")
    return json.loads(path.read_text())


def load_class_keys(processed_dir: Path = DEFAULT_PROCESSED) -> list[str]:
    class_map = load_class_map(processed_dir)
    return [c["key"] for c in sorted(class_map["classes"], key=lambda c: c["index"])]


def build_dataset(
    processed_dir: Path,
    split: str,
    train_mode: bool,
    img_size: int = 224,
) -> ImageFolder:
    """ImageFolder for one split, with the transform that split should get.

    train_mode is separate from split on purpose: baseline.py and the A9 lab-vs-field chart
    both want to read the train split *without* augmentation.
    """
    split_dir = processed_dir / split
    if not split_dir.is_dir():
        raise SystemExit(f"{split_dir} missing. Run ml/data/prepare.py first.")

    transform = (
        build_train_transform(img_size) if train_mode else build_eval_transform(img_size)
    )
    dataset = ImageFolder(str(split_dir), transform=transform)

    expected = load_class_keys(processed_dir)
    if dataset.classes != expected:
        raise SystemExit(
            "class order mismatch between the processed tree and class_map.json.\n"
            f"  ImageFolder: {dataset.classes}\n"
            f"  class_map:   {expected}\n"
            "Re-run ml/data/prepare.py — do not train against this."
        )
    return dataset


def build_loader(
    dataset: ImageFolder,
    batch_size: int,
    shuffle: bool,
    num_workers: int = 4,
) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
        persistent_workers=num_workers > 0,
        drop_last=False,
    )


def pick_device(requested: str = "auto") -> torch.device:
    if requested != "auto":
        return torch.device(requested)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def describe_device(device: torch.device) -> str:
    if device.type == "cuda":
        props = torch.cuda.get_device_properties(device)
        return f"cuda ({props.name}, {props.total_memory / 1024**3:.1f} GB)"
    return "cpu"

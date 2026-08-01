"""Tile preprocessing in PIL and numpy only — a byte-exact port of the training transform.

This file exists because `/agents` cannot import torchvision. The backend deliberately ships
without torch: inference is ONNX Runtime on CPU, and a 3 GB training stack on a demo laptop
is a liability. So `ml/data/augment.py:build_eval_transform` has to be reimplemented here
rather than imported, and the two must agree exactly. If they drift, the model sees a
different distribution than the one `ml/artifacts/metrics.json` was measured on, and the
accuracy on the slide stops describing the demo.

Two details are load-bearing and both are easy to get subtly wrong:

  * the resize **truncates** the long side (`int(...)`, not `round(...)`)
  * the centre crop offset **rounds** (`int(round(...))`, not floor division)

Getting the crop wrong shifts every tile by one pixel. It raises no error, the predictions
mostly still agree, and it quietly costs accuracy — which is exactly how it survived the
first attempt at this file. `agents/verify_preprocess.py` is the check that caught it; run
that, not your intuition.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

IMG_SIZE = 224
RESIZE_RATIO = 1.14  # 224 -> 255, matching build_eval_transform's int(img_size * 1.14)


def resize_short_side(img: Image.Image, short_target: int) -> Image.Image:
    """torchvision `Resize(int)`: scale so the SHORT side hits the target, keep aspect.

    The long side truncates. torchvision computes `int(size * long / short)` with no
    rounding, and a half-pixel disagreement here changes which pixels survive the crop.
    """
    w, h = img.size
    short, long = (w, h) if w <= h else (h, w)
    if short == short_target:
        return img
    new_long = int(short_target * long / short)
    new_size = (short_target, new_long) if w <= h else (new_long, short_target)
    return img.resize(new_size, Image.BILINEAR)


def center_crop(img: Image.Image, size: int) -> Image.Image:
    """torchvision `CenterCrop`: offset is int(round((n - size) / 2.0)), NOT (n - size) // 2.

    For a 255x255 input the two differ by one pixel — 16 versus 15.
    """
    w, h = img.size
    if w < size or h < size:  # torchvision pads here; our tiles never hit this path
        raise ValueError(f"tile {w}x{h} is smaller than the {size}px crop — resize first")
    left = int(round((w - size) / 2.0))
    top = int(round((h - size) / 2.0))
    return img.crop((left, top, left + size, top + size))


def to_chw_float(img: Image.Image) -> np.ndarray:
    """`ToTensor` then `Normalize`: uint8 HWC -> float32 CHW in [0,1], then standardised."""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
    return np.ascontiguousarray(arr.transpose(2, 0, 1), dtype=np.float32)


def preprocess_tile(img: Image.Image, img_size: int = IMG_SIZE) -> np.ndarray:
    """One tile -> a (3, H, W) float32 array ready to stack into an ONNX batch."""
    resized = resize_short_side(img.convert("RGB"), int(img_size * RESIZE_RATIO))
    return to_chw_float(center_crop(resized, img_size))


def preprocess_batch(images: list[Image.Image], img_size: int = IMG_SIZE) -> np.ndarray:
    """(N, 3, H, W). The ONNX graph has a dynamic batch axis, so N is free."""
    if not images:
        return np.zeros((0, 3, img_size, img_size), dtype=np.float32)
    return np.stack([preprocess_tile(im, img_size) for im in images])


# --- test-time augmentation, for the A5 Second-Opinion agent ---------------------------
#
# Identity, horizontal flip, vertical flip, 180 degree rotation. All four are label-
# preserving for an overhead leaf photo and all four are cheap. They are applied to the
# already-cropped array rather than to the PIL image, so a TTA pass costs four ONNX runs and
# only one decode + resize. Mirrors ml/data/augment.py:build_tta_transforms.

TTA_VIEWS = ("identity", "hflip", "vflip", "rot180")


def apply_tta(batch: np.ndarray, view: str) -> np.ndarray:
    """Flip an already-preprocessed (N, 3, H, W) batch. Axis 2 is height, axis 3 is width."""
    if view == "identity":
        return batch
    if view == "hflip":
        return np.ascontiguousarray(batch[:, :, :, ::-1])
    if view == "vflip":
        return np.ascontiguousarray(batch[:, :, ::-1, :])
    if view == "rot180":
        return np.ascontiguousarray(batch[:, :, ::-1, ::-1])
    raise ValueError(f"unknown TTA view {view!r} — expected one of {TTA_VIEWS}")


def softmax(logits: np.ndarray) -> np.ndarray:
    """Row-wise, shifted for stability. The ONNX graph emits raw logits by design: the
    Second-Opinion agent averages probabilities across TTA views, and averaging inside the
    graph would have made that impossible without a re-export."""
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=-1, keepdims=True)

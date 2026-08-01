"""Transform pipelines, aimed squarely at the lab-to-field gap.

PlantVillage is studio photography: one detached leaf, flat lighting, plain grey background,
sharp focus. AgriSentinel feeds the model 224px *crops of a phone photo of a field* —
motion-blurred, harshly lit, JPEG-compressed twice over, with soil and neighbouring leaves
in frame. A model trained on the raw dataset scores ~99% on its own test split and then
falls over on the demo image. That gap is the single biggest technical risk in this project,
and this file is the mitigation.

Every train-time transform below corresponds to a specific way a field photo differs:

    RandomResizedCrop   leaves are partial and off-centre in a tile, not centred
    H/V flip + rotation an overhead field photo has no canonical "up"
    ColorJitter         midday sun vs overcast vs golden hour
    GaussianBlur        phone camera, moving hand, leaf out of the focal plane
    RandomJPEG          phone JPEG, then our own re-encode when tiling
    RandomGrayscale     a weak stand-in for unusual white balance

Eval transforms are deliberately plain — resize and centre crop — so the reported test
number measures the model, not the augmenter.
"""

from __future__ import annotations

import io
import random

from PIL import Image
from torchvision import transforms

# ImageNet statistics. EfficientNet-B0's pretrained weights were fitted with these; using
# dataset-specific stats instead would quietly break transfer learning.
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

IMG_SIZE = 224


class RandomJPEGCompression:
    """Re-encode the image as JPEG at a random quality.

    Not in torchvision, and worth the 12 lines: our own pipeline JPEG-compresses tiles on
    the way in, so compression artefacts are not a hypothetical distribution shift, they
    are guaranteed to be present at inference time.
    """

    def __init__(self, quality_range: tuple[int, int] = (30, 90), p: float = 0.5):
        self.quality_range = quality_range
        self.p = p

    def __call__(self, img: Image.Image) -> Image.Image:
        if random.random() > self.p:
            return img
        quality = random.randint(*self.quality_range)
        buffer = io.BytesIO()
        img.convert("RGB").save(buffer, format="JPEG", quality=quality)
        buffer.seek(0)
        return Image.open(buffer).convert("RGB")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(quality_range={self.quality_range}, p={self.p})"


def build_train_transform(img_size: int = IMG_SIZE, normalize: bool = True):
    """Augmented pipeline for training.

    Set normalize=False to get tensors you can actually look at — inspect.py does this.
    """
    steps = [
        RandomJPEGCompression(quality_range=(30, 90), p=0.5),
        transforms.RandomResizedCrop(img_size, scale=(0.6, 1.0), ratio=(0.8, 1.25)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomVerticalFlip(p=0.5),
        transforms.RandomRotation(degrees=25, fill=(124, 116, 104)),
        transforms.ColorJitter(brightness=0.35, contrast=0.35, saturation=0.35, hue=0.06),
        transforms.RandomApply([transforms.GaussianBlur(kernel_size=5, sigma=(0.1, 2.0))], p=0.3),
        transforms.RandomGrayscale(p=0.05),
        transforms.ToTensor(),
    ]
    if normalize:
        steps.append(transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD))
    return transforms.Compose(steps)


def build_eval_transform(img_size: int = IMG_SIZE, normalize: bool = True):
    """Deterministic pipeline for val, test and production inference.

    agents/diagnostician.py must preprocess tiles exactly this way. If the two ever drift,
    the ONNX model sees a different distribution than it was evaluated on and the accuracy
    on the slide stops describing the demo.
    """
    steps = [
        transforms.Resize(int(img_size * 1.14)),  # 224 -> 256, the standard ImageNet ratio
        transforms.CenterCrop(img_size),
        transforms.ToTensor(),
    ]
    if normalize:
        steps.append(transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD))
    return transforms.Compose(steps)


def build_tta_transforms(img_size: int = IMG_SIZE):
    """The four views the A5 Second-Opinion agent averages over a low-confidence tile.

    Identity, horizontal flip, vertical flip, 180 degree rotation. All label-preserving for
    an overhead leaf photo, all cheap, and averaging them is a genuine confidence boost
    rather than four looks at the same pixels.
    """
    base = [
        transforms.Resize(int(img_size * 1.14)),
        transforms.CenterCrop(img_size),
    ]
    tail = [transforms.ToTensor(), transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)]
    views = {
        "identity": [],
        "hflip": [transforms.RandomHorizontalFlip(p=1.0)],
        "vflip": [transforms.RandomVerticalFlip(p=1.0)],
        "rot180": [transforms.RandomHorizontalFlip(p=1.0), transforms.RandomVerticalFlip(p=1.0)],
    }
    return {name: transforms.Compose(base + mid + tail) for name, mid in views.items()}

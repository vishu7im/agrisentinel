"""Model definitions. Shared by train.py, baseline.py, eval.py and export_onnx.py.

Keeping the constructors here means the architecture a checkpoint was trained with and the
architecture it is loaded into can never disagree — a class of bug that costs an hour and
looks like "the model got worse after export".
"""

from __future__ import annotations

import torch
from torch import nn
from torchvision import models


def build_efficientnet(num_classes: int, pretrained: bool = True) -> nn.Module:
    """EfficientNet-B0 with the ImageNet head swapped for ours.

    B0 over anything larger for one reason: this has to run per tile, on CPU, on whatever
    laptop is plugged into the projector. 40 tiles x a heavier backbone is the difference
    between a 4-second scan and a 40-second one, and a 40-second scan is not a demo.
    """
    weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
    model = models.efficientnet_b0(weights=weights)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, num_classes)
    return model


def set_stage(model: nn.Module, stage: int) -> list[nn.Parameter]:
    """Configure which parameters train, and return them for the optimiser.

    Stage 1 — everything frozen except the new head. The head starts from random weights;
    letting its large early gradients flow into a pretrained backbone is how you destroy
    the features you are trying to transfer.

    Stage 2 — additionally unfreeze the last two feature blocks. Those hold the most
    task-specific representations, so they are where adaptation to leaf texture pays off.
    Earlier blocks stay frozen: they encode edges and colour blobs, which leaves share with
    ImageNet, and unfreezing them on ~14k images mostly buys overfitting.
    """
    if stage not in (1, 2):
        raise ValueError(f"stage must be 1 or 2, got {stage}")

    for param in model.parameters():
        param.requires_grad = False
    for param in model.classifier.parameters():
        param.requires_grad = True

    if stage == 2:
        for block in list(model.features)[-2:]:
            for param in block.parameters():
                param.requires_grad = True

    return [p for p in model.parameters() if p.requires_grad]


class SmallCNN(nn.Module):
    """From-scratch baseline for A2's comparison slide.

    Deliberately a reasonable small CNN and not a strawman — four conv blocks with
    batchnorm, which is what somebody would actually write if they skipped transfer
    learning. The comparison is only worth showing if the baseline is honest.
    """

    def __init__(self, num_classes: int, in_channels: int = 3):
        super().__init__()

        def block(cin: int, cout: int) -> nn.Sequential:
            return nn.Sequential(
                nn.Conv2d(cin, cout, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(cout),
                nn.ReLU(inplace=True),
                nn.Conv2d(cout, cout, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(cout),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
            )

        self.features = nn.Sequential(
            block(in_channels, 32),  # 224 -> 112
            block(32, 64),  # 112 -> 56
            block(64, 128),  # 56 -> 28
            block(128, 256),  # 28 -> 14
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(0.3),
            nn.Linear(256, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.pool(self.features(x)))


def count_parameters(model: nn.Module) -> tuple[int, int]:
    """(total, trainable) parameter counts — printed at the top of every training run."""
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return total, trainable

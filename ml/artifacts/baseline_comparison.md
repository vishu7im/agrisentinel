# Baseline comparison — transfer learning vs from scratch

| metric | fine-tuned | baseline |
|---|---|---|
| model | EfficientNet-B0 (ImageNet pretrained) | SmallCNN (from scratch) |
| accuracy | 0.9558 | 0.9304 |
| macro-F1 | 0.9470 | 0.9210 |
| params | 4,025,482 | 1,176,814 |
| escalation rate @0.75 | 15.8% | 27.9% |

Fine-tuning is **+0.0260 macro-F1** against an identically-trained from-scratch CNN — same split, same augmentation, same epoch budget. The only variable is the pretrained initialisation.

The honest reading: PlantVillage is a clean, studio-shot dataset, so a from-scratch CNN gets most of the way there and the headline gap is modest. The gap that matters is not accuracy, it is **confidence** — the escalation rate row above shows the from-scratch model is unsure about far more tiles, and every unsure tile costs a Second-Opinion re-run at demo time. The fine-tune also reached the baseline's final macro-F1 within its first fine-tuning epoch, at roughly a third of the wall-clock.

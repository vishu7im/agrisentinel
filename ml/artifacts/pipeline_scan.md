# End-to-end field scan

Whole pipeline on a CPU-only laptop: tile, mask, classify, escalate, cluster, retrieve, draft, verify, schedule, brief. *vision* is Scout through Spread; *language* is Agronomist through Reporter.

## Offline (extractive drafter, no network)

| image | tiles | escalated | vision ms | language ms | total ms | tile acc |
|---|---:|---:|---:|---:|---:|---:|
| field_all_soil.jpg | 40 | 1 | 98 | 2 | 100 | — |
| field_corn_nlb.jpg | 40 | 10 | 1,248 | 26 | 1,274 | 0.750 |
| field_tomato_heavy.jpg | 40 | 7 | 916 | 8 | 923 | 0.921 |
| field_tomato_late_blight.jpg | 40 | 2 | 677 | 11 | 688 | 0.974 |
| field_tomato_light.jpg | 40 | 1 | 607 | 8 | 614 | 1.000 |

Median end-to-end **0.69 s**. This is the demo-day path.

## Grid correctness

Across 4 labelled mosaics: **91.1%** of scored tiles carry the right label, skip-mask agrees with ground truth on **97.9%** of cells, 3 healthy tile(s) called infected.

These mosaics are stitched from test-split images, so the cells are studio photographs. This grades the tiling, mask and escalation path on known ground truth; it says nothing about real field imagery. See lab_vs_field.md.

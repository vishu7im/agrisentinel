# Headline numbers

Every row is read from an artifact on disk, not recomputed here. Rebuild with `ml/report/generate.py`.

| metric | value | source |
|---|---|---|
| test accuracy | 95.6% | `metrics.json` |
| test macro-F1 | 0.9470 | `metrics.json` |
| classes / test images | 14 / 2,399 | `metrics.json` |
| escalated at 0.75 | 15.8% | `metrics.json` |
| vs from-scratch CNN | +0.0260 macro-F1 | `baseline_comparison.md` |
| simulated field accuracy | 86.6%  (-9.0%) | `lab_vs_field.md` |
| escalated, field conditions | 35.9% | `lab_vs_field.md` |
| real field photos | not collected | `demo/field_photos/` |
| per-tile inference | 6.5 ms CPU | `latency.md` |
| end-to-end scan, offline | 0.46 s | `latency.md` |
| tile accuracy on labelled mosaics | 91.1% | `pipeline_scan.md` |
| adversarial attacks landed | 2 of 10 | `block_rate.md` |
| caught by the Verifier | 2 blocked/stripped | `block_rate.md` |
| leaked to the farmer | 0 | `block_rate.md` |

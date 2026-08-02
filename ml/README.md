# `/ml` — dataset, training, export

Owned by Dev A. Everything here is offline work: it produces `ml/artifacts/model.onnx`, and
from that point on nothing in the running system imports torch.

## Setup

```bash
.venv/bin/pip install -r ml/requirements.txt   # ~3 GB, includes CUDA
```

Torch is deliberately **not** in `backend/requirements.txt`. The backend only ever needs
`onnxruntime`, and a demo laptop should not have to carry a training stack.

## Phase A1 — data

```bash
.venv/bin/python ml/data/download.py    # ~500 MB, sparse clone of PlantVillage
.venv/bin/python ml/data/prepare.py     # cap + stratified 70/15/15 split
.venv/bin/python ml/data/inspect.py     # count table + augmented sample grid
```

`ml/data/raw/` and `ml/data/processed/` are gitignored; the processed tree is hardlinks into
raw, so it costs no extra disk. Both are reproducible from `download.py` in about ten
minutes, so nothing about them needs committing.

## Phase A2 — model

```bash
.venv/bin/python ml/train.py            # 3 epochs frozen + 5 epochs fine-tune
.venv/bin/python ml/eval.py             # test metrics + confusion matrix
.venv/bin/python ml/baseline.py         # from-scratch CNN, for the comparison slide
.venv/bin/python ml/export_onnx.py      # ONNX + parity check + CPU latency
```

Every script takes `--device cpu` if there is no GPU, and `--help` lists the rest.

## Results as of A2

| | fine-tuned | from-scratch baseline |
|---|---|---|
| test accuracy | **0.9558** | 0.9304 |
| test macro-F1 | **0.9470** | 0.9210 |
| tiles below 0.75 confidence | **15.8%** | 27.9% |
| training wall-clock | 7.2 min | 20.7 min |

16,031 images over 14 classes, 70/15/15 stratified, seed 42, RTX 3050.

Two numbers worth carrying into A5. **15.8% of test tiles land below the 0.75 confidence
gate**, so the Second-Opinion escalation path genuinely fires rather than being decorative.
And the gate separates cleanly: accuracy is 0.993 above it and 0.758 below it, which is the
evidence that 0.75 is the right threshold rather than a number someone liked.

Weakest class is `corn__gray_leaf_spot` (F1 0.844), which loses 18% of its images to
`corn__northern_leaf_blight`. Those two are a genuinely hard pair on real corn and the
confusion is one-directional, so it is worth a sentence to judges rather than an apology.

CPU inference is **4.9 ms/tile**, so a 40-tile field scan is ~0.2 s of model time.

## The class registry

`ml/data/classes.py` is the single source of truth for which 14 PlantVillage classes are in
scope and — importantly — for `tile_label`, the snake_case slug that lands in
`tiles[].label` in `contract/run_state.schema.json`. Change a slug there and Dev B's heatmap
legend changes with it, so that field is effectively contract-adjacent. Talk before editing.

Model class order is `sorted(key)`, which is also the order `torchvision.ImageFolder`
assigns. `ml/datasets.py` asserts the two match on every run; if that assert ever fires, the
model is mislabelling every prediction while still looking accurate. Do not skip past it.

## Artifacts

`ml/artifacts/` is committed on purpose — the charts go on the judging slides and the ONNX
file is what makes the demo run without a GPU.

| file | from | used by |
|---|---|---|
| `augmented_samples.png` | `data/inspect.py` | slides |
| `train_log.csv` | `train.py` | slides |
| `metrics.json`, `per_class_table.md`, `confusion_matrix.png` | `eval.py` | slides, A9 |
| `metrics_baseline.json`, `baseline_comparison.md` | `baseline.py` | slides |
| `model.onnx`, `model_classes.json` | `export_onnx.py` | **A3 Diagnostician** |
| `confusion_matrix_baseline.png`, `per_class_table_baseline.md` | `eval.py --tag baseline` | slides |
| `latency.json` | `export_onnx.py` | `report/generate.py` |
| `latency.md` | `report/generate.py` | slides |
| `lab_vs_field.png/.md/.json` | `report/field_gap.py` | slides |
| `pipeline_scan.md/.json` | `report/pipeline_run.py` | slides |
| `block_rate.md/.json` | `report/verifier_eval.py` | slides |
| `SUMMARY.md` | `report/generate.py` | slides |

Checkpoints (`ml/checkpoints/*.pt`) are gitignored — they are 20 MB of torch-specific state
that only `export_onnx.py` reads, and the ONNX file is the real deliverable.

## Phase A9 — the metrics pack

```bash
.venv/bin/python ml/report/generate.py        # the whole pack, then the headline table
.venv/bin/python ml/report/generate.py --only summary   # re-read what is on disk, recompute nothing
.venv/bin/python ml/report/verifier_eval.py --both      # the adversarial suite, run separately
```

One rule holds the pack together: **`generate.py` computes nothing.** Every number is produced
by the script that owns the measurement and written to disk; `generate.py` runs those scripts,
reads what they wrote, and lays it out. So "where did that number come from" always has a
one-word answer, and `SUMMARY.md` cannot drift from the artifacts it summarises.

The adversarial suite is deliberately not part of the pack build. It fails for reasons that
have nothing to do with the model — a spent API quota, most likely — and a red number should
not scroll past inside a longer build.

Read `NOTES.md` at the repo root before quoting any of it. In particular the lab-to-field
chart's third bar is empty: no real field photographs have been collected, so the only field
number here is simulated and is a floor, not the gap.

## Note for A3 — preprocessing must be reimplemented, not imported

`agents/diagnostician.py` cannot call `build_eval_transform`: that needs torchvision, and
the backend deliberately has no torch. The four steps have to be redone in PIL and numpy,
and `model_classes.json` carries the exact arithmetic for that.

Two details in there are not cosmetic. The resize **truncates** the long side, and the
centre crop offset **rounds** rather than floors. Getting the crop wrong shifts every tile
one pixel and quietly costs accuracy with no error anywhere. A pure PIL+numpy
implementation following that spec was checked bit-identical to torchvision across 280 test
images, with 280/280 identical ONNX predictions — reproduce that check in A3 before
trusting new preprocessing code.

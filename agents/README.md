# `/agents` — the multi-agent pipeline

Owned by Dev A. Everything downstream of `ml/artifacts/model.onnx`.

**Agents never call each other.** Each one takes the shared `RunState`, reads what it needs,
writes what it produced, and appends to `events[]`. The orchestrator (A5) is the only thing
that knows the running order, which is why a new agent can be slotted in without touching the
others — and why the event log on Dev B's screen is a true picture of what ran, not a
narration written next to it.

**Nothing here imports torch.** Inference is ONNX Runtime on CPU. See `preprocess.py`.

## Phase A3 — Scout and Diagnostician

```bash
.venv/bin/python agents/run.py agents/testdata/field_tomato_late_blight.jpg
.venv/bin/python agents/run.py <image> --json | .venv/bin/python contract/validate.py -
```

*(As of A5 `run.py` runs the whole pipeline through `orchestrator.run_pipeline`, so these
commands also exercise the confidence gate and the Second-Opinion agent.)*

| file | what it is |
|---|---|
| `state.py` | `RunState` + `Tile`. The schema shape lives here and nowhere else. |
| `tiling.py` | Grid geometry. Not an agent — arithmetic both agents need identically. |
| `preprocess.py` | The eval transform in PIL/numpy, byte-exact against torchvision. |
| `scout.py` | **Scout Agent** — grid layout and the soil/sky skip mask. |
| `diagnostician.py` | **Diagnostician Agent** — batched ONNX inference per tile. |
| `second_opinion.py` | **Second-Opinion Agent** — 4-view TTA on tiles under the gate. |
| `spread.py` | **Spread Analyst Agent** — severity, clusters, direction, yield loss. |
| `severity_weights.json` | The yield-loss weights, with the caveats spelled out. |
| `orchestrator.py` | **The running order.** The only file that knows it. |
| `run.py` | CLI over `run_pipeline` — the same call the backend makes. |
| `verify_preprocess.py` | Dev tool. The only file allowed to import torchvision. |

### Results on the synthetic fixtures

| fixture | grid | tiles exact | false skips | false keeps | errors caught by the 0.75 gate |
|---|---|---|---|---|---|
| `field_tomato_light` | 8×5 | 40/40 | 0 | 0 | — |
| `field_tomato_late_blight` | 8×5 | 39/40 | 0 | 0 | 1/1 |
| `field_tomato_heavy` | 8×5 | 37/40 | 0 | 0 | 2/3 |
| `field_corn_nlb` | 6×4 | 24/24 | 0 | 0 | — |
| `field_all_soil` | 2×2 | 4/4 | 0 | 0 | — |
| **total** | | **144/148** | **0** | **0** | **3/4** |

Of the four misses, three land under the 0.75 gate and go to A5's Second-Opinion. The fourth
does not, and it is the one worth naming: `t_03_01` on the heavy fixture, a late-blight tile
called `healthy` at 0.89. Confidence gating cannot catch a confident false negative — only a
better model or a second view can — so it is the honest ceiling on what escalation buys.

A 38-tile scan is **~300 ms**: 28 ms of Scout, 273 ms of decode + preprocess + inference, and
under 2 ms of Spread. That is roughly 7 ms per tile against the 4.9 ms in
`ml/artifacts/latency.md`; the difference is JPEG decode and resize, which the model-only
number does not include and A9 should. The Spread Analyst's first call in a process looks
like 20–50 ms — that is scikit-learn's lazy import, paid once, and A5 pays it at startup.

Regenerate the fixtures with:

```bash
.venv/bin/python ml/data/make_field.py --crop tomato --disease late_blight
.venv/bin/python ml/data/make_field.py --infected "6,0 6,1" --seed 7 \
  --out agents/testdata/field_tomato_light.jpg
.venv/bin/python ml/data/make_field.py --seed 11 \
  --infected "0,0 1,0 2,0 6,0 7,0 0,1 1,1 2,1 3,1 0,2 1,2 2,2 3,2 0,3 1,3 2,3 3,3 1,4 2,4 3,4" \
  --out agents/testdata/field_tomato_heavy.jpg
```

They are stitched from the held-out test split, so a `.truth.txt` sits next to each one and
every cell has a known answer. **They are a harness for tiling, skipping and batching — not a
lab-to-field test.** The tiles are still studio photographs of detached leaves. Measuring the
real gap needs `demo/field_photos/`, and that is A9's job.

## Phase A4 — Spread Analyst

Reads `state.tiles` and nothing else — no image, no model — so it runs in about a
millisecond and can be replayed against a stored run state without the original photo.

Fed the 40 tiles from `contract/mock_run.json`, it reproduces that file's `spread` object
exactly, cluster centroids and ordering included. The frozen reference run and the real agent
agree, which is the strongest check available before A5 puts this behind an API.

### Against ground truth

Every fixture, pipeline output versus the same agent fed the true labels:

| fixture | pct_affected | clusters | direction | est_yield_loss_pct |
|---|---|---|---|---|
| `field_tomato_light` | 5.3 / **5.3** | 1 / **1** | NE / **NE** | 3.2 / **3.2** |
| `field_tomato_late_blight` | 18.4 / **18.4** | 3 / **3** | NE / **NE** | 10.4 / **11.2** |
| `field_tomato_heavy` | 50.0 / **52.6** | 2 / **2** | W / **W** | 29.0 / **32.1** |
| `field_corn_nlb` | 25.0 / **25.0** | 2 / **2** | NE / **NE** | 7.5 / **7.5** |
| `field_all_soil` | 0.0 / **0.0** | 0 / **0** | null / **null** | 0.0 / **0.0** |

*(pipeline / truth. Bold is the truth column.)*

Cluster count and direction are exact on all five. `pct_affected` is exact on four; the heavy
fixture misses one infected tile out of twenty. The yield gaps are downstream of label
errors, not of the yield model: one late-blight tile called `bacterial_spot` drags the
tile-weighted mean from 0.61 toward 0.30, which is the mixed-disease weighting behaving
correctly on a wrong input.

### Edge cases that no fixture reaches

| input | result |
|---|---|
| nothing infected | 0%, 0 clusters, direction null, `spread.clean_field` |
| 5 isolated infected tiles | 12.5%, **0 clusters**, `spread.scattered.5_tiles` |
| 2 blobs plus 2 strays | 17.5%, 2 clusters, `spread.scattered.2_tiles` |
| whole field infected | 100%, 1 cluster, direction null, `spread.direction.uniform` |
| whole frame skipped | zeroes, `spread.no_field` |
| unknown crop | default weight, `spread.weight_default.1_labels` |

All eight compass points verified against hand-computed bearings, plus the two null cases.

**A lone infected tile is noise, not a cluster.** DBSCAN with `min_samples=2` says so and that
is the right call: one isolated tile is as likely to be a misclassification as a real focus,
and a farmer would walk out to check it. It is never silently dropped — it still counts in
`pct_affected`, and `spread.scattered.<n>_tiles` puts it on Dev B's timeline.

## Phase A5 — Orchestrator and Second-Opinion

`orchestrator.run_pipeline` is the only function that knows the running order, and both the
CLI and the backend call it. That is deliberate: the moment `run.py` sequences the agents
itself, a phase can pass on the command line and fail through the API, and the difference
shows up at M1 with Dev B watching.

```
Scout -> Diagnostician -> [confidence gate] -> Second-Opinion -> Spread -> run.complete
```

### Does escalation actually do anything?

Nothing in `ml/artifacts/` measured TTA, so A5 measured it — on the full 2,399-image held-out
split, comparing single-view against the 4-view average **on the sub-population the 0.75 gate
selects**, because that is the only population the agent ever sees:

| | single view | 4-view TTA |
|---|---|---|
| escalated subset (n=379, 15.8%) | 75.73% | **78.36%** |
| — of which | | 32 fixed, 22 broken, **net +10** |
| confident subset (n=2,020) | 99.31% | 99.31% |
| whole split | 95.58% | **96.00%** |

Two things there matter more than the headline. TTA **breaks 22 tiles it previously got
right** — the gain is +10 net, not +32, and "a second opinion only ever helps" is false. And
on the confident 84% accuracy does not move at all, to two decimals: that is the empirical
case for gating rather than running TTA on everything, which would quadruple inference to
move a number that does not move.

On the five fixtures escalation is net zero (1 fixed, 1 broken across 13 escalated tiles).
That neither confirms nor contradicts the split result — 13 tiles can only resolve an effect
of about a third of a tile. The split is the measurement with power; the fixtures confirm
nothing regressed.

TTA also *raised* mean confidence on those tiles, 0.582 to 0.611, lifting 65 of 379 clear of
the gate. That is the opposite of what smoothing usually does and the opposite of what the
first draft of `second_opinion.py` claimed — the four views mostly agree, and agreement
concentrates the mean instead of flattening it.

### The bare-soil bug, which is the one worth reading

Running the all-soil fixture through the API at the default 8×5 grid produced:

```json
{ "pct_affected": 100.0, "est_yield_loss_pct": 70.0 }
```

A photograph of dirt, reporting that the field is completely lost. One tile out of 40 escaped
the Scout's mask — vegetation 0.0000, uniformity 0.0227 against a 0.022 threshold — and the
model labelled it `yellow_leaf_curl_virus` at 0.10 confidence. One infected tile over one
scored tile is 100%.

Every individual component behaved as designed. The Scout's false keep is the failure
direction A3 deliberately chose. The gate caught the tile and escalated it; TTA correctly
failed to rescue it, because the model has no idea what dirt is. **The bug was in the
argument, not the code:** A3 called a false keep harmless because it costs one low-confidence
prediction, and that was true of every consumer that existed at the time. A ratio is not such
a consumer. A single bad tile in a denominator of one becomes a headline.

`spread.py` now refuses to report below `MIN_SCORED_TILES` (3), emitting
`spread.insufficient_field.<n>_tiles` with zeroes, and flags a thin-but-usable sample with
`spread.thin_sample.<n>_tiles` below a quarter of the grid rather than suppressing it. Bare
soil now returns 0%, and the four real fixtures are unchanged.

The general lesson, which will apply again in A6-A8: an error budget assigned to one component
is only valid against the consumers that existed when it was written.

### Latency through the API

A 40-tile scan, POST to `run.complete`, is **~560 ms** on this CPU: 54 ms Scout, 305 ms
diagnosis, 154 ms Second-Opinion on 7 tiles, under 2 ms Spread. Events reach the SSE client
progressively at the 50 ms poll granularity — the heatmap fills in during the run rather than
appearing at the end.

## Two decisions you will want the reasoning for

**The skip mask needs two tests, not one.** Skipping is asymmetric: a false keep costs one
low-confidence prediction that A5 escalates anyway, while a false skip silently deletes a
diagnosis — and the tiles most at risk are the severely diseased ones, because dead foliage
is brown. A plain Excess Green threshold dropped a fully necrotic corn tile scoring 0.001
vegetation, indistinguishable from soil. So a tile is skipped only when it has no vegetation
**and** looks like a single uniform surface; a dead leaf is still a leaf against a different
background, so its colour spread stays high (0.032) where soil sits at 0.014.

`UNIFORMITY_MAX` is calibrated against synthetic soil, which is more uniform than the real
thing. Real soil drifts *up* past the threshold, so the error it trends toward is a false
keep — the harmless direction. Re-measure on real photos in A9 before quoting a number.

**Predictions are restricted to the run's crop, but confidence is not.** The model spans 14
classes across three crops; a field is one crop and `POST /api/run` says which. Unrestricted,
a stray tile comes back `corn__common_rust` in a tomato field and that flows into A4's
severity weights and A6's retrieval as if real. The confidence stays the unrestricted 14-way
softmax, because that is the quantity `ml/eval.py` measured the 0.75 gate against — reporting
a renormalised number would make the threshold describe something else.

The visible payoff: declare the wrong crop and every tile lands under 0.05 confidence instead
of returning confident nonsense. Try it —
`agents/run.py agents/testdata/field_tomato_late_blight.jpg --crop corn`.

## What A5 leaves null

`plan_draft`, `verification`, `schedule`, `cost_estimate`, `rescan_date` and `report` are all
null. `status` is `complete` and `finished_at` is set, because the contract says the SSE
stream closes on `run.complete` or `run.error` and nothing else — a run that ends without
emitting one leaves the browser holding an open connection and a spinner. So `complete` here
means "the pipeline finished as far as it currently goes", with the schema's nullable fields
carrying the difference. A6-A8 insert stages ahead of the completion in `orchestrator.py` and
nothing outside that file changes.

`run.py` validates the state against the schema before printing it, so a shape regression
fails loudly here rather than quietly in Dev B's browser.

## One thing A6 should know

scikit-learn is now pinned in `backend/requirements.txt` for one DBSCAN call on a few dozen
integer points, and it carries scipy with it. If backend install weight turns out to matter,
the equivalent is connected components over the 8-neighbourhood and about fifteen lines. Not
worth doing speculatively — worth knowing the exit exists, especially before A6 adds a vector
database on top.

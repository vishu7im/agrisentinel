# Latency

## Per tile — ONNX Runtime, CPU

CPUExecutionProvider, batch 1, 224x224, 50 runs after warm-up.

| metric | ms |
|---|---:|
| mean | 6.5 |
| median | 6.5 |
| p95 | 8.0 |
| min | 4.9 |
| max | 9.6 |

Parity with PyTorch: 10/10 argmax agree, max |logit diff| 9.54e-06.

## Per scan — the whole pipeline, measured

| path | median end-to-end | vision | language |
|---|---:|---:|---:|
| offline (extractive drafter) | 0.46 s | 0.46 s | 0.00 s |

40 tiles x the per-tile mean predicts 0.26 s of inference; the measured offline run is **0.46 s**. The difference is everything inference is not — decode, tile, green-mask, batch, the second pass over escalated tiles, DBSCAN, retrieval. Quote the measured number.

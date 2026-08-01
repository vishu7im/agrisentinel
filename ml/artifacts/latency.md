# CPU inference latency

ONNX Runtime, CPUExecutionProvider, batch 1, 224x224, 50 runs after warm-up.

| metric | ms |
|---|---:|
| mean | 4.9 |
| median | 4.8 |
| p95 | 5.8 |
| min | 4.0 |
| max | 6.2 |

A 40-tile field scan is **0.2 s** of inference single-threaded, before batching.

PyTorch/ONNX parity: 10/10 argmax agree, max |logit diff| 9.54e-06.

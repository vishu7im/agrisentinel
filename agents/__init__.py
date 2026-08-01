"""AgriSentinel agents.

Agents never call each other. Each one takes a RunState, reads what it needs, writes what
it produced, and appends to events[]. The orchestrator (A5) is the only thing that knows
the running order, which is why a new agent can be slotted in without touching the others.

Nothing in here may import torch. Inference is ONNX Runtime on CPU — see
agents/preprocess.py for why that constrains how tiles are prepared.
"""

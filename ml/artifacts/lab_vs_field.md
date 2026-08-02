# Lab to field

| condition | n | accuracy | macro-F1 | mean conf | escalated @0.75 |
|---|---:|---:|---:|---:|---:|
| test split, clean | 2,399 | 0.9558 | 0.9470 | 0.885 | 15.8% |
| simulated: mild | 2,399 | 0.9279 | 0.9189 | 0.857 | 21.9% |
| simulated: field | 2,399 | 0.8662 | 0.8483 | 0.782 | 35.9% |

Simulated field conditions cost **9.0 accuracy points** against the clean test split, and push the escalation rate from 15.8% to 35.9% — the Second-Opinion agent exists for exactly that second number.

No real field photographs have been collected, so the third bar is empty. The simulated number is a **lower bound on the gap**: it degrades image quality and leaves image content alone — one leaf, centred, nothing else in frame. Overlapping plants, soil, shadow and oblique angles are not simulated and are most of what makes a field photo hard. Treat the drop above as the floor.

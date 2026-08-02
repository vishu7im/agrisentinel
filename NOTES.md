# NOTES — Dev A (ML, agents, backend)

Written at the end of A9. What the numbers mean, what broke on the way to them, and what I
would not want a judge to discover before I said it.

Every figure below is in `ml/artifacts/`, produced by the script named beside it in
`ml/artifacts/SUMMARY.md`. Rebuild the whole pack with `ml/report/generate.py`; the adversarial
suite is separate, on purpose, because a red number there should not scroll past inside a
larger build.

## The headline, with the caveat attached

| | |
|---|---|
| test accuracy / macro-F1 | 95.6% / 0.947 on 2,399 held-out PlantVillage images, 14 classes |
| simulated field conditions | **86.6%** — blur, JPEG, harsh light, rotation, downscale |
| real field photographs | **not collected** |
| end-to-end scan, offline | 0.46 s median on CPU, whole pipeline |
| adversarial attacks landed / caught / leaked | 2 / 2 / 0 (extractive drafter only) |

The gap between the first two rows is the honest content of this project. A model that scores
95.6% on studio photographs of detached leaves and 86.6% once the image looks like a phone
photo is a model with a nine-point problem, and the simulated number is a **floor**: it damages
image quality and leaves image content alone. One leaf, centred, nothing else in frame. The
real gap also contains overlapping plants, soil, hands, shadow, oblique angles and disease
stages the dataset never photographed, and no transform produces those.

`demo/field_photos/` is empty, so the third bar of `lab_vs_field.png` is drawn as an empty
slot rather than omitted. That is the single most valuable missing measurement in the repo and
it costs an afternoon with a phone. Thirty labelled photos would either confirm the system or
end the argument.

## What broke

Roughly in the order it hurt.

- **`ml/data/inspect.py` shadowed the stdlib `inspect` module**, which torch and PIL both
  import. Any script that put `ml/data/` on `sys.path` died somewhere deep inside torchvision
  with an error naming neither file. `ml/data/__init__.py` and `make_field.py` carry the note.
- **A picture of bare soil produced a full treatment plan.** One tile survived the Scout's
  green mask, got labelled at 0.10 confidence, and the Agronomist drafted for it — cited,
  fluent, and about a disease in a photograph of dirt. The Spread Analyst had already declined
  to measure that field and reported 0% affected; the fix was making the Agronomist obey that
  rather than re-derive severity from tiles. An honest "I could not measure this" is only worth
  something if the next stage reads it. The same fixture (`field_all_soil.jpg`) still escalates
  one tile today and still produces no plan.
- **Cosine similarity cannot tell a true sentence from a convincing one.** Scoring plan
  sentences against their cited chunks, an invented chemical at an invented dose scored 0.297
  against a passage that never mentions it — higher than a true sentence scored against its
  real source. It measures register, not truth. Grounding is a containment test now, and the
  numbers are in `agents/claims.py` because they are the argument for the design.
- **The extractive drafter picked the wrong sentence for corn** — the economics of spraying
  maize rather than the sentence naming propiconazole and its dose — and everything downstream
  degraded politely: no product to schedule, no dose to cost, and a farmer brief that read
  "Today, follow plan guidance. Then, follow plan guidance."
- **Every upload was scanned as tomato.** `crop` defaults to `tomato` in the form field, in
  `new_run()` and in the frontend's own `startRun(image, crop = 'tomato')`, and no crop picker
  was ever built — so the default was not a default, it was the only value the system ever saw.
  The Diagnostician masks its logits to the declared crop, which made it unrecoverable rather
  than merely wrong: a corn field came back as tomato diseases at near-zero confidence,
  reporting 94.4% infected and ~49.9% yield at risk against a true 30.6% and 9.2%. The signal
  was sitting in plain view — 36 of 36 tiles below the confidence gate — and nothing read it.
  Worth remembering as a class of bug: a default that nothing ever overrides is not a default,
  and masking turned a soft error into a confident one.
- **The first fix for that was itself wrong, and only real photographs showed it.** A probe pass
  that votes on the crop from unmasked probabilities scores 0.91-0.99 on the synthetic mosaics
  and looked finished. On four photographs downloaded from Wikimedia Commons it got **all four
  wrong**: a corn field split tomato 0.502 / corn 0.483, corn rust read tomato, a potato leaf
  read corn, and a tomato plant read corn at 0.754 — above the override threshold, so the
  "fix" would have relabelled a correctly-declared tomato field as corn. The vote now decides
  only when the caller sent `auto`, an explicit crop is always obeyed, and the UI has a crop
  picker. Two lessons: the lab-to-field gap is not confined to disease labels, it degrades
  every inference the system makes; and thirty minutes of real images falsified a mechanism
  that four synthetic fixtures had unanimously endorsed.
- **Today, in A9: the first adversarial run scored 10/10 neutralised**, which looked like a
  result and was an artifact. Payloads were appended to the poisoned chunk, and the extractive
  drafter breaks ties toward the earlier sentence, so no payload was ever selected. Moving the
  poison to the lead sentence — which is what an attacker editing a document would write —
  made two of them land immediately.
- **Today, in A9: the "online" adversarial run silently produced offline results.** The Gemini
  key is over quota (HTTP 429), the Agronomist falls back to the extractive drafter by design,
  the run succeeds, and the report cheerfully labelled ten extractive results as LLM ones.
  `verifier_eval.py` now probes the provider before it claims to have tested it.

## What is measured and what is not

Measured: test-split accuracy per class, confusion matrix, from-scratch baseline, confidence
distribution and escalation rate, ONNX/PyTorch parity, per-tile CPU latency, real end-to-end
scan latency with a per-stage breakdown, tile-level accuracy on five labelled mosaics, and ten
adversarial attacks against the extractive drafter.

Not measured, and each one is a real hole:

1. **Real field photographs.** Nothing in this repo has been *evaluated* on one. Seven were
   pushed through the pipeline by hand while chasing the crop bug, and the result is the most
   alarming number I have: a healthy potato field photograph came back **69.2% affected** and a
   healthy maize field **56.7% affected**, both with a confident disease name and a spray
   schedule attached. A tomato septoria photo was called yellow leaf curl virus at 97.5%. Seven
   images with no ground-truth labels is an anecdote, not a measurement — but it is the same
   anecdote seven times, and it points one way. The Verifier cannot help here: the plan is
   correctly grounded advice for a disease the field does not have. **This is the thing to fix
   before anything else on this list.**
2. **The prompt-injection half of the adversarial suite.** Five of the ten attacks target a
   model's willingness to follow instructions hidden in a passage. The extractive drafter has
   no such willingness — it copies sentences — so those five have never met the drafter they
   were written for. Re-run `verifier_eval.py --both` on a working key before quoting a rate.
3. **Anything about a crop that is not tomato, potato or corn**, or a disease outside the
   fourteen classes. The Agronomist refuses those, which is correct, and untested at scale.

## The four things I would fix first

1. **Collect the photographs.** Everything else on this list is a guess until that bar is
   filled in.
2. **The confidence gate is calibrated against clean data.** Escalation runs at 15.8% on the
   test split and **35.9%** under simulated field conditions — the Second-Opinion agent does
   more than twice the work exactly when the model is least reliable, and 0.75 was chosen
   against the clean distribution. On a real field photo the gate may be firing on most of the
   grid, which is both slow and a sign the threshold is wrong.
3. **Corn is the weak crop.** Gray leaf spot has the lowest per-class F1 (0.844), and the corn
   mosaic scores 0.75 tile accuracy with 0.60 recall on infected tiles and three healthy tiles
   called infected — against 0.97–1.00 on the tomato mosaics. Northern leaf blight and gray
   leaf spot are genuinely hard to separate, and the class counts are the smallest in the set.
   If the demo image is corn, this is what goes wrong on stage.
4. **Corpus poisoning has no verification answer, and the report should keep saying so.** A
   false sentence written into a retrieved passage is *grounded in it by definition* —
   containment scores it 1.000 and the check designed to catch invention certifies it. Only the
   allowlist and the dose table can contradict the corpus, and they only recognise things
   shaped like a pesticide name or a dose. "Add one cup of household bleach to the spray"
   satisfies every check this system owns. The fix is upstream: the corpus is trusted input and
   should be treated as a reviewed artifact, not a folder.

## Two smaller things worth knowing

- **Per-tile latency times tile count underestimates a scan.** 40 tiles at the 6.5 ms mean
  predicts 0.26 s; the measured pipeline is 0.46 s, and the difference is decode,
  tiling, the green mask, batching, the second pass over escalated tiles, DBSCAN and retrieval.
  `latency.md` now carries both, because quoted apart they mislead in opposite directions.
- **The offline path is the demo path.** With no key the plan is composed from sentences lifted
  out of the retrieved passages, so every citation is literally where the text came from. It is
  less fluent than the LLM draft and it is not a degraded mode in the way that matters: it
  cannot fabricate, and it runs in under half a second with no network. At a venue with bad wifi that is the
  normal case, not the sad path.

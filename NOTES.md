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
| spray plans for fields that did not need one | **7/7 → 4/7** after A10's vision cross-check |
| crop identified correctly | 3/5 → **5/5** after A11 stopped discarding the vision crop |

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
   correctly grounded advice for a disease the field does not have.

   **A10 addressed this and did not close it.** The Observer asks a vision model the same
   question independently, and the Consensus agent refuses when the two answers are
   categorically different. `ml/artifacts/vision_crosscheck.md` has the before and after: spray
   plans for fields that did not need one went **7/7 → 4/7**, and all three withheld runs are
   ones that should be withheld — the two healthy fields, plus a *botanical illustration* the
   classifier had called 92% affected. The genuinely diseased maize field kept its plan, which
   is the non-regression that matters. Crop identification went 3/5 → 4/5.

   What has not changed is the classifier. Nothing in A10 made it better at reading a real
   photograph; a second opinion was bolted alongside it that is wrong in different places, and
   the system now declines where the two disagree. That is a real improvement in what reaches a
   farmer and it is not a fix for the underlying gap — and the three runs that still shipped a
   plan did so because the API was rate-limited, which is the other honest number here: **the
   cross-check was unavailable on 3 of 7 attempts.** Thirty labelled photographs are still the
   most valuable afternoon anyone could spend on this repo.
2. **The prompt-injection half of the adversarial suite.** Five of the ten attacks target a
   model's willingness to follow instructions hidden in a passage. The extractive drafter has
   no such willingness — it copies sentences — so those five have never met the drafter they
   were written for. Re-run `verifier_eval.py --both` on a working key before quoting a rate.
3. **Anything about a crop that is not tomato, potato or corn**, or a disease outside the
   fourteen classes. The Agronomist refuses those, which is correct, and untested at scale.

## What A10 broke on the way, and what it taught

- **The first `is_crop_field` gate would have refused three of our own demo fixtures.** Shown
  `field_tomato_heavy.jpg` the vision model answered "not a crop field — a grid of forty
  individual leaves against plain backgrounds", which is exactly what that fixture is. It was
  right, and acting on it alone would have blocked every mosaic and every laboratory photograph.
  The fix is that a refusal now needs two signals: the vision model saying "not a field" *and*
  the Scout's green mask saying there is no plant tissue (0.00 on bare soil, 0.62-1.00 on
  everything else). A mosaic of leaves is not a field and is still perfectly diagnosable.
- **Keying "healthy" on the class name would have missed the maize case.** Shown a healthy maize
  field the model answered `class_key: unknown` — honestly, the plants were too young to
  identify — but `pct_affected: 0`. "I cannot tell you what this crop is, but nothing is wrong
  with it" contradicts a 56.7%-infected reading exactly as strongly as a named healthy class.
  The check reads the percentage, not the label, and that was found by running it, not by
  thinking about it.
- **A JSON schema with `"type": "number"` cost an entire response.** Asked for `pct_affected` as
  a number, the model emitted `0.000000000…` until it hit MAX_TOKENS and the whole reply was
  lost. Integers cannot do that. Two of the first seven probe responses died this way.
- **`thinkingBudget` is per-model, and an unsupported value is a hard 400** — not an ignored
  field. `gemini-flash-latest` rejects the budget that `gemini-2.5-flash` requires. Since the
  model is configurable, no table of which-model-takes-what stays true, so the transport retries
  once without the knob.
- **The first timeout was set by guessing and it lost every call.** 10 s, against a call that
  measured 12.0, 12.2, 12.5 and 12.9 seconds — so all five fixtures timed out while the model
  was still answering: the full wait and none of the benefit. Measuring it first would have
  taken two minutes.
- **Twelve seconds of dead air is its own bug.** Inline, the vision call blocked the entire run
  before a single tile appeared. It now starts after the Scout and is collected before the
  Consensus agent, so with an explicitly chosen crop most of the pipeline hides behind it
  (6.55 s against a 6 s stand-in call, versus 7.00 s on `auto`, where the crop must be settled
  before the Diagnostician masks its logits).

## What A11 found, which was mostly A10's own mistakes

- **One `or` cost four stages of the pipeline.** `_adopt_crop` refused to adopt the vision
  model's crop unless `is_crop_field` was true. Shown a photograph of one detached tomato leaf
  the model answered `crop: tomato` at 90% confidence with `is_crop_field: false` — correctly,
  a leaf on a bench is not a field — and the crop was thrown away for it. The probe vote then
  said corn, the Diagnostician masked its logits to corn, the classifier returned northern leaf
  blight, and the Consensus agent dropped the vision model's correct `tomato__late_blight` as
  belonging to the wrong crop. The brief read *"Your corn field has northern leaf blight."*
  A10's own Consensus agent had already worked out the right rule for exactly this photograph
  and written the argument down; the Observer was never told. **A constant that encodes a policy
  should live with the policy** — `SCOUT_TISSUE_MIN` and `tissue_share` are in `scout.py` now,
  where the measurement is made, and both readers import them.
- **Making the LLM reachable again made the plan worse.** The quota fall-through added in A11
  meant the Agronomist could draft for the first time in days — and the model it reached
  returned eleven fluent, correct, entirely unmarked sentences, three drafts running, repair
  pass included. The Verifier did its job and stripped all eleven, and the run finished
  `status: complete` with no plan, no schedule and no brief: strictly worse than the extractive
  draft the same run produces offline. `agronomist.llm_uncited` now falls back when *nothing* in
  a draft is citable, which is a different condition from a draft with two bad lines in it.
- **`"2.5" in model` was a bug waiting for a rate limit.** Thinking was disabled by testing the
  model id for a substring. The moment the fall-through reached a 3.x model, the budget went on
  thinking and answers arrived cut mid-clause. Defaulting thinking to off makes it a property of
  the task rather than of which quota bucket still had room.
- **The Advisor cites what the evidence says, not what the model claims.** A marker the model
  writes is an assertion about provenance; containment against the retrieved chunk is a
  measurement of it. The first live answer was a near-verbatim quotation with no marker at all —
  fully checkable, and it would have been discarded for a formatting slip. Computing the
  citation is strictly stronger than believing one.
- **No lexical threshold separates an in-corpus question from an out-of-corpus one.** Measured
  over 12 in-domain and 9 out-of-domain questions: retrieval scores overlap (0.134–0.310 against
  0.140–0.198) and so does question containment (0.000–1.000 against 0.000–0.333). "How does
  this spread?" repeats no word of the passage that answers it; "What is the price of tomatoes
  in Delhi?" scores 0.333 because the corpus is full of the word tomato. So there is no floor in
  `advisor.py` — the model reads the passages and answers `INSUFFICIENT_CONTEXT`, and the
  grounding check is the net under it. `retrieve.py` had already reached this conclusion once.
- **My own regression check was not testing what I thought.** `unset GEMINI_API_KEY` does not
  produce an offline run: `llm.setting` falls through to `.env`, so five "offline" baselines were
  captured with a live, rate-limited key. The genuinely keyless comparison had to patch
  `settings.dotenv` — and it does pass, with every field outside `events[]` identical.

## The four things I would fix first

1. **Collect the photographs.** Everything else on this list is a guess until that bar is
   filled in — including A10's and A11's, which rest on the same seven images. The 5/5 crop
   figure is five photographs. It is the right direction and it is not a measurement.
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
- **A fifth endpoint is owed to Dev B.** `POST /api/run/{id}/chat` ships under the same "also
  served, not part of the frozen four" heading `GET /api/run/{id}/image` already sits under.
  `run_state.schema.json` and `mock_run.json` are untouched, nothing is written back to a run,
  and a client that does not know the path exists behaves identically. It is still a
  conversation to have, and `contract/endpoints.md` should be the place it lands — along with
  the older correction that `crop` defaults to `auto`, not `tomato`.
- **The offline path is the demo path.** With no key the plan is composed from sentences lifted
  out of the retrieved passages, so every citation is literally where the text came from. It is
  less fluent than the LLM draft and it is not a degraded mode in the way that matters: it
  cannot fabricate, and it runs in under half a second with no network. At a venue with bad wifi that is the
  normal case, not the sad path.

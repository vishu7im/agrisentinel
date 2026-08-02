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

**`auto` when nobody chose, and the vote never overrules someone who did.** That payoff above
was still a failure, just a legible one. `crop` used to default to `tomato` in the form field,
in `new_run()` and in the frontend's own call, with no crop picker anywhere — so the default
was never overridden by anything, and a corn field uploaded by an ordinary user was scanned as
tomato and reported **94.4% infected, ~49.9% yield at risk** against the true 30.6% and 9.2%.

Callers now send `auto` when no human has chosen. A probe pass over the first
`CROP_PROBE_TILES` tiles reads them unmasked and sums probability mass per crop; the winner
becomes the crop. On the synthetic mosaics it takes 0.91-0.99 of the mass and is never wrong.

**On real photographs it is wrong most of the time**, and that is why it stops at `auto`. Four
Wikimedia Commons photos: a corn field split tomato 0.502 / corn 0.483, corn rust read tomato
0.469, a potato leaf read corn 0.438, and a tomato plant read corn at 0.754 — above the
threshold, and confidently wrong. Letting that overrule a person who picked "tomato" in the UI
would lose more runs than it saved, so an explicit crop is obeyed and the disagreement is only
logged. Same lab-to-field gap as `ml/artifacts/lab_vs_field.md`, arriving one layer up.

Every branch logs — `diagnose.crop_detected.corn.96pct`, then one of `crop_auto.corn`,
`crop_uncertain.corn.70pct`, `crop_mismatch.corn` (declared crop kept) or
`crop_unresolved.tomato` (nothing to vote on). Nothing changes silently, because `crop` is what
the farmer brief, the severity weights and the retrieval filter all key off.

## A6 — RAG and the Agronomist

| file | what it is |
|---|---|
| `rag/corpus/*.md` | Ten agronomy documents covering all eleven diseases. See the corpus README on what they are and are not. |
| `rag/ingest.py` | Corpus → 49 citable chunks in `rag/index/chunks.json`. |
| `rag/retrieve.py` | TF-IDF search with crop and disease filters. |
| `llm.py` | The only place an LLM is called. Gemini over stdlib `urllib`. |
| `prompts.py` | Prompt text, so a wording edit cannot break control flow. |
| `drafting.py` | The two drafters and the marker check that judges both. |
| `agronomist.py` | The agent: which disease, is it covered, whose answer wins. |

**Zero new dependencies.** No Qdrant, no FAISS, no sentence-transformers, no SDK. Retrieval is
`TfidfVectorizer` over 49 chunks — scikit-learn was already pinned for DBSCAN — and the Gemini
call is a JSON POST. Dense embeddings earn their keep when query and document say the same
thing in different words; here the query is built from a classifier label and the documents use
those words because they are the names of the things. It also buys determinism, which A7 needs:
the same sentence and chunk give the same score every time, so a stored run can be re-audited.

**The plan runs without a network.** With no `GEMINI_API_KEY`, the Agronomist composes the plan
extractively — each line is a sentence copied out of the passage whose id it carries, so the
markers cannot be wrong. Drop a key in `.env` (see `.env.example`) and it drafts with Gemini
instead, policed by the same marker check. Venue wifi is not a dependency worth taking, so the
offline path is the normal one and the key is the upgrade.

### Retrieval is filtered, not just ranked — three bugs' worth of reason

Each of these produced a plan that was fluent, correctly cited, and about the wrong thing —
the failure a citation is least able to warn anyone about.

1. **Wrong crop.** "tomato late blight" returned the *potato* document, which recommends
   earthing up to protect tubers. `doc_04`'s prose says "Late blight, caused by Phytophthora
   infestans" and never repeats the crop; `doc_08` says "tomato" three times explaining that
   the two crops infect each other. Fixed by tagging each document with its crops and filtering.
2. **Wrong disease.** Constrained to tomato, it then cited the *early* blight document for a
   late blight diagnosis. Body-text containment does not fix this — the early blight document
   legitimately says "Unlike late blight it begins on the oldest leaves". So `require` matches
   title and heading only: a document is about what it is titled, not what it mentions.
3. **Right document, wrong section.** `doc_10` is titled for all three corn diseases, so the
   title admits every section of it, and a section headed "Gray leaf spot" was supplying
   first-response advice for northern leaf blight. Fixed by excluding chunks whose *heading*
   names a different disease.

### Coverage is a containment test, not a score threshold

The obvious design refuses when the best retrieval score falls below a floor. Measured, it
cannot work here: over 18 in-domain and 6 out-of-domain queries, in-domain top-1 bottomed out
at **0.110** and out-of-domain reached **0.104** — the populations overlap, and "rice blast
paddy nitrogen top dressing" scores that well because "nitrogen" appears in two tomato
documents. Any cut would have looked principled and been worth nothing.

What separates them is that a corpus covering a disease *says its name*. So the disease-scoped
searches refuse anything not naming it, and an empty identification section means no coverage.
Both refusals are real and demonstrated: `panama_wilt` (absent entirely) and corn `late_blight`
(present, but only for tomato and potato) each return `agronomist.insufficient_context` with
`plan_draft` null.

### An LLM refusal is not overruled

If the model reads the passages and answers `INSUFFICIENT_CONTEXT`, the agent stops. It does
*not* fall through to extractive drafting, because the extractive drafter cannot assess
coverage at all — it assembles whatever retrieval returned. Falling through would mean the one
component that actually read the passages is ignored precisely when it says no. Transport
failures are the opposite case and do fall back: there, nothing was judged.

### The bare-soil bug, again, one stage later

`field_all_soil.jpg` — a photograph of dirt — came back with a full treatment plan for yellow
leaf curl virus, cited and fluent, drafted from the single tile that survived the Scout's mask
at 0.10 confidence. Spread already declines that case and reports 0% affected; the Agronomist
was re-deriving the disease from tile labels and never read it.

This is A5's bug wearing a different hat. There, a false keep was called harmless because it
cost one low-confidence prediction — true of every consumer that existed at the time, false of
a ratio. Here, Spread's honest "I could not measure this" was worth nothing because the next
consumer didn't look at it. **The lesson generalises: an agent that declines to answer has only
done half the job; the decline has to be something the next agent reads.** The Agronomist now
treats Spread as the authority on how much of the field is affected rather than recomputing it.

### What A6 leaves null

`verification`, `schedule`, `cost_estimate`, `rescan_date` and `report`. `plan_draft` is now
populated. `status` is `complete` and `finished_at` is set, because the contract says the SSE
stream closes on `run.complete` or `run.error` and nothing else — a run that ends without
emitting one leaves the browser holding an open connection and a spinner.

`run.py` validates the state against the schema before printing it, so a shape regression fails
loudly here rather than quietly in Dev B's browser.

### Two things A7 had to know

**An unverified draft shipped until A7.** The Agronomist writes `plan_draft` and there was nobody
to overrule it. Sentences that came back without a valid marker are deliberately *left in*
rather than stripped, with `agronomist.unmarked.<n>_sentences` on the log — pre-filtering them
would hand the Verifier a clean plan and hide the failure it exists to report. That was a stated, temporary
condition of A6; the Verifier closed it.

**Do not demand corpus support for scan numbers.** The diagnosis line states the affected
percentage and cluster count, which come from the field scan and appear in no passage; its
citation backs the *description of the disease*, not the numbers. A grounding check that
demands a source for "18.4%" will flag a sentence that is true and correctly cited.

`retriever().similarity(sentence, chunk_id)` is already there for the grounding check, and
`state.sources` carries the exact chunks the draft was written from — that hand-off is why
`RunState` has an `INTERNAL_FIELDS` tuple. Only the Verifier may publish them, under
`verification.sources`, because `verification.status` has no value meaning "not ruled on yet"
and writing one would mean inventing it.


---

## A7 — the Verifier

| file | what it is |
|---|---|
| `verifier.py` | The ruling: PASS, REWRITE, BLOCK, and who gets overruled. |
| `claims.py` | The evidence the ruling is made on. No policy — grounding, chemicals, doses. |
| `allowlist.json` | What may be sprayed, and at what rate. Committed, not derived. |
| `refusal.py` | The bilingual brief a blocked run ships instead of a plan. |

The loop lives in `orchestrator.py` and nowhere else. The Agronomist writes drafts and reads
rulings; the Verifier reads drafts and writes rulings; neither imports the other. A rewrite
reaches the Agronomist the way everything else does — as `verification.unsupported_claims`,
already on the run state, with `agronomist.redraft.<n>_rejected` on the log. The retry budget
is `MAX_REWRITES` in `verifier.py` and is not counted anywhere else, because two components
each believing they own the budget is how a plan gets rewritten five times.

### Cosine similarity does not work as a grounding test

The obvious design scores each sentence against the chunk it cites using the same TF-IDF
similarity the retriever already offers. Measured over seven real sentences and seven
fabrications:

| | range |
|---|---|
| verbatim, true | 0.265 – 0.727 |
| fabricated | 0.000 – 0.297 |

The populations overlap. *"Apply carbendazim 50 percent WP at 4.0 grams per litre for faster
knockdown"* — invented chemical, invented dose — scored **0.297** against a chunk that never
mentions it, beating the true sentence *"Re-inspect the field seven days after the first
application"* at **0.265**. Cosine rewards sharing the vocabulary of dosing advice, and a
convincing fabrication shares exactly that vocabulary. It measures register, not truth.

Containment — what fraction of the sentence's content words occur in the cited chunk —
separates them, because a sentence lifted from a passage is *made of* that passage: verbatim
sentences score 1.000, fabrications 0.000 – 0.250. `GROUNDING_MIN` is 0.45, and both numbers
either side of it were measured rather than picked. This is the same shape of finding as A6's
coverage threshold, one level down: the plausible scalar does not separate the populations,
and something structural does.

### Three checks, because each is blind to what the others see

The one fabrication containment ranks highly (0.625) is that carbendazim sentence, because it
copies the *format* of dosing advice — "percent", "grams", "per litre" — while inventing the
only two things that matter. Grounding cannot catch it; the allowlist catches it instantly.
Grounding catches invented advice, the allowlist catches invented chemicals, dose ranges catch
altered numbers. Any one of them alone ships something bad.

`allowlist.json` is committed rather than computed from the corpus at run time. A check derived
from the thing it checks can never disagree with it, and editing a corpus file must not
silently widen what the system may recommend.

### Why a chemical violation blocks and an ungrounded sentence does not

Dropping an unsupported sentence leaves a shorter, still-correct plan. A chemical the corpus
never names, or a dose outside the range it states, is different in kind: the failure mode is
not an embarrassing sentence, it is a person mixing the wrong thing into a sprayer. There is no
version of that worth rewriting toward, so it is a BLOCK — `plan_draft` is cleared, `status`
becomes `blocked`, and `refusal.py` writes the brief in place of the plan.

A blocked run still emits `run.complete`, not `run.error`. A refusal is a successful outcome of
the pipeline — the system worked out that it should not answer — and reporting it as an error
would tell the UI to show a crash where it should show a decision.

### The honest limitation

A truthful paraphrase scores as low as a fabrication. *"Do not rely on the same chemical group
again and again or it will stop working"* is a faithful restatement of `doc_19#p1` and scores
**0.000** against it. Nothing lexical can tell that from invention — only entailment can, and
that needs a model. So with no API key the system demands near-verbatim grounding and sends a
paraphrase back as REWRITE. That costs nothing on the default path, where the drafter copies
sentences and containment is 1.000 by construction, and it fails toward asking again rather
than toward trusting.

### Verified

| case | ruling | events |
|---|---|---|
| grounded draft | PASS | `agronomist.done` → `verify.pass` |
| one ungrounded sentence, model fixes it | PASS | `verify.rewrite` → `agronomist.redraft.1_rejected` → `verify.pass` |
| model never fixes it | PASS, stripped | two `verify.rewrite` rounds → `verify.stripped.1_sentences` → `verify.pass` |
| unapproved chemical + 3× dose | BLOCK | `verify.block.2_violations` → `verify.block` |
| banned active (monocrotophos) | BLOCK | `verify.block.1_violations` → `verify.block` |
| corpus does not cover the disease | BLOCK | `agronomist.insufficient_context` → `verify.block` |

The three adversarial drafts were injected at the drafting step, not at the Verifier, so each
case ran through the real orchestrator loop.

### What A7 fixed for the UI

`verification.sources` is now published, so the `[doc_04#p4]` markers in the plan resolve to
source chips. Before this the plan panel had citations and nothing to resolve them against —
and in fact rendered no plan at all, because it gates on `verification` being present.

### What A7 left null

`schedule`, `cost_estimate`, `rescan_date`, and `report` on a passing run — all filled by A8. A
blocked run has a `report` and nothing else, because a BLOCK skips both remaining agents and
something still has to be on the screen of someone standing in a field who has just been told no.

---

## A8 — Planner and Reporter

| file | what it is |
|---|---|
| `planner.py` | Schedule, cost band, re-scan date, read out of the verified plan. |
| `treatment_costs.json` | Per-product INR bands. A triage figure, not a quote. |
| `reporter.py` | Six plain sentences in English and Hindi. |

Both parse the verified `plan_draft` rather than asking a model to summarise it, because a
paraphrase of a dose is a safety problem and not a style one. The re-inspection interval is read
from the plan's own follow-up sentence, not hardcoded. `report.hi` is a reviewed phrase table
filled in with numbers — never a runtime translation — for the same reason the extractive
drafter exists: the one farmer-facing artefact nobody re-checks should not be produced by the
component least able to guarantee it.

Both are skipped entirely on a BLOCK. A schedule is a list of dates to go and spray something,
and on a blocked run there is nothing to spray.

### Two bugs the corn fixture found, both upstream of A8

**The chemical section picked the wrong sentence.** Asked for chemical control of northern leaf
blight, word overlap chose *"The decision to spray maize is economic and depends on growth
stage..."* over the sentence directly after it naming propiconazole at 1.0 millilitre per litre.
Nothing downstream could recover: the Planner had no product to schedule and no dose to cost, so
it emitted "Follow plan guidance" and the brief read *"Today, follow plan guidance. Then, follow
plan guidance."* `best_sentence(..., must_dose=True)` now ranks dosed sentences first for that
section only — a section headed "Chemical control" is being asked what to spray and how much.

**The English brief pasted corpus prose.** It ran to nine sentences containing "gives curative
action on tissue already infected", while the Hindi brief was six short ones from a phrase
table. The spec says six, plain, no jargon. English now uses the schedule's short action label
plus the dose — the full grounded sentence is still one panel up, with its source.

# Vision cross-check — before and after

`ml/report/vision_crosscheck.py`, over 7 photographs in `agents/testdata/real`.

**This is not an evaluation set.** These photographs have no expert diagnosis behind
them, so nothing here scores the disease label. What is counted is the one thing that is
unambiguous and is the reason the cross-check exists: whether a run hands a farmer a
spray schedule. Seven photographs is an anecdote — it is the same anecdote several times
and it points one way, and it is still an anecdote.

## Headline

| | before | after |
|---|---|---|
| runs that shipped a spray plan | 7/7 | **4/7** |
| crop identified correctly | 3/5 | **5/5** |
| cross-check usable | — | 7/7 |

## Per photograph

| image | crop before → after | tiles say | vision says | plan before → after |
|---|---|---|---|---|
| `corn_nlb.jpg` | corn → corn | 62.5% affected | corn__gray_leaf_spot · 40% | plan → plan |
| `corn_rust.jpg` | tomato → tomato | 92.0% affected | unknown · 0% | plan → **withheld** |
| `maize_field_healthy.jpg` | corn → corn | 56.7% affected | corn__healthy · 0% | plan → **withheld** |
| `potato_field_healthy.jpg` | corn → potato | 76.9% affected | potato__healthy · 0% | plan → **withheld** |
| `potato_lateblight.jpg` | corn → potato | 20.0% affected | potato__late_blight · 10% | plan → plan |
| `tomato_lateblight.jpg` | corn → tomato | 30.8% affected | unknown · 60% | plan → plan |
| `tomato_septoria.jpg` | tomato → tomato | 97.5% affected | tomato__bacterial_spot · 20% | plan → plan |

## What the second model reported seeing

- `corn_nlb.jpg` — A close-up view of corn plants showing elongated, necrotic, grayish-brown lesions on the leaves.
- `corn_rust.jpg` — A black and white line drawing showing a cross-section of plant tissue with fungal structures emerging from the surface.
- `maize_field_healthy.jpg` — A field with rows of young green crop plants emerging through plastic mulch, with a hilly, grassy landscape in the background.
- `potato_field_healthy.jpg` — A field of young potato plants growing in rows with red soil.
- `potato_lateblight.jpg` — A potato leaf shows a large, dark, necrotic lesion with a slightly chlorotic halo.
- `tomato_lateblight.jpg` — Two views of a harvested tomato fruit with large dark lesions and white mold on a wooden surface.
- `tomato_septoria.jpg` — A close-up view of tomato leaves showing small, scattered brown spots on the foliage.

## Cost

| median scan, cross-check off | 8.95 s |
|---|---|
| median scan, cross-check on | 11.62 s |

The call is started after the Scout and collected before the Consensus agent, so on a run
with an explicitly chosen crop it overlaps tile scoring. On an `auto` run the crop has to
be settled before the Diagnostician masks its logits, and the wait is unavoidable.

## Runs that lost a plan

Each of these previously produced a treatment schedule and now does not:

- `corn_rust.jpg`
- `maize_field_healthy.jpg`
- `potato_field_healthy.jpg`

Every one is a case where the whole-image check contradicted the tile grid. Whether
that is a fix or an over-block cannot be settled from these photographs alone — it
needs a diagnosis from someone who stood in the field.

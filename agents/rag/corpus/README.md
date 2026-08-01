# Corpus — provenance, and what these documents are

**These are summaries compiled for this project. They are not scans or reproductions of any
specific publication, and no document here should be cited as if it were one.**

Every file was written for AgriSentinel from widely published agronomy guidance — the kind
carried by state agriculture university extension bulletins and ICAR crop advisories. The
active-ingredient names and the dose ranges are the conventional Indian recommendations for
these crops; the wording is ours.

That distinction is the whole reason this README exists. The Verifier in A7 will hold every
sentence of a treatment plan against a chunk of one of these files, and a grounding check is
only worth as much as the thing it grounds against. Claiming these were extension PDFs would
make the demo look stronger and the system worth less.

## Why these ten documents

| id | title | covers |
|---|---|---|
| `doc_01` | Tomato Early Blight — Identification and Management | `tomato__early_blight` |
| `doc_02` | Tomato Bacterial Spot — Identification and Management | `tomato__bacterial_spot` |
| `doc_03` | Tomato Septoria Leaf Spot and Leaf Mold | `tomato__septoria_leaf_spot`, `tomato__leaf_mold` |
| `doc_04` | Tomato Late Blight - Field Identification and Management | `tomato__late_blight` |
| `doc_06` | Tomato Yellow Leaf Curl Virus and Whitefly Vector Management | `tomato__yellow_leaf_curl_virus` |
| `doc_07` | Fungicide Application Practice Note | spray technique, timing, water volume |
| `doc_08` | Potato Late Blight and Early Blight — Field Management | `potato__late_blight`, `potato__early_blight` |
| `doc_10` | Corn Foliar Diseases — Rust, Northern Leaf Blight, Gray Leaf Spot | the three `corn__*` diseases |
| `doc_12` | Integrated Disease Management for Solanaceous Crops | sanitation, scouting, healthy-crop practice |
| `doc_19` | Fungicide Resistance Management Guidelines | mode-of-action rotation |

That covers all eleven diseases the classifier can emit, plus the three cross-cutting topics
every plan needs regardless of disease. The numbering is sparse on purpose: `doc_04`,
`doc_07`, `doc_12` and `doc_19` carry the exact ids and titles already cited in the frozen
`contract/mock_run.json`, so the source chips Dev B built against the mock resolve against
the real corpus too.

## Format the ingester expects

- `# Title` on the first line — becomes the `doc` field the UI shows in the drawer header.
- `## Heading` starts each section. One section is roughly one chunk.
- The filename's number is the doc id: `doc_04_*.md` → `doc_04`.

Page numbers are assigned by `ingest.py` as the chunk's ordinal position in the document.
Markdown has no pages, and stamping plausible-looking page numbers onto a document that was
never printed is exactly the kind of decoration that turns a citation into a prop.

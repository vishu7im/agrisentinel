# backend — Dev A

FastAPI app serving the four endpoints in `contract/endpoints.md`. **All four are live as of
A5**, plus `GET /api/run/{id}/image` for the heatmap backing image.

| file | what it is |
|---|---|
| `app/main.py` | The endpoints, and nothing else. Meant to read like `endpoints.md`. |
| `app/pipeline.py` | Model singleton and the background job. Adds the repo root to `sys.path`. |
| `app/store.py` | Live runs in a dict, finished runs in SQLite, uploads on disk. |

`POST /api/run` returns `202` with a `run_id` before the work starts, then the scan runs in
Starlette's worker threadpool. `GET /api/run/{id}/events` replays `events[]` from index 0 —
so a reconnecting or late-opening tab sees the whole run, not the tail — and closes on
`run.complete` or `run.error`.

The ONNX session is built once at startup and shared across threads. If `ml/artifacts/model.onnx`
is missing the app still starts and `/api/health` still answers; `POST /api/run` returns `503`
with the reason. "Backend down" and "model not exported" send you to different places, and an
app that refuses to boot tells you neither.

Uploads and the SQLite file live in `backend/uploads/`, which is gitignored. Delete it to
reset; it is rebuilt on startup.

## Optional: an LLM key

As of A6 a run returns a `plan_draft`, and as of A8 a schedule, cost band and farmer brief too. It does that with or without a network — with no key
the Agronomist composes the plan extractively from the retrieved corpus passages, which is the
mode the demo should assume. To draft with Gemini instead, copy the repo-root `.env.example`
to `.env` and set `GEMINI_API_KEY`. Nothing else changes; the endpoints and the response shape
are identical either way, and the event log says which path ran
(`agronomist.drafted.llm` vs `agronomist.drafted.extractive`).

The retrieval index is committed (`agents/rag/index/chunks.json`). Rebuild it after editing the
corpus with `.venv/bin/python -m agents.rag.ingest`.

## Setup

This machine's Python is PEP-668 externally managed, so a venv is required — `pip install`
outside one will refuse.

```bash
# from the repo root
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

## Run

```bash
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
curl -s http://localhost:8000/api/health
# {"status":"ok"}
```

Interactive docs at http://localhost:8000/docs.

## Port 8000 is shared with the mock server

`contract/mock_server.mjs` also defaults to 8000. Run one at a time. That collision is
intentional: at M1 Dev B stops the mock, you start this, and their `VITE_API_URL` never
changes.

## Checking the contract still holds

Every response must match the frozen schema:

```bash
RID=$(curl -s -X POST localhost:8000/api/run \
        -F "image=@agents/testdata/field_tomato_heavy.jpg" -F "crop=tomato" | jq -r .run_id)
curl -sN localhost:8000/api/run/$RID/events        # watch it happen, closes on run.complete
curl -s  localhost:8000/api/run/$RID | .venv/bin/python contract/validate.py -
```

That validator also diffs top-level keys against `contract/mock_run.json`, which is what
catches the failure mode that actually hurts: a response that is schema-valid but missing a
field Dev B's UI reads.

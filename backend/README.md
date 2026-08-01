# backend — Dev A

FastAPI app serving the four endpoints in `contract/endpoints.md`.
As of Phase 0 only `/api/health` is implemented; the rest lands in **A5**.

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

After A5, every response must match the frozen schema:

```bash
RID=$(curl -s -X POST localhost:8000/api/run -F "image=@demo/field_photos/field_01.jpg" | jq -r .run_id)
curl -s localhost:8000/api/run/$RID | ../.venv/bin/python ../contract/validate.py -
```

That validator also diffs top-level keys against `contract/mock_run.json`, which is what
catches the failure mode that actually hurts: a response that is schema-valid but missing a
field Dev B's UI reads.

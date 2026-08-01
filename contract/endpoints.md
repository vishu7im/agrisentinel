# API Contract — 4 endpoints

**FROZEN after Phase 0.** Dev A implements these in `backend/`; Dev B calls them from `frontend/`.
Both sides depend on this file, so a change here needs both devs to agree out loud.

Base URL comes from `VITE_API_URL` on the frontend. Default `http://localhost:8000`.

There are exactly four endpoints. If you need a fifth, that's a conversation, not a commit.

---

## `POST /api/run`

Upload a field image and start a run. Returns immediately — the pipeline runs in the background.

**Request:** `multipart/form-data`

| Field | Type | Required | Notes |
|---|---|---|---|
| `image` | file | yes | JPEG or PNG field mosaic |
| `crop` | string | no | `tomato` \| `potato` \| `corn`. Defaults to `tomato`. |

**Response `202 Accepted`**

```json
{ "run_id": "7f3c1e88-9a24-4b6d-b0e1-2c5f9d84a013" }
```

Errors: `400` if no image, `415` if not an image type, `413` if oversized.

```bash
curl -s -X POST http://localhost:8000/api/run \
  -F "image=@demo/field_photos/field_01.jpg" -F "crop=tomato"
```

---

## `GET /api/run/{run_id}`

The full run-state object. Shape is defined by `run_state.schema.json` — that schema is the
authority, not this document.

**Response `200`** — the complete run state. Poll-safe. While `status` is `running`, the
optional sections (`spread`, `plan_draft`, `verification`, `schedule`, `report`,
`cost_estimate`, `rescan_date`) may be `null`, and `tiles[]` may be partially filled.
`404` if the run_id is unknown.

See `mock_run.json` for a complete, realistic example. The response keys must match it exactly.

```bash
curl -s http://localhost:8000/api/run/7f3c1e88-9a24-4b6d-b0e1-2c5f9d84a013 | jq .spread
```

---

## `GET /api/run/{run_id}/events`

Server-Sent Events stream of the agent event log. This is what makes the orchestration
visible in the UI.

**Response `200`**, `Content-Type: text/event-stream`.

Each event is one line from `events[]`, sent as the SSE `data:` field:

```
data: scout.done

data: diagnose.tile.t_05_00

data: orchestrator.escalate.3_tiles
```

- Events replay from the **start** of the run on connect, so a late or reconnecting client
  still sees the whole story. The client can safely rebuild its state from scratch.
- The stream closes after `run.complete` or `run.error`.
- Event strings are namespaced `<agent>.<event>[.<detail>]`. The known set is listed in the
  `events` description in `run_state.schema.json`. **Unknown events must not break the UI** —
  render anything unrecognised in a neutral style, so Dev A can add events without a contract change.

```bash
curl -N http://localhost:8000/api/run/7f3c1e88-9a24-4b6d-b0e1-2c5f9d84a013/events
```

---

## `GET /api/health`

**Response `200`**

```json
{ "status": "ok" }
```

Used by the frontend to tell "backend is down" from "run failed".

---

## Also served (not part of the frozen four)

`GET /api/run/{run_id}/image` returns the uploaded field image, so the heatmap has something
to sit on. The path is carried in the run state's `image_url` field rather than being
constructed by the client — treat `image_url` as opaque.

---

## Mock server

Dev B builds against the mock all of Day 1 and swaps `VITE_API_URL` at M1. Zero dependencies:

```bash
node contract/mock_server.mjs              # port 8000, 1 event/sec
node contract/mock_server.mjs --fast       # 150ms/event, for quick UI iteration
node contract/mock_server.mjs --slow       # 2s/event, for demo rehearsal
node contract/mock_server.mjs --block      # serves a BLOCK-verdict run, for the B6 refusal UI
node contract/mock_server.mjs --port 8010  # if 8000 is taken
```

A full replay is 51 events, so roughly 51s at the default rate. Use `--fast` while building.

### Two known differences from the real backend

1. **`GET /api/run/{id}` always returns the completed run**, even one millisecond after `POST`.
   The real backend fills the state in progressively. Drive progressive rendering from the SSE
   stream, not from polling this endpoint, and the difference never bites you.
2. **Any `run_id` is accepted** and echoed back in the response body — the mock never 404s.
   Don't rely on the mock to test your not-found path.

### Port collision

The mock server and the real backend both default to **8000**. Run one at a time. That is the
entire point of the M1 switchover: same port, same shapes, flip one env var.

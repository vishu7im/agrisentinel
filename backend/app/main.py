"""AgriSentinel backend — the four endpoints in contract/endpoints.md, and nothing else.

    cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000

The shapes here are not negotiable: `contract/run_state.schema.json` is frozen and the
frontend was built against `contract/mock_run.json` all of Day 1. At M1 Dev B stops the mock
server, starts this on the same port, and changes nothing. Every response below therefore
comes straight from `RunState.to_dict()`, which emits every schema key including the null
ones — so a field that is not filled until A7 arrives as `null` rather than going missing.

Threading and model loading live in pipeline.py; run storage in store.py. This file is meant
to read like the contract document.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app import pipeline
from app.store import RunStore

# Vite's dev server. 127.0.0.1 and localhost are distinct origins to the browser, so both are
# listed — the difference is otherwise a ten-minute CORS mystery.
FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# A field mosaic off a phone is 2-8 MB. 32 covers a DSLR panorama and still refuses the
# accidental video upload before it reaches the disk.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
CHUNK = 1024 * 1024

# How often the SSE endpoint checks for new events. The pipeline appends roughly one event
# per 7 ms during diagnosis, so this batches a handful per wake-up rather than spinning.
SSE_POLL_SECONDS = 0.05
# A stream that never sees run.complete is a browser connection held open forever. The whole
# pipeline is well under a second on the fixtures; ten minutes is a backstop, not a budget.
SSE_MAX_SECONDS = 600

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("agrisentinel")

store = RunStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline.load_classifier()
    pipeline.warm_up()
    log.info("ready — %d stored runs", store.count())
    yield


app = FastAPI(
    title="AgriSentinel",
    description="Autonomous field health agent. See contract/endpoints.md.",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Liveness probe. The frontend uses this to tell 'backend down' from 'run failed'."""
    return {"status": "ok"}


@app.post("/api/run", status_code=202)
async def start_run(
    background: BackgroundTasks,
    image: UploadFile | None = File(None),
    crop: str = Form("tomato"),
) -> dict[str, str]:
    """Accept a field image, start the pipeline in the background, return the run id at once.

    Returning before the work starts is the point: the frontend opens the SSE stream with
    this id and watches the run happen. A synchronous version would hold the request open for
    the whole scan and there would be nothing to stream.
    """
    # File(None) rather than File(...) on purpose: a required field makes FastAPI answer a
    # missing upload with 422, and contract/endpoints.md says 400. The contract is frozen and
    # the framework's default is not, so the check is written out by hand.
    if image is None:
        raise HTTPException(400, "no image provided")
    if pipeline.classifier_error():
        raise HTTPException(503, f"model unavailable: {pipeline.classifier_error()}")
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(415, f"expected an image, got {image.content_type!r}")

    from agents.state import new_run

    state = new_run(crop=crop)
    suffix = ".png" if "png" in (image.content_type or "") else ".jpg"
    target = store.image_path(state.run_id, suffix)

    # Streamed in chunks and size-checked as it goes, so a rejected 2 GB upload costs 32 MB of
    # disk and no memory at all rather than being buffered whole and then refused.
    try:
        size = 0
        with target.open("wb") as out:
            while chunk := await image.read(CHUNK):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"image exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
                out.write(chunk)
        if not size:
            raise HTTPException(400, "empty image upload")
    except HTTPException:
        store.discard(state.run_id)
        raise

    store.put_live(state)
    store.save(state)  # persist the queued row now, so a crash mid-run still leaves a record
    background.add_task(pipeline.run_scan, state, target, store)
    log.info("run %s queued — crop=%s, %d KB", state.run_id, crop, size // 1024)
    return {"run_id": state.run_id}


@app.get("/api/run/{run_id}")
async def get_run(run_id: str) -> dict:
    """The full run state. Poll-safe, and partially filled while the run is in flight."""
    state = store.get(run_id)
    if state is None:
        raise HTTPException(404, f"no run {run_id}")
    return state


@app.get("/api/run/{run_id}/image")
async def get_run_image(run_id: str) -> FileResponse:
    """The uploaded field photo, so the heatmap has something to sit on. The client gets this
    path from the run state's image_url and should treat it as opaque."""
    path = store.find_image(run_id)
    if path is None or not path.exists():
        raise HTTPException(404, f"no image for run {run_id}")
    return FileResponse(path)


@app.get("/api/run/{run_id}/events")
async def stream_events(run_id: str, request: Request) -> StreamingResponse:
    """SSE replay of events[], from the beginning of the run, closing on run.complete/error.

    Replaying from index 0 rather than from "now" is what makes a reconnect or a late-opened
    tab show the whole story instead of half of it — the client can always rebuild its view
    from scratch, which is the property that makes the stream the source of truth for the UI.
    """
    if store.get(run_id) is None:
        raise HTTPException(404, f"no run {run_id}")

    async def events():
        sent, waited = 0, 0.0
        while waited < SSE_MAX_SECONDS:
            if await request.is_disconnected():
                return
            new, finished = store.events_since(run_id, sent)
            for event in new:
                yield f"data: {event}\n\n"
            sent += len(new)
            if finished:
                return
            if not new:
                # A comment line keeps proxies and load balancers from reaping an idle
                # connection. Clients ignore it; EventSource never surfaces it.
                yield ": keepalive\n\n"
            await asyncio.sleep(SSE_POLL_SECONDS)
            waited += SSE_POLL_SECONDS

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # nginx buffers proxied responses by default, which turns a live event stream into
            # one silent pause followed by the entire run arriving at once.
            "X-Accel-Buffering": "no",
        },
    )

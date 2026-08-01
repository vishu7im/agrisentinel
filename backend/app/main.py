"""
AgriSentinel backend — Phase 0 scaffold.

Only /api/health exists right now. The other three endpoints in contract/endpoints.md
(POST /api/run, GET /api/run/{id}, GET /api/run/{id}/events) are built in Phase A5, at
which point the frontend flips VITE_API_URL from the mock server to this app and nothing
else changes.

Run:
    .venv/bin/uvicorn app.main:app --reload --port 8000     # from backend/
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Vite's dev server. 127.0.0.1 and localhost are distinct origins to the browser, so both
# are listed — the difference is otherwise a ten-minute CORS mystery.
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app = FastAPI(
    title="AgriSentinel",
    description="Autonomous field health agent. See contract/endpoints.md.",
    version="0.1.0",
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

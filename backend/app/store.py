"""Where runs live: a dict for the run in flight, SQLite for the ones that finished.

Two tiers, because the two access patterns are genuinely different. A run in progress is
mutated dozens of times a second by a worker thread while an SSE stream reads its event log —
that wants a live object in memory. A finished run is read-only and needs to survive
`--reload` restarting the process mid-demo — that wants a row on disk.

`get()` checks memory, then disk, so the caller never has to know which tier answered.

**Threading.** The pipeline runs in Starlette's worker threadpool while the SSE endpoint reads
from the event loop, so every dict access is under a lock. The event list itself is not
copied under that lock by the writer — `list.append` is atomic under the GIL — but readers
snapshot it inside `events_since` so they can never observe a half-built list.

**SQLite connections are per-call.** A connection is not safe to share across threads without
`check_same_thread=False` plus serialisation, and opening one costs microseconds against a
write that happens once per run. Not a hot path, so it buys thread-safety for free.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
# backend/uploads/ is already in .gitignore, and an uploaded field photo is exactly the kind
# of large binary that must never reach a commit.
DATA_DIR = BACKEND_ROOT / "uploads"
DB_PATH = DATA_DIR / "runs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    status     TEXT NOT NULL,
    started_at TEXT,
    state      TEXT NOT NULL
)
"""


class RunStore:
    def __init__(self, data_dir: Path = DATA_DIR, db_path: Path = DB_PATH):
        self.data_dir = data_dir
        self.db_path = db_path
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._live: dict[str, object] = {}
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=5.0)

    # --- images ---------------------------------------------------------------------------

    def image_path(self, run_id: str, suffix: str = ".jpg") -> Path:
        """One directory per run. Keeps the upload next to nothing else, so cleaning up a
        run is a single rmtree and there is no chance of colliding filenames."""
        run_dir = self.data_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir / f"field{suffix}"

    def discard(self, run_id: str) -> None:
        """Remove a run's directory. For uploads rejected after the directory was made —
        without it, every oversized or empty POST leaves an empty folder behind forever."""
        shutil.rmtree(self.data_dir / run_id, ignore_errors=True)

    def find_image(self, run_id: str) -> Path | None:
        run_dir = self.data_dir / run_id
        if not run_dir.is_dir():
            return None
        return next((p for p in sorted(run_dir.glob("field.*"))), None)

    # --- live runs ------------------------------------------------------------------------

    def put_live(self, state) -> None:
        with self._lock:
            self._live[state.run_id] = state

    def live(self, run_id: str):
        with self._lock:
            return self._live.get(run_id)

    def events_since(self, run_id: str, index: int) -> tuple[list[str], bool]:
        """(new events after `index`, run is finished). The SSE endpoint's only read.

        Returns the finished flag from the same snapshot as the events, not from a second
        lookup — otherwise a run that completes between the two reads drops its last events,
        which on screen is the run.complete line never arriving.
        """
        state = self.live(run_id)
        if state is not None:
            events = list(state.events)
            return events[index:], state.status in ("complete", "blocked", "error")
        stored = self.load(run_id)
        if stored is None:
            return [], True
        return list(stored["events"])[index:], True

    # --- persistence ----------------------------------------------------------------------

    def save(self, state) -> None:
        """Write the run to disk and drop it from memory once it is terminal."""
        payload = state.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (run_id, status, started_at, state) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET status=excluded.status, state=excluded.state",
                (state.run_id, state.status, state.started_at, json.dumps(payload)),
            )
        if state.status in ("complete", "blocked", "error"):
            with self._lock:
                self._live.pop(state.run_id, None)

    def load(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT state FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def get(self, run_id: str) -> dict | None:
        """The run state as a plain dict — live if it is still running, stored if it is not."""
        state = self.live(run_id)
        return state.to_dict() if state is not None else self.load(run_id)

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

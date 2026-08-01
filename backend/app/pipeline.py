"""The bridge from HTTP to /agents: model loading, and the background job that runs a scan.

Kept out of main.py so the endpoint file stays about the contract and this file stays about
execution. main.py should read like contract/endpoints.md; this is where the threading and
the model live.

**The classifier is a process-wide singleton.** Building an ONNX InferenceSession costs far
more than running one, and a session is safe to call from multiple threads. Loading it per
request would put a second of model init in front of every scan.

**Model load failure is not startup failure.** If ml/artifacts/model.onnx is missing, the app
still starts and /api/health still answers — POST /api/run returns 503 with the reason. That
distinction matters at a venue: "backend down" and "model not exported" send you to different
places, and an app that refuses to boot tells you neither.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    # uvicorn is launched from backend/, so the repo root is not importable by default and
    # `import agents` would fail. One insert here rather than a PYTHONPATH the run command
    # has to remember.
    sys.path.insert(0, str(REPO_ROOT))

from agents.diagnostician import Classifier  # noqa: E402
from agents.orchestrator import pipeline_summary, run_pipeline  # noqa: E402
from agents.state import RunState  # noqa: E402
from agents.tiling import load_image  # noqa: E402

log = logging.getLogger(__name__)

_classifier: Classifier | None = None
_load_error: str | None = None


def load_classifier() -> None:
    """Build the ONNX session once, at startup. Records the failure instead of raising."""
    global _classifier, _load_error
    try:
        _classifier = Classifier()
        log.info("model loaded: %d classes, crops %s", len(_classifier.class_keys), _classifier.crops)
    except BaseException as exc:  # Classifier raises SystemExit when the model is missing
        _load_error = str(exc) or exc.__class__.__name__
        log.error("model unavailable: %s", _load_error)


def warm_up() -> None:
    """Pay scikit-learn's lazy import at startup rather than inside the first run.

    It is 20-50 ms of import that would otherwise land in the middle of the Spread Analyst on
    the very first scan of the demo — the one being watched.
    """
    try:
        from sklearn.cluster import DBSCAN  # noqa: F401
    except Exception as exc:
        log.warning("sklearn warm-up failed: %s", exc)


def classifier_error() -> str | None:
    return _load_error


def run_scan(state: RunState, image_path: Path, store, crop_kwargs: dict | None = None) -> None:
    """Background job: decode the upload, run the pipeline, persist. Never raises.

    Called from Starlette's worker threadpool after the 202 has already been sent, so there
    is no client left to receive an exception — anything that escapes here would vanish into
    a log nobody reads mid-demo, leaving a run stuck at `running` forever. So the pipeline's
    own error handling is backstopped by this one.
    """
    try:
        img = load_image(image_path)
        run_pipeline(state, img, _classifier, **(crop_kwargs or {}))
        log.info("run %s: %s", state.run_id, pipeline_summary(state))
    except Exception:
        log.exception("run %s died outside the pipeline", state.run_id)
        if state.status not in ("complete", "blocked", "error"):
            # The pipeline handles its own failures; reaching here means the image itself
            # could not be opened, which happens before any agent runs.
            from agents.state import utc_now

            state.apply("orchestrator.failed.image_decode")
            state.apply("run.error", status="error", finished_at=utc_now())
    finally:
        store.save(state)

"""Orchestrator — the only module that knows the running order.

    from agents.orchestrator import run_pipeline
    run_pipeline(state, img, classifier)      # runs everything, returns the finished state

Every other agent is a function of the run state: it reads what it needs, writes what it
produced, appends to `events[]`, and knows nothing about who ran before it or who runs next.
That is what lets a new agent be inserted here without editing any of them — and what makes
the event log on screen a true trace of execution rather than a story written alongside it.

The supervision this file actually performs is the confidence gate. The Diagnostician scores
every tile once; the orchestrator reads those scores, decides which are weak enough to be
worth a second, more expensive look, announces the count, and hands them to the Second-Opinion
agent. The Diagnostician is not told this happened and does not need to be.

**Failure is a state, not a crash.** If any stage raises, the run ends `status: error` with
`run.error` on the log, because the contract says the SSE stream closes on `run.complete` or
`run.error` and nothing else. A pipeline that dies without emitting one of those leaves the
browser holding an open connection and a spinner forever — the failure mode that looks worst
on a projector. Whatever the failing agent had already written stays in the state: a run that
died in the Agronomist still has a valid grid and a valid severity read, and showing those is
better than showing an error page.

**A6 ends at the Agronomist.** `run.complete` fires with `verification`, `schedule`, `report`,
`cost_estimate` and `rescan_date` still null. That is not the pipeline pretending to be
finished — it is the pipeline being finished as far as it currently goes, with the contract's
nullable fields carrying the difference. A7-A8 add stages between the Agronomist and the
completion below, and nothing outside this file changes when they do.

**Until A7 exists, an unverified draft ships.** The Agronomist writes `plan_draft` and there
is as yet nobody to overrule it, so this is the one window in the project where treatment text
reaches the API without having been checked. `agronomist.unmarked.<n>_sentences` on the log is
the only warning anyone gets. That is a stated, temporary condition of A6 and it is what A7 is
for; it should not survive the phase.
"""

from __future__ import annotations

import logging

from PIL import Image

from agents.agronomist import run_agronomist
from agents.diagnostician import BATCH_SIZE, Classifier, run_diagnostician
from agents.scout import GREEN_THRESHOLD, UNIFORMITY_MAX, run_scout
from agents.second_opinion import CONFIDENCE_GATE, low_confidence_tiles, run_second_opinion
from agents.spread import run_spread
from agents.state import RunState, utc_now
from agents.tiling import DEFAULT_COLS, DEFAULT_ROWS

log = logging.getLogger(__name__)


def run_pipeline(
    state: RunState,
    img: Image.Image,
    classifier: Classifier,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
    batch_size: int = BATCH_SIZE,
    gate: float = CONFIDENCE_GATE,
    green_threshold: float = GREEN_THRESHOLD,
    uniformity_max: float = UNIFORMITY_MAX,
) -> RunState:
    """Scout, Diagnostician, confidence gate, Second-Opinion, Spread, Agronomist. Always terminal."""
    stage = "scout"
    try:
        run_scout(state, img, cols, rows, green_threshold, uniformity_max)

        stage = "diagnostician"
        run_diagnostician(state, img, classifier, cols, rows, batch_size)

        stage = "second_opinion"
        escalate = low_confidence_tiles(state, gate)
        if escalate:
            # Announced before the work, not after: on a slow venue laptop the four-view pass
            # is the longest visible pause in the run, and the UI should be able to say what
            # it is waiting for rather than going quiet.
            state.apply(f"orchestrator.escalate.{len(escalate)}_tiles")
            run_second_opinion(state, img, classifier, gate, cols, rows, batch_size)
        else:
            state.apply("orchestrator.no_escalation")

        stage = "spread"
        run_spread(state)

        # The Agronomist runs after Spread because it needs the severity numbers, not just the
        # disease: how much of the field is affected is what decides between a protectant on
        # the marked clusters and a systemic across the block.
        stage = "agronomist"
        run_agronomist(state)

        state.apply("run.complete", status="complete", finished_at=utc_now())
    except Exception:
        # The stage name goes on the log; the traceback goes to the server. An exception
        # message can carry a filesystem path, and the event log is rendered in a browser.
        log.exception("run %s failed during %s", state.run_id, stage)
        state.apply(f"orchestrator.failed.{stage}")
        state.apply("run.error", status="error", finished_at=utc_now())
    return state


def pipeline_summary(state: RunState) -> str:
    scored = state.scored_tiles
    escalated = [t for t in state.tiles if t.escalated]
    spread = state.spread or {}
    return (
        f"{state.status} | {len(state.tiles)} tiles, {len(scored)} scored, "
        f"{len(escalated)} escalated | {spread.get('pct_affected', 0.0)}% affected | "
        f"{len(state.events)} events"
    )

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

**The pipeline is complete as of A8.** Every field in the contract is now written by some
stage below, and the only nulls left in a finished run are the ones a BLOCK deliberately
leaves: no plan, no schedule, no cost, no re-scan date.

**A blocked run still completes.** `status` becomes `blocked` rather than `error`, and the
event is still `run.complete`, because the contract says the SSE stream closes on
`run.complete` or `run.error` and nothing else. A refusal is a successful outcome of the
pipeline — the system worked out that it should not answer — and reporting it as an error
would tell the UI to show a crash where it should show a decision.
"""

from __future__ import annotations

import logging

from PIL import Image

from concurrent.futures import Future, ThreadPoolExecutor

from PIL import Image

from agents.agronomist import run_agronomist
from agents.consensus import run_consensus
from agents.crop_vote import AUTO
from agents.diagnostician import BATCH_SIZE, Classifier, run_diagnostician
from agents.observer import VISION_TIMEOUT, observe, record_observation
from agents.planner import run_planner
from agents.reporter import run_reporter
from agents.scout import GREEN_THRESHOLD, UNIFORMITY_MAX, run_scout
from agents.second_opinion import CONFIDENCE_GATE, low_confidence_tiles, run_second_opinion
from agents.spread import run_spread
from agents.state import RunState, utc_now
from agents.tiling import DEFAULT_COLS, DEFAULT_ROWS
from agents.verifier import MAX_REWRITES, run_verifier

log = logging.getLogger(__name__)

# One worker. There is exactly one vision call per run, and a single-slot pool makes that a
# property of the code rather than a convention. Not a module-level singleton: the backend runs
# scans on Starlette's threadpool and a shared executor would silently serialise two concurrent
# uploads behind each other's 12-second network call.
OBSERVER_WORKERS = 1

# How long to wait at collection time on top of the call's own timeout. Small: `observe` already
# owns VISION_TIMEOUT and returns rather than raises, so this only covers a thread that has not
# been scheduled yet, and a run must never hang on it.
OBSERVER_JOIN_GRACE = 5.0


def start_observer(img: Image.Image) -> tuple[ThreadPoolExecutor, Future]:
    """Begin the vision call and return immediately.

    The pool is handed back with the future because it has to outlive this function and be shut
    down exactly once, at collection.
    """
    pool = ThreadPoolExecutor(max_workers=OBSERVER_WORKERS, thread_name_prefix="observer")
    return pool, pool.submit(observe, img)


def run_observer_result(state: RunState, started: tuple[ThreadPoolExecutor, Future]) -> RunState:
    """Wait for the vision call and write what it found into the run state.

    Every failure lands as a verdict rather than an exception, including this function's own:
    an observer that cannot be collected must not be able to fail a run that has a perfectly
    good grid, a severity read and a treatment plan waiting behind it.
    """
    from agents.vision_verdict import VisionVerdict

    pool, future = started
    try:
        verdict = future.result(timeout=VISION_TIMEOUT + OBSERVER_JOIN_GRACE)
    except Exception as exc:  # noqa: BLE001 — deliberately total, see the docstring
        log.warning("observer collection failed: %s", exc)
        verdict = VisionVerdict(ok=False, error="failed")
    finally:
        pool.shutdown(wait=False)
    return record_observation(state, verdict)


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
    """Scout, Observe, Diagnose, gate, Second-Opinion, Consensus, Spread, Agronomist, Verifier,
    Planner, Reporter."""
    stage = "scout"
    try:
        run_scout(state, img, cols, rows, green_threshold, uniformity_max)

        # The whole-image cross-check starts here and is collected below. Started rather than
        # run, because it is a network call that measured 12.0-12.9 s against a 1.35 s pipeline,
        # and running it inline means twelve seconds of dead air before a single tile appears.
        # On the projector that pause is the whole system looking broken.
        #
        # Measured with a 6 s stand-in call: an explicit crop costs 6.55 s total, so 0.8 s of
        # the 1.35 s pipeline disappears behind the call; `auto` costs 7.00 s, because only the
        # Scout can overlap before the crop is needed. Never worse than inline, and nearly free
        # whenever a human picked the crop.
        #
        # The thread does no state mutation — `observe` takes an image and returns a verdict —
        # so there is no interleaving with the tile events the Diagnostician is writing. All of
        # its events are applied at `collect`, in one place, in a fixed order.
        stage = "observer"
        state.apply("observer.requested")
        observation = start_observer(img)

        # Where it gets collected is the one real constraint. The Diagnostician masks its logits
        # to the run's crop, so on an `auto` run the crop must be settled first and the wait is
        # unavoidable — though no worse than running it inline. When a human chose the crop the
        # vision answer cannot override it (crop_vote.py's policy), nothing before Consensus
        # reads the verdict, and the entire call overlaps tile scoring for free.
        if state.crop == AUTO:
            run_observer_result(state, observation)
            observation = None

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

        # Fusion, and it must happen before Spread: every number Spread computes is a function
        # of the tile labels, so rewriting them here means Spread, the Agronomist, the Verifier,
        # the Planner and the Reporter all read the fused answer without one line changing in
        # any of them. The division of labour is that the CNN knows *where* and the vision model
        # knows *what* — the tile grid and its clustering are real spatial information that a
        # single whole-image verdict does not have, so a relabel never moves the
        # infected/healthy partition, only the name attached to it.
        stage = "observer"
        if observation is not None:
            run_observer_result(state, observation)

        stage = "consensus"
        run_consensus(state)

        stage = "spread"
        run_spread(state)

        # The Agronomist runs after Spread because it needs the severity numbers, not just the
        # disease: how much of the field is affected is what decides between a protectant on
        # the marked clusters and a systemic across the block.
        stage = "agronomist"
        run_agronomist(state)

        # The verify-redraft loop, and the one place in this pipeline where a stage runs more
        # than once. It lives here rather than inside either agent because neither of them is
        # allowed to know about the other: the Agronomist writes a draft and reads rulings, the
        # Verifier reads drafts and writes rulings, and the going-round is this file's job.
        #
        # The loop condition obeys the Verifier unconditionally. There is no branch below where
        # a REWRITE is overridden, no count kept here that could disagree with MAX_REWRITES,
        # and nothing that inspects the plan to decide whether the ruling was reasonable. When
        # the budget runs out the Verifier is the one that strips and passes — the orchestrator
        # does not get to make that call either.
        stage = "verifier"
        for attempt in range(MAX_REWRITES + 1):
            run_verifier(state, attempt)
            if (state.verification or {}).get("status") != "REWRITE":
                break
            stage = "agronomist"
            run_agronomist(state)
            stage = "verifier"

        # Both are skipped on a BLOCK, and skipped rather than run-and-discarded: a schedule is
        # a set of dates to go and spray something, and there is nothing to spray. The refusal
        # brief the Verifier already wrote stands as the report for that run.
        blocked = (state.verification or {}).get("status") == "BLOCK"
        if not blocked:
            stage = "planner"
            run_planner(state)

            # The Reporter runs last because it summarises the schedule as well as the plan —
            # what to do first is a question about day 0, which does not exist until the
            # Planner has written one.
            stage = "reporter"
            run_reporter(state)

        state.apply(
            "run.complete",
            status="blocked" if blocked else "complete",
            finished_at=utc_now(),
        )
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

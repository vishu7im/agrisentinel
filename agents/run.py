"""Temporary CLI: field image in, run-state JSON out.

    .venv/bin/python agents/run.py <image>
    .venv/bin/python agents/run.py <image> --json | .venv/bin/python contract/validate.py -

A thin CLI over `agents.orchestrator.run_pipeline` — the *same* function the backend calls,
deliberately. The moment this file sequences the agents itself, it becomes possible for a
phase to pass here and fail through the API, and that difference would surface at M1 with
Dev B watching. So the running order lives in exactly one place and this only prints it.

The run-state it prints is validated against contract/run_state.schema.json before it is
shown, because "it looked right" is how a frontend gets broken by a field that was a string
where the schema said number.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.diagnostician import (  # noqa: E402
    BATCH_SIZE,
    Classifier,
    DEFAULT_MODEL,
    diagnose_summary,
)
from agents.orchestrator import run_pipeline  # noqa: E402
from agents.scout import GREEN_THRESHOLD, UNIFORMITY_MAX, scout_summary  # noqa: E402
from agents.second_opinion import CONFIDENCE_GATE, second_opinion_summary  # noqa: E402
from agents.spread import spread_summary  # noqa: E402
from agents.state import new_run  # noqa: E402
from agents.tiling import DEFAULT_COLS, DEFAULT_ROWS, load_image  # noqa: E402

SCHEMA_PATH = REPO_ROOT / "contract" / "run_state.schema.json"
MOCK_PATH = REPO_ROOT / "contract" / "mock_run.json"


def validate(payload: dict) -> list[str]:
    """Schema errors plus top-level key drift against the reference run.

    The key diff catches what a schema check cannot: a response that is perfectly valid and
    still missing a field Dev B reads. Mirrors contract/validate.py so the two never
    disagree about what passing means.
    """
    from jsonschema import Draft202012Validator

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    problems = [
        f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda e: list(e.path))
    ]
    extra = set(payload) - set(json.loads(MOCK_PATH.read_text(encoding="utf-8")))
    if extra:
        problems.append(f"<root>: unexpected top-level keys {sorted(extra)}")
    return problems


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image", type=Path, help="field photo to scan")
    p.add_argument("--crop", default="tomato", help="tomato | potato | corn")
    p.add_argument("--cols", type=int, default=DEFAULT_COLS)
    p.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    p.add_argument(
        "--green-threshold",
        type=float,
        default=GREEN_THRESHOLD,
        help="vegetation fraction below which a tile is a skip candidate (0 disables skipping)",
    )
    p.add_argument(
        "--uniformity-max",
        type=float,
        default=UNIFORMITY_MAX,
        help="colour spread above which a tile is kept even with no green in it",
    )
    p.add_argument(
        "--gate",
        type=float,
        default=CONFIDENCE_GATE,
        help="confidence below which a tile is escalated to the Second-Opinion agent",
    )
    p.add_argument("--json", action="store_true", help="print only the run state, for piping")
    args = p.parse_args()

    if not args.image.exists():
        raise SystemExit(f"{args.image} not found")

    log = (lambda *a, **k: None) if args.json else print

    img = load_image(args.image)
    log(f"image: {args.image}  {img.size[0]}x{img.size[1]}  crop={args.crop}")

    state = new_run(crop=args.crop)
    classifier = Classifier(model_path=args.model)
    log(f"model:  {len(classifier.class_keys)} classes, crops {classifier.crops}")

    started = time.perf_counter()
    run_pipeline(
        state,
        img,
        classifier,
        cols=args.cols,
        rows=args.rows,
        batch_size=args.batch_size,
        gate=args.gate,
        green_threshold=args.green_threshold,
        uniformity_max=args.uniformity_max,
    )
    total_ms = (time.perf_counter() - started) * 1000

    log(f"scout:  {scout_summary(state)}")
    log(f"diag:   {diagnose_summary(state)}")
    log(f"2nd:    {second_opinion_summary(state)}")
    log(f"spread: {spread_summary(state)}")
    log(f"total:  {total_ms:.0f} ms, status={state.status}")

    payload = state.to_dict()
    problems = validate(payload)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1 if problems else 0

    log(f"\nevents ({len(state.events)}):")
    for event in state.events[:4]:
        log(f"  {event}")
    log(f"  ... {max(len(state.events) - 8, 0)} more ...")
    for event in state.events[-4:]:
        log(f"  {event}")

    log("\ntiles:")
    for tile in state.tiles:
        end = "\n" if tile.x == args.cols - 1 else " "
        # trailing * marks a tile the Second-Opinion agent re-scored
        cell = "----" if tile.skipped else f"{tile.confidence:.2f}"
        cell += "*" if tile.escalated else " "
        log(f"{tile.label[:12]:>13}:{cell}", end=end)

    if problems:
        log("\nFAIL  run state does not match the contract:")
        for problem in problems:
            log(f"  {problem}")
        return 1

    log(f"\nOK    validates against {SCHEMA_PATH.relative_to(REPO_ROOT)}")
    log(f"      status={payload['status']} (plan/verification/report stay null until A6-A8)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Building a run state by hand, so the Consensus policy can be checked without a model.

    from agents.consensus_cases import grid, seen, infected, check

The harness behind `agents/verify_consensus.py`, split out under the 300-line rule. Everything
here constructs inputs or compares outputs; the cases themselves — which are the actual
specification of what the system refuses — live next door where they can be read as a table.
"""


from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.consensus import (  # noqa: E402
    CONTEST_MIN_PCT,
    VISION_CLEAN_PCT,
    VISION_MIN_CONFIDENCE,
    run_consensus,
)
from agents.dispute import dispute, dispute_parts  # noqa: E402
from agents.state import RunState, Tile  # noqa: E402
from agents.vision_verdict import VisionVerdict  # noqa: E402

PASSED = 0
FAILED: list[str] = []


def grid(labels: list[str], crop: str = "tomato") -> RunState:
    """A run state carrying exactly these tile labels, laid out left to right."""
    state = RunState(crop=crop)
    state.tiles = [
        Tile(id=f"t_{i:02d}_00", x=i, y=0, label=label, confidence=0.9)
        for i, label in enumerate(labels)
    ]
    return state


def seen(**kwargs) -> dict:
    """A vision verdict as it is stored — a plain dict, exactly as the Observer writes it."""
    return VisionVerdict(ok=True, **kwargs).to_dict()


def infected(n: int, healthy: int, label: str = "late_blight") -> list[str]:
    return [label] * n + ["healthy"] * healthy


def check(
    name: str,
    state: RunState,
    vision: dict | None,
    *,
    expect_events: list[str] = (),
    forbid_events: list[str] = (),
    expect_labels: list[str] | None = None,
    expect_dispute: bool | None = None,
) -> None:
    global PASSED
    state.vision = vision
    run_consensus(state)
    problems = []

    for fragment in expect_events:
        if not any(fragment in e for e in state.events):
            problems.append(f"missing event containing {fragment!r}")
    for fragment in forbid_events:
        if any(fragment in e for e in state.events):
            problems.append(f"unexpected event containing {fragment!r}")
    if expect_labels is not None:
        got = [t.label for t in state.tiles]
        if got != expect_labels:
            problems.append(f"labels {got} != {expect_labels}")
    if expect_dispute is not None and bool(dispute(state)) != expect_dispute:
        problems.append(f"dispute={bool(dispute(state))}, wanted {expect_dispute}")
    if "consensus.done" not in state.events:
        problems.append("never reached consensus.done")

    if problems:
        FAILED.append(f"{name}: " + "; ".join(problems))
        print(f"FAIL {name}\n       " + "\n       ".join(problems))
        print(f"       events: {[e for e in state.events if e.startswith('consensus')]}")
    else:
        PASSED += 1
        print(f"ok   {name}")


def report() -> int:
    """Print the tally and return a process exit code."""
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED, {PASSED} passed")
        return 1
    print(f"all {PASSED} consensus cases pass")
    return 0

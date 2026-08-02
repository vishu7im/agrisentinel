"""The Consensus decision table, asserted offline.

    .venv/bin/python agents/verify_consensus.py

No network, no ONNX, no PIL, no image. Every case is a hand-written `RunState` and a
hand-written vision dict, which is the whole reason `agents/consensus.py` was written as a pure
function of those two things: the policy that decides whether a farmer is shown a spray
schedule should be checkable in milliseconds, by reading it.

Modelled on `agents/verify_preprocess.py` — same shape, same reason. What it asserts is not
"does it run" but the exact outcome of each row: which label every tile ends up carrying, and
which events were emitted. Events are the contract with the UI, so a wording change that would
silently stop the frontend recognising a refusal fails here.

The boundary cases are the point. 19.9% versus 20.1% affected, confidence 59 versus 61, an
empty grid, a verdict dict missing every key: those are where a policy with four gates goes
wrong, and they are exactly the inputs nobody produces by accident while testing by hand.

The harness is in `agents/consensus_cases.py`.
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
)
from agents.consensus_cases import check, grid, infected, report, seen  # noqa: E402
from agents.dispute import dispute_parts  # noqa: E402
from agents.vision_verdict import VisionVerdict  # noqa: E402


def main() -> int:
    # --- 1. no vision: the run must be untouched -----------------------------------------
    check(
        "1  vision unavailable leaves everything alone",
        grid(infected(4, 6)),
        VisionVerdict(ok=False, error="no_key").to_dict(),
        expect_events=["consensus.skipped.no_vision"],
        forbid_events=["consensus.contested", "consensus.relabel"],
        expect_labels=infected(4, 6),
        expect_dispute=False,
    )
    check(
        "1b vision absent entirely",
        grid(infected(4, 6)),
        None,
        expect_events=["consensus.skipped.no_vision"],
        expect_dispute=False,
    )

    # --- 2. not a crop photograph ---------------------------------------------------------
    #
    # The Scout is the second signal, and it is what keeps our own demo fixtures alive: shown
    # field_tomato_heavy.jpg the real model answers is_crop_field=false and describes "a grid of
    # forty individual leaves", which is correct and must not refuse the run.
    check(
        "2  not a crop AND no plant tissue -> blocks and clears the grid",
        grid(infected(5, 5) + ["skipped_soil"] * 90),
        seen(is_crop_field=False, class_key=None, confidence=90, pct_affected=0),
        expect_events=["consensus.not_crop.10_tiles", "consensus.not_crop"],
        expect_labels=["skipped_not_crop"] * 10 + ["skipped_soil"] * 90,
        expect_dispute=True,
    )
    check(
        "2b not a crop but the frame is full of foliage -> a note, never a refusal",
        grid(infected(5, 5)),
        seen(is_crop_field=False, class_key=None, confidence=100, pct_affected=40),
        expect_events=["consensus.not_field_but_foliage"],
        forbid_events=["consensus.not_crop"],
        expect_labels=infected(5, 5),
        expect_dispute=False,
    )

    # --- 3. the healthy dispute — the case this phase exists for ---------------------------
    check(
        "3a CNN 70% vs a confident clean read -> contested, labels untouched",
        grid(infected(7, 3), crop="potato"),
        seen(crop="potato", class_key="potato__healthy", confidence=95, pct_affected=0),
        expect_events=["consensus.contested.healthy_dispute.late_blight.70pct"],
        expect_labels=infected(7, 3),
        expect_dispute=True,
    )
    check(
        "3a' unnamed crop but 0% affected still contests (the maize case)",
        grid(infected(6, 4), crop="corn"),
        seen(crop=None, class_key=None, confidence=80, pct_affected=0),
        expect_events=["consensus.contested.healthy_dispute"],
        expect_dispute=True,
    )
    check(
        "3b below the materiality gate -> note only, plan ships",
        grid(infected(1, 9)),
        seen(crop="tomato", class_key="tomato__healthy", confidence=95, pct_affected=0),
        expect_events=["consensus.vision_clean.minor.10pct"],
        forbid_events=["consensus.contested"],
        expect_dispute=False,
    )
    check(
        "3c an unsure clean read never contests",
        grid(infected(7, 3)),
        seen(crop="tomato", class_key="tomato__healthy", confidence=40, pct_affected=0),
        expect_events=["consensus.low_confidence_vision.clean.40pct"],
        forbid_events=["consensus.contested"],
        expect_dispute=False,
    )
    check(
        "3d both clean -> agreement, no plan either way",
        grid(["healthy"] * 10),
        seen(crop="tomato", class_key="tomato__healthy", confidence=95, pct_affected=0),
        expect_events=["consensus.agree.healthy"],
        expect_dispute=False,
    )

    # --- 4/5. same disease, different disease ---------------------------------------------
    check(
        "4  agreement on the disease changes nothing",
        grid(infected(5, 5)),
        seen(crop="tomato", class_key="tomato__late_blight", confidence=90, pct_affected=50),
        expect_events=["consensus.agree.late_blight"],
        expect_labels=infected(5, 5),
        expect_dispute=False,
    )
    check(
        "5  different disease -> infected tiles relabelled, healthy untouched",
        grid(infected(4, 6, "yellow_leaf_curl_virus")),
        seen(
            crop="tomato",
            class_key="tomato__septoria_leaf_spot",
            confidence=85,
            pct_affected=35,
        ),
        expect_events=[
            "consensus.relabel.yellow_leaf_curl_virus_to_septoria_leaf_spot.4_tiles",
            "consensus.tile.t_00_00",
        ],
        expect_labels=infected(4, 6, "septoria_leaf_spot"),
        expect_dispute=False,
    )
    check(
        "5b an unsure rename is logged, not applied",
        grid(infected(4, 6, "yellow_leaf_curl_virus")),
        seen(
            crop="tomato",
            class_key="tomato__septoria_leaf_spot",
            confidence=50,
            pct_affected=35,
        ),
        expect_events=["consensus.low_confidence_vision.septoria_leaf_spot.50pct"],
        expect_labels=infected(4, 6, "yellow_leaf_curl_virus"),
        expect_dispute=False,
    )

    # --- 6. nothing usable to fuse --------------------------------------------------------
    check(
        "6a a disease outside the fourteen classes is recorded, not applied",
        grid(infected(4, 6)),
        seen(crop="tomato", class_key=None, off_enum="anthracnose", confidence=90, pct_affected=30),
        expect_events=["consensus.no_disease_opinion.anthracnose"],
        expect_labels=infected(4, 6),
        expect_dispute=False,
    )
    check(
        "6b a disease of another crop is scoped out",
        grid(infected(4, 6), crop="tomato"),
        seen(crop="corn", class_key="corn__common_rust", confidence=90, pct_affected=30),
        expect_events=["consensus.crop_scoped_out.corn.common_rust"],
        expect_labels=infected(4, 6),
        expect_dispute=False,
    )

    # --- 7. vision alone sees disease -----------------------------------------------------
    check(
        "7  a clean scan is never turned into a refusal by vision alone",
        grid(["healthy"] * 10),
        seen(crop="tomato", class_key="tomato__late_blight", confidence=95, pct_affected=40),
        expect_events=["consensus.vision_only.late_blight"],
        forbid_events=["consensus.contested"],
        expect_labels=["healthy"] * 10,
        expect_dispute=False,
    )

    # --- 8. the percentage-gap note -------------------------------------------------------
    check(
        "8  a 30-point gap between the two estimates is noted",
        grid(infected(8, 2)),
        seen(crop="tomato", class_key="tomato__late_blight", confidence=90, pct_affected=20),
        expect_events=["consensus.pct_gap.60pp", "consensus.agree.late_blight"],
        expect_dispute=False,
    )

    # --- boundaries: where a four-gate policy actually goes wrong --------------------------
    # 20% of the grid exactly. CONTEST_MIN_PCT is >=, so this contests and 19% does not.
    check(
        f"B1 exactly {CONTEST_MIN_PCT}% affected contests",
        grid(infected(2, 8)),
        seen(crop="tomato", class_key="tomato__healthy", confidence=90, pct_affected=0),
        expect_events=["consensus.contested"],
        expect_dispute=True,
    )
    check(
        "B2 one tile under the gate does not",
        grid(infected(19, 81)),
        seen(crop="tomato", class_key="tomato__healthy", confidence=90, pct_affected=0),
        forbid_events=["consensus.contested"],
        expect_dispute=False,
    )
    check(
        f"B3 confidence exactly {VISION_MIN_CONFIDENCE} contests",
        grid(infected(5, 5)),
        seen(class_key="tomato__healthy", confidence=VISION_MIN_CONFIDENCE, pct_affected=0),
        expect_events=["consensus.contested"],
        expect_dispute=True,
    )
    check(
        "B4 one point under does not",
        grid(infected(5, 5)),
        seen(class_key="tomato__healthy", confidence=VISION_MIN_CONFIDENCE - 1, pct_affected=0),
        forbid_events=["consensus.contested"],
        expect_dispute=False,
    )
    check(
        f"B5 {VISION_CLEAN_PCT}% reported by vision still counts as clean",
        grid(infected(5, 5)),
        seen(class_key="tomato__late_blight", confidence=90, pct_affected=VISION_CLEAN_PCT),
        expect_events=["consensus.contested"],
        expect_dispute=True,
    )
    check(
        "B6 one point over is a real disease reading, so it fuses instead",
        grid(infected(5, 5, "yellow_leaf_curl_virus")),
        seen(class_key="tomato__late_blight", confidence=90, pct_affected=VISION_CLEAN_PCT + 1),
        expect_events=["consensus.relabel"],
        forbid_events=["consensus.contested"],
        expect_dispute=False,
    )
    check(
        "B7 an empty grid decides nothing and still finishes",
        grid([]),
        seen(class_key="tomato__healthy", confidence=95, pct_affected=0),
        expect_events=["consensus.agree.healthy"],
        forbid_events=["consensus.contested"],
        expect_dispute=False,
    )
    check(
        "B8 a grid of skipped tiles is not a healthy field",
        grid(["skipped_soil"] * 10),
        seen(class_key="tomato__healthy", confidence=95, pct_affected=0),
        forbid_events=["consensus.contested", "consensus.relabel"],
        expect_labels=["skipped_soil"] * 10,
        expect_dispute=False,
    )
    check(
        "B9 a verdict dict missing every key must not refuse anything",
        grid(infected(7, 3)),
        {"ok": True},
        forbid_events=["consensus.contested", "consensus.not_crop", "consensus.relabel"],
        expect_labels=infected(7, 3),
        expect_dispute=False,
    )

    # --- dispute_parts round-trips the event it is given -----------------------------------
    reason, label, pct = dispute_parts("consensus.contested.healthy_dispute.late_blight.70pct")
    assert (reason, label, pct) == ("healthy_dispute", "late_blight", 70.0), (reason, label, pct)
    assert dispute_parts("consensus.not_crop")[0] == "not_crop"
    assert dispute_parts("consensus.contested.x")[2] == 0.0, "a malformed tail must not raise"
    print("ok   dispute_parts round-trips, including a malformed tail")

    return report()


if __name__ == "__main__":
    sys.exit(main())

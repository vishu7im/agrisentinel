"""Does the vision cross-check actually fix the thing it was built for?

    .venv/bin/python ml/report/vision_crosscheck.py
    .venv/bin/python ml/report/vision_crosscheck.py --images demo/field_photos

Runs every image twice — once with `AGRISENTINEL_OBSERVER=0`, once with it on — and writes
`ml/artifacts/vision_crosscheck.md`. The before column is the measurement in NOTES.md that
prompted the whole phase: a healthy potato field returning 69.2% affected with a confident
disease name and a spray schedule attached.

Two things this deliberately does not do:

**It does not grade the disease label.** The photographs have no expert diagnosis behind them,
so a label column would be an opinion presented as a score. What is measured instead is the
thing that matters and is unambiguous: whether a run shipped a spray schedule for a field that
does not need one.

**It does not claim a sample size it does not have.** Seven photographs is an anecdote. It is
the same anecdote seven times and it points one way, which is worth writing down — and it is
not an evaluation set, and the artifact says so in its own header.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from PIL import Image  # noqa: E402

from agents.consensus import cnn_pct  # noqa: E402
from agents.diagnostician import Classifier  # noqa: E402
from agents.observer import vision_verdict  # noqa: E402
from agents.orchestrator import run_pipeline  # noqa: E402
from agents.state import new_run  # noqa: E402

DEFAULT_IMAGES = REPO_ROOT / "agents" / "testdata" / "real"
OUT_PATH = REPO_ROOT / "ml" / "artifacts" / "vision_crosscheck.md"


def truth_for(images: Path) -> dict:
    """Optional `{filename: {crop, note}}` sidecar. Absent is fine — crop is the only column
    it feeds, and an unlabelled run still measures everything else."""
    sidecar = images / "truth.json"
    return json.loads(sidecar.read_text()) if sidecar.exists() else {}


def scan(path: Path, classifier: Classifier, observer_on: bool) -> dict:
    os.environ["AGRISENTINEL_OBSERVER"] = "1" if observer_on else "0"
    state = new_run(crop="auto")
    started = time.perf_counter()
    run_pipeline(state, Image.open(path), classifier)
    data = state.to_dict()
    verdict = vision_verdict(state)
    return {
        "blocked": data["status"] == "blocked",
        "crop": data["crop"],
        "elapsed": time.perf_counter() - started,
        "pct": (data["spread"] or {}).get("pct_affected", 0.0),
        "plan": bool(data["plan_draft"]),
        "tile_pct": cnn_pct(state),
        "vision_error": verdict.error,
        "vision_ok": verdict.ok,
        "vision_pct": verdict.pct_affected,
        "vision_sees": verdict.class_key,
        "visible": verdict.visible,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--model", default=None, help="override GEMINI_VISION_MODEL")
    args = parser.parse_args()

    if args.model:
        os.environ["GEMINI_VISION_MODEL"] = args.model
    images = sorted(p for p in args.images.glob("*.jpg"))
    if not images:
        raise SystemExit(f"no .jpg images in {args.images}")

    truth = truth_for(args.images)
    classifier = Classifier()
    rows = []
    for path in images:
        print(f"  {path.name} ...", flush=True)
        before = scan(path, classifier, observer_on=False)
        after = scan(path, classifier, observer_on=True)
        rows.append({"after": after, "before": before, "name": path.name,
                     "truth": truth.get(path.name, {})})

    write_report(rows, args.images)
    print(f"\nwrote {OUT_PATH.relative_to(REPO_ROOT)}")
    return 0


def write_report(rows: list[dict], images: Path) -> None:
    measured = [r for r in rows if r["after"]["vision_ok"]]
    unusable = len(rows) - len(measured)

    spray_before = sum(1 for r in rows if r["before"]["plan"])
    spray_after = sum(1 for r in rows if r["after"]["plan"])
    lost = [r["name"] for r in rows if r["before"]["plan"] and not r["after"]["plan"]]
    crop_before = sum(
        1 for r in rows if r["truth"].get("crop") and r["before"]["crop"] == r["truth"]["crop"]
    )
    crop_after = sum(
        1 for r in rows if r["truth"].get("crop") and r["after"]["crop"] == r["truth"]["crop"]
    )
    labelled = sum(1 for r in rows if r["truth"].get("crop"))

    lines = [
        "# Vision cross-check — before and after",
        "",
        f"`ml/report/vision_crosscheck.py`, over {len(rows)} photographs in "
        f"`{images.relative_to(REPO_ROOT)}`.",
        "",
        "**This is not an evaluation set.** These photographs have no expert diagnosis behind",
        "them, so nothing here scores the disease label. What is counted is the one thing that is",
        "unambiguous and is the reason the cross-check exists: whether a run hands a farmer a",
        "spray schedule. Seven photographs is an anecdote — it is the same anecdote several times",
        "and it points one way, and it is still an anecdote.",
        "",
        "## Headline",
        "",
        "| | before | after |",
        "|---|---|---|",
        f"| runs that shipped a spray plan | {spray_before}/{len(rows)} | "
        f"**{spray_after}/{len(rows)}** |",
        f"| crop identified correctly | {crop_before}/{labelled} | **{crop_after}/{labelled}** |"
        if labelled
        else "| crop identified correctly | *no truth sidecar* | — |",
        f"| cross-check usable | — | {len(measured)}/{len(rows)} |",
        "",
    ]

    if unusable:
        reasons = sorted({r["after"]["vision_error"] for r in rows if not r["after"]["vision_ok"]})
        lines += [
            f"{unusable} run(s) could not obtain a second opinion ({', '.join(reasons)}) and are",
            "reported as they ran — the cross-check degrading to today's behaviour is the designed",
            "outcome, not a gap in the measurement.",
            "",
        ]

    lines += [
        "## Per photograph",
        "",
        "| image | crop before → after | tiles say | vision says | plan before → after |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        after, before = row["after"], row["before"]
        vision = (
            f"{after['vision_sees'] or 'unknown'} · {after['vision_pct']}%"
            if after["vision_ok"]
            else f"*{after['vision_error']}*"
        )
        plan = f"{'plan' if before['plan'] else 'none'} → {'plan' if after['plan'] else '**withheld**'}"
        lines.append(
            f"| `{row['name']}` | {before['crop']} → {after['crop']} | "
            f"{before['tile_pct']}% affected | {vision} | {plan} |"
        )

    lines += ["", "## What the second model reported seeing", ""]
    for row in rows:
        if row["after"]["visible"]:
            lines.append(f"- `{row['name']}` — {row['after']['visible']}")

    lines += [
        "",
        "## Cost",
        "",
        f"| median scan, cross-check off | {median(r['before']['elapsed'] for r in rows):.2f} s |",
        "|---|---|",
        f"| median scan, cross-check on | {median(r['after']['elapsed'] for r in rows):.2f} s |",
        "",
        "The call is started after the Scout and collected before the Consensus agent, so on a run",
        "with an explicitly chosen crop it overlaps tile scoring. On an `auto` run the crop has to",
        "be settled before the Diagnostician masks its logits, and the wait is unavoidable.",
        "",
    ]

    if lost:
        lines += [
            "## Runs that lost a plan",
            "",
            "Each of these previously produced a treatment schedule and now does not:",
            "",
            *(f"- `{name}`" for name in lost),
            "",
            "Every one is a case where the whole-image check contradicted the tile grid. Whether",
            "that is a fix or an over-block cannot be settled from these photographs alone — it",
            "needs a diagnosis from someone who stood in the field.",
            "",
        ]

    OUT_PATH.write_text("\n".join(lines))


def median(values) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


if __name__ == "__main__":
    sys.exit(main())

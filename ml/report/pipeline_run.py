"""End-to-end field scan: what the whole pipeline costs, and whether it gets the grid right.

    .venv/bin/python ml/report/pipeline_run.py

ml/artifacts/latency.json already holds per-tile ONNX latency measured in isolation. That
number answers "how fast is the model" and nobody asked it. The question on the slide is how
long a farmer waits between pressing upload and reading a plan, which includes tiling, the
green mask, a second inference pass over the escalated tiles, DBSCAN, retrieval and — on the
online path — two or three LLM round trips that dwarf everything else.

**Timings come from instrumenting the real orchestrator, not from re-sequencing the agents
here.** The stage functions are wrapped in `agents.orchestrator`'s own namespace and then
`run_pipeline` is called normally, so this file cannot drift into being a second, subtly
different execution order that happens to be the one we benchmarked.

It also scores the run. agents/testdata/*.truth.txt gives the true label of every cell in each
synthetic mosaic, so the same pass that measures the clock measures whether the grid came out
right. Be clear about what that accuracy is worth: the mosaics are built from test-split
images, so the tiles are still studio photographs of detached leaves. This checks the tiling,
skip-mask, batching and second-opinion path end to end on known ground truth. It is not a
lab-to-field measurement — that is ml/report/field_gap.py, and it needs real photographs.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from agents import llm, orchestrator  # noqa: E402
from agents.diagnostician import Classifier  # noqa: E402
from agents.state import new_run  # noqa: E402
from agents.tiling import load_image  # noqa: E402

TESTDATA = REPO_ROOT / "agents" / "testdata"
ARTIFACTS = REPO_ROOT / "ml" / "artifacts"

# The stages as the orchestrator names them, in running order.
STAGES = ("run_scout", "run_diagnostician", "run_second_opinion", "run_spread",
          "run_agronomist", "run_verifier", "run_planner", "run_reporter")


def crop_of(path: Path) -> str:
    """field_tomato_late_blight.jpg -> tomato. Bare-soil fixtures get the demo default."""
    for crop in ("tomato", "potato", "corn"):
        if crop in path.stem:
            return crop
    return "tomato"


def load_truth(path: Path) -> dict[str, str]:
    lines = (line.split() for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return {parts[0]: parts[1] for parts in lines if len(parts) >= 2}


class Timed:
    """Wraps the orchestrator's stage functions and records how long each spent."""

    def __init__(self):
        self.ms: dict[str, float] = {}
        self._originals: dict[str, object] = {}

    def __enter__(self):
        for name in STAGES:
            original = getattr(orchestrator, name)
            self._originals[name] = original
            setattr(orchestrator, name, self._wrap(name, original))
        return self

    def __exit__(self, *exc):
        for name, original in self._originals.items():
            setattr(orchestrator, name, original)
        return False

    def _wrap(self, name: str, fn):
        def wrapped(*args, **kwargs):
            started = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                # Accumulated, not overwritten: the Agronomist and Verifier each run more than
                # once when a draft is sent back, and the cost of that loop is the point.
                self.ms[name] = self.ms.get(name, 0.0) + (time.perf_counter() - started) * 1000
        return wrapped


def grade(state, truth: dict[str, str]) -> dict:
    """Tile-level agreement with the mosaic's ground truth."""
    skip_right = correct = scored = infected_hit = infected_total = false_alarm = 0
    for tile in state.tiles:
        want = truth.get(tile.id)
        if want is None:
            continue
        want_skip = want.startswith("skipped")
        skip_right += want_skip == tile.skipped
        if want_skip or tile.skipped:
            continue
        scored += 1
        correct += tile.label == want
        if want != "healthy":
            infected_total += 1
            infected_hit += tile.label != "healthy"
        elif tile.label != "healthy":
            false_alarm += 1
    return {
        "tiles": len(state.tiles),
        "skip_agreement": round(skip_right / max(len(truth), 1), 4),
        "scored": scored,
        "label_accuracy": round(correct / scored, 4) if scored else None,
        # Missing an infected tile and inventing one are different mistakes with different
        # consequences, so they are counted separately rather than averaged into accuracy.
        "infected_recall": round(infected_hit / infected_total, 4) if infected_total else None,
        "false_alarms": false_alarm,
    }


def scan(path: Path, classifier: Classifier, offline: bool) -> dict:
    truth_path = path.with_suffix(".truth.txt")
    img = load_image(path)
    state = new_run(crop=crop_of(path))

    original_available = llm.available
    if offline:
        llm.available = lambda: False  # extractive drafter, no network, venue-with-no-wifi path
    try:
        started = time.perf_counter()
        with Timed() as timed:
            orchestrator.run_pipeline(state, img, classifier)
        total_ms = (time.perf_counter() - started) * 1000
    finally:
        llm.available = original_available

    vision_ms = sum(timed.ms.get(s, 0.0) for s in STAGES[:4])
    row = {
        "image": path.name,
        "crop": state.crop,
        "offline": offline,
        "status": state.status,
        "verification": (state.verification or {}).get("status"),
        "escalated": sum(1 for t in state.tiles if t.escalated),
        "total_ms": round(total_ms, 1),
        "vision_ms": round(vision_ms, 1),
        "language_ms": round(total_ms - vision_ms, 1),
        "stages_ms": {s.removeprefix("run_"): round(timed.ms.get(s, 0.0), 1) for s in STAGES},
        "events": len(state.events),
    }
    if truth_path.exists():
        row.update(grade(state, load_truth(truth_path)))
    return row


def render_md(rows: list[dict]) -> str:
    def table(subset: list[dict]) -> str:
        head = "| image | tiles | escalated | vision ms | language ms | total ms | tile acc |\n|---|---:|---:|---:|---:|---:|---:|"
        body = "\n".join(
            f"| {r['image']} | {r.get('tiles', 0)} | {r['escalated']} | {r['vision_ms']:,.0f} | "
            f"{r['language_ms']:,.0f} | {r['total_ms']:,.0f} | "
            f"{'—' if r.get('label_accuracy') is None else format(r['label_accuracy'], '.3f')} |"
            for r in subset
        )
        return f"{head}\n{body}"

    offline = [r for r in rows if r["offline"]]
    online = [r for r in rows if not r["offline"]]
    parts = ["# End-to-end field scan\n"]
    parts.append(
        "Whole pipeline on a CPU-only laptop: tile, mask, classify, escalate, cluster, retrieve, "
        "draft, verify, schedule, brief. *vision* is Scout through Spread; *language* is "
        "Agronomist through Reporter.\n"
    )
    if offline:
        med = statistics.median(r["total_ms"] for r in offline)
        parts.append(f"## Offline (extractive drafter, no network)\n\n{table(offline)}\n")
        parts.append(f"Median end-to-end **{med / 1000:.2f} s**. This is the demo-day path.\n")
    if online:
        med = statistics.median(r["total_ms"] for r in online)
        parts.append(f"## Online (Gemini drafting)\n\n{table(online)}\n")
        parts.append(
            f"Median end-to-end **{med / 1000:.2f} s**, and the language column is essentially "
            "all of it — the vision half of the system is a rounding error against one LLM round "
            "trip, and a rewrite loop pays for a second.\n"
        )
    graded = [r for r in rows if r.get("label_accuracy") is not None]
    if graded:
        acc = statistics.mean(r["label_accuracy"] for r in graded)
        skip = statistics.mean(r["skip_agreement"] for r in graded)
        alarms = sum(r["false_alarms"] for r in graded)
        parts.append(
            f"## Grid correctness\n\nAcross {len(graded)} labelled mosaics: **{acc:.1%}** of scored "
            f"tiles carry the right label, skip-mask agrees with ground truth on **{skip:.1%}** of "
            f"cells, {alarms} healthy tile(s) called infected.\n\n"
            "These mosaics are stitched from test-split images, so the cells are studio "
            "photographs. This grades the tiling, mask and escalation path on known ground truth; "
            "it says nothing about real field imagery. See lab_vs_field.md.\n"
        )
    return "\n".join(parts)


def build(images: list[Path], modes: list[bool]) -> list[dict]:
    classifier = Classifier()
    rows = []
    for offline in modes:
        for path in images:
            row = scan(path, classifier, offline)
            rows.append(row)
            print(f"  {'offline' if offline else 'online ':<8} {path.name:<34} "
                  f"{row['total_ms']:>8,.0f} ms  status={row['status']}")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "pipeline_scan.json").write_text(json.dumps(rows, indent=2) + "\n")
    (ARTIFACTS / "pipeline_scan.md").write_text(render_md(rows), encoding="utf-8")
    print(f"\nwrote {ARTIFACTS}/pipeline_scan.json, .md")
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--images", nargs="*", type=Path, default=sorted(TESTDATA.glob("field_*.jpg")))
    p.add_argument("--online", action="store_true", help="also time the Gemini drafting path")
    args = p.parse_args()

    if not args.images:
        raise SystemExit(f"no field images in {TESTDATA}")
    modes = [True] + ([False] if args.online else [])
    build(list(args.images), modes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

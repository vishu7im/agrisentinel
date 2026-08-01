"""Spread Analyst Agent — per-tile labels in, field-level severity out.

    from agents.spread import run_spread
    run_spread(state)          # writes state.spread, emits spread.done

This is the agent that makes the reframe real. A classifier tells you a leaf is sick; this
tells you how much of the field is sick, whether it is one advancing front or scattered
noise, which way it is heading, and roughly what it costs. None of those four numbers exist
in a leaf app, and all four come from the tile grid the Scout laid out.

It reads only `state.tiles`. No image, no model, no network — which is why it runs in under a
millisecond and why it can be re-run against a stored run state without the original photo.

Four outputs, and the reasoning behind each:

**pct_affected** — infected tiles over *scored* tiles. Skipped soil and sky are not part of
the field, so counting them in the denominator would silently flatter every number. The same
denominator is why this agent refuses to report below MIN_SCORED_TILES: a ratio taken over one
or two tiles is not a field measurement, and it is the one place where a single bad tile can
turn into a headline number.

**clusters** — DBSCAN over infected tile coordinates, eps 1.5 and min_samples 2. On an
integer grid eps 1.5 reaches the eight surrounding cells (distance 1 or 1.414) and nothing
further, so a cluster is a contiguous blob of infection. min_samples 2 means a lone infected
tile is *noise*, not a cluster, and that is deliberate: one isolated tile is as likely to be
a misclassification as a real focus, and calling it a cluster would put a number on the
screen that a farmer would walk out to check. Scattered tiles are still reported, through the
spread.scattered event and through pct_affected, which the cluster count never suppresses.

**direction** — bearing from the centre of the scored field to the centre of the infection.
Only meaningful when the infection is actually off-centre; see MIN_DISPLACEMENT.

**est_yield_loss_pct** — pct_affected times a per-disease weight from severity_weights.json.
The weights are midpoints of published ranges and that file says so at length. Mixed-disease
fields get the tile-count-weighted mean of the weights present, so half a field of late
blight and half of leaf mold lands between the two rather than on whichever label happened to
be first.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from sklearn.cluster import DBSCAN

from agents.state import RunState

WEIGHTS_PATH = Path(__file__).resolve().parent / "severity_weights.json"

# eps 1.5 on an integer grid = the 8 neighbouring cells, no further. min_samples 2 counts the
# point itself, so two touching tiles form a cluster and a lone tile is noise.
DBSCAN_EPS = 1.5
DBSCAN_MIN_SAMPLES = 2

# How far the infection centre must sit from the field centre, in tile widths, before a
# compass bearing means anything. Infection spread evenly across the whole field puts the two
# centres on top of each other, and the bearing between them is then pure floating-point
# noise — it would point somewhere confident and arbitrary. A quarter of a tile is small
# enough to catch a genuine lean and large enough to reject that.
MIN_DISPLACEMENT = 0.25

# A percentage needs a denominator that means something. Found in A5 integration testing: a
# photograph of bare soil had exactly one tile survive the Scout's mask — vegetation 0.0000,
# uniformity 0.0227 against a 0.022 threshold — which the model then labelled
# yellow_leaf_curl_virus at 0.10 confidence. One infected tile over one scored tile is 100%
# affected, and the field reported "100% affected, 70% yield loss" for a picture of dirt.
#
# A3 called a false keep "the harmless direction" because it costs one low-confidence
# prediction that A5 escalates anyway. That was true of the Diagnostician and false of this
# agent: a ratio amplifies a single bad tile in a way a per-tile label never does. Below this
# many scored tiles there is no field to measure, and saying so is the honest output.
MIN_SCORED_TILES = 3

# Above the floor but still a thin slice of the frame, the numbers are real but shaky — a
# mostly-sky photo with four crop tiles in the corner. Reported, with the sample size on the
# event log so the UI can caveat it rather than the agent silently suppressing it.
THIN_SAMPLE_FRACTION = 0.25

COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

EMPTY_SPREAD = {
    "pct_affected": 0.0,
    "clusters": 0,
    "direction": None,
    "est_yield_loss_pct": 0.0,
    "cluster_centroids": [],
}


def load_weights(path: Path = WEIGHTS_PATH) -> tuple[dict[str, float], float]:
    table = json.loads(path.read_text(encoding="utf-8"))
    return table["weights"], float(table["_default"])


def bearing_to_compass(degrees: float) -> str:
    """Bearing in degrees clockwise from north to one of eight points."""
    return COMPASS[int((degrees + 22.5) // 45) % 8]


def centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def direction_between(
    origin: tuple[float, float],
    target: tuple[float, float],
    min_displacement: float = MIN_DISPLACEMENT,
) -> str | None:
    """Compass bearing from origin to target, or None if they are effectively the same point.

    Tile y increases SOUTHWARD — that is stated in the schema and it is the one sign error
    that would flip every bearing on the screen without anything looking broken. So the
    northward component is the negative of the y displacement.
    """
    east = target[0] - origin[0]
    north = -(target[1] - origin[1])
    if math.hypot(east, north) < min_displacement:
        return None
    return bearing_to_compass(math.degrees(math.atan2(east, north)) % 360.0)


def cluster_infected(
    coords: list[tuple[int, int]],
    eps: float = DBSCAN_EPS,
    min_samples: int = DBSCAN_MIN_SAMPLES,
) -> tuple[list[dict], int]:
    """DBSCAN over infected tile coordinates -> (centroids in cluster order, noise count).

    Points are passed in reading order, so cluster ids come out in the order the blobs are
    first encountered top-left to bottom-right — stable across runs, and the same order the
    reference run in contract/mock_run.json uses.
    """
    if not coords:
        return [], 0
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit(np.array(coords, dtype=float)).labels_

    centroids = []
    for cluster_id in sorted({int(label) for label in labels if label >= 0}):
        members = [c for c, label in zip(coords, labels) if label == cluster_id]
        cx, cy = centroid(members)
        centroids.append({"x": round(cx, 2), "y": round(cy, 2), "size": len(members)})
    return centroids, int((labels < 0).sum())


def severity_weight(crop: str, labels: list[str]) -> tuple[float, list[str]]:
    """Tile-count-weighted mean weight across the infected labels, plus any that fell back.

    Averaging over tiles rather than over distinct diseases is the point: one stray septoria
    tile in a field of late blight should barely move the number.
    """
    weights, default = load_weights()
    total, unknown = 0.0, []
    for label in labels:
        key = f"{crop}__{label}"
        if key in weights:
            total += weights[key]
        else:
            total += default
            unknown.append(key)
    return total / len(labels), sorted(set(unknown))


def run_spread(state: RunState) -> RunState:
    """Compute the four severity numbers and write them into state.spread."""
    scored = state.scored_tiles
    if len(scored) < MIN_SCORED_TILES:
        # Too little crop in frame to compute a field statistic. Zeroes rather than null,
        # because the schema requires all four keys and "we could not measure this" is better
        # expressed as an honest zero plus an event than as a confident number from one tile.
        state.apply(
            "spread.no_field" if not scored else f"spread.insufficient_field.{len(scored)}_tiles",
            spread=dict(EMPTY_SPREAD),
        )
        state.apply("spread.done")
        return state

    infected = [t for t in scored if t.label != "healthy"]
    pct_affected = 100.0 * len(infected) / len(scored)

    coords = [(t.x, t.y) for t in infected]
    centroids, noise = cluster_infected(coords)

    if infected:
        weight, unknown = severity_weight(state.crop, [t.label for t in infected])
        direction = direction_between(
            centroid([(t.x, t.y) for t in scored]),
            centroid([(float(x), float(y)) for x, y in coords]),
        )
    else:
        weight, unknown, direction = 0.0, [], None

    spread = {
        "pct_affected": round(pct_affected, 1),
        "clusters": len(centroids),
        "direction": direction,
        "est_yield_loss_pct": round(min(pct_affected * weight, 100.0), 1),
        "cluster_centroids": centroids,
    }

    # Events before the result, so the timeline reads as reasoning rather than announcement.
    if state.tiles and len(scored) < THIN_SAMPLE_FRACTION * len(state.tiles):
        state.apply(f"spread.thin_sample.{len(scored)}_tiles")
    if unknown:
        state.apply(f"spread.weight_default.{len(unknown)}_labels")
    if not infected:
        state.apply("spread.clean_field")
    if noise:
        state.apply(f"spread.scattered.{noise}_tiles")
    if infected and direction is None:
        state.apply("spread.direction.uniform")

    state.apply(f"spread.clusters.{len(centroids)}")
    state.apply("spread.done", spread=spread)
    return state


def spread_summary(state: RunState) -> str:
    s = state.spread
    if not s:
        return "spread not computed"
    where = s["direction"] or "no dominant direction"
    return (
        f"{s['pct_affected']:.1f}% affected | {s['clusters']} cluster(s) | "
        f"{where} | ~{s['est_yield_loss_pct']:.1f}% yield at risk"
    )

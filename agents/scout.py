"""Scout Agent — lay out the grid, and refuse to diagnose tiles that hold no crop.

    from agents.scout import run_scout
    run_scout(state, img)          # writes state.tiles, emits scout.done

A field photo is mostly not crop. Bare soil between rows, an irrigation channel, sky above
the horizon, a shed. Handing those to a classifier trained only on leaves guarantees a
confident wrong answer — dry soil looks a lot like a late-blight lesion to a model that has
never been shown soil. Worse, junk tiles land in the denominator and quietly deflate
pct_affected. So the Scout marks them skipped and the Diagnostician never sees them.

**Skipping is asymmetric and the whole design follows from that.** A false keep costs one
low-confidence prediction, which A5 escalates anyway. A false skip silently deletes a
diagnosis — and the tiles most likely to be falsely skipped are the severely diseased ones,
because badly blighted foliage is brown, not green. That is not hypothetical: the first
version of this file used a plain Excess Green threshold and dropped a fully necrotic corn
tile that scored 0.001 vegetation, indistinguishable from soil on colour alone.

So a tile is skipped only when **two independent tests agree**:

1. *No vegetation* — Excess Green, ExG = 2g - r - b on chromatic-normalised RGB
   (Woebbecke et al., 1995), the standard cheap vegetation index in agronomy.
2. *Positively looks like one uniform surface* — low spread in the chromatic coordinates.
   Bare soil and sky are a single material filling the frame. A dead leaf is still a leaf
   against a differently-coloured background, so its colour distribution stays bimodal even
   when nothing in it is green. This is what rescues the necrotic tile above: it scores
   0.0007 on test 1 and 0.032 on test 2, against 0.014 for real soil.

Both thresholds were re-measured in A4 against 148 tiles of known ground truth, after the
heavy fixture false-skipped two blighted tiles. The numbers moved; the constants carry the
measurements. The lesson worth keeping is that a threshold justified by one argument and
validated on one fixture is a threshold that has not been tested.

Caveat worth carrying into A9: UNIFORMITY_MAX is calibrated against the synthetic soil in
`ml/data/make_field.py`, which is monochromatic noise and therefore more uniform than real
earth. Stones, shadows and wet patches all push real soil *up* past the threshold — meaning
the error it drifts toward is a false keep, which is the harmless direction. Re-measure it on
demo/field_photos/ before claiming a number for it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from agents.state import RunState, Tile
from agents.tiling import DEFAULT_COLS, DEFAULT_ROWS, tile_boxes

# Below this fraction of vegetation pixels a tile becomes a skip *candidate* — it still has to
# fail the uniformity test below before it is actually dropped.
#
# Read that sentence carefully, because the first version of this file got it wrong. 0.15 was
# the original value, chosen as "how green must a tile be to be worth scoring". That is a
# different question, and using it here cost two heavily blighted tiles on the A4 heavy
# fixture: they scored 0.129, meaning 13% of their pixels read as vegetation, and were still
# called empty. Measured across every fixture, background tiles sit at 0.0000-0.0002 and
# foliage tiles start at 0.0007 — the whole decision lives two orders of magnitude below 0.15.
#
# 0.05 is set well above where synthetic backgrounds actually land, with room for real soil
# that has weeds and crop residue in it. Anything it gets wrong on real photos it gets wrong
# by keeping a soil tile, which is the direction that costs one low-confidence prediction
# instead of a lost diagnosis.
GREEN_THRESHOLD = 0.05

# Above this spread in chromatic coordinates, the tile holds more than one material and is
# kept regardless of how little green is in it.
#
# Measured over 148 tiles: background 0.0125-0.0143, foliage 0.0084-0.2011. Those OVERLAP —
# a flat, evenly-lit healthy tile can be more uniform than soil. So this test cannot stand on
# its own; it is only ever the second half of an AND, rescuing dead foliage that the
# vegetation test alone would drop. 0.022 sits above the whole measured background range with
# ~1.5x headroom.
UNIFORMITY_MAX = 0.022

# ExG cut-off for a single pixel. Above zero is "greener than neutral"; 0.05 gives headroom
# so a grey-brown pixel with sensor noise doesn't flicker into the vegetation class.
EXG_PIXEL_CUTOFF = 0.05

# Sky has to be blue by a margin, not by a rounding error, and bright with it. Purely
# cosmetic — the UI greys both labels identically — but "skipped_sky" along the bottom row of
# a field photo is the kind of detail that makes a demo audience stop trusting the rest.
SKY_BLUE_MARGIN = 8.0
SKY_MIN_BRIGHTNESS = 120.0

# Statistics are computed on a downscaled copy. A ratio over thousands of pixels does not
# need full resolution, and this makes the Scout's cost independent of camera megapixels.
MASK_SIZE = 64

# Share of the grid this agent has to keep before the rest of the pipeline treats "there is
# plant tissue in this photograph" as settled. Two later agents ask that question — the
# Observer, deciding whether to trust a crop name, and the Consensus agent, deciding whether to
# stop a run — and both need the same answer, so it lives here with the measurement that
# produced it rather than in either of them.
#
# The Scout is good at this and the numbers say so: 0.03 on a photograph of bare soil,
# 0.62-1.00 on every real photograph and every mosaic tested. What it is being used for is to
# be the second signal against a whole-image model's `is_crop_field`, which answers a subtly
# different question — "is this a *field*". Shown `field_tomato_heavy.jpg` that model answered
# false and described "a grid of forty individual leaves against plain backgrounds", which is
# exactly what the fixture is. It is right, and acting on it alone would refuse three of our
# own demo fixtures and every laboratory photograph anyone tries. A mosaic of leaves is not a
# field and is still perfectly diagnosable; only when both signals say the frame is empty is
# there nothing to look at.
SCOUT_TISSUE_MIN = 0.25


@dataclass(frozen=True)
class TileStats:
    vegetation: float  # fraction of pixels passing the Excess Green test
    uniformity: float  # mean per-channel SD of the chromatic coordinates; low = one surface
    mean_rgb: tuple[float, float, float]


def tile_stats(img: Image.Image) -> TileStats:
    """Both skip signals from a single downscale — they share all the expensive work."""
    small = img.convert("RGB").resize((MASK_SIZE, MASK_SIZE), Image.BILINEAR)
    arr = np.asarray(small, dtype=np.float32)
    # Chromatic coordinates: divide each channel by the pixel's total intensity, so both
    # measures describe colour rather than how brightly the sun happened to be shining.
    total = arr.sum(axis=2, keepdims=True)
    total[total == 0] = 1.0
    chroma = arr / total
    r, g, b = np.moveaxis(chroma, 2, 0)
    exg = 2.0 * g - r - b
    return TileStats(
        vegetation=float((exg > EXG_PIXEL_CUTOFF).mean()),
        uniformity=float(chroma.reshape(-1, 3).std(axis=0).mean()),
        mean_rgb=tuple(float(v) for v in arr.mean(axis=(0, 1))),
    )


def is_background(
    stats: TileStats,
    threshold: float = GREEN_THRESHOLD,
    uniformity_max: float = UNIFORMITY_MAX,
) -> bool:
    """Both tests must agree before a tile is dropped. See the module docstring for why."""
    return stats.vegetation < threshold and stats.uniformity <= uniformity_max


def skip_label(stats: TileStats) -> str:
    """Which kind of background this is. Cosmetic — the UI greys both — but 'skipped_sky'
    along the top row and 'skipped_soil' along the bottom makes the mask legible."""
    r, g, b = stats.mean_rgb
    # Sky is blue-dominant and bright; soil is red-dominant. The margin on that comparison is
    # not decoration: a near-neutral grey tile has b within a point or two of r, and a bare
    # `b > r` turns a rounding difference into a confident "sky". Requiring real blue
    # dominance sends genuinely grey surfaces to the soil label instead of flipping a coin.
    if b > r + SKY_BLUE_MARGIN and (r + g + b) / 3 > SKY_MIN_BRIGHTNESS:
        return "skipped_sky"
    return "skipped_soil"


def run_scout(
    state: RunState,
    img: Image.Image,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
    threshold: float = GREEN_THRESHOLD,
    uniformity_max: float = UNIFORMITY_MAX,
) -> RunState:
    """Write the full grid into state.tiles, skipped tiles already labelled.

    Every cell is written, including skipped ones — the UI derives grid dimensions from
    max(x) and max(y), so a hole in the array would silently reshape the heatmap. Scored
    cells keep the placeholder label until the Diagnostician replaces it; the heatmap does
    not reveal a tile until its diagnose.tile.<id> event arrives, so nothing flashes.
    """
    width, height = img.size
    tiles: list[Tile] = []
    skipped = 0

    for x, y, box in tile_boxes(width, height, cols, rows):
        tile = Tile.at(x, y)
        stats = tile_stats(img.crop(box))
        if is_background(stats, threshold, uniformity_max):
            tile.label = skip_label(stats)
            skipped += 1
        tiles.append(tile)

    state.apply(f"scout.grid.{cols}x{rows}", tiles=tiles)
    if skipped:
        state.apply(f"scout.skipped.{skipped}_tiles")
    state.apply("scout.done")
    return state


def tissue_share(state: RunState) -> float:
    """Share of the grid this agent kept — its answer to "is there plant tissue in frame".

    Read back off the tiles rather than off an event so it stays true if the grid size ever
    changes, and computed over every tile rather than the scored ones because the skipped tiles
    are precisely the measurement.
    """
    if not state.tiles:
        return 0.0
    return sum(1 for t in state.tiles if not t.skipped) / len(state.tiles)


def has_subject(state: RunState) -> bool:
    """Is there enough plant tissue in frame to be worth reading a diagnosis off?"""
    return tissue_share(state) >= SCOUT_TISSUE_MIN


def scout_summary(state: RunState) -> str:
    cols, rows = state.grid_size()
    skipped = [t for t in state.tiles if t.skipped]
    return (
        f"grid {cols}x{rows} = {len(state.tiles)} tiles, "
        f"{len(state.tiles) - len(skipped)} to score, {len(skipped)} skipped"
    )

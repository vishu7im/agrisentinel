"""Grid geometry, shared by the Scout and the Diagnostician.

This is not an agent — it is arithmetic. It lives in its own module because both agents need
the identical grid and neither is allowed to call the other. If the Diagnostician derived
boxes even slightly differently from the Scout, it would score tile t_03_02 using pixels the
Scout judged as belonging to t_03_01, and nothing would report an error.

Edges are computed with `round(i * w / cols)` rather than a fixed tile width, so the
remainder is spread across the grid instead of dumped in the last column. On a 1920px image
with an 8-wide grid that is the difference between eight 240px columns and seven 240px
columns plus one that is 233px.
"""

from __future__ import annotations

from PIL import Image, ImageOps

DEFAULT_COLS = 8
DEFAULT_ROWS = 5


def load_image(path) -> Image.Image:
    """Open a field photo as RGB, honouring EXIF orientation.

    Phone cameras store a rotation flag rather than rotating the pixels. Without the
    transpose, a portrait-held photo is tiled sideways and every compass bearing A4 computes
    is 90 degrees wrong.
    """
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def edges(total: int, n: int) -> list[int]:
    return [round(i * total / n) for i in range(n + 1)]


def tile_boxes(
    width: int, height: int, cols: int = DEFAULT_COLS, rows: int = DEFAULT_ROWS
) -> list[tuple[int, int, tuple[int, int, int, int]]]:
    """[(x, y, (left, top, right, bottom))] in reading order — row 0 first, west to east.

    Reading order matters: it is the order diagnose.tile.<id> events fire, so the heatmap
    fills in top-left to bottom-right and looks like a scan rather than a shuffle.
    """
    if cols < 1 or rows < 1:
        raise ValueError(f"grid must be at least 1x1, got {cols}x{rows}")
    xs = edges(width, cols)
    ys = edges(height, rows)
    return [
        (x, y, (xs[x], ys[y], xs[x + 1], ys[y + 1]))
        for y in range(rows)
        for x in range(cols)
    ]


def crop_tiles(
    img: Image.Image, cols: int = DEFAULT_COLS, rows: int = DEFAULT_ROWS
) -> dict[str, Image.Image]:
    """Tile id -> crop. Keyed by id so a caller can pick out only the tiles it needs."""
    w, h = img.size
    return {f"t_{x:02d}_{y:02d}": img.crop(box) for x, y, box in tile_boxes(w, h, cols, rows)}

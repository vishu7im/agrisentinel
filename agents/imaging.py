"""Turning a PIL image into something that fits in a JSON request body.

    from agents.imaging import inline_image
    part = inline_image(img)          # ("image/jpeg", "<base64>") or None

Split out of `agents/llm.py` for two reasons, one of them a rule and one of them a judgement.
The rule is the 300-line ceiling. The judgement is that `llm.py` is otherwise standard library
top to bottom, which is what lets it be read, stubbed and reasoned about without an image
stack; keeping the only PIL dependency in a file of its own preserves that rather than hiding
it behind a lazy import.

Encoding happens from the in-memory image, never from `backend/uploads/<run_id>/field.jpg`.
That is what makes the Observer work identically from `agents/run.py`, which has no store and
no run directory, and it is what guarantees a 32 MB upload never reaches the wire at 32 MB.
"""

from __future__ import annotations

import base64
import io

from PIL import Image

# Long edge the image is downscaled to before encoding. Gemini resamples to 768px tiles
# internally, so 1024 on the long edge of a 4:3 photo is one native tile plus headroom; beyond
# that you pay latency and tokens for pixels the model throws away. Measured on the seven
# Wikimedia field photographs: 78-235 KB encoded, from originals up to 4.2 MB.
#
# 1536 is the knob to reach for if small lesions turn out to be lost — septoria specks are the
# case to watch, and it is the one disease the Observer currently misreads.
LONG_EDGE = 1024
JPEG_QUALITY = 85

# Gemini's inline_data ceiling is around 20 MB. This is the comfort zone, not the limit: an
# upload may be 32 MB (backend/app/main.py MAX_UPLOAD_BYTES) and must never reach the wire at
# that size. Nothing in the measured set came within 5% of this.
MAX_INLINE_BYTES = 4_000_000

# Second attempt if the first still will not fit. Smaller and rougher, on the argument that a
# degraded look at the field beats no look at all.
FALLBACK_EDGE = 768
FALLBACK_QUALITY = 70


def _fit(img: Image.Image, long_edge: int) -> Image.Image:
    """Downscale so the long edge is at most `long_edge`. Never upscales."""
    if max(img.size) <= long_edge:
        return img
    scale = long_edge / max(img.size)
    return img.resize(
        (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
        Image.LANCZOS,
    )


def encode(img: Image.Image, long_edge: int, quality: int) -> bytes:
    """One JPEG, at this size and quality. `.convert("RGB")` because a PNG upload arrives as
    RGBA and JPEG has no alpha channel — without it this raises on a perfectly ordinary file."""
    buffer = io.BytesIO()
    _fit(img.convert("RGB"), long_edge).save(
        buffer, format="JPEG", quality=quality, optimize=True
    )
    return buffer.getvalue()


def inline_image(
    img: Image.Image,
    long_edge: int = LONG_EDGE,
    quality: int = JPEG_QUALITY,
) -> tuple[str, str] | None:
    """A PIL image as `(mime_type, base64)` ready for `llm.complete(image=...)`, or None.

    None means "this will not fit, do not attempt the call" — the caller degrades instead of
    sending a request that will be refused at the far end after a round trip.
    """
    for edge, jpeg_quality in ((long_edge, quality), (FALLBACK_EDGE, FALLBACK_QUALITY)):
        raw = encode(img, edge, jpeg_quality)
        if len(raw) <= MAX_INLINE_BYTES:
            return "image/jpeg", base64.b64encode(raw).decode("ascii")
    return None

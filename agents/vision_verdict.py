"""What the Observer is allowed to say, and how to read it back safely.

    from agents.vision_verdict import VisionVerdict, parse_verdict, verdict_schema, class_keys

The data contract, kept apart from `agents/observer.py` so the agent file reads as the decision
it makes rather than as a parser. It is also the half worth testing on its own: every function
here is total and offline, so the malformed-response cases can be exercised without a network,
an image or a model.

Nothing here trusts the response schema. A stub server, a proxy, a model that ignored the
config and a genuine answer all arrive down the same pipe and are indistinguishable until
parsed. The schema is a way of asking nicely; this is the check.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLASSES = REPO_ROOT / "ml" / "artifacts" / "model_classes.json"

# Crops the classifier knows. Anything else is "other" — a real answer, not a gap.
CROPS = ("tomato", "potato", "corn")
UNKNOWN = "unknown"
HEALTHY = "healthy"

# Truncation limits for anything that reaches the event log or a browser.
MAX_VISIBLE_CHARS = 200
MAX_SLUG_CHARS = 32

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


@lru_cache(maxsize=1)
def class_keys(path: Path = DEFAULT_CLASSES) -> tuple[str, ...]:
    """The classifier's own class list, which is the authority on what diseases exist.

    Same argument as `disease_vocabulary()` in the Agronomist: a disease the Observer names that
    the classifier has never heard of has no severity weight, no corpus coverage and no Hindi
    phrase, so the vocabulary comes from one place and this is it.
    """
    return tuple(json.loads(path.read_text())["class_keys"])


@dataclass(frozen=True)
class VisionVerdict:
    """What the Observer saw. Stored on `state.vision` as a plain dict.

    `ok` is about the *call*, not the answer. A successful call that returned `unknown` is
    `ok=True` with `class_key=None`, because "I looked and I cannot name it" is information and
    "I never got to look" is not — and the two lead to opposite decisions downstream.
    """

    ok: bool
    is_crop_field: bool = True
    crop: str | None = None
    class_key: str | None = None
    confidence: int = 0
    pct_affected: int | None = None
    visible: str = ""
    off_enum: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict | None) -> VisionVerdict:
        if not raw:
            return cls(ok=False, error="absent")
        return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})


def verdict_schema(keys: tuple[str, ...]) -> dict:
    """The response schema. Three details in here are load-bearing.

    **`unknown` is in the class enum.** Without it the model is forced to name one of fourteen
    diseases when it is shown anthracnose, a nutrient deficiency or a photograph of a road —
    which is precisely the failure this agent exists to catch, reproduced one layer up.

    **`confidence` and `pct_affected` are integers, not numbers.** Measured, not defensive: as
    `number` the model emitted `"pct_affected":0.000000000…` and ran to MAX_TOKENS, losing the
    entire reply. An integer cannot do that.

    **`propertyOrdering` puts `visible` first.** Fields are generated in that order, so the
    model writes "a wide field of young potato plants in rows of reddish-brown soil" before it
    commits to a label. Free reasoning at no prompt cost, and it doubles as the sentence a
    human reads to check the answer.
    """
    return {
        "type": "object",
        "properties": {
            "visible": {"type": "string"},
            "is_crop_field": {"type": "boolean"},
            "crop": {"type": "string", "enum": [*CROPS, "other"]},
            "class_key": {"type": "string", "enum": [*keys, UNKNOWN]},
            "confidence": {"type": "integer"},
            "pct_affected": {"type": "integer"},
        },
        "required": [
            "visible",
            "is_crop_field",
            "crop",
            "class_key",
            "confidence",
            "pct_affected",
        ],
        "propertyOrdering": [
            "visible",
            "is_crop_field",
            "crop",
            "class_key",
            "confidence",
            "pct_affected",
        ],
    }


def slug(text: str) -> str:
    """Anything that goes into an event string, made safe for one. Never empty."""
    cleaned = _SLUG_RE.sub("_", str(text).strip().lower()).strip("_")
    return cleaned[:MAX_SLUG_CHARS] or UNKNOWN


def _clamp(value, low: int, high: int, fallback: int | None) -> int | None:
    try:
        return max(low, min(high, int(round(float(value)))))
    except (TypeError, ValueError):
        return fallback


def parse_verdict(text: str, keys: tuple[str, ...]) -> VisionVerdict:
    """A response body into a verdict. Total: every malformed input has an answer.

    Defaults lean toward today's behaviour, never toward a refusal — a missing `is_crop_field`
    is True, an unparseable body is a failed call. The one thing this must never do is invent a
    disagreement out of a parse artifact and withhold a farmer's treatment plan because of it.
    """
    body = (text or "").strip()
    if body.startswith("```"):
        # Belt and braces: with responseMimeType set the reply is bare JSON, but a stub or a
        # model that ignored the config will fence it.
        body = body.strip("`").lstrip()
        if body[:4].lower() == "json":
            body = body[4:].lstrip()
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return VisionVerdict(ok=False, error="malformed")
    if not isinstance(data, dict):
        return VisionVerdict(ok=False, error="malformed")

    raw_key = str(data.get("class_key") or "").strip()
    known = raw_key in keys
    crop = str(data.get("crop") or "").strip().lower()

    return VisionVerdict(
        ok=True,
        # Anything that is not exactly False is True. A missing field must not be able to
        # declare a real field photograph a non-photograph and block the run.
        is_crop_field=data.get("is_crop_field") is not False,
        crop=crop if crop in CROPS else None,
        class_key=raw_key if known else None,
        confidence=_clamp(data.get("confidence"), 0, 100, 0) or 0,
        pct_affected=_clamp(data.get("pct_affected"), 0, 100, None),
        visible=str(data.get("visible") or "").strip()[:MAX_VISIBLE_CHARS],
        # Kept rather than discarded: "the model saw something it could not name" is a
        # different and more interesting statement than "the model said nothing".
        off_enum=None if known or not raw_key or raw_key == UNKNOWN else slug(raw_key),
    )

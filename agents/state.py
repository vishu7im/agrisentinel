"""RunState — the one object every agent reads and writes.

Shape is dictated by contract/run_state.schema.json, which is frozen. This module exists so
that shape lives in exactly one place: if the schema ever does change, this file changes and
nothing else does.

The event log is not decoration. Every mutation goes through `apply()`, which takes the
event string as its first argument, so it is structurally impossible to change the run state
without saying so on the log. That log is what makes the multi-agent architecture visible on
Dev B's screen, and invisible architecture scores zero.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Exactly the top-level keys in the schema, in schema order. The schema sets
# additionalProperties:false, so anything not on this list is a hard validation failure.
STATE_FIELDS = (
    "run_id",
    "crop",
    "status",
    "image_url",
    "started_at",
    "finished_at",
    "tiles",
    "spread",
    "plan_draft",
    "verification",
    "schedule",
    "cost_estimate",
    "rescan_date",
    "report",
    "events",
)

# Fields that agents hand to each other but that never reach the API response.
#
# The Agronomist retrieves the chunks it drafts from; the Verifier needs those exact chunks to
# check the draft against. Only the Verifier may publish them, because they land under
# `verification.sources` and `verification.status` has no value meaning "not ruled on yet" —
# writing them earlier would mean inventing one.
#
# This does not widen the API surface: `to_dict()` is unchanged and still emits exactly the
# schema's keys. The point of routing it through `apply()` anyway is that the handoff stays
# on the event log like every other mutation, rather than becoming a quiet setattr between
# two agents that the timeline never shows.
INTERNAL_FIELDS = ("sources",)

STATUSES = frozenset({"queued", "running", "complete", "blocked", "error"})

# Placeholder label for a tile the Scout has laid out but the Diagnostician has not scored.
# It must not start with "skipped" (the UI would grey it out permanently) and must not be
# "healthy" (it would render green). In practice the UI never draws it: the heatmap only
# reveals a tile once its diagnose.tile.<id> event arrives.
PENDING_LABEL = "pending"


def utc_now() -> str:
    """ISO 8601 UTC with a Z suffix — what the schema's date-time format expects."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def tile_id(x: int, y: int) -> str:
    """t_<xx>_<yy>, zero-padded. The schema enforces this pattern, so build ids only here."""
    return f"t_{x:02d}_{y:02d}"


@dataclass
class Tile:
    id: str
    x: int
    y: int
    label: str = PENDING_LABEL
    confidence: float | None = None
    escalated: bool = False

    @classmethod
    def at(cls, x: int, y: int) -> "Tile":
        return cls(id=tile_id(x, y), x=x, y=y)

    @property
    def skipped(self) -> bool:
        return self.label.startswith("skipped")

    @property
    def scored(self) -> bool:
        return not self.skipped and self.label != PENDING_LABEL

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "label": self.label,
            # round() here rather than at the call site: the schema allows any number, but a
            # confidence printed as 0.8712999820709229 in a demo looks like a leak, not a model.
            "confidence": None if self.confidence is None else round(float(self.confidence), 4),
            "escalated": bool(self.escalated),
        }


@dataclass
class RunState:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    crop: str = "tomato"
    status: str = "queued"
    image_url: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    tiles: list[Tile] = field(default_factory=list)
    spread: dict | None = None
    plan_draft: str | None = None
    verification: dict | None = None
    schedule: list[dict] | None = None
    cost_estimate: dict | None = None
    rescan_date: str | None = None
    report: dict | None = None
    events: list[str] = field(default_factory=list)

    # Not serialised — see INTERNAL_FIELDS. Retrieved chunks, in verification.sources shape.
    sources: list[dict] = field(default_factory=list)

    # --- the only way to mutate -------------------------------------------------------

    def apply(self, event: str, **changes) -> "RunState":
        """Set fields and log the event, in that order. Pass no changes for a pure event.

        Rejects unknown field names on the spot. A typo like `state.apply(..., spred=...)`
        would otherwise sail through, leave `spread` null, and surface three agents later as
        an empty severity panel with no error anywhere.
        """
        for key, value in changes.items():
            if key not in STATE_FIELDS and key not in INTERNAL_FIELDS:
                raise KeyError(f"{key!r} is not a RunState field — the schema forbids it")
            setattr(self, key, value)
        if changes.get("status") is not None and self.status not in STATUSES:
            raise ValueError(f"status {self.status!r} is not one of {sorted(STATUSES)}")
        self.events.append(event)
        return self

    def update_tile(self, target: str, event: str, **changes) -> Tile:
        """Mutate one tile in place and log it. Used per-tile by the Diagnostician."""
        tile = self.tile(target)
        for key, value in changes.items():
            if not hasattr(tile, key):
                raise KeyError(f"{key!r} is not a Tile field")
            setattr(tile, key, value)
        self.events.append(event)
        return tile

    # --- reads ------------------------------------------------------------------------

    def tile(self, target: str) -> Tile:
        for tile in self.tiles:
            if tile.id == target:
                return tile
        raise KeyError(f"no tile {target!r} in this run")

    @property
    def scored_tiles(self) -> list[Tile]:
        """Tiles with a real prediction. This is the denominator for pct_affected in A4 —
        skipped tiles are not part of the field, so counting them would flatter the number."""
        return [t for t in self.tiles if t.scored]

    def grid_size(self) -> tuple[int, int]:
        if not self.tiles:
            return (0, 0)
        return (max(t.x for t in self.tiles) + 1, max(t.y for t in self.tiles) + 1)

    # --- serialisation ----------------------------------------------------------------

    def to_dict(self) -> dict:
        """Every schema key, always present. Optional keys are emitted as null rather than
        omitted so the frontend never has to distinguish "absent" from "not yet"."""
        return {
            "run_id": self.run_id,
            "crop": self.crop,
            "status": self.status,
            "image_url": self.image_url,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "tiles": [t.to_dict() for t in self.tiles],
            "spread": self.spread,
            "plan_draft": self.plan_draft,
            "verification": self.verification,
            "schedule": self.schedule,
            "cost_estimate": self.cost_estimate,
            "rescan_date": self.rescan_date,
            "report": self.report,
            "events": list(self.events),
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def new_run(crop: str = "tomato", image_url: str | None = None) -> RunState:
    """A run in flight: status running, clock started, run.start on the log.

    image_url defaults to the endpoint that serves this run's own upload, because the
    frontend's demo-mode replay has no File object to fall back on and needs the backend to
    hand it a URL it can just GET.
    """
    state = RunState(crop=crop)
    state.image_url = image_url or f"/api/run/{state.run_id}/image"
    return state.apply("run.start", status="running", started_at=utc_now())

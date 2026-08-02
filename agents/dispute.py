"""Was this run contested, and what over? — read back off the event log.

    from agents.dispute import dispute, dispute_parts

Split from `agents/consensus.py` because the callers are different and so is the direction.
That module *decides*; this one is what the Agronomist and the Verifier ask afterwards, and
neither of them has any business importing the decision procedure to find out what it concluded.
It also keeps `consensus.py` under the 300-line ceiling.

The answer is read from `events[]` rather than kept in a field, the same way the Verifier
re-derives the disease from `agronomist.disease.*`. The event log is already the record of what
happened; a second copy in state is a second thing that can disagree with it.
"""

from __future__ import annotations

from agents.state import RunState

CONTESTED_EVENT = "consensus.contested."
NOT_CROP_EVENT = "consensus.not_crop"


def dispute(state: RunState) -> str | None:
    """The contested event, read back off the log, or None if the run is not in dispute.

    Read from `events[]` rather than kept in a field, the same way the Verifier re-derives the
    disease from `agronomist.disease.*`. The event log is already the record of what happened;
    a second copy in state is a second thing that can disagree with it.
    """
    for event in state.events:
        if event.startswith(CONTESTED_EVENT) or event == NOT_CROP_EVENT:
            return event
    return None


def dispute_parts(event: str) -> tuple[str, str, float]:
    """A contested event as `(reason, cnn_label, cnn_pct)`. Tolerant of a malformed tail."""
    if event == NOT_CROP_EVENT:
        return "not_crop", "", 0.0
    body = event[len(CONTESTED_EVENT) :]
    pieces = body.split(".")
    reason = pieces[0] if pieces else "disagreement"
    label = pieces[1] if len(pieces) > 1 else ""
    pct = 0.0
    if len(pieces) > 2:
        try:
            pct = float(pieces[2].removesuffix("pct"))
        except ValueError:
            pct = 0.0
    return reason, label, pct

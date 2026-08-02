"""The three checks a drafted plan has to survive, and the allowlist they are made against.

    from agents.checks import ungrounded, chemical_violations, dose_violations

Split out of `agents/verifier.py` under the 300-line rule, and the seam is a real one rather
than an arbitrary cut: everything here *gathers evidence* and returns it, and nothing here
decides anything. Whether two ungrounded sentences mean a rewrite or a strip, whether a banned
active means BLOCK — that is policy, it lives in the Verifier, and it is worth being able to
read it without ninety lines of regex-and-table work in the way.

Not folded into `agents/claims.py`, which was the obvious candidate: that file is deliberately
free of any dependency on `RunState`, and `ungrounded` needs the run's spread numbers and its
event log. Keeping claims.py as primitives over strings is worth more than one fewer file.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from agents.claims import (
    GROUNDING_MIN,
    Claim,
    containment,
    doses,
    is_scan_statement,
    mentioned,
    names_disease,
    unknown_actives,
)
from agents.state import RunState

ALLOWLIST_PATH = Path(__file__).resolve().parent / "allowlist.json"


@lru_cache(maxsize=1)
def allowlist() -> dict:
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))


def approved() -> list[str]:
    return sorted(allowlist()["chemicals"])


def dominant_label(state: RunState) -> str:
    """The disease the plan is about, as words. Read off the event log the Agronomist wrote,
    so the Verifier does not re-derive it from tiles and reach a different answer."""
    prefix = "agronomist.disease."
    for event in reversed(state.events):
        if event.startswith(prefix):
            return event[len(prefix):].rsplit(".", 1)[0].replace("_", " ")
    return ""


def ungrounded(claims: list[Claim], chunks: dict[str, dict], state: RunState) -> list[str]:
    """Sentences that do not trace back to the chunk they cite. Returns the original lines.

    Three distinct failures, all of them ungrounded and only the first of them obvious: no
    marker at all; a marker naming a chunk that was never retrieved (an invented id, which is
    worse than none because it looks checked); and a marker naming a real chunk that does not
    actually contain the sentence.
    """
    disease = dominant_label(state)
    out = []
    for claim in claims:
        chunk = chunks.get(claim.marker or "")
        if chunk is None:
            out.append(claim.line)
        elif is_scan_statement(claim.text, state.spread):
            # Its numbers came from the Spread Analyst and are in no passage. What its source
            # has to back is the other half of the sentence — that this field has this disease.
            if not names_disease(claim.text, chunk, disease):
                out.append(claim.line)
        elif containment(claim.text, chunk) < GROUNDING_MIN:
            out.append(claim.line)
    return out


def chemical_violations(claims: list[Claim]) -> list[tuple[str, str]]:
    """(sentence, reason) for banned actives and anything not on the allowlist."""
    banned = allowlist()["banned"]
    known = approved()
    problems = []
    for claim in claims:
        for name in mentioned(claim.text, banned):
            problems.append((claim.text, f"{name} is banned or severely restricted for agricultural use"))
        for name in unknown_actives(claim.text, known):
            if name not in banned:
                problems.append((claim.text, f"{name} is not a chemical any source document names"))
    return problems


def dose_violations(claims: list[Claim]) -> list[tuple[str, str]]:
    """(sentence, reason) for doses outside the stated range, in the wrong unit, or unattached.

    A dose in the wrong unit is its own failure and not a rounding matter: 3 grams per litre of
    a wettable powder and 3 millilitres per litre of a concentrate are different amounts of
    active ingredient, and the mistake is invisible in a sentence that otherwise reads well.
    """
    table = allowlist()["chemicals"]
    known = approved()
    problems = []
    for claim in claims:
        # Unapproved actives are included when attributing doses, purely so the number lands on
        # the right name. Without them, "carbendazim ... at 4.0 grams per litre" reported a
        # dose "with no chemical named" — true of the allowlist, and baffling to read next to a
        # sentence that plainly names one. The chemical itself is already a violation above;
        # this loop only has to avoid describing it wrongly.
        for name, low, high, unit in doses(claim.text, known + unknown_actives(claim.text, known)):
            if name is None:
                problems.append((claim.text, f"a dose of {low} {unit} is given with no chemical named"))
            elif name not in table:
                continue
            elif unit != table[name]["unit"]:
                problems.append(
                    (claim.text, f"{name} is dosed in {unit}, but its source states {table[name]['unit']}")
                )
            elif low < table[name]["low"] or high > table[name]["high"]:
                problems.append((
                    claim.text,
                    f"{name} at {low}-{high} {unit} is outside the supported "
                    f"{table[name]['low']}-{table[name]['high']} {unit}",
                ))
    return problems

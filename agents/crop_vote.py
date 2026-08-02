"""Which crop is this field? The policy, kept apart from the model that supplies the evidence.

`agents/diagnostician.py` owns the inference and reports what the pixels say; this file decides
what to do about it. The split is deliberate. The question here is not technical — it is how
much authority a model's guess has over a person's statement — and that decision should be
readable on its own, changeable on its own, and hard to alter by accident while tuning a
classifier.

The short version: a crop the caller chose is always obeyed. The vote only decides when the
caller said AUTO, because nobody chose and something has to be picked. See the measurements in
the constants below for why the vote is not trusted with more than that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from agents.state import RunState

if TYPE_CHECKING:  # import-time cycle otherwise — the Diagnostician imports this module
    from agents.diagnostician import Classifier

# --- crop detection ---------------------------------------------------------------------
#
# How many tiles the probe pass reads before deciding what crop this is. They are the first
# tiles of the scan and their probabilities are kept, so the probe costs no extra inference —
# it only delays the first `diagnose.tile.*` event by a couple of batches.
CROP_PROBE_TILES = 8

# What the caller sends when no human has chosen a crop. A sentinel rather than an empty
# string so an accidentally-blank form field cannot silently mean "guess".
AUTO = "auto"

# Where `auto` lands when there is nothing to vote on — a frame of pure soil, no scored tiles.
# Only reachable on a run that produces no plan anyway, and the event says it happened.
FALLBACK_CROP = "tomato"

# Mean probability mass on the winning crop. Synthetic mosaics in agents/testdata/:
#
#     the three tomato mosaics     tomato 0.969-0.985   (runner-up 0.017 or less)
#     field_corn_nlb               corn   0.912         (next: tomato 0.073)
#     field_all_soil               corn   0.594         (next: tomato 0.356)
#
# Real photographs, which is the case that matters and the case this fails:
#
#     corn NLB field               tomato 0.502 / corn 0.483     <- wrong, and nearly tied
#     corn common rust             tomato 0.469 / potato 0.393   <- wrong
#     potato late blight leaf      corn   0.438 / tomato 0.411   <- wrong
#     tomato late blight plant     corn   0.754 / tomato 0.216   <- wrong, and above the bar
#
# 0.75 separates a studio mosaic from bare soil and separates nothing at all on real imagery.
# It is kept because a confident vote is still better than a hardcoded default when nobody has
# said anything, and it is never allowed to overrule a person — see resolve_crop. The last row
# is the whole argument: on a real photograph this check is confidently wrong often enough that
# giving it authority over a human would lose more runs than it saved.
CROP_MIN_SHARE = 0.75
CROP_MIN_MARGIN = 0.50
# Same reasoning as spread.MIN_SCORED_TILES: one tile is not a field.
CROP_MIN_TILES = 3

def resolve_crop(state: RunState, classifier: "Classifier", probs: np.ndarray) -> str | None:
    """Decide which crop's classes the tiles get decoded against. May rewrite `state.crop`.

    Returns the crop to mask with, or None for no mask at all. Every branch logs, because the
    farmer brief, the severity weights and the retrieved documents all key off this string, and
    a run whose crop changed underneath it with no event makes three panels inexplicable at once.

    `state.crop` is guaranteed to be a real crop on the way out — never the AUTO sentinel — so
    nothing downstream has to know this negotiation happened.
    """
    declared = state.crop
    chosen = declared != AUTO and classifier.crop_mask(declared) is not None
    shares = classifier.crop_shares(probs)

    if not shares:
        if chosen:
            return declared
        state.apply(f"diagnose.crop_unresolved.{FALLBACK_CROP}", crop=FALLBACK_CROP)
        return None

    detected, share = max(shares.items(), key=lambda kv: kv[1])
    state.apply(f"diagnose.crop_detected.{detected}.{round(share * 100)}pct")

    if chosen:
        if detected != declared:
            # Logged, never acted on. The vote is wrong on real photographs often enough that
            # letting it overrule the one person who looked at the field would lose more runs
            # than it saved — the numbers are in the constants block above. The UI can surface
            # this event to ask "is this really tomato?", which is the right way to spend it.
            state.apply(f"diagnose.crop_mismatch.{detected}")
        return declared

    # Nobody chose. Something has to be picked and the vote is the only evidence there is, so it
    # is taken even when it is under the bar — a weak read of the pixels still beats a constant.
    # The event carries the doubt so the UI can show it and the log can be argued with later.
    if len(probs) < CROP_MIN_TILES or share < CROP_MIN_SHARE:
        state.apply(f"diagnose.crop_uncertain.{detected}.{round(share * 100)}pct")
    if declared != AUTO:
        # A crop the model was never trained on. Record it before it is replaced, or the run
        # state will claim the caller asked for something they never asked for.
        state.apply(f"diagnose.crop_unknown.{declared}")
    state.apply(f"diagnose.crop_auto.{detected}", crop=detected)
    return detected


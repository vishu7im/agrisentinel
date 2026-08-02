"""What a blocked run says to the farmer instead of a treatment plan.

Separated from verifier.py because it is the only farmer-facing prose that file produces, and
it is the part most likely to be rewritten under time pressure — a wording change here cannot
reach the ruling logic.

**Why the Verifier writes a report at all**, when the Reporter agent exists to do exactly
that: the Reporter runs after a plan is verified, and a BLOCK means there is no plan to
report on, so it never runs. Something still has to be on the screen of somebody standing in
a field who has just been told no. The refusal is the deliverable in that case, not the
absence of one.

The diagnosis and the severity are stated plainly and without hedging. They were measured, the
Verifier has no quarrel with them, and they are the part an extension officer needs first. What
is withheld is the treatment — and the brief says so in one sentence rather than apologising.
"""

from __future__ import annotations

CROP_HI = {"tomato": "टमाटर", "potato": "आलू", "corn": "मक्का"}

# Hindi name with the English in brackets, the way extension material is actually written: the
# English term is what is printed on the packet the farmer will be sold, so dropping it would
# make the brief harder to act on, not more accessible.
DISEASE_HI = {
    "late blight": "पछेती झुलसा",
    "early blight": "अगेती झुलसा",
    "bacterial spot": "जीवाणु धब्बा",
    "septoria leaf spot": "सेप्टोरिया पत्ती धब्बा",
    "leaf mold": "पत्ती फफूँदी",
    "yellow leaf curl virus": "पीला पत्ती मरोड़ विषाणु",
    "mosaic virus": "मोज़ेक विषाणु",
    "target spot": "लक्ष्य धब्बा",
    "spider mites two spotted spider mite": "दो-धब्बेदार मकड़ी",
    "common rust": "सामान्य रतुआ",
    "northern leaf blight": "उत्तरी पत्ती झुलसा",
    "gray leaf spot": "धूसर पत्ती धब्बा",
}


def refusal_report(crop: str, disease: str, pct: float, plainly: str) -> dict:
    """The {en, hi} brief a BLOCK ships. `plainly` is one clause saying why, in farmer words."""
    disease_hi = f"{DISEASE_HI[disease]} ({disease})" if disease in DISEASE_HI else disease
    return {
        "en": (
            f"Your {crop} field shows signs of {disease} across {pct}% of the scanned area. "
            f"We are not able to give you a treatment recommendation for this scan, because {plainly}. "
            "Please show this scan to your local agriculture extension officer before you spray anything."
        ),
        "hi": (
            f"आपके {CROP_HI.get(crop, crop)} के खेत में स्कैन किए गए हिस्से के {pct}% भाग में "
            f"{disease_hi} के लक्षण मिले हैं। इस स्कैन के लिए हम कोई दवा नहीं बता सकते। "
            "कुछ भी छिड़काव करने से पहले कृपया अपने नज़दीकी कृषि विस्तार अधिकारी को यह रिपोर्ट दिखाएँ।"
        ),
    }

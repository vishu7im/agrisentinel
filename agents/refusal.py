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

**Except when the diagnosis is the thing in dispute**, which is what A10 added. `refusal_report`
opens by asserting the disease and the percentage as fact, and on a contested run that sentence
is the one claim the system has specifically decided it cannot stand behind. So a contested run
gets `contested_report` instead, which reports the disagreement rather than the diagnosis. Two
functions rather than a flag, because the difference is what the brief is *about*.
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


def contested_report(crop: str, disease: str, pct: float) -> dict:
    """The brief for a run where the two models disagreed about whether anything is wrong.

    Deliberately does not name the disease as a finding. Both readings are attributed to the
    thing that produced them — "our tile scanner found", "a second model found" — because the
    honest content of this run is that the system does not know, and a brief that leads with a
    diagnosis it has just declined to stand behind is worse than no brief.
    """
    disease_hi = DISEASE_HI.get(disease)
    named_hi = f" ({disease_hi})" if disease_hi else ""
    return {
        "en": (
            "Two checks were run on this photograph and they did not agree. "
            f"Our tile-by-tile scanner found signs of {disease} across {pct:g}% of the "
            f"{crop} field; a second check that looks at the whole photograph found no disease. "
            "Because of that disagreement we are not giving you a treatment recommendation. "
            "Walk the field and look at the plants yourself, and show this scan to your local "
            "agriculture extension officer before you spray anything."
        ),
        "hi": (
            "इस तस्वीर की दो अलग-अलग जाँच की गईं और दोनों के नतीजे अलग निकले। "
            f"हमारे टाइल स्कैनर को {CROP_HI.get(crop, crop)} के खेत के {pct:g}% भाग में "
            f"{disease}{named_hi} के लक्षण मिले, जबकि पूरी तस्वीर देखने वाली दूसरी जाँच में "
            "कोई बीमारी नहीं मिली। इस मतभेद के कारण हम कोई दवा नहीं बता रहे हैं। "
            "कृपया खुद खेत में जाकर पौधे देखें, और छिड़काव से पहले अपने नज़दीकी कृषि विस्तार "
            "अधिकारी को यह रिपोर्ट दिखाएँ।"
        ),
    }


def not_field_report() -> dict:
    """The brief for a photograph that is not of a growing crop at all.

    Takes no crop argument on purpose: there isn't one. Naming a crop here would be the system
    playing along with a premise it has just rejected.
    """
    return {
        "en": (
            "This photograph does not appear to show a growing crop, so there is nothing here "
            "to diagnose. Take a photograph standing in the field, looking down at the plants, "
            "with the leaves filling most of the frame, and scan again."
        ),
        "hi": (
            "इस तस्वीर में खड़ी फसल नहीं दिख रही है, इसलिए यहाँ जाँचने के लिए कुछ नहीं है। "
            "खेत में खड़े होकर, पौधों की तरफ़ नीचे देखते हुए तस्वीर लें, जिसमें पत्तियाँ "
            "अधिकांश फ़्रेम में दिखें, और दोबारा स्कैन करें।"
        ),
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

"""The three text-level checks the Verifier rules on. No policy here, only evidence.

Split out of verifier.py so that file reads as the ruling — PASS, REWRITE, BLOCK and who
overrules whom — while the question of what counts as evidence for a sentence lives here and
can be argued with separately.

**Grounding is containment, not cosine, and that is a measured result.** The obvious design is
to score each sentence against the chunk it cites with the same TF-IDF similarity the
retriever already offers. It does not work, and the numbers are worth keeping because they are
counter-intuitive. Scoring seven sentences of a real plan against their cited chunks and seven
fabrications against chunks they had nothing to do with:

    verbatim, true        0.265 - 0.727
    fabricated            0.000 - 0.297

The populations overlap. "Apply carbendazim 50 percent WP at 4.0 grams per litre for faster
knockdown" — an invented chemical at an invented dose — scored **0.297** against a chunk that
never mentions it, higher than the true sentence "Re-inspect the field seven days after the
first application" at 0.265. Cosine rewards sharing the vocabulary of dosing advice, and a
convincing fabrication shares exactly that vocabulary. It is measuring register, not truth.

Containment — what fraction of the sentence's content words actually occur in the cited chunk
— separates them, because a sentence lifted from a passage is *made of* that passage:

    verbatim, true        1.000  (0.500 for the scan-fact line, handled below)
    fabricated            0.000 - 0.250, except chemical-bearing ones (see next paragraph)

**No single check is sufficient, and that is why there are three.** The one fabrication
containment ranks highly (0.625) is the carbendazim sentence, because it copies the *format*
of dosing advice — "percent", "grams", "per litre" — while inventing the only two things that
matter, the chemical and the number. Grounding cannot catch it. The allowlist catches it
immediately, because carbendazim is not in the corpus and therefore not in allowlist.json.
Grounding catches invented advice, the allowlist catches invented chemicals, and the dose
ranges catch altered numbers. Each is blind to what the others see.

**The honest limitation.** A truthful paraphrase scores as low as a fabrication — "Do not rely
on the same chemical group again and again or it will stop working" is a faithful restatement
of doc_19#p1 and scores 0.000 against it. Nothing lexical can tell that from invention; only
entailment can, which needs a model. So with no API key the system demands near-verbatim
grounding, and a paraphrase is sent back as REWRITE rather than shipped or blocked. That costs
nothing on the default path, where the drafter copies sentences and containment is 1.000 by
construction, and it fails toward asking again rather than toward trusting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MARKER_RE = re.compile(r"\[(doc_\d+#p\d+)\]\s*$")
WORD_RE = re.compile(r"[a-z]+")

# Measured, not chosen: verbatim sentences land at 1.000 and the scan-fact line at 0.500,
# while fabrications that do not name a chemical top out at 0.250. Anything in 0.3-0.4 is a
# paraphrase, which this check cannot rule on and should therefore not wave through.
GROUNDING_MIN = 0.45

# Function words carry no evidence either way — a sentence sharing "the" with a chunk is not
# grounded by it, and one avoiding "the" is not ungrounded.
STOPWORDS = frozenset("""
the a an and or of to in on at is are was were be been being for with by from as it its this
that these those you your we they them not no if where while when which who what how any all
some each other than then so such very more most much many few own same only just also both
into out up down over under again further once here there do does did have has had will would
can could should may might must about after before during between within per
""".split())


@dataclass(frozen=True)
class Claim:
    """One sentence of a plan, with the source it points at."""

    text: str          # the sentence, marker stripped
    marker: str | None  # the cited chunk id, or None if it carried no marker
    line: str          # the original line, marker included — what gets stripped on a rewrite


def content_words(text: str) -> list[str]:
    """Words that carry evidence. Digits are excluded deliberately: a dose is checked against
    the allowlist range, not against whether the chunk happens to contain that numeral."""
    return [w for w in WORD_RE.findall(text.lower()) if w not in STOPWORDS and len(w) > 2]


def parse_claims(draft: str) -> list[Claim]:
    """Plan markdown -> the checkable sentences. Headings and blanks are not claims."""
    claims = []
    for raw in draft.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = MARKER_RE.search(line)
        claims.append(
            Claim(text=MARKER_RE.sub("", line).strip(), marker=match.group(1) if match else None, line=line)
        )
    return claims


def containment(sentence: str, chunk: dict) -> float:
    """Fraction of the sentence's content words present in the chunk. 1.0 means lifted from it.

    Title and heading count as part of the chunk: a section of "Tomato Late Blight" is entitled
    to say "late blight" without the body repeating it, and scoring that as unsupported would
    flag the one sentence in the plan that names the disease correctly.
    """
    body = set(content_words(f"{chunk['doc']} {chunk.get('heading', '')} {chunk['text']}"))
    words = content_words(sentence)
    if not words:
        return 0.0
    return round(sum(w in body for w in words) / len(words), 3)


def is_scan_statement(text: str, spread: dict | None) -> bool:
    """Does this sentence restate the field measurements rather than make a claim about them?

    The diagnosis line says "Late blight is present across 50.0% of the scanned field in 2
    cluster(s), trending W" — the disease comes from the corpus, the numbers come from the
    scan and appear in no passage, so containment scores it 0.500 against a chunk it is
    correctly citing. Detected by the numbers themselves rather than by the wording, so the
    Verifier is not quietly coupled to how the drafter phrases things: a sentence carrying both
    the measured percentage and the measured cluster count came from the Spread Analyst.

    Such a sentence is not exempt from checking. Its citation still has to back the part that
    is a claim — that the field has this disease — which is checked separately.
    """
    if not spread:
        return False
    pct, clusters = spread.get("pct_affected"), spread.get("clusters")
    return pct is not None and clusters is not None and str(pct) in text and str(clusters) in text


def names_disease(text: str, chunk: dict, disease: str) -> bool:
    """The weaker test a scan statement has to pass: it and its source agree on the disease."""
    lowered = disease.lower()
    return lowered in text.lower() and lowered in f"{chunk['doc']} {chunk['text']}".lower()


# --- chemicals and doses -------------------------------------------------------------------

# Morphology of pesticide common names — the -azole/-strobin/-zeb families and friends. This
# is how an active ingredient the allowlist has never heard of gets noticed at all: you cannot
# match an unknown name against a list of known ones, so the shape of the word has to raise its
# hand. A false positive here costs a BLOCK on a plan that should have shipped, so the prefix
# length is deliberately long enough that ordinary English does not trip it.
ACTIVE_SUFFIXES = (
    "azole", "strobin", "thalonil", "xanil", "laxyl", "mycin", "thoxam", "prid", "zeb",
    "dazim", "sulfan", "carb", "trin", "amide", "phos", "myl", "aryl", "quat", "fen",
)
ACTIVE_RE = re.compile(r"\b[a-z]{4,}(?:" + "|".join(ACTIVE_SUFFIXES) + r")\b", re.I)

# "2.5 grams per litre", "0.3 ml per litre", "2.0 to 2.5 grams per litre of water"
DOSE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:to\s*(\d+(?:\.\d+)?)\s*)?(grams?|g|millilitres?|ml)\s+per\s+litre",
    re.I,
)


def _unit(word: str) -> str:
    return "g/L" if word.lower().startswith("g") else "ml/L"


def mentioned(text: str, names: list[str]) -> list[str]:
    """Which of `names` this sentence mentions. Multi-word entries ("copper oxychloride",
    "neem oil") are why this is substring matching against the lowered text and not a token
    set."""
    lowered = text.lower()
    return sorted(n for n in names if n in lowered)


def unknown_actives(text: str, known: list[str]) -> list[str]:
    """Words shaped like an active ingredient that the allowlist does not contain."""
    known_words = {w for name in known for w in name.split()}
    return sorted({m.group(0).lower() for m in ACTIVE_RE.finditer(text)} - known_words)


def doses(text: str, known: list[str]) -> list[tuple[str | None, float, float, str]]:
    """(chemical, low, high, unit) for each dose in the sentence.

    The chemical is whichever allowlisted name most recently preceded the number, which is how
    these sentences are actually written: "mancozeb 75 percent WP at 2.0 to 2.5 grams per
    litre". A dose with no chemical before it returns None and is reported, not ignored —
    a bare number attached to nothing is not a thing to wave through.
    """
    lowered = text.lower()
    positions = sorted(
        (m.start(), name)
        for name in mentioned(text, known)
        for m in re.finditer(re.escape(name), lowered)
    )
    out = []
    for match in DOSE_RE.finditer(lowered):
        before = [name for pos, name in positions if pos < match.start()]
        low = float(match.group(1))
        out.append((before[-1] if before else None, low, float(match.group(2) or low), _unit(match.group(3))))
    return out

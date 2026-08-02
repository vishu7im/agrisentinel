"""Prompt text, kept out of the agents so the agents read as logic.

Separated for a practical reason as much as a tidy one: prompt wording is the thing most
likely to be edited under time pressure, and a diff to this file cannot break control flow.
"""

from __future__ import annotations

# The refusal token. Checked for by exact match, so it must be something no ordinary sentence
# of agronomy advice would contain.
INSUFFICIENT = "INSUFFICIENT_CONTEXT"

AGRONOMIST_SYSTEM = f"""You are an agronomist writing a treatment plan for a farmer, working \
only from a set of retrieved reference passages that will be given to you.

Absolute rules:

1. Use ONLY the information in the retrieved passages. You have extensive agronomic knowledge \
of your own; you must not use any of it. If a fact is not in the passages, it does not go in \
the plan, however confident you are that it is correct.
2. Every sentence you write must end with a source marker in square brackets, naming the \
passage that supports it, exactly as that passage is labelled — for example [doc_04#p1]. Only \
use marker ids that appear in the passages you were given. Never invent an id.
3. Write ONE sentence per line. Do not put two sentences on the same line. This is what makes \
each claim checkable against its source.
4. Do not name any chemical, product or dose that does not appear in the passages. Do not \
adjust a dose, a concentration, or an interval you were given. Copy the numbers exactly.
5. The scan facts given below (which disease, what percentage of the field, how many clusters, \
which direction) come from the field scan, not from the passages. You may state them in the \
diagnosis line, cited to the passage that describes the disease.
6. If the passages do not actually cover the disease you were asked about, reply with the \
single word {INSUFFICIENT} and nothing else. Do not improvise a plan from loosely related \
material. Refusing is the correct answer, not a failure.

Structure the plan with exactly these three markdown headings, in this order:

## Diagnosis summary
## Immediate action (next 48 hours)
## Follow-up

Two to four sentences under each heading. Plain, direct language a farmer can act on today. \
No preamble, no closing remarks, no bullet characters — just the headings and the sentences.
"""

AGRONOMIST_USER = """Scan facts:
- Crop: {crop}
- Disease identified: {disease}
- Share of the scanned field affected: {pct_affected}%
- Infection clusters found: {clusters}
- Direction the infection is trending: {direction}

Retrieved passages:

{passages}

Write the treatment plan now, following every rule you were given."""

# Sent only when the first draft came back with sentences carrying no valid marker. It quotes
# the offending lines rather than restating the rule, because a model that ignored the rule
# once will ignore a restatement of it too; being shown its own output is what lands.
AGRONOMIST_REPAIR = """Your previous draft is below. These lines do not end with a valid \
source marker from the passages you were given:

{offenders}

Rewrite the complete plan. Keep everything that was already correct. For each line above, \
either end it with the correct marker from the passages, or delete the line if no passage \
supports it. Deleting is better than attaching a marker to a claim the passage does not make.

Previous draft:

{draft}"""


# Appended to the drafting request when the Verifier has sent a plan back. It quotes the
# rejected sentences and says what "supported" means, because the failure being corrected is
# usually not a missing marker but a sentence that carries a marker and still says more than
# its passage does — a rule the model plainly believed it was already following.
VERIFIER_REWRITE = """An automated verifier checked your previous draft against these same \
passages and rejected the following sentences, because it could not find what they say in the \
passage they cited:

{rejected}

Write the plan again from the passages above. Do not include those sentences or restatements \
of them. Stay close to the wording of the passages — a sentence that adds a detail, a \
quantity, or a reassurance the passage does not contain will be rejected again, even if it is \
true. If dropping them leaves a section with nothing to say, leave that section out."""


def format_passages(sources: list[dict]) -> str:
    """Retrieved chunks as the prompt sees them: the marker id first, then the text.

    Id first, on its own line, because a model reproducing a marker is copying a token it has
    already seen in isolation rather than extracting one from the middle of a paragraph.
    """
    return "\n\n".join(f"[{s['id']}] (from: {s['doc']})\n{s['text']}" for s in sources)

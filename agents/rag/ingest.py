"""Chunk the markdown corpus into citable pieces.

    .venv/bin/python -m agents.rag.ingest          # rebuild agents/rag/index/chunks.json
    .venv/bin/python -m agents.rag.ingest --show   # ...and print what it built

Output is JSON, not a pickled vector store, and that is deliberate. The expensive-in-principle
step here is deciding where a chunk begins and ends; vectorising sixty short chunks takes
about four milliseconds, so retrieve.py does that at load time instead of persisting it.
What is left on disk is therefore the one artefact worth reviewing — plain text, diffable in a
pull request, and readable by a human who wants to know what the Agronomist was allowed to
see. A pickle would be neither.

**A chunk is a section.** Corpus files are written with `## ` headings at roughly a page of
prose each, and a section is a self-contained unit of advice — splitting one at a fixed token
count would cut a dosage away from the product it belongs to, and that is precisely the pair
the Verifier in A7 has to check together. Sections longer than MAX_WORDS are split with
overlap as a backstop, but the corpus is authored so that this rarely fires.

**Page numbers are chunk ordinals.** Markdown has no pages. Numbering the chunks 1, 2, 3
within a document gives the schema the integer it requires and says something true; inventing
page 47 of a document that was never printed would make the citation look authoritative and
be a fabrication.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

RAG_ROOT = Path(__file__).resolve().parent
CORPUS_DIR = RAG_ROOT / "corpus"
INDEX_DIR = RAG_ROOT / "index"
CHUNKS_PATH = INDEX_DIR / "chunks.json"

# ~500 tokens of English prose is roughly 380 words. The backstop split, not the normal path.
MAX_WORDS = 380
OVERLAP_WORDS = 60

# doc_04_tomato_late_blight.md -> doc_04. The id is in the filename rather than in front
# matter so that renaming a file can never silently re-point every citation in the corpus.
FILENAME_RE = re.compile(r"^(doc_\d+)_")

# Which crops a document applies to, taken from its title. An empty list means it applies to
# all of them — spray practice and resistance management do not care what is in the ground.
#
# This exists because lexical scoring got it wrong in a way worth recording. Asked for "tomato
# late blight", TF-IDF returned the *potato* document: doc_04's prose opens "Late blight,
# caused by Phytophthora infestans" and never repeats the crop name, while doc_08 says
# "tomato" three times explaining that the two crops infect each other. Both documents are
# written correctly; the ranking was reading mentions of a crop as being about that crop.
# The crop is known exactly, from state.crop, so it is a filter and not a scoring hint.
CROP_KEYWORDS = {"tomato": ("tomato",), "potato": ("potato",), "corn": ("corn", "maize")}
# "Solanaceous" names a family, not a crop, and the classifier only emits two of its members.
SOLANACEOUS = ("tomato", "potato")


def crops_for(title: str) -> list[str]:
    lowered = title.lower()
    if "solanaceous" in lowered:
        return list(SOLANACEOUS)
    return sorted(c for c, words in CROP_KEYWORDS.items() if any(w in lowered for w in words))


@dataclass(frozen=True)
class Chunk:
    id: str  # "doc_04#p1" — the marker that appears inline in plan_draft
    doc_id: str
    doc: str  # human-readable title, shown in the UI source drawer
    page: int
    heading: str
    text: str
    crops: list[str]  # empty = applies to every crop


def split_sections(body: str) -> list[tuple[str, str]]:
    """Markdown body -> [(heading, prose)], one entry per `## ` section."""
    sections: list[tuple[str, str]] = []
    heading, buffer = "", []
    for line in body.splitlines():
        if line.startswith("## "):
            if buffer:
                sections.append((heading, "\n".join(buffer).strip()))
            heading, buffer = line[3:].strip(), []
        else:
            buffer.append(line)
    if buffer:
        sections.append((heading, "\n".join(buffer).strip()))
    return [(h, t) for h, t in sections if t]


def split_long(text: str, max_words: int = MAX_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    """Backstop for an oversized section: fixed-size windows with overlap.

    The overlap exists so a sentence sitting on a boundary is fully present in at least one
    window — a claim cut in half is a claim that cannot be verified against either piece.
    """
    words = text.split()
    if len(words) <= max_words:
        return [text]
    step = max_words - overlap
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), step) if words[i:i + 1]]


def chunk_document(path: Path) -> list[Chunk]:
    match = FILENAME_RE.match(path.name)
    if not match:
        raise ValueError(f"{path.name} does not start with a doc id like 'doc_04_'")
    doc_id = match.group(1)

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ValueError(f"{path.name} must open with a '# Title' line")
    title = lines[0][2:].strip()
    crops = crops_for(title)

    chunks, page = [], 0
    for heading, prose in split_sections("\n".join(lines[1:])):
        for piece in split_long(prose):
            page += 1
            chunks.append(
                Chunk(
                    id=f"{doc_id}#p{page}",
                    doc_id=doc_id,
                    doc=title,
                    page=page,
                    heading=heading,
                    # Collapse to one line: the chunk text is rendered verbatim in the UI
                    # source drawer, where markdown line breaks would show as ragged wrapping.
                    text=" ".join(piece.split()),
                    crops=crops,
                )
            )
    return chunks


def build(corpus_dir: Path = CORPUS_DIR) -> list[Chunk]:
    """Every doc_*.md in the corpus, chunked, sorted by id so the output is reproducible."""
    paths = sorted(p for p in corpus_dir.glob("doc_*.md"))
    if not paths:
        raise FileNotFoundError(f"no doc_*.md files in {corpus_dir}")
    chunks = [c for path in paths for c in chunk_document(path)]
    return sorted(chunks, key=lambda c: (c.doc_id, c.page))


def write_index(chunks: list[Chunk], path: Path = CHUNKS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"n_docs": len({c.doc_id for c in chunks}), "chunks": [asdict(c) for c in chunks]}
    # No build timestamp on purpose: it would make every rebuild a diff even when the corpus
    # is unchanged, which trains people to stop reading the diff.
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk the agronomy corpus for retrieval.")
    parser.add_argument("--show", action="store_true", help="print every chunk id and heading")
    args = parser.parse_args()

    chunks = build()
    path = write_index(chunks)
    words = sum(len(c.text.split()) for c in chunks)
    print(f"{len(chunks)} chunks from {len({c.doc_id for c in chunks})} documents -> {path}")
    print(f"words: {words} total, {words // len(chunks)} mean, {max(len(c.text.split()) for c in chunks)} max")
    if args.show:
        for c in chunks:
            print(f"  {c.id:<12} {','.join(c.crops) or 'all':<14} {c.heading[:44]:<46} {c.doc}")


if __name__ == "__main__":
    main()

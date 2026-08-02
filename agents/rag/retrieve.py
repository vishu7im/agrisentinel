"""Search the chunked corpus. TF-IDF, cosine similarity, no network and no model download.

    from agents.rag.retrieve import retriever
    hits = retriever().search("tomato late blight chemical control", k=4)

**Why TF-IDF and not embeddings.** Dense embeddings earn their keep when the query and the
document say the same thing in different words. This corpus is the opposite case: it is 49
chunks of a narrow technical vocabulary, and the query is built from a classifier label —
"tomato late blight" — against documents that use those exact words because they are the
names of the things. Lexical overlap is not a weak proxy for relevance here, it is relevance.
Against that, sentence-transformers plus FAISS is half a gigabyte of download and a model
that must be present on a venue laptop with no reliable network.

It also buys something A7 needs: the score is a deterministic function of two strings, so the
Verifier's grounding check gives the same answer on the same input every time, and a run can
be replayed from a stored state and audited. An embedding model behind a version number does
not offer that.

The interface is deliberately narrow — `search`, `search_multi`, `similarity`, `to_sources` —
so swapping in a dense retriever later is one file, not a refactor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

from agents.rag.ingest import CHUNKS_PATH

# A weak pre-filter against ranking noise, and deliberately NOT the coverage test.
#
# Measured over 18 in-domain queries and 6 out-of-domain ones, the two populations overlap:
# in-domain top-1 ran 0.110 to 0.34 (median 0.229) while out-of-domain reached 0.104 —
# "rice blast paddy nitrogen top dressing" scores that well because "nitrogen" appears in two
# tomato documents discussing susceptibility. There is no cut here that admits every real
# query and rejects every foreign one, and picking 0.10 anyway would have produced a threshold
# that looked principled and was worth nothing.
#
# So the floor is set low, where it only discards chunks sharing a single stopword-adjacent
# term, and the Agronomist decides coverage a different way: it checks that the disease it was
# actually given is named in the retrieved text. See agents/agronomist.py.
MIN_RELEVANCE = 0.05

DEFAULT_K = 4


@dataclass(frozen=True)
class Hit:
    id: str
    doc: str
    page: int
    heading: str
    text: str
    score: float

    def source(self) -> dict:
        """The schema shape for verification.sources[] — id, doc, page, text, nothing else."""
        return {"id": self.id, "doc": self.doc, "page": self.page, "text": self.text}


class Retriever:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        # Bigrams matter more than usual here: "late blight" and "leaf blight" share a unigram
        # and are different diseases, and "leaf mold" against "leaf spot" is the same trap.
        # sublinear_tf keeps a chunk that repeats "blight" six times from dominating one that
        # says it twice and is actually about the treatment.
        self._vectorizer = TfidfVectorizer(
            sublinear_tf=True,
            stop_words="english",
            ngram_range=(1, 2),
            lowercase=True,
        )
        # Title and heading are prepended to the chunk's own text. The heading is what makes
        # "chemical control" in a query pull the section that is *about* chemical control
        # rather than one that merely mentions a product. The title carries facts the prose
        # leaves implicit: doc_04's body says "Late blight, caused by Phytophthora infestans"
        # and never repeats the crop, because a document titled "Tomato Late Blight" has no
        # reason to. Without the title in the indexed text that chunk scored below the
        # relevance floor for the query "tomato late blight" — the single most obvious query
        # this corpus will ever be asked.
        self._matrix = self._vectorizer.fit_transform(
            f"{c['doc']}. {c['heading']}. {c['text']}" for c in chunks
        )

    def _allowed(
        self,
        index: int,
        crop: str | None,
        require: str | None,
        exclude: tuple[str, ...],
        agnostic_only: bool,
    ) -> bool:
        """Is this chunk in scope: right crop, about the right subject, not about another one.

        Hard filters, not score penalties, and each was added after watching ranking alone get
        it wrong in a way a citation could not warn anyone about — a plan that is fluent, cited
        and about the wrong thing.

        `crop`: asked about tomato late blight, pure lexical ranking returned the *potato*
        document, whose chemical section recommends earthing up to protect tubers. Correctly
        retrieved, correctly cited, useless to someone growing tomatoes.

        `require`, matched against **title and heading only, never the body**: constrained to
        tomato, ranking then cited the tomato *early* blight document for a late blight
        diagnosis. Body containment does not fix that, because the early blight document
        legitimately says "Unlike late blight it begins on the oldest, lowest leaves" — a
        contrastive mention, which body matching reads as aboutness. A document is about what
        it is titled, not what its prose mentions in passing. Title counts as well as heading
        because doc_04's chemical section never repeats the disease name: it has no reason to,
        being a section of a document called "Tomato Late Blight".

        `exclude`: the other diseases, matched against the heading only. One document may
        cover three — doc_10 is titled for all three corn diseases — so the title admits every
        section of it and the heading is what says which disease a given section is about. A
        section headed "Gray leaf spot" is not first-response advice for northern leaf blight,
        however well it scores when the document has no first-response section to offer.

        `agnostic_only`: for the questions that are not about a disease at all — how to hold a
        sprayer, why to rotate a mode of action — restrict to the crop-agnostic documents that
        exist to answer them. Without it, a late blight run pulled the septoria document's
        chemical section into its sources on the strength of the phrase "leaf underside": a
        different disease's dosing advice, sitting in the drawer of a plan that is not about
        it. Sources may still legitimately go uncited — retrieval returns two per section and
        the drafter uses one — but they should at least be about the right disease.
        """
        chunk = self.chunks[index]
        heading = chunk["heading"].lower()
        crops = chunk.get("crops") or []
        if agnostic_only:
            return not crops
        if require and require.lower() not in f"{chunk['doc']} {heading}".lower():
            return False
        if any(other in heading for other in exclude):
            return False
        return crop is None or not crops or crop in crops

    def search(
        self,
        query: str,
        k: int = DEFAULT_K,
        min_score: float = MIN_RELEVANCE,
        crop: str | None = None,
        require: str | None = None,
        exclude: tuple[str, ...] = (),
        agnostic_only: bool = False,
    ) -> list[Hit]:
        """Top-k chunks above min_score, best first. Empty list means the corpus does not cover it."""
        if not query.strip():
            return []
        # TfidfVectorizer L2-normalises its rows, so this dot product is already the cosine.
        scores = (self._matrix @ self._vectorizer.transform([query]).T).toarray().ravel()
        eligible = [
            i for i in range(len(scores))
            if self._allowed(i, crop, require, exclude, agnostic_only)
        ]
        ranked = sorted(eligible, key=lambda i: -scores[i])[:k]
        return [
            Hit(
                id=self.chunks[i]["id"],
                doc=self.chunks[i]["doc"],
                page=self.chunks[i]["page"],
                heading=self.chunks[i]["heading"],
                text=self.chunks[i]["text"],
                score=round(float(scores[i]), 4),
            )
            for i in ranked
            if scores[i] >= min_score
        ]

    def similarity(self, text: str, chunk_id: str) -> float:
        """Cosine between an arbitrary sentence and one known chunk.

        Not used by the Agronomist. This is the hook A7's grounding check needs: given a
        sentence from the draft and the chunk it cites, how much of it is actually there.
        """
        row = next((i for i, c in enumerate(self.chunks) if c["id"] == chunk_id), None)
        if row is None:
            return 0.0
        return round(float((self._matrix[row] @ self._vectorizer.transform([text]).T).toarray()[0][0]), 4)

    def chunk(self, chunk_id: str) -> dict | None:
        return next((c for c in self.chunks if c["id"] == chunk_id), None)

    @property
    def ids(self) -> set[str]:
        return {c["id"] for c in self.chunks}


def load_chunks(path: Path = CHUNKS_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing — run: .venv/bin/python -m agents.rag.ingest"
        )
    return json.loads(path.read_text(encoding="utf-8"))["chunks"]


@lru_cache(maxsize=1)
def retriever(path: Path = CHUNKS_PATH) -> Retriever:
    """Process-wide singleton. Fitting 49 chunks costs a few milliseconds, but the API would
    otherwise pay it on every request, and it is pure waste over an unchanging corpus."""
    return Retriever(load_chunks(path))


def to_sources(hits: list[Hit]) -> list[dict]:
    """Hits -> verification.sources[], ordered by id so the UI drawer lists them predictably."""
    return [h.source() for h in sorted(hits, key=lambda h: h.id)]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Query the agronomy corpus.")
    parser.add_argument("query", nargs="+")
    parser.add_argument("-k", type=int, default=DEFAULT_K)
    parser.add_argument("--crop", default=None, help="tomato | potato | corn — filter by crop")
    args = parser.parse_args()

    hits = retriever().search(" ".join(args.query), k=args.k, crop=args.crop)
    if not hits:
        print("no chunk above the relevance floor — the corpus does not cover this")
    for hit in hits:
        print(f"{hit.score:.3f}  {hit.id:<12} {hit.doc[:40]:<42} {hit.heading}")


if __name__ == "__main__":
    main()

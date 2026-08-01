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

    def _haystack(self, index: int) -> str:
        chunk = self.chunks[index]
        return f"{chunk['doc']} {chunk['heading']} {chunk['text']}".lower()

    def _allowed(self, index: int, crop: str | None, require: str | None) -> bool:
        """A chunk is in scope if it is crop-agnostic or names this crop, and, when `require`
        is given, if it names that subject too.

        Hard filters, not score penalties, and both were added after watching ranking alone
        get it wrong. Asked about tomato late blight, pure lexical ranking returned the potato
        document, whose chemical section recommends earthing up to protect tubers — grounded,
        cited, and useless to someone growing tomatoes. Constrained to tomato, it then returned
        the tomato *early* blight document for a late blight diagnosis, because "early blight"
        and "late blight" share a word and a document title full of "identification" outranks
        the difference. Both mistakes produce a plan that is fluent, cited, and about the wrong
        thing, which is the failure mode a citation is least able to warn anyone about.

        `require` matches against title and heading as well as body: doc_04's chemical section
        never repeats "late blight" because it is a section of a document titled "Tomato Late
        Blight", and demanding the phrase in the body alone would reject the single most
        relevant chunk in the corpus.
        """
        if require and require.lower() not in self._haystack(index):
            return False
        crops = self.chunks[index].get("crops") or []
        return crop is None or not crops or crop in crops

    def search(
        self,
        query: str,
        k: int = DEFAULT_K,
        min_score: float = MIN_RELEVANCE,
        crop: str | None = None,
        require: str | None = None,
    ) -> list[Hit]:
        """Top-k chunks above min_score, best first. Empty list means the corpus does not cover it."""
        if not query.strip():
            return []
        # TfidfVectorizer L2-normalises its rows, so this dot product is already the cosine.
        scores = (self._matrix @ self._vectorizer.transform([query]).T).toarray().ravel()
        eligible = [i for i in range(len(scores)) if self._allowed(i, crop, require)]
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

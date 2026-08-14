"""BGE-compatible reranking port and a deterministic local placeholder."""

from typing import Callable, List, Protocol, Sequence

from .types import FusedHit


class Reranker(Protocol):
    def rerank(self, query_text: str, hits: Sequence[FusedHit], top_k: int) -> List[float]:
        ...


class PassThroughReranker:
    """Keeps RRF order for smoke tests; replace with a BGE scoring adapter in production."""

    def rerank(self, query_text: str, hits: Sequence[FusedHit], top_k: int) -> List[float]:
        del query_text
        return [hit.rrf_score for hit in hits[:top_k]]


class CallableCrossEncoderReranker:
    """Uses an injected BGE/cross-encoder scoring function without owning model lifecycle."""

    def __init__(self, score: Callable[[str, str], float]):
        self._score = score

    def rerank(self, query_text: str, hits: Sequence[FusedHit], top_k: int) -> List[float]:
        return [
            self._score(query_text, hit.document.provision_text)
            for hit in hits[:top_k]
        ]

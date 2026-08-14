"""BGE-compatible reranking port and a deterministic local placeholder."""

from pathlib import Path
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


class LocalBgeCrossEncoderReranker:
    """Run a downloaded Sentence Transformers-compatible BGE reranker."""

    def __init__(self, model_path: Path, device: str = "cuda", batch_size: int = 32):
        if not model_path.is_dir():
            raise FileNotFoundError("local BGE reranker model is missing: %s" % model_path)
        if batch_size < 1:
            raise ValueError("BGE reranker batch_size must be positive")
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError("install sentence-transformers to use the local BGE reranker") from exc
        self.model = CrossEncoder(str(model_path), device=device)
        self.batch_size = batch_size

    def rerank(self, query_text: str, hits: Sequence[FusedHit], top_k: int) -> List[float]:
        selected_hits = hits[:top_k]
        if not selected_hits:
            return []
        scores = self.model.predict(
            [(query_text, hit.document.provision_text) for hit in selected_hits],
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        return [float(score) for score in scores]

"""BGE-compatible reranking port and a deterministic local placeholder."""

from pathlib import Path
from typing import Callable, List, Protocol, Sequence

from .corpus import ProvisionDocument
from .types import FusedHit


RERANK_DOCUMENT_MODES = frozenset({"body_only", "statute_and_body"})


def render_rerank_document(
    document: ProvisionDocument,
    mode: str = "body_only",
) -> str:
    """Render one provision for a cross-encoder under a frozen input mode."""
    if mode not in RERANK_DOCUMENT_MODES:
        raise ValueError("unsupported rerank document mode: %s" % mode)
    if mode == "statute_and_body":
        return "%s\n%s" % (document.statute_name, document.provision_text)
    return document.provision_text


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

    def __init__(
        self,
        score: Callable[[str, str], float],
        document_mode: str = "body_only",
    ):
        self._score = score
        if document_mode not in RERANK_DOCUMENT_MODES:
            raise ValueError("unsupported rerank document mode: %s" % document_mode)
        self.document_mode = document_mode

    def rerank(self, query_text: str, hits: Sequence[FusedHit], top_k: int) -> List[float]:
        return [
            self._score(
                query_text,
                render_rerank_document(hit.document, self.document_mode),
            )
            for hit in hits[:top_k]
        ]


class LocalBgeCrossEncoderReranker:
    """Run a downloaded Sentence Transformers-compatible BGE reranker."""

    def __init__(
        self,
        model_path: Path,
        device: str = "cuda",
        batch_size: int = 32,
        document_mode: str = "body_only",
    ):
        if not model_path.is_dir():
            raise FileNotFoundError("local BGE reranker model is missing: %s" % model_path)
        if batch_size < 1:
            raise ValueError("BGE reranker batch_size must be positive")
        if document_mode not in RERANK_DOCUMENT_MODES:
            raise ValueError("unsupported rerank document mode: %s" % document_mode)
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError("install sentence-transformers to use the local BGE reranker") from exc
        self.model = CrossEncoder(str(model_path), device=device)
        self.batch_size = batch_size
        self.document_mode = document_mode

    def rerank(self, query_text: str, hits: Sequence[FusedHit], top_k: int) -> List[float]:
        selected_hits = hits[:top_k]
        if not selected_hits:
            return []
        scores = self.model.predict(
            [
                (
                    query_text,
                    render_rerank_document(hit.document, self.document_mode),
                )
                for hit in selected_hits
            ],
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        return [float(score) for score in scores]

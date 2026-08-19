"""BM25 (bm25s) + CrossEncoder retrieval, matching the official ParSeR
`experiments/parser/vllm/utils.py` and `selection_retrieval.py` exactly:

  statute = [item['hierarchy'] + item['content'] for item in raw_items]
  corpus_tokens = bm25s.tokenize(statute, stopwords="en", show_progress=False)
  retriever = bm25s.BM25(); retriever.index(corpus_tokens, ...)
  ... per sub-query: retriever.retrieve(bm25s.tokenize([sq]), k=100)
  reranker = CrossEncoder(model, default_activation_function=torch.nn.Sigmoid())

This project's own retriever stack (retrieval/persistent.py, an FTS5 SQLite
BM25 index) is deliberately NOT reused here -- ParSeR's own retrieval
implementation (bm25s library, English-stopword tokenization applied to
Korean text, exactly as released) is part of what is being reproduced.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

import bm25s
import pyarrow.parquet as pq


@dataclass(frozen=True)
class StatuteRecord:
    index: str
    hierarchy: str
    content: str

    @property
    def text(self) -> str:
        return self.hierarchy + self.content


def load_statute_corpus(parquet_path: Path) -> List[StatuteRecord]:
    table = pq.read_table(str(parquet_path))
    columns = {name: table.column(name).to_pylist() for name in ("index", "hierarchy", "content")}
    n = len(columns["index"])
    return [
        StatuteRecord(index=columns["index"][i], hierarchy=columns["hierarchy"][i], content=columns["content"][i])
        for i in range(n)
    ]


class Bm25Retriever:
    """Thin wrapper matching `get_statute_retriever` from the official utils.py."""

    def __init__(self, records: List[StatuteRecord]):
        self.records = records
        texts = [record.text for record in records]
        build_start = time.monotonic()
        corpus_tokens = bm25s.tokenize(texts, stopwords="en", show_progress=False)
        self._retriever = bm25s.BM25()
        self._retriever.index(corpus_tokens, show_progress=False)
        self.build_seconds = time.monotonic() - build_start

    def top_k(self, query: str, k: int = 100) -> List[int]:
        tokens = bm25s.tokenize([query], show_progress=False)
        idxs, _scores = self._retriever.retrieve(tokens, k=k, show_progress=False)
        return [int(i) for i in idxs[0]]


class CrossEncoderReranker:
    """Matches `get_reranker()` in the official utils.py."""

    def __init__(self, model_path: Path, device: str = "cuda", batch_size: int = 50):
        import torch
        from sentence_transformers import CrossEncoder

        if not model_path.is_dir():
            raise FileNotFoundError("local BGE reranker model is missing: %s" % model_path)
        self.model = CrossEncoder(
            str(model_path),
            default_activation_function=torch.nn.Sigmoid(),
            device=device,
        )
        self.batch_size = batch_size

    def rerank(self, query: str, candidate_texts: List[str]) -> List[str]:
        """Return candidate_texts sorted by descending relevance score."""
        if not candidate_texts:
            return []
        pairs = [(query, text) for text in candidate_texts]
        scores = self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        ranked = sorted(zip(scores, candidate_texts), key=lambda pair: pair[0], reverse=True)
        return [text for _score, text in ranked]

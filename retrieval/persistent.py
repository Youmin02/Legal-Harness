"""Search adapters for the on-disk KoBLEX BM25 and KURE exact indexes."""

import sqlite3
from pathlib import Path
from typing import Dict, List, Sequence

from harness.contracts import RetrievalRequest

from .bm25 import baseline_korean_tokenize
from .corpus import InMemoryProvisionCorpus, ProvisionDocument
from .types import RetrievalHit


class SqliteFts5Bm25Searcher:
    """Read-only BM25 search over the reproducible SQLite FTS5 artifact."""

    def __init__(self, database_path: Path):
        if not database_path.is_file():
            raise FileNotFoundError("BM25 index is missing: %s" % database_path)
        self.database_path = database_path

    def search(self, request: RetrievalRequest) -> List[RetrievalHit]:
        terms = baseline_korean_tokenize(request.query_text)
        if not terms:
            return []
        # Tokenizer output is restricted to letters and numbers, making each
        # quoted literal safe for FTS5. OR implements the frozen multi-channel
        # recall-first Top-100 stage rather than requiring every keyword.
        match_expression = " OR ".join('"%s"' % term for term in terms)
        connection = sqlite3.connect("file:%s?mode=ro" % self.database_path, uri=True)
        try:
            rows = connection.execute(
                "SELECT provision_id, statute_name, provision_text, -bm25(provision_fts) AS score "
                "FROM provision_fts WHERE provision_fts MATCH ? "
                "ORDER BY score DESC, provision_id ASC LIMIT ?",
                (match_expression, request.top_k),
            ).fetchall()
        finally:
            connection.close()
        return [
            RetrievalHit(
                document=ProvisionDocument(provision_id=provision_id, statute_name=statute_name, provision_text=provision_text),
                score=float(score),
                source_request_id=request.request_id,
            )
            for provision_id, statute_name, provision_text, score in rows
        ]


class KureExactIndexSearcher:
    """GPU exact cosine search over a normalized KURE vector matrix.

    The full 233,544 x 1,024 float32 matrix is about 0.9 GB and fits
    comfortably on the H200. It is loaded into GPU once at construction, then
    every query is a full matrix-vector product rather than approximate ANN.
    """

    def __init__(
        self,
        vectors_path: Path,
        provision_ids_path: Path,
        normalized_corpus_path: Path,
        model_path: Path,
        device: str = "cuda",
    ):
        try:
            import numpy as np
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("install the project GPU retrieval dependencies first") from exc
        if not all(path.is_file() for path in (vectors_path, provision_ids_path, normalized_corpus_path)):
            raise FileNotFoundError("KURE vectors, ID mapping, and normalized corpus are required")
        if not model_path.is_dir():
            raise FileNotFoundError("local KURE model is missing: %s" % model_path)

        vectors = np.load(vectors_path)
        with provision_ids_path.open("r", encoding="utf-8") as handle:
            provision_ids = [line.rstrip("\n") for line in handle]
        if vectors.shape[0] != len(provision_ids):
            raise ValueError("KURE vectors and provision IDs have different lengths")
        corpus = InMemoryProvisionCorpus.from_jsonl(normalized_corpus_path)
        documents = corpus.all()
        documents_by_id: Dict[str, object] = {
            document.provision_id: document for document in documents
        }
        if any(provision_id not in documents_by_id for provision_id in provision_ids):
            raise ValueError("KURE ID mapping references a missing normalized provision")

        self._torch = torch
        self.device = device
        self.model = SentenceTransformer(str(model_path), device=device)
        self.provision_ids = provision_ids
        self.documents_by_id = documents_by_id
        self.vectors = torch.from_numpy(vectors).to(device=device, dtype=torch.float32)

    def search(self, request: RetrievalRequest) -> List[RetrievalHit]:
        query = self.model.encode(
            [request.query_text],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        query_tensor = self._torch.as_tensor(query, dtype=self._torch.float32, device=self.device)
        top_k = min(request.top_k, len(self.provision_ids))
        scores, indexes = self._torch.topk(self.vectors @ query_tensor, k=top_k)
        return [
            RetrievalHit(
                document=self.documents_by_id[self.provision_ids[index]],
                score=float(score),
                source_request_id=request.request_id,
            )
            for score, index in zip(scores.detach().cpu().tolist(), indexes.detach().cpu().tolist())
        ]

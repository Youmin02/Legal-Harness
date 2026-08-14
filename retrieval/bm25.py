"""A dependency-free BM25 baseline with a replaceable Korean tokenizer."""

import math
import re
from collections import Counter
from typing import Callable, Dict, Iterable, List, Sequence

from harness.contracts import RetrievalRequest

from .corpus import InMemoryProvisionCorpus, ProvisionDocument
from .types import RetrievalHit


Tokenizer = Callable[[str], Sequence[str]]


def baseline_korean_tokenize(text: str) -> List[str]:
    """Stable lexical fallback; production may inject a legal Korean analyzer."""
    return re.findall(r"[가-힣A-Za-z0-9]+", text.casefold())


class Bm25Retriever:
    def __init__(
        self,
        corpus: InMemoryProvisionCorpus,
        tokenizer: Tokenizer = baseline_korean_tokenize,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("BM25 requires k1 > 0 and 0 <= b <= 1")
        self.corpus = corpus
        self.tokenizer = tokenizer
        self.k1 = k1
        self.b = b
        self._documents = corpus.all()
        self._term_frequencies: Dict[str, Counter] = {}
        self._document_lengths: Dict[str, int] = {}
        document_frequency: Counter = Counter()
        for document in self._documents:
            tokens = list(tokenizer("%s %s" % (document.statute_name, document.provision_text)))
            term_frequency = Counter(tokens)
            self._term_frequencies[document.provision_id] = term_frequency
            self._document_lengths[document.provision_id] = len(tokens)
            document_frequency.update(term_frequency.keys())
        self._document_frequency = document_frequency
        self._average_length = (
            sum(self._document_lengths.values()) / len(self._documents)
            if self._documents
            else 0.0
        )

    def search(self, request: RetrievalRequest) -> List[RetrievalHit]:
        query_terms = list(self.tokenizer(request.query_text))
        if not query_terms or not self._documents:
            return []
        total_documents = len(self._documents)
        scored: List[RetrievalHit] = []
        for document in self._documents:
            term_frequency = self._term_frequencies[document.provision_id]
            document_length = self._document_lengths[document.provision_id]
            score = 0.0
            for term in query_terms:
                frequency = term_frequency.get(term, 0)
                if not frequency:
                    continue
                df = self._document_frequency[term]
                inverse_frequency = math.log(1.0 + (total_documents - df + 0.5) / (df + 0.5))
                normalization = frequency + self.k1 * (
                    1.0 - self.b + self.b * document_length / self._average_length
                )
                score += inverse_frequency * frequency * (self.k1 + 1.0) / normalization
            if score > 0.0:
                scored.append(
                    RetrievalHit(
                        document=document,
                        score=score,
                        source_request_id=request.request_id,
                    )
                )
        return sorted(scored, key=lambda hit: (-hit.score, hit.document.provision_id))[: request.top_k]

"""Frozen BM25-or-KURE -> within-retriever RRF -> rerank Top-10 pipeline."""

from collections import defaultdict
from typing import Dict, List, Protocol, Sequence

from harness.contracts import CandidateProvision, RetrievalRequest

from .reranker import Reranker
from .rrf import reciprocal_rank_fusion
from .types import RetrievalHit


class FirstStageSearcher(Protocol):
    def search(self, request: RetrievalRequest) -> List[RetrievalHit]:
        ...


class RetrievalPipeline:
    """Use exactly one first-stage searcher per experimental condition.

    The pipeline deliberately has one `first_stage` instance: BM25+KURE hybrid
    retrieval is excluded by the frozen study design.
    """

    def __init__(
        self,
        first_stage: FirstStageSearcher,
        reranker: Reranker = None,
        rrf_k: int = 60,
        rerank_top_k: int = 10,
    ):
        if rerank_top_k != 10:
            raise ValueError("the frozen rerank cutoff is Top-10")
        self.first_stage = first_stage
        if reranker is None:
            raise ValueError("a BGE-compatible reranker must be configured")
        self.reranker = reranker
        self.rrf_k = rrf_k
        self.rerank_top_k = rerank_top_k

    def retrieve(
        self,
        requests: Sequence[RetrievalRequest],
        retrieval_round: int,
    ) -> List[CandidateProvision]:
        requests_by_issue: Dict[str, List[RetrievalRequest]] = defaultdict(list)
        for request in requests:
            requests_by_issue[request.issue_id].append(request)
        candidates: List[CandidateProvision] = []
        for issue_id, issue_requests in sorted(requests_by_issue.items()):
            ranked_lists = [self.first_stage.search(request) for request in issue_requests]
            fused_hits = reciprocal_rank_fusion(ranked_lists, k=self.rrf_k)
            query_text = " ".join(request.query_text for request in issue_requests)
            rerank_scores = self.reranker.rerank(query_text, fused_hits, self.rerank_top_k)
            reranked = sorted(
                zip(fused_hits[: self.rerank_top_k], rerank_scores),
                key=lambda pair: (-pair[1], pair[0].document.provision_id),
            )
            for rerank_rank, (hit, rerank_score) in enumerate(reranked, start=1):
                candidates.append(
                    CandidateProvision(
                        provision_id=hit.document.provision_id,
                        statute_name=hit.document.statute_name,
                        provision_text=hit.document.provision_text,
                        issue_id=issue_id,
                        source_request_id=hit.source_request_ids[0],
                        retrieval_round=retrieval_round,
                        first_stage_score=hit.first_stage_score,
                        fusion_rank=rerank_rank,
                        rerank_score=rerank_score,
                    )
                )
        return candidates

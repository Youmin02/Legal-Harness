"""BM25-or-KURE -> within-retriever RRF -> broad-pool BGE reranking."""

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
        rerank_pool_k: int = 100,
        final_top_k: int = 10,
    ):
        if rerank_pool_k < 1 or final_top_k < 1:
            raise ValueError("rerank pool and final cutoff must be positive")
        if final_top_k > rerank_pool_k:
            raise ValueError("final cutoff cannot exceed the rerank pool")
        self.first_stage = first_stage
        if reranker is None:
            raise ValueError("a BGE-compatible reranker must be configured")
        self.reranker = reranker
        self.rrf_k = rrf_k
        self.rerank_pool_k = rerank_pool_k
        self.final_top_k = final_top_k

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
            rerank_pool = fused_hits[: self.rerank_pool_k]
            rerank_scores = self.reranker.rerank(
                query_text, rerank_pool, len(rerank_pool)
            )
            if len(rerank_scores) != len(rerank_pool):
                raise ValueError("reranker must score every hit in the rerank pool")
            reranked = sorted(
                zip(rerank_pool, rerank_scores),
                key=lambda pair: (-pair[1], pair[0].document.provision_id),
            )[: self.final_top_k]
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

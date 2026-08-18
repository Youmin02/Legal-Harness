"""BM25-or-KURE -> within-retriever RRF -> broad-pool BGE reranking."""

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Protocol, Sequence, Set, Tuple

from harness.contracts import (
    CandidateProvision,
    CandidateStageRecord,
    RetrievalRequest,
)

from .reranker import Reranker
from .rrf import reciprocal_rank_fusion
from .types import FusedHit, RetrievalHit


@dataclass(frozen=True)
class _RequestRerankObservation:
    hit: FusedHit
    rerank_score: float
    rerank_rank: int


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
        rerank_query_mode: str = "combined_issue",
        candidate_selection: str = "global_top_k",
        per_evidence_min_k: int = 1,
    ):
        if rrf_k < 1:
            raise ValueError("RRF k must be positive")
        if rerank_pool_k < 1 or final_top_k < 1:
            raise ValueError("rerank pool and final cutoff must be positive")
        if rerank_query_mode not in {"combined_issue", "per_request"}:
            raise ValueError("unsupported rerank query mode: %s" % rerank_query_mode)
        if candidate_selection not in {"global_top_k", "evidence_balanced"}:
            raise ValueError("unsupported candidate selection: %s" % candidate_selection)
        if per_evidence_min_k < 1:
            raise ValueError("per_evidence_min_k must be positive")
        if final_top_k > rerank_pool_k:
            raise ValueError("final cutoff cannot exceed the rerank pool")
        self.first_stage = first_stage
        if reranker is None:
            raise ValueError("a BGE-compatible reranker must be configured")
        self.reranker = reranker
        self.rrf_k = rrf_k
        self.rerank_pool_k = rerank_pool_k
        self.final_top_k = final_top_k
        self.rerank_query_mode = rerank_query_mode
        self.candidate_selection = candidate_selection
        self.per_evidence_min_k = per_evidence_min_k
        self.last_stage_records: List[CandidateStageRecord] = []
        self.last_unsatisfied_critical_evidence_item_ids: List[str] = []

    @staticmethod
    def _target_evidence_ids(
        source_request_ids: Sequence[str],
        requests_by_id: Dict[str, RetrievalRequest],
    ) -> List[str]:
        return list(
            dict.fromkeys(
                requests_by_id[request_id].evidence_item_id
                for request_id in source_request_ids
            )
        )

    def _rank_fuse_ids(
        self,
        ranked_id_lists: Sequence[Sequence[str]],
    ) -> List[Tuple[str, float]]:
        scores: Dict[str, float] = defaultdict(float)
        for ranked_ids in ranked_id_lists:
            seen: Set[str] = set()
            for rank, provision_id in enumerate(ranked_ids, start=1):
                if provision_id in seen:
                    continue
                seen.add(provision_id)
                scores[provision_id] += 1.0 / (self.rrf_k + rank)
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))

    def _rerank(
        self,
        query_text: str,
        pool: Sequence[FusedHit],
    ) -> List[Tuple[FusedHit, float]]:
        raw_scores = list(self.reranker.rerank(query_text, pool, len(pool)))
        if len(raw_scores) != len(pool):
            raise ValueError("reranker must score every hit in the rerank pool")
        scores: List[float] = []
        for raw_score in raw_scores:
            if isinstance(raw_score, bool):
                raise ValueError("reranker scores must be finite numbers")
            try:
                score = float(raw_score)
            except (TypeError, ValueError) as exc:
                raise ValueError("reranker scores must be finite numbers") from exc
            if not math.isfinite(score):
                raise ValueError("reranker scores must be finite numbers")
            scores.append(score)
        return sorted(
            zip(pool, scores),
            key=lambda pair: (-pair[1], pair[0].document.provision_id),
        )

    def _select_ids(
        self,
        global_ranking: Sequence[str],
        evidence_rankings: Dict[str, List[str]],
        critical_evidence_item_ids: Sequence[str],
    ) -> Tuple[List[str], Dict[str, str]]:
        if self.candidate_selection == "global_top_k":
            selected = list(global_ranking[: self.final_top_k])
            return selected, {
                provision_id: "global_top_k" for provision_id in selected
            }

        critical_ids = [
            evidence_id
            for evidence_id in evidence_rankings
            if evidence_id in set(critical_evidence_item_ids)
        ]
        evidence_members = {
            evidence_id: set(ranking)
            for evidence_id, ranking in evidence_rankings.items()
        }
        selected: List[str] = []
        quota_selected: Set[str] = set()
        for quota_target in range(1, self.per_evidence_min_k + 1):
            for evidence_id in critical_ids:
                current_count = sum(
                    provision_id in evidence_members[evidence_id]
                    for provision_id in selected
                )
                if current_count >= quota_target:
                    continue
                if len(selected) >= self.final_top_k:
                    continue
                provision_id = next(
                    (
                        candidate_id
                        for candidate_id in evidence_rankings[evidence_id]
                        if candidate_id not in selected
                    ),
                    None,
                )
                if provision_id is not None:
                    selected.append(provision_id)
                    quota_selected.add(provision_id)

        for provision_id in global_ranking:
            if len(selected) >= self.final_top_k:
                break
            if provision_id not in selected:
                selected.append(provision_id)

        unsatisfied = [
            evidence_id
            for evidence_id in critical_ids
            if sum(
                provision_id in evidence_members[evidence_id]
                for provision_id in selected
            ) < self.per_evidence_min_k
        ]
        self.last_unsatisfied_critical_evidence_item_ids.extend(unsatisfied)
        reasons: Dict[str, str] = {}
        for provision_id in selected:
            if provision_id in quota_selected:
                satisfied = [
                    evidence_id
                    for evidence_id in critical_ids
                    if provision_id in evidence_members[evidence_id]
                ]
                reasons[provision_id] = "critical_quota:%s" % ",".join(satisfied)
            else:
                reasons[provision_id] = "rank_fusion_fill"
        return selected, reasons

    def _record_first_stage(
        self,
        request: RetrievalRequest,
        hits: Sequence[RetrievalHit],
        retrieval_round: int,
    ) -> None:
        for first_stage_rank, hit in enumerate(hits, start=1):
            self.last_stage_records.append(
                CandidateStageRecord(
                    provision_id=hit.document.provision_id,
                    retrieval_round=retrieval_round,
                    candidate_stage="first_stage",
                    source_request_ids=[request.request_id],
                    target_evidence_item_ids=[request.evidence_item_id],
                    first_stage_rank=first_stage_rank,
                    first_stage_score=hit.score,
                    selection_reason="request_top_k",
                )
            )

    def _retrieve_combined_issue(
        self,
        issue_id: str,
        issue_requests: Sequence[RetrievalRequest],
        hits_by_request: Dict[str, List[RetrievalHit]],
        requests_by_id: Dict[str, RetrievalRequest],
        retrieval_round: int,
        critical_evidence_item_ids: Sequence[str],
    ) -> List[CandidateProvision]:
        fused_hits = reciprocal_rank_fusion(
            [hits_by_request[request.request_id] for request in issue_requests],
            k=self.rrf_k,
        )
        for hit in fused_hits[:100]:
            self.last_stage_records.append(
                CandidateStageRecord(
                    provision_id=hit.document.provision_id,
                    retrieval_round=retrieval_round,
                    candidate_stage="rrf",
                    source_request_ids=list(hit.source_request_ids),
                    target_evidence_item_ids=self._target_evidence_ids(
                        hit.source_request_ids, requests_by_id
                    ),
                    first_stage_rank=hit.first_stage_rank,
                    fusion_rank=hit.fusion_rank,
                    first_stage_score=hit.first_stage_score,
                    fusion_score=hit.rrf_score,
                    selection_reason="rrf_top_100",
                )
            )

        query_text = " ".join(request.query_text for request in issue_requests)
        reranked_all = self._rerank(
            query_text,
            fused_hits[: self.rerank_pool_k],
        )
        reranked_by_id: Dict[str, Tuple[FusedHit, float, int]] = {}
        for rerank_rank, (hit, rerank_score) in enumerate(reranked_all, start=1):
            reranked_by_id[hit.document.provision_id] = (
                hit,
                rerank_score,
                rerank_rank,
            )
            self.last_stage_records.append(
                CandidateStageRecord(
                    provision_id=hit.document.provision_id,
                    retrieval_round=retrieval_round,
                    candidate_stage="bge_rerank",
                    source_request_ids=list(hit.source_request_ids),
                    target_evidence_item_ids=self._target_evidence_ids(
                        hit.source_request_ids, requests_by_id
                    ),
                    first_stage_rank=hit.first_stage_rank,
                    fusion_rank=hit.fusion_rank,
                    rerank_rank=rerank_rank,
                    first_stage_score=hit.first_stage_score,
                    fusion_score=hit.rrf_score,
                    rerank_score=rerank_score,
                    selection_reason="rerank_pool",
                )
            )

        evidence_order = list(
            dict.fromkeys(request.evidence_item_id for request in issue_requests)
        )
        evidence_rankings = {
            evidence_id: [
                hit.document.provision_id
                for hit, _ in reranked_all
                if evidence_id
                in self._target_evidence_ids(hit.source_request_ids, requests_by_id)
            ]
            for evidence_id in evidence_order
        }
        global_ranking = [hit.document.provision_id for hit, _ in reranked_all]
        selected_ids, selection_reasons = self._select_ids(
            global_ranking,
            evidence_rankings,
            critical_evidence_item_ids,
        )

        candidates: List[CandidateProvision] = []
        for selection_rank, provision_id in enumerate(selected_ids, start=1):
            hit, rerank_score, rerank_rank = reranked_by_id[provision_id]
            source_request_ids = list(hit.source_request_ids)
            target_evidence_item_ids = self._target_evidence_ids(
                source_request_ids, requests_by_id
            )
            reason = selection_reasons[provision_id]
            candidate = CandidateProvision(
                provision_id=hit.document.provision_id,
                statute_name=hit.document.statute_name,
                provision_text=hit.document.provision_text,
                issue_id=issue_id,
                source_request_id=source_request_ids[0],
                retrieval_round=retrieval_round,
                first_stage_score=hit.first_stage_score,
                fusion_rank=hit.fusion_rank or 0,
                rerank_score=rerank_score,
                source_request_ids=source_request_ids,
                target_evidence_item_ids=target_evidence_item_ids,
                first_stage_rank=hit.first_stage_rank,
                rerank_rank=rerank_rank,
                selection_rank=selection_rank,
                candidate_stage="selected",
                selection_reason=reason,
            )
            candidates.append(candidate)
            self.last_stage_records.append(
                CandidateStageRecord(
                    provision_id=hit.document.provision_id,
                    retrieval_round=retrieval_round,
                    candidate_stage="selected",
                    source_request_ids=source_request_ids,
                    target_evidence_item_ids=target_evidence_item_ids,
                    first_stage_rank=hit.first_stage_rank,
                    fusion_rank=hit.fusion_rank,
                    rerank_rank=rerank_rank,
                    selection_rank=selection_rank,
                    first_stage_score=hit.first_stage_score,
                    fusion_score=hit.rrf_score,
                    rerank_score=rerank_score,
                    selection_reason=reason,
                )
            )
        return candidates

    def _retrieve_per_request(
        self,
        issue_id: str,
        issue_requests: Sequence[RetrievalRequest],
        hits_by_request: Dict[str, List[RetrievalHit]],
        requests_by_id: Dict[str, RetrievalRequest],
        retrieval_round: int,
        critical_evidence_item_ids: Sequence[str],
    ) -> List[CandidateProvision]:
        observations_by_request: Dict[
            str, Dict[str, _RequestRerankObservation]
        ] = {}
        ranked_ids_by_request: Dict[str, List[str]] = {}

        audit_fused_hits = reciprocal_rank_fusion(
            [hits_by_request[request.request_id] for request in issue_requests],
            k=self.rrf_k,
        )
        for hit in audit_fused_hits[:100]:
            self.last_stage_records.append(
                CandidateStageRecord(
                    provision_id=hit.document.provision_id,
                    retrieval_round=retrieval_round,
                    candidate_stage="rrf",
                    source_request_ids=list(hit.source_request_ids),
                    target_evidence_item_ids=self._target_evidence_ids(
                        hit.source_request_ids, requests_by_id
                    ),
                    first_stage_rank=hit.first_stage_rank,
                    fusion_rank=hit.fusion_rank,
                    first_stage_score=hit.first_stage_score,
                    fusion_score=hit.rrf_score,
                    selection_reason="audit_issue_rrf_top_100",
                )
            )

        for request in issue_requests:
            request_hits = reciprocal_rank_fusion(
                [hits_by_request[request.request_id]],
                k=self.rrf_k,
            )
            reranked = self._rerank(
                request.query_text,
                request_hits[: self.rerank_pool_k],
            )
            observations: Dict[str, _RequestRerankObservation] = {}
            ranked_ids: List[str] = []
            for rerank_rank, (hit, rerank_score) in enumerate(reranked, start=1):
                observation = _RequestRerankObservation(
                    hit=hit,
                    rerank_score=rerank_score,
                    rerank_rank=rerank_rank,
                )
                observations[hit.document.provision_id] = observation
                ranked_ids.append(hit.document.provision_id)
                self.last_stage_records.append(
                    CandidateStageRecord(
                        provision_id=hit.document.provision_id,
                        retrieval_round=retrieval_round,
                        candidate_stage="request_rerank",
                        source_request_ids=[request.request_id],
                        target_evidence_item_ids=[request.evidence_item_id],
                        first_stage_rank=hit.first_stage_rank,
                        fusion_rank=hit.fusion_rank,
                        rerank_rank=rerank_rank,
                        first_stage_score=hit.first_stage_score,
                        fusion_score=hit.rrf_score,
                        rerank_score=rerank_score,
                        selection_reason="request_rerank_pool",
                    )
                )
            observations_by_request[request.request_id] = observations
            ranked_ids_by_request[request.request_id] = ranked_ids

        evidence_order = list(
            dict.fromkeys(request.evidence_item_id for request in issue_requests)
        )
        evidence_rankings: Dict[str, List[str]] = {}
        for evidence_id in evidence_order:
            evidence_requests = [
                request
                for request in issue_requests
                if request.evidence_item_id == evidence_id
            ]
            fused = self._rank_fuse_ids(
                [
                    ranked_ids_by_request[request.request_id]
                    for request in evidence_requests
                ]
            )
            evidence_rankings[evidence_id] = [
                provision_id for provision_id, _ in fused
            ]
            for fusion_rank, (provision_id, fusion_score) in enumerate(
                fused[:100],
                start=1,
            ):
                source_request_ids = [
                    request.request_id
                    for request in evidence_requests
                    if provision_id
                    in observations_by_request[request.request_id]
                ]
                observations = [
                    observations_by_request[request_id][provision_id]
                    for request_id in source_request_ids
                ]
                self.last_stage_records.append(
                    CandidateStageRecord(
                        provision_id=provision_id,
                        retrieval_round=retrieval_round,
                        candidate_stage="evidence_fusion",
                        source_request_ids=source_request_ids,
                        target_evidence_item_ids=[evidence_id],
                        first_stage_rank=min(
                            observation.hit.first_stage_rank or 1
                            for observation in observations
                        ),
                        fusion_rank=fusion_rank,
                        rerank_rank=min(
                            observation.rerank_rank
                            for observation in observations
                        ),
                        first_stage_score=observations[0].hit.first_stage_score,
                        fusion_score=fusion_score,
                        selection_reason="evidence_rank_fusion",
                    )
                )

        issue_fused = self._rank_fuse_ids(
            [evidence_rankings[evidence_id] for evidence_id in evidence_order]
        )
        global_ranking = [provision_id for provision_id, _ in issue_fused]
        issue_fusion_by_id = {
            provision_id: (rank, score)
            for rank, (provision_id, score) in enumerate(issue_fused, start=1)
        }
        for rerank_rank, (provision_id, fusion_score) in enumerate(
            issue_fused[: self.rerank_pool_k], start=1
        ):
            source_request_ids = [
                request.request_id
                for request in issue_requests
                if provision_id in observations_by_request[request.request_id]
            ]
            observations = [
                observations_by_request[request_id][provision_id]
                for request_id in source_request_ids
            ]
            self.last_stage_records.append(
                CandidateStageRecord(
                    provision_id=provision_id,
                    retrieval_round=retrieval_round,
                    candidate_stage="bge_rerank",
                    source_request_ids=source_request_ids,
                    target_evidence_item_ids=self._target_evidence_ids(
                        source_request_ids, requests_by_id
                    ),
                    first_stage_rank=min(observation.hit.first_stage_rank or 1 for observation in observations),
                    fusion_rank=rerank_rank,
                    rerank_rank=rerank_rank,
                    fusion_score=fusion_score,
                    selection_reason="issue_rank_fusion_after_request_rerank",
                )
            )
        selected_ids, selection_reasons = self._select_ids(
            global_ranking,
            evidence_rankings,
            critical_evidence_item_ids,
        )

        candidates: List[CandidateProvision] = []
        for selection_rank, provision_id in enumerate(selected_ids, start=1):
            source_request_ids = [
                request.request_id
                for request in issue_requests
                if provision_id
                in observations_by_request[request.request_id]
            ]
            target_evidence_item_ids = self._target_evidence_ids(
                source_request_ids, requests_by_id
            )
            primary = observations_by_request[source_request_ids[0]][provision_id]
            observations = [
                observations_by_request[request_id][provision_id]
                for request_id in source_request_ids
            ]
            fusion_rank, fusion_score = issue_fusion_by_id[provision_id]
            reason = selection_reasons[provision_id]
            candidate = CandidateProvision(
                provision_id=primary.hit.document.provision_id,
                statute_name=primary.hit.document.statute_name,
                provision_text=primary.hit.document.provision_text,
                issue_id=issue_id,
                source_request_id=source_request_ids[0],
                retrieval_round=retrieval_round,
                first_stage_score=primary.hit.first_stage_score,
                fusion_rank=fusion_rank,
                rerank_score=primary.rerank_score,
                source_request_ids=source_request_ids,
                target_evidence_item_ids=target_evidence_item_ids,
                first_stage_rank=min(
                    observation.hit.first_stage_rank or 1
                    for observation in observations
                ),
                rerank_rank=fusion_rank,
                selection_rank=selection_rank,
                candidate_stage="selected",
                selection_reason=reason,
            )
            candidates.append(candidate)
            self.last_stage_records.append(
                CandidateStageRecord(
                    provision_id=primary.hit.document.provision_id,
                    retrieval_round=retrieval_round,
                    candidate_stage="selected",
                    source_request_ids=source_request_ids,
                    target_evidence_item_ids=target_evidence_item_ids,
                    first_stage_rank=candidate.first_stage_rank,
                    fusion_rank=fusion_rank,
                    rerank_rank=fusion_rank,
                    selection_rank=selection_rank,
                    first_stage_score=primary.hit.first_stage_score,
                    fusion_score=fusion_score,
                    rerank_score=primary.rerank_score,
                    selection_reason=reason,
                )
            )
        return candidates

    def retrieve(
        self,
        requests: Sequence[RetrievalRequest],
        retrieval_round: int,
        *,
        critical_evidence_item_ids: Sequence[str] = (),
    ) -> List[CandidateProvision]:
        self.last_stage_records = []
        self.last_unsatisfied_critical_evidence_item_ids = []
        requests_by_id = {request.request_id: request for request in requests}
        if len(requests_by_id) != len(requests):
            raise ValueError("retrieval request IDs must be unique")
        requests_by_issue: Dict[str, List[RetrievalRequest]] = defaultdict(list)
        for request in requests:
            requests_by_issue[request.issue_id].append(request)

        candidates: List[CandidateProvision] = []
        for issue_id, issue_requests in sorted(requests_by_issue.items()):
            hits_by_request: Dict[str, List[RetrievalHit]] = {}
            for request in issue_requests:
                hits = list(self.first_stage.search(request))
                hits_by_request[request.request_id] = hits
                self._record_first_stage(request, hits, retrieval_round)

            if self.rerank_query_mode == "combined_issue":
                issue_candidates = self._retrieve_combined_issue(
                    issue_id,
                    issue_requests,
                    hits_by_request,
                    requests_by_id,
                    retrieval_round,
                    critical_evidence_item_ids,
                )
            else:
                issue_candidates = self._retrieve_per_request(
                    issue_id,
                    issue_requests,
                    hits_by_request,
                    requests_by_id,
                    retrieval_round,
                    critical_evidence_item_ids,
                )
            candidates.extend(issue_candidates)
        self.last_unsatisfied_critical_evidence_item_ids = list(
            dict.fromkeys(self.last_unsatisfied_critical_evidence_item_ids)
        )
        return candidates

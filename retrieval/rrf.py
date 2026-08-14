"""Reciprocal-rank fusion within one selected retriever's query channels."""

from typing import Dict, Iterable, List, Sequence

from .types import FusedHit, RetrievalHit


def reciprocal_rank_fusion(
    ranked_lists: Iterable[Sequence[RetrievalHit]],
    k: int = 60,
) -> List[FusedHit]:
    if k <= 0:
        raise ValueError("RRF k must be positive")
    aggregate: Dict[str, Dict[str, object]] = {}
    for ranked_list in ranked_lists:
        for rank, hit in enumerate(ranked_list, start=1):
            item = aggregate.setdefault(
                hit.document.provision_id,
                {
                    "document": hit.document,
                    "rrf_score": 0.0,
                    "first_stage_score": hit.score,
                    "source_request_ids": [],
                },
            )
            item["rrf_score"] = float(item["rrf_score"]) + 1.0 / (k + rank)
            item["first_stage_score"] = max(float(item["first_stage_score"]), hit.score)
            item["source_request_ids"].append(hit.source_request_id)
    fused = [
        FusedHit(
            document=item["document"],
            rrf_score=float(item["rrf_score"]),
            first_stage_score=float(item["first_stage_score"]),
            source_request_ids=list(item["source_request_ids"]),
        )
        for item in aggregate.values()
    ]
    return sorted(fused, key=lambda hit: (-hit.rrf_score, hit.document.provision_id))

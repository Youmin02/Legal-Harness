"""Validated state transitions and progress accounting."""

from typing import Iterable, List, Sequence

from .contracts import (
    CandidateProvision,
    CoverageAssessment,
    CoverageStatus,
    EvidenceConflict,
    EvidenceLink,
    LegalIssue,
    Phase,
    RequiredEvidenceItem,
    RetrievalRequest,
)
from .run_state import RunState


class StateInvariantError(ValueError):
    pass


def apply_initial_plan(
    state: RunState,
    legal_issues: Sequence[LegalIssue],
    required_evidence_items: Sequence[RequiredEvidenceItem],
) -> None:
    if state.legal_issues or state.required_evidence_items:
        raise StateInvariantError("initial plan can only be applied once")
    state.legal_issues = list(legal_issues)
    state.required_evidence_items = list(required_evidence_items)
    state.phase = Phase.PLANNING_INITIAL
    state.last_validated_event = "S1.INITIAL_PLAN"
    state.record("INITIAL_PLAN_VALIDATED", issue_count=len(legal_issues), evidence_count=len(required_evidence_items))


def register_retrieval_round(
    state: RunState,
    requests: Sequence[RetrievalRequest],
    candidates: Sequence[CandidateProvision],
    is_gap: bool,
) -> None:
    if not requests:
        raise StateInvariantError("a retrieval round requires at least one request")
    if state.remaining_round_budget <= 0:
        raise StateInvariantError("retrieval round budget is exhausted")
    if len(requests) > state.remaining_request_budget:
        raise StateInvariantError("retrieval request budget is exhausted")
    expected_round = state.retrieval_rounds_used + 1
    if any(candidate.retrieval_round != expected_round for candidate in candidates):
        raise StateInvariantError("candidate retrieval_round does not match the state")

    existing = state.candidate_by_id()
    new_ids = {candidate.provision_id for candidate in candidates if candidate.provision_id not in existing}
    for candidate in candidates:
        previous = existing.get(candidate.provision_id)
        if previous is None or candidate.rerank_score > previous.rerank_score:
            existing[candidate.provision_id] = candidate
        state.corpus_text_snapshots.setdefault(candidate.provision_id, candidate.provision_text)
    state.candidate_provisions = list(existing.values())
    state.seen_provision_ids.update(candidate.provision_id for candidate in candidates)
    state.query_history.extend(requests)
    state.remaining_round_budget -= 1
    state.remaining_request_budget -= len(requests)
    state.retrieval_rounds_used = expected_round
    state.last_retrieval_new_provision_count = len(new_ids)
    state.phase = Phase.RETRIEVING_GAP if is_gap else Phase.RETRIEVING_INITIAL
    state.last_validated_event = "D2.GAP_RETRIEVAL" if is_gap else "D2.INITIAL_RETRIEVAL"
    state.record(
        "GAP_RETRIEVAL_VALIDATED" if is_gap else "INITIAL_RETRIEVAL_VALIDATED",
        request_count=len(requests),
        candidate_count=len(candidates),
        new_provision_count=len(new_ids),
        retrieval_round=expected_round,
    )


_CRITICAL_IMPROVEMENTS = {
    (CoverageStatus.UNCOVERED, CoverageStatus.PARTIALLY_COVERED),
    (CoverageStatus.UNCOVERED, CoverageStatus.COVERED),
    (CoverageStatus.PARTIALLY_COVERED, CoverageStatus.COVERED),
    (CoverageStatus.CONFLICTING, CoverageStatus.PARTIALLY_COVERED),
    (CoverageStatus.CONFLICTING, CoverageStatus.COVERED),
}

_MONOTONIC_STATUS_RANK = {
    CoverageStatus.UNCOVERED: 0,
    CoverageStatus.PARTIALLY_COVERED: 1,
    CoverageStatus.COVERED: 2,
}


def apply_coverage_assessment(
    state: RunState,
    evidence_links: Sequence[EvidenceLink],
    coverage_assessments: Sequence[CoverageAssessment],
    evidence_conflicts: Sequence[EvidenceConflict],
) -> bool:
    previous = state.coverage_by_evidence_id()
    incoming = {
        assessment.evidence_item_id: assessment
        for assessment in coverage_assessments
    }
    unresolved_conflict_ids = {
        conflict.evidence_item_id
        for conflict in evidence_conflicts
        if not conflict.resolved
    }
    current = {}
    preserved_ids = set()
    for item in state.required_evidence_items:
        evidence_id = item.evidence_item_id
        assessment = incoming[evidence_id]
        prior = previous.get(evidence_id)
        if (
            prior is not None
            and evidence_id not in unresolved_conflict_ids
            and prior.status in _MONOTONIC_STATUS_RANK
            and assessment.status in _MONOTONIC_STATUS_RANK
            and _MONOTONIC_STATUS_RANK[prior.status]
            > _MONOTONIC_STATUS_RANK[assessment.status]
        ):
            current[evidence_id] = prior
            preserved_ids.add(evidence_id)
        else:
            current[evidence_id] = assessment
    critical_ids = {
        item.evidence_item_id
        for item in state.required_evidence_items
        if item.critical
    }
    status_improved = any(
        evidence_id in critical_ids
        and evidence_id in previous
        and (previous[evidence_id].status, assessment.status) in _CRITICAL_IMPROVEMENTS
        for evidence_id, assessment in current.items()
    )
    progress = state.last_retrieval_new_provision_count > 0 or status_improved
    incoming_links = list(evidence_links)
    retained_links = [
        link
        for link in state.evidence_links
        if link.evidence_item_id in preserved_ids
        and link.provision_id in current[link.evidence_item_id].linked_provision_ids
    ]
    link_by_key = {
        (link.evidence_item_id, link.provision_id, link.assessment): link
        for link in retained_links + incoming_links
        if link.evidence_item_id not in preserved_ids or link in retained_links
    }
    state.evidence_links = list(link_by_key.values())
    state.coverage_assessments = [
        current[item.evidence_item_id] for item in state.required_evidence_items
    ]
    state.evidence_conflicts = list(evidence_conflicts)
    state.no_progress_rounds = 0 if progress else state.no_progress_rounds + 1
    state.phase = Phase.ASSESSING_COVERAGE
    state.last_validated_event = "S2.ASSESS_COVERAGE"
    state.refresh_derived_fields()
    state.record(
        "COVERAGE_ASSESSMENT_VALIDATED",
        progress=progress,
        no_progress_rounds=state.no_progress_rounds,
        missing_critical_count=len(state.missing_critical_items),
        unresolved_conflict_count=len(state.unresolved_critical_conflicts()),
    )
    return progress


def record_policy_decision(state: RunState, action: str, **details: object) -> None:
    state.record("POLICY_DECISION", action=action, **details)

"""Mutable run state and derived evidence-control fields."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .contracts import (
    ActionTrace,
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


@dataclass
class RunState:
    question: str
    normalized_question: str
    run_id: str
    total_round_budget: int = 3
    remaining_round_budget: int = 3
    remaining_request_budget: int = 9
    phase: Phase = Phase.INITIALIZING
    legal_issues: List[LegalIssue] = field(default_factory=list)
    required_evidence_items: List[RequiredEvidenceItem] = field(default_factory=list)
    candidate_provisions: List[CandidateProvision] = field(default_factory=list)
    evidence_links: List[EvidenceLink] = field(default_factory=list)
    coverage_assessments: List[CoverageAssessment] = field(default_factory=list)
    missing_critical_items: List[RequiredEvidenceItem] = field(default_factory=list)
    evidence_conflicts: List[EvidenceConflict] = field(default_factory=list)
    accepted_provision_ids: Set[str] = field(default_factory=set)
    seen_provision_ids: Set[str] = field(default_factory=set)
    query_history: List[RetrievalRequest] = field(default_factory=list)
    corpus_text_snapshots: Dict[str, str] = field(default_factory=dict)
    no_progress_rounds: int = 0
    retrieval_rounds_used: int = 0
    last_retrieval_new_provision_count: int = 0
    last_validated_event: Optional[str] = None
    action_trace: List[ActionTrace] = field(default_factory=list)

    def candidate_by_id(self) -> Dict[str, CandidateProvision]:
        return {candidate.provision_id: candidate for candidate in self.candidate_provisions}

    def evidence_by_id(self) -> Dict[str, RequiredEvidenceItem]:
        return {
            item.evidence_item_id: item
            for item in self.required_evidence_items
        }

    def coverage_by_evidence_id(self) -> Dict[str, CoverageAssessment]:
        return {
            assessment.evidence_item_id: assessment
            for assessment in self.coverage_assessments
        }

    def unresolved_critical_conflicts(self) -> List[EvidenceConflict]:
        evidence = self.evidence_by_id()
        return [
            conflict
            for conflict in self.evidence_conflicts
            if not conflict.resolved
            and evidence.get(conflict.evidence_item_id)
            and evidence[conflict.evidence_item_id].critical
        ]

    def has_critical_blockers(self) -> bool:
        coverage = self.coverage_by_evidence_id()
        for item in self.required_evidence_items:
            if not item.critical:
                continue
            assessment = coverage.get(item.evidence_item_id)
            if assessment is None or assessment.status is not CoverageStatus.COVERED:
                return True
        return False

    def refresh_derived_fields(self) -> None:
        """Rebuild fields that must never be independently authored."""
        evidence = self.evidence_by_id()
        coverage = self.coverage_by_evidence_id()
        self.accepted_provision_ids = {
            link.provision_id
            for link in self.evidence_links
            if link.assessment == "accepted"
        }
        self.missing_critical_items = [
            item
            for item in self.required_evidence_items
            if item.critical
            and (
                item.evidence_item_id not in coverage
                or coverage[item.evidence_item_id].status
                is not CoverageStatus.COVERED
            )
        ]
        # Ignore impossible links defensively; validation rejects them before state update.
        self.accepted_provision_ids = {
            provision_id
            for provision_id in self.accepted_provision_ids
            if provision_id in self.candidate_by_id()
            and any(
                link.provision_id == provision_id
                and link.evidence_item_id in evidence
                for link in self.evidence_links
            )
        }

    def record(self, event: str, **details: object) -> None:
        self.action_trace.append(
            ActionTrace(event=event, phase=self.phase, details=dict(details))
        )

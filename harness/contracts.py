"""Typed contracts shared by the harness, retrieval layer, and future skills."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Phase(str, Enum):
    INITIALIZING = "INITIALIZING"
    PLANNING_INITIAL = "PLANNING_INITIAL"
    RETRIEVING_INITIAL = "RETRIEVING_INITIAL"
    ASSESSING_COVERAGE = "ASSESSING_COVERAGE"
    PLANNING_GAP = "PLANNING_GAP"
    RETRIEVING_GAP = "RETRIEVING_GAP"
    GENERATING = "GENERATING"
    VALIDATING_CITATIONS = "VALIDATING_CITATIONS"
    COMPLETED = "COMPLETED"
    ABSTAINED = "ABSTAINED"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"


class PolicyAction(str, Enum):
    RETRIEVE_GAP = "RETRIEVE_GAP"
    GENERATE = "GENERATE"
    ABSTAIN = "ABSTAIN"


class CoverageStatus(str, Enum):
    COVERED = "covered"
    PARTIALLY_COVERED = "partially_covered"
    UNCOVERED = "uncovered"
    CONFLICTING = "conflicting"


class QueryChannel(str, Enum):
    PROVISION_STYLE = "provision_style"
    SPARSE_KEYWORD = "sparse_keyword"
    STATUTE_AWARE = "statute_aware"


class AbstentionReason(str, Enum):
    INSUFFICIENT_CRITICAL_EVIDENCE = "INSUFFICIENT_CRITICAL_EVIDENCE"
    UNRESOLVED_EVIDENCE_CONFLICT = "UNRESOLVED_EVIDENCE_CONFLICT"


class TerminationReason(str, Enum):
    COMPLETED = "COMPLETED"
    RETRIEVAL_BUDGET_EXHAUSTED = "RETRIEVAL_BUDGET_EXHAUSTED"
    MAX_RETRIEVAL_ROUNDS_REACHED = "MAX_RETRIEVAL_ROUNDS_REACHED"
    NO_RETRIEVAL_PROGRESS = "NO_RETRIEVAL_PROGRESS"
    NO_VALID_GAP_QUERY = "NO_VALID_GAP_QUERY"
    INVALID_SKILL_OUTPUT = "INVALID_SKILL_OUTPUT"
    SKILL_EXECUTION_FAILED = "SKILL_EXECUTION_FAILED"
    RETRIEVER_FAILURE = "RETRIEVER_FAILURE"
    CITATION_INTEGRITY_FAILED = "CITATION_INTEGRITY_FAILED"


class OutcomeStatus(str, Enum):
    ANSWER = "ANSWER"
    ABSTAIN = "ABSTAIN"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"


@dataclass(frozen=True)
class LegalIssue:
    issue_id: str
    description: str


@dataclass(frozen=True)
class RequiredEvidenceItem:
    evidence_item_id: str
    issue_id: str
    evidence_type: str
    description: str
    critical: bool

    completion_criteria: str = ""

@dataclass(frozen=True)
class RetrievalRequest:
    request_id: str
    issue_id: str
    evidence_item_id: str
    query_channel: QueryChannel
    query_text: str
    top_k: int = 100
    query_terms: List[str] = field(default_factory=list)
    statute_hints: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateProvision:
    provision_id: str
    statute_name: str
    provision_text: str
    issue_id: str
    source_request_id: str
    retrieval_round: int
    first_stage_score: float
    fusion_rank: int
    rerank_score: float


@dataclass(frozen=True)
class SupportSpan:
    start_char: int
    end_char: int


@dataclass(frozen=True)
class EvidenceLink:
    issue_id: str
    evidence_item_id: str
    provision_id: str
    support_spans: List[SupportSpan]
    assessment: str = "accepted"


@dataclass(frozen=True)
class CoverageAssessment:
    evidence_item_id: str
    status: CoverageStatus
    linked_provision_ids: List[str]
    rationale: str


@dataclass(frozen=True)
class EvidenceConflict:
    evidence_item_id: str
    provision_ids: List[str]
    description: str
    resolved: bool = False


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str


@dataclass(frozen=True)
class ClaimCitation:
    claim_id: str
    provision_ids: List[str]


@dataclass(frozen=True)
class AnswerDraft:
    claims: List[Claim]
    claim_citations: List[ClaimCitation]
    answer: str


@dataclass(frozen=True)
class CitationIntegrityResult:
    passed: bool
    errors: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PolicyDecision:
    action: PolicyAction
    termination_reason: Optional[TerminationReason] = None
    explanation: str = ""


@dataclass(frozen=True)
class ActionTrace:
    event: str
    phase: Phase
    details: Dict[str, object] = field(default_factory=dict)

"""Deterministic input, schema-shape, and cross-reference validation."""

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .contracts import (
    AnswerDraft,
    CandidateProvision,
    Claim,
    ClaimCitation,
    CoverageAssessment,
    CoverageStatus,
    EvidenceConflict,
    EvidenceLink,
    LegalIssue,
    QueryChannel,
    RequiredEvidenceItem,
    RetrievalRequest,
    SupportSpan,
)
from .run_state import RunState


class ValidationError(ValueError):
    pass


def normalize_question(question: str) -> str:
    """Apply only deterministic Unicode/whitespace normalization."""
    if not isinstance(question, str):
        raise ValidationError("question must be a string")
    normalized = unicodedata.normalize("NFC", question)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        raise ValidationError("question must not be empty")
    return normalized


def normalized_query(query: str) -> str:
    return normalize_question(query).casefold()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("%s must be an object" % label)
    return value


def _items(payload: Mapping[str, Any], key: str, allow_empty: bool = False) -> List[Mapping[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValidationError("%s must be a list" % key)
    if not value and not allow_empty:
        raise ValidationError("%s must not be empty" % key)
    return [_mapping(item, "%s[]" % key) for item in value]


def _string(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("%s must be a non-empty string" % key)
    return value.strip()


def _boolean(raw: Mapping[str, Any], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise ValidationError("%s must be a boolean" % key)
    return value


def _string_list(raw: Mapping[str, Any], key: str) -> List[str]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValidationError("%s must be a list of non-empty strings" % key)
    normalized = [normalize_question(item) for item in value]
    if len(normalized) != len(set(normalized)):
        raise ValidationError("%s must not contain duplicates" % key)
    return normalized


def _unique(values: Iterable[str], label: str) -> None:
    values = list(values)
    if len(values) != len(set(values)):
        raise ValidationError("%s contains duplicate IDs" % label)


def _parse_request(raw: Mapping[str, Any]) -> RetrievalRequest:
    try:
        channel = QueryChannel(_string(raw, "query_channel"))
    except ValueError as exc:
        raise ValidationError("query_channel is not a frozen allowed value") from exc
    top_k = raw.get("top_k")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k != 100:
        raise ValidationError("top_k must be the frozen value 100")
    return RetrievalRequest(
        request_id=_string(raw, "request_id"),
        issue_id=_string(raw, "issue_id"),
        evidence_item_id=_string(raw, "evidence_item_id"),
        query_channel=channel,
        query_text=normalize_question(_string(raw, "query_text")),
        top_k=top_k,
        query_terms=_string_list(raw, "query_terms"),
        statute_hints=_string_list(raw, "statute_hints"),
    )


def validate_initial_plan(
    payload: Mapping[str, Any],
) -> Tuple[List[LegalIssue], List[RequiredEvidenceItem], List[RetrievalRequest]]:
    issues = [
        LegalIssue(issue_id=_string(raw, "issue_id"), description=_string(raw, "description"))
        for raw in _items(payload, "legal_issues")
    ]
    _unique([issue.issue_id for issue in issues], "legal_issues")

    evidence_items = [
        RequiredEvidenceItem(
            evidence_item_id=_string(raw, "evidence_item_id"),
            issue_id=_string(raw, "issue_id"),
            evidence_type=_string(raw, "evidence_type"),
            description=_string(raw, "description"),
            critical=_boolean(raw, "critical"),
            completion_criteria=raw.get("completion_criteria", "") or _string(raw, "description"),
        )
        for raw in _items(payload, "required_evidence_items")
    ]
    _unique([item.evidence_item_id for item in evidence_items], "required_evidence_items")
    issue_ids = {issue.issue_id for issue in issues}
    if any(item.issue_id not in issue_ids for item in evidence_items):
        raise ValidationError("required_evidence_items references an unknown issue_id")

    requests = [_parse_request(raw) for raw in _items(payload, "retrieval_requests")]
    _validate_requests(requests, issue_ids, {item.evidence_item_id for item in evidence_items}, [])
    return issues, evidence_items, requests


def validate_gap_plan(payload: Mapping[str, Any], state: RunState) -> List[RetrievalRequest]:
    raw_requests = payload.get("gap_retrieval_requests")
    if not isinstance(raw_requests, list):
        raise ValidationError("gap_retrieval_requests must be a list")
    requests = [_parse_request(_mapping(raw, "gap_retrieval_requests[]")) for raw in raw_requests]
    _validate_requests(
        requests,
        {issue.issue_id for issue in state.legal_issues},
        set(state.evidence_by_id()),
        state.query_history,
    )
    return requests


def _validate_requests(
    requests: Sequence[RetrievalRequest],
    issue_ids: Sequence[str],
    evidence_ids: Sequence[str],
    history: Sequence[RetrievalRequest],
) -> None:
    _unique([request.request_id for request in requests], "retrieval requests")
    issue_ids, evidence_ids = set(issue_ids), set(evidence_ids)
    seen_queries = {normalized_query(request.query_text) for request in history}
    for request in requests:
        if request.issue_id not in issue_ids:
            raise ValidationError("retrieval request references an unknown issue_id")
        if request.evidence_item_id not in evidence_ids:
            raise ValidationError("retrieval request references an unknown evidence_item_id")
        query = normalized_query(request.query_text)
        if query in seen_queries:
            raise ValidationError("duplicate normalized retrieval query is forbidden")
        seen_queries.add(query)


def validate_coverage_assessment(
    payload: Mapping[str, Any],
    state: RunState,
) -> Tuple[List[EvidenceLink], List[CoverageAssessment], List[EvidenceConflict]]:
    candidate_by_id = state.candidate_by_id()
    evidence_by_id = state.evidence_by_id()
    links: List[EvidenceLink] = []
    for raw in _items(payload, "evidence_links", allow_empty=True):
        evidence_item_id = _string(raw, "evidence_item_id")
        provision_id = _string(raw, "provision_id")
        issue_id = _string(raw, "issue_id")
        if evidence_item_id not in evidence_by_id:
            raise ValidationError("evidence link references unknown evidence_item_id")
        if issue_id != evidence_by_id[evidence_item_id].issue_id:
            raise ValidationError("evidence link issue_id does not match evidence item")
        candidate = candidate_by_id.get(provision_id)
        if candidate is None:
            raise ValidationError("evidence link references provision outside candidates")
        spans: List[SupportSpan] = []
        for span_raw in _items(_mapping(raw, "evidence_link"), "support_spans"):
            start, end = span_raw.get("start_char"), span_raw.get("end_char")
            if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(candidate.provision_text)):
                raise ValidationError("support span is outside the cited provision text")
            spans.append(SupportSpan(start_char=start, end_char=end))
        links.append(
            EvidenceLink(
                issue_id=issue_id,
                evidence_item_id=evidence_item_id,
                provision_id=provision_id,
                support_spans=spans,
                assessment=_string(raw, "assessment"),
            )
        )

    assessments: List[CoverageAssessment] = []
    for raw in _items(payload, "coverage_assessments"):
        evidence_item_id = _string(raw, "evidence_item_id")
        if evidence_item_id not in evidence_by_id:
            raise ValidationError("coverage assessment references unknown evidence_item_id")
        try:
            status = CoverageStatus(_string(raw, "status"))
        except ValueError as exc:
            raise ValidationError("coverage status is not a frozen allowed value") from exc
        linked_ids = raw.get("linked_provision_ids")
        if not isinstance(linked_ids, list) or not all(isinstance(value, str) for value in linked_ids):
            raise ValidationError("linked_provision_ids must be a list of strings")
        if any(provision_id not in candidate_by_id for provision_id in linked_ids):
            raise ValidationError("coverage assessment references provision outside candidates")
        partial_kind = raw.get(
            "partial_kind",
            "legal_support_gap"
            if status is CoverageStatus.PARTIALLY_COVERED
            else "not_applicable",
        )
        allowed_partial_kinds = {"factual_condition", "legal_support_gap"}
        if status is CoverageStatus.PARTIALLY_COVERED:
            if partial_kind not in allowed_partial_kinds:
                raise ValidationError("partial coverage requires a valid partial_kind")
        elif partial_kind != "not_applicable":
            raise ValidationError("non-partial coverage must use partial_kind=not_applicable")
        missing_aspects = raw.get("missing_aspects", [])
        if not isinstance(missing_aspects, list) or not all(
            isinstance(value, str) and value.strip() for value in missing_aspects
        ):
            raise ValidationError("missing_aspects must be a list of non-empty strings")
        assessments.append(
            CoverageAssessment(
                evidence_item_id=evidence_item_id,
                status=status,
                linked_provision_ids=list(linked_ids),
                rationale=_string(raw, "rationale"),
                partial_kind=partial_kind,
                missing_aspects=list(missing_aspects),
            )
        )
    _unique([assessment.evidence_item_id for assessment in assessments], "coverage_assessments")
    if set(assessment.evidence_item_id for assessment in assessments) != set(evidence_by_id):
        raise ValidationError("S2 must assess every required evidence item")

    conflicts: List[EvidenceConflict] = []
    for raw in _items(payload, "evidence_conflicts", allow_empty=True):
        evidence_item_id = _string(raw, "evidence_item_id")
        provision_ids = raw.get("provision_ids")
        if evidence_item_id not in evidence_by_id:
            raise ValidationError("evidence conflict references unknown evidence_item_id")
        if not isinstance(provision_ids, list) or not all(isinstance(value, str) for value in provision_ids):
            raise ValidationError("evidence conflict provision_ids must be a list of strings")
        if any(provision_id not in candidate_by_id for provision_id in provision_ids):
            raise ValidationError("evidence conflict references provision outside candidates")
        conflicts.append(
            EvidenceConflict(
                evidence_item_id=evidence_item_id,
                provision_ids=list(provision_ids),
                description=_string(raw, "description"),
                resolved=raw.get("resolved", False) is True,
            )
        )
    return links, assessments, conflicts


def validate_answer_draft(payload: Mapping[str, Any], state: RunState) -> AnswerDraft:
    claims = [
        Claim(claim_id=_string(raw, "claim_id"), text=_string(raw, "text"))
        for raw in _items(payload, "claims")
    ]
    _unique([claim.claim_id for claim in claims], "claims")
    citations: List[ClaimCitation] = []
    for raw in _items(payload, "claim_citations"):
        provision_ids = raw.get("provision_ids")
        if not isinstance(provision_ids, list) or not provision_ids or not all(isinstance(value, str) for value in provision_ids):
            raise ValidationError("claim citation must contain one or more provision IDs")
        citations.append(
            ClaimCitation(claim_id=_string(raw, "claim_id"), provision_ids=list(provision_ids))
        )
    _unique([citation.claim_id for citation in citations], "claim_citations")
    if {claim.claim_id for claim in claims} != {citation.claim_id for citation in citations}:
        raise ValidationError("every answer claim must have exactly one claim citation")
    cited_ids = {provision_id for citation in citations for provision_id in citation.provision_ids}
    if not cited_ids.issubset(state.accepted_provision_ids):
        raise ValidationError("S3 cited a provision outside accepted_provision_ids")
    return AnswerDraft(claims=claims, claim_citations=citations, answer=_string(payload, "answer"))



def validate_retrieval_candidates(
    candidates: Sequence[CandidateProvision],
    requests: Sequence[RetrievalRequest],
    retrieval_round: int,
) -> None:
    """Check deterministic retrieval output before it enters RunState."""
    request_by_id = {request.request_id: request for request in requests}
    for candidate in candidates:
        if not isinstance(candidate, CandidateProvision):
            raise ValidationError("retriever must return CandidateProvision instances")
        request = request_by_id.get(candidate.source_request_id)
        if request is None:
            raise ValidationError("candidate source_request_id is not in this retrieval round")
        if candidate.issue_id != request.issue_id:
            raise ValidationError("candidate issue_id does not match source retrieval request")
        if candidate.retrieval_round != retrieval_round:
            raise ValidationError("candidate retrieval_round is invalid")
        if not candidate.provision_id or not candidate.provision_text:
            raise ValidationError("candidate provision_id and provision_text are required")
        if candidate.fusion_rank < 1:
            raise ValidationError("candidate fusion_rank must be positive")

"""End-to-end deterministic orchestration around externally supplied skills."""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .contracts import (
    AbstentionReason,
    AnswerMode,
    CandidateAnswerBasis,
    CandidateAnswerStatus,
    OutcomeStatus,
    Phase,
    PolicyAction,
    PolicyDecision,
    TerminationReason,
)
from .interfaces import CitationIntegrityValidator, ProvisionRetriever, SkillExecutor
from .policy import abstention_reason_for, decide_next_action
from .run_state import RunState
from .state_update import (
    StateInvariantError,
    apply_coverage_assessment,
    apply_initial_plan,
    record_policy_decision,
    register_retrieval_round,
)
from .tracing import NullTraceSink, TraceSink, to_primitive
from .validation import (
    ValidationError,
    normalize_question,
    validate_answer_draft,
    validate_benchmark_candidate_draft,
    validate_coverage_assessment,
    validate_gap_plan,
    validate_initial_plan,
    validate_retrieval_candidates,
    validate_retrieval_stage_records,
)


S1 = "legal_issue_and_query_planning"
S2 = "provision_coverage_assessment"
S3 = "grounded_legal_answer_generation"


@dataclass(frozen=True)
class HarnessConfig:
    total_retrieval_rounds: int = 3
    total_retrieval_requests: int = 9

    def __post_init__(self) -> None:
        if self.total_retrieval_rounds < 1:
            raise ValueError("total_retrieval_rounds must include the initial round")
        if self.total_retrieval_requests < 1:
            raise ValueError("total_retrieval_requests must be positive")


@dataclass
class HarnessOutcome:
    status: OutcomeStatus
    state: RunState
    answer: Optional[str] = None
    answer_mode: Optional[AnswerMode] = None
    complete_answer: bool = False
    answered_target_ids: List[str] = field(default_factory=list)
    deferred_target_ids: List[str] = field(default_factory=list)
    abstention_reason: Optional[AbstentionReason] = None
    termination_reason: Optional[TerminationReason] = None
    candidate_answer: Optional[str] = None
    candidate_answer_status: Optional[CandidateAnswerStatus] = None
    candidate_answer_basis: Optional[CandidateAnswerBasis] = None
    candidate_answer_termination_reason: Optional[TerminationReason] = None
    candidate_answer_error: Optional[str] = None
    errors: List[str] = field(default_factory=list)


class HarnessRunner:
    def __init__(
        self,
        skill_executor: SkillExecutor,
        retriever: ProvisionRetriever,
        citation_validator: CitationIntegrityValidator,
        config: HarnessConfig = HarnessConfig(),
        trace_sink: TraceSink = None,
    ):
        self.skill_executor = skill_executor
        self.retriever = retriever
        self.citation_validator = citation_validator
        self.config = config
        self.trace_sink = trace_sink or NullTraceSink()

    def run(self, question: str, run_id: Optional[str] = None) -> HarnessOutcome:
        try:
            normalized_question = normalize_question(question)
        except ValidationError as exc:
            state = RunState(
                question=question if isinstance(question, str) else "",
                normalized_question="",
                run_id=run_id or str(uuid.uuid4()),
                total_round_budget=self.config.total_retrieval_rounds,
                remaining_round_budget=self.config.total_retrieval_rounds,
                remaining_request_budget=self.config.total_retrieval_requests,
                phase=Phase.EXECUTION_FAILURE,
            )
            return HarnessOutcome(
                status=OutcomeStatus.EXECUTION_FAILURE,
                state=state,
                termination_reason=TerminationReason.INVALID_SKILL_OUTPUT,
                errors=[str(exc)],
            )

        state = RunState(
            question=question,
            normalized_question=normalized_question,
            run_id=run_id or str(uuid.uuid4()),
            total_round_budget=self.config.total_retrieval_rounds,
            remaining_round_budget=self.config.total_retrieval_rounds,
            remaining_request_budget=self.config.total_retrieval_requests,
            phase=Phase.PLANNING_INITIAL,
        )
        self._trace("RUN_STARTED", state)

        try:
            initial_raw = self._execute(
                S1,
                "INITIAL_PLAN",
                {
                    "run_id": state.run_id,
                    "question": state.question,
                    "normalized_question": state.normalized_question,
                    "query_history": [],
                },
            )
            issues, answer_targets, evidence_items, initial_requests = validate_initial_plan(
                initial_raw,
                question=state.normalized_question,
                include_answer_targets=True,
            )
            if len(initial_requests) > state.remaining_request_budget:
                raise ValidationError("initial retrieval requests exceed the frozen request budget")
            apply_initial_plan(state, issues, evidence_items, answer_targets)
            self._trace("INITIAL_PLAN_VALIDATED", state, retrieval_request_count=len(initial_requests))
        except (ValidationError, StateInvariantError, RuntimeError) as exc:
            return self._failure(state, TerminationReason.INVALID_SKILL_OUTPUT, exc)

        retrieval_error = self._retrieve(state, initial_requests, is_gap=False)
        if retrieval_error:
            return retrieval_error

        while True:
            assessment_error = self._assess_coverage(state)
            if assessment_error:
                return assessment_error

            decision = decide_next_action(state)
            record_policy_decision(
                state,
                decision.action.value,
                termination_reason=(decision.termination_reason.value if decision.termination_reason else None),
                explanation=decision.explanation,
                answer_mode=(decision.answer_mode.value if decision.answer_mode else None),
                answered_target_ids=decision.answered_target_ids,
                deferred_target_ids=decision.deferred_target_ids,
            )
            self._trace("POLICY_DECISION", state, action=decision.action.value, explanation=decision.explanation)

            if decision.action is PolicyAction.GENERATE:
                self._apply_generation_scope(state, decision)
                return self._generate_and_validate(state)
            if decision.action is PolicyAction.ABSTAIN:
                return self._abstain(state, decision.termination_reason)

            try:
                state.phase = Phase.PLANNING_GAP
                gap_raw = self._execute(S1, "GAP_QUERY_PLAN", self._gap_payload(state))
                gap_requests = validate_gap_plan(gap_raw, state)
            except (ValidationError, RuntimeError) as exc:
                return self._failure(state, TerminationReason.INVALID_SKILL_OUTPUT, exc)

            if not gap_requests:
                fallback = decide_next_action(state, can_attempt_gap_query=False)
                if fallback.action is PolicyAction.GENERATE:
                    self._record_and_apply_generation_decision(state, fallback)
                    return self._generate_and_validate(state)
                return self._abstain(state, fallback.termination_reason)
            if len(gap_requests) > state.remaining_request_budget:
                if state.has_any_citable_answer_target():
                    limited = PolicyDecision(
                        action=PolicyAction.GENERATE,
                        explanation="The next gap plan exceeds the budget; answer only citable targets.",
                        answer_mode=AnswerMode.LIMITED,
                        answered_target_ids=state.covered_answer_target_ids(),
                        deferred_target_ids=[
                            target.answer_target_id
                            for target in state.answer_targets
                            if target.answer_target_id not in state.covered_answer_target_ids()
                        ],
                    )
                    self._record_and_apply_generation_decision(state, limited)
                    return self._generate_and_validate(state)
                if state.can_generate_conditionally():
                    record_policy_decision(
                        state,
                        PolicyAction.GENERATE.value,
                        explanation="The next gap plan exceeds the budget; generate a conditional answer from citable partial support.",
                    )
                    self._apply_generation_scope(
                        state,
                        PolicyDecision(
                            action=PolicyAction.GENERATE,
                            answer_mode=AnswerMode.CONDITIONAL,
                        ),
                    )
                    return self._generate_and_validate(state)
                return self._abstain(state, TerminationReason.RETRIEVAL_BUDGET_EXHAUSTED)
            retrieval_error = self._retrieve(state, gap_requests, is_gap=True)
            if retrieval_error:
                return retrieval_error

    def _retrieve(
        self,
        state: RunState,
        requests: Sequence,
        is_gap: bool,
    ) -> Optional[HarnessOutcome]:
        retrieval_round = state.retrieval_rounds_used + 1
        try:
            critical_evidence_item_ids = [
                item.evidence_item_id
                for item in state.required_evidence_items
                if item.critical
            ]
            candidates = self.retriever.retrieve(
                requests,
                retrieval_round,
                critical_evidence_item_ids=critical_evidence_item_ids,
            )
            validate_retrieval_candidates(candidates, requests, retrieval_round)
            stage_records = list(
                getattr(self.retriever, "last_stage_records", ())
            )
            unsatisfied_critical_evidence_item_ids = list(
                getattr(self.retriever, "last_unsatisfied_critical_evidence_item_ids", ())
            )
            dedup_removed_count = getattr(
                self.retriever, "last_dedup_removed_count", 0
            )
            if isinstance(dedup_removed_count, bool) or not isinstance(
                dedup_removed_count, int
            ):
                dedup_removed_count = 0
            validate_retrieval_stage_records(
                stage_records, requests, retrieval_round
            )
            register_retrieval_round(
                state,
                requests,
                candidates,
                is_gap=is_gap,
                candidate_stage_records=stage_records,
            )
            self._trace(
                "GAP_RETRIEVAL_VALIDATED" if is_gap else "INITIAL_RETRIEVAL_VALIDATED",
                state,
                request_count=len(requests),
                candidate_count=len(candidates),
                stage_record_count=len(stage_records),
                dedup_removed_count=dedup_removed_count,
                unsatisfied_critical_evidence_item_ids=unsatisfied_critical_evidence_item_ids,
            )
            return None
        except (ValidationError, StateInvariantError) as exc:
            return self._failure(state, TerminationReason.RETRIEVER_FAILURE, exc)
        except Exception as exc:
            return self._failure(state, TerminationReason.RETRIEVER_FAILURE, exc)

    def _assess_coverage(self, state: RunState) -> Optional[HarnessOutcome]:
        try:
            raw = self._execute(S2, "ASSESS_COVERAGE", self._coverage_payload(state))
            links, assessments, conflicts = validate_coverage_assessment(raw, state)
            apply_coverage_assessment(state, links, assessments, conflicts)
            self._trace("COVERAGE_ASSESSMENT_VALIDATED", state)
            return None
        except (ValidationError, StateInvariantError, RuntimeError) as exc:
            return self._failure(state, TerminationReason.INVALID_SKILL_OUTPUT, exc)

    def _generate_and_validate(self, state: RunState) -> HarnessOutcome:
        try:
            state.phase = Phase.GENERATING
            raw = self._execute(S3, "GENERATE_ANSWER", self._answer_payload(state))
            answer = validate_answer_draft(raw, state)
            state.last_validated_event = "S3.GENERATE_ANSWER"
            state.record(
                "ANSWER_DRAFT_VALIDATED",
                claim_count=len(answer.claims),
                answer_mode=state.answer_mode.value if state.answer_mode else None,
                answered_target_ids=state.answered_target_ids,
                deferred_target_ids=state.deferred_target_ids,
            )
            state.phase = Phase.VALIDATING_CITATIONS
            citation_result = self.citation_validator.validate(state, answer)
        except (ValidationError, RuntimeError) as exc:
            return self._failure(state, TerminationReason.INVALID_SKILL_OUTPUT, exc)
        except Exception as exc:
            return self._failure(state, TerminationReason.CITATION_INTEGRITY_FAILED, exc)

        if not citation_result.passed:
            return self._failure(
                state,
                TerminationReason.CITATION_INTEGRITY_FAILED,
                RuntimeError("; ".join(citation_result.errors)),
            )
        state.phase = Phase.COMPLETED
        state.last_validated_event = "D4.CITATION_INTEGRITY_PASS"
        state.record("CITATION_INTEGRITY_PASS")
        self._trace("RUN_COMPLETED", state)
        return HarnessOutcome(
            status=OutcomeStatus.ANSWER,
            state=state,
            answer=answer.answer,
            answer_mode=state.answer_mode,
            complete_answer=state.answer_mode is AnswerMode.FULL,
            answered_target_ids=list(state.answered_target_ids),
            deferred_target_ids=list(state.deferred_target_ids),
            termination_reason=TerminationReason.COMPLETED,
            candidate_answer=answer.answer,
            candidate_answer_status=CandidateAnswerStatus.PUBLISHED_ANSWER,
            candidate_answer_basis=CandidateAnswerBasis.PUBLISHED_ANSWER,
        )

    def _abstain(
        self,
        state: RunState,
        termination_reason: Optional[TerminationReason],
    ) -> HarnessOutcome:
        state.phase = Phase.ABSTAINED
        state.last_validated_event = "RESPONSE_ASSEMBLY.ABSTAIN"
        reason = abstention_reason_for(state)
        state.record(
            "ABSTAIN",
            abstention_reason=reason.value,
            termination_reason=(termination_reason.value if termination_reason else None),
        )
        self._trace("RUN_ABSTAINED", state, reason=reason.value)
        (
            candidate_answer,
            candidate_status,
            candidate_basis,
            candidate_termination_reason,
            candidate_error,
        ) = self._generate_benchmark_candidate(state)
        return HarnessOutcome(
            status=OutcomeStatus.ABSTAIN,
            state=state,
            abstention_reason=reason,
            termination_reason=termination_reason,
            candidate_answer=candidate_answer,
            candidate_answer_status=candidate_status,
            candidate_answer_basis=candidate_basis,
            candidate_answer_termination_reason=candidate_termination_reason,
            candidate_answer_error=candidate_error,
        )

    def _generate_benchmark_candidate(
        self, state: RunState
    ) -> tuple[
        Optional[str],
        CandidateAnswerStatus,
        CandidateAnswerBasis,
        Optional[TerminationReason],
        Optional[str],
    ]:
        payload = self._benchmark_candidate_payload(state)
        basis = CandidateAnswerBasis(payload["candidate_answer_basis"])
        try:
            state.record(
                "BENCHMARK_CANDIDATE_GENERATION_STARTED",
                candidate_provision_count=len(payload["candidate_provisions"]),
                candidate_answer_basis=basis.value,
            )
            raw = self._execute(
                S3,
                "GENERATE_BENCHMARK_CANDIDATE",
                payload,
            )
            candidate = validate_benchmark_candidate_draft(raw, state)
            state.record(
                "BENCHMARK_CANDIDATE_VALIDATED",
                claim_count=len(candidate.claims),
                candidate_provision_count=len(payload["candidate_provisions"]),
                candidate_answer_basis=basis.value,
            )
            self._trace("BENCHMARK_CANDIDATE_VALIDATED", state)
            return candidate.answer, CandidateAnswerStatus.GENERATED, basis, None, None
        except (ValidationError, RuntimeError) as exc:
            return self._benchmark_candidate_failure(state, basis, exc)
        except Exception as exc:
            return self._benchmark_candidate_failure(state, basis, exc)

    def _benchmark_candidate_failure(
        self, state: RunState, basis: CandidateAnswerBasis, error: Exception
    ) -> tuple[None, CandidateAnswerStatus, CandidateAnswerBasis, TerminationReason, str]:
        termination_reason = TerminationReason.INVALID_SKILL_OUTPUT
        state.record(
            "BENCHMARK_CANDIDATE_EXECUTION_FAILURE",
            termination_reason=termination_reason.value,
            error=str(error),
        )
        self._trace(
            "BENCHMARK_CANDIDATE_EXECUTION_FAILURE",
            state,
            error=str(error),
            termination_reason=termination_reason.value,
        )
        return (
            None,
            CandidateAnswerStatus.EXECUTION_FAILURE,
            basis,
            termination_reason,
            str(error),
        )

    def _failure(
        self,
        state: RunState,
        termination_reason: TerminationReason,
        error: Exception,
    ) -> HarnessOutcome:
        state.phase = Phase.EXECUTION_FAILURE
        state.record("EXECUTION_FAILURE", termination_reason=termination_reason.value, error=str(error))
        self._trace("RUN_EXECUTION_FAILURE", state, error=str(error), termination_reason=termination_reason.value)
        return HarnessOutcome(
            status=OutcomeStatus.EXECUTION_FAILURE,
            state=state,
            termination_reason=termination_reason,
            errors=[str(error)],
        )

    def _execute(self, skill_name: str, entry_point: str, payload: Dict[str, Any]) -> Mapping[str, Any]:
        result = self.skill_executor.execute(skill_name, entry_point, payload)
        if not isinstance(result, Mapping):
            raise ValidationError("%s must return an object" % skill_name)
        return result

    def _coverage_payload(self, state: RunState) -> Dict[str, Any]:
        return {
            "run_id": state.run_id,
            "normalized_question": state.normalized_question,
            "legal_issues": to_primitive(state.legal_issues),
            "answer_targets": to_primitive(state.answer_targets),
            "required_evidence_items": to_primitive(state.required_evidence_items),
            "candidate_provisions": to_primitive(state.candidate_provisions),
            "prior_coverage_assessments": to_primitive(state.coverage_assessments),
        }

    def _gap_payload(self, state: RunState) -> Dict[str, Any]:
        return {
            "run_id": state.run_id,
            "normalized_question": state.normalized_question,
            "next_retrieval_round": state.retrieval_rounds_used + 1,
            "legal_issues": to_primitive(state.legal_issues),
            "answer_targets": to_primitive(state.answer_targets),
            "required_evidence_items": to_primitive(state.required_evidence_items),
            "coverage_assessments": to_primitive(state.coverage_assessments),
            "missing_evidence_items": to_primitive(state.missing_critical_items),
            "evidence_conflicts": to_primitive(state.unresolved_critical_conflicts()),
            "accepted_provision_ids": sorted(state.accepted_provision_ids),
            "query_history": to_primitive(state.query_history),
            "seen_provision_ids": sorted(state.seen_provision_ids),
            "remaining_request_budget": state.remaining_request_budget,
        }

    def _answer_payload(self, state: RunState) -> Dict[str, Any]:
        supported_evidence_by_provision: Dict[str, List[str]] = {}
        for link in state.evidence_links:
            if link.assessment == "accepted":
                supported_evidence_by_provision.setdefault(link.provision_id, []).append(
                    link.evidence_item_id
                )
        accepted = []
        for candidate in state.candidate_provisions:
            if candidate.provision_id not in state.accepted_provision_ids:
                continue
            payload = to_primitive(candidate)
            payload["supported_evidence_item_ids"] = sorted(
                set(supported_evidence_by_provision.get(candidate.provision_id, []))
            )
            accepted.append(payload)
        return {
            "run_id": state.run_id,
            "question": state.question,
            "normalized_question": state.normalized_question,
            "legal_issues": to_primitive(state.legal_issues),
            "answer_targets": to_primitive(state.answer_targets),
            "required_evidence_items": to_primitive(state.required_evidence_items),
            "coverage_assessments": to_primitive(state.coverage_assessments),
            "accepted_provisions": to_primitive(accepted),
            "answer_mode": state.answer_mode.value if state.answer_mode else AnswerMode.FULL.value,
            "answered_target_ids": list(state.answered_target_ids),
            "deferred_target_ids": list(state.deferred_target_ids),
            "state_version": len(state.action_trace),
        }

    def _benchmark_candidate_payload(self, state: RunState) -> Dict[str, Any]:
        requests_by_id = {
            request.request_id: request for request in state.query_history
        }
        candidates = []
        for candidate in state.candidate_provisions:
            payload = to_primitive(candidate)
            evidence_ids = list(candidate.target_evidence_item_ids)
            if not evidence_ids:
                source_ids = candidate.source_request_ids or [candidate.source_request_id]
                evidence_ids = [
                    requests_by_id[source_id].evidence_item_id
                    for source_id in source_ids
                    if source_id in requests_by_id
                ]
            if not evidence_ids:
                continue
            payload["supported_evidence_item_ids"] = list(dict.fromkeys(evidence_ids))
            candidates.append(payload)
        basis = (
            CandidateAnswerBasis.RETRIEVED_CANDIDATES.value
            if candidates
            else CandidateAnswerBasis.QUESTION_ONLY.value
        )
        return {
            "run_id": state.run_id,
            "question": state.question,
            "normalized_question": state.normalized_question,
            "legal_issues": to_primitive(state.legal_issues),
            "answer_targets": to_primitive(state.answer_targets),
            "required_evidence_items": to_primitive(state.required_evidence_items),
            "coverage_assessments": to_primitive(state.coverage_assessments),
            "accepted_provisions": [],
            "candidate_provisions": candidates,
            "candidate_answer_basis": basis,
            "answer_mode": "abstain_candidate",
            "answered_target_ids": [
                target.answer_target_id for target in state.answer_targets
            ],
            "deferred_target_ids": [],
            "state_version": len(state.action_trace),
        }

    def _apply_generation_scope(
        self,
        state: RunState,
        decision: PolicyDecision,
    ) -> None:
        state.answer_mode = decision.answer_mode or AnswerMode.FULL
        state.answered_target_ids = list(decision.answered_target_ids)
        state.deferred_target_ids = list(decision.deferred_target_ids)

    def _record_and_apply_generation_decision(
        self, state: RunState, decision: PolicyDecision
    ) -> None:
        record_policy_decision(
            state,
            decision.action.value,
            termination_reason=(
                decision.termination_reason.value if decision.termination_reason else None
            ),
            explanation=decision.explanation,
            answer_mode=decision.answer_mode.value if decision.answer_mode else None,
            answered_target_ids=decision.answered_target_ids,
            deferred_target_ids=decision.deferred_target_ids,
        )
        self._apply_generation_scope(state, decision)

    def _trace(self, event: str, state: RunState, **details: object) -> None:
        self.trace_sink.record(event, state, **details)

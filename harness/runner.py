"""End-to-end deterministic orchestration around externally supplied skills."""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .contracts import (
    AbstentionReason,
    OutcomeStatus,
    Phase,
    PolicyAction,
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
    validate_coverage_assessment,
    validate_gap_plan,
    validate_initial_plan,
    validate_retrieval_candidates,
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
    abstention_reason: Optional[AbstentionReason] = None
    termination_reason: Optional[TerminationReason] = None
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
                    "question": state.question,
                    "normalized_question": state.normalized_question,
                    "query_history": [],
                },
            )
            issues, evidence_items, initial_requests = validate_initial_plan(initial_raw)
            if len(initial_requests) > state.remaining_request_budget:
                raise ValidationError("initial retrieval requests exceed the frozen request budget")
            apply_initial_plan(state, issues, evidence_items)
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
            )
            self._trace("POLICY_DECISION", state, action=decision.action.value, explanation=decision.explanation)

            if decision.action is PolicyAction.GENERATE:
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
                return self._abstain(state, TerminationReason.NO_VALID_GAP_QUERY)
            if len(gap_requests) > state.remaining_request_budget:
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
            candidates = self.retriever.retrieve(requests, retrieval_round)
            validate_retrieval_candidates(candidates, requests, retrieval_round)
            register_retrieval_round(state, requests, candidates, is_gap=is_gap)
            self._trace(
                "GAP_RETRIEVAL_VALIDATED" if is_gap else "INITIAL_RETRIEVAL_VALIDATED",
                state,
                request_count=len(requests),
                candidate_count=len(candidates),
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
            state.record("ANSWER_DRAFT_VALIDATED", claim_count=len(answer.claims))
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
            termination_reason=TerminationReason.COMPLETED,
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
        return HarnessOutcome(
            status=OutcomeStatus.ABSTAIN,
            state=state,
            abstention_reason=reason,
            termination_reason=termination_reason,
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
            "normalized_question": state.normalized_question,
            "legal_issues": to_primitive(state.legal_issues),
            "required_evidence_items": to_primitive(state.required_evidence_items),
            "candidate_provisions": to_primitive(state.candidate_provisions),
        }

    def _gap_payload(self, state: RunState) -> Dict[str, Any]:
        return {
            "normalized_question": state.normalized_question,
            "missing_evidence_items": to_primitive(state.missing_critical_items),
            "evidence_conflicts": to_primitive(state.unresolved_critical_conflicts()),
            "accepted_provision_ids": sorted(state.accepted_provision_ids),
            "query_history": to_primitive(state.query_history),
            "seen_provision_ids": sorted(state.seen_provision_ids),
        }

    def _answer_payload(self, state: RunState) -> Dict[str, Any]:
        accepted = [
            candidate
            for candidate in state.candidate_provisions
            if candidate.provision_id in state.accepted_provision_ids
        ]
        return {
            "question": state.question,
            "legal_issues": to_primitive(state.legal_issues),
            "accepted_provisions": to_primitive(accepted),
        }

    def _trace(self, event: str, state: RunState, **details: object) -> None:
        self.trace_sink.record(event, state, **details)

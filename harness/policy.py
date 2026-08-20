"""Pure provision-coverage control policy.

Only this module selects a normal action. Skills, retrievers, and validators do
not select control flow.
"""

from .contracts import (
    AbstentionReason,
    AnswerMode,
    PolicyAction,
    PolicyDecision,
    TerminationReason,
)
from .run_state import RunState


def abstention_reason_for(state: RunState) -> AbstentionReason:
    if state.unresolved_critical_conflicts():
        return AbstentionReason.UNRESOLVED_EVIDENCE_CONFLICT
    return AbstentionReason.INSUFFICIENT_CRITICAL_EVIDENCE


def _generation_decision(state: RunState, mode: AnswerMode) -> PolicyDecision:
    all_target_ids = [target.answer_target_id for target in state.answer_targets]
    answered_target_ids = (
        state.covered_answer_target_ids()
        if mode is AnswerMode.LIMITED
        else all_target_ids
    )
    return PolicyDecision(
        action=PolicyAction.GENERATE,
        explanation={
            AnswerMode.FULL: "Every answer target has citable legal support.",
            AnswerMode.CONDITIONAL: "Legal support is complete; only question facts select an application branch.",
            AnswerMode.LIMITED: "Only the citable answer targets will be answered; remaining targets are deferred.",
        }[mode],
        answer_mode=mode,
        answered_target_ids=answered_target_ids,
        deferred_target_ids=[
            target_id for target_id in all_target_ids if target_id not in answered_target_ids
        ],
    )


def _limited_or_abstain(
    state: RunState,
    termination_reason: TerminationReason,
    explanation: str,
) -> PolicyDecision:
    if state.has_any_citable_answer_target():
        return _generation_decision(state, AnswerMode.LIMITED)
    return PolicyDecision(
        action=PolicyAction.ABSTAIN,
        termination_reason=termination_reason,
        explanation=explanation,
    )


def decide_next_action(
    state: RunState,
    can_attempt_gap_query: bool = True,
) -> PolicyDecision:
    """Apply the answer-target policy without calling any skill."""
    if state.unresolved_critical_conflicts():
        return PolicyDecision(
            action=PolicyAction.ABSTAIN,
            termination_reason=TerminationReason.NO_RETRIEVAL_PROGRESS,
            explanation="A substantive critical-evidence conflict remains unresolved.",
        )

    if state.all_answer_targets_legally_covered():
        mode = AnswerMode.CONDITIONAL if state.has_missing_fact() else AnswerMode.FULL
        return _generation_decision(state, mode)

    if state.no_progress_rounds >= 2:
        return _limited_or_abstain(
            state,
            TerminationReason.NO_RETRIEVAL_PROGRESS,
            "Two consecutive retrieval rounds did not improve critical evidence.",
        )

    if state.remaining_round_budget <= 0:
        return _limited_or_abstain(
            state,
            TerminationReason.MAX_RETRIEVAL_ROUNDS_REACHED,
            "The frozen maximum number of retrieval rounds was used.",
        )

    if state.remaining_request_budget <= 0:
        return _limited_or_abstain(
            state,
            TerminationReason.RETRIEVAL_BUDGET_EXHAUSTED,
            "The retrieval request budget was exhausted.",
        )

    if state.has_retrievable_statute_gap() and can_attempt_gap_query:
        return PolicyDecision(
            action=PolicyAction.RETRIEVE_GAP,
            explanation="A critical statute gap remains and bounded retrieval is allowed.",
        )

    if not can_attempt_gap_query:
        return _limited_or_abstain(
            state,
            TerminationReason.NO_VALID_GAP_QUERY,
            "No non-duplicate gap retrieval request can be produced.",
        )

    return _limited_or_abstain(
        state,
        TerminationReason.NO_RETRIEVAL_PROGRESS,
        "Critical evidence is not citable and no retrievable statute gap remains.",
    )

"""Pure provision-coverage control policy.

Only this module selects a normal action. Skills, retrievers, and validators do
not select control flow.
"""

from .contracts import (
    AbstentionReason,
    PolicyAction,
    PolicyDecision,
    TerminationReason,
)
from .run_state import RunState


def abstention_reason_for(state: RunState) -> AbstentionReason:
    if state.unresolved_critical_conflicts():
        return AbstentionReason.UNRESOLVED_EVIDENCE_CONFLICT
    return AbstentionReason.INSUFFICIENT_CRITICAL_EVIDENCE


def decide_next_action(
    state: RunState,
    can_attempt_gap_query: bool = True,
) -> PolicyDecision:
    """Apply the frozen three-action policy without calling any skill.

    `can_attempt_gap_query` is a preflight capability supplied by the runtime.
    A produced gap plan is still validated before retrieval.
    """
    if not state.has_critical_blockers() and not state.unresolved_critical_conflicts():
        return PolicyDecision(
            action=PolicyAction.GENERATE,
            explanation="All critical evidence items are covered without conflict.",
        )

    if state.no_progress_rounds >= 2:
        if state.can_generate_conditionally():
            return PolicyDecision(
                action=PolicyAction.GENERATE,
                explanation="Retrieval stalled, but every critical item has citable partial support; generate a conditional answer.",
            )
        return PolicyDecision(
            action=PolicyAction.ABSTAIN,
            termination_reason=TerminationReason.NO_RETRIEVAL_PROGRESS,
            explanation="Two consecutive retrieval rounds produced no progress.",
        )

    if state.remaining_round_budget <= 0:
        if state.can_generate_conditionally():
            return PolicyDecision(
                action=PolicyAction.GENERATE,
                explanation="The round budget is exhausted, but every critical item has citable partial support; generate a conditional answer.",
            )
        return PolicyDecision(
            action=PolicyAction.ABSTAIN,
            termination_reason=TerminationReason.MAX_RETRIEVAL_ROUNDS_REACHED,
            explanation="The frozen maximum number of retrieval rounds was used.",
        )

    if state.remaining_request_budget <= 0:
        if state.can_generate_conditionally():
            return PolicyDecision(
                action=PolicyAction.GENERATE,
                explanation="The request budget is exhausted, but every critical item has citable partial support; generate a conditional answer.",
            )
        return PolicyDecision(
            action=PolicyAction.ABSTAIN,
            termination_reason=TerminationReason.RETRIEVAL_BUDGET_EXHAUSTED,
            explanation="The retrieval request budget was exhausted.",
        )

    if not can_attempt_gap_query:
        return PolicyDecision(
            action=PolicyAction.ABSTAIN,
            termination_reason=TerminationReason.NO_VALID_GAP_QUERY,
            explanation="No non-duplicate gap retrieval request can be produced.",
        )

    return PolicyDecision(
        action=PolicyAction.RETRIEVE_GAP,
        explanation="Critical evidence remains and a bounded gap retrieval is allowed.",
    )

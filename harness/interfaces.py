"""Ports that keep model/skill implementations outside the deterministic harness."""

from typing import Any, Dict, List, Protocol, Sequence

from .contracts import AnswerDraft, CandidateProvision, CitationIntegrityResult, RetrievalRequest
from .run_state import RunState


class SkillExecutionError(RuntimeError):
    """An unavailable or failed external skill implementation."""


class SkillExecutor(Protocol):
    def execute(
        self,
        skill_name: str,
        entry_point: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        ...


class ProvisionRetriever(Protocol):
    def retrieve(
        self,
        requests: Sequence[RetrievalRequest],
        retrieval_round: int,
        *,
        critical_evidence_item_ids: Sequence[str] = (),
    ) -> List[CandidateProvision]:
        ...


class CitationIntegrityValidator(Protocol):
    def validate(self, state: RunState, answer: AnswerDraft) -> CitationIntegrityResult:
        ...

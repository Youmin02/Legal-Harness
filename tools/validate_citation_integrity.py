"""Deterministic citation ID, acceptance, snapshot, and claim checks."""

from typing import List, Protocol

from harness.contracts import AnswerDraft, CitationIntegrityResult
from harness.run_state import RunState


class CorpusLookup(Protocol):
    def get(self, provision_id: str):
        ...


class CitationIntegrityChecker:
    def __init__(self, corpus: CorpusLookup):
        self.corpus = corpus

    def validate(self, state: RunState, answer: AnswerDraft) -> CitationIntegrityResult:
        errors: List[str] = []
        citations_by_claim = {
            citation.claim_id: citation
            for citation in answer.claim_citations
        }
        for claim in answer.claims:
            citation = citations_by_claim.get(claim.claim_id)
            if citation is None or not citation.provision_ids:
                errors.append("MISSING_CITATION:%s" % claim.claim_id)
                continue
            for provision_id in citation.provision_ids:
                document = self.corpus.get(provision_id)
                if document is None:
                    errors.append("UNKNOWN_PROVISION_ID:%s" % provision_id)
                    continue
                if provision_id not in state.accepted_provision_ids:
                    errors.append("UNACCEPTED_PROVISION_ID:%s" % provision_id)
                snapshot = state.corpus_text_snapshots.get(provision_id)
                if snapshot is None:
                    errors.append("MISSING_PROVISION_SNAPSHOT:%s" % provision_id)
                elif snapshot != document.provision_text:
                    errors.append("PROVISION_SNAPSHOT_MISMATCH:%s" % provision_id)
        return CitationIntegrityResult(passed=not errors, errors=errors)

import unittest

from harness.contracts import (
    CoverageAssessment,
    CoverageStatus,
    LegalIssue,
    PolicyAction,
    RequiredEvidenceItem,
)
from harness.policy import decide_next_action
from harness.run_state import RunState
from harness.validation import ValidationError, normalize_question, validate_gap_plan


class PolicyAndValidationTests(unittest.TestCase):
    def test_non_critical_gap_does_not_block_generation(self):
        state = RunState(question="q", normalized_question="q", run_id="r")
        state.legal_issues = [LegalIssue("I1", "쟁점")]
        state.required_evidence_items = [
            RequiredEvidenceItem("E1", "I1", "requirement", "필수", True),
            RequiredEvidenceItem("E2", "I1", "exception", "비필수", False),
        ]
        state.coverage_assessments = [
            CoverageAssessment("E1", CoverageStatus.COVERED, ["P1"], "충족"),
            CoverageAssessment("E2", CoverageStatus.UNCOVERED, [], "미충족"),
        ]

        self.assertEqual(decide_next_action(state).action, PolicyAction.GENERATE)

    def test_duplicate_normalized_gap_query_is_rejected(self):
        state = RunState(question="q", normalized_question="q", run_id="r")
        state.legal_issues = [LegalIssue("I1", "쟁점")]
        state.required_evidence_items = [RequiredEvidenceItem("E1", "I1", "requirement", "필수", True)]
        state.query_history = [
            type("History", (), {"query_text": "  적용   요건 ", "request_id": "old"})()
        ]
        payload = {
            "gap_retrieval_requests": [
                {
                    "request_id": "RQ-I1-02",
                    "issue_id": "I1",
                    "evidence_item_id": "E1",
                    "query_channel": "sparse_keyword",
                    "query_text": "적용 요건",
                    "top_k": 100,
                }
            ]
        }

        with self.assertRaises(ValidationError):
            validate_gap_plan(payload, state)

    def test_normalization_preserves_meaning_and_only_normalizes_form(self):
        self.assertEqual(normalize_question("  제  3 조\n적용?  "), "제 3 조 적용?")

import importlib.util
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = (
    PROJECT_ROOT
    / "skills/legal_issue_and_query_planning/scripts/validate_output.py"
)
SPEC = importlib.util.spec_from_file_location("s1_validate_output", VALIDATOR_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VALIDATOR)


def gap_input():
    return {
        "run_id": "run-gap-id-test",
        "mode": "GAP_QUERY_PLAN",
        "constraints": {
            "allowed_query_channels": ["statute_aware"],
            "max_requests_per_issue": 3,
        },
        "legal_issues": [{"issue_id": "I1"}],
        "required_evidence_items": [{"evidence_item_id": "E1", "issue_id": "I1"}],
        "missing_evidence_items": [{"evidence_item_id": "E1"}],
        "evidence_conflicts": [],
        "query_history": [],
        "remaining_request_budget": 3,
    }


def gap_output(request_id):
    return {
        "schema_version": "1.0",
        "skill_id": "S1",
        "mode": "GAP_QUERY_PLAN",
        "status": "ok",
        "run_id": "run-gap-id-test",
        "target_evidence_item_ids": ["E1"],
        "gap_retrieval_requests": [
            {
                "request_id": request_id,
                "issue_id": "I1",
                "evidence_item_id": "E1",
                "query_channel": "statute_aware",
                "query_text": "적용 예외 요건",
                "query_terms": ["적용", "예외", "요건"],
                "statute_hints": [],
                "rationale": "미충족 요건을 확인한다.",
                "gap_reason": "필수 요건 조문이 부족하다.",
                "source_assessment_status": "uncovered",
            }
        ],
    }


class S1GapRequestIdValidationTests(unittest.TestCase):
    def test_accepts_round_and_index_gap_ids(self):
        for request_id in ("GRQ-R1-1", "GRQ-R2-3"):
            with self.subTest(request_id=request_id):
                self.assertEqual(VALIDATOR.validate(gap_output(request_id), gap_input()), [])

    def test_rejects_malformed_gap_ids(self):
        for request_id in ("GRQ1", "GRQ-R0-1", "GRQ-R1-0"):
            with self.subTest(request_id=request_id):
                errors = VALIDATOR.validate(gap_output(request_id), gap_input())
                self.assertIn("invalid request_id: %r" % request_id, errors)


if __name__ == "__main__":
    unittest.main()

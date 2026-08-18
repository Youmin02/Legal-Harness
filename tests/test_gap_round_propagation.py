import json
import unittest
from pathlib import Path

from runtime.local_ollama_executor import LocalOllamaSkillExecutor, SkillExecutionError

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class GapRoundPropagationTests(unittest.TestCase):
    def setUp(self):
        self.responses = iter(["두 번째 보충 질의", "세 번째 보충 질의"])

        def generator(prompt):
            self.assertIn("ENTRY POINT: GAP_QUERY_PLAN", prompt)
            query_text = next(self.responses)
            return json.dumps({"schema_version": "1.0", "skill_id": "S1", "mode": "GAP_QUERY_PLAN", "status": "ok", "run_id": "model-run-id", "target_evidence_item_ids": ["E1"], "gap_retrieval_requests": [{"request_id": "model-owned-id", "issue_id": "I1", "evidence_item_id": "E1", "query_channel": "statute_aware", "query_text": query_text, "source_assessment_status": "uncovered"}]}, ensure_ascii=False)

        self.executor = LocalOllamaSkillExecutor(PROJECT_ROOT / "skills", "test-model", generator=generator)

    @staticmethod
    def payload(next_retrieval_round, query_history):
        return {
            "run_id": "run-gap-rounds",
            "normalized_question": "적용 예외는 무엇인가",
            "next_retrieval_round": next_retrieval_round,
            "legal_issues": [{"issue_id": "I1"}],
            "required_evidence_items": [{"evidence_item_id": "E1", "issue_id": "I1", "evidence_type": "exception", "description": "적용 예외", "critical": True}],
            "coverage_assessments": [{"evidence_item_id": "E1", "status": "uncovered"}],
            "missing_evidence_items": [{"evidence_item_id": "E1"}],
            "evidence_conflicts": [],
            "query_history": query_history,
            "seen_provision_ids": [],
            "remaining_request_budget": 2,
        }

    def test_execute_canonicalizes_second_and_third_gap_round_ids(self):
        history = [{"request_id": "GRQ-R1-1", "query_text": "첫 번째 보충 질의"}]
        round_two_payload = self.payload(2, history)
        planning_input = self.executor._planning_input("GAP_QUERY_PLAN", round_two_payload, "run-gap-rounds")
        self.assertEqual(planning_input["next_retrieval_round"], 2)
        round_two = self.executor.execute("legal_issue_and_query_planning", "GAP_QUERY_PLAN", round_two_payload)
        self.assertEqual(round_two["gap_retrieval_requests"][0]["request_id"], "GRQ-R2-1")
        history.append(round_two["gap_retrieval_requests"][0])
        round_three = self.executor.execute("legal_issue_and_query_planning", "GAP_QUERY_PLAN", self.payload(3, history))
        self.assertEqual(round_three["gap_retrieval_requests"][0]["request_id"], "GRQ-R3-1")
        prior_queries = {item["query_text"] for item in history}
        self.assertNotIn(round_three["gap_retrieval_requests"][0]["query_text"], prior_queries)

    def test_execute_rejects_zero_boolean_and_missing_next_round(self):
        history = [{"request_id": "GRQ-R1-1", "query_text": "첫 번째 보충 질의"}]
        for invalid_round in (0, False, None):
            with self.subTest(next_retrieval_round=invalid_round):
                payload = self.payload(invalid_round, history)
                if invalid_round is None:
                    del payload["next_retrieval_round"]
                with self.assertRaisesRegex(SkillExecutionError, "next_retrieval_round must be a positive integer"):
                    self.executor.execute("legal_issue_and_query_planning", "GAP_QUERY_PLAN", payload)


if __name__ == "__main__":
    unittest.main()

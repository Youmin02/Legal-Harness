import json
import unittest
from pathlib import Path

from runtime.local_ollama_executor import LocalOllamaSkillExecutor


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LocalOllamaExecutorTests(unittest.TestCase):
    def setUp(self):
        self.executor = LocalOllamaSkillExecutor(
            skills_root=PROJECT_ROOT / "skills",
            model="test-model",
            generator=self._generate,
        )

    @staticmethod
    def _generate(prompt):
        if "ENTRY POINT: INITIAL_PLAN" in prompt:
            return json.dumps(
                {
                    "schema_version": "1.0",
                    "skill_id": "S1",
                    "mode": "INITIAL_PLAN",
                    "status": "ok",
                    "run_id": "run-1",
                    "legal_issues": [
                        {
                            "issue_id": "I1",
                            "issue_statement": "손해배상 요건",
                            "decision_question": "손해배상 요건은 무엇인가",
                            "importance": "critical",
                        }
                    ],
                    "required_evidence_items": [
                        {
                            "evidence_item_id": "E1",
                            "issue_id": "I1",
                            "evidence_type": "rule",
                            "description": "손해배상 규정",
                            "critical": True,
                            "completion_criteria": "책임의 근거 조문이 있다",
                        }
                    ],
                    "retrieval_requests": [
                        {
                            "request_id": "RQ1",
                            "issue_id": "I1",
                            "evidence_item_id": "E1",
                            "query_channel": "sparse_keywords",
                            "query_text": "손해배상 책임",
                            "query_terms": ["손해배상"],
                            "statute_hints": [],
                            "rationale": "책임 조문 검색",
                        }
                    ],
                },
                ensure_ascii=False,
            )
        if "ENTRY POINT: ASSESS_COVERAGE" in prompt:
            return json.dumps(
                {
                    "schema_version": "1.0",
                    "skill_id": "S2",
                    "mode": "ASSESS_COVERAGE",
                    "status": "ok",
                    "run_id": "run-1",
                    "evidence_links": [
                        {
                            "link_id": "L1",
                            "evidence_item_id": "E1",
                            "provision_id": "C001",
                            "relation": "supports",
                            "quoted_text": "[FULL_TEXT]",
                            "rationale": "책임을 정한다",
                        }
                    ],
                    "coverage_assessments": [
                        {
                            "evidence_item_id": "E1",
                            "status": "covered",
                            "linked_provision_ids": ["C001"],
                            "rationale": "책임 규정이 있다",
                            "satisfied_aspects": ["책임"],
                            "missing_aspects": [],
                        }
                    ],
                    "missing_evidence_items": [],
                    "evidence_conflicts": [],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "schema_version": "1.0",
                "skill_id": "S3",
                "mode": "GENERATE_ANSWER",
                "status": "ok",
                "run_id": "run-1",
                "answer": "손해를 배상해야 합니다.[CT1]",
                "claims": [
                    {
                        "claim_id": "C1",
                        "text": "손해를 배상해야 합니다.",
                        "claim_type": "legal_rule",
                        "applicability": "direct",
                        "citation_required": True,
                    }
                ],
                "claim_citations": [
                    {
                        "citation_id": "CT1",
                        "claim_id": "C1",
                        "provision_id": "P1",
                        "quoted_text": "손해를 배상한다",
                        "support_description": "책임의 근거",
                        "answer_marker": "[CT1]",
                    }
                ],
                "assumptions": [],
                "limitations": [],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _candidate():
        return {
            "provision_id": "P1",
            "statute_name": "예시법 제1조",
            "provision_text": "고의 또는 과실로 손해를 배상한다.",
            "issue_id": "I1",
            "source_request_id": "RQ1",
            "retrieval_round": 1,
            "first_stage_score": 1.0,
            "fusion_rank": 1,
            "rerank_score": 1.0,
        }

    def test_s1_maps_plural_sparse_channel_and_frozen_top_k(self):
        result = self.executor.execute(
            "legal_issue_and_query_planning",
            "INITIAL_PLAN",
            {
                "run_id": "run-1",
                "question": "손해배상 책임은 무엇인가",
                "normalized_question": "손해배상 책임은 무엇인가",
                "query_history": [],
            },
        )

        self.assertEqual(result["retrieval_requests"][0]["query_channel"], "sparse_keyword")
        self.assertEqual(result["retrieval_requests"][0]["top_k"], 100)
        self.assertEqual(result["required_evidence_items"][0]["completion_criteria"], "책임의 근거 조문이 있다")

    def test_s2_and_s3_map_rich_skill_contracts_to_harness_contracts(self):
        evidence = {
            "evidence_item_id": "E1",
            "issue_id": "I1",
            "evidence_type": "rule",
            "description": "손해배상 규정",
            "critical": True,
            "completion_criteria": "책임의 근거 조문이 있다",
        }
        coverage = self.executor.execute(
            "provision_coverage_assessment",
            "ASSESS_COVERAGE",
            {
                "run_id": "run-1",
                "normalized_question": "손해배상 책임은 무엇인가",
                "legal_issues": [{"issue_id": "I1", "description": "손해배상"}],
                "required_evidence_items": [evidence],
                "candidate_provisions": [self._candidate()],
            },
        )
        self.assertEqual(coverage["evidence_links"][0]["assessment"], "accepted")
        self.assertEqual(coverage["evidence_links"][0]["provision_id"], "P1")
        self.assertEqual(coverage["evidence_links"][0]["support_spans"], [{"start_char": 0, "end_char": len(self._candidate()["provision_text"])}])

        answer = self.executor.execute(
            "grounded_legal_answer_generation",
            "GENERATE_ANSWER",
            {
                "run_id": "run-1",
                "normalized_question": "손해배상 책임은 무엇인가",
                "legal_issues": [{"issue_id": "I1", "description": "손해배상"}],
                "required_evidence_items": [evidence],
                "coverage_assessments": coverage["coverage_assessments"],
                "accepted_provisions": [
                    dict(self._candidate(), supported_evidence_item_ids=["E1"])
                ],
                "state_version": 3,
            },
        )
        self.assertEqual(answer["claim_citations"], [{"claim_id": "C1", "provision_ids": ["P1"]}])

    def test_s1_normalizes_initial_and_gap_queries(self):
        initial = self.executor._normalize_harness_owned_fields(
            "legal_issue_and_query_planning",
            "INITIAL_PLAN",
            {"run_id": "run-1"},
            {
                "legal_issues": [
                    {"issue_id": "I1", "decision_question": "도박죄 처벌"},
                    {"issue_id": "I2", "decision_question": "도박죄 성립 요건"},
                ],
                "retrieval_requests": [
                    {"issue_id": "I1", "query_text": "도박죄 처벌 규정"},
                    {"issue_id": "I2", "query_text": "도박죄 처벌 규정"},
                ],
            },
        )
        initial_requests = initial["retrieval_requests"]
        self.assertEqual([item["request_id"] for item in initial_requests], ["RQ1", "RQ2"])
        self.assertNotEqual(initial_requests[0]["query_text"], initial_requests[1]["query_text"])

        gap = self.executor._normalize_harness_owned_fields(
            "legal_issue_and_query_planning",
            "GAP_QUERY_PLAN",
            {
                "run_id": "run-1",
                "required_evidence_items": [
                    {
                        "evidence_item_id": "E1",
                        "issue_id": "I1",
                        "description": "도박죄 처벌 규정",
                        "completion_criteria": "처벌 조문",
                    }
                ],
                "missing_evidence_items": [{"evidence_item_id": "E1"}],
                "evidence_conflicts": [],
                "query_history": [{"query_text": "기존 질의"}],
            },
            {
                "gap_retrieval_requests": [
                    {"issue_id": None, "evidence_item_id": None, "query_text": "기존 질의"}
                ]
            },
        )
        gap_request = gap["gap_retrieval_requests"][0]
        self.assertEqual(gap_request["request_id"], "GRQ1")
        self.assertEqual(gap_request["issue_id"], "I1")
        self.assertEqual(gap_request["evidence_item_id"], "E1")
        self.assertNotEqual(gap_request["query_text"], "기존 질의")
        self.assertEqual(gap["target_evidence_item_ids"], ["E1"])

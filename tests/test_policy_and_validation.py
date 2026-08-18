import unittest

from harness.contracts import (
    CandidateProvision,
    CandidateStageRecord,
    CoverageAssessment,
    CoverageStatus,
    EvidenceLink,
    LegalIssue,
    PolicyAction,
    QueryChannel,
    RequiredEvidenceItem,
    RetrievalRequest,
    SupportSpan,
)
from harness.policy import decide_next_action
from harness.run_state import RunState
from harness.state_update import apply_coverage_assessment, register_retrieval_round
from harness.validation import (
    ValidationError,
    normalize_question,
    validate_gap_plan,
    validate_retrieval_stage_records,
)


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

    def test_supported_partial_critical_generates_after_budget_exhaustion(self):
        state = RunState(
            question="q",
            normalized_question="q",
            run_id="r",
            remaining_round_budget=0,
        )
        state.required_evidence_items = [
            RequiredEvidenceItem("E1", "I1", "rule", "조건부 법리", True)
        ]
        state.coverage_assessments = [
            CoverageAssessment(
                "E1",
                CoverageStatus.PARTIALLY_COVERED,
                ["P1"],
                "사실 조건만 미확정",
                partial_kind="factual_condition",
                missing_aspects=["중대한 과실 해당 여부"],
            )
        ]
        state.evidence_links = [
            EvidenceLink("I1", "E1", "P1", [SupportSpan(0, 1)], "accepted")
        ]

        self.assertEqual(decide_next_action(state).action, PolicyAction.GENERATE)

    def test_uncovered_critical_still_abstains_after_budget_exhaustion(self):
        state = RunState(
            question="q",
            normalized_question="q",
            run_id="r",
            remaining_round_budget=0,
        )
        state.required_evidence_items = [
            RequiredEvidenceItem("E1", "I1", "rule", "핵심 법리", True)
        ]
        state.coverage_assessments = [
            CoverageAssessment("E1", CoverageStatus.UNCOVERED, [], "근거 없음")
        ]

        self.assertEqual(decide_next_action(state).action, PolicyAction.ABSTAIN)

    def test_coverage_cannot_regress_when_candidate_set_only_grows(self):
        state = RunState(question="q", normalized_question="q", run_id="r")
        state.required_evidence_items = [
            RequiredEvidenceItem("E1", "I1", "rule", "핵심 법리", True)
        ]
        prior = CoverageAssessment(
            "E1", CoverageStatus.COVERED, ["P1"], "기존 후보로 충족"
        )
        prior_link = EvidenceLink(
            "I1", "E1", "P1", [SupportSpan(0, 1)], "accepted"
        )
        state.coverage_assessments = [prior]
        state.evidence_links = [prior_link]

        apply_coverage_assessment(
            state,
            [],
            [CoverageAssessment("E1", CoverageStatus.UNCOVERED, [], "후속 판정 누락")],
            [],
        )

        self.assertEqual(state.coverage_assessments, [prior])
        self.assertEqual(state.evidence_links, [prior_link])

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

    def test_stage_provenance_must_match_source_request_evidence(self):
        request = RetrievalRequest(
            request_id="RQ1",
            issue_id="I1",
            evidence_item_id="E1",
            query_channel=QueryChannel.SPARSE_KEYWORD,
            query_text="법적 요건",
            top_k=100,
        )
        valid = CandidateStageRecord(
            provision_id="P1",
            retrieval_round=1,
            candidate_stage="first_stage",
            source_request_ids=["RQ1"],
            target_evidence_item_ids=["E1"],
            first_stage_rank=1,
            first_stage_score=2.0,
            selection_reason="request_top_k",
        )

        validate_retrieval_stage_records([valid], [request], retrieval_round=1)

        wrong_target = CandidateStageRecord(
            provision_id="P1",
            retrieval_round=1,
            candidate_stage="first_stage",
            source_request_ids=["RQ1"],
            target_evidence_item_ids=["E2"],
            first_stage_rank=1,
            first_stage_score=2.0,
            selection_reason="request_top_k",
        )
        with self.assertRaises(ValidationError):
            validate_retrieval_stage_records(
                [wrong_target], [request], retrieval_round=1
            )

    def test_candidate_merge_never_compares_raw_scores_across_rounds(self):
        state = RunState(question="q", normalized_question="q", run_id="r")
        requests = [
            RetrievalRequest(
                "RQ1", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "질의1"
            ),
            RetrievalRequest(
                "RQ2", "I1", "E2", QueryChannel.STATUTE_AWARE, "질의2"
            ),
        ]
        first = CandidateProvision(
            provision_id="P1",
            statute_name="테스트법",
            provision_text="동일 조문",
            issue_id="I1",
            source_request_id="RQ1",
            retrieval_round=1,
            first_stage_score=0.01,
            fusion_rank=3,
            rerank_score=0.1,
            source_request_ids=["RQ1"],
            target_evidence_item_ids=["E1"],
            first_stage_rank=7,
            rerank_rank=2,
        )
        later = CandidateProvision(
            provision_id="P1",
            statute_name="테스트법",
            provision_text="동일 조문",
            issue_id="I1",
            source_request_id="RQ2",
            retrieval_round=2,
            first_stage_score=1000.0,
            fusion_rank=1,
            rerank_score=999.0,
            source_request_ids=["RQ2"],
            target_evidence_item_ids=["E2"],
            first_stage_rank=1,
            rerank_rank=1,
        )

        register_retrieval_round(state, [requests[0]], [first], is_gap=False)
        register_retrieval_round(state, [requests[1]], [later], is_gap=True)

        merged = state.candidate_provisions[0]
        self.assertEqual(merged.source_request_id, "RQ1")
        self.assertEqual(merged.source_request_ids, ["RQ1", "RQ2"])
        self.assertEqual(merged.target_evidence_item_ids, ["E1", "E2"])
        self.assertEqual(merged.rerank_score, 0.1)
        self.assertEqual(merged.rerank_rank, 2)

    def test_normalization_preserves_meaning_and_only_normalizes_form(self):
        self.assertEqual(normalize_question("  제  3 조\n적용?  "), "제 3 조 적용?")

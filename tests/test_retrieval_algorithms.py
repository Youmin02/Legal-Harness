import sqlite3
import tempfile
import unittest
from pathlib import Path

from harness.contracts import QueryChannel, RetrievalRequest
from retrieval.bm25 import Bm25Retriever
from retrieval.corpus import (
    InMemoryProvisionCorpus,
    ProvisionDocument,
    legal_text_alias_key,
)
from retrieval.kure import KureExactVectorRetriever
from retrieval.pipeline import RetrievalPipeline
from retrieval.persistent import SqliteFts5Bm25Searcher, _query_terms_and_prefixes
from retrieval.reranker import CallableCrossEncoderReranker, PassThroughReranker
from retrieval.rrf import reciprocal_rank_fusion
from retrieval.types import RetrievalHit


class RecordingReranker:
    def __init__(self):
        self.scored_ids = []

    def rerank(self, query_text, hits, top_k):
        del query_text
        selected = list(hits[:top_k])
        self.scored_ids = [hit.document.provision_id for hit in selected]
        return [
            100.0 if hit.document.provision_id == "P9" else hit.rrf_score
            for hit in selected
        ]


class ScriptedFirstStage:
    def __init__(self, documents, rankings):
        self.documents = {
            document.provision_id: document for document in documents
        }
        self.rankings = rankings

    def search(self, request):
        provision_ids = self.rankings.get(request.request_id, [])
        return [
            RetrievalHit(
                self.documents[provision_id],
                float(len(provision_ids) - rank),
                request.request_id,
            )
            for rank, provision_id in enumerate(provision_ids)
        ]


class QueryRecordingFirstStage(ScriptedFirstStage):
    def __init__(self, documents, rankings):
        super().__init__(documents, rankings)
        self.queries = []

    def search(self, request):
        self.queries.append((request.query_text, list(request.query_terms)))
        return super().search(request)


class QueryRecordingReranker:
    def __init__(self, scores_by_query):
        self.scores_by_query = scores_by_query
        self.calls = []

    def rerank(self, query_text, hits, top_k):
        selected = list(hits[:top_k])
        self.calls.append(
            (query_text, [hit.document.provision_id for hit in selected])
        )
        scores = self.scores_by_query[query_text]
        return [scores[hit.document.provision_id] for hit in selected]


class RetrievalAlgorithmTests(unittest.TestCase):
    def setUp(self):
        self.documents = [
            ProvisionDocument("P1", "계약법", "계약 성립을 위한 청약과 승낙의 요건"),
            ProvisionDocument("P2", "계약법", "계약 해제의 효과"),
        ]
        self.corpus = InMemoryProvisionCorpus(self.documents)
        self.request = RetrievalRequest(
            request_id="RQ-I1-01",
            issue_id="I1",
            evidence_item_id="E1",
            query_channel=QueryChannel.PROVISION_STYLE,
            query_text="계약 성립 요건",
            top_k=100,
        )

    def test_bm25_and_pipeline_return_ranked_candidates(self):
        bm25 = Bm25Retriever(self.corpus)
        hits = bm25.search(self.request)
        pipeline = RetrievalPipeline(bm25, PassThroughReranker())
        candidates = pipeline.retrieve([self.request], retrieval_round=1)

        self.assertEqual(hits[0].document.provision_id, "P1")
        self.assertEqual(candidates[0].provision_id, "P1")
        self.assertEqual(candidates[0].retrieval_round, 1)

    def test_rrf_fuses_query_channels_without_mixing_retrievers(self):
        first = [
            RetrievalHit(self.documents[0], 2.0, "RQ-1"),
            RetrievalHit(self.documents[1], 1.0, "RQ-1"),
        ]
        second = [
            RetrievalHit(self.documents[1], 3.0, "RQ-2"),
            RetrievalHit(self.documents[0], 1.0, "RQ-2"),
        ]

        fused = reciprocal_rank_fusion([first, second])

        self.assertEqual([hit.document.provision_id for hit in fused], ["P1", "P2"])
        self.assertEqual(set(fused[0].source_request_ids), {"RQ-1", "RQ-2"})
        self.assertEqual(fused[0].first_stage_rank, 1)
        self.assertEqual(fused[0].fusion_rank, 1)
        self.assertEqual(fused[1].fusion_rank, 2)

    def test_kure_exact_vector_adapter_uses_injected_encoder(self):
        vectors = {"P1": [1.0, 0.0], "P2": [0.0, 1.0]}
        retriever = KureExactVectorRetriever(self.corpus, vectors, lambda query: [1.0, 0.0])

        hits = retriever.search(self.request)

        self.assertEqual(hits[0].document.provision_id, "P1")

    def test_bge_scores_full_pool_before_final_top_ten_cutoff(self):
        documents = [
            ProvisionDocument("P%d" % index, "테스트법", "공통어 조문 %d" % index)
            for index in range(1, 13)
        ]
        reranker = RecordingReranker()
        pipeline = RetrievalPipeline(
            Bm25Retriever(InMemoryProvisionCorpus(documents)),
            reranker,
            rerank_pool_k=100,
            final_top_k=10,
        )
        request = RetrievalRequest(
            request_id="RQ1",
            issue_id="I1",
            evidence_item_id="E1",
            query_channel=QueryChannel.SPARSE_KEYWORD,
            query_text="공통어",
            top_k=100,
        )

        candidates = pipeline.retrieve([request], retrieval_round=1)

        self.assertEqual(len(reranker.scored_ids), 12)
        self.assertEqual(candidates[0].provision_id, "P9")
        self.assertEqual(len(candidates), 10)
        self.assertEqual(candidates[0].rerank_rank, 1)
        self.assertNotEqual(candidates[0].fusion_rank, candidates[0].rerank_rank)
        self.assertEqual(len([x for x in pipeline.last_stage_records if x.candidate_stage == "first_stage"]), 12)
        self.assertEqual(len([x for x in pipeline.last_stage_records if x.candidate_stage == "selected"]), 10)

    def test_pipeline_preserves_all_request_and_evidence_provenance(self):
        documents = [
            ProvisionDocument("P1", "테스트법", "공통 근거"),
            ProvisionDocument("P2", "테스트법", "보조 근거"),
        ]
        requests = [
            RetrievalRequest(
                request_id="RQ1",
                issue_id="I1",
                evidence_item_id="E1",
                query_channel=QueryChannel.SPARSE_KEYWORD,
                query_text="공통",
                top_k=100,
            ),
            RetrievalRequest(
                request_id="RQ2",
                issue_id="I1",
                evidence_item_id="E2",
                query_channel=QueryChannel.SPARSE_KEYWORD,
                query_text="근거",
                top_k=100,
            ),
        ]

        candidates = RetrievalPipeline(
            Bm25Retriever(InMemoryProvisionCorpus(documents)),
            PassThroughReranker(),
            final_top_k=2,
        ).retrieve(requests, retrieval_round=1)

        shared = next(candidate for candidate in candidates if candidate.provision_id == "P1")
        self.assertEqual(shared.source_request_id, "RQ1")
        self.assertEqual(shared.source_request_ids, ["RQ1", "RQ2"])
        self.assertEqual(shared.target_evidence_item_ids, ["E1", "E2"])
        self.assertEqual(shared.first_stage_rank, 1)
        self.assertEqual(shared.candidate_stage, "selected")
        self.assertEqual(shared.selection_reason, "global_top_k")

    def test_callable_reranker_defaults_to_body_only_document_input(self):
        scored_pairs = []
        reranker = CallableCrossEncoderReranker(
            lambda query, document: scored_pairs.append((query, document)) or 1.0
        )
        hits = reciprocal_rank_fusion(
            [[RetrievalHit(self.documents[0], 1.0, "RQ-1")]]
        )

        scores = reranker.rerank("계약 요건", hits, top_k=1)

        self.assertEqual(scores, [1.0])
        self.assertEqual(
            scored_pairs,
            [("계약 요건", "계약 성립을 위한 청약과 승낙의 요건")],
        )

    def test_callable_reranker_can_include_statute_name_in_document_input(self):
        scored_documents = []
        reranker = CallableCrossEncoderReranker(
            lambda _query, document: scored_documents.append(document) or 1.0,
            document_mode="statute_and_body",
        )
        hits = reciprocal_rank_fusion(
            [[RetrievalHit(self.documents[0], 1.0, "RQ-1")]]
        )

        reranker.rerank("계약 요건", hits, top_k=1)

        self.assertEqual(
            scored_documents,
            ["계약법\n계약 성립을 위한 청약과 승낙의 요건"],
        )

    def test_callable_reranker_rejects_unknown_document_mode(self):
        with self.assertRaisesRegex(ValueError, "unsupported rerank document mode"):
            CallableCrossEncoderReranker(
                lambda _query, _document: 1.0,
                document_mode="unknown",
            )

    def test_explicit_baseline_mode_matches_default_candidate_order(self):
        documents = [
            ProvisionDocument("P1", "법1", "본문1"),
            ProvisionDocument("P2", "법2", "본문2"),
            ProvisionDocument("P3", "법3", "본문3"),
        ]
        requests = [
            RetrievalRequest(
                "RQ1",
                "I1",
                "E1",
                QueryChannel.SPARSE_KEYWORD,
                "질의1",
            ),
            RetrievalRequest(
                "RQ2",
                "I1",
                "E2",
                QueryChannel.STATUTE_AWARE,
                "질의2",
            ),
        ]
        rankings = {"RQ1": ["P1", "P2"], "RQ2": ["P3", "P2"]}

        default = RetrievalPipeline(
            ScriptedFirstStage(documents, rankings),
            PassThroughReranker(),
            final_top_k=2,
        ).retrieve(requests, retrieval_round=1)
        explicit = RetrievalPipeline(
            ScriptedFirstStage(documents, rankings),
            PassThroughReranker(),
            final_top_k=2,
            rerank_query_mode="combined_issue",
            candidate_selection="global_top_k",
            dedup_mode="none",
        ).retrieve(requests, retrieval_round=1)

        self.assertEqual(
            [candidate.provision_id for candidate in default],
            [candidate.provision_id for candidate in explicit],
        )
        self.assertEqual(
            [candidate.source_request_ids for candidate in default],
            [candidate.source_request_ids for candidate in explicit],
        )

    def test_first_stage_and_rerank_queries_are_independently_configurable(self):
        document = ProvisionDocument("P1", "법1 제1조", "정밀 근거")
        request = RetrievalRequest(
            "RQ1",
            "I1",
            "E1",
            QueryChannel.SPARSE_KEYWORD,
            "legacy combined query",
            query_terms=["legacy"],
            first_stage_query_text="BM25 recall query",
            rerank_query_text="BGE precision query",
        )
        first_stage = QueryRecordingFirstStage([document], {"RQ1": ["P1"]})
        reranker = QueryRecordingReranker(
            {"BGE precision query": {"P1": 1.0}}
        )

        RetrievalPipeline(first_stage, reranker).retrieve(
            [request], retrieval_round=1
        )

        self.assertEqual(first_stage.queries, [("BM25 recall query", [])])
        self.assertEqual(
            [query for query, _ in reranker.calls], ["BGE precision query"]
        )

    def test_legal_text_alias_key_normalizes_unicode_and_whitespace(self):
        first = ProvisionDocument("P1", "공직선거법  제18조", " 선거권이   없는 자 ")
        second = ProvisionDocument("P2", "공직선거법 제18조", "선거권이 없는 자")

        self.assertEqual(legal_text_alias_key(first), legal_text_alias_key(second))

    def test_alias_dedup_preserves_raw_stages_and_final_alias_ids(self):
        documents = [
            ProvisionDocument("P1", "공직선거법 제18조", "선거권이 없는 자"),
            ProvisionDocument("P2", "공직선거법 제18조", "선거권이 없는 자"),
            ProvisionDocument("P3", "공직선거법 제19조", "선거권 회복"),
        ]
        request = RetrievalRequest(
            "RQ1", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "선거권"
        )
        pipeline = RetrievalPipeline(
            ScriptedFirstStage(documents, {"RQ1": ["P1", "P2", "P3"]}),
            PassThroughReranker(),
            final_top_k=2,
            dedup_mode="legal_text_alias",
        )

        candidates = pipeline.retrieve([request], retrieval_round=1)

        self.assertEqual([candidate.provision_id for candidate in candidates], ["P1", "P3"])
        self.assertEqual(candidates[0].alias_provision_ids, ["P1", "P2"])
        self.assertEqual(
            [
                record.provision_id
                for record in pipeline.last_stage_records
                if record.candidate_stage == "bge_rerank"
            ],
            ["P1", "P2", "P3"],
        )
        collapse = [
            record
            for record in pipeline.last_stage_records
            if record.candidate_stage == "dedup_collapse"
        ]
        self.assertEqual(len(collapse), 1)
        self.assertEqual(collapse[0].alias_provision_ids, ["P1", "P2"])

    def test_alias_dedup_does_not_merge_same_body_from_different_statutes(self):
        documents = [
            ProvisionDocument("P1", "법A 제1조", "공통 문장"),
            ProvisionDocument("P2", "법B 제1조", "공통 문장"),
        ]
        request = RetrievalRequest(
            "RQ1", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "공통"
        )

        candidates = RetrievalPipeline(
            ScriptedFirstStage(documents, {"RQ1": ["P1", "P2"]}),
            PassThroughReranker(),
            final_top_k=2,
            dedup_mode="legal_text_alias",
        ).retrieve([request], retrieval_round=1)

        self.assertEqual([candidate.provision_id for candidate in candidates], ["P1", "P2"])
        self.assertEqual(
            [candidate.alias_provision_ids for candidate in candidates],
            [["P1"], ["P2"]],
        )

    def test_qa_139_duplicate_cutoff_regression_recovers_article_18(self):
        documents = []
        ranking = []
        for index in range(1, 6):
            statute = "중복법 제%d조" % index
            body = "중복 snapshot 본문 %d" % index
            for alias in ("A", "B"):
                provision_id = "D%d%s" % (index, alias)
                documents.append(ProvisionDocument(provision_id, statute, body))
                ranking.append(provision_id)
        documents.append(
            ProvisionDocument("ARTICLE_18", "공직선거법 제18조", "선거권이 없는 자")
        )
        ranking.append("ARTICLE_18")
        request = RetrievalRequest(
            "RQ139", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "선거권"
        )

        baseline = RetrievalPipeline(
            ScriptedFirstStage(documents, {"RQ139": ranking}),
            PassThroughReranker(),
            final_top_k=10,
            dedup_mode="none",
        ).retrieve([request], retrieval_round=1)
        proposed = RetrievalPipeline(
            ScriptedFirstStage(documents, {"RQ139": ranking}),
            PassThroughReranker(),
            final_top_k=10,
            dedup_mode="legal_text_alias",
        ).retrieve([request], retrieval_round=1)

        self.assertNotIn("ARTICLE_18", [candidate.provision_id for candidate in baseline])
        self.assertIn("ARTICLE_18", [candidate.provision_id for candidate in proposed])

    def test_per_request_reranking_never_concatenates_repeated_context(self):
        documents = [
            ProvisionDocument("P1", "법1", "본문1"),
            ProvisionDocument("P2", "법2", "본문2"),
        ]
        requests = [
            RetrievalRequest(
                "RQ1",
                "I1",
                "E1",
                QueryChannel.SPARSE_KEYWORD,
                "요건 [원문 맥락] 사실",
            ),
            RetrievalRequest(
                "RQ2",
                "I1",
                "E2",
                QueryChannel.STATUTE_AWARE,
                "예외 [원문 맥락] 사실",
            ),
        ]
        scores = {
            requests[0].query_text: {"P1": 1.0},
            requests[1].query_text: {"P2": 1.0},
        }
        reranker = QueryRecordingReranker(scores)
        pipeline = RetrievalPipeline(
            ScriptedFirstStage(
                documents,
                {"RQ1": ["P1"], "RQ2": ["P2"]},
            ),
            reranker,
            final_top_k=2,
            rerank_query_mode="per_request",
        )

        pipeline.retrieve(requests, retrieval_round=1)

        queries = [query for query, _ in reranker.calls]
        self.assertEqual(queries, [request.query_text for request in requests])
        self.assertTrue(all(query.count("[원문 맥락]") == 1 for query in queries))
        stages = {record.candidate_stage for record in pipeline.last_stage_records}
        self.assertTrue({"rrf", "evidence_fusion"}.issubset(stages))
        request_stage = [record for record in pipeline.last_stage_records if record.candidate_stage == "request_rerank"]
        bge_stage = [record for record in pipeline.last_stage_records if record.candidate_stage == "bge_rerank"]
        self.assertEqual([record.provision_id for record in request_stage], ["P1", "P2"])
        self.assertEqual([record.provision_id for record in bge_stage], ["P1", "P2"])
        self.assertEqual([record.rerank_rank for record in bge_stage], [1, 2])

    def test_evidence_balancing_uses_ranks_not_cross_query_raw_scores(self):
        documents = [
            ProvisionDocument("P1", "법1", "E1 상위"),
            ProvisionDocument("P2", "법1", "E1 하위"),
            ProvisionDocument("P3", "법2", "E2 상위"),
            ProvisionDocument("P4", "법2", "E2 하위"),
        ]
        requests = [
            RetrievalRequest(
                "RQ1", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "질의1"
            ),
            RetrievalRequest(
                "RQ2", "I1", "E2", QueryChannel.STATUTE_AWARE, "질의2"
            ),
        ]
        reranker = QueryRecordingReranker(
            {
                "질의1": {"P1": 1000.0, "P2": 999.0},
                "질의2": {"P3": 0.2, "P4": 0.1},
            }
        )
        pipeline = RetrievalPipeline(
            ScriptedFirstStage(
                documents,
                {"RQ1": ["P1", "P2"], "RQ2": ["P3", "P4"]},
            ),
            reranker,
            final_top_k=2,
            rerank_query_mode="per_request",
            candidate_selection="evidence_balanced",
            per_evidence_min_k=1,
        )

        candidates = pipeline.retrieve(
            requests,
            retrieval_round=1,
            critical_evidence_item_ids=["E1", "E2"],
        )

        self.assertEqual(
            [candidate.provision_id for candidate in candidates],
            ["P1", "P3"],
        )
        self.assertEqual(
            {candidate.target_evidence_item_ids[0] for candidate in candidates},
            {"E1", "E2"},
        )

    def test_per_request_aliases_share_one_critical_quota_slot(self):
        documents = [
            ProvisionDocument("P1", "공직선거법 제18조", "선거권이 없는 자"),
            ProvisionDocument("P2", "공직선거법 제18조", "선거권이 없는 자"),
        ]
        requests = [
            RetrievalRequest("RQ1", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "선거권"),
            RetrievalRequest("RQ2", "I1", "E2", QueryChannel.STATUTE_AWARE, "선거권"),
        ]
        pipeline = RetrievalPipeline(
            ScriptedFirstStage(documents, {"RQ1": ["P1"], "RQ2": ["P2"]}),
            QueryRecordingReranker(
                {"선거권": {"P1": 1.0, "P2": 1.0}}
            ),
            final_top_k=1,
            rerank_query_mode="per_request",
            candidate_selection="evidence_balanced",
            dedup_mode="legal_text_alias",
        )

        candidates = pipeline.retrieve(
            requests,
            retrieval_round=1,
            critical_evidence_item_ids=["E1", "E2"],
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].alias_provision_ids, ["P1", "P2"])
        self.assertEqual(candidates[0].source_request_ids, ["RQ1", "RQ2"])
        self.assertEqual(candidates[0].target_evidence_item_ids, ["E1", "E2"])
        self.assertEqual(candidates[0].selection_reason, "critical_quota:E1,E2")

    def test_per_round_budget_applies_one_final_cutoff_across_issues(self):
        documents = [
            ProvisionDocument("P1", "법1 제1조", "E1 우선"),
            ProvisionDocument("P2", "법1 제2조", "E1 보조"),
            ProvisionDocument("P3", "법2 제1조", "E2 우선"),
            ProvisionDocument("P4", "법2 제2조", "E2 보조"),
        ]
        requests = [
            RetrievalRequest("RQ1", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "질의1"),
            RetrievalRequest("RQ2", "I2", "E2", QueryChannel.STATUTE_AWARE, "질의2"),
        ]
        pipeline = RetrievalPipeline(
            ScriptedFirstStage(
                documents,
                {"RQ1": ["P1", "P2"], "RQ2": ["P3", "P4"]},
            ),
            QueryRecordingReranker(
                {
                    "질의1": {"P1": 10.0, "P2": 1.0},
                    "질의2": {"P3": 8.0, "P4": 9.0},
                }
            ),
            final_top_k=3,
            rerank_query_mode="per_request",
            candidate_selection="evidence_balanced",
            candidate_budget_scope="per_round",
        )

        candidates = pipeline.retrieve(
            requests,
            retrieval_round=1,
            critical_evidence_item_ids=["E1", "E2"],
        )

        self.assertEqual([candidate.provision_id for candidate in candidates], ["P1", "P4", "P3"])
        self.assertEqual(
            [candidate.selection_reason for candidate in candidates],
            [
                "critical_quota:E1",
                "critical_quota:E2",
                "round_global_score_fill",
            ],
        )

    def test_per_round_global_top_k_skips_critical_quotas(self):
        documents = [
            ProvisionDocument("P1", "법1 제1조", "E1 우선"),
            ProvisionDocument("P2", "법1 제2조", "E1 보조"),
            ProvisionDocument("P3", "법2 제1조", "E2 우선"),
        ]
        requests = [
            RetrievalRequest("RQ1", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "질의1"),
            RetrievalRequest("RQ2", "I2", "E2", QueryChannel.STATUTE_AWARE, "질의2"),
        ]
        pipeline = RetrievalPipeline(
            ScriptedFirstStage(
                documents,
                {"RQ1": ["P1", "P2"], "RQ2": ["P3"]},
            ),
            QueryRecordingReranker(
                {
                    "질의1": {"P1": 10.0, "P2": 9.0},
                    "질의2": {"P3": 1.0},
                }
            ),
            final_top_k=2,
            rerank_query_mode="per_request",
            candidate_selection="global_top_k",
            candidate_budget_scope="per_round",
        )

        candidates = pipeline.retrieve(
            requests,
            retrieval_round=1,
            critical_evidence_item_ids=["E1", "E2"],
        )

        self.assertEqual([candidate.provision_id for candidate in candidates], ["P1", "P2"])
        self.assertEqual(
            [candidate.selection_reason for candidate in candidates],
            ["round_global_top_k", "round_global_top_k"],
        )
        self.assertEqual(pipeline.last_unsatisfied_critical_evidence_item_ids, [])

    def test_shared_provision_satisfies_multiple_quotas_and_keeps_provenance(self):
        documents = [
            ProvisionDocument("P0", "공통법", "공통"),
            ProvisionDocument("P1", "법1", "E1"),
            ProvisionDocument("P2", "법2", "E2"),
        ]
        requests = [
            RetrievalRequest(
                "RQ1", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "질의1"
            ),
            RetrievalRequest(
                "RQ2", "I1", "E2", QueryChannel.STATUTE_AWARE, "질의2"
            ),
        ]
        reranker = QueryRecordingReranker(
            {
                "질의1": {"P0": 2.0, "P1": 1.0},
                "질의2": {"P0": 0.2, "P2": 0.1},
            }
        )
        pipeline = RetrievalPipeline(
            ScriptedFirstStage(
                documents,
                {"RQ1": ["P0", "P1"], "RQ2": ["P0", "P2"]},
            ),
            reranker,
            final_top_k=2,
            rerank_query_mode="per_request",
            candidate_selection="evidence_balanced",
        )

        candidates = pipeline.retrieve(
            requests,
            retrieval_round=1,
            critical_evidence_item_ids=["E1", "E2"],
        )

        shared = candidates[0]
        self.assertEqual(shared.provision_id, "P0")
        self.assertEqual(shared.source_request_ids, ["RQ1", "RQ2"])
        self.assertEqual(shared.target_evidence_item_ids, ["E1", "E2"])
        self.assertEqual(
            shared.selection_reason,
            "critical_quota:E1,E2",
        )
        self.assertEqual(
            [candidate.provision_id for candidate in candidates].count("P0"),
            1,
        )

    def test_noncritical_evidence_can_fill_but_does_not_receive_quota(self):
        documents = [
            ProvisionDocument("P1", "법1", "critical"),
            ProvisionDocument("P2", "법2", "noncritical"),
        ]
        requests = [
            RetrievalRequest(
                "RQ1", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "질의1"
            ),
            RetrievalRequest(
                "RQ2", "I1", "E2", QueryChannel.STATUTE_AWARE, "질의2"
            ),
        ]
        pipeline = RetrievalPipeline(
            ScriptedFirstStage(
                documents,
                {"RQ1": ["P1"], "RQ2": ["P2"]},
            ),
            QueryRecordingReranker(
                {"질의1": {"P1": 1.0}, "질의2": {"P2": 1.0}}
            ),
            final_top_k=2,
            rerank_query_mode="per_request",
            candidate_selection="evidence_balanced",
        )

        candidates = pipeline.retrieve(
            requests,
            retrieval_round=1,
            critical_evidence_item_ids=["E1"],
        )
        reasons = {
            candidate.provision_id: candidate.selection_reason
            for candidate in candidates
        }

        self.assertEqual(reasons["P1"], "critical_quota:E1")
        self.assertEqual(reasons["P2"], "rank_fusion_fill")

    def test_evidence_quota_reports_unfulfilled_items_without_preemptive_error(self):
        documents = [
            ProvisionDocument("P1", "법1", "본문1"),
            ProvisionDocument("P2", "법2", "본문2"),
        ]
        requests = [
            RetrievalRequest(
                "RQ1", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "질의1"
            ),
            RetrievalRequest(
                "RQ2", "I1", "E2", QueryChannel.STATUTE_AWARE, "질의2"
            ),
        ]
        pipeline = RetrievalPipeline(
            ScriptedFirstStage(
                documents,
                {"RQ1": ["P1"], "RQ2": ["P2"]},
            ),
            QueryRecordingReranker(
                {"질의1": {"P1": 1.0}, "질의2": {"P2": 1.0}}
            ),
            final_top_k=2,
            rerank_query_mode="per_request",
            candidate_selection="evidence_balanced",
            per_evidence_min_k=2,
        )

        candidates = pipeline.retrieve(
            requests,
            retrieval_round=1,
            critical_evidence_item_ids=["E1", "E2"],
        )
        self.assertEqual([candidate.provision_id for candidate in candidates], ["P1", "P2"])
        self.assertEqual(
            pipeline.last_unsatisfied_critical_evidence_item_ids, ["E1", "E2"]
        )

    def test_quota_never_exceeds_candidate_budget_when_quotas_compete(self):
        documents = [
            ProvisionDocument("P1", "법1", "E1-1"),
            ProvisionDocument("P2", "법1", "E1-2"),
            ProvisionDocument("P3", "법2", "E2-1"),
            ProvisionDocument("P4", "법2", "E2-2"),
        ]
        requests = [
            RetrievalRequest("RQ1", "I1", "E1", QueryChannel.SPARSE_KEYWORD, "질의1"),
            RetrievalRequest("RQ2", "I1", "E2", QueryChannel.STATUTE_AWARE, "질의2"),
        ]
        pipeline = RetrievalPipeline(
            ScriptedFirstStage(documents, {"RQ1": ["P1", "P2"], "RQ2": ["P3", "P4"]}),
            QueryRecordingReranker({
                "질의1": {"P1": 2.0, "P2": 1.0},
                "질의2": {"P3": 2.0, "P4": 1.0},
            }),
            final_top_k=2,
            rerank_query_mode="per_request",
            candidate_selection="evidence_balanced",
            per_evidence_min_k=2,
        )

        candidates = pipeline.retrieve(
            requests, retrieval_round=1, critical_evidence_item_ids=["E1", "E2"]
        )

        self.assertEqual([candidate.provision_id for candidate in candidates], ["P1", "P3"])
        self.assertLessEqual(len(candidates), 2)
        self.assertEqual(
            pipeline.last_unsatisfied_critical_evidence_item_ids, ["E1", "E2"]
        )

    def test_sqlite_bm25_bridges_korean_legal_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.sqlite3"
            connection = sqlite3.connect(database_path)
            connection.execute(
                "CREATE VIRTUAL TABLE provision_fts USING fts5("
                "provision_id UNINDEXED, statute_name, provision_text)"
            )
            connection.execute(
                "INSERT INTO provision_fts VALUES (?, ?, ?)",
                (
                    "GOLD",
                    "상법 814조 운송인의 채권ㆍ채무의 소멸 1항",
                    "운송인이 운송물을 인도한 날부터 1년 이내에 재판상 청구가 없으면 소멸한다.",
                ),
            )
            connection.commit()
            connection.close()
            request = RetrievalRequest(
                request_id="RQ1",
                issue_id="I1",
                evidence_item_id="E1",
                query_channel=QueryChannel.PROVISION_STYLE,
                query_text="상품이 인도된 날로부터 언제까지 청구할 수 있는가",
                query_terms=["운송계약"],
                top_k=100,
            )

            hits = SqliteFts5Bm25Searcher(database_path).search(request)

            self.assertEqual([hit.document.provision_id for hit in hits], ["GOLD"])

    def test_bare_focus_term_becomes_prefix_without_expanding_source_noise(self):
        request = RetrievalRequest(
            request_id="RQ1",
            issue_id="I1",
            evidence_item_id="E1",
            query_channel=QueryChannel.PROVISION_STYLE,
            query_text=(
                "운송계약 소멸시효 기간 "
                "[원문 맥락] 상품이 인도된 날부터 고민하게 되었다"
            ),
            query_terms=["운송계약", "운송인", "소멸시효"],
            top_k=100,
        )

        _, prefixes = _query_terms_and_prefixes(request)

        self.assertIn("기간", prefixes)
        self.assertNotIn("고민하게", prefixes)
        self.assertIn("운송인", prefixes)

    def test_statute_hint_channel_cannot_evict_lexical_top_eighty_percent(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.sqlite3"
            connection = sqlite3.connect(database_path)
            connection.execute(
                "CREATE VIRTUAL TABLE provision_fts USING fts5("
                "provision_id UNINDEXED, statute_name, provision_text)"
            )
            connection.executemany(
                "INSERT INTO provision_fts VALUES (?, ?, ?)",
                [
                    ("H%d" % index, "상법 %d조" % index, "운송인의 책임")
                    for index in range(10)
                ],
            )
            connection.commit()
            lexical_rows = [
                ("L%d" % index, "일반법", "lexical", float(100 - index))
                for index in range(10)
            ]
            searcher = SqliteFts5Bm25Searcher(database_path)

            merged = searcher._merge_statute_hint_hits(
                connection,
                lexical_rows,
                ["상법"],
                ["운송인"],
                10,
            )

            self.assertEqual([row[0] for row in merged[:8]], ["L%d" % i for i in range(8)])

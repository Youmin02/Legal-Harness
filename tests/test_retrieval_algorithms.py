import sqlite3
import tempfile
import unittest
from pathlib import Path

from harness.contracts import QueryChannel, RetrievalRequest
from retrieval.bm25 import Bm25Retriever
from retrieval.corpus import InMemoryProvisionCorpus, ProvisionDocument
from retrieval.kure import KureExactVectorRetriever
from retrieval.pipeline import RetrievalPipeline
from retrieval.persistent import SqliteFts5Bm25Searcher, _query_terms_and_prefixes
from retrieval.reranker import PassThroughReranker
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
            query_terms=["운송계약", "소멸시효"],
            top_k=100,
        )

        _, prefixes = _query_terms_and_prefixes(request)

        self.assertIn("기간", prefixes)
        self.assertNotIn("고민하게", prefixes)

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

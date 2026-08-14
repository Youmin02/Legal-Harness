import unittest

from harness.contracts import QueryChannel, RetrievalRequest
from retrieval.bm25 import Bm25Retriever
from retrieval.corpus import InMemoryProvisionCorpus, ProvisionDocument
from retrieval.kure import KureExactVectorRetriever
from retrieval.pipeline import RetrievalPipeline
from retrieval.reranker import PassThroughReranker
from retrieval.rrf import reciprocal_rank_fusion
from retrieval.types import RetrievalHit


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

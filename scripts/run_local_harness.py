#!/usr/bin/env python3
"""Run one Korean statutory QA question through the local legal harness."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from harness.contracts import OutcomeStatus
from harness.runner import HarnessConfig, HarnessRunner
from harness.skill_registry import assert_skill_layout_complete
from retrieval.corpus import InMemoryProvisionCorpus
from retrieval.persistent import KureExactIndexSearcher, SqliteFts5Bm25Searcher
from retrieval.pipeline import RetrievalPipeline
from retrieval.reranker import LocalBgeCrossEncoderReranker
from runtime.comparison_guard import resolve_frozen_configuration
from runtime.experiment_record import ExperimentRecord
from runtime.local_ollama_executor import (
    DEFAULT_S1_TRUNCATION_RETRY_MAX_TOKENS,
    DEFAULT_SKILL_MAX_TOKENS,
    LocalOllamaSkillExecutor,
)
from runtime.source_snapshot import (
    assert_source_snapshot_unchanged,
    capture_clean_source_snapshot,
)
from tools.validate_citation_integrity import CitationIntegrityChecker



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="Korean statutory question to run")
    parser.add_argument("--retriever", choices=("bm25", "kure"), default="bm25")
    parser.add_argument("--model", default="legal-harness-qwen")
    parser.add_argument("--skills-root", type=Path, default=PROJECT_ROOT / "skills")
    parser.add_argument("--ollama-endpoint", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--num-ctx", type=int, default=32768)
    parser.add_argument(
        "--s1-max-tokens",
        type=int,
        default=DEFAULT_SKILL_MAX_TOKENS["legal_issue_and_query_planning"],
    )
    parser.add_argument(
        "--s1-truncation-retry-max-tokens",
        type=int,
        default=DEFAULT_S1_TRUNCATION_RETRY_MAX_TOKENS,
    )
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--requests", type=int, default=9)
    parser.add_argument("--rerank-pool-k", type=int, default=100)
    parser.add_argument("--final-top-k", type=int, choices=(10, 20, 30), default=10)
    parser.add_argument(
        "--rerank-query-mode",
        choices=("combined_issue", "per_request"),
        default="combined_issue",
    )
    parser.add_argument(
        "--candidate-selection",
        choices=("global_top_k", "evidence_balanced"),
        default="global_top_k",
    )
    parser.add_argument("--per-evidence-min-k", type=int, default=1)
    parser.add_argument(
        "--candidate-budget-scope",
        choices=("per_issue", "per_round"),
        default="per_issue",
    )
    parser.add_argument(
        "--dedup-mode",
        choices=("none", "legal_text_alias"),
        default="none",
    )
    parser.add_argument(
        "--rerank-document-mode",
        choices=("body_only", "statute_and_body"),
        default="body_only",
    )
    parser.add_argument("--input-format", default="question_only")
    parser.add_argument("--record-dir", type=Path, default=PROJECT_ROOT / "records/runs")
    parser.add_argument("--question-id", help="stable benchmark item ID, for example qa_19_1hop_28")
    parser.add_argument("--condition", default="M", help="frozen experimental condition ID")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--result-file", type=Path, help="write the complete run result as JSON")
    parser.add_argument("--expected-git-commit")
    parser.add_argument("--expected-source-manifest-sha256")
    return parser.parse_args()


def build_retriever(args: argparse.Namespace) -> RetrievalPipeline:
    bm25_path = PROJECT_ROOT / "data/koblex/indexes/bm25/statute_fts5.sqlite3"
    if args.retriever == "bm25":
        first_stage = SqliteFts5Bm25Searcher(bm25_path)
    else:
        first_stage = KureExactIndexSearcher(
            vectors_path=PROJECT_ROOT / "data/koblex/indexes/kure-v1/vectors.f32.npy",
            provision_ids_path=PROJECT_ROOT / "data/koblex/indexes/kure-v1/provision_ids.txt",
            normalized_corpus_path=PROJECT_ROOT / "data/koblex/normalized/statute.jsonl",
            model_path=PROJECT_ROOT / "models/huggingface/nlpai-lab--KURE-v1",
            device="cuda",
        )
    reranker = LocalBgeCrossEncoderReranker(
        PROJECT_ROOT / "models/huggingface/dragonkue--bge-reranker-v2-m3-ko",
        device="cuda",
        document_mode=args.rerank_document_mode,
    )
    return RetrievalPipeline(
        first_stage,
        reranker,
        rerank_pool_k=args.rerank_pool_k,
        final_top_k=args.final_top_k,
        rerank_query_mode=args.rerank_query_mode,
        candidate_selection=args.candidate_selection,
        per_evidence_min_k=args.per_evidence_min_k,
        dedup_mode=args.dedup_mode,
        candidate_budget_scope=args.candidate_budget_scope,
    )


def main() -> int:
    args = parse_args()
    source_snapshot = capture_clean_source_snapshot(PROJECT_ROOT)
    if (
        args.expected_git_commit is not None
        and source_snapshot.git_commit != args.expected_git_commit
    ):
        raise RuntimeError("Git commit does not match the frozen batch source")
    if (
        args.expected_source_manifest_sha256 is not None
        and source_snapshot.source_manifest_sha256
        != args.expected_source_manifest_sha256
    ):
        raise RuntimeError("source manifest hash does not match the frozen batch source")

    run_id = str(uuid.uuid4())
    configuration = resolve_frozen_configuration({
        "condition": args.condition,
        "seed": args.seed,
        "retriever": args.retriever,
        "model": args.model,
        "ollama_endpoint": args.ollama_endpoint,
        "num_ctx": args.num_ctx,
        "total_retrieval_rounds": args.rounds,
        "total_retrieval_requests": args.requests,
        "rerank_pool_k": args.rerank_pool_k,
        "final_top_k": args.final_top_k,
        "candidate_budget_scope": args.candidate_budget_scope,
        "rerank_query_mode": args.rerank_query_mode,
        "candidate_selection": args.candidate_selection,
        "per_evidence_min_k": args.per_evidence_min_k,
        "dedup_mode": args.dedup_mode,
        "rerank_document_mode": args.rerank_document_mode,
        "conditional_generation": "answer_target_full_conditional_limited",
        "planning_contract": "answer_targets_required",
        "monotonic_coverage": True,
        "input_format": args.input_format,
        "s1_max_tokens": args.s1_max_tokens,
        "s1_truncation_retry_max_tokens": (
            args.s1_truncation_retry_max_tokens
        ),
        "source_manifest_sha256": source_snapshot.source_manifest_sha256,
    })
    record = ExperimentRecord(
        record_root=args.record_dir,
        run_id=run_id,
        project_root=PROJECT_ROOT,
        skills_root=args.skills_root,
        configuration=configuration,
        question=args.question,
        question_id=args.question_id,
        source_snapshot=source_snapshot.to_dict(),
    )
    assert_skill_layout_complete(args.skills_root)
    corpus = InMemoryProvisionCorpus.from_jsonl(
        PROJECT_ROOT / "data/koblex/normalized/statute.jsonl"
    )
    runner = HarnessRunner(
        skill_executor=LocalOllamaSkillExecutor(
            skills_root=args.skills_root,
            model=args.model,
            endpoint=args.ollama_endpoint,
            num_ctx=args.num_ctx,
            diagnostic_sink=record.record_skill_attempt,
            s1_max_tokens=args.s1_max_tokens,
            s1_truncation_retry_max_tokens=args.s1_truncation_retry_max_tokens,
        ),
        retriever=build_retriever(args),
        citation_validator=CitationIntegrityChecker(corpus),
        config=HarnessConfig(
            total_retrieval_rounds=args.rounds,
            total_retrieval_requests=args.requests,
        ),
        trace_sink=record.trace_sink,
    )
    outcome = runner.run(args.question, run_id=run_id)
    assert_source_snapshot_unchanged(PROJECT_ROOT, source_snapshot)
    record_result_path = record.finalize(outcome)
    assert_source_snapshot_unchanged(PROJECT_ROOT, source_snapshot)
    summary = {
        "status": outcome.status.value,
        "record_directory": str(record.directory),
        "record_result_file": str(record_result_path),
        "condition": args.condition,
        "seed": args.seed,
        "question_id": args.question_id,
        "termination_reason": outcome.termination_reason.value if outcome.termination_reason else None,
        "abstention_reason": outcome.abstention_reason.value if outcome.abstention_reason else None,
        "run_id": outcome.state.run_id,
        "retrieval_rounds_used": outcome.state.retrieval_rounds_used,
        "accepted_provision_ids": sorted(outcome.state.accepted_provision_ids),
        "candidate_answer_status": (
            outcome.candidate_answer_status.value
            if outcome.candidate_answer_status
            else None
        ),
        "candidate_answer_basis": (
            outcome.candidate_answer_basis.value
            if outcome.candidate_answer_basis
            else None
        ),
        "errors": outcome.errors,
    }
    result = dict(summary, answer=outcome.answer, candidate_answer=outcome.candidate_answer)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.result_file:
        args.result_file.parent.mkdir(parents=True, exist_ok=True)
        args.result_file.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if outcome.answer:
        print("\n--- answer ---\n" + outcome.answer)
    elif outcome.candidate_answer:
        print("\n--- benchmark candidate (ABSTAIN remains public status) ---\n" + outcome.candidate_answer)
    return 0 if outcome.status is OutcomeStatus.ANSWER else 1


if __name__ == "__main__":
    raise SystemExit(main())

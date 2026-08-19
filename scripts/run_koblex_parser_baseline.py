#!/usr/bin/env python3
"""Run the official KoBLEX ParSeR baseline (paper's own method, not the
project's skill harness) over the KoBLEX QA set using a local Ollama model.

This is intentionally a separate code path from scripts/run_local_harness.py
and scripts/run_bm25_bge_pilot_batch.py. See baselines/koblex_parser/__init__.py
and docs/KOBLEX_PARSER_BASELINE_REPRODUCTION_NOTES.md for what is and is not
reproduced from the official repository.

Example (smoke test, 3 questions):
  .venv/bin/python scripts/run_koblex_parser_baseline.py \\
    --output-dir records/baselines/koblex-parser-qwen38-q8-smoke-<uuid> \\
    --limit 3

Example (full 226-question run, launch inside tmux):
  .venv/bin/python scripts/run_koblex_parser_baseline.py \\
    --output-dir records/baselines/koblex-parser-qwen38-q8-226-<uuid>
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pyarrow.parquet as pq  # noqa: E402

from baselines.koblex_parser.pipeline import (  # noqa: E402
    BM25_TOP_K,
    RERANK_TOP_L,
    STAGE1_MAX_TOKENS,
    STAGE2_MAX_TOKENS,
    STAGE3_MAX_TOKENS,
    TEMPERATURE,
    ItemResult,
    run_item,
)
from baselines.koblex_parser.retrieval import Bm25Retriever, CrossEncoderReranker, load_statute_corpus  # noqa: E402


def _git_commit(project_root: Path) -> Optional[str]:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(project_root), check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_source_worktree_dirty(project_root: Path) -> Optional[bool]:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=str(project_root),
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return any(line[3:] and not line[3:].startswith("records/") for line in status.splitlines())


def load_qa_items(parquet_path: Path) -> List[Dict[str, Any]]:
    table = pq.read_table(str(parquet_path))
    return table.to_pylist()


def load_completed_ids(output_dir: Path) -> Set[str]:
    path = output_dir / "final_results.jsonl"
    if not path.is_file():
        return set()
    completed = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            qid = record.get("question_id")
            if qid:
                completed.add(qid)
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-parquet", type=Path, default=PROJECT_ROOT / "data/koblex/qa/test-00000-of-00001.parquet")
    parser.add_argument(
        "--statute-parquet", type=Path, default=PROJECT_ROOT / "data/koblex/statute/corpus-00000-of-00001.parquet"
    )
    parser.add_argument("--model", type=str, default="legal-harness-qwen38-q8")
    parser.add_argument(
        "--reranker-path", type=Path, default=PROJECT_ROOT / "models/huggingface/dragonkue--bge-reranker-v2-m3-ko"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N items (smoke tests).")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--endpoint", type=str, default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--num-ctx", type=int, default=32768)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--progress-every", type=int, default=5)
    parser.add_argument(
        "--resume", action="store_true", help="Skip question_ids already present in an existing final_results.jsonl."
    )
    args = parser.parse_args()

    output_dir: Path = args.output_dir
    if output_dir.exists() and not args.resume:
        raise SystemExit(
            "output dir already exists: %s (pass --resume to continue an interrupted run, "
            "or pick a new UUID directory -- do not overwrite completed run records)" % output_dir
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    completed_ids = load_completed_ids(output_dir) if args.resume else set()
    if completed_ids:
        print("Resuming: %d question_ids already completed, skipping." % len(completed_ids))

    print("Loading QA items from %s" % args.qa_parquet)
    qa_items = load_qa_items(args.qa_parquet)
    if args.start_index:
        qa_items = qa_items[args.start_index :]
    if args.limit is not None:
        qa_items = qa_items[: args.limit]
    print("Loaded %d QA items to process." % len(qa_items))

    print("Loading statute corpus from %s" % args.statute_parquet)
    statute_records = load_statute_corpus(args.statute_parquet)
    print("Loaded %d statute provisions." % len(statute_records))

    print("Building BM25 index (bm25s, stopwords='en', matching official ParSeR utils.py)...")
    bm25 = Bm25Retriever(statute_records)
    print("BM25 index built in %.1fs." % bm25.build_seconds)

    print("Loading CrossEncoder reranker from %s" % args.reranker_path)
    reranker = CrossEncoderReranker(args.reranker_path)

    ollama_kwargs = {"endpoint": args.endpoint, "num_ctx": args.num_ctx, "timeout_seconds": args.timeout_seconds}

    run_metadata = {
        "baseline": "ParSeR (Reproduced) -- KoBLEX paper's own proposed method, corrected per the paper's stated algorithm rather than a byte-for-byte copy of the released code; see docs/KOBLEX_PARSER_BASELINE_REPRODUCTION_NOTES.md",
        "source_repository": "https://github.com/daehuikim/KoBLEX",
        "source_paper": "https://aclanthology.org/2025.emnlp-main.200/",
        "deviations_from_released_code": [
            "Fixed a confirmed indexing bug in the official "
            "experiments/parser/vllm/selection_retrieval.py process_completions(): "
            "the released code always selects from contexts_list[0] (the first "
            "parametric provision's reranked candidates) for every sub-query. This "
            "reproduction selects each provision's answer from its OWN reranked "
            "top-10, matching the paper's stated algorithm.",
            "Did not reproduce the official utils.py escape_quotes() double-escaping "
            "quirk (manual backslash-escaping followed by json.dumps, which escapes "
            "again); parsed parametric-provision strings are kept as-is and JSON-"
            "escaped exactly once when written to disk.",
        ],
        "not_run": [
            "Official LF-Eval (GPT-4o G-Eval via deepeval) was NOT run: requires an "
            "OpenAI API key and incurs external API cost that must be pre-registered "
            "before spending. Token-F1 and retrieval P/R/F1/EM (both fully local, "
            "zero-cost, and defined identically to experiments/lf-eval/eval_pipeline.py) "
            "are computed by scripts/evaluate_koblex_parser_baseline.py instead."
        ],
        "hyperparameters": {
            "bm25_top_k_per_subquery": BM25_TOP_K,
            "rerank_top_l_shown_to_llm": RERANK_TOP_L,
            "temperature": TEMPERATURE,
            "stage1_max_tokens": STAGE1_MAX_TOKENS,
            "stage2_max_tokens": STAGE2_MAX_TOKENS,
            "stage3_max_tokens": STAGE3_MAX_TOKENS,
            "num_ctx": args.num_ctx,
        },
        "model": args.model,
        "reranker_path": str(args.reranker_path),
        "qa_parquet": str(args.qa_parquet),
        "statute_parquet": str(args.statute_parquet),
        "statute_corpus_size": len(statute_records),
        "qa_items_planned": len(qa_items),
        "start_index": args.start_index,
        "limit": args.limit,
        "git_commit": _git_commit(PROJECT_ROOT),
        "git_source_worktree_dirty": _git_source_worktree_dirty(PROJECT_ROOT),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
    }
    (output_dir / "run_metadata.json").write_text(
        json.dumps(run_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    final_results_path = output_dir / "final_results.jsonl"
    stage_trace_path = output_dir / "stage_trace.jsonl"
    final_handle = final_results_path.open("a", encoding="utf-8")
    trace_handle = stage_trace_path.open("a", encoding="utf-8")

    n_done = 0
    n_errors = 0
    latencies: List[float] = []
    wall_start = time.monotonic()

    try:
        for i, item in enumerate(qa_items, start=1):
            question_id = item["id"]
            if question_id in completed_ids:
                continue

            gold_contexts = ["%s%s" % (c["hierarchy"], c["content"]) for c in (item.get("contexts") or [])]

            try:
                result: ItemResult = run_item(
                    question_id=question_id,
                    background=item["background"] or "",
                    question=item["question"] or "",
                    bm25=bm25,
                    reranker=reranker,
                    model=args.model,
                    ollama_kwargs=ollama_kwargs,
                )
            except Exception as exc:  # noqa: BLE001 - one bad item must not kill a multi-hour run
                n_errors += 1
                error_record = {
                    "question_id": question_id,
                    "background": item.get("background"),
                    "question": item.get("question"),
                    "answer": "",
                    "provisions": [],
                    "n_hops": item.get("n_hops"),
                    "gold_answer": item.get("answer"),
                    "gold_contexts": gold_contexts,
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
                final_handle.write(json.dumps(error_record, ensure_ascii=False) + "\n")
                final_handle.flush()
                print("[%d/%d] %s ERROR: %s: %s" % (i, len(qa_items), question_id, type(exc).__name__, exc))
                continue

            final_record = {
                "question_id": result.question_id,
                "background": result.background,
                "question": result.question,
                "answer": result.answer,
                "provisions": result.selected_provisions,
                "n_hops": item.get("n_hops"),
                "gold_answer": item.get("answer"),
                "gold_contexts": gold_contexts,
                "parametric_provisions": result.parametric_provisions,
                "stage1_latency_seconds": round(result.stage1_latency_seconds, 3),
                "stage2_latency_seconds": round(result.stage2_latency_seconds, 3),
                "stage3_latency_seconds": round(result.stage3_latency_seconds, 3),
                "total_latency_seconds": round(result.total_latency_seconds, 3),
                "error": result.error,
            }
            final_handle.write(json.dumps(final_record, ensure_ascii=False) + "\n")
            final_handle.flush()

            trace_record = {
                "question_id": result.question_id,
                "parametric_provisions": result.parametric_provisions,
                "stage1_raw_text": result.stage1_raw_text,
                "stage3_raw_text": result.stage3_raw_text,
                "selections": [
                    {
                        "parametric_provision": trace.parametric_provision,
                        "bm25_candidate_count": trace.bm25_candidate_count,
                        "bm25_top_k_texts": trace.bm25_top_k_texts,
                        "reranked_top_l": trace.reranked_top_l,
                        "llm_raw_text": trace.llm_raw_text,
                        "llm_choice_index": trace.llm_choice_index,
                        "selected_text": trace.selected_text,
                        "latency_seconds": round(trace.latency_seconds, 3),
                    }
                    for trace in result.selection_traces
                ],
            }
            trace_handle.write(json.dumps(trace_record, ensure_ascii=False) + "\n")
            trace_handle.flush()

            n_done += 1
            latencies.append(result.total_latency_seconds)
            if result.error:
                n_errors += 1

            if i % args.progress_every == 0 or i == len(qa_items):
                elapsed = time.monotonic() - wall_start
                avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
                remaining = len(qa_items) - i
                eta_seconds = remaining * avg_latency
                print(
                    "[%d/%d] done=%d errors=%d avg_latency=%.1fs elapsed=%.0fs eta=%.0fs (%s)"
                    % (i, len(qa_items), n_done, n_errors, avg_latency, elapsed, eta_seconds, question_id)
                )
    finally:
        final_handle.close()
        trace_handle.close()

    summary = {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "items_processed": n_done,
        "items_errored": n_errors,
        "wall_seconds": round(time.monotonic() - wall_start, 1),
        "mean_latency_seconds": round(sum(latencies) / len(latencies), 2) if latencies else None,
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("Run complete:", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

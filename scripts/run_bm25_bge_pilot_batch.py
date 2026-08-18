#!/usr/bin/env python3
"""Run the remaining entries in the frozen BM25+BGE pilot sequentially."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Set


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "data/koblex/manifests/bm25_bge_pilot_20_seed_20260815.json"
DEFAULT_RECORD_ROOT = PROJECT_ROOT / "records/runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--start-ordinal", type=int, default=1)
    parser.add_argument("--end-ordinal", type=int)
    parser.add_argument("--batch-name")
    parser.add_argument("--python", type=Path, default=PROJECT_ROOT / ".venv/bin/python")
    parser.add_argument("--record-root", type=Path, default=DEFAULT_RECORD_ROOT)
    parser.add_argument("--batch-log-root", type=Path, default=PROJECT_ROOT / "records/batches")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_questions(dataset_path: Path) -> Dict[str, Mapping[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("install pyarrow in the project environment to run the pilot batch") from exc
    rows = pq.read_table(
        dataset_path, columns=["id", "background", "question", "n_hops"]
    ).to_pylist()
    return {str(row["id"]): row for row in rows}


def format_benchmark_input(question: Mapping[str, Any]) -> str:
    background = str(question.get("background") or "").strip()
    prompt = str(question.get("question") or "").strip()
    if not prompt:
        raise RuntimeError("benchmark question text is empty")
    if not background:
        return "[질문]\n%s" % prompt
    return "[배경 시나리오]\n%s\n\n[질문]\n%s" % (background, prompt)


def record_directories(root: Path) -> Set[Path]:
    if not root.exists():
        return set()
    return {path for path in root.iterdir() if path.is_dir()}


def read_result(created: Iterable[Path]) -> Dict[str, Any]:
    directories = sorted(created)
    if len(directories) != 1:
        return {"record_directory_count": len(directories), "status": "NO_UNIQUE_RECORD"}
    directory = directories[0]
    result_file = directory / "result.json"
    outcome: Dict[str, Any] = {"record_directory": str(directory)}
    if not result_file.is_file():
        outcome["status"] = "NO_FINAL_RESULT"
        return outcome
    result = json.loads(result_file.read_text(encoding="utf-8"))
    outcome.update(
        {
            "status": result.get("status"),
            "termination_reason": result.get("termination_reason"),
            "abstention_reason": result.get("abstention_reason"),
            "errors": result.get("errors", []),
            "end_to_end_latency_ms": result.get("end_to_end_latency_ms"),
        }
    )
    return outcome


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = PROJECT_ROOT / manifest_path
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest["source_dataset"]
    dataset_path = PROJECT_ROOT / source["path"]
    if sha256(dataset_path) != source["sha256"]:
        raise RuntimeError("KoBLEX dataset hash does not match the frozen pilot manifest")
    if not args.python.is_file():
        raise RuntimeError("project Python is unavailable: %s" % args.python)

    questions = load_questions(dataset_path)
    configuration = manifest["frozen_configuration"]
    if args.end_ordinal is not None and args.end_ordinal < args.start_ordinal:
        raise RuntimeError("end ordinal cannot be smaller than start ordinal")
    entries: List[Mapping[str, Any]] = [
        entry
        for entry in manifest["entries"]
        if int(entry["ordinal"]) >= args.start_ordinal
        and (
            args.end_ordinal is None
            or int(entry["ordinal"]) <= args.end_ordinal
        )
    ]
    if not entries:
        raise RuntimeError("no pilot entries remain at or after ordinal %d" % args.start_ordinal)

    batch_name = args.batch_name or manifest.get("name", "bm25-bge-batch")
    batch_id = "%s-%s" % (batch_name, uuid.uuid4())
    batch_dir = args.batch_log_root / batch_id
    batch_dir.mkdir(parents=True, exist_ok=False)
    (batch_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    batch_metadata = {
        "batch_id": batch_id,
        "started_at_utc": utc_now(),
        "manifest": str(manifest_path.relative_to(PROJECT_ROOT)),
        "manifest_sha256": sha256(manifest_path),
        "start_ordinal": args.start_ordinal,
        "end_ordinal": args.end_ordinal,
        "entry_count": len(entries),
        "configuration": configuration,
    }
    (batch_dir / "metadata.json").write_text(
        json.dumps(batch_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    summary_path = batch_dir / "summary.jsonl"
    has_failure = False
    with summary_path.open("w", encoding="utf-8") as summary:
        for entry in entries:
            ordinal = int(entry["ordinal"])
            question_id = str(entry["question_id"])
            question = questions.get(question_id)
            if question is None:
                raise RuntimeError("question ID missing from frozen dataset: %s" % question_id)
            if int(question["n_hops"]) != int(entry["n_hops"]):
                raise RuntimeError("hop count mismatch for %s" % question_id)
            log_path = batch_dir / ("%02d_%s.log" % (ordinal, question_id))
            benchmark_input = format_benchmark_input(question)
            command = [
                str(args.python),
                str(PROJECT_ROOT / "scripts/run_local_harness.py"),
                benchmark_input,
                "--retriever", configuration["retriever"],
                "--model", configuration["model"],
                "--num-ctx", str(configuration["num_ctx"]),
                "--rounds", str(configuration["total_retrieval_rounds"]),
                "--requests", str(configuration["total_retrieval_requests"]),
                "--question-id", question_id,
                "--condition", configuration["condition"],
                "--seed", str(configuration["seed"]),
                "--rerank-pool-k", str(configuration.get("rerank_pool_k", 100)),
                "--final-top-k", str(configuration.get("final_top_k", 10)),
                "--rerank-query-mode", str(configuration.get("rerank_query_mode", "combined_issue")),
                "--candidate-selection", str(configuration.get("candidate_selection", "global_top_k")),
                "--per-evidence-min-k", str(configuration.get("per_evidence_min_k", 1)),
                "--rerank-document-mode", str(configuration.get("rerank_document_mode", "body_only")),
                "--input-format", str(
                    configuration.get(
                        "input_format", "koblex_background_plus_question"
                    )
                ),
            ]
            before = record_directories(args.record_root)
            started_at = utc_now()
            with log_path.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    command,
                    cwd=PROJECT_ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
            outcome = read_result(record_directories(args.record_root) - before)
            status = outcome.get("status")
            normal = status in {"ANSWER", "ABSTAIN"}
            has_failure = has_failure or not normal
            summary_row = {
                "ordinal": ordinal,
                "question_id": question_id,
                "n_hops": entry["n_hops"],
                "started_at_utc": started_at,
                "completed_at_utc": utc_now(),
                "exit_code": completed.returncode,
                "log_file": str(log_path.relative_to(PROJECT_ROOT)),
                **outcome,
            }
            summary.write(json.dumps(summary_row, ensure_ascii=False) + "\n")
            summary.flush()
            print(json.dumps(summary_row, ensure_ascii=False), flush=True)

    batch_metadata["completed_at_utc"] = utc_now()
    batch_metadata["has_execution_failure"] = has_failure
    (batch_dir / "metadata.json").write_text(
        json.dumps(batch_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 1 if has_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())

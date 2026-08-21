#!/usr/bin/env python3
"""Reconcile ambiguous KURE batch rows, then run the frozen evaluator.

The original batch is never modified.  Rows marked ``NO_UNIQUE_RECORD`` are
joined to immutable run directories by condition, question ID, and run start
time.  A separate reconciled batch is written for evaluation.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALID_STATUSES = {"ANSWER", "ABSTAIN", "EXECUTION_FAILURE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--output-batch-dir", type=Path, required=True)
    parser.add_argument("--output-evaluation-dir", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, default=PROJECT_ROOT / "records/runs")
    parser.add_argument("--condition", required=True)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=30)
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("JSON root must be an object: %s" % path)
    return payload


def read_summary(path: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def wait_for_batch(batch_dir: Path, poll_seconds: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    last_count = -1
    while True:
        metadata = read_json(batch_dir / "metadata.json")
        rows = read_summary(batch_dir / "summary.jsonl")
        expected = int(metadata["entry_count"])
        if len(rows) != last_count:
            print("Waiting for source batch: %d/%d" % (len(rows), expected), flush=True)
            last_count = len(rows)
        if metadata.get("completed_at_utc") and len(rows) == expected:
            return metadata, rows
        if not 0 <= len(rows) <= expected:
            raise RuntimeError("source batch summary count is invalid")
        time.sleep(poll_seconds)


def load_run_candidates(runs_root: Path, condition: str) -> List[Tuple[Path, Dict[str, Any]]]:
    candidates: List[Tuple[Path, Dict[str, Any]]] = []
    for metadata_path in runs_root.glob("*/metadata.json"):
        try:
            metadata = read_json(metadata_path)
        except (OSError, json.JSONDecodeError, RuntimeError):
            continue
        if metadata.get("configuration", {}).get("condition") == condition:
            candidates.append((metadata_path.parent.resolve(), metadata))
    return candidates


def result_summary(result: Mapping[str, Any], run_dir: Path) -> Dict[str, Any]:
    return {
        "record_directory": str(run_dir),
        "status": result.get("status"),
        "termination_reason": result.get("termination_reason"),
        "abstention_reason": result.get("abstention_reason"),
        "errors": result.get("errors", []),
        "end_to_end_latency_ms": result.get("end_to_end_latency_ms"),
    }


def reconcile(
    rows: List[Dict[str, Any]],
    candidates: List[Tuple[Path, Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], List[int]]:
    output: List[Dict[str, Any]] = []
    repaired_ordinals: List[int] = []
    for original in rows:
        row = dict(original)
        if row.get("status") != "NO_UNIQUE_RECORD":
            if row.get("status") not in VALID_STATUSES:
                raise RuntimeError("unexpected source status for ordinal %s" % row.get("ordinal"))
            output.append(row)
            continue

        started = datetime.fromisoformat(str(row["started_at_utc"]))
        completed = datetime.fromisoformat(str(row["completed_at_utc"]))
        matches: List[Path] = []
        for run_dir, metadata in candidates:
            if metadata.get("question_id") != row.get("question_id"):
                continue
            run_started = datetime.fromisoformat(str(metadata["started_at_utc"]))
            if started.timestamp() - 5 <= run_started.timestamp() <= completed.timestamp() + 5:
                if (run_dir / "result.json").is_file():
                    matches.append(run_dir)
        if len(matches) != 1:
            raise RuntimeError(
                "ordinal %s has %d matching KURE run directories"
                % (row.get("ordinal"), len(matches))
            )
        run_dir = matches[0]
        result = read_json(run_dir / "result.json")
        if result.get("status") not in VALID_STATUSES:
            raise RuntimeError("matched run has invalid status: %s" % run_dir)
        row.update(result_summary(result, run_dir))
        row["record_reconciliation"] = {
            "original_status": "NO_UNIQUE_RECORD",
            "method": "condition_question_id_and_start_time_window",
        }
        repaired_ordinals.append(int(row["ordinal"]))
        output.append(row)
    return output, repaired_ordinals


def main() -> int:
    args = parse_args()
    batch_dir = resolve(args.batch_dir).resolve()
    output_batch_dir = resolve(args.output_batch_dir).resolve()
    output_evaluation_dir = resolve(args.output_evaluation_dir).resolve()
    runs_root = resolve(args.runs_root).resolve()
    if output_batch_dir.exists() or output_evaluation_dir.exists():
        raise RuntimeError("refusing to overwrite an existing reconciled output")

    if args.wait:
        metadata, rows = wait_for_batch(batch_dir, args.poll_seconds)
    else:
        metadata = read_json(batch_dir / "metadata.json")
        rows = read_summary(batch_dir / "summary.jsonl")
    expected = int(metadata["entry_count"])
    if not metadata.get("completed_at_utc") or len(rows) != expected:
        raise RuntimeError("source batch is not complete")

    candidates = load_run_candidates(runs_root, args.condition)
    reconciled, repaired_ordinals = reconcile(rows, candidates)
    output_batch_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(batch_dir / "manifest.json", output_batch_dir / "manifest.json")
    reconciled_metadata = dict(metadata)
    reconciled_metadata["batch_id"] = str(metadata["batch_id"]) + "-reconciled"
    reconciled_metadata["reconciliation"] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_batch_directory": str(batch_dir),
        "method": "condition_question_id_and_start_time_window",
        "repaired_ordinals": repaired_ordinals,
    }
    (output_batch_dir / "metadata.json").write_text(
        json.dumps(reconciled_metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_batch_dir / "summary.jsonl").open("w", encoding="utf-8") as handle:
        for row in reconciled:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        "Reconciled %d rows into %s" % (len(repaired_ordinals), output_batch_dir),
        flush=True,
    )

    completed = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv/bin/python"),
            str(PROJECT_ROOT / "scripts/evaluate_dev_runs.py"),
            "--batch-dir",
            str(output_batch_dir),
            "--output-dir",
            str(output_evaluation_dir),
        ],
        cwd=PROJECT_ROOT,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

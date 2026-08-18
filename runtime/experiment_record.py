"""Write immutable, paper-ready artifacts for one harness execution."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Mapping, Optional

from harness.tracing import JsonlTraceSink, to_primitive


RECORD_SCHEMA_VERSION = "1.1"
RETRIEVAL_PROVENANCE_SCHEMA_VERSION = "1.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_worktree_dirty_from_porcelain(status: str) -> bool:
    return any(
        line[3:] and not line[3:].startswith("records/")
        for line in status.splitlines()
    )


def _git_source_worktree_dirty(project_root: Path) -> Optional[bool]:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=str(project_root), check=True, capture_output=True, text=True,
        ).stdout
        return _source_worktree_dirty_from_porcelain(status)
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_commit(project_root: Path) -> Optional[str]:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _package_versions() -> Dict[str, Optional[str]]:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - Python 3.8 fallback
        return {}
    versions: Dict[str, Optional[str]] = {}
    for package in ("torch", "transformers", "sentence-transformers", "pyarrow"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    return versions


def _ollama_model_artifact(model: object) -> Optional[str]:
    if not isinstance(model, str) or not model:
        return None
    try:
        modelfile = subprocess.run(
            ["ollama", "show", model, "--modelfile"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in modelfile.splitlines():
        if line.startswith("FROM "):
            return line.removeprefix("FROM ").strip()
    return None


def _skill_hashes(skills_root: Path) -> Dict[str, str]:
    hashes: Dict[str, str] = {}
    for path in sorted(skills_root.glob("**/*")):
        if (
            path.is_file()
            and path.name != ".gitkeep"
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        ):
            hashes[str(path.relative_to(skills_root))] = _sha256(path)
    return hashes


class ExperimentRecord:
    """Own one fresh on-disk record directory and its event trace."""

    def __init__(
        self,
        record_root: Path,
        run_id: str,
        project_root: Path,
        skills_root: Path,
        configuration: Mapping[str, Any],
        question: str,
        question_id: Optional[str],
    ):
        self.run_id = run_id
        self.directory = record_root / run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.trace_sink = JsonlTraceSink(self.directory / "events.jsonl")
        self.started_at = datetime.now(timezone.utc)
        self._started_at_monotonic = perf_counter()
        metadata = {
            "record_schema_version": RECORD_SCHEMA_VERSION,
            "retrieval_provenance_schema_version": RETRIEVAL_PROVENANCE_SCHEMA_VERSION,
            "run_id": run_id,
            "started_at_utc": self.started_at.isoformat(),
            "model_artifact": _ollama_model_artifact(configuration.get("model")),
            "question_id": question_id,
            "question": question,
            "configuration": to_primitive(dict(configuration)),
            "git_commit": _git_commit(project_root),
            "git_source_worktree_dirty": _git_source_worktree_dirty(project_root),
            "runtime": {
                "python": sys.version,
                "platform": platform.platform(),
                "packages": _package_versions(),
            },
            "skill_sha256": _skill_hashes(skills_root),
            "index_metadata": self._read_index_metadata(project_root),
        }
        self._write_json("metadata.json", metadata)

    @staticmethod
    def _read_index_metadata(project_root: Path) -> Optional[Dict[str, Any]]:
        path = project_root / "data/koblex/indexes/metadata.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"error": "invalid index metadata", "path": str(path)}

    def finalize(self, outcome: Any) -> Path:
        completed_at = datetime.now(timezone.utc)
        state = to_primitive(outcome.state)
        stage_records = state.pop("retrieval_stage_records", [])
        stage_counts = Counter(
            record.get("candidate_stage", "unknown")
            for record in stage_records
            if isinstance(record, dict)
        )
        stage_file = None
        if stage_records:
            stage_file = "retrieval_stages.jsonl"
            with (self.directory / stage_file).open("w", encoding="utf-8") as handle:
                for record in stage_records:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                    handle.write("\n")
        result = {
            "record_schema_version": RECORD_SCHEMA_VERSION,
            "retrieval_provenance": {
                "schema_version": RETRIEVAL_PROVENANCE_SCHEMA_VERSION,
                "stage_file": stage_file,
                "stage_record_counts": dict(sorted(stage_counts.items())),
            },
            "run_id": self.run_id,
            "completed_at_utc": completed_at.isoformat(),
            "end_to_end_latency_ms": round((perf_counter() - self._started_at_monotonic) * 1000, 3),
            "status": outcome.status.value,
            "termination_reason": outcome.termination_reason.value if outcome.termination_reason else None,
            "abstention_reason": outcome.abstention_reason.value if outcome.abstention_reason else None,
            "answer": outcome.answer,
            "errors": list(outcome.errors),
            "state": state,
        }
        return self._write_json("result.json", result)

    def _write_json(self, filename: str, payload: Mapping[str, Any]) -> Path:
        path = self.directory / filename
        path.write_text(
            json.dumps(to_primitive(dict(payload)), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

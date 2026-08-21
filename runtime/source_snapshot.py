"""Capture and enforce a clean, immutable source snapshot for experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Sequence


EXCLUDED_SOURCE_PREFIXES = ("records/",)


class SourceSnapshotError(RuntimeError):
    """The repository cannot provide the frozen source required for a run."""


@dataclass(frozen=True)
class SourceSnapshot:
    git_commit: str
    git_tree: str
    source_manifest_sha256: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def _git(project_root: Path, arguments: Sequence[str]) -> str:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=str(project_root),
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SourceSnapshotError(
            "could not inspect Git source state: %s" % exc
        ) from exc


def _is_excluded_source_path(path: str) -> bool:
    normalized = path.strip().strip('"').replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in EXCLUDED_SOURCE_PREFIXES)


def source_dirty_paths_from_porcelain(status: str) -> List[str]:
    """Return dirty paths outside generated-record roots."""
    dirty: List[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        payload = line[3:]
        paths = payload.split(" -> ")
        if paths and all(_is_excluded_source_path(path) for path in paths):
            continue
        dirty.append(payload)
    return dirty


def _source_manifest_sha256(project_root: Path) -> str:
    """Hash Git index blob IDs and paths for every tracked non-record file."""
    index = _git(project_root, ["ls-files", "--stage"])
    digest = hashlib.sha256()
    for line in index.splitlines():
        if "\t" not in line:
            continue
        metadata, path = line.split("\t", 1)
        if _is_excluded_source_path(path):
            continue
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(metadata.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def capture_clean_source_snapshot(project_root: Path) -> SourceSnapshot:
    status = _git(
        project_root,
        ["-c", "core.quotepath=false", "status", "--porcelain=v1", "--untracked-files=all"],
    )
    dirty_paths = source_dirty_paths_from_porcelain(status)
    if dirty_paths:
        preview = ", ".join(dirty_paths[:5])
        if len(dirty_paths) > 5:
            preview += ", ... (%d paths total)" % len(dirty_paths)
        raise SourceSnapshotError(
            "experiment source worktree is dirty outside records/: %s" % preview
        )
    return SourceSnapshot(
        git_commit=_git(project_root, ["rev-parse", "HEAD"]).strip(),
        git_tree=_git(project_root, ["rev-parse", "HEAD^{tree}"]).strip(),
        source_manifest_sha256=_source_manifest_sha256(project_root),
    )


def assert_source_snapshot_unchanged(
    project_root: Path,
    expected: SourceSnapshot,
) -> SourceSnapshot:
    actual = capture_clean_source_snapshot(project_root)
    if actual != expected:
        raise SourceSnapshotError(
            "experiment source changed: expected %s, found %s"
            % (expected.to_dict(), actual.to_dict())
        )
    return actual

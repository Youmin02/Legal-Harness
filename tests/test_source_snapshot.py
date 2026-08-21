import subprocess
import tempfile
import unittest
from pathlib import Path

from runtime.source_snapshot import (
    SourceSnapshotError,
    assert_source_snapshot_unchanged,
    capture_clean_source_snapshot,
    source_dirty_paths_from_porcelain,
)


class SourceSnapshotTests(unittest.TestCase):
    def test_dirty_parser_ignores_records_but_not_source_paths(self):
        status = (
            "?? records/runs/run-1/result.json\n"
            " M runtime/local_ollama_executor.py\n"
            "R  records/old.json -> scripts/new.py\n"
        )

        self.assertEqual(
            source_dirty_paths_from_porcelain(status),
            [
                "runtime/local_ollama_executor.py",
                "records/old.json -> scripts/new.py",
            ],
        )

    def test_snapshot_allows_record_outputs_and_rejects_source_changes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=project,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=project,
                check=True,
            )
            source = project / "source.py"
            source.write_text("version = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "source.py"], cwd=project, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "fixture"],
                cwd=project,
                check=True,
            )
            record = project / "records" / "runs" / "run-1" / "result.json"
            record.parent.mkdir(parents=True)
            record.write_text("{}\n", encoding="utf-8")

            snapshot = capture_clean_source_snapshot(project)
            self.assertEqual(
                assert_source_snapshot_unchanged(project, snapshot),
                snapshot,
            )

            source.write_text("version = 2\n", encoding="utf-8")
            with self.assertRaises(SourceSnapshotError):
                assert_source_snapshot_unchanged(project, snapshot)


if __name__ == "__main__":
    unittest.main()

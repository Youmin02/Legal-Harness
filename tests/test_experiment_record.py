import json
import tempfile
import unittest
from pathlib import Path

from harness.contracts import (
    CandidateStageRecord,
    OutcomeStatus,
    TerminationReason,
)
from harness.run_state import RunState
from harness.runner import HarnessOutcome
from runtime.experiment_record import (
    ExperimentRecord,
    _source_worktree_dirty_from_porcelain,
)


class ExperimentRecordTests(unittest.TestCase):
    def test_source_dirty_ignores_only_records_paths(self):
        self.assertFalse(_source_worktree_dirty_from_porcelain("?? records/runs/run-1/result.json\n"))
        self.assertTrue(_source_worktree_dirty_from_porcelain("?? scripts/run_local_harness.py\n"))

    def test_writes_distinct_metadata_trace_and_result_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            skills = project / "skills"
            skills.mkdir(parents=True)
            (skills / "planner.md").write_text("planner", encoding="utf-8")

            record = ExperimentRecord(
                record_root=root / "records",
                run_id="run-1",
                project_root=project,
                skills_root=skills,
                configuration={"condition": "M", "seed": 7},
                question="질문",
                question_id="qa_19_1hop_28",
            )
            state = RunState(question="질문", normalized_question="질문", run_id="run-1")
            state.retrieval_stage_records = [
                CandidateStageRecord(
                    provision_id="P1",
                    retrieval_round=1,
                    candidate_stage="first_stage",
                    source_request_ids=["RQ1"],
                    target_evidence_item_ids=["E1"],
                    first_stage_rank=1,
                    first_stage_score=2.5,
                    selection_reason="request_top_k",
                )
            ]
            record.trace_sink.record("RUN_STARTED", state)
            result_path = record.finalize(
                HarnessOutcome(
                    status=OutcomeStatus.ABSTAIN,
                    state=state,
                    termination_reason=TerminationReason.MAX_RETRIEVAL_ROUNDS_REACHED,
                )
            )

            metadata = json.loads((record.directory / "metadata.json").read_text(encoding="utf-8"))
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["question_id"], "qa_19_1hop_28")
            self.assertIn("planner.md", metadata["skill_sha256"])
            self.assertIn("git_source_worktree_dirty", metadata)
            self.assertEqual(result["status"], "ABSTAIN")
            self.assertTrue((record.directory / "events.jsonl").is_file())
            self.assertEqual(result["record_schema_version"], "1.1")
            self.assertEqual(
                result["retrieval_provenance"]["stage_record_counts"],
                {"first_stage": 1},
            )
            self.assertNotIn("retrieval_stage_records", result["state"])
            self.assertTrue((record.directory / "retrieval_stages.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()

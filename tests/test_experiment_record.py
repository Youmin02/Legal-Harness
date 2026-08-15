import json
import tempfile
import unittest
from pathlib import Path

from harness.contracts import OutcomeStatus, TerminationReason
from harness.run_state import RunState
from harness.runner import HarnessOutcome
from runtime.experiment_record import ExperimentRecord


class ExperimentRecordTests(unittest.TestCase):
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
            self.assertEqual(result["status"], "ABSTAIN")
            self.assertTrue((record.directory / "events.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()

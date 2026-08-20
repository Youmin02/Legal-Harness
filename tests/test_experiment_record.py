import json
import tempfile
import unittest
from pathlib import Path

from harness.contracts import (
    AnswerMode,
    CandidateAnswerStatus,
    CandidateAnswerBasis,
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
            self.assertIsNone(result["answer_mode"])
            self.assertFalse(result["complete_answer"])
            self.assertTrue((record.directory / "events.jsonl").is_file())
            self.assertEqual(result["record_schema_version"], "1.2")
            self.assertIsNone(result["candidate_answer"])
            self.assertIsNone(result["candidate_answer_status"])
            self.assertEqual(
                result["retrieval_provenance"]["stage_record_counts"],
                {"first_stage": 1},
            )
            self.assertNotIn("retrieval_stage_records", result["state"])
            self.assertTrue((record.directory / "retrieval_stages.jsonl").is_file())

    def test_writes_optional_answer_scope_without_changing_status(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            skills = project / "skills"
            skills.mkdir(parents=True)
            record = ExperimentRecord(
                record_root=root / "records",
                run_id="run-answer-scope",
                project_root=project,
                skills_root=skills,
                configuration={},
                question="질문",
                question_id=None,
            )
            state = RunState(question="질문", normalized_question="질문", run_id="run-answer-scope")
            result_path = record.finalize(
                HarnessOutcome(
                    status=OutcomeStatus.ANSWER,
                    state=state,
                    answer="제한 답변",
                    answer_mode=AnswerMode.LIMITED,
                    complete_answer=False,
                    answered_target_ids=["T1"],
                    deferred_target_ids=["T2"],
                )
            )

            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "ANSWER")
            self.assertEqual(result["answer_mode"], "limited")
            self.assertEqual(result["answered_target_ids"], ["T1"])
            self.assertEqual(result["deferred_target_ids"], ["T2"])

    def test_writes_abstain_candidate_without_changing_public_status(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            skills = project / "skills"
            skills.mkdir(parents=True)
            record = ExperimentRecord(
                record_root=root / "records",
                run_id="run-candidate",
                project_root=project,
                skills_root=skills,
                configuration={},
                question="질문",
                question_id="q1",
            )
            state = RunState(question="질문", normalized_question="질문", run_id="run-candidate")
            result_path = record.finalize(
                HarnessOutcome(
                    status=OutcomeStatus.ABSTAIN,
                    state=state,
                    candidate_answer="벤치마크 후보 답변",
                    candidate_answer_status=CandidateAnswerStatus.GENERATED,
                    candidate_answer_basis=CandidateAnswerBasis.RETRIEVED_CANDIDATES,
                )
            )

            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "ABSTAIN")
            self.assertEqual(result["candidate_answer"], "벤치마크 후보 답변")
            self.assertEqual(result["candidate_answer_status"], "GENERATED")
            self.assertEqual(result["candidate_answer_basis"], "retrieved_candidates")


if __name__ == "__main__":
    unittest.main()

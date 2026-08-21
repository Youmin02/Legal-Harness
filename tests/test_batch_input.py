import unittest
from pathlib import Path
from runtime.source_snapshot import SourceSnapshot

from scripts.run_bm25_bge_pilot_batch import (
    build_run_command,
    format_benchmark_input,
)


class BatchInputTests(unittest.TestCase):
    def test_koblex_background_and_question_are_both_preserved(self):
        result = format_benchmark_input(
            {
                "background": "갑은 운송계약을 체결하였다.",
                "question": "언제까지 청구할 수 있는가?",
            }
        )

        self.assertEqual(
            result,
            "[배경 시나리오]\n갑은 운송계약을 체결하였다.\n\n"
            "[질문]\n언제까지 청구할 수 있는가?",
        )

    def test_empty_background_keeps_an_explicit_question_boundary(self):
        self.assertEqual(
            format_benchmark_input({"background": "", "question": "질문"}),
            "[질문]\n질문",
        )

    def test_custom_record_root_is_forwarded_to_child_command(self):
        record_root = Path("/tmp/dedicated-smoke-records")
        source_snapshot = SourceSnapshot(
            git_commit="a" * 40,
            git_tree="b" * 40,
            source_manifest_sha256="c" * 64,
        )
        command = build_run_command(
            Path("/tmp/python"),
            "[질문]\n질문",
            "qa_19_1hop_28",
            {
                "retriever": "bm25",
                "model": "test-model",
                "num_ctx": 32768,
                "total_retrieval_rounds": 3,
                "total_retrieval_requests": 9,
                "condition": "D4-test",
                "seed": 0,
                "ollama_endpoint": "http://127.0.0.1:11435/api/generate",
            },
            record_root,
            source_snapshot,
        )

        record_dir_index = command.index("--record-dir")
        self.assertEqual(command[record_dir_index + 1], str(record_root))
        endpoint_index = command.index("--ollama-endpoint")
        self.assertEqual(
            command[endpoint_index + 1],
            "http://127.0.0.1:11435/api/generate",
        )
        s1_limit_index = command.index("--s1-max-tokens")
        self.assertEqual(command[s1_limit_index + 1], "4096")
        retry_limit_index = command.index("--s1-truncation-retry-max-tokens")
        self.assertEqual(command[retry_limit_index + 1], "8192")
        commit_index = command.index("--expected-git-commit")
        self.assertEqual(command[commit_index + 1], "a" * 40)
        manifest_index = command.index("--expected-source-manifest-sha256")
        self.assertEqual(command[manifest_index + 1], "c" * 64)


if __name__ == "__main__":
    unittest.main()

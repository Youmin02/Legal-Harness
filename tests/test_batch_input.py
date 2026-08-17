import unittest

from scripts.run_bm25_bge_pilot_batch import format_benchmark_input


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


if __name__ == "__main__":
    unittest.main()

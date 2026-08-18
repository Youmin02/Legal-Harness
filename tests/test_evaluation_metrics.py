import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_dev_runs import (
    CorpusEntry,
    EvaluationError,
    GoldGroup,
    build_gold_groups,
    evaluate_batch,
    percentile_type7,
    precision_recall_f1,
    write_outputs,
)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GoldMappingTests(unittest.TestCase):
    def test_exact_duplicate_composite_image_and_punctuation_mapping(self):
        questions = {
            "q-exact": {
                "contexts": [
                    {"index": "법A 1조", "hierarchy": "법A 1조", "content": "정답 조문"}
                ]
            },
            "q-composite": {
                "contexts": [
                    {
                        "index": "법B 2조",
                        "hierarchy": "법B 2조",
                        "content": "제2조(의무)\n① 신고한다.\n② 위반하면 처벌한다.",
                    }
                ]
            },
            "q-image": {
                "contexts": [
                    {
                        "index": "법C 3조",
                        "hierarchy": "법C 3조 1항",
                        "content": "① 금액은 다음 표와 같다. 표내용",
                    }
                ]
            },
            "q-period": {
                "contexts": [
                    {"index": "법D 4조", "hierarchy": "법D 4조", "content": "끝 문장"}
                ]
            },
        }
        corpus = [
            CorpusEntry("A1", "법A 1조", "법A 1조", "정답 조문"),
            CorpusEntry("A1-duplicate", "법A 1조", "법A 1조", "정답 조문"),
            # Identical text in another statute must never become a gold alias.
            CorpusEntry("WRONG-LAW", "법X 1조", "법X 1조", "정답 조문"),
            CorpusEntry("B-title", "법B 2조", "법B 2조", "제2조(의무)"),
            CorpusEntry("B-1", "법B 2조", "법B 2조 1항", "① 신고한다."),
            CorpusEntry("B-2", "법B 2조", "법B 2조 2항", "② 위반하면 처벌한다."),
            CorpusEntry(
                "C-1",
                "법C 3조",
                "법C 3조 1항",
                '① 금액은 다음 표와 같다. <img src="x">표내용</img>',
            ),
            CorpusEntry("D-1", "법D 4조", "법D 4조", "끝 문장."),
        ]

        groups = build_gold_groups(questions, list(questions), corpus)

        self.assertEqual(
            groups["q-exact"][0].acceptable_provision_ids, ("A1", "A1-duplicate")
        )
        self.assertEqual(groups["q-exact"][0].match_type, "exact_duplicate")
        self.assertNotIn("WRONG-LAW", groups["q-exact"][0].acceptable_provision_ids)
        self.assertEqual(
            set(groups["q-composite"][0].acceptable_provision_ids),
            {"B-title", "B-1", "B-2"},
        )
        self.assertEqual(groups["q-composite"][0].match_type, "composite")
        self.assertEqual(groups["q-image"][0].acceptable_provision_ids, ("C-1",))
        self.assertEqual(groups["q-image"][0].match_type, "normalized_image_tag")
        self.assertEqual(groups["q-period"][0].acceptable_provision_ids, ("D-1",))
        self.assertEqual(groups["q-period"][0].match_type, "terminal_punctuation")

    def test_unmapped_gold_fails_instead_of_using_fuzzy_content(self):
        questions = {
            "q": {
                "contexts": [
                    {"index": "법A 1조", "hierarchy": "법A 1조", "content": "같은 문구"}
                ]
            }
        }
        corpus = [CorpusEntry("X", "법X 1조", "법X 1조", "같은 문구")]

        with self.assertRaises(EvaluationError):
            build_gold_groups(questions, ["q"], corpus)


class MetricFunctionTests(unittest.TestCase):
    def test_duplicate_predictions_do_not_inflate_gold_true_positives(self):
        groups = [
            GoldGroup("q", "G1", "법A", "법A", "h1", ("P1", "P1-copy"), "exact_duplicate"),
            GoldGroup("q", "G2", "법B", "법B", "h2", ("P2",), "exact_single"),
        ]

        metric = precision_recall_f1({"P1", "P1-copy", "DISTRACTOR"}, groups)

        self.assertEqual(metric["true_positive"], 1)
        self.assertAlmostEqual(metric["precision"], 1 / 3)
        self.assertAlmostEqual(metric["recall"], 1 / 2)
        self.assertFalse(metric["complete"])

    def test_empty_predictions_have_zero_precision_recall_and_f1(self):
        groups = [GoldGroup("q", "G1", "법A", "법A", "h", ("P1",), "exact_single")]

        metric = precision_recall_f1(set(), groups)

        self.assertEqual(metric["precision"], 0.0)
        self.assertEqual(metric["recall"], 0.0)
        self.assertEqual(metric["f1"], 0.0)

    def test_type7_percentile_is_deterministic(self):
        self.assertEqual(percentile_type7([100, 200, 300], 0.95), 290.0)
        self.assertEqual(percentile_type7([42], 0.95), 42.0)


class EvaluationFixture:
    def __init__(self, root, include_stages, include_labels=False):
        self.root = root
        self.batch = root / "records/batches/batch-1"
        self.runs = root / "records/runs"
        self.dataset = root / "qa.json"
        self.corpus = root / "corpus.jsonl"
        self.labels = root / "answer_labels.json" if include_labels else None
        dataset_rows = [
            {
                "id": "q1",
                "question": "질문1",
                "answer": "정답1",
                "background": "",
                "n_hops": 1,
                "contexts": [
                    {"index": "법A 1조", "hierarchy": "법A 1조", "content": "정답 A"}
                ],
            },
            {
                "id": "q2",
                "question": "질문2",
                "answer": "정답2",
                "background": "",
                "n_hops": 2,
                "contexts": [
                    {
                        "index": "법B 2조",
                        "hierarchy": "법B 2조",
                        "content": "제2조\n① 의무\n② 처벌",
                    }
                ],
            },
            {
                "id": "q3",
                "question": "질문3",
                "answer": "정답3",
                "background": "",
                "n_hops": 3,
                "contexts": [
                    {"index": "법C 3조", "hierarchy": "법C 3조", "content": "정답 C"}
                ],
            },
        ]
        write_json(self.dataset, dataset_rows)
        write_jsonl(
            self.corpus,
            [
                {
                    "provision_id": "P1",
                    "source_index": "법A 1조",
                    "statute_name": "법A 1조",
                    "provision_text": "정답 A",
                },
                {
                    "provision_id": "P1-copy",
                    "source_index": "법A 1조",
                    "statute_name": "법A 1조",
                    "provision_text": "정답 A",
                },
                {
                    "provision_id": "P2-title",
                    "source_index": "법B 2조",
                    "statute_name": "법B 2조",
                    "provision_text": "제2조",
                },
                {
                    "provision_id": "P2-duty",
                    "source_index": "법B 2조",
                    "statute_name": "법B 2조 1항",
                    "provision_text": "① 의무",
                },
                {
                    "provision_id": "P2-penalty",
                    "source_index": "법B 2조",
                    "statute_name": "법B 2조 2항",
                    "provision_text": "② 처벌",
                },
                {
                    "provision_id": "P3",
                    "source_index": "법C 3조",
                    "statute_name": "법C 3조",
                    "provision_text": "정답 C",
                },
            ],
        )
        manifest = {
            "manifest_schema_version": "1.0",
            "name": "fixture-batch",
            "source_dataset": {"path": str(self.dataset), "sha256": sha256(self.dataset)},
            "selection": {"entry_count": 3},
            "frozen_configuration": {"condition": "B0", "retriever": "bm25"},
            "entries": [
                {"ordinal": 1, "question_id": "q1", "n_hops": 1},
                {"ordinal": 2, "question_id": "q2", "n_hops": 2},
                {"ordinal": 3, "question_id": "q3", "n_hops": 3},
            ],
        }
        write_json(self.batch / "manifest.json", manifest)
        specs = [
            ("q1", "run-1", "ANSWER", "COMPLETED", "P1", 100.0),
            ("q2", "run-2", "ABSTAIN", "MAX_RETRIEVAL_ROUNDS_REACHED", None, 200.0),
            ("q3", "run-3", "EXECUTION_FAILURE", "INVALID_SKILL_OUTPUT", None, 300.0),
        ]
        summaries = []
        for ordinal, (question_id, run_id, status, reason, accepted, latency) in enumerate(
            specs, start=1
        ):
            run = self.runs / run_id
            candidates = []
            if question_id == "q1":
                candidates = [
                    {"provision_id": "P1"},
                    {"provision_id": "DISTRACTOR"},
                ]
            elif question_id == "q2":
                candidates = [{"provision_id": "P2-duty"}]
            state = {
                "accepted_provision_ids": [accepted] if accepted else [],
                "candidate_provisions": candidates,
                "query_history": [{"request_id": "RQ-%s" % question_id}],
                "retrieval_rounds_used": ordinal,
                "last_validated_event": "D4.CITATION_INTEGRITY_PASS"
                if status == "ANSWER"
                else "S2.ASSESS_COVERAGE",
                "action_trace": [
                    {
                        "event": "INITIAL_RETRIEVAL_VALIDATED",
                        "details": {"candidate_count": len(candidates)},
                    }
                ],
            }
            write_json(
                run / "metadata.json",
                {
                    "record_schema_version": "1.0",
                    "run_id": run_id,
                    "question_id": question_id,
                    "configuration": {"condition": "B0", "retriever": "bm25", "seed": 0},
                },
            )
            write_json(
                run / "result.json",
                {
                    "record_schema_version": "1.0",
                    "run_id": run_id,
                    "status": status,
                    "termination_reason": reason,
                    "abstention_reason": "INSUFFICIENT_CRITICAL_EVIDENCE"
                    if status == "ABSTAIN"
                    else None,
                    "end_to_end_latency_ms": latency,
                    "state": state,
                },
            )
            summaries.append(
                {
                    "ordinal": ordinal,
                    "question_id": question_id,
                    "n_hops": ordinal,
                    "record_directory": str(run),
                    "status": status,
                }
            )
        write_jsonl(self.batch / "summary.jsonl", summaries)
        if include_stages:
            stage_rows = {
                "run-1": [
                    {"stage": "first_stage", "rank": 1, "provision_id": "P1"},
                    {"stage": "fusion", "rank": 1, "provision_id": "P1"},
                    {"stage": "rerank", "rank": 1, "provision_id": "P1"},
                ],
                "run-2": [
                    {"stage": "first_stage", "rank": 100, "provision_id": "P2-duty"},
                    {"stage": "fusion", "rank": 100, "provision_id": "P2-duty"},
                    {"stage": "rerank", "rank": 11, "provision_id": "P2-duty"},
                ],
                "run-3": [
                    {"stage": "first_stage", "rank": 101, "provision_id": "P3"},
                    {"stage": "fusion", "rank": 1, "provision_id": "P3"},
                    {"stage": "rerank", "rank": 31, "provision_id": "P3"},
                ],
            }
            for run_id, rows in stage_rows.items():
                write_jsonl(self.runs / run_id / "retrieval_stages.jsonl", rows)
        if include_labels:
            write_json(self.labels, {"labels": {"q1": {"false_supported": True}}})


class EndToEndEvaluationTests(unittest.TestCase):
    def test_legacy_records_keep_stage_metrics_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = EvaluationFixture(Path(directory), include_stages=False)

            aggregate, rows, _ = evaluate_batch(
                fixture.batch, fixture.dataset, fixture.corpus
            )

            self.assertEqual(aggregate["outcomes"]["ANSWER"]["count"], 1)
            self.assertEqual(aggregate["outcomes"]["ABSTAIN"]["count"], 1)
            self.assertEqual(aggregate["outcomes"]["EXECUTION_FAILURE"]["count"], 1)
            self.assertAlmostEqual(aggregate["answers"]["supported_answer_yield"], 1 / 3)
            self.assertIsNone(aggregate["answers"]["false_supported_answer_count"])
            self.assertFalse(aggregate["retrieval"]["first_stage_at_100"]["available"])
            self.assertIsNone(
                aggregate["retrieval"]["first_stage_at_100"]["provision_recall_micro"]
            )
            self.assertIn("STAGE_PROVENANCE_UNAVAILABLE", aggregate["warnings"])
            self.assertTrue(all(not row["stage_provenance_available"] for row in rows))

    def test_stage_boundaries_labels_hops_and_efficiency(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = EvaluationFixture(
                Path(directory), include_stages=True, include_labels=True
            )

            aggregate, rows, metadata = evaluate_batch(
                fixture.batch,
                fixture.dataset,
                fixture.corpus,
                answer_labels_path=fixture.labels,
                require_stage_provenance=True,
            )

            self.assertAlmostEqual(
                aggregate["retrieval"]["first_stage_at_100"]["provision_recall_micro"],
                2 / 3,
            )
            self.assertAlmostEqual(
                aggregate["retrieval"]["rrf_at_100"]["complete_evidence_recall"],
                1.0,
            )
            self.assertAlmostEqual(
                aggregate["retrieval"]["bge_at_10"]["provision_recall_micro"],
                1 / 3,
            )
            self.assertAlmostEqual(
                aggregate["retrieval"]["bge_at_20"]["provision_recall_micro"],
                2 / 3,
            )
            self.assertAlmostEqual(
                aggregate["retrieval"]["bge_at_30"]["provision_recall_micro"],
                2 / 3,
            )
            self.assertEqual(aggregate["answers"]["false_supported_answer_count"], 1)
            self.assertEqual(aggregate["answers"]["false_supported_answer_rate"], 1.0)
            self.assertEqual(aggregate["citation_integrity"]["attempted"], 1)
            self.assertEqual(aggregate["citation_integrity"]["pass_rate"], 1.0)
            self.assertEqual(aggregate["by_hop"]["1"]["outcomes"]["ANSWER"]["count"], 1)
            self.assertEqual(aggregate["by_hop"]["2"]["outcomes"]["ABSTAIN"]["count"], 1)
            self.assertEqual(
                aggregate["by_hop"]["3"]["outcomes"]["EXECUTION_FAILURE"]["count"],
                1,
            )
            self.assertEqual(
                aggregate["efficiency"]["end_to_end_latency_ms"]["median"], 200.0
            )
            self.assertEqual(
                aggregate["efficiency"]["end_to_end_latency_ms"]["p95"], 290.0
            )
            self.assertEqual(metadata["validation"]["joined_results"], 3)
            self.assertEqual([row["ordinal"] for row in rows], [1, 2, 3])

    def test_writes_json_csv_markdown_and_metadata_in_ordinal_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = EvaluationFixture(root, include_stages=False)
            aggregate, rows, metadata = evaluate_batch(
                fixture.batch, fixture.dataset, fixture.corpus
            )
            output = root / "evaluation"

            write_outputs(output, aggregate, list(reversed(rows)), metadata)

            self.assertTrue((output / "aggregate.json").is_file())
            self.assertTrue((output / "per_question.csv").is_file())
            self.assertTrue((output / "summary.md").is_file())
            self.assertTrue((output / "metadata.json").is_file())
            with (output / "per_question.csv").open(encoding="utf-8") as handle:
                csv_rows = list(csv.DictReader(handle))
            self.assertEqual([row["question_id"] for row in csv_rows], ["q1", "q2", "q3"])
            self.assertEqual(csv_rows[0]["first_stage_recall_at_100"], "")
            self.assertIn("Retrieval stages", (output / "summary.md").read_text(encoding="utf-8"))
            with self.assertRaises(FileExistsError):
                write_outputs(output, aggregate, rows, metadata)

    def test_missing_manifest_result_is_an_input_error_not_an_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = EvaluationFixture(Path(directory), include_stages=False)
            summaries = [
                row
                for row in json.loads("[" + ",".join(
                    line for line in (fixture.batch / "summary.jsonl").read_text().splitlines()
                ) + "]")
                if row["question_id"] != "q3"
            ]
            write_jsonl(fixture.batch / "summary.jsonl", summaries)

            with self.assertRaises(EvaluationError):
                evaluate_batch(fixture.batch, fixture.dataset, fixture.corpus)


if __name__ == "__main__":
    unittest.main()

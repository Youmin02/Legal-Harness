# KoBLEX 226-item paper experiment protocol

This protocol treats the 226 KoBLEX QA items as a held-out benchmark.  Freeze all
prompts, skill files, model settings, retrieval indexes, policies, and budgets
before the final evaluation.  Choose those settings on a non-overlapping
development set; do not use the 226 test outcomes for iterative tuning.

## Unit of evaluation and strata

- Unit: one question (`question_id`) under one frozen condition and seed.
- Strata: 55 one-hop, 125 two-hop, and 46 three-hop questions.
- Primary stratum: two- and three-hop questions together (171 items), where
  iterative evidence acquisition is expected to matter.
- Report all 226 items as the main aggregate and each hop stratum separately.

## Frozen experimental conditions

Use the proposed harness as `M`.  The principal causal comparison should be
`C3`, which performs one initial retrieval and immediately answers/abstains,
while holding the same model, corpus, retriever, candidate count, and output
format fixed.  Add these controlled ablations:

| ID | Condition |
| --- | --- |
| M | Full evidence-aware iterative harness |
| C3 | One-shot retrieval plus immediate answer/abstention |
| C4 | M without gap-query planning |
| C5 | M without abstention / forced answer |
| A1 | M without BGE reranking |
| A2 | M forced to use the maximum retrieval budget |

Run retrieval experiments in this fixed order:

1. Complete all 226 questions for every selected condition with **BM25+BGE**.
   Freeze the source corpus, BM25 index, BGE reranker, model, skill hashes, and
   all harness budgets for this phase.
2. After the BM25+BGE phase is complete and its aggregate results are frozen,
   repeat the identical 226-question condition matrix with **KURE+BGE**.

Use the same question IDs, seeds, conditions, prompts, and budgets in both
phases. Treat retriever family as an explicit experimental factor; never
attribute a retrieval change to the harness policy.

## Frozen 20-item engineering pilot

The preflight pilot is fixed in
`data/koblex/manifests/bm25_bge_pilot_20_seed_20260815.json`. It comprises
5 one-hop, 11 two-hop, and 4 three-hop items, with `qa_92_1hop_149` as the
already completed anchor and 19 remaining items. The selection seed, source
dataset SHA-256, IDs, execution order, and all BM25+BGE settings are in that
manifest.

Run the remaining entries sequentially through
`scripts/run_bm25_bge_pilot_batch.py` in a tmux session. This pilot is an
engineering preflight: report it separately from the held-out 226-item paper
evaluation, preserve all outcomes including abstentions and failures, and do
not alter the frozen harness from its outcomes before the full benchmark.

## Metrics

Primary metrics:

- Provision-level precision, recall, and F1 against the gold provisions.
- Complete-evidence Recall@100, especially for two- and three-hop questions.
- Supported-answer yield: the fraction of all questions that receive a valid,
  citation-supported answer.

Safety and quality metrics:

- Abstention rate, unsafe-answer rate, citation integrity pass rate, and false
  coverage rate.
- Answer quality scored by a pre-specified rubric, reported both end-to-end
  (abstentions count as zero) and answer-only.

Efficiency metrics:

- Retrieval rounds and requests, candidate count, wall-clock latency (median,
  p95), and model-token usage when available.

## Repetitions and statistical analysis

Run three fixed seeds per question and condition.  Average repeated results
within each question first, then calculate condition differences with 10,000
question-level paired bootstrap samples and 95% confidence intervals.  Use
McNemar tests for paired binary outcomes and control multiple comparisons with
Holm adjustment.  Report effect sizes and confidence intervals, not p-values
alone.

## Run records and publication artifacts

Every CLI execution writes a new `records/runs/<uuid>/` directory.  Preserve
`metadata.json`, `events.jsonl`, and `result.json`; they bind a result to the
question, condition, seed, Git revision, model configuration, skill hashes, and
retrieval-index metadata.  Do not overwrite or edit completed runs.  Commit the
selected completed run directories, the frozen experiment manifest, and the
aggregation script used to create paper tables.

Before the final benchmark run, make and tag a clean Git commit.  After it
finishes, publish the tag/commit, the records, aggregate CSV/Parquet, and the
exact evaluation script.

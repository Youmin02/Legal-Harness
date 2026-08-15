# Experiment records

Each call to `scripts/run_local_harness.py` creates `records/runs/<run_id>/`.

- `metadata.json`: question, condition, seed, Git revision, package versions, skill SHA-256 values, and index metadata.
- `events.jsonl`: deterministic harness state-transition events.
- `result.json`: final outcome, answer or abstention, latency, errors, and frozen run state.

Keep these records for paper artifacts. Commit selected completed experiment directories with the corresponding configuration and aggregate results; do not overwrite an existing run directory.

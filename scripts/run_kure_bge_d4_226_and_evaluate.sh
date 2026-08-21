#!/usr/bin/env bash
set -u -o pipefail

KURE_PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KURE_BATCH_NAME="kure-bge-abstain-repair-d4-qwen38-q8-226-20260820"
KURE_MANIFEST="data/koblex/manifests/kure_bge_abstain_repair_d4_qwen38_q8_226_20260820.json"
KURE_EVALUATION_DIR="records/evaluations/kure-bge-abstain-repair-d4-qwen38-q8-226-20260820"

cd "$KURE_PROJECT_ROOT" || exit 2

if [ -e "$KURE_EVALUATION_DIR" ]; then
  echo "Refusing to overwrite existing evaluation directory: $KURE_EVALUATION_DIR" >&2
  exit 2
fi

.venv/bin/python scripts/run_bm25_bge_pilot_batch.py \
  --manifest "$KURE_MANIFEST" \
  --batch-name "$KURE_BATCH_NAME"
KURE_BATCH_STATUS=$?

KURE_BATCH_DIR="$(
  find records/batches -mindepth 1 -maxdepth 1 -type d \
    -name "$KURE_BATCH_NAME-*" -printf '%T@ %p\n' \
    | sort -nr \
    | head -n 1 \
    | cut -d' ' -f2-
)"

if [ -z "$KURE_BATCH_DIR" ]; then
  echo "Could not locate the completed KURE batch directory." >&2
  exit 2
fi

echo "Evaluating batch: $KURE_BATCH_DIR"
.venv/bin/python scripts/evaluate_dev_runs.py \
  --batch-dir "$KURE_BATCH_DIR" \
  --output-dir "$KURE_EVALUATION_DIR"
KURE_EVALUATION_STATUS=$?

echo "KURE batch exit status: $KURE_BATCH_STATUS"
echo "KURE evaluation exit status: $KURE_EVALUATION_STATUS"

if [ "$KURE_EVALUATION_STATUS" -ne 0 ]; then
  exit "$KURE_EVALUATION_STATUS"
fi
exit "$KURE_BATCH_STATUS"

#!/usr/bin/env python3
"""Evaluate a koblex_parser (ParSeR) baseline run using the official KoBLEX
metric definitions, ported verbatim from experiments/lf-eval/eval_pipeline.py
(fetched 2026-08-19 from raw.githubusercontent.com/daehuikim/KoBLEX/main):

  - normalize() / tokenize() / compute_token_f1(): identical regex, identical
    whitespace tokenization, identical Counter-intersection F1.
  - evaluate_retrieval(): identical set-based precision/recall/F1/EM against
    gold `hierarchy + content` context strings.

Official LF-Eval (GPT-4o G-Eval via deepeval) is NOT computed here -- it
requires an OpenAI API key and external API cost that must be pre-registered
before spending (see docs/HANDOFF_TO_CLAUDE_CODE_20260819.md section 7 and
docs/KOBLEX_PARSER_BASELINE_REPRODUCTION_NOTES.md). To run it later on this
baseline's own output, point the official
`experiments/lf-eval/eval_pipeline.py --eval_type legal_fidelity` at
final_results.jsonl (it already has the required `answer`/`provisions`
fields) after an explicit cost decision.

Adds latency statistics (per-stage and total generation time) which the
official evaluator does not report, per this project's own comparison needs.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Ported verbatim from experiments/lf-eval/eval_pipeline.py
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^가-힣a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    return text.split()


def compute_token_f1(prediction: str, ground_truth: str) -> Dict[str, float]:
    pred_tokens = tokenize(normalize(prediction))
    gt_tokens = tokenize(normalize(ground_truth))

    common = Counter(pred_tokens) & Counter(gt_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    precision = num_same / len(pred_tokens)
    recall = num_same / len(gt_tokens)
    f1 = 2 * precision * recall / (precision + recall)
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def evaluate_retrieval_one(pred: List[str], gold: List[str]) -> Dict[str, float]:
    P, G = set(pred), set(gold)
    tp = len(P & G)
    fp = len(P) - tp
    fn = len(G) - tp
    if not P and not G:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "em": 1.0}
    p = tp / len(P) if P else 0.0
    r = tp / len(G) if G else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    em = 1.0 if (fp + fn) == 0 else 0.0
    return {"precision": p, "recall": r, "f1": f1, "em": em}


def official_truncate_prediction(answer: str) -> str:
    """`temp_answer.split("<\\think>")[0][:800]` from the official evaluator.

    NOTE: `"<\\think>"` in the official Python source is `<` + TAB + `hink>`
    (an accidental `\\t` escape, not the intended `</think>` closing tag), so
    this split is a near no-op against real text; kept for exact numerical
    parity with the official evaluator rather than "fixed", since this is
    scoring code whose literal behavior is what produced the paper's numbers.
    """
    if not answer:
        return ""
    return answer.split("<\think>")[0][:800]  # noqa: W605 - intentional, see docstring


# ---------------------------------------------------------------------------
# Baseline-specific aggregation
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def mean(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 3) if values else None


def median(values: List[float]) -> Optional[float]:
    return round(statistics.median(values), 3) if values else None


def load_stage_traces(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.is_file():
        return {}
    return {rec["question_id"]: rec for rec in load_jsonl(path)}


def compute_retrieval_funnel(gold_contexts: List[str], trace: Optional[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """Per-question gold coverage at each ParSeR retrieval stage, unioned across
    all of that question's parametric-provision sub-queries:
      bm25_100  -> gold text appears anywhere in any sub-query's BM25 top-100
      rerank_10 -> gold text appears anywhere in any sub-query's rerank top-10
      selected  -> gold text is one of the provisions actually selected/used for QA
    This isolates whether a lost gold provision fell out at BM25 recall, at
    reranking, or was available but not chosen by the LLM selection step.
    """
    if not gold_contexts or trace is None:
        return None
    selections = trace.get("selections") or []
    bm25_union = set()
    rerank_union = set()
    selected_union = set()
    for sel in selections:
        bm25_union.update(sel.get("bm25_top_k_texts") or [])
        rerank_union.update(sel.get("reranked_top_l") or [])
        if sel.get("selected_text"):
            selected_union.add(sel["selected_text"])

    in_bm25 = [1.0 if g in bm25_union else 0.0 for g in gold_contexts]
    in_rerank = [1.0 if g in rerank_union else 0.0 for g in gold_contexts]
    in_selected = [1.0 if g in selected_union else 0.0 for g in gold_contexts]
    return {
        "bm25_100_recall": round(sum(in_bm25) / len(gold_contexts), 4),
        "rerank_10_recall": round(sum(in_rerank) / len(gold_contexts), 4),
        "selected_recall": round(sum(in_selected) / len(gold_contexts), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True, help="Dir with final_results.jsonl from run_koblex_parser_baseline.py")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    records = load_jsonl(args.batch_dir / "final_results.jsonl")
    stage_traces = load_stage_traces(args.batch_dir / "stage_trace.jsonl")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    per_question_rows = []
    token_f1s, token_ps, token_rs = [], [], []
    ret_ps, ret_rs, ret_f1s, ret_ems = [], [], [], []
    by_hop: Dict[int, Dict[str, List[float]]] = {}
    total_lat, s1_lat, s2_lat, s3_lat = [], [], [], []
    funnel_bm25, funnel_rerank, funnel_selected = [], [], []
    n_errors = 0

    for rec in records:
        error = rec.get("error") or ""
        n_hops = rec.get("n_hops")
        if error:
            n_errors += 1
            per_question_rows.append(
                {
                    "question_id": rec.get("question_id"),
                    "n_hops": n_hops,
                    "error": error,
                    "token_f1": "",
                    "retrieval_precision": "",
                    "retrieval_recall": "",
                    "retrieval_f1": "",
                    "retrieval_em": "",
                    "total_latency_seconds": "",
                    "funnel_bm25_100_recall": "",
                    "funnel_rerank_10_recall": "",
                    "funnel_selected_recall": "",
                }
            )
            continue

        prediction = official_truncate_prediction(rec.get("answer") or "")
        gold_answer = rec.get("gold_answer") or ""
        tf1 = compute_token_f1(prediction, gold_answer)
        token_f1s.append(tf1["f1"])
        token_ps.append(tf1["precision"])
        token_rs.append(tf1["recall"])

        pred_provisions = rec.get("provisions") or []
        gold_contexts = rec.get("gold_contexts") or []
        ret = evaluate_retrieval_one(pred_provisions, gold_contexts)
        ret_ps.append(ret["precision"])
        ret_rs.append(ret["recall"])
        ret_f1s.append(ret["f1"])
        ret_ems.append(ret["em"])

        total_latency = rec.get("total_latency_seconds")
        if total_latency is not None:
            total_lat.append(total_latency)
        if rec.get("stage1_latency_seconds") is not None:
            s1_lat.append(rec["stage1_latency_seconds"])
        if rec.get("stage2_latency_seconds") is not None:
            s2_lat.append(rec["stage2_latency_seconds"])
        if rec.get("stage3_latency_seconds") is not None:
            s3_lat.append(rec["stage3_latency_seconds"])

        funnel = compute_retrieval_funnel(gold_contexts, stage_traces.get(rec.get("question_id")))
        if funnel is not None:
            funnel_bm25.append(funnel["bm25_100_recall"])
            funnel_rerank.append(funnel["rerank_10_recall"])
            funnel_selected.append(funnel["selected_recall"])

        if isinstance(n_hops, int):
            bucket = by_hop.setdefault(n_hops, {"token_f1": [], "ret_f1": [], "ret_recall": [], "latency": []})
            bucket["token_f1"].append(tf1["f1"])
            bucket["ret_f1"].append(ret["f1"])
            bucket["ret_recall"].append(ret["recall"])
            if total_latency is not None:
                bucket["latency"].append(total_latency)

        per_question_rows.append(
            {
                "question_id": rec.get("question_id"),
                "n_hops": n_hops,
                "error": "",
                "token_f1": tf1["f1"],
                "retrieval_precision": round(ret["precision"], 4),
                "retrieval_recall": round(ret["recall"], 4),
                "retrieval_f1": round(ret["f1"], 4),
                "retrieval_em": ret["em"],
                "total_latency_seconds": total_latency,
                "funnel_bm25_100_recall": funnel["bm25_100_recall"] if funnel else "",
                "funnel_rerank_10_recall": funnel["rerank_10_recall"] if funnel else "",
                "funnel_selected_recall": funnel["selected_recall"] if funnel else "",
            }
        )

    aggregate = {
        "batch_dir": str(args.batch_dir),
        "n_items": len(records),
        "n_errors": n_errors,
        "n_scored": len(token_f1s),
        "answer_rate": round((len(records) - n_errors) / len(records), 4) if records else None,
        "token_f1": {"mean": mean(token_f1s), "precision_mean": mean(token_ps), "recall_mean": mean(token_rs)},
        "retrieval": {
            "precision_mean": mean(ret_ps),
            "recall_mean": mean(ret_rs),
            "f1_mean": mean(ret_f1s),
            "em_mean": mean(ret_ems),
        },
        "latency_seconds": {
            "total_mean": mean(total_lat),
            "total_median": median(total_lat),
            "stage1_parametric_provision_mean": mean(s1_lat),
            "stage2_selection_retrieval_mean": mean(s2_lat),
            "stage3_answer_generation_mean": mean(s3_lat),
            "wall_sum_total": round(sum(total_lat), 1) if total_lat else None,
        },
        "by_hop": {
            str(hop): {
                "n": len(bucket["token_f1"]),
                "token_f1_mean": mean(bucket["token_f1"]),
                "retrieval_f1_mean": mean(bucket["ret_f1"]),
                "retrieval_recall_mean": mean(bucket["ret_recall"]),
                "latency_mean": mean(bucket["latency"]),
            }
            for hop, bucket in sorted(by_hop.items())
        },
        "retrieval_funnel": {
            "description": (
                "Per-question gold-provision coverage at each ParSeR stage, unioned across all "
                "of that question's parametric-provision sub-queries. Isolates whether a missed "
                "gold provision fell out at BM25 recall, at reranking, or was retrieved but not "
                "the one the LLM selection step chose."
            ),
            "n_scored": len(funnel_bm25),
            "bm25_top100_recall_mean": mean(funnel_bm25),
            "rerank_top10_recall_mean": mean(funnel_rerank),
            "selected_recall_mean": mean(funnel_selected),
        },
        "legal_fidelity_lf_eval": "not computed (requires OpenAI API key + cost pre-registration; see module docstring)",
        "note": (
            "ANSWER rate is expected to be ~100%: ParSeR (the KoBLEX paper's own method) has no "
            "abstention mechanism and is instructed not to refuse. n_errors counts only pipeline "
            "execution failures (e.g. Ollama request errors), not model-declined answers."
        ),
    }

    (args.output_dir / "aggregate.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    csv_path = args.output_dir / "per_question.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "question_id",
                "n_hops",
                "error",
                "token_f1",
                "retrieval_precision",
                "retrieval_recall",
                "retrieval_f1",
                "retrieval_em",
                "total_latency_seconds",
                "funnel_bm25_100_recall",
                "funnel_rerank_10_recall",
                "funnel_selected_recall",
            ],
        )
        writer.writeheader()
        for row in per_question_rows:
            writer.writerow(row)

    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    print("\nWrote %s and %s" % (args.output_dir / "aggregate.json", csv_path))


if __name__ == "__main__":
    main()

"""ParSeR 3-stage pipeline orchestration for one QA item.

Stage 1: parametric provision generation (LLM, parametric knowledge only)
Stage 2: per-provision BM25 top-100 -> CrossEncoder rerank -> top-10 ->
         LLM selects 1 (from that provision's OWN top-10 -- see
         docs/KOBLEX_PARSER_BASELINE_REPRODUCTION_NOTES.md for the official
         `contexts_list[0][choice]` indexing bug this fixes)
Stage 3: grounded answer generation from the selected provisions

This module has no dependency on `skills/`, `harness/`, or
`runtime/local_ollama_executor.py`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from . import prompts
from .ollama_client import GenerationResult, OllamaGenerationError, generate
from .parsing import extract_first_list, parse_list_block
from .retrieval import Bm25Retriever, CrossEncoderReranker

BM25_TOP_K = 100
RERANK_TOP_L = 10
STAGE1_MAX_TOKENS = 4000
STAGE2_MAX_TOKENS = 2048
STAGE3_MAX_TOKENS = 4000
TEMPERATURE = 0.0


@dataclass
class SelectionTrace:
    parametric_provision: str
    bm25_candidate_count: int
    reranked_top_l: List[str]
    llm_raw_text: str
    llm_choice_index: int
    selected_text: str
    latency_seconds: float


@dataclass
class ItemResult:
    question_id: str
    background: str
    question: str
    parametric_provisions: List[str]
    selection_traces: List[SelectionTrace]
    selected_provisions: List[str]
    answer: str
    stage1_latency_seconds: float
    stage2_latency_seconds: float
    stage3_latency_seconds: float
    total_latency_seconds: float
    stage1_raw_text: str
    stage3_raw_text: str
    error: str = ""
    partial: Dict[str, Any] = field(default_factory=dict)


def generate_parametric_provisions(
    background: str, question: str, model: str, ollama_kwargs: Dict[str, Any]
) -> tuple:
    user_prompt = prompts.PARAMETRIC_INSTRUCTION_PROMPT.substitute(background=background, question=question)
    result: GenerationResult = generate(
        prompts.PARAMETRIC_SYSTEM_PROMPT,
        user_prompt,
        model,
        STAGE1_MAX_TOKENS,
        temperature=TEMPERATURE,
        **ollama_kwargs,
    )
    raw = result.text
    block = extract_first_list(raw)
    if block is None:
        return [], result
    subs = parse_list_block(block)
    if not isinstance(subs, list):
        subs = [subs]
    subs = [str(item) for item in subs if str(item).strip()]
    return subs, result


def select_provisions(
    background: str,
    question: str,
    parametric_provisions: List[str],
    bm25: Bm25Retriever,
    reranker: CrossEncoderReranker,
    model: str,
    ollama_kwargs: Dict[str, Any],
) -> List[SelectionTrace]:
    traces: List[SelectionTrace] = []
    for provision_query in parametric_provisions:
        query_text = provision_query if provision_query.strip() else question
        candidate_indices = bm25.top_k(query_text, k=BM25_TOP_K)
        candidate_texts = [bm25.records[i].text for i in candidate_indices]
        ranked_texts = reranker.rerank(query_text, candidate_texts)
        top_l = ranked_texts[:RERANK_TOP_L]
        cand_lines = "\n".join("%d: %s" % (i, text) for i, text in enumerate(top_l))
        user_prompt = prompts.SELECTION_INSTRUCTION_PROMPT.substitute(
            background=background, question=question, candidates=cand_lines
        )
        result = generate(
            prompts.SELECTION_SYSTEM_PROMPT,
            user_prompt,
            model,
            STAGE2_MAX_TOKENS,
            temperature=TEMPERATURE,
            **ollama_kwargs,
        )
        ans = result.text.split("Answer:")[-1].split("</think>")[0].strip()
        choice = int(ans) if ans.isdigit() and 0 <= int(ans) <= 9 else 0
        choice = min(choice, len(top_l) - 1) if top_l else 0
        selected_text = top_l[choice] if top_l else ""
        traces.append(
            SelectionTrace(
                parametric_provision=provision_query,
                bm25_candidate_count=len(candidate_indices),
                reranked_top_l=top_l,
                llm_raw_text=result.text,
                llm_choice_index=choice,
                selected_text=selected_text,
                latency_seconds=result.latency_seconds,
            )
        )
    return traces


def answer_question(
    background: str,
    question: str,
    selected_texts: List[str],
    model: str,
    ollama_kwargs: Dict[str, Any],
) -> tuple:
    combined_question = background + question
    context_str = "\n".join(selected_texts)
    user_prompt = prompts.QA_INSTRUCTION_PROMPT.substitute(question=combined_question, context_str=context_str)
    result = generate(
        prompts.QA_SYSTEM_PROMPT,
        user_prompt,
        model,
        STAGE3_MAX_TOKENS,
        temperature=TEMPERATURE,
        **ollama_kwargs,
    )
    answer = result.text.split("Answer:")[-1].split("</think>")[0].strip()
    return answer, result


def run_item(
    question_id: str,
    background: str,
    question: str,
    bm25: Bm25Retriever,
    reranker: CrossEncoderReranker,
    model: str,
    ollama_kwargs: Dict[str, Any],
) -> ItemResult:
    total_start = time.monotonic()

    stage1_start = time.monotonic()
    parametric_provisions, stage1_result = generate_parametric_provisions(
        background, question, model, ollama_kwargs
    )
    stage1_latency = time.monotonic() - stage1_start

    if not parametric_provisions:
        total_latency = time.monotonic() - total_start
        return ItemResult(
            question_id=question_id,
            background=background,
            question=question,
            parametric_provisions=[],
            selection_traces=[],
            selected_provisions=[],
            answer="",
            stage1_latency_seconds=stage1_latency,
            stage2_latency_seconds=0.0,
            stage3_latency_seconds=0.0,
            total_latency_seconds=total_latency,
            stage1_raw_text=stage1_result.text,
            stage3_raw_text="",
            error="STAGE1_EMPTY_PARAMETRIC_PROVISIONS",
        )

    stage2_start = time.monotonic()
    selection_traces = select_provisions(
        background, question, parametric_provisions, bm25, reranker, model, ollama_kwargs
    )
    stage2_latency = time.monotonic() - stage2_start
    selected_provisions = [trace.selected_text for trace in selection_traces if trace.selected_text]

    stage3_start = time.monotonic()
    answer, stage3_result = answer_question(background, question, selected_provisions, model, ollama_kwargs)
    stage3_latency = time.monotonic() - stage3_start

    total_latency = time.monotonic() - total_start
    return ItemResult(
        question_id=question_id,
        background=background,
        question=question,
        parametric_provisions=parametric_provisions,
        selection_traces=selection_traces,
        selected_provisions=selected_provisions,
        answer=answer,
        stage1_latency_seconds=stage1_latency,
        stage2_latency_seconds=stage2_latency,
        stage3_latency_seconds=stage3_latency,
        total_latency_seconds=total_latency,
        stage1_raw_text=stage1_result.text,
        stage3_raw_text=stage3_result.text,
    )

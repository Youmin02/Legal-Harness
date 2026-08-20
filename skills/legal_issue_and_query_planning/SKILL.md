---
name: legal-evidence-planning
description: Structure Korean statutory multi-hop questions into legal issues, required evidence items, and targeted provision-retrieval requests. Use for S1 INITIAL_PLAN before retrieval or S1 GAP_QUERY_PLAN after a provision-coverage assessment identifies missing or conflicting evidence; do not use it to retrieve statutes, assess coverage, choose the next harness action, or draft the answer.
---

# Legal Evidence Planning

Produce one contract-valid JSON object for S1. Treat the surrounding harness as the sole owner of skill order, retry, budget, and stop decisions.

## Select the mode

- Use `INITIAL_PLAN` for a normalized question that has not yet been decomposed.
- Use `GAP_QUERY_PLAN` only with S2 assessments, missing/conflicting evidence, query history, a remaining request budget, and a positive `next_retrieval_round`.

Read [references/contract.md](references/contract.md) before executing. Conform to [references/input.schema.json](references/input.schema.json) and [references/output.schema.json](references/output.schema.json).

## Execute

1. Copy `run_id` from input. Use `RQ<positive index>` request IDs in `INITIAL_PLAN`; in `GAP_QUERY_PLAN`, use the supplied `next_retrieval_round` in `GRQ-R<positive round>-<positive index>`, never a mode name. The harness canonicalizes these transport identifiers, but the target evidence and query text remain your responsibility.
2. Preserve the question's meaning. Do not perform a legal rewrite in place of deterministic input normalization.
3. Extract `answer_targets[]` from only the outputs the question asks for. Each `question_anchor` must be a literal substring of the question; do not add a target merely because it would be useful in a complete legal opinion. When `constraints.answer_target_contract` is `required`, return at least one target and the linked evidence fields below.
4. Decompose by legal issue and required evidence, not by a hard statute-domain route and not by a fixed hop count. For each new evidence item, link `answer_target_ids`, state why it is needed in `necessity_reason`, set `scope_source`, and express the minimum atomic `completion_requirements[]`.
5. Mark an evidence item `critical: true` only when the core conclusion cannot be justified without it. Do not split details that one governing provision can ordinarily establish into separate critical items. Create a separate critical item only for an independently necessary legal conclusion. A `supporting_context` item is never critical. Procedure, submission documents, venue, and deadline are critical only when the question asks for them or they change the requested conclusion.
6. In `INITIAL_PLAN`, create at least one retrieval request for every critical evidence item. Use only the allowed channels and treat statute/article hints as hypotheses, never as found evidence. Put 2-8 concise, particle-free Korean legal nouns or phrases in `query_terms`. Keep `query_text` focused on the conduct, legal effect, exception, procedure, or penalty being sought. Put a statute name in `statute_hints` only when the question strongly supports that hypothesis.
   When supplied, use `first_stage_query_text` for high-recall BM25 wording and `rerank_query_text` for the answer target plus atomic requirement; otherwise `query_text` remains the fallback for both.
7. In `GAP_QUERY_PLAN`, target only unresolved evidence items and preserve their input `answer_target_ids` scope; do not turn a background or unrelated answer target into a gap query. Avoid any normalized query already present in `query_history`; respect `remaining_request_budget`. Change the lexical angle: prefer the missing legal effect, actor, condition, exception, penalty, or a reliable statute-name hypothesis rather than paraphrasing the prior query.
8. Return JSON only. On an invalid or incomplete input, return the error envelope defined by the output schema.

## Preserve the control boundary

- Never retrieve or quote a statute as if it had been found.
- Never return `covered`, `accepted_provision_ids`, `RETRIEVE_GAP`, `GENERATE`, or `ABSTAIN`.
- Never call S2, S3, or a retrieval tool directly.
- Let the retrieval tool own Top-k, index, fusion, and reranker settings.

Validate a result with:

```bash
python3 scripts/validate_output.py output.json --input input.json
```

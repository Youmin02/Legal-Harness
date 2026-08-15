---
name: legal-evidence-planning
description: Structure Korean statutory multi-hop questions into legal issues, required evidence items, and targeted provision-retrieval requests. Use for S1 INITIAL_PLAN before retrieval or S1 GAP_QUERY_PLAN after a provision-coverage assessment identifies missing or conflicting evidence; do not use it to retrieve statutes, assess coverage, choose the next harness action, or draft the answer.
---

# Legal Evidence Planning

Produce one contract-valid JSON object for S1. Treat the surrounding harness as the sole owner of skill order, retry, budget, and stop decisions.

## Select the mode

- Use `INITIAL_PLAN` for a normalized question that has not yet been decomposed.
- Use `GAP_QUERY_PLAN` only with S2 assessments, missing/conflicting evidence, query history, and a remaining request budget.

Read [references/contract.md](references/contract.md) before executing. Conform to [references/input.schema.json](references/input.schema.json) and [references/output.schema.json](references/output.schema.json).

## Execute

1. Preserve the question's meaning. Do not perform a legal rewrite in place of deterministic input normalization.
2. Decompose by legal issue and required evidence, not by a hard statute-domain route and not by a fixed hop count.
3. Mark an evidence item `critical: true` only when the core conclusion cannot be justified without it.
4. In `INITIAL_PLAN`, create at least one retrieval request for every critical evidence item. Use only the allowed channels and treat statute/article hints as hypotheses, never as found evidence.
5. In `GAP_QUERY_PLAN`, target only unresolved evidence items. Avoid any normalized query already present in `query_history`; respect `remaining_request_budget`.
6. Return JSON only. On an invalid or incomplete input, return the error envelope defined by the output schema.

## Preserve the control boundary

- Never retrieve or quote a statute as if it had been found.
- Never return `covered`, `accepted_provision_ids`, `RETRIEVE_GAP`, `GENERATE`, or `ABSTAIN`.
- Never call S2, S3, or a retrieval tool directly.
- Let the retrieval tool own Top-k, index, fusion, and reranker settings.

Validate a result with:

```bash
python3 scripts/validate_output.py output.json --input input.json
```

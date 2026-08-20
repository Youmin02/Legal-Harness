# S1 contract

## Modes

### `INITIAL_PLAN`

Input the normalized question and harness constraints. When `constraints.answer_target_contract` is `required`, `answer_targets[]` and the answer-target evidence fields below are mandatory for that new execution; omitted constraints preserve legacy parsing. Output:

- `answer_targets[]`: question-scoped answerable sub-results, each anchored in the question text.
- `legal_issues[]`: atomic legal decision questions.
- `required_evidence_items[]`: answer-target-linked evidence obligations with a scope source, necessity reason, and atomic completion requirements.
- `retrieval_requests[]`: structured, issue/evidence-linked search requests.

Use these query channels only:

- `provision_style`: a non-quoted sentence shaped like the rule being sought.
- `sparse_keywords`: concise noun-centered legal terms.
- `statute_aware`: an issue phrase combined with tentative statute or article hints.

Do not claim that a statute hint exists or applies. The retrieval tool must verify it.

`query_text` remains the backward-compatible fallback. When separate retrieval text is useful, `first_stage_query_text` carries broad BM25 recall wording and `rerank_query_text` carries the answer target plus atomic completion requirement for BGE precision.

### `GAP_QUERY_PLAN`

Input prior issues/evidence, optional original `answer_targets[]`, S2 assessments, missing items, conflicts, query history, seen provision IDs, the remaining request budget, and `next_retrieval_round` (a positive integer). Preserve each unresolved item's linked answer-target scope when forming a gap query. Output:

- `target_evidence_item_ids[]`: the unresolved items actually targeted in this call.
- `gap_retrieval_requests[]`: new queries with a `gap_reason` and the prior assessment status.

Do not simply repeat the original question. Convert each unresolved completion criterion or conflict into a focused search target. If the budget cannot cover all gaps, prioritize critical items, then conflicts blocking a critical item.

## Evidence types

Use one of: `definition`, `element`, `rule`, `exception`, `procedure`, `remedy`, `limitation`, `relationship`, `other`.

## ID and reference rules

- Use `I1`, `I2`, ... for issues.
- Use `E1`, `E2`, ... for evidence items.
- Use `T1`, `T2`, ... for answer targets and `E1-R1`, `E1-R2`, ... for atomic completion requirements.
- Use `RQ1`, `RQ2`, ... for initial requests. For gap requests, use `GRQ-R<round>-<index>` with positive decimal values, such as `GRQ-R1-1` and `GRQ-R2-3`.
- Keep IDs unique in the result.
- Every evidence item must reference an existing issue.
- Every critical evidence item must reference at least one answer target, and every answer target needs critical evidence.
- `supporting_context` evidence must be non-critical. Use `explicit_question` or `outcome_changing_condition` for critical evidence only when its omission would prevent the requested answer.
- Every request must reference a valid issue/evidence pair.
- Keep `query_text` unique after Unicode NFKC normalization, whitespace collapse, and lowercasing.

## Error envelope

Return `status: "error"` with:

```json
- `run_id` and request IDs are transport fields: copy the input `run_id`; use the mode-appropriate ID prefix. The harness may canonicalize their values before semantic validation.
{
  "schema_version": "1.0",
  "skill_id": "S1",
  "mode": "INITIAL_PLAN",
  "status": "error",
  "run_id": "run-001",
  "error": {
    "code": "INVALID_INPUT",
    "message": "Required input is missing.",
    "details": []
  }
}
```

Use error codes `INVALID_INPUT`, `BUDGET_EXHAUSTED`, or `CONTRACT_UNSATISFIABLE`. Do not convert an S1 error into a policy action.

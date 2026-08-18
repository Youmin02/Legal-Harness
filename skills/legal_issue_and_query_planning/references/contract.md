# S1 contract

## Modes

### `INITIAL_PLAN`

Input the normalized question and harness constraints. Output:

- `legal_issues[]`: atomic legal decision questions.
- `required_evidence_items[]`: evidence obligations needed to resolve each issue.
- `retrieval_requests[]`: structured, issue/evidence-linked search requests.

Use these query channels only:

- `provision_style`: a non-quoted sentence shaped like the rule being sought.
- `sparse_keywords`: concise noun-centered legal terms.
- `statute_aware`: an issue phrase combined with tentative statute or article hints.

Do not claim that a statute hint exists or applies. The retrieval tool must verify it.

### `GAP_QUERY_PLAN`

Input prior issues/evidence, S2 assessments, missing items, conflicts, query history, seen provision IDs, and the remaining request budget. Output:

- `target_evidence_item_ids[]`: the unresolved items actually targeted in this call.
- `gap_retrieval_requests[]`: new queries with a `gap_reason` and the prior assessment status.

Do not simply repeat the original question. Convert each unresolved completion criterion or conflict into a focused search target. If the budget cannot cover all gaps, prioritize critical items, then conflicts blocking a critical item.

## Evidence types

Use one of: `definition`, `element`, `rule`, `exception`, `procedure`, `remedy`, `limitation`, `relationship`, `other`.

## ID and reference rules

- Use `I1`, `I2`, ... for issues.
- Use `E1`, `E2`, ... for evidence items.
- Use `RQ1`, `RQ2`, ... for initial requests. For gap requests, use `GRQ-R<round>-<index>` with positive decimal values, such as `GRQ-R1-1` and `GRQ-R2-3`.
- Keep IDs unique in the result.
- Every evidence item must reference an existing issue.
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

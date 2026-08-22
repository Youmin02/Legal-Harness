---
name: grounded-legal-answer-generation
description: Generate a Korean statutory answer with claim-level citations from the provision set authorized by the harness. Use for publishable S3 GENERATE_ANSWER or non-publishable GENERATE_BENCHMARK_CANDIDATE; do not use it to retrieve evidence, assess coverage, choose abstention, or validate citations.
---

# Grounded Legal Answer Generation

Return one compact S3 JSON object. Read
[references/contract.md](references/contract.md) and follow the harness-owned
authorization and answer scope.

## Generate

1. Make the first claim directly answer the requested Korean legal output; do not
   begin with an issue restatement or statute summary. Normally use one
   conclusion-bearing claim per answered target. Add another only when a distinct
   exception or condition cannot be combined accurately.
2. Use only the provisions supplied for the current mode. Every substantive claim
   must name an answered target and have a citation.
3. Combine a rule and its direct application when accurate. Do not add full
   provision quotations, background lessons, or repeated conclusions.
4. Put a conclusion-changing condition inside the relevant conditional claim.
   Keep material premises and scope limits in `assumptions` or `limitations`;
   an audit note cannot repair an unconditional claim. Do not present a missing
   fact as established, add generic disclaimers, or repeat a claim as a note.
5. Respect `max_answer_chars` and return JSON only.

For `GENERATE_ANSWER`, cite only `accepted_provisions`. For
`GENERATE_BENCHMARK_CANDIDATE`, cite only `candidate_provisions`, answer all
supplied targets, and keep the result non-publishable; the public policy remains
`ABSTAIN`. With `question_only`, return a concise diagnostic answer with empty
claims and citations.

## Boundary

Do not retrieve, reassess coverage, choose a policy action, or claim that citation
validation passed. Return a structured error when authorization or evidence
preconditions fail.

Validate a result with:

```bash
python3 scripts/validate_output.py output.json --input input.json
```

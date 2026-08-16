---
name: grounded-legal-answer-generation
description: Generate a Korean statutory answer and claim-level provision citations using only harness-accepted provision texts. Use for S3 GENERATE_ANSWER after the provision-coverage policy authorizes a fully supported or explicitly conditional answer; do not use it to retrieve evidence, assess coverage, choose abstention, or validate citations against the corpus.
---

# Grounded Legal Answer Generation

Produce one contract-valid S3 JSON object using only the accepted provisions supplied by the harness.

Read [references/contract.md](references/contract.md) before executing. Conform to [references/input.schema.json](references/input.schema.json) and [references/output.schema.json](references/output.schema.json).

## Check the preconditions

1. Require a harness authorization with action `GENERATE`.
2. Require every critical evidence item to be `covered`, or `partially_covered` with an accepted supporting provision when the policy authorizes an explicitly conditional answer. Never proceed with an `uncovered` or `conflicting` critical item.
3. Require at least one accepted provision with full text.
4. Return a structured error instead of answering when a precondition fails. Do not choose `ABSTAIN`; that remains a harness action.

## Generate

1. Answer in Korean unless the input constraint explicitly selects another language.
2. Separate statutory rules from conditional application to the facts. Do not invent missing facts, case law, administrative guidance, or provision text.
3. Use only `accepted_provisions[]`. Copy every `quoted_text` exactly from its accepted provision.
4. Represent every substantive legal claim in `claims[]`. Make each claim text an exact substring of `answer`.
5. Attach at least one citation to every claim that requires statutory support. Put each citation marker such as `[CT1]` in the answer.
6. State assumptions and material limitations explicitly.
7. For every partially covered critical item, state the unresolved condition in `limitations[]` and phrase the corresponding claim with `applicability: "conditional"`. Do not turn the missing factual premise into a fact.
8. Return JSON only.

## Preserve the control boundary

- Never retrieve, call S1/S2, or inspect a corpus directly.
- Never cite a provision outside the accepted set.
- Never return `RETRIEVE_GAP`, `GENERATE`, `ABSTAIN`, or `PASS` as a policy/validation result.
- Let the deterministic citation-integrity tool verify provision existence, snapshot text, accepted-set membership, and claim-citation linkage after this skill returns.

Validate a result with:

```bash
python3 scripts/validate_output.py output.json --input input.json
```

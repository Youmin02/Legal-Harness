---
name: grounded-legal-answer-generation
description: Generate a Korean statutory answer and claim-level provision citations using only harness-accepted provision texts. Use for S3 GENERATE_ANSWER after the provision-coverage policy authorizes a full, conditional, or evidence-scoped limited answer; do not use it to retrieve evidence, assess coverage, choose abstention, or validate citations against the corpus.
---

# Grounded Legal Answer Generation

Produce one contract-valid S3 JSON object using only the accepted provisions supplied by the harness.

Read [references/contract.md](references/contract.md) before executing. Conform to [references/input.schema.json](references/input.schema.json) and [references/output.schema.json](references/output.schema.json).

## Check the preconditions

1. Require a harness authorization with action `GENERATE`.
2. Read the harness-owned `answer_mode`, `answered_target_ids`, and `deferred_target_ids`. In `full` or `conditional` mode, answer every authorized target. In `limited` mode, make substantive claims only for `answered_target_ids`, include those target IDs in every claim, and explicitly defer the others without turning the deferral into a legal conclusion.
3. Require every critical evidence item to be `covered`, or `partially_covered` with an accepted supporting provision when the policy authorizes an explicitly conditional answer. Never proceed with an `uncovered` or `conflicting` critical item unless it belongs solely to a deferred limited-answer target.
4. Require at least one accepted provision with full text.
5. Return a structured error instead of answering when a precondition fails. Do not choose `ABSTAIN`; that remains a harness action.

## Generate

1. Answer in Korean unless the input constraint explicitly selects another language. Put the legal conclusion first and keep the public `answer` to 1--3 short sentences, never more than 800 characters and preferably about 300--500 characters. Include only the outcome-changing condition and the minimum statutory basis needed to understand the conclusion.
2. Separate statutory rules from conditional application to the facts. Do not invent missing facts, case law, administrative guidance, or provision text.
3. Use only `accepted_provisions[]`. Preserve each selected claim-to-provision connection and its support description; the harness replaces `quoted_text` with the immutable full provision snapshot.
4. Put only substantive legal claims in `claims[]`, set `citation_required: true`, attach at least one citation, and identify its `answer_target_ids`. The harness preserves every audit claim and citation but deterministically publishes at most three prioritized claims with harness-owned IDs, markers, full provision text, and final serialization.
5. Keep uncited factual premises and limitation explanations out of `claims[]`; preserve them in `assumptions[]` and `limitations[]`. Do not append every audit note to the public answer.
6. Preserve all assumptions and material limitations without presenting them as established facts. Repeat only an outcome-changing condition briefly in the public answer body.
7. For every partially covered critical item, state the unresolved condition in `limitations[]` and phrase the corresponding claim with `applicability: "conditional"`. Do not turn the missing factual premise into a fact.
8. Return JSON only.

For `GENERATE_BENCHMARK_CANDIDATE`, use only `candidate_provisions[]` and answer
all supplied targets as a non-publishable benchmark diagnostic. The public
policy remains `ABSTAIN`; do not describe the candidate as authorized, supported,
or publishable.

When `candidate_answer_basis` is `question_only`, no retrieved source exists.
Return the diagnostic answer with empty `claims[]` and `claim_citations[]`; do
not invent citations or change the policy status.

## Preserve the control boundary

- Never retrieve, call S1/S2, or inspect a corpus directly.
- Never cite a provision outside the accepted set.
- Never return `RETRIEVE_GAP`, `GENERATE`, `ABSTAIN`, or `PASS` as a policy/validation result.
- Let the deterministic citation-integrity tool verify provision existence, snapshot text, accepted-set membership, and claim-citation linkage after this skill returns.

Validate a result with:

```bash
python3 scripts/validate_output.py output.json --input input.json
```

---
name: provision-coverage-assessment
description: Assess whether retrieved Korean statutory provisions satisfy each required legal evidence item and return evidence links plus covered, partially_covered, uncovered, or conflicting assessments. Use for S2 ASSESS_COVERAGE after initial or gap provision retrieval; do not use it to retrieve more evidence, select RETRIEVE_GAP/GENERATE/ABSTAIN, derive accepted provision IDs, or generate the answer.
---

# Provision Coverage Assessment

Produce one contract-valid S2 JSON object from the supplied issues, evidence obligations, and candidate provision texts. Treat relevance and evidence sufficiency as different questions.

Read [references/contract.md](references/contract.md) before executing. Conform to [references/input.schema.json](references/input.schema.json) and [references/output.schema.json](references/output.schema.json).

## Execute

1. Assess every `required_evidence_item` exactly once against only the supplied `candidate_provisions`.
2. Create evidence links only for operational support, partial support, or a real unresolved conflict. Use only the short candidate IDs supplied as `candidate_provisions[].provision_id` (for example `C001`); never recreate a source statute ID.
3. Set every evidence link's `quoted_text` to the literal string `[FULL_TEXT]`. The harness deterministically replaces this token with the complete immutable candidate text, preventing paraphrased or mistyped quotations.
4. Construct `evidence_links` first. For each assessment, copy `linked_provision_ids` from that evidence item's links exactly; use `[]` only for `uncovered`.
5. Apply the four status definitions in the contract. Base the judgment on each item's `completion_criteria`, not retrieval score or topical similarity alone. Treat the completion criteria as closed: do not invent an additional element that the question or criterion did not require. If a provision states a conditional rule but the question does not establish the condition, use `partially_covered` and identify the condition precisely so S3 can state it rather than fabricate the fact.
6. Emit one `missing_evidence_item` for every non-covered assessment. Emit a conflict object only for `conflicting` assessments.
7. Explain what is satisfied and what remains missing; do not conceal uncertainty behind a high-level relevance statement. Because later candidate sets only grow, preserve a prior `covered` or `partially_covered` finding when its linked provision is still supplied, unless a newly supplied provision creates a real unresolved conflict.
8. Return JSON only. On invalid input, return the error envelope.

## Preserve the control boundary

- Never call retrieval, S1, or S3.
- Never return a policy action or `accepted_provision_ids`.
- Never treat an absent candidate as proof that no governing provision exists.
- Never perform answer generation or user-facing legal advice.
- Treat `conflicting` as an unresolved applicability/scope/exception conflict, not mere coexistence of multiple provisions.

Validate a result with:

```bash
python3 scripts/validate_output.py output.json --input input.json
```

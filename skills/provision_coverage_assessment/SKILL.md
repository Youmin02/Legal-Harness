---
name: provision-coverage-assessment
description: Assess whether retrieved Korean statutory provisions satisfy each required legal evidence item and return evidence links plus covered, partially_covered, uncovered, or conflicting assessments. Use for S2 ASSESS_COVERAGE after initial or gap provision retrieval; do not use it to retrieve more evidence, select RETRIEVE_GAP/GENERATE/ABSTAIN, derive accepted provision IDs, or generate the answer.
---

# Provision Coverage Assessment

Produce one contract-valid S2 JSON object from the supplied issues, evidence obligations, and candidate provision texts. Treat relevance and evidence sufficiency as different questions.

Read [references/contract.md](references/contract.md) before executing. Conform to [references/input.schema.json](references/input.schema.json) and [references/output.schema.json](references/output.schema.json).

## Execute

1. Assess every `required_evidence_item` exactly once against only the supplied `candidate_provisions`.
2. Create evidence links only for operational support, partial support, or a real unresolved conflict. Copy `quoted_text` exactly from the supplied provision text.
3. Apply the four status definitions in the contract. Base the judgment on each item's `completion_criteria`, not retrieval score or topical similarity alone.
4. Emit one `missing_evidence_item` for every non-covered assessment. Emit a conflict object only for `conflicting` assessments.
5. Explain what is satisfied and what remains missing; do not conceal uncertainty behind a high-level relevance statement.
6. Return JSON only. On invalid input, return the error envelope.

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

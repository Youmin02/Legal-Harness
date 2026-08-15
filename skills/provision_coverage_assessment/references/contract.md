# S2 contract

## Operational status definitions

- `covered`: the supplied provisions satisfy the evidence item's completion criteria, and no unresolved conflict blocks use of that evidence.
- `partially_covered`: at least one supplied provision supports part of the criteria, but an identified aspect remains unsupported.
- `uncovered`: no supplied provision supports the evidence item. This is a statement about the current candidate set, not the entire law.
- `conflicting`: supplied provisions create an unresolved scope, applicability, rule/exception, or cross-reference conflict that blocks a stable coverage finding.

## Output sets

- `evidence_links[]`: item-to-provision links with exact excerpts and one of `supports`, `partially_supports`, or `conflicts`.
- `coverage_assessments[]`: exactly one assessment for every required evidence item.
- `missing_evidence_items[]`: exactly the evidence items whose status is not `covered`.
- `evidence_conflicts[]`: exactly the evidence items whose status is `conflicting`.

## Structural consistency

- A `covered` item must have at least one linked provision, no `missing_aspects`, and no conflict object.
- A `partially_covered` item must have at least one linked provision and at least one `missing_aspect`.
- An `uncovered` item must have no linked provisions and no satisfied aspects.
- A `conflicting` item must have linked provisions and a conflict object.
- All link and assessment provision IDs must occur in `candidate_provisions[]`.
- Every quote must be an exact substring of the corresponding candidate provision text.

The harness state reducer may derive `accepted_provision_ids[]` after validation. S2 must not emit that field and must not choose the next action.

## Error envelope

Use `status: "error"` with code `INVALID_INPUT`, `MISSING_REQUIRED_EVIDENCE`, or `CONTRACT_UNSATISFIABLE`. An error is an execution result, not `ABSTAIN`.

# S2 contract

## Coverage axes and legacy status

- `legal_status`: whether supplied provisions satisfy the requested legal rule (`covered`, `partially_covered`, `uncovered`, or `conflicting`).
- `applicability_status`: `direct`, `conditional`, or `not_assessed`; it records fact-to-rule application separately from legal support.
- `gap_type`: `none`, `missing_statute`, `missing_fact`, `scope_excess`, or `conflict`.
- Emit the derived legacy `status` and `partial_kind` as well: covered/direct → `covered`; covered/conditional → `partially_covered` + `factual_condition`; partial legal support → `partially_covered` + `legal_support_gap`.

## Operational status definitions

- `covered`: the supplied provisions satisfy the evidence item's completion criteria, and no unresolved conflict blocks use of that evidence.
- `partially_covered`: at least one supplied provision supports part of the criteria, but an identified aspect remains unsupported. Classify it as `factual_condition` when the complete rule for each supported factual branch is present and only the fact selecting the applicable branch is unresolved (for example, maritime versus air carriage); link all supported branches. Otherwise classify it as `legal_support_gap`.
- `uncovered`: no supplied provision supports the evidence item. This is a statement about the current candidate set, not the entire law.
- `conflicting`: supplied provisions create incompatible legal rules for the same established facts, or an unresolved legal scope/rule/exception/cross-reference conflict. Alternative rules selected solely by a missing fact are not `conflicting`; they are `partially_covered` with `partial_kind: factual_condition`.

## Output sets

- `evidence_links[]`: item-to-provision links with one of `supports`, `partially_supports`, or `conflicts`.
- `coverage_assessments[]`: exactly one assessment for every required evidence item.
- `missing_evidence_items[]`: exactly the evidence items whose status is not `covered`.
- `evidence_conflicts[]`: exactly the evidence items whose status is `conflicting`.

## Structural consistency

- Every `criterion_results[].requirement_id` must refer to an existing S1 completion requirement; do not add a new `missing_aspect` outside that set.
- A `covered` item must have at least one linked provision, no `missing_aspects`, and no conflict object.
- A `partially_covered` item must have at least one linked provision, at least one `missing_aspect`, and `partial_kind` equal to `factual_condition` or `legal_support_gap`.
- Every non-partial item must use `partial_kind: "not_applicable"`.
- An `uncovered` item must have no linked provisions and no satisfied aspects.
- A `conflicting` item must have linked provisions and a conflict object.
- All link and assessment provision IDs must be the short IDs in `candidate_provisions[]` (for example `C001`), never a reconstructed statute ID.
- Set every `quoted_text` value to `[FULL_TEXT]`. The deterministic adapter expands it to the entire immutable candidate text, which is the exact source span retained in the harness state.

The harness state reducer may derive `accepted_provision_ids[]` after validation. S2 must not emit that field and must not choose the next action.

## Error envelope

Use `status: "error"` with code `INVALID_INPUT`, `MISSING_REQUIRED_EVIDENCE`, or `CONTRACT_UNSATISFIABLE`. An error is an execution result, not `ABSTAIN`.

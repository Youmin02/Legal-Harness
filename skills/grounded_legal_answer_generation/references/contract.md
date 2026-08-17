# S3 contract

## Preconditions

The input must contain:

- `authorization.action = "GENERATE"` from `PROVISION_COVERAGE_POLICY`.
- A `covered` assessment for every `critical: true` evidence item, or a policy-authorized `partially_covered` assessment backed by an accepted provision for conditional generation.
- No `uncovered` or `conflicting` critical evidence item.
- A non-empty `accepted_provisions[]` list whose texts are frozen-snapshot inputs supplied by the harness.

If any precondition fails, return an error envelope. S3 does not decide whether to re-retrieve or abstain.

## Success output

- `answer`: the user-facing Korean draft containing citation markers.
- `claims[]`: cited substantive legal claims that are exact answer substrings, classified as `legal_rule`, `application`, `exception`, `procedure`, or `remedy`.
- `claim_citations[]`: claim-to-accepted-provision links with exact source excerpts.
- `assumptions[]`: facts treated as assumptions rather than established facts.
- `limitations[]`: material boundaries of the statutory answer.

Every `claims[]` item must set `citation_required: true` and have at least one citation. Uncited factual or limitation prose belongs only in `answer`, `assumptions[]`, or `limitations[]`. A citation marker must equal `[citation_id]` and appear in `answer`.

## Grounding rules

- Use no provision outside `accepted_provisions[]`.
- Keep `quoted_text` byte-for-byte present in the supplied provision `text`.
- Do not claim that the citation-integrity check passed; that deterministic tool runs next.
- Do not upgrade any partially covered point into a certain conclusion. Express the unresolved condition as a limitation and mark the associated claim conditional, or omit the point.

## Error envelope

Use code `INVALID_INPUT`, `GENERATION_NOT_AUTHORIZED`, `UNCOVERED_CRITICAL_EVIDENCE`, or `CONTRACT_UNSATISFIABLE`. An error is an execution outcome, not `ABSTAIN`.

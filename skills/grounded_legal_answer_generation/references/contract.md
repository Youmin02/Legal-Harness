# S3 contract

## Preconditions

The input must contain:

- `authorization.action = "GENERATE"` from `PROVISION_COVERAGE_POLICY`.
- Harness-owned `answer_mode`, `answered_target_ids`, and `deferred_target_ids`. These constrain claim scope; S3 does not alter them.
- A `covered` assessment for every `critical: true` evidence item, or a policy-authorized `partially_covered` assessment backed by an accepted provision for conditional generation.
- No `uncovered` or `conflicting` critical evidence item.
- A non-empty `accepted_provisions[]` list whose texts are frozen-snapshot inputs supplied by the harness.

For `GENERATE_BENCHMARK_CANDIDATE`, the harness has already decided `ABSTAIN` and
sets `authorization.action = "GENERATE_BENCHMARK_CANDIDATE"`,
`generation_purpose = "benchmark_candidate"`, and `publishable = false`. This
diagnostic-only entry point uses `candidate_provisions[]` (retrieved but not
accepted evidence) and may never change the public `ABSTAIN` decision. It must
not be presented as a supported or publishable answer.

If retrieval produced no candidates, the harness sets
`candidate_answer_basis = "question_only"`. S3 then produces an uncited
diagnostic answer with empty `claims[]` and `claim_citations[]`; it remains
non-publishable and is recorded so candidate-generation failure is not confused
with an empty retrieval result.

If any precondition fails, return an error envelope. S3 does not decide whether to re-retrieve or abstain.

## Success output

- `answer`: the user-facing Korean draft. The harness deterministically serializes accepted claim text, citation markers, assumptions, and limitations after validating the model's claim-to-provision connections.
- `claims[]`: cited substantive legal claims that are exact answer substrings, classified as `legal_rule`, `application`, `exception`, `procedure`, or `remedy`.
- Every claim identifies its answer target(s). In `limited` mode, no claim may identify a deferred target; the answer must instead state its deferral as a non-substantive limitation.
- `claim_citations[]`: claim-to-accepted-provision links with exact source excerpts.
- `assumptions[]`: facts treated as assumptions rather than established facts.
- `limitations[]`: material boundaries of the statutory answer.

Every `claims[]` item must set `citation_required: true` and have at least one citation. Uncited factual or limitation prose belongs only in `answer`, `assumptions[]`, or `limitations[]`. The model owns claim text, claim-to-provision selection, and support descriptions; the harness owns sequential claim/citation IDs, full-text snapshots, marker values, and answer rendering.

## Grounding rules

- Use no provision outside `accepted_provisions[]`.
- In `GENERATE_BENCHMARK_CANDIDATE`, use no provision outside
  `candidate_provisions[]`; its citations are diagnostic provenance only.
- Keep `quoted_text` byte-for-byte present in the supplied provision `text`.
- Do not claim that the citation-integrity check passed; that deterministic tool runs next.
- Do not upgrade any partially covered point into a certain conclusion. Express the unresolved condition as a limitation and mark the associated claim conditional, or omit the point.

## Error envelope

Use code `INVALID_INPUT`, `GENERATION_NOT_AUTHORIZED`, `UNCOVERED_CRITICAL_EVIDENCE`, or `CONTRACT_UNSATISFIABLE`. An error is an execution outcome, not `ABSTAIN`.

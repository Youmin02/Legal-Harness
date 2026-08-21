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

- `answer`: a conclusion-first Korean public answer of 1--3 short sentences, at most 800 characters and preferably 300--500. It contains the legal conclusion, any outcome-changing condition, and only the minimum statutory basis needed to understand that conclusion.
- `claims[]`: the complete audit list of cited substantive legal claims, classified as `legal_rule`, `application`, `exception`, `procedure`, or `remedy`. Audit claims need not all appear in the public answer.
- Every claim identifies its answer target(s). In `limited` mode, no claim may identify a deferred target; the answer must instead state its deferral as a non-substantive limitation.
- `claim_citations[]`: the complete audit list of claim-to-accepted-provision links with exact source excerpts.
- `assumptions[]`: audit facts treated as assumptions rather than established facts.
- `limitations[]`: audit boundaries of the statutory answer.

Every `claims[]` item must set `citation_required: true` and have at least one citation. Uncited factual or limitation prose belongs in `assumptions[]` or `limitations[]`; only an outcome-changing condition is repeated briefly in `answer`. The harness does not append all audit claims, assumptions, or limitations to the public answer. The model owns claim text, claim-to-provision selection, applicability, and support descriptions; the harness owns sequential claim/citation IDs, full-text snapshots, marker values, prioritized public-claim selection, and final answer rendering.

The deterministic public serializer selects at most three audit claims in this order: the first conclusion claim, conditional claims, legal-rule claims, then remaining claims. It renders only those selected claim texts and their harness-owned citation markers. All unselected claims and every assumption and limitation remain available in the structured record.

## Grounding rules

- Use no provision outside `accepted_provisions[]`.
- In `GENERATE_BENCHMARK_CANDIDATE`, use no provision outside
  `candidate_provisions[]`; its citations are diagnostic provenance only.
- Keep `quoted_text` byte-for-byte present in the supplied provision `text`.
- Do not claim that the citation-integrity check passed; that deterministic tool runs next.
- Do not upgrade any partially covered point into a certain conclusion. Express the unresolved condition as a limitation and mark the associated claim conditional, or omit the point.

## Error envelope

Use code `INVALID_INPUT`, `GENERATION_NOT_AUTHORIZED`, `UNCOVERED_CRITICAL_EVIDENCE`, or `CONTRACT_UNSATISFIABLE`. An error is an execution outcome, not `ABSTAIN`.

# S3 contract

## Authorization

`GENERATE_ANSWER` requires harness action `GENERATE`, the supplied answer scope,
and citable accepted provisions for every answered critical item. An uncovered or
conflicting critical item may belong only to a deferred limited-answer target.

`GENERATE_BENCHMARK_CANDIDATE` requires its diagnostic authorization, uses only
`candidate_provisions`, and remains non-publishable. It cannot change public
`ABSTAIN`. With `candidate_answer_basis: question_only`, return an uncited
diagnostic answer with empty `claims` and `claim_citations`.

## Success output

- `answer`: conclusion-first Korean draft within `max_answer_chars`;
- `claims[]`: minimal substantive claims that are exact answer substrings and name
  only answered targets;
- `claim_citations[]`: one or more allowed provision links per claim;
- `assumptions[]` and `limitations[]`: only material premises and scope limits,
  not generic disclaimers or repeated conclusions.

Every claim sets `citation_required: true`. A conclusion-changing condition must
also appear in its conditional claim; an assumption or limitation alone cannot
cure an overbroad conclusion. Do not repeat a rule and its application when one
accurate cited claim can express both. Start with the requested result, not a
statute summary or issue restatement.

## Grounding

Use no provision outside the mode's supplied provision set. Citation excerpts
must occur in the supplied text. The harness owns transport IDs, full snapshots,
citation markers, answer serialization, and deterministic citation validation.
It renders conclusion claims first and retains material assumptions and
limitations after them.

On failed preconditions, use the schema error envelope with `INVALID_INPUT`,
`GENERATION_NOT_AUTHORIZED`, `UNCOVERED_CRITICAL_EVIDENCE`, or
`CONTRACT_UNSATISFIABLE`. An S3 error is `EXECUTION_FAILURE`, not `ABSTAIN`.

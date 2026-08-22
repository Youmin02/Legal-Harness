# Legal Harness development-run evaluation

- Questions: 17
- Supported-answer yield: 0.8824
- Provision micro P/R/F1: 0.6212 / 0.8723 / 0.7257
- Latency median/p95: 475284.866 ms / 636753.999 ms

## Outcomes

| Outcome | Count | Rate |
| --- | ---: | ---: |
| ANSWER | 15 | 0.8824 |
| ABSTAIN | 2 | 0.1176 |
| EXECUTION_FAILURE | 0 | 0.0000 |

## ABSTAIN benchmark-candidate diagnostic

Candidate answers are diagnostic only: the public harness status remains `ABSTAIN` and candidate citations are not accepted evidence.

| Candidate Token-F1@800 scope | Score | Available | Missing |
| --- | ---: | ---: | ---: |
| All outcomes (missing/failure = 0) | 34.01 | 17 | 0 |
| Normal outcomes (ANSWER + ABSTAIN; missing = 0) | 34.01 | 17 | 0 |
| ABSTAIN only (missing = 0) | 22.99 | 2 | 0 |
| ABSTAIN candidates only (available only) | 22.99 | 2 | N/A |
| Available candidates only | 34.01 | 17 | N/A |

- Potential over-abstention exact matches@800: 0 / 2 (0.0000).

## KoBLEX-aligned metrics

All scores in this table use the 0--100 display scale; JSON keeps 0--1 values.

| Split | N | Full | Conditional | Limited | Abstain | Failure | Prov F1 | Prov EM | Token-F1@800 E2E | LF-Eval E2E | Token-F1@800 Answered | LF-Eval Answered |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 17 | 9 | 0 | 6 | 2 | 0 | 72.57 | 17.65 | 31.31 | N/A | 35.48 | N/A |

## Retrieval stages

| Stage | Provision recall | Complete-evidence recall | Availability |
| --- | ---: | ---: | --- |
| first_stage_at_100 | 0.9787 | 0.9412 | available |
| rrf_at_100 | 0.9574 | 0.8824 | available |
| bge_at_10 | 0.9574 | 0.8824 | available |
| bge_at_20 | 0.9787 | 0.9412 | available |
| bge_at_30 | 0.9787 | 0.9412 | available |

## Hop strata

| Hop | ANSWER | ABSTAIN | FAILURE | Supported yield |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 0 | 0 | 1.0000 |
| 2 | 1 | 1 | 0 | 0.5000 |
| 3 | 13 | 1 | 0 | 0.9286 |

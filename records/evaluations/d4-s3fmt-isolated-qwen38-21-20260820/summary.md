# Legal Harness development-run evaluation

- Questions: 21
- Supported-answer yield: 0.7143
- Provision micro P/R/F1: 0.4531 / 0.7250 / 0.5577
- Latency median/p95: 422800.704 ms / 783020.477 ms

## Outcomes

| Outcome | Count | Rate |
| --- | ---: | ---: |
| ANSWER | 15 | 0.7143 |
| ABSTAIN | 5 | 0.2381 |
| EXECUTION_FAILURE | 1 | 0.0476 |

## ABSTAIN benchmark-candidate diagnostic

Candidate answers are diagnostic only: the public harness status remains `ABSTAIN` and candidate citations are not accepted evidence.

| Candidate Token-F1@800 scope | Score | Available | Missing |
| --- | ---: | ---: | ---: |
| All outcomes (missing/failure = 0) | 21.03 | 19 | 2 |
| Normal outcomes (ANSWER + ABSTAIN; missing = 0) | 22.08 | 19 | 1 |
| ABSTAIN only (missing = 0) | 11.27 | 4 | 1 |
| ABSTAIN candidates only (available only) | 14.08 | 4 | N/A |
| Available candidates only | 23.24 | 19 | N/A |

- Potential over-abstention exact matches@800: 0 / 5 (0.0000).

## KoBLEX-aligned metrics

All scores in this table use the 0--100 display scale; JSON keeps 0--1 values.

| Split | N | Full | Conditional | Limited | Abstain | Failure | Prov F1 | Prov EM | Token-F1@800 E2E | LF-Eval E2E | Token-F1@800 Answered | LF-Eval Answered |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 21 | 10 | 1 | 4 | 5 | 1 | 55.77 | 23.81 | 18.35 | N/A | 25.69 | N/A |

## Retrieval stages

| Stage | Provision recall | Complete-evidence recall | Availability |
| --- | ---: | ---: | --- |
| first_stage_at_100 | N/A | N/A | unavailable |
| rrf_at_100 | N/A | N/A | unavailable |
| bge_at_10 | N/A | N/A | unavailable |
| bge_at_20 | N/A | N/A | unavailable |
| bge_at_30 | N/A | N/A | unavailable |

## Hop strata

| Hop | ANSWER | ABSTAIN | FAILURE | Supported yield |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 3 | 3 | 0 | 0.5000 |
| 2 | 9 | 1 | 1 | 0.8182 |
| 3 | 3 | 1 | 0 | 0.7500 |

## Warnings

- `STAGE_PROVENANCE_UNAVAILABLE`

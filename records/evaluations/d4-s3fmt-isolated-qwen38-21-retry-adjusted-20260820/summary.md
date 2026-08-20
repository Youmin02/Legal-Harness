# Legal Harness development-run evaluation

- Questions: 21
- Supported-answer yield: 0.7619
- Provision micro P/R/F1: 0.4412 / 0.7500 / 0.5556
- Latency median/p95: 509906.014 ms / 783020.477 ms

## Outcomes

| Outcome | Count | Rate |
| --- | ---: | ---: |
| ANSWER | 16 | 0.7619 |
| ABSTAIN | 5 | 0.2381 |
| EXECUTION_FAILURE | 0 | 0.0000 |

## ABSTAIN benchmark-candidate diagnostic

Candidate answers are diagnostic only: the public harness status remains `ABSTAIN` and candidate citations are not accepted evidence.

| Candidate Token-F1@800 scope | Score | Available | Missing |
| --- | ---: | ---: | ---: |
| All outcomes (missing/failure = 0) | 21.49 | 20 | 1 |
| Normal outcomes (ANSWER + ABSTAIN; missing = 0) | 21.49 | 20 | 1 |
| ABSTAIN only (missing = 0) | 11.27 | 4 | 1 |
| ABSTAIN candidates only (available only) | 14.08 | 4 | N/A |
| Available candidates only | 22.57 | 20 | N/A |

- Potential over-abstention exact matches@800: 0 / 5 (0.0000).

## KoBLEX-aligned metrics

All scores in this table use the 0--100 display scale; JSON keeps 0--1 values.

| Split | N | Full | Conditional | Limited | Abstain | Failure | Prov F1 | Prov EM | Token-F1@800 E2E | LF-Eval E2E | Token-F1@800 Answered | LF-Eval Answered |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 21 | 11 | 1 | 4 | 5 | 0 | 55.56 | 23.81 | 18.81 | N/A | 24.69 | N/A |

## Retrieval stages

| Stage | Provision recall | Complete-evidence recall | Availability |
| --- | ---: | ---: | --- |
| first_stage_at_100 | 0.8250 | 0.7143 | available |
| rrf_at_100 | 0.7750 | 0.6667 | available |
| bge_at_10 | 0.7250 | 0.5238 | available |
| bge_at_20 | 0.7750 | 0.6190 | available |
| bge_at_30 | 0.7750 | 0.6190 | available |

## Hop strata

| Hop | ANSWER | ABSTAIN | FAILURE | Supported yield |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 3 | 3 | 0 | 0.5000 |
| 2 | 10 | 1 | 0 | 0.9091 |
| 3 | 3 | 1 | 0 | 0.7500 |

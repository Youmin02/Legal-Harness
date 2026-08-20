# Legal Harness development-run evaluation

- Questions: 21
- Supported-answer yield: 0.1905
- Provision micro P/R/F1: 0.4565 / 0.5250 / 0.4884
- Latency median/p95: 319372.368 ms / 434042.294 ms

## Outcomes

| Outcome | Count | Rate |
| --- | ---: | ---: |
| ANSWER | 4 | 0.1905 |
| ABSTAIN | 17 | 0.8095 |
| EXECUTION_FAILURE | 0 | 0.0000 |

## ABSTAIN benchmark-candidate diagnostic

Candidate answers are diagnostic only: the public harness status remains `ABSTAIN` and candidate citations are not accepted evidence.

| Candidate Token-F1@800 scope | Score | Available | Missing |
| --- | ---: | ---: | ---: |
| All outcomes (missing/failure = 0) | 9.02 | 4 | 17 |
| Normal outcomes (ANSWER + ABSTAIN; missing = 0) | 9.02 | 4 | 17 |
| ABSTAIN only (missing = 0) | 0.00 | 0 | 17 |
| ABSTAIN candidates only (available only) | N/A | 0 | N/A |
| Available candidates only | 47.33 | 4 | N/A |

- Potential over-abstention exact matches@800: 0 / 17 (0.0000).

## KoBLEX-aligned metrics

All scores in this table use the 0--100 display scale; JSON keeps 0--1 values.

| Split | N | Full | Conditional | Limited | Abstain | Failure | Prov F1 | Prov EM | Token-F1@800 E2E | LF-Eval E2E | Token-F1@800 Answered | LF-Eval Answered |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 21 | 0 | 0 | 0 | 17 | 0 | 48.84 | 23.81 | 9.02 | N/A | 47.33 | N/A |

## Retrieval stages

| Stage | Provision recall | Complete-evidence recall | Availability |
| --- | ---: | ---: | --- |
| first_stage_at_100 | 0.8500 | 0.7619 | available |
| rrf_at_100 | 0.8000 | 0.6667 | available |
| bge_at_10 | 0.5500 | 0.4762 | available |
| bge_at_20 | 0.6500 | 0.5714 | available |
| bge_at_30 | 0.6750 | 0.5714 | available |

## Hop strata

| Hop | ANSWER | ABSTAIN | FAILURE | Supported yield |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 5 | 0 | 0.1667 |
| 2 | 3 | 8 | 0 | 0.2727 |
| 3 | 0 | 4 | 0 | 0.0000 |

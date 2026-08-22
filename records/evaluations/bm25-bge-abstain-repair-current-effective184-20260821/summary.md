# Legal Harness development-run evaluation

- Questions: 184
- Supported-answer yield: 0.8152
- Provision micro P/R/F1: 0.5309 / 0.7600 / 0.6251
- Latency median/p95: 303865.531 ms / 837132.267 ms

## Outcomes

| Outcome | Count | Rate |
| --- | ---: | ---: |
| ANSWER | 150 | 0.8152 |
| ABSTAIN | 34 | 0.1848 |
| EXECUTION_FAILURE | 0 | 0.0000 |

## ABSTAIN benchmark-candidate diagnostic

Candidate answers are diagnostic only: the public harness status remains `ABSTAIN` and candidate citations are not accepted evidence.

| Candidate Token-F1@800 scope | Score | Available | Missing |
| --- | ---: | ---: | ---: |
| All outcomes (missing/failure = 0) | 23.59 | 181 | 3 |
| Normal outcomes (ANSWER + ABSTAIN; missing = 0) | 23.59 | 181 | 3 |
| ABSTAIN only (missing = 0) | 13.51 | 31 | 3 |
| ABSTAIN candidates only (available only) | 14.82 | 31 | N/A |
| Available candidates only | 23.98 | 181 | N/A |

- Potential over-abstention exact matches@800: 0 / 34 (0.0000).

## KoBLEX-aligned metrics

All scores in this table use the 0--100 display scale; JSON keeps 0--1 values.

| Split | N | Full | Conditional | Limited | Abstain | Failure | Prov F1 | Prov EM | Token-F1@800 E2E | LF-Eval E2E | Token-F1@800 Answered | LF-Eval Answered |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 184 | 114 | 2 | 34 | 34 | 0 | 62.51 | 30.43 | 21.09 | N/A | 25.87 | N/A |

## Retrieval stages

| Stage | Provision recall | Complete-evidence recall | Availability |
| --- | ---: | ---: | --- |
| first_stage_at_100 | 0.8600 | 0.7554 | available |
| rrf_at_100 | 0.8343 | 0.7065 | available |
| bge_at_10 | 0.8057 | 0.6630 | available |
| bge_at_20 | 0.8371 | 0.7174 | available |
| bge_at_30 | 0.8429 | 0.7228 | available |

## Hop strata

| Hop | ANSWER | ABSTAIN | FAILURE | Supported yield |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 39 | 10 | 0 | 0.7959 |
| 2 | 88 | 22 | 0 | 0.8000 |
| 3 | 23 | 2 | 0 | 0.9200 |

# Legal Harness development-run evaluation

- Questions: 21
- Supported-answer yield: 0.2857
- Provision micro P/R/F1: 0.3585 / 0.4750 / 0.4086
- Latency median/p95: 311993.593 ms / 474483.465 ms

## Outcomes

| Outcome | Count | Rate |
| --- | ---: | ---: |
| ANSWER | 6 | 0.2857 |
| ABSTAIN | 13 | 0.6190 |
| EXECUTION_FAILURE | 2 | 0.0952 |

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
| 1 | 4 | 2 | 0 | 0.6667 |
| 2 | 2 | 7 | 2 | 0.1818 |
| 3 | 0 | 4 | 0 | 0.0000 |

## Warnings

- `STAGE_PROVENANCE_UNAVAILABLE`

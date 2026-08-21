# Legal Harness development-run evaluation

> **Status: `INVALID_FOR_CLEAN_RETRIEVER_COMPARISON` (`DIAGNOSTIC_ONLY`).**
>
> Do not use this artifact for a clean BM25-versus-KURE comparison. S1 JSON generation failed in 35 runs, and the batch was split across two recorded code provenances (58 and 168 runs). The files are retained for diagnostics.

- Questions: 226
- Supported-answer yield: 0.6549
- Provision micro P/R/F1: 0.5519 / 0.6366 / 0.5912
- Latency median/p95: 235913.342 ms / 793275.710 ms

## Outcomes

| Outcome | Count | Rate |
| --- | ---: | ---: |
| ANSWER | 148 | 0.6549 |
| ABSTAIN | 38 | 0.1681 |
| EXECUTION_FAILURE | 40 | 0.1770 |

## ABSTAIN benchmark-candidate diagnostic

Candidate answers are diagnostic only: the public harness status remains `ABSTAIN` and candidate citations are not accepted evidence.

| Candidate Token-F1@800 scope | Score | Available | Missing |
| --- | ---: | ---: | ---: |
| All outcomes (missing/failure = 0) | 19.44 | 183 | 43 |
| Normal outcomes (ANSWER + ABSTAIN; missing = 0) | 23.62 | 183 | 3 |
| ABSTAIN only (missing = 0) | 13.92 | 35 | 3 |
| ABSTAIN candidates only (available only) | 15.11 | 35 | N/A |
| Available candidates only | 24.00 | 183 | N/A |

- Potential over-abstention exact matches@800: 0 / 38 (0.0000).

## KoBLEX-aligned metrics

All scores in this table use the 0--100 display scale; JSON keeps 0--1 values.

| Split | N | Full | Conditional | Limited | Abstain | Failure | Prov F1 | Prov EM | Token-F1@800 E2E | LF-Eval E2E | Token-F1@800 Answered | LF-Eval Answered |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 226 | 122 | 3 | 23 | 38 | 40 | 59.12 | 29.65 | 17.10 | N/A | 26.11 | N/A |

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
| 1 | 39 | 14 | 4 | 0.6842 |
| 2 | 99 | 19 | 9 | 0.7795 |
| 3 | 10 | 5 | 27 | 0.2381 |

## Warnings

- `STAGE_PROVENANCE_UNAVAILABLE`

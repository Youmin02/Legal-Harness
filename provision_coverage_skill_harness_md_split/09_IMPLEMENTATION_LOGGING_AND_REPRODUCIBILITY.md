---
project: "조문 근거 충족도 기반 스킬 하네스"
document_part: "실행 환경·로그·재현성·코드 구조"
source_version: "1.0-handoff-split"
last_updated: "2026-08-11"
---

[← 시작 문서로 돌아가기](00_START_HERE.md)

# 18. 실행 환경

- NVIDIA H200 141GB 1장
- Qwen3.6-27B BF16 text-only serving
- vLLM structured output
- 문서 임베딩은 오프라인 1회 구축
- 온라인에서 KURE 질의 인코딩만 수행
- Qwen, KURE, BGE는 질의 단위 순차 스케줄링 우선
- 하네스, BM25, exact vector search, Citation Integrity는 CPU/RAM 병행
- 실제 토큰 분포를 측정해 32K/64K/131K 중 가장 작은 충분 컨텍스트를 동결
- S1·S2는 non-thinking structured output
- S3는 thinking 기반 grounded generation
- format-only retry 1회
- 재시도 후 Schema 유효율 목표 99% 이상

모델 revision과 라이브러리 버전은 실행 직전에 확인하고 lock file에 기록한다.

---

# 19. 로그와 재현성

## 19.1 로그 Schema

```text
run_id, condition, seed, question_id,
model_id, model_revision, tokenizer_revision,
skill_id, skill_version, prompt_hash,
tool_id, tool_revision, tool_arguments,
retrieval_request, query_channel, retriever_id,
top100_ids, fused_ids, bge_top10_ids, bge_scores,
legal_issues, required_evidence_items,
provision_assessments,
accepted_provision_ids,
missing_evidence_items, evidence_conflicts,
coverage_output, policy_action,
input_tokens, output_tokens, latency_ms,
final_answer, cited_provision_ids,
abstention_reason, termination_reason,
execution_error
```

## 19.2 보존 아티팩트

- S1·S2·S3 SKILL.md
- prompt templates
- JSON Schemas
- failure contracts
- Run State transition and Policy code
- corpus hash and preprocessing code
- BM25/KURE/BGE/Qwen revision
- raw and adjudicated annotations
- raw run logs
- aggregation/statistics/figure scripts
- H200/CUDA/vLLM/Transformers lock file

---

# 20. 권장 코드 구조

```text
project/
├── README.md
├── configs/
│   ├── model.yaml
│   ├── retrieval.yaml
│   ├── policy.yaml
│   └── experiment_conditions.yaml
├── harness/
│   ├── runner.py
│   ├── run_state.py
│   ├── policy.py
│   ├── validation.py
│   ├── state_update.py
│   └── tracing.py
├── skills/
│   ├── legal_issue_and_query_planning/
│   ├── provision_coverage_assessment/
│   └── grounded_legal_answer_generation/
├── tools/
│   ├── retrieve_provisions/
│   └── validate_citation_integrity/
├── retrieval/
│   ├── bm25.py
│   ├── kure.py
│   ├── rrf.py
│   ├── reranker.py
│   └── corpus.py
├── annotation/
│   ├── guidelines.md
│   ├── schema.json
│   └── adjudication.py
├── evaluation/
│   ├── provision_metrics.py
│   ├── coverage_metrics.py
│   ├── answer_metrics.py
│   ├── bootstrap.py
│   └── human_eval.py
├── experiments/
│   ├── baselines/
│   ├── ablations/
│   └── run_experiment.py
├── tests/
│   ├── test_initial_path.py
│   ├── test_gap_path.py
│   ├── test_generate_path.py
│   ├── test_abstain_path.py
│   ├── test_citation_integrity.py
│   └── test_state_invariants.py
└── artifacts/
```

---

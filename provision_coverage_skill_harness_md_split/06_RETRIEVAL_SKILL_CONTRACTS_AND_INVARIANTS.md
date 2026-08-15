---
project: "조문 근거 충족도 기반 스킬 하네스"
document_part: "검색 파이프라인·스킬 계약·실행 불변식"
source_version: "1.0-handoff-split"
last_updated: "2026-08-11"
---

[← 시작 문서로 돌아가기](00_START_HERE.md)

# 10. 검색 파이프라인

## 10.1 검색기 후보

| 조건 | 1차 검색기 | 질의 채널 통합 | 2차 재순위화 |
|---|---|---|---|
| Sparse | BM25 | 쟁점별 RRF | BGE cross-encoder |
| Dense | KURE-v1 exact vector search | 쟁점별 RRF | BGE cross-encoder |

Hybrid는 현재 주 실험 범위에서 제외한다.

## 10.2 선택 규칙

개발 세트에서 다음 우선순위로 하나를 선택한다.

1. Complete Evidence Recall@100
2. Provision Recall@100
3. Complete Evidence Recall@10
4. Provision Recall@10
5. 동률이면 지연시간과 구현 단순성

선택한 검색기와 revision, 전처리, top-k, RRF 설정을 테스트 전에 동결한다.

## 10.3 RRF의 역할

RRF는 BM25와 KURE-v1을 합치는 hybrid 용도가 아니다. 선택된 한 검색기에서 여러 법률 쟁점·질의 채널별 ranked list를 융합한다.

```text
각 issue의 provision-style 결과
각 issue의 sparse-keyword 결과
각 issue의 statute-aware 결과
→ Issue-level Reciprocal Rank Fusion
```

## 10.4 검색 데이터 처리

- 법령명 + 조·항·호 계층 + 본문을 검색 표현으로 사용
- 긴 조문은 조·항·호 경계를 우선해 분할
- 필요 시 중첩 window 사용
- chunk 점수를 원본 provision ID로 통합
- split/trim 비율과 원본 ID 매핑 보존
- Dense 검색은 정확도 우선 exact inner-product search
- KURE-v1 문서 임베딩은 오프라인 구축

---

# 11. 스킬 패키지 구현 계약

## 11.1 공통 패키지 구조

```text
skills/
├── legal_issue_and_query_planning/
│   ├── SKILL.md
│   ├── prompt_template.jinja
│   ├── input.schema.json
│   ├── output.schema.json
│   └── failure_contract.json
├── provision_coverage_assessment/
│   ├── SKILL.md
│   ├── prompt_template.jinja
│   ├── input.schema.json
│   ├── output.schema.json
│   └── failure_contract.json
└── grounded_legal_answer_generation/
    ├── SKILL.md
    ├── prompt_template.jinja
    ├── input.schema.json
    ├── output.schema.json
    └── failure_contract.json
```

## 11.2 실패 코드 예시

| 스킬 | 실패 코드 예시 |
|---|---|
| S1 | `INVALID_PLAN`, `EMPTY_ISSUE_SET`, `DUPLICATE_RETRIEVAL_REQUEST` |
| S2 | `INVALID_COVERAGE`, `UNMAPPED_EVIDENCE`, `UNKNOWN_PROVISION_REFERENCE` |
| S3 | `UNSUPPORTED_CLAIM`, `INVALID_CITATION`, `EMPTY_ANSWER` |

스킬은 다음 스킬이나 도구를 직접 호출하지 않는다.

---

# 12. 실행 불변식

1. S1·S2·S3는 서로를 직접 호출하지 않는다.
2. 스킬은 다음 행동을 선택하지 않는다.
3. S2는 검색기를 직접 호출하지 않는다.
4. S3는 Citation Integrity 도구를 직접 호출하지 않는다.
5. 모든 결과는 Schema/참조 검증과 상태 갱신을 거친 뒤 Policy에서 사용한다.
6. 추가 검색 결과는 반드시 S2 재판정을 거친다.
7. `ABSTAIN`은 S3와 Citation Integrity를 우회한다.
8. Citation Integrity `PASS` 전에는 생성 답변을 최종 반환하지 않는다.
9. Qwen은 A·C·D-1·D-3에만 연결한다.
10. 코퍼스·인덱스는 B·D-2·D-4에만 연결한다.
11. 최초 검색과 추가 검색은 동일한 동결 검색 설정을 사용한다.
12. S3에는 accepted evidence만 전달한다.
13. `ABSTAIN`과 `EXECUTION_FAILURE`를 로그·평가에서 분리한다.

---

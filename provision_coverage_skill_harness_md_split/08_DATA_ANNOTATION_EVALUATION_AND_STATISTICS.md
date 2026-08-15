---
project: "조문 근거 충족도 기반 스킬 하네스"
document_part: "데이터·주석·평가·통계·사람 평가"
source_version: "1.0-handoff-split"
last_updated: "2026-08-11"
---

[← 시작 문서로 돌아가기](00_START_HERE.md)

# 14. 데이터와 주석

## 14.1 KoBLEX

- 226문항
- 1-hop 55
- 2-hop 125
- 3-hop 46
- 배경 시나리오, 질문, 정답, 지지 조문 포함

## 14.2 근거 항목 주석 Schema

```text
question_id
issue_id
issue_description
evidence_item_id
evidence_type
critical
criticality_rationale
gold_support_groups
satisfaction_rule
scope_or_temporal_condition
annotation_rationale
```

## 14.3 근거 유형

- 주된 적용 규정·권리·의무
- 정의·적용 범위
- 성립·적용 요건
- 예외·단서·배제
- 절차·기한·관할
- 법적 효과·제재·벌칙
- 위임 규정·하위 법령
- 준용·인용·연결 규정

`critical=true`는 해당 항목을 제거하면 핵심 결론이 바뀌거나 조문으로 완전하게 정당화할 수 없게 되는 경우다.

## 14.4 복수 근거 만족 규칙

대체 가능한 조문과 결합이 필요한 조문을 표현하기 위해 `gold_support_groups`를 사용한다.

```text
gold_satisfied(item, S) = 1
iff there exists G in gold_support_groups(item)
such that G ⊆ S
```

## 14.5 주석 절차

- 법학 배경 평가자 2명 우선
- 독립 주석 후 협의
- 원 주석과 합의 주석 모두 보존
- evidence type, criticality, issue–provision mapping 합의도 보고
- 시스템 출력 및 조건을 주석자에게 비공개

## 14.6 스트레스 세트

문항별로 다음 상태를 구축한다.

1. 모든 critical gold 조문 포함
2. 각 critical item 제거
3. 제거 item을 hard negative 조문으로 교체
4. gold + distractor 혼합
5. 전문가가 확인한 conflict 사례

신뢰할 만한 conflict 사례를 구축하지 못하면 `conflicting`은 탐색적 분석으로 하향한다.

---

# 15. 평가 지표

## 15.1 조문 수준

질문 `q`의 gold 조문 집합을 `G_q`, 최종 accepted 조문 집합을 `A_q`로 정의한다.

```text
Precision_q = |A_q ∩ G_q| / |A_q|
Recall_q    = |A_q ∩ G_q| / |G_q|
F1_q        = harmonic_mean(Precision_q, Recall_q)

CompleteEvidence@K_q = 1 if G_q ⊆ RetrievedTopK_q else 0
```

`A_q`가 비어 있으면 Precision과 F1을 0으로 정의한다.

주 지표 후보:

- 2·3-hop Provision F1
- Complete Evidence Recall@100
- Provision Recall@100

## 15.2 S2 intrinsic 평가

통제된 gold item과 후보 조문 상태에서 M과 C5를 비교한다.

```text
FCR_micro = Σ false_covered / Σ truly_uncovered
FCR_macro = mean_q(false_covered_q / truly_uncovered_q)
```

- False-Covered Rate
- False-Uncovered Rate
- Covered Precision
- S2 Macro-F1
- issue–provision mapping F1
- Gap Recovery Rate

스트레스 상태가 같은 원 질문에서 파생되므로 bootstrap unit은 상태가 아니라 `question_id`다.

## 15.3 답변 수준

- Answer Coverage
- Supported Answer Yield
- Unsafe Answer Rate
- Unsupported Claim Rate
- Token-F1
- LF-Eval 또는 명시적으로 구분한 adapted evaluator
- Citation Precision/Recall/F1
- 존재하지 않는 조문 ID 인용률
- accepted evidence 외 조문 인용률

Token-F1과 evaluator 점수는 두 방식으로 보고한다.

1. ABSTAIN을 0점 처리한 end-to-end 결과
2. 실제 답변한 문항만 계산한 answered-only 결과

## 15.4 비용

- 검색 라운드 수
- retrieval request 수
- Qwen 호출 수
- input/output/total tokens
- BM25, KURE, BGE, Qwen, end-to-end latency
- H200 peak memory
- Supported Answer Yield당 비용

---

# 16. 통계 계획

- 질문 단위 paired/cluster bootstrap 10,000회
- F1, LF-Eval, FCR 차이의 95% CI
- 이진 오류는 사전 이진화 규칙을 둔 McNemar 보조 분석
- 다중 비교 Holm 보정
- 2·3-hop 결합 분석을 confirmatory
- hop별·법령군별 분석은 subgroup/exploratory
- p-value뿐 아니라 effect size와 CI 보고
- 조건별 3개 고정 seed
- 문항별 seed 평균 후 문항 단위 분석
- seed를 독립 표본으로 취급하지 않음

---

# 17. 사람 평가

- 최종 테스트 최소 60문항
- hop별 층화
- 법학 배경 평가자 2명 우선
- 시스템명과 hop 정보 블라인드
- 무작위 순서

평가 항목:

- 결론 정확성
- 조문 적절성
- 누락 근거
- 과도한 단정
- 보류 적정성
- 주장–조문 실제 지지 여부

Cohen’s kappa 또는 Krippendorff’s alpha를 보고한다.

---

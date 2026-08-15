---
project: "조문 근거 충족도 기반 스킬 하네스"
document_part: "비교 실험·기준선·제거 실험"
source_version: "1.0-handoff-split"
last_updated: "2026-08-11"
---

[← 시작 문서로 돌아가기](00_START_HERE.md)

# 13. 비교 실험

## 13.1 연구 질문

### RQ1. 전체 시스템 효과

동일한 S1, Qwen, 동결 검색기, BGE, S3 조건에서 제안 하네스가 즉시 생성보다 2·3-hop 최종 채택 조문 F1과 근거가 완비된 답변 산출을 개선하는가?

### RQ2. 법률 근거 유형의 가치

법률 근거 유형 기반 S2가 범용 missing-information 충분성 제어보다 부족한 critical 근거의 오승인을 줄이는가?

### RQ3. 운영 비용

고정 반복 검색 대비 검색 라운드, Qwen 호출, 토큰, 지연시간, Supported Answer Yield당 비용은 어떻게 달라지는가?

## 13.2 비교군

| 조건 | 구성 | 목적 |
|---|---|---|
| C0 No Retrieval | 검색 없는 Qwen 답변 | 파라메트릭 하한선 |
| C1 Fixed-K One-Shot RAG | 원 질문 고정 Top-k 검색 후 1회 생성 | 일반 RAG |
| C2 ParSeR-Qwen | Retrieve–Rerank–Selection 통제 재구현 | KoBLEX 원 방법 계열 |
| C-DaR DaR-Qwen | 분해·질의 정제·쟁점별 Selection에 가까운 재구현 | 외부 강한 방법 비교 |
| C3 Controlled Immediate | M과 같은 S1·초기 검색·S3, S2 없이 즉시 생성 | RQ1 핵심 인과 기준선 |
| C4 Fixed Iterative | 충족도 없이 최대 라운드까지 검색 후 생성 | 고정 반복 검색 |
| C5 Generic Sufficiency | 같은 항목·상태·예산, 법률 근거 유형 규칙만 제거 | RQ2 핵심 기준선 |
| M Proposed | 법률 근거 유형 기반 S2 + 조건부 재검색·생성·보류 | 제안 방법 |

## 13.3 공정 비교를 위한 고정 요소

- Qwen model/revision/tokenizer/chat template
- 질문×seed별 캐시된 S1 INITIAL_PLAN 결과
- 개발 세트에서 선택·동결한 검색기
- RRF 및 BGE Top-10
- 동결 법령 코퍼스와 전처리
- 최대 검색 예산
- S3 prompt/sampling
- Citation Integrity 검사

## 13.4 제거 실험

1. `w/o Gap Query`: 원 질문 반복
2. `w/o Abstention`: 예산 소진에도 생성
3. `w/o Reranker`: BGE 제거
4. `w/o Harness State`: 라운드별 독립 실행
5. `M-ForcedMax`: S2와 Gap Query를 유지하지만 최대 라운드까지 항상 검색

C3은 `w/o Provision Coverage`, C5는 `w/o Legal Evidence Types` 역할을 겸한다.

## 13.5 진단 실험

- Gold Evidence → S3: 생성기 상한
- Gold Coverage Decision + System Retrieval: Policy/coverage 상한
- System Coverage + Gold Candidate Pool: 검색 실패와 S2 실패 분리

---

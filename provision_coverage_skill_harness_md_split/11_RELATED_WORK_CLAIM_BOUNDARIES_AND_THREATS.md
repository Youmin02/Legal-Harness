---
project: "조문 근거 충족도 기반 스킬 하네스"
document_part: "선행연구·주장 경계·타당성 위협"
source_version: "1.0-handoff-split"
last_updated: "2026-08-11"
---

[← 시작 문서로 돌아가기](00_START_HERE.md)

# 23. 선행연구와 신규성 경계

## KoBLEX / ParSeR

- 주 벤치마크 및 지지 조문 제공
- Retrieve–Rerank–Selection 계열
- ParSeR Selection을 하네스로 재명명하지 않는다.

## Decompose-and-Refine

- atomic sub-question / legal issue decomposition
- provision-style, sparse keyword, statute-aware query refinement
- S1은 고정 선행 구성으로 사용하고 신규성으로 주장하지 않는다.

## S2G-RAG

- evidence sufficiency와 structured gap 기반 반복 retrieval
- 반복 gap retrieval 자체를 최초로 주장하지 않는다.
- 차이는 typed legal evidence obligation, provision ID linkage, criticality, budget-aware skill/tool control이다.

## 관련 분야

- Adaptive-RAG: 질문 복잡도 기반 검색 적응
- citation generation 연구: claim-level citation과 groundedness 평가

---

# 24. 사용하지 않을 주장

- 본 시스템은 멀티에이전트다.
- MCP가 정확도를 향상한다.
- 질의 분해를 최초로 제안한다.
- gap retrieval을 최초로 제안한다.
- KURE-v1 또는 BM25가 모든 한국 법률 검색기보다 우수하다.
- 조문 ID 존재가 법적 타당성을 보장한다.
- Citation Integrity가 entailment를 보장한다.
- 자동 Coverage Assessment가 법률가의 최종 판단을 대체한다.
- KoBLEX 결과가 실제 법률 상담 능력을 증명한다.

---

# 25. 타당성 위협과 대응

| 위협 | 위험 | 대응 |
|---|---|---|
| DaR 중복 | S1을 신규성으로 오해 | S1 고정, controlled baseline 포함 |
| S2G-RAG 중복 | sufficiency/gap 최초 주장 | 최초 주장 금지, C5 비교 |
| 검색기 효과 혼입 | retriever 성능이 harness 효과로 보임 | 개발 세트에서 선택 후 C3/C5/M에 고정 |
| 같은 Qwen의 자기평가 | 계획·판정·생성 결합 | intrinsic S2, stress set, deterministic citation check, human eval |
| 충족도 라벨 부재 | gold provision을 critical/type로 오인 | 별도 2인 주석 |
| 충돌 과장 | hard negative를 conflict로 오인 | 전문가 curated conflict 없으면 exploratory |
| 테스트 누출 | 정답 조문/hop로 policy tuning | dev/test 분리와 설정 hash |
| 과도한 abstention | 안전 지표만 좋아짐 | Answer Coverage, Supported Answer Yield, end-to-end 0점 처리 |
| H200 OOM | 여러 모델 및 긴 context | 순차 스케줄링, 최소 충분 context 동결 |

---

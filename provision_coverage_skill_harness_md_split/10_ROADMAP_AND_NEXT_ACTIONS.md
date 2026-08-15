---
project: "조문 근거 충족도 기반 스킬 하네스"
document_part: "12주 로드맵·즉시 실행 작업"
source_version: "1.0-handoff-split"
last_updated: "2026-08-11"
---

[← 시작 문서로 돌아가기](00_START_HERE.md)

# 21. 12주 로드맵

| 주 | 작업 | 완료 기준 |
|---:|---|---|
| 1 | KoBLEX/법령 코퍼스 확보, hash, 예비 주석 | 226문항·코퍼스 통계 검증, 예비 20~30문항 |
| 2 | BM25/KURE/BGE, chunk 규칙 | Recall 및 Complete Evidence Recall 로그 |
| 3 | Qwen/vLLM/Schema 사전점검, 기준선 착수 | memory/context/JSON 성공 |
| 4 | S1 INITIAL/GAP 및 cache | 입출력 계약 통과 |
| 5 | S2 intrinsic 평가와 stress states | FCR 산출 가능 |
| 6 | Policy/S3/Citation Integrity | 세 action 및 종료 경로 unit test |
| 7 | C0/C1/C3/C5/M smoke test | end-to-end 로그 완결 |
| 8 | ParSeR/DaR/C4/M-ForcedMax | 공정 비교 검증 |
| 9 | 검색기/prompt/budget/statistics 동결 | 최종 설정 hash |
| 10 | 최종 테스트 및 핵심 ablation | 누락 없는 raw results |
| 11 | cluster bootstrap 및 사람 평가 | CI/effect size/agreement |
| 12 | KCI 원고·도표·재현 패키지 | 본문/부록/checklist |

---

# 22. 즉시 실행할 작업

## P0 — 먼저 해야 함

- [ ] 최종 변수명으로 Notion/PDF/Figma/코드 문서 통일
- [ ] S1 input/output JSON Schema 작성
- [ ] S2 input/output JSON Schema 작성
- [ ] S3 input/output JSON Schema 작성
- [ ] RunState dataclass 또는 Pydantic model 작성
- [ ] Policy unit test 작성
- [ ] BM25와 KURE-v1 smoke retrieval 구현
- [ ] BGE reranker 연결
- [ ] 20~30문항 예비 주석

## P1 — 실험 전

- [ ] 개발/테스트 group-stratified split 동결
- [ ] BM25 vs KURE-v1 선택
- [ ] 검색 round=3 및 no-progress=2 확인
- [ ] C3/C5/M end-to-end 실행
- [ ] abstention response schema 구현
- [ ] raw log completeness test

## P2 — 최종 실험

- [ ] 외부 baselines
- [ ] 모든 ablations
- [ ] final test 3 seeds
- [ ] bootstrap and human evaluation
- [ ] reproducibility package

---

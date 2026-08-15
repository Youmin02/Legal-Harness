---
project: "조문 근거 충족도 기반 스킬 하네스"
document_part: "미팅 브리프·미결정 사항·최종 체크"
source_version: "1.0-handoff-split"
last_updated: "2026-08-11"
---

[← 시작 문서로 돌아가기](00_START_HERE.md)

# 26. 지도교수 미팅용 요약

## 60초 설명

> 이 연구는 한국 법률 다중 홉 질문을 법률 쟁점과 필수 조문 근거 항목으로 먼저 구조화한다. 검색된 조문을 각 근거 항목과 연결해 현재 근거가 충분한지 판정하고, critical 근거가 부족하면 그 gap만 다시 검색한다. 모든 필수 근거가 확보되면 채택 조문만으로 답변을 생성하고 인용 무결성을 검사한다. 검색 예산 내에 근거를 확보하지 못하면 불완전한 법률 결론 대신 부족 근거와 종료 이유를 포함한 보류 응답을 반환한다. 기여는 질문별 근거 상태와 예산을 이용해 S1·S2·S3와 검색·검사 도구의 실행 순서를 관리하는 데 있다.

## 예상 질문

### DaR와 S2G-RAG를 결합한 것 아닌가?

쟁점 분해와 범용 sufficiency/gap은 선행 구성이다. 신규성은 법률 쟁점별 typed evidence obligation, 실제 provision ID linkage, criticality와 budget 기반 control, 그리고 이를 평가하기 위한 annotation/stress protocol에 둔다.

### 하네스가 정확히 무엇인가?

모델이 아니라 질문별 상태, 실행 순서, 검색 예산, 재시도, 중단, 답변 보류를 관리하는 실행 런타임이다.

### 같은 Qwen이 계획·판정·답변을 하면 자기평가 아닌가?

그래서 intrinsic S2 평가, controlled stress states, deterministic citation integrity, independent human evaluation을 분리한다.

### 모두 보류하면 안전 지표가 좋아지는 것 아닌가?

Answer Coverage와 Supported Answer Yield를 함께 보고하고, 보류를 0점 처리한 end-to-end 답변 지표를 병기한다.

---

# 27. 현재 남은 미결정 사항

다음은 구현 전 또는 지도교수 확인 후 결정한다.

1. 226문항 전체 2인 주석의 현실성
2. `준용·인용·연결 규정`을 독립 evidence type으로 유지할지
3. DaR 재구현을 주 비교군으로 둘지 보조 비교로 둘지
4. 답변 수준 주 안전성 지표를 Supported Answer Yield와 Unsafe Answer Rate 중 무엇으로 둘지
5. conflict set을 주 결과에 포함할 수 있는지
6. 외부 judge를 사용할지 사람 평가 중심으로 제한할지
7. 최종 검색기 BM25 또는 KURE-v1

---

# 28. 피겨 최종 체크리스트

- [ ] 제목: `조문 근거 충족도 기반 스킬 하네스`
- [ ] S1 → Retrieval 선은 `retrieval_requests[]`
- [ ] Retrieval → S2 선은 `candidate_provisions[]`
- [ ] S2 → Policy는 최종 변수명 사용
- [ ] Policy → S3에 `accepted_provision_ids[]`
- [ ] D-2 → S2 재판정 선 존재
- [ ] ABSTAIN → Response Assembly 직결
- [ ] Citation PASS 전 최종 답변 반환 없음
- [ ] LLM 점선은 A/C/D-1/D-3에만 연결
- [ ] 데이터 점선은 B/D-2/D-4에만 연결
- [ ] BGE는 Retrieval 내부
- [ ] RRF는 질의 채널 단위 순위 융합
- [ ] 점선에 화살촉 없음
- [ ] `ABSTAIN`과 `EXECUTION_FAILURE` 혼동 없음

---

# 29. 참고문헌 및 링크

- Lee, J. et al. (2025). [KoBLEX: Open Legal Question Answering with Multi-hop Reasoning](https://aclanthology.org/2025.emnlp-main.200/)
- Lee, J., Kim, H., & Lee, G. (2026). [Decompose-and-Refine: Structured Legal Question Answering with Parametric Retrieval](https://arxiv.org/abs/2605.24454)
- Li, M. et al. (2026). [S2G-RAG: Structured Sufficiency and Gap Judging for Iterative Retrieval-Augmented QA](https://aclanthology.org/2026.acl-long.1185/)
- Jeong, S. et al. (2024). [Adaptive-RAG](https://aclanthology.org/2024.naacl-long.389/)
- Gao, T. et al. (2023). [Enabling Large Language Models to Generate Text with Citations](https://aclanthology.org/2023.emnlp-main.398/)
- [Qwen3.6-27B model card](https://huggingface.co/Qwen/Qwen3.6-27B)
- [KURE-v1 model card](https://huggingface.co/nlpai-lab/KURE-v1)
- [bge-reranker-v2-m3-ko model card](https://huggingface.co/dragonkue/bge-reranker-v2-m3-ko)

> 구현 시작 전에 모델·라이브러리 revision과 serving 옵션을 다시 확인하고 lock file에 기록한다.

---

# 30. 인수인계 완료 조건

다음 사람이 작업을 시작하기 전에 아래를 확인한다.

- 이 문서와 Figure 1의 경로가 일치하는가
- Notion/논문/Figma/코드 변수명이 일치하는가
- 동결 결정과 미결정 사항이 구분돼 있는가
- 실험 결과를 보기 전에 검색기, budget, prompt, metrics를 lock할 계획이 있는가
- 모든 비교군이 같은 S1/검색/S3/예산 조건을 공유하는가
- ABSTAIN과 실행 오류를 별도로 기록하는가

이 문서를 변경할 때는 문서 상단의 `version`, `status`, `last_updated`와 변경 기록을 함께 갱신한다.

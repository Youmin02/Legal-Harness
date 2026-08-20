# KoBLEX ParSeR (Reproduced) 226문항 베이스라인 보고서

- 작성일: 2026-08-19 (UTC)
- 목적: 사용자 자신의 스킬 하네스 방법을 배제하고, KoBLEX 논문(EMNLP 2025)이
  직접 제안한 방법 ParSeR(Parametric provision-guided Selection Retrieval)을
  Qwen3.8로 그대로 재현하여 226문항 전체에서 실행한 결과를 정리한다. 논문용
  베이스라인 확보가 목적이며, 사용자의 제안 방법(S1/S2/S3 스킬 하네스)은 이
  실행에 전혀 관여하지 않는다.
- 모델: Qwen3.8 (`legal-harness-qwen38-q8`, Ollama, Q8_0, temperature=0)
- 소스 커밋: `1b3d615`(최초 구현) → `3f5381c`(rerank 질의 버그 수정) →
  `ccea6ad`(검색 funnel 평가기 추가) → `d78ed0c`(226문항 결과 기록)
- 결과 batch: [`koblex-parser-reproduced-qwen38-q8-226-23f5c9ae-45a5-4d7e-a88f-fbcfb5320185`](../baselines/koblex-parser-reproduced-qwen38-q8-226-23f5c9ae-45a5-4d7e-a88f-fbcfb5320185/)
- 평가 산출물: [`records/evaluations/koblex-parser-reproduced-qwen38-q8-226-20260819`](../evaluations/koblex-parser-reproduced-qwen38-q8-226-20260819/)
- 상세 재현 노트: [docs/KOBLEX_PARSER_BASELINE_REPRODUCTION_NOTES.md](../../docs/KOBLEX_PARSER_BASELINE_REPRODUCTION_NOTES.md)
- 상세 결과 문서: [docs/KOBLEX_PARSER_BASELINE_RESULTS_226_20260819.md](../../docs/KOBLEX_PARSER_BASELINE_RESULTS_226_20260819.md)

## 1. 핵심 결론

1. KoBLEX 공식 GitHub(`daehuikim/KoBLEX`)의 ParSeR 구현(프롬프트, `bm25s` 검색,
   `dragonkue/bge-reranker-v2-m3-ko` reranker, LLM selection, QA 생성)을 원문
   그대로 포팅해 `baselines/koblex_parser/`에 독립 구현했다. 기존 `skills/`,
   `harness/`, `runtime/`와 import 의존성이 전혀 없다.
2. 공식 코드에서 실제 버그 하나를 발견했다: `selection_retrieval.py`가 한
   문항의 모든 파라메트릭 조문 선택을 항상 **첫 번째 조문의 후보군**에서만
   뽑는 인덱싱 오류(`contexts_list[0][choice]`). 사용자 확인 후 논문 서술대로
   "조문마다 자기 자신의 top-10에서 선택"하도록 고쳤다 — 이 재현은
   **"ParSeR (Reproduced)"**로 표기하며 "Official"이라 부르지 않는다.
3. 226문항 전체 실행 중 별도로, CrossEncoder rerank 질의에 원 질문이 아니라
   파라메트릭 조문을 잘못 넣고 있던 두 번째 구현 오류를 35/226 시점에 발견해
   즉시 중단·수정·재실행했다(§3 연대기). 틀린 부분 실행 결과는 삭제하지 않고
   `INVALID_RUN_NOTE.md`와 함께 보존했다.
4. 수정된 설정으로 226문항 전체를 완주했다: **220/226 정상 답변(97.35%)**,
   6건은 Qwen3.8이 stage1에서 반복 루프에 빠져 리스트를 못 닫은 실행 실패
   (재시도 없음, 공식 코드와 동일 정책).
5. 226문항 전체 Token-F1은 answered-only 0.436, end-to-end(실패=0점) 0.424다.
   Retrieval F1은 0.535 / 0.521, EM(조문 집합 완전 일치)은 26.4%다.
6. hop이 늘수록 검색 성능이 뚜렷이 저하된다(retrieval F1: 1-hop 0.670 →
   2-hop 0.507 → 3-hop 0.431).
7. 검색 단계별 gold 손실 분해 결과, gold 조문의 **32.2%가 BM25 top-100에도
   들어오지 못한다** — 가장 큰 손실 지점이다. 이후 rerank top-10 절단에서
   7.0%p, LLM 최종 선택에서 추가 8.4%p가 더 빠진다.
8. 사용자 하네스(Qwen3.8/B1a)가 이미 실행한 동일 21문항으로 ParSeR을 부분
   집계하면 ParSeR은 21/21 답변(F1 0.3387)이고, 하네스는 4/21 답변
   (answered-only F1 0.4733, end-to-end F1 0.0902)이다. **ABSTAIN이 없는
   ParSeR과 직접 우열을 비교하면 안 된다** — §5 참고.
9. 공식 GPT-4o LF-Eval은 비용·API 키 사전 승인이 없어 실행하지 않았다.

## 2. 재현 범위와 의도적 수정

| 구성 요소 | 재현 방식 |
|---|---|
| 프롬프트 3종(parametric provision / selection / QA) | 원문 그대로(in-context 예시 포함, 한 글자도 수정 안 함) |
| 1차 검색 | `bm25s` 라이브러리, `stopwords="en"`, corpus=`hierarchy+content` — 공식과 동일. 하네스 자체 BM25(FTS5 SQLite)는 사용 안 함 |
| Reranker | `dragonkue/bge-reranker-v2-m3-ko`, CrossEncoder+Sigmoid, batch_size=50 — 공식과 동일 |
| 하이퍼파라미터 | BM25 top-100/조문, rerank 상위 10개 LLM에 제시, temperature=0, `enable_thinking=False` — 공식과 동일 |
| `contexts_list[0][choice]` 인덱싱 버그 | **의도적으로 수정** — 논문 서술("LLM identifies single most relevant provision **per parametric provision**")대로 각 조문이 자기 top-10에서 선택되게 함 |
| CrossEncoder rerank 질의 | 최초 구현 오류(파라메트릭 조문 사용)를 발견해 원 질문으로 수정 — 공식 코드와 일치시킴(수정이 아니라 정정) |
| `escape_quotes()` 이중 이스케이프 | 생략(파싱 문자열을 그대로 두고 `json.dumps`에서 한 번만 이스케이프) — 알고리즘 본질에 영향 없음 |
| 공식 GPT-4o LF-Eval | 미실행(비용 사전 승인 필요) |

## 3. 연대기

| 시점 | 사건 | 조치 |
|---|---|---|
| 07:26 | 최초 226문항 배치 시작(rerank 질의에 파라메트릭 조문 사용) | — |
| 07:44 | 35/226 시점, GPT 리뷰로 rerank 질의 오류 지적받고 공식 코드 재대조로 확인 | tmux 세션 즉시 종료 |
| 07:48 | `pipeline.py` 수정: rerank 질의를 원 질문으로 교체, `bm25_top_k_texts` 트레이스 추가 | 스모크 재검증(1-hop 결과가 실제로 달라짐 확인), 테스트 56개 통과 |
| 07:49 | 소스 커밋(`3f5381c`) + 틀린 부분 실행 결과 보존 커밋(`ddc5247`) | push, `origin/main...main = 0 0` |
| 07:53 | 수정된 설정으로 226문항 재실행 시작(batch `23f5c9ae-...`) | tmux `koblex-parser-226` |
| 08:xx | 사용자 요청으로 recall@100→@10→@1 funnel 분석을 평가기에 추가 | 커밋 `ccea6ad`, 스모크 데이터로 검증 |
| 10:05 | 226/226 완료(6건 실행 실패, 전부 stage1 반복 루프) | 평가 실행, 결과·문서 커밋(`d78ed0c`), push |

## 4. 226문항 전체 결과

### 4.1 실행

| 항목 | 값 |
|---|---:|
| 총 문항 | 226 |
| 정상 답변 | 220 (97.35%) |
| 실행 실패 | 6 (2.65%) — 전부 `STAGE1_EMPTY_PARAMETRIC_PROVISIONS` |
| 총 wall time | 7,924.5초 (약 2시간 12분) |
| 순수 생성 시간 합 | 6,650.7초 (약 1시간 51분) |
| 평균/중앙값 지연시간 | 30.2초 / 27.8초 |

실행 실패 6건(`qa_130_2hop_501_rand`, `qa_291_2hop_1111_rand`, `qa_584_2hop_884`,
`qa_85_2hop_333_rand`, `qa_73_3hop_113`, `qa_136_2hop_523_rand`)은 전부 2/3-hop
문항이며, temperature=0 greedy decoding에서 Qwen3.8이 조문 번호나 친족 관계
표현을 수백 회 반복하며 `max_tokens=4000` 안에 JSON 리스트를 닫지 못한 경우다
(`records/baselines/.../stage_trace.jsonl`의 `stage1_raw_text`로 확인). 공식
코드에 재시도가 없으므로 재시도를 추가하지 않았다.

### 4.2 지표

| 지표 | Answered-only (n=220) | End-to-end (n=226, 실패=0점) |
|---|---:|---:|
| Token-F1 | 0.436 | 0.424 |
| Retrieval F1 | 0.535 | 0.521 |

Retrieval Precision 0.588 / Recall 0.524 / EM 0.264.

### 4.3 hop별

| hop | n | Token-F1 | Retrieval F1 | Retrieval Recall | 평균 지연 |
|---|---:|---:|---:|---:|---:|
| 1-hop | 57 | 0.432 | 0.670 | 0.711 | 22.1s |
| 2-hop | 122 | 0.472 | 0.507 | 0.477 | 30.9s |
| 3-hop | 41 | 0.334 | 0.431 | 0.407 | 39.4s |

### 4.4 검색 단계별 gold 손실 분해 (retrieval funnel)

같은 문항의 모든 파라메트릭 조문(서브쿼리)에 걸쳐 합집합으로 계산.

| 단계 | gold 조문 recall |
|---|---:|
| BM25 top-100 | 67.8% |
| BGE rerank top-10 | 60.8% |
| 최종 선택 | 52.4% |

가장 큰 손실은 BM25 단계(32.2%p)다 — `bm25s` 영어 stopword 토크나이즈를
한국어 텍스트에 그대로 적용하는 방식과 파라메트릭 조문을 질의로 쓰는 구조의
한계로 보인다. rerank 절단(100→10)에서 7.0%p, LLM 최종 선택에서 추가로
8.4%p가 더 빠진다.

## 5. 사용자 하네스(Qwen3.8/B1a)와의 21문항 직접 비교

같은 21문항(`data/koblex/manifests/bm25_bge_per_request_b1a_qwen38_q8_21_20260818.json`),
같은 Qwen3.8 모델. ParSeR 쪽은 이번 226문항 실행의 부분집합이며 별도 재실행하지
않았다.

| | 하네스 (Qwen3.8/B1a, `b000f10`) | ParSeR (Reproduced) |
|---|---:|---:|
| Answer rate | 4/21 (19.0%) | 21/21 (100%) |
| Token-F1 (answered-only) | 0.4733 (n=4) | 0.3387 (n=21) |
| Token-F1 (end-to-end) | 0.0902 | 0.3387 (실패 0건) |
| 평균 지연시간 | 328.72초 | 226문항 전체 평균 30.2초 (21문항만 별도 재계산 안 함) |

**해석 시 주의**:

- ParSeR은 ABSTAIN 메커니즘이 없고 "거부하지 말라"고 프롬프트에 명시되어
  있어 항상 답을 낸다. end-to-end와 answered-only Token-F1이 같아지는 것은
  품질이 아니라 "항상 제출하기 때문"이다.
- 하네스가 실제로 ANSWER한 4문항(`qa_92`, `qa_197`, `qa_211`, `qa_83`)은 모두
  gold 조문·결론이 100% 정확했다. 같은 4문항에서 ParSeR의 retrieval F1은
  1.0 / 1.0 / 0.667 / 0.667 — 하네스가 자신 있게 답한 문항에서는 ParSeR도
  비교적 강하지만 완전히 같지는 않다.
- 두 파이프라인의 BM25 구현이 다르다(ParSeR: `bm25s`, 하네스: FTS5 SQLite).
  검색 성능 차이의 일부는 방법론 효과가 아니라 검색기 구현 차이일 수 있다.
- 21문항은 하네스 쪽에서 정책 튜닝에 쓰인 개발셋이다. ParSeR 226문항 전체
  결과(§4)는 held-out 성격이지만, 이 21문항 비교 자체는 개발셋 기준이다.

## 6. 남은 선택지

1. `contexts_list[0]` 버그를 보존한 "ParSeR-Official" 조건 병렬 실행 (미실행,
   사용자 결정: 필요시 나중에)
2. 공식 GPT-4o LF-Eval (비용 사전 승인 필요, 미실행)
3. 사용자 하네스 226문항 본실험 — 21문항 Answer Coverage가 19%로 아직 pilot
   gate를 통과하지 못해 시작하지 않음(`docs/HANDOFF_TO_CLAUDE_CODE_20260819.md` §9)

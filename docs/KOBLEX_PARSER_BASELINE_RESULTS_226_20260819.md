# ParSeR (Reproduced) — KoBLEX 226문항 전체 결과

작성일: 2026-08-19 UTC

- 코드: `baselines/koblex_parser/` (재현 방식·수정 사항은
  `docs/KOBLEX_PARSER_BASELINE_REPRODUCTION_NOTES.md` 참조)
- 모델: Qwen3.8 (`legal-harness-qwen38-q8`, Ollama, Q8_0)
- batch: `records/baselines/koblex-parser-reproduced-qwen38-q8-226-23f5c9ae-45a5-4d7e-a88f-fbcfb5320185`
- 평가: `records/evaluations/koblex-parser-reproduced-qwen38-q8-226-20260819`
- 실행 커밋: `ccea6ad` (레포지션 rerank 질의 수정 + funnel 평가기 포함)
- 이전에 잘못된 rerank 질의로 35/226까지 실행하다 중단한 배치는
  `records/baselines/koblex-parser-baseline-qwen38-q8-226-f3e8ee44-4983-49bf-a2fa-55328e764c35/INVALID_RUN_NOTE.md`
  로 보존되어 있으며 본 결과에는 포함되지 않는다.

## 1. 실행 개요

| 항목 | 값 |
|---|---:|
| 총 문항 | 226 |
| 실행 실패(error) | 6 (2.65%) — 전부 `STAGE1_EMPTY_PARAMETRIC_PROVISIONS` |
| 정상 답변(scored) | 220 (97.35%) |
| 총 wall time | 7,924.5초 (약 2시간 12분, 인덱스/모델 로딩 포함) |
| 순수 생성 시간 합 | 6,650.7초 (약 1시간 51분) |
| 평균 지연시간 | 30.2초/문항 (중앙값 27.8초) |

**6건의 실행 실패 원인**: temperature=0 greedy decoding에서 Qwen3.8이 stage1
파라메트릭 조문 생성 중 반복 루프(예: "제1조제1항에 따른 확인의 청구, 제2조..."를
1조부터 300여 조까지 순차 반복, 또는 "...의 배우자의 직계혈족..."을 무한 반복)에
빠져 `max_tokens=4000` 안에 JSON 리스트를 닫지 못한 경우다. 공식 ParSeR 코드에는
재시도 로직이 없으므로 재시도를 추가하지 않고 그대로 실패로 기록했다
(question_id: `qa_130_2hop_501_rand`, `qa_291_2hop_1111_rand`, `qa_584_2hop_884`,
`qa_85_2hop_333_rand`, `qa_73_3hop_113`, `qa_136_2hop_523_rand` — 전부 2/3-hop).

## 2. 226문항 전체 지표

| 지표 | 값 |
|---|---:|
| Answer rate | 97.35% (6건은 실행 실패, ABSTAIN 아님) |
| Token-F1 (answered-only, n=220) | **0.436** |
| Token-F1 (end-to-end, 실패=0점, n=226) | **0.424** |
| Retrieval Precision | 0.588 |
| Retrieval Recall | 0.524 |
| Retrieval F1 (answered-only) | 0.535 |
| Retrieval F1 (end-to-end) | 0.521 |
| Retrieval EM (조문 집합 완전 일치) | 0.264 |

### Hop별

| hop | n | Token-F1 | Retrieval F1 | Retrieval Recall | 평균 지연 |
|---|---:|---:|---:|---:|---:|
| 1-hop | 57 | 0.432 | 0.670 | 0.711 | 22.1s |
| 2-hop | 122 | 0.472 | 0.507 | 0.477 | 30.9s |
| 3-hop | 41 | 0.334 | 0.431 | 0.407 | 39.4s |

### 검색 단계별 gold 조문 손실 분해 (retrieval funnel)

같은 문항의 모든 파라메트릭 조문(서브쿼리)에 걸쳐 합집합으로 계산.

| 단계 | gold 조문 recall |
|---|---:|
| BM25 top-100 (서브쿼리 합집합) | 67.8% |
| BGE rerank top-10 (서브쿼리 합집합) | 60.8% |
| 최종 선택(LLM이 실제로 고른 조문) | 52.4% |

해석: gold 조문의 약 **32.2%는 BM25 top-100에 아예 들어오지 못함** (bm25s 영어
stopword 토크나이즈 + 파라메트릭 조문을 질의로 쓰는 방식의 한계로 보인다).
BM25→rerank에서 추가로 7.0%p 손실(100→10 절단), rerank→최종 선택에서 추가로
8.4%p 손실(reranker가 올려놓은 후보 중 LLM이 다른 것을 고르거나, 한 문항에
gold가 여러 개인데 서브쿼리/선택은 1개씩만 나오는 구조적 특성 포함).

공식 LF-Eval(GPT-4o G-Eval)은 비용·API 키 사전 승인 없이 실행하지 않았다.

## 3. 사용자 하네스(Qwen3.8/B1a) 21문항 개발셋과의 직접 비교

같은 21문항(`data/koblex/manifests/bm25_bge_per_request_b1a_qwen38_q8_21_20260818.json`),
같은 Qwen3.8 alias로 ParSeR(Reproduced) 결과만 따로 뽑았다. **동일 226문항 실행의
부분집합이며 재실행하지 않았다** — 같은 모델/데이터에서 방법론만 다른 직접 비교.

| | 사용자 하네스 (Qwen3.8/B1a, `b000f10`) | ParSeR (Reproduced) |
|---|---:|---:|
| ANSWER / Answer rate | 4/21 (19.0%) | 21/21 (100%, 에러 0) |
| ABSTAIN | 17/21 (81.0%) | 없음 (알고리즘 자체에 ABSTAIN 없음) |
| Token-F1 (answered-only) | 0.4733 (n=4) | 0.3387 (n=21) |
| Token-F1 (end-to-end, 미답변=0) | 0.0902 | 0.3387 (동일 — 실패 0건) |
| 평균 지연시간 | 328.72초 | 약 30초대 (21문항 개별 재계산 안 함, 226 전체 평균 사용) |

**주의 — 이 표를 우열 판정에 그대로 쓰지 말 것** (`docs/KOBLEX_PARSER_BASELINE_REPRODUCTION_NOTES.md`,
`docs/HANDOFF_TO_CLAUDE_CODE_20260819.md` §11 원칙과 동일):

- ParSeR은 ABSTAIN이 없어 **항상 답을 낸다** — end-to-end Token-F1이 answered-only와
  같아지는 것은 "정답을 더 잘 맞혀서"가 아니라 "틀려도 항상 제출하기 때문"이다.
  사용자 하네스는 근거 불충분 시 명시적으로 보류하므로 두 수치를 직접 비교하면
  하네스가 불리하게 보인다.
- 사용자 하네스가 ANSWER한 4문항(`qa_92`, `qa_197`, `qa_211`, `qa_83`)은 모두
  gold 조문과 결론이 100% 정확했다(§7 참조). ParSeR의 같은 4문항 retrieval F1은
  `qa_92`=1.0, `qa_197`=1.0, `qa_211`=0.667, `qa_83`=0.667로, 하네스가 답한
  문항에서는 ParSeR도 비교적 강하지만 완전히 같지는 않다 — "쉬운 문항에서는 둘 다
  잘한다"는 정도로만 해석한다.
- 두 파이프라인의 BM25 구현이 다르다(ParSeR: `bm25s` 영어 stopword 토크나이즈,
  하네스: `retrieval/persistent.py` FTS5 SQLite) — 검색 성능 차이의 일부는
  하네스 효과가 아니라 검색기 구현 차이일 수 있다.
- 21문항은 개발셋이며 held-out 226 본실험과 다른 지위다(§5). 위 표의 "21문항
  기준 ParSeR" 행은 어차피 이번 226 전체 실행의 부분집합이라 held-out 훼손은
  없지만, 하네스 쪽 4/21 결과는 정책 튜닝에 쓰인 개발셋 성능이라는 점은 유지된다.

## 4. 다음 단계 제안

1. 226문항 전체에서 사용자 하네스를 아직 실행하지 않았으므로, 이 표는 226 대
   226 비교가 아니라 21 대 21(부분) + 226(ParSeR 단독) 비교다. 완전한 비교는
   하네스도 226 본실험을 마쳐야 가능하다(`docs/EXPERIMENT_PROTOCOL.md`,
   §P6 — 21문항 pilot gate 통과 후).
2. `contexts_list[0]` 버그를 보존한 ParSeR-Official 조건은 아직 실행하지
   않았다(사용자 결정: 나중에 필요하면 추가).
3. 공식 GPT-4o LF-Eval은 비용 사전 승인 후 별도로 실행 결정.

# Legal Harness ABSTAIN 감소 및 BM25–KURE-v1 비교 구현 계획서

## 1. 문서 목적

이 문서는 다른 코딩 에이전트가 그대로 작업 지시로 사용할 수 있는 구현 계획서다. 목표는 현재 21문항 개발 파일럿에서 발생한 높은 `ABSTAIN`의 원인을 단계별로 줄이고, `BM25+BGE`와 `KURE-v1+BGE` 중 어떤 검색 구성이 더 적합한지 통제된 조건에서 비교하는 것이다.

이 문서는 **계획**이며 아직 구현 또는 성능 개선이 완료되었다는 뜻이 아니다.

기준 저장소와 결과:

- 저장소: `Youmin02/Legal-Harness`
- 기준 브랜치: `main`
- 기준 Git SHA: `092286f8f418c984ec73cb974db59beb2abc995d`
- 개발 데이터: 현재 반복 사용한 21문항
- 최종 평가 후보: 위 21문항을 제외한 205문항
- 현재 21문항 결과: `ANSWER 6`, `ABSTAIN 13`, `EXECUTION_FAILURE 2`

## 2. 최상위 작업 지시

아래 단계를 순서대로 수행하라.

1. 기존 결과와 완료된 실행 기록을 수정하거나 덮어쓰지 않는다.
2. 행동을 바꾸기 전에 평가 및 후보 provenance를 먼저 보강한다.
3. 21문항만 개발·ablation에 사용한다.
4. 한 조건에서 여러 원인을 동시에 변경하지 않는다.
5. `ABSTAIN` 비율만으로 개선을 판정하지 않는다.
6. 검색·planning 수정 전에 전역 evidence gate를 완화하지 않는다.
7. 설정을 고정하기 전에는 남은 205문항을 실행하지 않는다.
8. 각 단계가 끝날 때 테스트와 개발셋 지표를 제출하고 다음 단계 진행 여부를 판단한다.

## 3. 현재 확인된 문제

### 3.1 결과 및 검색 손실

- 전체 gold context 40개는 코퍼스에 모두 존재한다.
- BM25 Top-100에는 34개가 남았다.
- RRF Top-100에는 30개가 남았다.
- BGE 최종 Top-10에는 19개만 남았다.
- `ABSTAIN` 13건 중 12건은 최종 후보에 문항별 gold evidence가 완전하게 남지 않았다.
- `ABSTAIN` 13건 중 11건은 retrieval request 예산을 1~3회 남긴 채 3라운드 상한에 도달했다.
- 3-hop 4문항은 모두 `ABSTAIN`이었다.

### 3.2 코드 수준 원인 가설

1. `retrieval/pipeline.py`가 요청을 `issue_id` 단위로 합쳐 서로 다른 evidence item이 하나의 Top-K 안에서 경쟁한다.
2. 같은 issue의 여러 `query_text`를 하나의 긴 문자열로 연결해 BGE에 전달한다.
3. 각 `query_text`에 원문 맥락이 붙어 있어 BGE 입력에 같은 맥락이 반복될 수 있다.
4. BGE 문서 입력이 `provision_text`뿐이라 법령명·조문 제목 정보가 약하다.
5. `CandidateProvision.source_request_id`가 RRF의 여러 출처 중 첫 번째 ID만 보존한다.
6. `fusion_rank` 필드에 실제 BGE rerank 순위가 저장되어 RRF 순위와 BGE 순위를 구분할 수 없다.
7. 새 조문 ID가 하나라도 생기면 critical evidence 개선과 무관하게 retrieval progress로 계산된다.
8. S1이 불필요하거나 중복된 critical evidence item을 만들면 이후 단계에서 이를 제거하거나 재분류할 수 없다.
9. S3가 citation ID, marker, claim substring 같은 전송 형식까지 직접 생성해 형식 실패가 발생한다.
10. 현재 citation integrity는 ID·accepted set·원문 snapshot을 확인하지만 법적 적용의 타당성이나 answer entailment를 검증하지 않는다.

## 4. 연구 및 구현 경계

### 반드시 유지할 것

- 동일한 질문, 코퍼스, LLM, S1/S2/S3 역할 분리
- 동일한 BGE reranker 모델
- 동일한 seed와 실행 순서
- 동일 조건에서는 동일한 retrieval budget과 candidate budget
- 하네스가 `RETRIEVE_GAP`·`GENERATE`·`ABSTAIN`·retry·budget·stop을 소유하는 구조
- 완료된 `records/runs/<uuid>/`의 불변성

### 이번 계획에서 하지 않을 것

- 전역 gate 완화
- forced answer를 주 설정으로 채택
- 처음부터 BM25+KURE hybrid를 주 설정으로 채택
- 21문항 결과를 KoBLEX 공식 점수라고 표현
- 개발 결과를 확인적 성능 증거로 사용
- held-out 205문항을 이용한 반복 튜닝
- GraphRAG·판례 결합·fine-tuning을 동시에 추가

## 5. Phase 0 — 기준선 고정 및 평가 코드 추가

### 목적

행동을 바꾸기 전에 현재 상태를 재현하고 이후 변경 효과를 동일한 방식으로 측정한다.

### 구현 지시

다음 파일을 추가하거나 보강한다.

- 신규: `scripts/evaluate_dev_runs.py`
- 보강: `runtime/experiment_record.py`
- 보강: `scripts/run_bm25_bge_pilot_batch.py` 또는 retriever 공통 이름의 신규 batch runner
- 신규 테스트: `tests/test_evaluation_metrics.py`

평가 스크립트는 최소한 다음 지표를 출력해야 한다.

- outcome count와 비율: `ANSWER`, `ABSTAIN`, `EXECUTION_FAILURE`
- gold provision precision·recall·F1
- BM25/KURE first-stage Recall@100
- RRF Recall@100
- BGE Recall@10·20·30
- 문항별 complete-evidence recall
- supported-answer yield
- false-supported answer count/rate
- citation integrity pass rate
- hop별 결과
- retrieval round·request·candidate 수
- latency median·p95

출력 형식:

- 기계 판독용 JSON
- 문항 단위 CSV
- 사람 검토용 Markdown 요약

### provenance 수정

다음 필드를 구분해서 기록한다.

- `source_request_ids[]`
- `target_evidence_item_ids[]`
- `first_stage_rank`
- `fusion_rank`
- `rerank_rank`
- `candidate_stage`
- `selection_reason`

관련 파일:

- `harness/contracts.py`
- `retrieval/types.py`
- `retrieval/rrf.py`
- `retrieval/pipeline.py`
- `harness/validation.py`
- `runtime/experiment_record.py`

기존 `source_request_id`는 호환성을 위해 즉시 제거하지 말고, migration 기간에는 primary source로 유지할 수 있다. 새로운 분석은 반드시 `source_request_ids[]`를 기준으로 한다.

### 완료 조건

- 기존 행동 조건으로 21문항 집계가 현재 결과와 일치한다.
- RRF 순위와 BGE 순위를 별도로 재구성할 수 있다.
- 어떤 candidate가 어느 request/evidence item에서 왔는지 추적 가능하다.
- 기존 단위 테스트와 신규 평가 테스트가 모두 통과한다.

## 6. Phase 1 — BGE 입력과 evidence-balanced 후보 선택

### 목적

BM25/KURE가 찾은 근거가 BGE와 전역 Top-K에서 탈락하는 문제를 줄인다.

### 수정 파일

- `retrieval/pipeline.py`
- `retrieval/reranker.py`
- `retrieval/types.py`
- `harness/contracts.py`
- `scripts/run_local_harness.py`
- `scripts/run_bm25_bge_pilot_batch.py`
- `tests/test_retrieval_algorithms.py`

### 필수 설정 추가

기존 조건을 재현할 수 있도록 기본값 또는 명시적 baseline mode를 유지하면서 다음 설정을 추가한다.

```text
rerank_query_mode = combined_issue | per_request
candidate_selection = global_top_k | evidence_balanced
per_evidence_min_k = integer
final_top_k = 10 | 20 | 30
rerank_document_mode = body_only | statute_and_body
```

### BGE 문서 입력

`statute_and_body` 조건에서는 다음과 같이 입력한다.

```python
document_text = f"{hit.document.statute_name}\n{hit.document.provision_text}"
```

### 권장 재정렬 구조

```text
request별 first-stage Top-100
→ request별 BGE 점수화
→ evidence_item별 rank fusion
→ critical evidence마다 최소 후보 수 보장
→ provision_id 중복 제거
→ rank 기반 전역 후보 보충
→ 최종 candidate budget 적용
```

서로 다른 query에서 나온 raw BGE score를 직접 비교하지 않는다. query별 순위를 RRF 또는 명시적인 rank-normalization으로 결합한다.

### evidence-balanced 선택 규칙

1. 모든 critical evidence item에 우선 quota를 배정한다.
2. 각 critical item에서 `per_evidence_min_k`개까지 선택한다.
3. 같은 provision이 여러 evidence item에 해당하면 하나만 보존하되 모든 source/evidence provenance를 유지한다.
4. 남은 candidate budget은 rank-fusion 점수로 채운다.
5. 최종 후보가 `final_top_k`를 초과하지 않게 한다.

### 필수 테스트

- 같은 issue에 E1·E2가 있을 때 두 evidence item 모두 최소 후보를 확보한다.
- 여러 request에서 검색된 동일 provision이 모든 `source_request_ids`를 보존한다.
- `statute_and_body` 모드에서 법령명이 reranker 입력에 포함된다.
- `body_only` baseline이 기존 결과를 재현한다.
- 반복 원문 맥락이 하나의 BGE query에 여러 번 중복되지 않는다.
- raw BGE score를 서로 다른 query 사이에서 직접 비교하지 않는다.
- `final_top_k`와 per-evidence quota 경계값을 검증한다.

### 완료 조건

- baseline mode가 기존 결과와 호환된다.
- 신규 mode에서 21문항의 BGE 이후 gold recall과 complete-evidence recall을 산출한다.
- `ABSTAIN`이 줄더라도 false-supported answer가 증가하면 자동 성공으로 판정하지 않는다.

## 7. Phase 2 — BM25와 KURE-v1 통제 비교

### 예상

- **KURE-v1**: 자연어 질문과 법조문 표현이 다를 때 Top-100 의미 기반 recall이 높을 가능성이 있다.
- **BM25**: 정확한 법령명, 조문 번호, 고유 법률 용어, 속도와 재현성에서 유리할 가능성이 있다.
- **예상 최종 판단**: KURE가 first-stage recall에서 우세할 수 있으나, KoBLEX 최종 답변 품질·속도·재현성까지 고려하면 BM25+BGE가 주 설정으로 남을 가능성이 높다.
- 어느 retriever도 벌칙·미수·준용 관계를 명시적으로 따라가지 않으므로 교차참조 누락은 별도 문제다.

이 예상은 실험 결과가 아니며, 아래 통제 비교로 검증한다.

### 기존 구현 활용

저장소에는 이미 다음 경로가 존재한다.

- `scripts/run_local_harness.py --retriever bm25|kure`
- `retrieval.persistent.SqliteFts5Bm25Searcher`
- `retrieval.persistent.KureExactIndexSearcher`
- `scripts/build_kure_exact_index.py`

새 retriever를 구현하지 말고 인덱스·manifest·평가 경로를 검증한다.

### 비교 조건

| 조건 | First-stage retriever | BGE query | 후보 선택 | 최종 K |
| --- | --- | --- | --- | ---: |
| B0 | BM25 | 현재 issue 결합 | global | 10 |
| K0 | KURE-v1 | 현재 issue 결합 | global | 10 |
| B1 | BM25 | per-request | evidence-balanced | 20 |
| K1 | KURE-v1 | per-request | evidence-balanced | 20 |

필요하면 `final_top_k=10/20/30`을 추가 ablation으로 실행하되, Top-K 이외의 설정은 고정한다.

### retriever만 비교하는 방법

LLM이 생성한 S1 query 차이가 retriever 비교에 섞이지 않도록 retrieval-only 비교에서는 동일한 validated S1 plan과 retrieval requests를 replay한다.

1. 기준 실행에서 21문항의 validated S1 output을 불변 아티팩트로 저장한다.
2. 같은 request를 BM25와 KURE에 각각 전달한다.
3. first-stage Recall@100과 complete-evidence Recall@100을 비교한다.
4. 그 다음 동일한 BGE와 candidate selection을 적용한다.

### end-to-end 비교

- 질문 ID, 순서, seed, 모델, skill hash, budget, BGE 모델을 동일하게 한다.
- retriever만 `bm25`와 `kure`로 변경한다.
- 가능한 경우 문항·조건별 3회 반복을 사용하고 문항 내 평균 후 비교한다.
- small-n 개발 결과는 방향성 판단에만 사용한다.

### 승자 결정 규칙

다음 순서로 판단한다.

1. false-supported answer가 악화되지 않는가
2. complete-evidence Recall@100이 높은가
3. BGE 이후 complete-evidence Recall@K가 높은가
4. supported-answer yield가 높은가
5. 정답 품질 지표가 높은가
6. latency·GPU 비용이 감당 가능한가

`ABSTAIN` 비율이 낮다는 이유만으로 승자로 선택하지 않는다.

### hybrid 추가 조건

BM25와 KURE가 서로 다른 gold context 또는 서로 다른 complete-evidence 문항을 실제로 복구하는 것이 확인될 때만 `BM25+KURE RRF+BGE`를 별도 ablation으로 추가한다. Hybrid 결과를 BM25 또는 KURE 단독 효과로 해석하지 않는다.

### 완료 조건

- 동일한 21문항·request·BGE 설정에서 BM25/KURE 비교표가 생성된다.
- 각 retriever만 복구한 gold 목록이 생성된다.
- first-stage 효과와 BGE/candidate-selection 효과가 분리된다.
- 모델·인덱스·corpus SHA와 설정이 실행 기록에 남는다.

## 8. Phase 3 — 조문 교차참조 확장

### 목적

어휘 검색이나 dense 유사도만으로 찾기 어려운 벌칙·미수·준용·인용 조문을 복구한다.

### 구현안

신규 모듈 후보:

- `retrieval/reference_expander.py`
- `scripts/build_statute_reference_index.py`

최소 관계:

- 같은 법령 내 `제○조` 인용
- 위반 조문 ↔ 벌칙 조문
- 본조 ↔ 미수범 조문
- 본조 ↔ 준용 조문
- 정의 조문 ↔ 적용 조문

초기 버전은 정규식 기반 1-hop 확장으로 제한한다. LLM이 참조 관계를 임의로 생성하지 않게 한다.

### 비교 조건

- `B1`: BM25+BGE evidence-balanced
- `B2`: B1 + deterministic reference expansion
- `K1`: KURE+BGE evidence-balanced
- `K2`: K1 + deterministic reference expansion

### 완료 조건

- 확장 전후 후보 provenance가 분리된다.
- reference expansion이 추가한 candidate 수와 gold 복구 수가 기록된다.
- 잘못된 대량 확장으로 candidate budget이 잠식되지 않는다.

## 9. Phase 4 — S1 critical evidence 과분해 방지

### 수정 파일

- `skills/legal_issue_and_query_planning/SKILL.md`
- `skills/legal_issue_and_query_planning/references/output.schema.json`
- `skills/legal_issue_and_query_planning/scripts/validate_output.py`
- `runtime/local_ollama_executor.py`
- `harness/contracts.py`
- `harness/validation.py`
- `tests/test_local_ollama_executor.py`
- `tests/test_policy_and_validation.py`

### schema 제안

critical evidence item에 다음 의미 필드를 추가한다.

```json
{
  "legal_conclusion_key": "손해배상책임_성립",
  "necessity_reason": "이 근거가 없으면 핵심 결론을 정당화할 수 없음"
}
```

### 검증 규칙

- 동일한 `legal_conclusion_key`를 의미상 같은 critical item으로 중복 생성하지 않는다.
- 하나의 governing provision이 통상 함께 충족하는 세부사항을 별도 critical item으로 나누지 않는다.
- 질문에 없는 시행령 세부사항이나 다른 법 영역을 자동으로 critical 처리하지 않는다.
- 고정 hop 수 또는 `critical item 최대 N개`를 일반 규칙으로 강제하지 않는다.

21문항에서 확인된 과분해·잘못된 법 영역 사례를 few-shot 반례로 추가하되, gold provision ID를 프롬프트에 노출하지 않는다.

### 완료 조건

- 기존 valid S1 출력과 schema migration이 명확하다.
- 중복 critical item에 대한 validator 테스트가 있다.
- 21문항에서 critical item 수, 중복률, complete-evidence 요구량 변화를 보고한다.

## 10. Phase 5 — progress 및 retrieval budget 의미 수정

### 수정 파일

- `harness/state_update.py`
- `harness/run_state.py`
- `harness/policy.py`
- `harness/runner.py`
- `scripts/run_local_harness.py`
- `tests/test_harness_paths.py`
- `tests/test_policy_and_validation.py`

### progress 정의

다음 중 하나가 발생할 때만 progress로 계산한다.

- critical coverage가 `uncovered → partially_covered/covered`로 개선
- critical coverage가 `partially_covered → covered`로 개선
- critical item에 새로운 accepted evidence link가 추가
- critical conflict가 실제로 해결

새 candidate provision ID가 생겼다는 사실만으로 progress로 계산하지 않는다.

### budget 권장안

```text
total_retrieval_requests = 실질 비용 예산
max_retrieval_rounds = 무한 반복 방지용 안전 상한
max_no_progress_rounds = 조기 종료 기준
max_requests_per_round = 한 라운드 폭 제한
```

요청 예산이 남고 progress가 있으면 3라운드를 넘어서도 안전 상한 내에서 계속할 수 있게 한다. 검색 개선 전에 이 단계만 단독 적용하지 않는다.

### 필수 테스트

- 관련 없는 새 provision은 no-progress를 초기화하지 않는다.
- 새로운 accepted critical link는 progress로 인정한다.
- request budget이 남았을 때 round budget만으로 즉시 종료되지 않는다.
- no-progress와 request exhaustion의 termination reason이 구분된다.
- 무한루프가 불가능하다.

## 11. Phase 6 — S3 전송 형식 결정론화

### 목적

내용이 아니라 citation ID·marker·substring 형식 때문에 발생한 실행 실패를 제거한다.

### 수정 파일

- `runtime/local_ollama_executor.py`
- `skills/grounded_legal_answer_generation/references/output.schema.json`
- `skills/grounded_legal_answer_generation/scripts/validate_output.py`
- `harness/contracts.py`
- `harness/validation.py`
- `tools/validate_citation_integrity.py`
- `tests/test_local_ollama_executor.py`
- `tests/test_harness_paths.py`

### 권장 구조

```text
LLM 출력: claim text + provision_ids + applicability + assumptions/limitations
하네스: claim_id 할당
하네스: citation_id 할당
하네스: [CTn] marker 삽입
하네스: 최종 answer 직렬화
검증기: accepted set·snapshot·claim-citation linkage 확인
```

법적 판단이나 적용 여부를 결정론적 포맷터가 변경해서는 안 된다. 포맷터는 ID·marker·배열 정렬·answer 조립만 소유한다.

### 완료 조건

- marker 누락·citation ID 불일치·claim substring 형식 때문에 실행 실패하지 않는다.
- 비허용 provision 인용은 계속 실패한다.
- 법적 적용 정확도 검증은 별도 평가 항목으로 남는다.

## 12. 실험 실행 순서

1. 기준 SHA와 완료된 21문항 결과를 보존한다.
2. Phase 0만 적용하고 baseline 재현 여부를 확인한다.
3. 1-hop·2-hop·3-hop 각 1문항으로 smoke test를 수행한다.
4. Phase 1 조건을 21문항에서 실행한다.
5. B0/K0로 retriever 자체 차이를 측정한다.
6. B1/K1로 evidence-balanced 효과와 retriever 차이를 측정한다.
7. 필요할 때만 Top-10/20/30 ablation을 수행한다.
8. Phase 3 교차참조 확장을 B2/K2로 비교한다.
9. Phase 4 S1 수정 전후를 별도 조건으로 비교한다.
10. Phase 5 budget 수정 전후를 별도 조건으로 비교한다.
11. Phase 6 S3 형식 실패를 검증한다.
12. 선택한 설정과 코드·모델·index·skill hash를 고정한다.
13. held-out manifest가 21개 개발 ID를 포함하지 않는지 검사한다.
14. 승인 후 남은 205문항을 한 번만 실행한다.

## 13. 테스트 명령과 검증

모든 코드 변경 뒤 최소한 다음을 실행한다.

```bash
python -m unittest discover -s tests
```

추가 검증:

- baseline configuration 재현
- condition manifest schema 검증
- corpus–BM25 index–KURE vector ID 정렬 검증
- 동일 질문·seed·skill hash 확인
- 결과 디렉터리 신규 생성 확인
- 완료된 run 디렉터리 비변경 확인
- summary row 수와 manifest entry 수 일치 확인

## 14. 필수 산출물

각 단계 또는 최종 PR은 다음을 포함해야 한다.

- 변경 코드와 단위 테스트
- condition manifest
- 실행 설정과 Git SHA
- 모델·skill·index hash
- 문항 단위 결과 CSV
- aggregate JSON
- 사람이 읽는 Markdown 결과 요약
- BM25/KURE unique gold recovery 목록
- regression·rescue·harm 사례 목록
- 남은 한계와 다음 단계 판단

## 15. 중단 및 보고 조건

다음 경우 실행을 중단하고 원인을 먼저 보고한다.

- KURE 모델·vector index·normalized corpus가 없거나 hash가 다름
- baseline mode가 기존 결과 구조를 재현하지 못함
- candidate provenance가 소실됨
- false-supported answer가 증가함
- 완료된 run 기록을 덮어쓸 위험이 있음
- 21문항 이외 held-out ID가 개발 실행에 포함됨
- retriever 이외 설정이 BM25/KURE 조건 사이에서 달라짐
- 실행 실패를 `ABSTAIN` 또는 오답으로 합산하려는 경우

중단 보고에는 `실패 단계`, `영향 범위`, `재현 명령`, `관련 로그`, `수정 제안`을 포함한다.

## 16. 최종 의사결정 형식

최종 보고서는 최소한 다음 표를 포함한다.

| 조건 | Recall@100 | Complete-evidence Recall@100 | BGE Recall@K | Supported-answer yield | False-supported | ABSTAIN | Failure | Median latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 |  |  |  |  |  |  |  |  |
| K0 |  |  |  |  |  |  |  |  |
| B1 |  |  |  |  |  |  |  |  |
| K1 |  |  |  |  |  |  |  |  |

최종 결론은 다음 중 하나로 명시한다.

- `BM25+BGE를 주 설정으로 고정`
- `KURE-v1+BGE를 주 설정으로 고정`
- `retriever 차이는 불명확하며 BM25를 재현성 기준으로 유지`
- `상호 보완성이 확인되어 hybrid를 별도 ablation으로 추가`

개발셋 결과만으로 KoBLEX 공식 성능 개선을 선언하지 않는다.

## 17. 참고 자료

- 저장소 실험 프로토콜: `docs/EXPERIMENT_PROTOCOL.md`
- 21문항 파일럿 이력: `records/reports/2026-08-18_BM25_BGE_21item_pilot_history.md`
- KURE-v1 모델 카드: <https://huggingface.co/nlpai-lab/KURE-v1>
- KoBLEX 논문: <https://openreview.net/pdf/d69d6d08c6498e3210771e293bce616610b1cb99.pdf>

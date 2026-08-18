# Legal Harness BM25+BGE 엔지니어링 파일럿 이력 보고서

- 작성일: 2026-08-18 (UTC)
- 대상: 최초 로컬 E2E 테스트부터 수정 과정 및 최종 21문항 재실행까지
- 모델: `DavidAU/Qwen3.6-27B-Fable-Fusion-711-Uncensored-Heretic-NM-DAU-NEO-MAX-MTP-GGUF`의 Q4_K_M 파일
- Ollama 별칭: `legal-harness-qwen`
- 최종 결과 기록 커밋: `d4143e2` (`record: add 21-item BM25+BGE factual-branch run`)

## 1. 이 문서에서 사용하는 결과 상태

- `ANSWER`: 하네스가 S3 답변과 인용 형식을 검증하고 답변을 반환한 상태이다. KoBLEX 정답과 일치한다는 뜻은 아니다.
- `ABSTAIN`: 하나 이상의 critical evidence가 충족되지 않아 정책이 답변을 보류한 상태이다.
- `EXECUTION_FAILURE`: 스킬 출력, 스키마, 인용 계약 또는 런타임 오류로 정상 종료하지 못한 상태이다.
- `NO_FINAL_RESULT`: 실행이 중단되거나 초기 배치 코드가 실패하여 `result.json`이 완성되지 않은 상태이다. 성능 통계에서 제외한다.

## 2. 핵심 결론

1. 최초 개발 사이클의 21개 고유 문항은 `ANSWER 2`, `ABSTAIN 17`, `EXECUTION_FAILURE 2`였다. 다만 이 값은 하나의 고정 조건으로 한 번에 실행한 배치가 아니라, `qa_19` 단일 스모크와 최초 pilot20의 유효 최종 시도를 합친 개발용 합성 결과이다.
2. 최초 pilot20과 동일한 20문항만 비교하면 답변 생성률은 `2/20(10.0%)`에서 `5/20(25.0%)`로 올랐다.
3. `qa_19`를 추가하여 하나의 고정 조건으로 다시 실행한 최종 21문항 결과는 `ANSWER 6`, `ABSTAIN 13`, `EXECUTION_FAILURE 2`였다. 답변 생성률은 `28.6%`이다.
4. 낮은 답변률의 주원인은 코퍼스 누락이 아니다. 최종 ABSTAIN 13건의 gold context 28개는 코퍼스에 모두 있었고, BM25 Top-100이 21개를 찾았지만 최종 BGE Top-10에는 8개만 남았다.
5. 전체 21문항의 gold context 40개를 기준으로 하면 `코퍼스 40 → BM25 Top-100 34 → RRF Top-100 30 → BGE Top-10 19`였다. 가장 큰 손실은 재정렬과 Top-10 절단 구간이다.
6. 최종 `ANSWER` 6건을 KoBLEX 정답과 육안으로 예비 대조한 결과 5건은 정답 요지와 대체로 일치했지만, `qa_19`는 gold의 상법 제814조·1년이 아니라 상법 제902조·2년을 제시했다. 따라서 `ANSWER 28.6%`를 정답률로 쓰면 안 된다.
7. 현재 21문항은 226문항 KoBLEX test 파일에서 가져와 반복 튜닝에 사용했다. 논문에서 엄밀한 held-out 평가를 주장하려면 이 21개를 개발 세트로 선언하고 나머지 205개를 주 평가 세트로 사용하는 것이 안전하다.

## 3. 데이터와 최종 실행 조건

### 3.1 데이터

- QA 파일: `data/koblex/qa/test-00000-of-00001.parquet`
- 로컬 확인 결과: 226행, 226개 고유 ID
- 실제 hop 분포: 1-hop 57, 2-hop 127, 3-hop 42
- 법령 코퍼스: 233,544개 문서
- 법령 코퍼스 SHA-256: `6323f7d024ec504f4b2346cd3ab67aa709aac49a5340c9f3d8372ad6bd5f9b8b`

주의: [기존 실험 프로토콜](../../docs/EXPERIMENT_PROTOCOL.md)은 1-hop 55, 2-hop 125, 3-hop 46으로 적혀 있어 현재 parquet의 실제 분포와 다르다. 최종 논문 실험 전에 프로토콜 수치를 수정해야 한다.

### 3.2 최종 21문항 조건

- Manifest: [bm25_bge_factualbranch_21_20260817.json](../../data/koblex/manifests/bm25_bge_factualbranch_21_20260817.json)
- 구성: 기존 pilot20 + 가장 먼저 별도로 시험한 `qa_19_1hop_28`
- hop 분포: 1-hop 6, 2-hop 11, 3-hop 4
- Git revision: `d1611e7`
- 입력: KoBLEX `background + question`; gold answer와 gold context는 추론 입력에서 제외
- 1차 검색: SQLite FTS5 BM25
- 재정렬: `dragonkue/bge-reranker-v2-m3-ko`
- BM25/RRF pool: 100
- 최종 후보: issue별 Top-10
- 검색 한도: 최대 3라운드, 총 9요청
- LLM 컨텍스트: 32,768
- seed: 0
- KURE: 이번 결과에는 사용하지 않음

최종 배치 메타데이터는 [metadata.json](../batches/bm25-bge-factualbranch-21-full-808c1fa5-a4e8-4f6c-8f45-5f303c3da33f/metadata.json), 결과 요약은 [summary.jsonl](../batches/bm25-bge-factualbranch-21-full-808c1fa5-a4e8-4f6c-8f45-5f303c3da33f/summary.jsonl)에 있다.

## 4. 최초 테스트부터 최종 재실행까지의 연대기

| 시점/단계 | 실행 또는 커밋 | 결과 | 확인된 문제 | 수정 내용 |
|---|---|---|---|---|
| 2026-08-15 06:08 | 최초 `qa_19` run `27e95f6e-...`, commit `01116ea` | `EXECUTION_FAILURE` | S2가 인용 원문을 정확히 복사하지 않았고, assessment/link ID 불일치 및 후보 밖 조문 사용 | `88a8f82`: 후보를 `C001` 형식으로 단축하고 `[FULL_TEXT]`를 하네스가 원문으로 치환하도록 변경 |
| 2026-08-15 06:30~06:36 | `b7900d42-...`, `d6ca49ea-...` | 두 번 모두 `EXECUTION_FAILURE` | S2 evidence ledger 중복/누락, S1의 잘못된 run/request ID와 중복 gap query | `d67d98c`: run/request ID와 gap 대상 및 과거 query 제약을 결정론적으로 정규화 |
| 2026-08-15 07:08 | `qa_19` run `8188334b-...` | `ABSTAIN` | 실행 계약 오류는 없어졌지만 3회 검색 후 critical evidence 부족 | 최초로 하네스 전체 경로가 정상 종료한 스모크로 기록 |
| 2026-08-15 07:25 | 최초 `qa_92` run `1e6abb54-...` | `EXECUTION_FAILURE` | unknown/resolved evidence target과 중복 gap query | `6717de9`: unresolved target 강제, issue/evidence 정합성 및 fallback query 보정 |
| 2026-08-15 08:08 | `qa_92` run `3c1b22ca-...` | `ANSWER` | 형법 제330조와 10년 이하 징역을 정상 생성 | 최초 안정적 정답 생성 사례 |
| 2026-08-15 08:40 | 최초 remaining-19 배치 | `NO_FINAL_RESULT 18`, `EXECUTION_FAILURE 1` | `_normalize_harness_owned_fields`가 staticmethod 상태에서 `self`를 참조했고, `qa_352`는 INITIAL_PLAN 중복 query 오류 | `83f1afc`: 인스턴스 메서드 복구 및 INITIAL_PLAN 중복 query fallback 추가 |
| 2026-08-15 12:48~13:34 | `qa_139` 별도 재시도 + remaining-18 재실행 | pilot20 유효 결과 `A2/AB16/F2` | ABSTAIN 80%, S2 duplicate `E2` 두 건, multi-hop 답변 1건뿐 | 이후 recall 및 스키마 개선 단계로 전환 |
| 2026-08-16 | `85e8ac7`, recallfix 스모크 | `qa_19 ANSWER`, `qa_92` 실행 중 중단 | question-only 입력 때문에 법률관계가 사라졌고, 조건부 답변이 실제 정답 대신 민법 제766조 제목에 의존 | BGE pool 100→Top-10, statute hint 채널, S2 정규화, monotonic coverage, 제한적 조건부 생성 추가 |
| 2026-08-17 06:27 | `cd13612`, contextfix `qa_19` | `ANSWER` | KoBLEX background 누락이 핵심 입력 버그였음 | 모든 benchmark 입력을 `background + question`으로 수정하고 partial 유형을 분리 |
| 2026-08-17 06:49~07:26 | `1659fe6`→`4e15091`→`44bfa72`→`349e7fd` | `qa_19`가 네 조건에서 모두 `ABSTAIN` | 한국어 조사/어미, 원문 맥락, 핵심어, 행위자 표현을 보강해도 안정적으로 gold를 유지하지 못함 | 한국어 prefix, statute hint 20% quota, 원문 context anchor, focus prefix, actor prefix 순차 추가 |
| 2026-08-17 12:07 | `9f01c5a` factual-branch smoke | `EXECUTION_FAILURE` | 사실 하나가 적용 branch를 선택하는 경우를 conflict로 보던 문제는 고쳤으나 S3가 모든 claim을 인용하지 않음 | factual-condition partial을 명시 |
| 2026-08-17 12:19 | `53bc3a3` retry | `EXECUTION_FAILURE` | S3 claim 계약을 고친 뒤 contextual gap query가 과거 query와 중복 | claims를 모두 인용 대상으로 제한하고 비인용 사실/한계를 assumptions·limitations로 이동 |
| 2026-08-17 12:28 | `d1611e7` retry2 | `ANSWER` | context 부착 후 중복 여부를 판정하지 않던 문제 | context가 붙은 최종 문자열 기준으로 고유 query를 만들고 최대 100개 fallback 제공 |
| 2026-08-17 12:35~14:24 | 최종 21문항 batch | `A6/AB13/F2` | 답변률은 개선됐지만 Top-10 recall, 3-hop, S3 형식 문제가 남음 | 결과를 `d4143e2`에 기록 |

## 5. 주요 수정 커밋

| Commit | 수정 요약 | 해결하려던 문제 |
|---|---|---|
| `88a8f82` | S2 단축 candidate ID, `[FULL_TEXT]` 원문 치환, link-assessment 결정론적 연결 | 잘못된 인용문과 후보 밖 ID |
| `d67d98c` | S1 run/request ID 정규화 및 gap query 제약 | 잘못된 ID와 중복 query |
| `6717de9` | unresolved evidence target 강제 및 fallback query | resolved/unknown target 재검색 |
| `83f1afc` | 초기 query 정규화와 중복 fallback 안정화 | 배치 중단 및 duplicate query |
| `85e8ac7` | BM25 Top-100, BGE 재정렬 후 Top-10, statute hint, structured query, monotonic coverage, 조건부 생성 | 낮은 recall과 이전 coverage 퇴행 |
| `0434823` | 상대 manifest 경로 해결 | tmux 배치 실행 경로 오류 |
| `cd13612` | KoBLEX background 포함, partial 유형 분리 | 질문만 넣어 법률관계가 소실된 입력 버그 |
| `1659fe6` | 한국어 조사·어미 prefix와 statute-hint 20% quota | FTS exact token 불일치 |
| `4e15091` | 마지막 사실문과 질문을 retrieval query에 부착 | 짧은 S1 query의 맥락 부족 |
| `44bfa72` | focus query와 원문 맥락 분리, 2~4자 핵심 prefix | 긴 원문에 의한 검색 anchor 희석 |
| `349e7fd` | 행위자 접미사 기반 prefix 확장 | `운송인/수임인/보험자` 등 행위자 형태 불일치 |
| `9f01c5a` | missing factual selector를 conflict가 아닌 factual partial로 분류 | 조건 분기 때문에 불필요하게 ABSTAIN |
| `53bc3a3` | 모든 S3 claim에 인용 강제, 비인용 한계 분리 | claim-citation contract 불일치 |
| `d1611e7` | 원문 context 부착 후 gap query 중복 제거 | 동일 gap query 반복 및 S1 실패 |

## 6. 첫 결과와 최종 결과 비교

### 6.1 비교 단위 주의

최초 결과는 하나의 frozen 21-item batch가 아니다. 다음 네 결과를 합쳐 개발 사이클의 21개 고유 문항 최종 시도를 재구성했다.

- 별도 `qa_19` 정상 종료 스모크: `8188334b-...`
- pilot20 anchor `qa_92`: `3c1b22ca-...`
- `qa_139` 별도 재시도: `70daf5b3-...`
- remaining-18 유효 배치: `bm25-bge-pilot-19-e37e7dec-e7b4-48fa-872d-6e07479444f6`

따라서 첫 결과는 개발 진단용이며, 최종 고정 조건과 직접적인 논문 성능 비교로 사용하면 안 된다. 동일 문항 비교는 original pilot20에 한정하는 것이 더 적절하다.

### 6.2 집계 비교

| 집계 | ANSWER | ABSTAIN | EXECUTION_FAILURE | 답변 생성률 | 평균 지연 |
|---|---:|---:|---:|---:|---:|
| 최초 유효 pilot20 | 2 | 16 | 2 | 10.0% | 142.45초 |
| 최초 개발 사이클 21개 고유 문항 | 2 | 17 | 2 | 9.5% | 145.09초 |
| 최종 조건의 동일 pilot20 | 5 | 13 | 2 | 25.0% | 별도 산출하지 않음 |
| 최종 고정 조건 21문항 | 6 | 13 | 2 | 28.6% | 310.09초 |

최종 21문항의 중앙값은 311.99초이고 총 wall time은 6,538.3초, 즉 약 1시간 48분 58초였다. 입력 맥락과 검색·평가가 늘면서 최초 개발 사이클보다 문항당 시간이 약 2.1배 증가했다.

### 6.3 hop별 비교

| Hop | 최초 개발 21 | 최종 21 |
|---|---|---|
| 1-hop 6문항 | `ANSWER 1 / ABSTAIN 5 / FAILURE 0` | `ANSWER 4 / ABSTAIN 2 / FAILURE 0` |
| 2-hop 11문항 | `ANSWER 0 / ABSTAIN 9 / FAILURE 2` | `ANSWER 2 / ABSTAIN 7 / FAILURE 2` |
| 3-hop 4문항 | `ANSWER 1 / ABSTAIN 3 / FAILURE 0` | `ANSWER 0 / ABSTAIN 4 / FAILURE 0` |

최초 3-hop ANSWER였던 `qa_352`는 KoBLEX gold의 국민체육진흥법 제47·48조가 아니라 형법 제246조를 근거로 답했다. 따라서 최종 3-hop의 `ANSWER 0`은 생성률상 회귀지만, 최초 결과를 정답 성공으로 볼 수는 없다.

### 6.4 문항별 결과

`Gold hit`은 최종 누적 후보에 KoBLEX gold context와 `(index, content)`가 정확히 일치하는 코퍼스 행이 몇 개 남았는지를 뜻한다.

| # | Question ID | Hop | 최초 개발 결과 | 최종 결과 | Gold hit | 비고 |
|---:|---|---:|---|---|---:|---|
| 1 | `qa_19_1hop_28` | 1 | ABSTAIN | ANSWER | 0/1 | 최종 답변은 gold 1년이 아니라 항공운송 2년을 제시 |
| 2 | `qa_92_1hop_149` | 1 | ANSWER | ANSWER | 1/1 | 정답 요지 일치 |
| 3 | `qa_139_1hop_254` | 1 | ABSTAIN | ANSWER | 1/1 | 개선 |
| 4 | `qa_140_1hop_257` | 1 | ABSTAIN | ABSTAIN | 0/1 | 민법 제691조 누락 |
| 5 | `qa_165_1hop_293` | 1 | ABSTAIN | ABSTAIN | 0/1 | BM25에서는 gold가 상위였으나 최종 Top-10 탈락 |
| 6 | `qa_85_1hop_135` | 1 | ABSTAIN | ANSWER | 1/1 | 개선 |
| 7 | `qa_163_2hop_630_rand` | 2 | ABSTAIN | ABSTAIN | 0/2 | BM25 Top-100부터 두 gold 모두 누락 |
| 8 | `qa_180_2hop_689_rand` | 2 | ABSTAIN | ABSTAIN | 1/2 | 두 번째 gold 탈락 |
| 9 | `qa_197_2hop_752_rand` | 2 | ABSTAIN | EXECUTION_FAILURE | 2/2 | 검색 성공 후 S3 인용 형식 실패 |
| 10 | `qa_211_2hop_804_rand` | 2 | ABSTAIN | EXECUTION_FAILURE | 2/2 | 검색 성공 후 S3 인용 형식 실패 |
| 11 | `qa_234_2hop_892_rand` | 2 | ABSTAIN | ABSTAIN | 2/2 | 순수 S2/사실포섭 blocker |
| 12 | `qa_26_2hop_104_rand` | 2 | ABSTAIN | ABSTAIN | 1/2 | 검색 누락 + S1 completion criteria 과잉 |
| 13 | `qa_281_2hop_441` | 2 | EXECUTION_FAILURE | ABSTAIN | 0/2 | 스키마 오류는 고쳤으나 S1 법영역/검색 실패 |
| 14 | `qa_290_2hop_453` | 2 | EXECUTION_FAILURE | ABSTAIN | 1/2 | 스키마 오류는 고쳤으나 두 번째 gold 탈락 |
| 15 | `qa_423_2hop_656` | 2 | ABSTAIN | ABSTAIN | 1/2 | 신탁법 제63조 탈락 |
| 16 | `qa_430_2hop_668` | 2 | ABSTAIN | ANSWER | 2/2 | 개선 |
| 17 | `qa_83_2hop_325_rand` | 2 | ABSTAIN | ANSWER | 2/2 | 개선 |
| 18 | `qa_104_3hop_182` | 3 | ABSTAIN | ABSTAIN | 0/3 | 형법 제20조가 BM25 3위였지만 최종 탈락 |
| 19 | `qa_321_3hop_511` | 3 | ABSTAIN | ABSTAIN | 1/3 | 민법 제741·379조 탈락 |
| 20 | `qa_352_3hop_554` | 3 | ANSWER | ABSTAIN | 1/3 | 최초 ANSWER는 gold 법률과 불일치 |
| 21 | `qa_74_3hop_116` | 3 | ABSTAIN | ABSTAIN | 0/3 | 신고·벌칙 관련 gold 모두 최종 탈락 |

## 7. 최종 21문항의 상세 결과

### 7.1 상태와 시간

- `ANSWER`: 6/21, 28.6%
- `ABSTAIN`: 13/21, 61.9%
- `EXECUTION_FAILURE`: 2/21, 9.5%
- 평균 지연: 310.09초
- 중앙값 지연: 311.99초
- 평균 누적 후보: 32.1개, 범위 10~56개
- 13개 ABSTAIN 모두 `MAX_RETRIEVAL_ROUNDS_REACHED` + `INSUFFICIENT_CRITICAL_EVIDENCE`

ABSTAIN 문항의 최종 missing critical item 수는 다음과 같다.

- 1개 부족: 8문항
- 2개 부족: 3문항
- 3개 부족: 2문항

즉 많은 문항에서 일부 근거는 확보했지만 하나의 critical item 때문에 전체 답변이 차단됐다.

### 7.2 실행 실패 2건

- `qa_197_2hop_752_rand`: 두 번의 S3 시도 후에도 CT1~CT7 marker가 answer에 없었고 C5·C6 claim text가 answer의 정확한 substring이 아니었다.
- `qa_211_2hop_804_rand`: 두 번의 S3 시도 후에도 CT3 marker가 answer에 없었다.

두 문항은 gold context 2/2가 최종 후보에 있었고 policy도 생성 단계까지 도달했다. 검색을 바꾸지 않고 S3 직렬화와 marker 삽입을 결정론적으로 처리하면 생성 성공 가능 문항은 6개에서 최대 8개로 늘어날 수 있다. 다만 형식 통과가 정답성을 보장하지는 않는다.

### 7.3 예비 답변 정합성 확인

최종 ANSWER 6건을 KoBLEX gold answer와 육안으로 대조했다.

- 정답 요지와 대체로 일치: `qa_92`, `qa_139`, `qa_85`, `qa_430`, `qa_83`
- 명백한 불일치: `qa_19`

`qa_19`의 gold는 상법 제814조에 따른 상품 인도일로부터 1년이며 합의로 기간을 연장할 수 있다는 내용이다. 최종 답변은 상법 제902조를 근거로 항공운송의 2년을 제시했다. 이 사례는 “인용문이 실제 후보 조문에 존재한다”는 citation integrity만으로 “질문에 적용되는 정답 조문”을 보장할 수 없음을 보여준다.

이 육안 확인은 정식 평가가 아니다. 논문 수치에는 사전 정의된 rubric, 독립 평가자 또는 deterministic gold comparison을 사용해야 한다.

## 8. 왜 정답 근거를 잘 찾지 못했는가

### 8.1 단계별 gold context recall

추론 종료 후에만 KoBLEX gold context를 사용하여 각 gold `(index, content)`를 233,544개 코퍼스 행에 exact match하고, 저장된 query를 동일 BM25에 다시 재생했다. gold는 실제 추론 입력에 넣지 않았다.

| 단계 | 전체 21문항 gold 40개 | 모든 gold를 확보한 문항 |
|---|---:|---:|
| 정규화 코퍼스 존재 | 40/40, 100% | 21/21 |
| 생성된 BM25 query 중 Top-100에 한 번이라도 등장 | 34/40, 85.0% | 16/21 |
| RRF 후 BGE 입력 pool Top-100 | 30/40, 75.0% | 13/21 |
| BGE 후 최종 누적 Top-10 후보 | 19/40, 47.5% | 8/21 |
| S2 수용 후보 | 19/40, 47.5% | 8/21 |

최종 ABSTAIN 13건만 보면 gold는 28개였다.

- 코퍼스 존재: 28/28
- BM25 Top-100: 21/28, 75.0%
- 최종 BGE Top-10: 8/28, 28.6%
- BM25가 찾았으나 최종 단계에서 탈락: 13/21, 61.9%
- 13개 ABSTAIN 중 gold가 전부 최종 후보에 남은 문항: `qa_234` 1건

따라서 주된 병목은 코퍼스 다운로드나 index 생성 실패가 아니라 `BM25 → RRF → BGE → Top-10`의 누적 후보 손실이다.

### 8.2 BGE 입력과 Top-10 절단

현재 pipeline은 같은 issue의 여러 query를 한 문자열로 이어 붙인다([pipeline.py](../../retrieval/pipeline.py)). 각 query에는 다시 background 일부와 질문이 붙기 때문에 동일 원문이 반복된다([local_ollama_executor.py](../../runtime/local_ollama_executor.py)). BGE에는 `statute_name`이나 조문 제목이 아니라 `provision_text`만 전달된다([reranker.py](../../retrieval/reranker.py)). 짧은 벌칙·미수·준용 조항에서는 법령명과 조문 제목이 중요한데 이 정보가 재정렬 입력에서 사라진다.

대표 사례:

- `qa_165`: gold 소송촉진법 제26조 제7항이 BM25 5·6·9위 등에 있었으나 최종 Top-10에서 탈락
- `qa_104`: 형법 제20조가 세 query에서 모두 BM25 3위였으나 최종 탈락
- `qa_290`: 도시 및 주거환경정비법 제16조가 BM25 43위였으나 탈락
- `qa_423`: 신탁법 제63조가 BM25 64위였으나 탈락
- `qa_74`: 성폭력처벌법 제43조의2가 BM25 17~19위였으나 탈락

### 8.3 BM25가 놓친 7개 gold와 조문 상호참조

ABSTAIN 문항에서 BM25 Top-100에도 한 번도 들어오지 않은 gold는 7개였다.

- `qa_163`: 국세기본법 시행령 제65조의4 관련 2개 context
- `qa_26`: 간접투자자산 운용업법 제185조 벌칙
- `qa_281`: 형법 제300조 미수범
- `qa_352`: 국민체육진흥법 제47·48조 벌칙
- `qa_74`: 성폭력처벌법 제50조 제3항 벌칙

벌칙·미수 조항은 행위명을 반복하지 않고 `제26조를 위반한 자`, `제299조의 미수범`처럼 다른 조문 번호만 참조하는 경우가 많다. 자연어 행위 중심 BM25 query와 어휘가 겹치지 않으므로 상호참조 graph나 인접 조문 확장이 필요하다.

### 8.4 S1 계획과 evidence 분해 오류

- `qa_165`: gold는 소송촉진법 제26조인데 S1이 형사소송법 중심으로 계획
- `qa_281`: gold는 형법 제299·300조인데 성폭력특례법 요건 3개로 과잉 분해
- `qa_26`: gold 답에 필요하지 않은 대통령령상의 구체 제한까지 completion criteria에 요구
- `qa_281`: 2-hop 문항에 critical item 3개 생성
- `qa_352`: 3-hop 문항에 critical item 4개 생성

정책은 S1이 만든 모든 critical item이 충족되어야 일반 답변을 허용한다([run_state.py](../../harness/run_state.py)). S1이 gold보다 많은 의무를 만들면 검색이 일부 성공해도 답변률이 급격히 낮아진다.

### 8.5 S2/사실포섭의 순수 blocker

`qa_234`는 두 gold context가 모두 최종 후보에 있었지만 E2가 `partially_covered`로 남았다. 질문의 “부주의”가 조문의 “고의 또는 중대한 과실”에 해당하는지를 별도 입증해야 한다고 판단했기 때문이다. 이는 검색 실패가 아니라 KoBLEX 질문 표현과 엄격한 사실포섭 기준 사이의 불일치이다.

`qa_26`도 gold 제177조 제2항이 최종 1위였지만 S1이 gold 답보다 넓은 completion criteria를 만들어 E1을 partial 처리했다. 이 문항은 다른 gold 제185조도 검색에서 누락되어 검색과 planning이 결합된 실패이다.

### 8.6 검색 라운드를 늘리는 것만으로는 부족

현재 progress는 관련성 여부와 무관하게 새로운 provision ID가 추가되면 참으로 계산된다([state_update.py](../../harness/state_update.py)). 따라서 비슷한 query로 새로운 오답 조문만 추가해도 3라운드를 모두 사용한다. Top-10 품질과 query 다양성을 고치지 않은 채 라운드만 늘리면 지연만 증가할 가능성이 크다.

## 9. 논문 관점의 방법론상 문제

### 9.1 개발 세트와 held-out test의 중첩

현재 21문항은 226문항 test parquet의 부분집합이며, 특히 `qa_19`를 반복 실행하면서 retrieval과 S2/S3를 수정했다. 따라서 226개 전체를 그대로 최종 평가하면 완전한 held-out test라고 주장하기 어렵다.

권장 처리:

1. 현재 21문항을 공식 development set으로 고정한다.
2. 나머지 205문항을 한 번만 실행하는 held-out main evaluation으로 둔다.
3. 226개 전체 결과가 필요하면 supplementary benchmark로 제시하되, 21개가 개발에 사용됐음을 명시한다.

### 9.2 설정이 다른 최초 결과의 혼합

최초 개발 21 결과는 여러 Git revision과 별도 실행을 합친 값이다. 논문 표의 주 결과로 쓰지 말고 “engineering history”로만 제시해야 한다. 최종 batch는 commit `d1611e7`, seed 0, 동일 manifest로 실행되어 조건 내 일관성은 확보했다.

### 9.3 생성률과 정답률의 혼동

`ANSWER`는 스키마·인용 형식 통과율이다. gold 조문 선택과 최종 결론의 정답성을 별도로 평가하지 않으면 false supported answer가 숨는다. `qa_19`와 최초 `qa_352`가 그 사례이다.

### 9.4 seed와 반복

현재 최종 21은 seed 0 한 번이다. 논문 프로토콜의 3개 seed 및 paired bootstrap은 최종 조건을 완전히 고정한 뒤 적용해야 한다.

## 10. 다음 수정 및 실험 우선순위

### P0. 먼저 측정할 것

1. 매 문항·evidence item마다 `BM25 rank`, `RRF rank`, `BGE rank`, `final hit`, `S2 accepted`를 자동 저장한다.
2. gold context를 강제로 S2에 넣는 oracle retrieval 실험으로 S2 자체의 false negative를 분리한다.
3. gold evidence obligation을 주는 oracle S1 실험으로 planning 과잉 분해를 분리한다.

### P1. retrieval 수정

1. BGE document를 `법령명 + 조문 제목 + 본문`으로 구성한다.
2. 여러 query와 반복 원문을 한 문자열로 합치지 말고 query별로 재정렬한 뒤 max score 또는 RRF로 결합한다.
3. 같은 21문항에서 `final_top_k=10/20/30` ablation을 수행한다.
4. BM25 index에 법령명·조문 제목을 검색 가능한 필드로 포함한다.
5. 법령명 공백·약칭을 정규화하고, 정확한 statute hint가 있으면 해당 법률 내부 후보를 별도 quota로 보장한다.
6. 검색된 조문의 cross-reference와 인접 벌칙·미수·준용 조항을 확장한다.

### P2. S1/S2 정책 수정

1. 독립적으로 필요한 법적 결론만 critical로 만들고 설명용 세부사항은 non-critical로 둔다.
2. KoBLEX gold 수준을 넘어선 completion criteria를 만들지 않는 validator 또는 audit rule을 추가한다.
3. `qa_234`와 같은 사실 표현 차이는 별도 factual-bridge 평가 항목으로 두고, 단순 threshold 완화와 분리한다.
4. 정책 완화는 retrieval·planning이 개선된 뒤 별도 ablation으로만 실행한다. 현재 바로 완화하면 `qa_19` 같은 오답을 더 늘릴 수 있다.

### P3. S3 형식 안정화

1. claim ID, citation marker 및 exact-substring 위치를 모델 자유 생성에 맡기지 말고 후처리로 결정론적으로 조립한다.
2. validator 오류를 구조화하여 실패한 marker/claim만 재생성한다.
3. 목표는 21문항 개발 세트에서 S1/S2/S3 contract failure 0건이다.

### 권장 실행 순서

1. 위 진단 로깅 추가
2. BGE 입력 수정 + Top-k ablation
3. cross-reference 및 statute-name 검색 수정
4. S1/S2 oracle 검사와 최소 수정
5. S3 결정론적 형식 조립
6. 같은 21문항 development rerun
7. BM25+BGE 조건 고정
8. KURE+BGE를 동일 21문항에서 비교하고 조건 고정
9. 남은 205문항 held-out 실행

## 11. 재현성 경로

- 최종 manifest: [bm25_bge_factualbranch_21_20260817.json](../../data/koblex/manifests/bm25_bge_factualbranch_21_20260817.json)
- 최종 batch metadata: [metadata.json](../batches/bm25-bge-factualbranch-21-full-808c1fa5-a4e8-4f6c-8f45-5f303c3da33f/metadata.json)
- 최종 summary: [summary.jsonl](../batches/bm25-bge-factualbranch-21-full-808c1fa5-a4e8-4f6c-8f45-5f303c3da33f/summary.jsonl)
- 최종 tmux log: [bm25-bge-factualbranch-21-full-20260817.log](../tmux/bm25-bge-factualbranch-21-full-20260817.log)
- 최초 E2E 실패: [result.json](../runs/27e95f6e-173b-4a5f-bfd8-c25aa46c62f9/result.json)
- 최초 정상 종료 qa19 스모크: [result.json](../runs/8188334b-a845-4f07-8cf9-67898a5914f7/result.json)
- 최초 안정적 qa92 ANSWER: [result.json](../runs/3c1b22ca-3a57-48c6-a4c6-8556184fc182/result.json)
- 최초 유효 remaining-18 batch: `records/batches/bm25-bge-pilot-19-e37e7dec-e7b4-48fa-872d-6e07479444f6/`
- 최종 실행 기록 커밋: `d4143e2`

초기·중간 개발 run 중 일부는 현재 로컬에서만 미추적 상태이다. 논문 artifact 공개 전에 이 보고서가 참조하는 selected development run과 batch를 별도 커밋하고, 중단된 `NO_FINAL_RESULT`는 실패 원인 기록으로만 분리하는 것이 좋다.

# Legal Harness — Claude Code 인수인계

작성일: 2026-08-19 UTC
프로젝트 루트: `/root/Legal Harness`
GitHub: `git@github.com:Youmin02/Legal-Harness.git`
브랜치: `main`

## 0. Claude Code에 바로 전달할 지시

아래 프로젝트를 기존 상태에서 이어서 작업한다. 먼저 이 문서를 끝까지 읽고,
`provision_coverage_skill_harness_md_split/ABSTAIN_REDUCTION_AND_RETRIEVER_COMPARISON_PLAN.md`와
`docs/EXPERIMENT_PROTOCOL.md`를 확인한다. 완료된 run 기록은 수정하거나 덮어쓰지 말고,
새 실험은 반드시 새 UUID run 및 새 batch 디렉터리에 기록한다.

우선순위는 다음과 같다.

1. Qwen3.8 최종 21문항 배치를 오프라인 평가기로 집계한다.
2. ANSWER 4건의 공식 KoBLEX Token-F1 및 gold 조문 지표를 재현 가능한 평가 스크립트/산출물로 남긴다.
3. ABSTAIN 17건을 first-stage@100, RRF@100, BGE@10/20/30, S2 false-negative로 분해 진단한다.
4. 계획서에 따라 한 번에 한 요인만 바꾸는 ablation을 설계한다.
5. 21문항에서 근거 회수와 답변률이 충분히 안정되기 전에는 226문항 본실험을 시작하지 않는다.

모든 장기 실험은 tmux에서 실행하고, 5문항마다 진행률을 보고한다. 소스 변경은 실험 전에
테스트·커밋·푸시하여 run metadata의 Git SHA와 실제 동작을 일치시킨다.

## 1. 현재 Git 상태

이 문서를 만들기 직전 기준:

- HEAD 및 `origin/main`: `b000f10`
- 최근 중요 커밋:
  - `b000f10 record: add Qwen3.8 pilot and diagnostic runs`
  - `a9cc6ed fix: propagate gap retrieval round to S1`
  - `6264284 fix: align gap IDs and Qwen3.8 structured output`
  - `78b19f8 fix: load Qwen3.8 pilot model without vision projector`
  - `905de95 config: add Qwen3.8 27B Q8 pilot condition`
  - `139fce5 record: preserve diagnostic B0 evaluation artifacts`
  - `ac3f042 feat: add provenance-aware retrieval ablation framework`
  - `092286f record: preserve complete BM25 BGE development history`
  - `51319d0 docs: summarize BM25 BGE pilot history`
  - `d4143e2 record: add 21-item BM25+BGE factual-branch run`
- 전체 회귀 테스트: 56개 통과
- 테스트 명령:

```bash
cd '/root/Legal Harness'
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
git diff --check
```

이 문서를 추가한 뒤에는 당연히 작업 트리가 변경된다. 문서를 커밋했다면 새 HEAD를 기준으로
후속 실험 metadata를 기록해야 한다.

## 2. 연구 목표와 하네스 구조

목표는 KoBLEX 226문항을 대상으로 단일 로컬 LLM과 명시적 스킬 하네스를 사용하여
법률 QA의 근거 회수, 조문 충분성, 인용 정합성과 답변 품질을 평가하는 것이다.

파이프라인:

```text
사용자 질문
  -> S1 질의 상태 분석 및 검색 계획
  -> 법률 쟁점/critical evidence 분해
  -> 검색 질의 생성
  -> BM25 또는 KURE-v1 first stage
  -> RRF / BGE rerank / 후보 선택
  -> S2 조문 충분성 평가
      -> 근거 부족이면 제한된 GAP 검색 반복
      -> 근거 충분 또는 조건부 생성 가능이면 S3
  -> S3 근거 기반 답변 생성
  -> 조문 인용 무결성 검증
  -> ANSWER 또는 ABSTAIN
```

스킬 위치:

- `skills/legal_issue_and_query_planning/SKILL.md` — S1
- `skills/provision_coverage_assessment/SKILL.md` — S2
- `skills/grounded_legal_answer_generation/SKILL.md` — S3

중요 계약:

- 초기 요청 ID: `RQ1`, `RQ2`, ...
- GAP 요청 ID: `GRQ-R{retrieval_round}-{index}`
- GAP S1 입력에는 positive integer `next_retrieval_round`가 반드시 있어야 한다.
- `runtime/local_ollama_executor.py`가 이 값을 S1로 전달한다.
- S3의 모든 `claims[]`는 인용되어야 하고 실제 answer substring이어야 한다.
- 비인용 사실·한계는 `assumptions` 또는 `limitations`로 이동한다.

## 3. 데이터, 검색기와 로컬 모델

### KoBLEX

- QA: `data/koblex/qa/test-00000-of-00001.parquet`
- 문항 수: 226
- QA SHA-256: `afdaff3a8000cdf5e0a64adbcfc8e6aff0042b318bf03718155f2b70f551c47b`
- 원 법령 corpus: `data/koblex/statute/corpus-00000-of-00001.parquet`
- 정규화 corpus: `data/koblex/normalized/statute.jsonl`
- BM25 index: `data/koblex/indexes/bm25/statute_fts5.sqlite3`
- KURE vectors: `data/koblex/indexes/kure-v1/vectors.f32.npy`
- KURE ID map: `data/koblex/indexes/kure-v1/provision_ids.txt`

### 검색 모델

- KURE encoder: `models/huggingface/nlpai-lab--KURE-v1`
- BGE reranker: `models/huggingface/dragonkue--bge-reranker-v2-m3-ko`
- 연결 코드: `scripts/run_local_harness.py`
- BM25/KURE 구현: `retrieval/persistent.py`
- RRF/BGE/후보 선택: `retrieval/pipeline.py`

### Qwen3.8

- Ollama alias: `legal-harness-qwen38-q8`
- 원 checkpoint: `Qwen/Qwen3.8-27B`
- 원 revision: `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`
- GGUF: `ggml-org/Qwen3.8-27B-GGUF/Qwen3.8-27B-Q8_0.gguf`
- GGUF revision: `0669b98607d47046c7c2b3f801011d54a08cfccf`
- SHA-256: `f5c702d8820d36fb55985bb238fc83ee3a313e920f4b752a437c3a6a9e14e4c8`
- 크기: 28,595,763,552 bytes
- Ollama: 0.20.5
- Modelfile: `configs/ollama/Qwen3.8-27B-Q8_0.Modelfile`
- text-only alias이며 vision projector를 로드하지 않는다.
- Qwen3.8 공식 chat token + non-thinking framing을 사용한다.
- 하네스 실행 시 `num_ctx=32768`, `temperature=0`, `seed=0`이다.

Qwen3.8 GGUF의 vision projector를 함께 로드하면 Ollama가 compatibility llama.cpp runner로
fallback하며 `unknown model architecture: 'qwen35'` 오류가 발생했다. 현재 alias는 검증된 main
model blob만 `FROM`으로 사용하여 해결했다. raw-completion template도 JSON 뒤에 특수 토큰을
붙이거나 S1 JSON을 깨뜨렸으므로 다시 사용하면 안 된다.

### 이전 모델

- Ollama alias: `legal-harness-qwen`
- 과거 Qwen3.6 계열 실험에 사용했다.
- 삭제하지 말 것. 통제 비교에 필요하다.

### 하드웨어

- GPU: NVIDIA H200 NVL
- 총 VRAM: 143,771 MiB
- Qwen3.8 Q8 load: 모델 약 34 GiB
- BGE 등을 포함한 관측 총량: 약 40 GiB
- VRAM은 충분하다.

## 4. provenance 및 평가 프레임워크 구현 상태

`ac3f042` 이후 다음이 구현되어 있다.

- `CandidateProvision`에 first-stage, fusion, rerank, selection rank가 구분되어 기록된다.
- 요청/evidence provenance가 `source_request_ids`, `target_evidence_item_ids`로 보존된다.
- 각 run은 `retrieval_stages.jsonl` sidecar를 기록한다.
- stage에는 first stage, request rerank, evidence/issue fusion, selected 여부가 포함된다.
- `scripts/evaluate_dev_runs.py`는 KoBLEX gold contexts와 다음을 오프라인 평가한다.
  - provision precision/recall/F1
  - first-stage@100
  - RRF@100
  - BGE@10/20/30
  - complete evidence
  - citation integrity
  - supported-answer yield
  - latency와 요청 수
- 실행 metadata는 `git_source_worktree_dirty`를 기록한다. `records/` 산출물만 생성된 경우에는
  source dirty로 보지 않지만 `.py`, schema, manifest 등 소스 변경은 dirty로 간주한다.

주의: `state.candidate_provisions`에 누적된 scalar rank는 최초 관측값을 보존한다. 논문용 단계별
Recall 분석은 반드시 append-only `retrieval_stages.jsonl`을 기준으로 해야 한다.

## 5. 고정 21문항 개발 세트

Qwen3.8 manifest:

`data/koblex/manifests/bm25_bge_per_request_b1a_qwen38_q8_21_20260818.json`

고정 설정:

- 21문항: 1-hop 6, 2-hop 11, 3-hop 4
- retriever: BM25
- reranker: `dragonkue--bge-reranker-v2-m3-ko`
- `rerank_pool_k=100`
- `final_top_k=10`
- `rerank_query_mode=per_request`
- `candidate_selection=global_top_k`
- 후보 예산: issue/round 기준
- BGE document mode: `body_only`
- 검색 라운드 최대 3
- 검색 요청 최대 9
- 입력: KoBLEX `background + question`
- gold answer와 gold contexts는 모델 입력에 주지 않는다.

이 21문항은 개발 세트다. held-out 226문항 본실험 결과처럼 표현하면 안 된다.

## 6. 완료된 주요 실험

### 6.1 과거 Qwen3.6/BM25+BGE factual-branch 21

- batch:
  `records/batches/bm25-bge-factualbranch-21-full-808c1fa5-a4e8-4f6c-8f45-5f303c3da33f`
- 커밋: `d4143e2`
- ANSWER: 6/21 (28.6%)
- ABSTAIN: 13/21 (61.9%)
- EXECUTION_FAILURE: 2/21 (9.5%)
- 평균: 310.09초
- 중앙값: 311.99초
- wall: 약 1시간 49분

이전 진단에서 13개 ABSTAIN의 gold context 28개는 corpus에 모두 존재했다. BM25 생성 질의의
Top-100에는 21/28이 한 번 이상 들어왔지만 최종 BGE Top-10에는 8/28만 남았다. 이 수치는
과거 Qwen3.6/B0 계열 결과의 진단이며, Qwen3.8/B1a에 그대로 재사용하면 안 된다.

### 6.2 Qwen3.8/B1a 21 — 현재 최신

- batch:
  `records/batches/bm25-bge-per-request-b1a-qwen38-q8-21-r2-40bcce7e-e838-47f9-a752-04647f39ecde`
- 기록 커밋: `b000f10`
- ANSWER: 4/21 (19.0%)
- ABSTAIN: 17/21 (81.0%)
- EXECUTION_FAILURE: 0/21
- 평균: 328.72초
- 중앙값: 319.37초
- 총 실행 시간: 6,903초, 약 1시간 55분
- hop별:
  - 1-hop: ANSWER 1 / ABSTAIN 5
  - 2-hop: ANSWER 3 / ABSTAIN 8
  - 3-hop: ANSWER 0 / ABSTAIN 4
- ANSWER:
  - `qa_92_1hop_149`
  - `qa_197_2hop_752_rand`
  - `qa_211_2hop_804_rand`
  - `qa_83_2hop_325_rand`

ABSTAIN 17개 중 16개는 `MAX_RETRIEVAL_ROUNDS_REACHED`, 1개는
`RETRIEVAL_BUDGET_EXHAUSTED`이며 모두 `INSUFFICIENT_CRITICAL_EVIDENCE`다.

### 6.3 비교 해석 주의

Qwen3.6 6/21과 Qwen3.8 4/21을 순수 모델 비교로 쓰면 안 된다.

- Qwen3.6 결과는 과거 global/B0 성격 설정이다.
- Qwen3.8은 수정된 B1a per-request retrieval 설정이다.
- checkpoint, quantization(Q4 계열 대 Q8), prompt framing도 다르다.
- 반복 실행도 완전히 결정론적이지 않았다. smoke와 full에서 `qa_19`, `qa_92` 결과가 바뀌었다.

모델 비교를 하려면 동일 Git commit, 동일 manifest, 동일 retrieval, 동일 policy, 동일 21문항에서
모델 alias만 바꾼 paired run이 필요하다. quantization/prompt 차이는 confound로 명시한다.

## 7. Qwen3.8 ANSWER 품질 예비 평가

KoBLEX 공식 공개 코드의 정규화와 공백 단위 Counter Token-F1을 그대로 재현한 결과:

| question_id | Token-F1 | gold provision P/R/F1 | 수동 내용 판정 |
|---|---:|---:|---|
| `qa_92_1hop_149` | 0.0769 | 1.0 / 1.0 / 1.0 | 정답 |
| `qa_197_2hop_752_rand` | 0.5714 | 1.0 / 1.0 / 1.0 | 정답 |
| `qa_211_2hop_804_rand` | 0.7172 | 1.0 / 1.0 / 1.0 | 정답 |
| `qa_83_2hop_325_rand` | 0.5278 | 1.0 / 1.0 / 1.0 | 정답 |

- answered-only macro Token-F1: `0.4733`
- ABSTAIN을 0으로 처리한 21문항 end-to-end macro Token-F1: `0.0902`
- 4개 모두 citation integrity pass
- 4개 모두 accepted evidence가 gold evidence를 완전히 충족
- gold-incomplete supported answer: 0개

`qa_92`는 법적 결론이 정확하지만 gold가 `10년 이하의 징역`처럼 매우 짧고, 시스템 답변은
조문 설명과 `[CT1]` 표기를 포함해 49개 공백 토큰이므로 Token-F1이 0.0769로 낮다. 즉 현재
Token-F1은 정확성뿐 아니라 장황함과 citation token을 크게 벌점 처리한다.

공식 평가 코드:

`https://github.com/daehuikim/KoBLEX/blob/main/experiments/lf-eval/eval_pipeline.py`

공식 LF-Eval은 아직 실행하지 않았다. 논문 조건은 질문, gold answer, gold provisions와 prediction을
GPT-4o judge에 제공하고 반복 점수/확률로 집계한다. API 비용과 외부 judge 조건을 사전 고정하지
않은 채 임의로 실행하지 말 것. 로컬 Qwen을 judge로 쓰면 공식 LF-Eval이 아니므로 반드시
`adapted local evaluator`로 별도 표기한다.

## 8. 가장 중요한 미해결 문제

### 8.1 Qwen3.8에서 Answer Coverage가 19%에 불과함

ANSWER 4건은 모두 정확하지만 17건을 보류했다. 현재 최우선은 threshold를 무작정 낮추는 것이
아니라 각 ABSTAIN의 손실 위치를 분해하는 것이다.

각 문항을 다음 범주로 분류한다.

1. gold 조문이 first-stage Top-100에 전혀 없음
2. first-stage에는 있으나 RRF Top-100에서 탈락
3. RRF에는 있으나 BGE Top-10에서 탈락
4. BGE 11~20 또는 21~30에 있어 cutoff만 문제
5. 최종 후보에 gold가 모두 있으나 S2가 partial/missing으로 잘못 판정
6. S1이 잘못된 법령/쟁점/과도한 completion criteria를 생성
7. 정책 budget 때문에 근거가 오기 전에 중단

새 Qwen3.8 run에는 `retrieval_stages.jsonl`이 있으므로 과거보다 정확히 분석할 수 있다.

### 8.2 답변 품질 평가가 아직 자동화되지 않음

`scripts/evaluate_dev_runs.py`는 retrieval/gold provision/citation은 평가하지만 공식 Token-F1과
LF-Eval을 직접 산출하지 않는다. 다음 스크립트를 추가하는 것이 권장된다.

`scripts/evaluate_answer_quality.py`

필수 출력:

- question_id
- status
- gold answer
- prediction
- official-style Token precision/recall/F1
- answered-only aggregate
- ABSTAIN=0 end-to-end aggregate
- accepted/gold provision completeness
- citation integrity
- 선택적 LF-Eval score 및 evaluator provenance

논문 결과를 유리하게 만들기 위해 사후에 citation을 제거하거나 정답 부분만 사람이 추출하면 안 된다.
전체 226 실행 전에 다음 중 하나를 사전 등록한다.

1. 현재 사용자용 citation answer 자체를 그대로 평가
2. S3가 사용자용 `answer`와 별도 concise `benchmark_answer`를 동시에 생성하도록 계약 변경 후 전부 재실행
3. 완전히 결정론적인 사전 정의 추출기를 모든 조건에 동일 적용

기존 완료 run을 수정하지 말 것.

### 8.3 3-hop ANSWER가 0/4

다중 조문 회수, evidence 분배, budget, S1 과분해를 별도로 점검해야 한다. 3-hop 실패를 단순히
모델 생성 능력 문제로 결론 내리지 말 것.

## 9. 다음 작업 권장 순서

### P0 — 현재 결과 평가 산출물 고정

```bash
cd '/root/Legal Harness'
.venv/bin/python scripts/evaluate_dev_runs.py \
  --batch-dir records/batches/bm25-bge-per-request-b1a-qwen38-q8-21-r2-40bcce7e-e838-47f9-a752-04647f39ecde \
  --dataset data/koblex/qa/test-00000-of-00001.parquet \
  --corpus data/koblex/normalized/statute.jsonl \
  --output-dir records/evaluations/qwen38-b1a-21-20260819 \
  --require-stage-provenance
```

출력 후 aggregate와 per-question CSV/JSON을 검토하고 커밋한다. 평가기 소스를 수정했다면 먼저
소스만 별도 커밋한 뒤 평가 산출물을 다시 생성하여 evaluator SHA가 dirty source에 귀속되지 않게 한다.

### P1 — 공식 Token-F1 평가기 추가

공식 구현과 동일하게:

```python
text = text.lower()
text = re.sub(r'[^가-힣a-z0-9\s]', ' ', text)
text = re.sub(r'\s+', ' ', text).strip()
tokens = text.split()
common = Counter(pred_tokens) & Counter(gold_tokens)
```

공식 코드가 prediction을 800자에서 자르므로 동일 조건 사용 여부도 metadata에 남긴다.

### P2 — 17 ABSTAIN 손실 분해

`scripts/evaluate_dev_runs.py`의 per-question stage metrics를 활용하여 17개를 위 7개 범주로 분류한다.
최소 산출물:

- `records/evaluations/.../per_question.csv`
- `records/evaluations/.../aggregate.json`
- `docs` 또는 `records/evaluations` 아래 진단 Markdown
- gold stage waterfall 표
- S1/S2 false-negative 문항 목록과 근거

### P3 — 한 요인 ablation

계획서의 Phase 1/2를 따른다. 한 manifest에서 여러 요인을 동시에 바꾸지 않는다.

권장 예:

- B1a: 현재 per-request, global Top-10, body-only
- B1b: B1a와 같고 final Top-K만 20
- B1c: B1a와 같고 final Top-K만 30
- 그 다음 statute name + body reranker input을 단독 요인으로 비교
- evidence-balanced selection은 별도 조건

각 조건은 동일 21문항/seed/order/model에서 실행한다. 21개 모두 끝난 뒤에만 조건을 비교한다.

### P4 — 순수 모델 비교에 가까운 paired run

Qwen3.6 alias `legal-harness-qwen`을 현재 B1a 설정으로 다시 실행한다. Qwen3.8과 retrieval/harness를
같게 유지하고 model alias 및 model provenance만 바꾼 새 manifest를 만든다. 그래도 quantization과
prompt framing 차이는 남으므로 논문에 명시한다.

### P5 — BM25 대 KURE-v1

사용자 계획은 BM25+BGE 226문항을 먼저 끝내고 다음에 KURE-v1+BGE를 실행하는 것이다. 다만
현재 21문항 Answer Coverage 19%이므로 바로 226으로 확대하지 말고 P0~P3 후 pilot gate를 통과한다.

비교 시 first-stage retriever만 BM25에서 KURE로 바꾸고 다음은 고정한다.

- 질문/seed/order
- BGE reranker와 입력 mode
- pool K/final K
- candidate selection
- 하네스 policy
- 모델 checkpoint/quantization/template
- round/request budget

BM25, KURE 각각 full run을 완료한 뒤 hybrid는 사전 정의된 추가 조건에서만 실행한다.

### P6 — 226문항 본실험

`docs/EXPERIMENT_PROTOCOL.md`를 따른다.

- 조건별 clean commit 및 tag
- 3개 고정 seed
- 질문 내 seed 평균 후 question-level paired bootstrap 10,000회
- 95% CI
- 이진 결과 McNemar + Holm 보정
- answer-only와 end-to-end(ABSTAIN=0) 모두 보고
- supported-answer yield와 false-supported rate 분리
- hop별 결과는 subgroup/exploratory로 구분

## 10. 장기 실험 실행 규칙

모든 실험은 tmux로 실행한다. 예시:

```bash
cd '/root/Legal Harness'
tmux new-session -d \
  -s legal-harness-qwen38-b1a21 \
  -c '/root/Legal Harness' \
  "bash -lc 'set -o pipefail; \
  .venv/bin/python scripts/run_bm25_bge_pilot_batch.py \
    --manifest data/koblex/manifests/bm25_bge_per_request_b1a_qwen38_q8_21_20260818.json \
    --batch-name qwen38-b1a21-rerun \
    2>&1 | tee records/tmux/qwen38-b1a21-rerun.log'"
```

상태 확인:

```bash
tmux list-sessions
tmux capture-pane -p -t legal-harness-qwen38-b1a21 -S -120
wc -l records/batches/<batch-uuid>/summary.jsonl
nvidia-smi
```

완료 후:

1. summary 줄 수와 manifest entry 수 일치 확인
2. summary가 참조한 모든 run directory/result 존재 확인
3. ANSWER/ABSTAIN/EXECUTION_FAILURE 집계
4. 비밀정보·대용량 파일 검사
5. raw run, batch, tmux log, evaluation artifact 커밋
6. `git push origin main`
7. `origin/main...main = 0 0` 확인

중단·실패 run도 연구 이력이다. 삭제하지 말고 metadata/events와 함께 보존하며 완성 결과와 구분한다.

## 11. 절대 피해야 할 것

- 기존 `records/runs/<uuid>` 또는 batch 결과 덮어쓰기
- gold answer/context를 모델 입력에 포함
- ANSWER 수를 KoBLEX 정답 수로 그대로 보고
- threshold만 낮춰 ABSTAIN을 강제로 ANSWER로 변경
- 한 실험 조건에서 모델, Top-K, rerank input, selection을 동시에 변경
- dirty source 상태로 논문용 run 실행
- Qwen3.6 6/21과 Qwen3.8 4/21을 순수 모델 우열로 단정
- 공식 GPT-4o LF-Eval과 로컬 adapted judge 점수를 같은 이름으로 보고
- 모델 파일, 956MB KURE vectors, 129MB corpus 등을 실수로 Git force-add
- API key나 credential을 record/log에 남기기

## 12. 주요 참고 파일

- 연구 계획 원본:
  `KCI_한국법률QA_단일LLM_스킬하네스_연구계획서_v1 복사본.md`
- 분할 설계 문서:
  `provision_coverage_skill_harness_md_split/`
- ABSTAIN/검색기 계획:
  `provision_coverage_skill_harness_md_split/ABSTAIN_REDUCTION_AND_RETRIEVER_COMPARISON_PLAN.md`
- 실험 프로토콜:
  `docs/EXPERIMENT_PROTOCOL.md`
- 과거 종합 보고:
  `docs/BM25_BGE_PILOT_HISTORY_AND_RESULTS_20260817.md`
- 현재 Qwen3.8 manifest:
  `data/koblex/manifests/bm25_bge_per_request_b1a_qwen38_q8_21_20260818.json`
- 현재 Qwen3.8 최종 batch:
  `records/batches/bm25-bge-per-request-b1a-qwen38-q8-21-r2-40bcce7e-e838-47f9-a752-04647f39ecde`
- 평가기:
  `scripts/evaluate_dev_runs.py`
- batch runner:
  `scripts/run_bm25_bge_pilot_batch.py`
- single run:
  `scripts/run_local_harness.py`

## 13. 현재 상태 한 문장 요약

하네스의 스키마·인용·provenance·Qwen3.8 연동 오류는 해결되어 실행 실패 없이 21문항을 완주했고,
ANSWER 4건은 gold 조문과 법적 결론이 모두 정확했지만, 17건 ABSTAIN으로 Answer Coverage가
19%에 그쳐 다음 핵심 작업은 `retrieval_stages.jsonl` 기반 손실 위치 진단과 단일요인 ablation이다.

# KoBLEX ParSeR Baseline — Reproduction Notes

작성일: 2026-08-19 UTC

## 목적

이 문서는 `baselines/koblex_parser/` + `scripts/run_koblex_parser_baseline.py` +
`scripts/evaluate_koblex_parser_baseline.py`가 KoBLEX 논문 자체가 제안한
방법(ParSeR)을 얼마나 충실히 재현했는지, 그리고 의도적으로 무엇을 다르게
했는지를 기록한다. 이 파이프라인은 프로젝트 자체의 스킬 하네스(S1/S2/S3,
`skills/`, `harness/`, `runtime/local_ollama_executor.py`)와 완전히 독립된
코드 경로이며, 사용자 자신의 방법을 포함하지 않는다 — 논문 베이스라인
비교를 위한 순수 재현이다.

## 출처

- 논문: Lee, Kim, Hwang, Kim, Lee. "KoBLEX: Open Legal Question Answering
  with Multi-hop Reasoning." EMNLP 2025.
  https://aclanthology.org/2025.emnlp-main.200/
- 공식 저장소: https://github.com/daehuikim/KoBLEX (2026-08-19 `main` 기준)
- 직접 참조한 원본 파일 (raw.githubusercontent.com에서 원문 그대로 fetch,
  요약이 아님):
  - `experiments/parser/prompts/parametric_provision.py`
  - `experiments/parser/prompts/selection_retrieval.py`
  - `experiments/parser/prompts/question_answering.py`
  - `experiments/parser/vllm/parametric_provision.py`
  - `experiments/parser/vllm/selection_retrieval.py`
  - `experiments/parser/vllm/question_answering.py`
  - `experiments/parser/vllm/utils.py`
  - `experiments/parser/vllm/run_pipeline.py`
  - `experiments/lf-eval/eval_pipeline.py`
  - 루트 `README.md`, `experiments/README.md`, 각 하위 `README.md`

## 재현한 것

1. **3단계 ParSeR 알고리즘**: 파라메트릭 조문 생성 → (BM25 top-100 →
   BGE reranker top-10 → LLM 1개 선택) × 조문 수 → 선택된 조문들로 답변 생성.
2. **프롬프트**: 3단계 모두 SYSTEM_PROMPT/INSTRUCTION_PROMPT를 문자 단위로
   그대로 포팅 (`baselines/koblex_parser/prompts.py`). in-context 예시도 원문 그대로.
3. **검색기**: `bm25s` 라이브러리 + `stopwords="en"` 토크나이즈, corpus 텍스트는
   `hierarchy + content` 연결 — 공식 `utils.py`와 동일. 프로젝트 자체의
   `retrieval/persistent.py`(FTS5 SQLite BM25)는 사용하지 않는다.
4. **Reranker**: `dragonkue/bge-reranker-v2-m3-ko`, `CrossEncoder` +
   `Sigmoid` 활성화, `batch_size=50` — 공식 코드와 동일.
5. **하이퍼파라미터**: BM25 k=100/조문, rerank 후보 상위 10개를 LLM에 제시,
   temperature=0, stage1/3 max_tokens=4000, stage2 max_tokens=2048,
   `enable_thinking=False`(non-thinking) 프레이밍 — 공식 vLLM 스크립트 기본값과 동일.
6. **QA 입력**: `background + question` 연결, context는 선택된 조문 텍스트를
   개행으로 연결 — 공식과 동일.
7. **평가**: `normalize()`/`tokenize()`/`compute_token_f1()`,
   `evaluate_retrieval()`(집합 기반 P/R/F1/EM)을 문자 단위로 포팅.
   `official_truncate_prediction()`도 공식의 800자 절단 로직을 그대로 포함.
8. **데이터**: `data/koblex/qa/test-00000-of-00001.parquet`(226문항, 공식
   HF `id/question/answer/background/contexts/n_hops` 스키마와 일치),
   `data/koblex/statute/corpus-00000-of-00001.parquet`(233,544건 —
   논문이 명시한 corpus 크기와 일치, `index/hierarchy/content` 스키마).

## 의도적으로 다르게 한 것

### 1. `selection_retrieval.py`의 인덱싱 버그 수정

공식 `experiments/parser/vllm/selection_retrieval.py`의 `process_completions()`:

```python
for count, contexts_list in zip(counts, reranked):
    sel_per_q = []
    for _ in range(count):
        ...
        sel_per_q.append(contexts_list[0][choice])   # <- 항상 인덱스 0
```

`reranked[qi]`는 질문 qi의 조문별 재순위 리스트 목록인데, 매 조문의 선택을
**항상 첫 번째 조문(index 0)의 top-10**에서만 뽑는다. 2/3-hop처럼 조문이
2개 이상인 질문에서는 두 번째 이후 조문의 선택이 실제로는 첫 번째 조문의
후보 풀에서 나오게 되는, 공개 코드 자체의 버그로 보인다. 논문 서술
("LLM identifies single most relevant provision **per parametric provision**")과
불일치한다.

**결정**: 사용자 확인 후, 논문이 서술한 의도대로 각 조문이 **자기 자신의**
top-10에서 선택되도록 수정했다 (`baselines/koblex_parser/pipeline.py`의
`select_provisions()`). 이 재현은 "공식 코드의 버그를 그대로 재현한 결과"가
아니라 "논문이 설명하는 ParSeR 알고리즘"이다.

### 2. `escape_quotes()` 이중 이스케이프 생략

공식 `utils.py`의 `escape_quotes()`는 파싱된 파라메트릭 조문 문자열에
수동으로 백슬래시 이스케이프를 적용하는데, 이후 `save_jsonl()`이
`json.dumps()`로 다시 이스케이프하므로 이중 이스케이프가 된다. 이 재현은
파싱된 문자열을 그대로 두고 JSON 직렬화 시 한 번만 이스케이프한다 — BM25
질의 텍스트에 불필요한 백슬래시가 섞이는 것을 막기 위함이며, 알고리즘의
본질(파라메트릭 조문 생성/검색/선택)에는 영향이 없다.

## 실행하지 않은 것

**공식 LF-Eval (GPT-4o 기반 G-Eval)**: `experiments/lf-eval/eval_pipeline.py`의
`evaluate_legal_fidelity()`는 `deepeval` + OpenAI GPT-4o 호출이 필요하다.
`docs/HANDOFF_TO_CLAUDE_CODE_20260819.md` §7의 지침("API 비용과 외부 judge
조건을 사전 고정하지 않은 채 임의로 실행하지 말 것")에 따라 이번 베이스라인
실행에서는 호출하지 않았다. 이 문서 작성 시점에 `OPENAI_API_KEY`도
설정되어 있지 않다. 이후 사용자가 비용을 사전 승인하면
`final_results.jsonl`(`answer`/`provisions` 필드 보유)을 공식
`eval_pipeline.py --eval_type legal_fidelity`에 그대로 넣어 실행할 수 있다.
대신 `scripts/evaluate_koblex_parser_baseline.py`가 Token-F1 + 검색
P/R/F1/EM(둘 다 공식과 동일 정의, 비용 없음)과 hop별/단계별 지연시간을
계산한다.

## 사용자 자신의 스킬 하네스와의 비교 시 주의

- ParSeR은 **ABSTAIN이 없다** ("Do not refuse or say insufficient context").
  Answer rate는 항상 ~100%에 가깝다. 반면 사용자의 하네스는 근거 충족도
  기반으로 ABSTAIN한다. 따라서 answer rate 자체를 우열 지표로 쓰면 안 되고,
  **answer-only Token-F1**과 **end-to-end(미답변=0점) Token-F1**을 함께
  보고해야 공정하다 — `docs/HANDOFF_TO_CLAUDE_CODE_20260819.md` §9 P6의
  지침과 동일한 원칙이다.
- ParSeR의 검색기는 `bm25s`(영어 stopword 토크나이즈)이고, 사용자 하네스는
  `retrieval/persistent.py`(FTS5 SQLite)를 쓴다 — 둘 다 "BM25"라고 부르지만
  구현이 다르므로 검색 성능 차이를 하네스 효과로 오인하지 않는다.
- 두 파이프라인 모두 동일한 Qwen3.8 Ollama alias(`legal-harness-qwen38-q8`),
  동일한 226문항, 동일한 corpus를 쓰므로 모델·데이터는 통제되어 있다.

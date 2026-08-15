---
project: "조문 근거 충족도 기반 스킬 하네스"
document_part: "표기법·변수명·블록별 책임"
source_version: "1.0-handoff-split"
last_updated: "2026-08-11"
---

[← 시작 문서로 돌아가기](00_START_HERE.md)

# 5. 표기법과 변수명

## 5.1 표기법

| 표기 | 뜻 |
|---|---|
| `[]` | 배열/List. 여러 객체 또는 값이 들어갈 수 있음 |
| `{}` | 객체/Object. 여러 필드를 가진 구조 |
| `_id` | 단일 식별자 |
| `_ids[]` | 식별자 배열 |
| `snake_case` | JSON 및 코드 필드 이름 |
| `UPPER_CASE` | 제어 행동 또는 enum 값 |
| `candidate_*` | 검색됐지만 아직 답변 근거로 채택되지 않은 후보 |
| `accepted_*` | 판정 후 답변에 사용할 수 있도록 승인된 것 |
| `critical` | 없으면 핵심 법률 결론을 충분히 정당화할 수 없는 근거 항목 |

## 5.2 최종 데이터 이름

```text
normalized_question
run_id

legal_issues[]
required_evidence_items[]
retrieval_requests[]

candidate_provisions[]

evidence_links[]
coverage_assessments[]
missing_evidence_items[]
evidence_conflicts[]

accepted_provision_ids[]
gap_retrieval_requests[]

claims[]
claim_citations[]
answer
abstention_reason
```

## 5.3 `normalized_question`

결정적 text normalization만 수행한다.

허용:

- 앞뒤 공백 제거
- 연속 공백 및 줄바꿈 통일
- Unicode normalization
- 형식적 조문 번호 표기 통일
- 원 질문 별도 보존

금지:

- 질문 요약
- 법률 용어 의미 치환
- 법적 쟁점 추론
- 검색 목적의 의미 재작성

의미 처리는 S1부터 시작한다.

---

# 6. 블록별 책임

## 6.1 입력 처리

**입력**: 사용자 원질의 또는 KoBLEX 문항  
**출력**: `normalized_question`, `run_id`

역할:

- 형식 검증
- 문자 및 공백 정규화
- 실행 ID 생성
- 원 질문 보존

이 단계에서는 LLM을 사용하지 않고 법률적 판단을 하지 않는다.

## 6.2 S1 `INITIAL_PLAN`

**패키지**: `legal_issue_and_query_planning`  
**Entry point**: `INITIAL_PLAN`

입력:

- `normalized_question`
- `query_history[]`

출력:

- `legal_issues[]`
- `required_evidence_items[]`
- `retrieval_requests[]`

역할:

- 질문을 해결하는 데 필요한 최소 법률 쟁점 식별
- 쟁점별 필수 법적 근거 의무 정의
- 쟁점별 다채널 검색 요청 생성

제약:

- 모든 질문을 억지로 복수 쟁점으로 분해하지 않는다.
- `legal_issues[]` 최소 크기는 1이다.
- 원 질문은 Run State에 보존한다.

### 세 검색 질의 채널

1. **Provision-style Query**: 조문 문체에 가까운 검색 질의
2. **Sparse Keyword Query**: 법률 명사, 요건, 행위 중심 키워드 질의
3. **Statute-aware Query**: 후보 법령명과 법률 쟁점을 포함한 질의

후보 법령명은 힌트로 사용하며 전체 검색 범위를 강제 제한하지 않는다.

## 6.3 최초 조문 검색 파이프라인

**구현 Tool ID 선택 사항**: `T-R` / `retrieve_provisions`  
**논문 피겨 권장 이름**: `Initial Provision Retrieval Pipeline`

입력:

- `retrieval_requests[]`

출력:

- `candidate_provisions[]`

처리:

```text
BM25 또는 KURE-v1
→ 질의 채널별 Top-100
→ 질의 채널 단위 RRF
→ 조문 ID 중복 제거
→ BGE Cross-Encoder Reranking
→ Top-10
```

검색기는 관련 후보를 찾는 역할만 하며, 근거 충분성을 판단하지 않는다.

## 6.4 S2 `ASSESS_COVERAGE`

**패키지**: `provision_coverage_assessment`

입력:

- `legal_issues[]`
- `required_evidence_items[]`
- `candidate_provisions[]`
- 현재 Run State

출력:

- `evidence_links[]`
- `coverage_assessments[]`
- `missing_evidence_items[]`
- `evidence_conflicts[]`

역할:

- 쟁점–근거 항목–조문 ID 연결
- 실제 지지 구간 `support_spans` 기록
- 각 필수 근거의 충족 상태 판정

### 상태 enum

| 상태 | 의미 |
|---|---|
| `covered` | 필요한 근거가 실제 조문과 연결되고 충분히 확보됨 |
| `partially_covered` | 관련 근거는 있으나 요구되는 근거 의무를 완전히 만족하지 못함 |
| `uncovered` | 해당 근거를 지지할 조문을 확보하지 못함 |
| `conflicting` | 적용 범위·예외·시점 등에서 해소되지 않은 충돌이 있음 |

S2는 다음 행동을 선택하지 않는다. 구조화된 판정만 반환한다.

## 6.5 Provision-Coverage Control Policy

입력:

- `coverage_assessments[]`
- `missing_evidence_items[]`
- `evidence_conflicts[]`
- 남은 검색 예산
- 질의 이력
- 무진척 상태

출력 action:

- `RETRIEVE_GAP`
- `GENERATE`
- `ABSTAIN`

S2와 Policy를 분리하는 이유는 판정 모델의 효과와 제어 정책의 효과를 인과적으로 분리하기 위함이다.

## 6.6 S1 `GAP_QUERY_PLAN`

**동일 패키지의 두 번째 Entry point**: `GAP_QUERY_PLAN`

입력:

- critical인 `missing_evidence_items[]`
- `evidence_conflicts[]`
- 기존 accepted evidence 요약
- `query_history[]`
- `seen_provision_ids[]`

출력:

- `gap_retrieval_requests[]`

원 질문을 반복하지 않고 현재 부족한 근거를 직접 겨냥하는 비중복 검색 요청을 만든다.

## 6.7 추가 조문 검색

**논문 피겨 권장 이름**: `Additional Provision Retrieval`

입력:

- `gap_retrieval_requests[]`

출력:

- 새로운 `candidate_provisions[]`

최초 검색과 동일하게 동결된 검색기, RRF, BGE 설정을 사용한다. 새 후보 조문은 반드시 S2에 누적 입력되어 재판정을 거친다.

## 6.8 S3 `GENERATE_ANSWER`

**패키지**: `grounded_legal_answer_generation`

입력:

- 원 질문
- `legal_issues[]`
- accepted evidence links
- accepted provision texts

출력:

- `claims[]`
- `claim_citations[]`
- `answer`

검색 후보 전체를 전달하지 않는다. S2에서 채택된 조문만 사용한다.

## 6.9 Citation Integrity Check

**구현 Tool ID 선택 사항**: `T-C` / `validate_citation_integrity`

검사:

1. 인용한 조문 ID가 동결 코퍼스에 존재하는가
2. 인용 ID가 `accepted_provision_ids[]`에 포함되는가
3. 인용 본문이 동결 스냅샷과 일치하는가
4. 인용이 필요한 각 주장에 최소 하나의 조문 ID가 연결되는가

출력:

- `PASS`
- 또는 `FAIL` + `validation_errors[]`

이 도구는 법적 타당성, entailment, 결론의 정당성을 판정하지 않는다.

## 6.10 Response Assembly & Return

입력:

- 검증된 답변
- 또는 구조화된 abstention 정보

출력:

- 최종 답변
- 또는 근거 불충분 보류 응답

사용자에게 내부 action enum이 아니라 이해 가능한 메시지를 반환한다.

## 6.11 LLM

- 모델: `Qwen3.6-27B`
- S1 INITIAL, S1 GAP, S2, S3가 동일 체크포인트를 사용
- 검색, Policy, Citation Integrity, Response Assembly는 Qwen을 직접 사용하지 않음

## 6.12 법령 코퍼스·검색 인덱스

구성:

- KoBLEX 법령 스냅샷
- BM25 Index
- KURE-v1 Vector Index

사용:

- 최초 검색
- 추가 검색
- Citation Integrity의 원문/ID 검증

BGE는 저장 자원이 아니라 검색 파이프라인 내부 reranker이다.

---

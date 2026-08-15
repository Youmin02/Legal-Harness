---
project: "조문 근거 충족도 기반 스킬 하네스"
document_part: "Run State·제어 정책·ABSTAIN"
source_version: "1.0-handoff-split"
last_updated: "2026-08-11"
---

[← 시작 문서로 돌아가기](00_START_HERE.md)

# 8. Run State와 제어 정책

## 8.1 최종 Run State

```text
RunState = {
  question,
  normalized_question,
  run_id,
  phase,

  legal_issues[],
  required_evidence_items[],

  provision_assessments[],
  accepted_provision_ids[],
  missing_critical_items[],
  evidence_conflicts[],

  query_history[],
  seen_provision_ids[],

  remaining_round_budget,
  remaining_request_budget,
  no_progress_rounds,

  last_validated_event,
  action_trace[]
}
```

`accepted_provision_ids[]`는 독립 원본 상태가 아니다. `provision_assessments[]` 또는 accepted `evidence_links[]`에서 파생한 조문 ID의 합집합이다.

## 8.2 Critical blocker

```text
critical_blockers = critical evidence items whose status is in
{partially_covered, uncovered, conflicting}
```

non-critical 근거가 부족한 것만으로는 반드시 생성을 막지 않는다.

## 8.3 최종 Policy

```text
IF critical_blockers is empty
   AND unresolved critical conflicts are empty:
    GENERATE

ELSE IF retrieval budget remains
        AND a non-duplicate gap retrieval request can be produced
        AND no_progress_rounds < 2:
    RETRIEVE_GAP

ELSE:
    ABSTAIN
```

## 8.4 진척 판정

```text
progress =
  new_unique_provision_ids > 0
  OR any critical status improves:
     uncovered → partially_covered
     uncovered → covered
     partially_covered → covered
     conflicting → partially_covered
     conflicting → covered
```

## 8.5 검색 예산

현재 기본값:

```text
총 retrieval rounds = 3
Round 1 = initial retrieval
Round 2 = first gap retrieval
Round 3 = final gap retrieval
```

- 정답 hop 수를 실행 입력이나 종료 조건으로 사용하지 않는다.
- 동일 normalized query 재사용 금지
- 연속 2회 무진척이면 조기 중단

---

# 9. ABSTAIN 설계

## 9.1 정의

```text
ABSTAIN ≠ 무응답
ABSTAIN ≠ 시스템 오류
```

`ABSTAIN`은 시스템이 정상 작동했지만 필수 근거를 검색 예산 내에 충분히 확보하지 못한 정상 종료다.

## 9.2 실행 경로

```text
Policy
→ ABSTAIN
→ Response Assembly
→ 사용자에게 근거 부족 보류 응답
```

S3와 Citation Integrity를 호출하지 않는다.

## 9.3 구조화 출력

```json
{
  "status": "ABSTAIN",
  "abstention_reason": "INSUFFICIENT_CRITICAL_EVIDENCE",
  "missing_critical_evidence_items": [
    {
      "evidence_item_id": "E3",
      "issue_id": "I1",
      "evidence_type": "exception_or_exclusion",
      "description": "적용 예외 또는 배제 규정"
    }
  ],
  "unresolved_conflicts": [],
  "termination_reason": "RETRIEVAL_BUDGET_EXHAUSTED",
  "retrieval_rounds_used": 3,
  "user_message": "현재 확보된 조문만으로는 필수 근거가 충분하지 않아 답변을 보류합니다."
}
```

## 9.4 Reason codes

**법률 근거 상태**

```text
INSUFFICIENT_CRITICAL_EVIDENCE
UNRESOLVED_EVIDENCE_CONFLICT
```

**검색 종료 사유**

```text
RETRIEVAL_BUDGET_EXHAUSTED
NO_RETRIEVAL_PROGRESS
NO_VALID_GAP_QUERY
MAX_RETRIEVAL_ROUNDS_REACHED
```

## 9.5 사용자 메시지 예시

> 현재 확보된 조문만으로는 질문의 핵심 법률 쟁점을 충분히 판단할 수 없어 법률 결론을 생성하지 않았습니다. 미충족 필수 근거는 예외·단서 규정과 적용 기한에 관한 규정입니다. 추가 검색 예산이 소진되어 답변을 보류합니다.

## 9.6 `EXECUTION_FAILURE`와 구분

| 상태 | 의미 |
|---|---|
| `ABSTAIN` | 정상 작동했으나 근거 부족 |
| `EXECUTION_FAILURE` | Schema 오류, 도구 실패, 잘못된 참조 등 실행 실패 |

---

---
project: "조문 근거 충족도 기반 스킬 하네스"
document_part: "대표 데이터 계약"
source_version: "1.0-handoff-split"
last_updated: "2026-08-11"
---

[← 시작 문서로 돌아가기](00_START_HERE.md)

# 7. 대표 데이터 계약

## 7.1 `retrieval_request`

```json
{
  "request_id": "RQ-I1-01",
  "issue_id": "I1",
  "evidence_item_id": "E1",
  "query_channel": "provision_style",
  "query_text": "...",
  "top_k": 100
}
```

`query_channel` 후보:

```text
provision_style
sparse_keyword
statute_aware
```

## 7.2 `candidate_provision`

```json
{
  "provision_id": "STATUTE_ARTICLE_ID",
  "statute_name": "법령명",
  "provision_text": "조문 본문",
  "issue_id": "I1",
  "source_request_id": "RQ-I1-01",
  "retrieval_round": 1,
  "first_stage_score": 0.0,
  "fusion_rank": 1,
  "rerank_score": 0.0
}
```

## 7.3 `required_evidence_item`

```json
{
  "evidence_item_id": "E1",
  "issue_id": "I1",
  "evidence_type": "application_requirement",
  "description": "성립·적용 요건에 관한 근거",
  "critical": true
}
```

## 7.4 `evidence_link`

```json
{
  "issue_id": "I1",
  "evidence_item_id": "E1",
  "provision_id": "STATUTE_ARTICLE_ID",
  "support_spans": [
    {
      "start_char": 10,
      "end_char": 68
    }
  ],
  "assessment": "accepted"
}
```

## 7.5 `coverage_assessment`

```json
{
  "evidence_item_id": "E1",
  "status": "covered",
  "linked_provision_ids": ["STATUTE_ARTICLE_ID"],
  "rationale": "해당 조문이 필수 요건을 명시함"
}
```

## 7.6 `claim_citation`

```json
{
  "claim_id": "C1",
  "provision_ids": ["STATUTE_ARTICLE_ID"]
}
```

---

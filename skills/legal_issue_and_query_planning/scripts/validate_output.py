#!/usr/bin/env python3
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path


def load(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def norm(text):
    return " ".join(unicodedata.normalize("NFKC", text).lower().split())


def history_queries(data):
    values = set()
    for item in (data or {}).get("query_history", []):
        if isinstance(item, str):
            values.add(norm(item))
        elif isinstance(item, dict):
            value = item.get("normalized_query") or item.get("query_text")
            if isinstance(value, str):
                values.add(norm(value))
    return values


def unique_ids(items, key, pattern, errors):
    seen = set()
    for item in items:
        value = item.get(key)
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            errors.append(f"invalid {key}: {value!r}")
        elif value in seen:
            errors.append(f"duplicate {key}: {value}")
        seen.add(value)
    return seen


def validate_common(out, inp, errors):
    if out.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if out.get("skill_id") != "S1":
        errors.append("skill_id must be S1")
    if out.get("mode") not in {"INITIAL_PLAN", "GAP_QUERY_PLAN"}:
        errors.append("invalid mode")
    if out.get("status") not in {"ok", "error"}:
        errors.append("status must be ok or error")
    if inp:
        if out.get("run_id") != inp.get("run_id"):
            errors.append("run_id does not match input")
        if out.get("mode") != inp.get("mode"):
            errors.append("mode does not match input")
    forbidden = {"accepted_provision_ids", "policy_action", "action", "coverage_assessments"}
    present = sorted(forbidden.intersection(out))
    if present:
        errors.append(f"harness/S2-owned fields are forbidden: {present}")


def validate_requests(requests, issues, evidence, prior_queries, allowed_channels, max_per_issue, errors, gap=False):
    pattern = r"GRQ[1-9][0-9]*" if gap else r"RQ[1-9][0-9]*"
    unique_ids(requests, "request_id", pattern, errors)
    current_queries = set()
    per_issue = {}
    evidence_by_id = {item.get("evidence_item_id"): item for item in evidence}
    for request in requests:
        issue_id = request.get("issue_id")
        evidence_id = request.get("evidence_item_id")
        if issue_id not in issues:
            errors.append(f"unknown issue_id in request: {issue_id}")
        if evidence_id not in evidence_by_id:
            errors.append(f"unknown evidence_item_id in request: {evidence_id}")
        elif evidence_by_id[evidence_id].get("issue_id") != issue_id:
            errors.append(f"request issue/evidence mismatch: {request.get('request_id')}")
        channel = request.get("query_channel")
        if channel not in allowed_channels:
            errors.append(f"query channel not allowed: {channel}")
        query = request.get("query_text")
        if not isinstance(query, str) or not norm(query):
            errors.append(f"empty query_text: {request.get('request_id')}")
        else:
            normalized = norm(query)
            if normalized in current_queries:
                errors.append(f"duplicate normalized query in output: {query}")
            if normalized in prior_queries:
                errors.append(f"query repeats query_history: {query}")
            current_queries.add(normalized)
        per_issue[issue_id] = per_issue.get(issue_id, 0) + 1
        if gap and request.get("source_assessment_status") not in {"partially_covered", "uncovered", "conflicting"}:
            errors.append(f"invalid source_assessment_status: {request.get('request_id')}")
    for issue_id, count in per_issue.items():
        if count > max_per_issue:
            errors.append(f"{issue_id} has {count} requests; max is {max_per_issue}")


def validate(out, inp):
    errors = []
    validate_common(out, inp, errors)
    if out.get("status") == "error":
        error = out.get("error")
        if not isinstance(error, dict) or error.get("code") not in {"INVALID_INPUT", "BUDGET_EXHAUSTED", "CONTRACT_UNSATISFIABLE"}:
            errors.append("invalid error envelope")
        return errors

    constraints = (inp or {}).get("constraints", {})
    allowed = set(constraints.get("allowed_query_channels", ["provision_style", "sparse_keywords", "statute_aware"]))
    max_per_issue = constraints.get("max_requests_per_issue", 3)
    prior = history_queries(inp)

    if out.get("mode") == "INITIAL_PLAN":
        issues = out.get("legal_issues", [])
        evidence = out.get("required_evidence_items", [])
        requests = out.get("retrieval_requests", [])
        issue_ids = unique_ids(issues, "issue_id", r"I[1-9][0-9]*", errors)
        evidence_ids = unique_ids(evidence, "evidence_item_id", r"E[1-9][0-9]*", errors)
        if not issue_ids or not evidence_ids or not requests:
            errors.append("INITIAL_PLAN requires non-empty issues, evidence, and requests")
        for item in evidence:
            if item.get("issue_id") not in issue_ids:
                errors.append(f"evidence references unknown issue: {item.get('evidence_item_id')}")
        validate_requests(requests, issue_ids, evidence, prior, allowed, max_per_issue, errors)
        targeted = {r.get("evidence_item_id") for r in requests}
        for item in evidence:
            if item.get("critical") is True and item.get("evidence_item_id") not in targeted:
                errors.append(f"critical evidence lacks a retrieval request: {item.get('evidence_item_id')}")
    else:
        requests = out.get("gap_retrieval_requests", [])
        targets = out.get("target_evidence_item_ids", [])
        if not inp:
            errors.append("GAP_QUERY_PLAN validation requires --input")
            return errors
        issues = {x.get("issue_id") for x in inp.get("legal_issues", [])}
        evidence = inp.get("required_evidence_items", [])
        evidence_ids = {x.get("evidence_item_id") for x in evidence}
        unresolved = {x.get("evidence_item_id") for x in inp.get("missing_evidence_items", [])}
        unresolved.update(x.get("evidence_item_id") for x in inp.get("evidence_conflicts", []))
        if len(targets) != len(set(targets)):
            errors.append("target_evidence_item_ids must be unique")
        if set(targets) - evidence_ids:
            errors.append("target list contains unknown evidence items")
        if set(targets) - unresolved:
            errors.append("target list contains resolved evidence items")
        request_targets = {r.get("evidence_item_id") for r in requests}
        if set(targets) != request_targets:
            errors.append("target_evidence_item_ids must equal request targets")
        if len(requests) > inp.get("remaining_request_budget", 0):
            errors.append("gap requests exceed remaining_request_budget")
        validate_requests(requests, issues, evidence, prior, allowed, max_per_issue, errors, gap=True)
    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate S1 output semantics")
    parser.add_argument("output")
    parser.add_argument("--input")
    args = parser.parse_args()
    try:
        output = load(args.output)
        input_data = load(args.input) if args.input else None
        errors = validate(output, input_data)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print("VALID: S1 output contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path


def load(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def unique(items, key, pattern, errors):
    seen = set()
    for item in items:
        value = item.get(key)
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            errors.append(f"invalid {key}: {value!r}")
        elif value in seen:
            errors.append(f"duplicate {key}: {value}")
        seen.add(value)
    return seen


def validate_preconditions(input_data, errors):
    authorization = input_data.get("authorization", {})
    if authorization.get("action") != "GENERATE" or authorization.get("authorized_by") != "PROVISION_COVERAGE_POLICY":
        errors.append("generation is not authorized by the provision coverage policy")
    evidence = {x.get("evidence_item_id"): x for x in input_data.get("required_evidence_items", [])}
    assessments = {x.get("evidence_item_id"): x for x in input_data.get("coverage_assessments", [])}
    for evidence_id, item in evidence.items():
        if item.get("critical") is True and assessments.get(evidence_id, {}).get("status") != "covered":
            errors.append(f"critical evidence is not covered: {evidence_id}")
    if not input_data.get("accepted_provisions"):
        errors.append("accepted_provisions must not be empty")


def validate(output, input_data):
    errors = []
    if output.get("schema_version") != "1.0" or output.get("skill_id") != "S3":
        errors.append("schema_version/skill_id must be 1.0/S3")
    if output.get("mode") != "GENERATE_ANSWER":
        errors.append("mode must be GENERATE_ANSWER")
    if output.get("status") not in {"ok", "error"}:
        errors.append("status must be ok or error")
    if input_data and output.get("run_id") != input_data.get("run_id"):
        errors.append("run_id does not match input")
    forbidden = {"policy_action", "action", "abstention_reason", "citation_check_result", "PASS"}
    present = sorted(forbidden.intersection(output))
    if present:
        errors.append(f"harness/tool-owned fields are forbidden: {present}")
    if output.get("status") == "error":
        error = output.get("error")
        allowed = {"INVALID_INPUT", "GENERATION_NOT_AUTHORIZED", "UNCOVERED_CRITICAL_EVIDENCE", "CONTRACT_UNSATISFIABLE"}
        if not isinstance(error, dict) or error.get("code") not in allowed:
            errors.append("invalid error envelope")
        return errors
    if not input_data:
        errors.append("success validation requires --input")
        return errors
    validate_preconditions(input_data, errors)

    answer = output.get("answer", "")
    max_chars = input_data.get("generation_constraints", {}).get("max_answer_chars")
    if isinstance(max_chars, int) and len(answer) > max_chars:
        errors.append(f"answer exceeds max_answer_chars: {len(answer)} > {max_chars}")
    claims = output.get("claims", [])
    citations = output.get("claim_citations", [])
    claim_ids = unique(claims, "claim_id", r"C[1-9][0-9]*", errors)
    unique(citations, "citation_id", r"CT[1-9][0-9]*", errors)
    claim_by_id = {x.get("claim_id"): x for x in claims}
    accepted = input_data.get("accepted_provisions", [])
    accepted_by_id = {x.get("provision_id"): x for x in accepted}
    if len(accepted_by_id) != len(accepted):
        errors.append("accepted provision IDs must be unique")

    citations_by_claim = {}
    for citation in citations:
        citation_id = citation.get("citation_id")
        claim_id = citation.get("claim_id")
        provision_id = citation.get("provision_id")
        citations_by_claim.setdefault(claim_id, []).append(citation)
        if claim_id not in claim_ids:
            errors.append(f"citation references unknown claim: {citation_id}")
        provision = accepted_by_id.get(provision_id)
        if not provision:
            errors.append(f"citation uses non-accepted provision: {citation_id}")
        else:
            quote = citation.get("quoted_text")
            if not isinstance(quote, str) or quote not in provision.get("text", ""):
                errors.append(f"quoted_text is not exact accepted source text: {citation_id}")
        marker = citation.get("answer_marker")
        expected_marker = f"[{citation_id}]"
        if marker != expected_marker:
            errors.append(f"answer_marker must be {expected_marker}: {citation_id}")
        elif marker not in answer:
            errors.append(f"answer is missing citation marker: {citation_id}")

    required_types = {"legal_rule", "application", "exception", "procedure", "remedy"}
    for claim_id, claim in claim_by_id.items():
        text = claim.get("text")
        if not isinstance(text, str) or text not in answer:
            errors.append(f"claim text must be an exact substring of answer: {claim_id}")
        if claim.get("claim_type") in required_types and claim.get("citation_required") is not True:
            errors.append(f"substantive legal claim must require citation: {claim_id}")
        if claim.get("citation_required") is True and not citations_by_claim.get(claim_id):
            errors.append(f"citation-required claim lacks citation: {claim_id}")
    for claim_id in citations_by_claim:
        if claim_id not in claim_by_id:
            errors.append(f"citations contain unknown claim: {claim_id}")
    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate S3 output semantics")
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
    print("VALID: S3 output contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

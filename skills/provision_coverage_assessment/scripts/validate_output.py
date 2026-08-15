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


def validate(output, input_data):
    errors = []
    if output.get("schema_version") != "1.0" or output.get("skill_id") != "S2":
        errors.append("schema_version/skill_id must be 1.0/S2")
    if output.get("mode") != "ASSESS_COVERAGE":
        errors.append("mode must be ASSESS_COVERAGE")
    if output.get("status") not in {"ok", "error"}:
        errors.append("status must be ok or error")
    if input_data:
        if output.get("run_id") != input_data.get("run_id"):
            errors.append("run_id does not match input")
        if input_data.get("mode") != "ASSESS_COVERAGE":
            errors.append("input mode must be ASSESS_COVERAGE")
    forbidden = {"accepted_provision_ids", "policy_action", "action", "answer", "claim_citations"}
    present = sorted(forbidden.intersection(output))
    if present:
        errors.append(f"harness/S3-owned fields are forbidden: {present}")
    if output.get("status") == "error":
        error = output.get("error")
        if not isinstance(error, dict) or error.get("code") not in {"INVALID_INPUT", "MISSING_REQUIRED_EVIDENCE", "CONTRACT_UNSATISFIABLE"}:
            errors.append("invalid error envelope")
        return errors
    if not input_data:
        errors.append("success validation requires --input")
        return errors

    evidence_items = input_data.get("required_evidence_items", [])
    evidence_by_id = {x.get("evidence_item_id"): x for x in evidence_items}
    if len(evidence_by_id) != len(evidence_items):
        errors.append("input evidence IDs must be unique")
    provisions = input_data.get("candidate_provisions", [])
    provision_by_id = {x.get("provision_id"): x for x in provisions}
    if len(provision_by_id) != len(provisions):
        errors.append("input candidate provision IDs must be unique")

    links = output.get("evidence_links", [])
    assessments = output.get("coverage_assessments", [])
    missing = output.get("missing_evidence_items", [])
    conflicts = output.get("evidence_conflicts", [])
    unique(links, "link_id", r"L[1-9][0-9]*", errors)
    assessment_ids = unique(assessments, "evidence_item_id", r"E[1-9][0-9]*", errors)
    missing_ids = unique(missing, "evidence_item_id", r"E[1-9][0-9]*", errors)
    unique(conflicts, "conflict_id", r"CF[1-9][0-9]*", errors)
    conflict_evidence_ids = [x.get("evidence_item_id") for x in conflicts]
    if len(conflict_evidence_ids) != len(set(conflict_evidence_ids)):
        errors.append("only one conflict object is allowed per evidence item")

    expected = set(evidence_by_id)
    if assessment_ids != expected:
        errors.append(f"assessments must cover every evidence item exactly once: expected {sorted(expected)}, got {sorted(assessment_ids)}")

    links_by_evidence = {}
    for link in links:
        evidence_id = link.get("evidence_item_id")
        provision_id = link.get("provision_id")
        links_by_evidence.setdefault(evidence_id, []).append(link)
        if evidence_id not in expected:
            errors.append(f"link references unknown evidence item: {evidence_id}")
        provision = provision_by_id.get(provision_id)
        if not provision:
            errors.append(f"link references unknown candidate provision: {provision_id}")
        else:
            quote = link.get("quoted_text")
            if not isinstance(quote, str) or quote not in provision.get("text", ""):
                errors.append(f"quoted_text is not exact source text: {link.get('link_id')}")
        if link.get("relation") not in {"supports", "partially_supports", "conflicts"}:
            errors.append(f"invalid link relation: {link.get('link_id')}")

    conflict_id_set = set(conflict_evidence_ids)
    assessment_by_id = {x.get("evidence_item_id"): x for x in assessments}
    for evidence_id, assessment in assessment_by_id.items():
        status = assessment.get("status")
        linked = assessment.get("linked_provision_ids", [])
        actual_linked = {x.get("provision_id") for x in links_by_evidence.get(evidence_id, [])}
        if len(linked) != len(set(linked)):
            errors.append(f"linked_provision_ids must be unique: {evidence_id}")
        if set(linked) != actual_linked:
            errors.append(f"assessment/link provision mismatch: {evidence_id}")
        if set(linked) - set(provision_by_id):
            errors.append(f"assessment uses non-candidate provision: {evidence_id}")
        satisfied = assessment.get("satisfied_aspects", [])
        missing_aspects = assessment.get("missing_aspects", [])
        if status == "covered":
            if not linked or missing_aspects or evidence_id in conflict_id_set:
                errors.append(f"covered consistency failure: {evidence_id}")
        elif status == "partially_covered":
            if not linked or not missing_aspects or evidence_id in conflict_id_set:
                errors.append(f"partially_covered consistency failure: {evidence_id}")
        elif status == "uncovered":
            if linked or satisfied or not missing_aspects or evidence_id in conflict_id_set:
                errors.append(f"uncovered consistency failure: {evidence_id}")
        elif status == "conflicting":
            if not linked or evidence_id not in conflict_id_set:
                errors.append(f"conflicting consistency failure: {evidence_id}")
        else:
            errors.append(f"invalid coverage status: {evidence_id}")

    expected_missing = {eid for eid, a in assessment_by_id.items() if a.get("status") != "covered"}
    if missing_ids != expected_missing:
        errors.append("missing_evidence_items must equal all non-covered assessments")
    expected_conflicts = {eid for eid, a in assessment_by_id.items() if a.get("status") == "conflicting"}
    if conflict_id_set != expected_conflicts:
        errors.append("evidence_conflicts must equal all conflicting assessments")
    for item in missing:
        evidence = evidence_by_id.get(item.get("evidence_item_id"), {})
        if item.get("issue_id") != evidence.get("issue_id") or item.get("critical") != evidence.get("critical"):
            errors.append(f"missing item does not preserve issue/critical fields: {item.get('evidence_item_id')}")
    for conflict in conflicts:
        if set(conflict.get("provision_ids", [])) - set(provision_by_id):
            errors.append(f"conflict uses non-candidate provision: {conflict.get('conflict_id')}")
    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate S2 output semantics")
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
    print("VALID: S2 output contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

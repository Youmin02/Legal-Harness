"""Execute the externally supplied S1/S2/S3 skill pack through local Ollama.

The deterministic harness deliberately uses compact internal contracts.  The
skill pack keeps richer, model-facing JSON contracts.  This adapter is the
only place where those representations meet: it prepares each skill input,
validates the model output with the skill's own validator, and maps the result
back to the harness contract.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from harness.interfaces import SkillExecutionError


SKILL_IDS = {
    "legal_issue_and_query_planning": "S1",
    "provision_coverage_assessment": "S2",
    "grounded_legal_answer_generation": "S3",
}
EXTERNAL_CHANNELS = {
    "sparse_keyword": "sparse_keywords",
}
INTERNAL_CHANNELS = {
    "sparse_keywords": "sparse_keyword",
}


class LocalOllamaSkillExecutor:
    """Call local Qwen for skills while keeping all control in the harness."""

    def __init__(
        self,
        skills_root: Path,
        model: str,
        endpoint: str = "http://127.0.0.1:11434/api/generate",
        timeout_seconds: int = 600,
        num_ctx: int = 32768,
        max_attempts: int = 2,
        generator: Optional[Callable[[str], str]] = None,
    ):
        if timeout_seconds < 1 or num_ctx < 1024 or max_attempts < 1:
            raise ValueError("timeout, num_ctx, and max_attempts must be positive")
        self.skills_root = skills_root
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.num_ctx = num_ctx
        self.max_attempts = max_attempts
        self.generator = generator
        self._resources: Dict[str, Dict[str, str]] = {}
        self._validators: Dict[str, Callable[[Mapping[str, Any], Mapping[str, Any]], List[str]]] = {}
        for skill_name in SKILL_IDS:
            self._load_skill(skill_name)

    def execute(
        self,
        skill_name: str,
        entry_point: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        if skill_name not in SKILL_IDS:
            raise SkillExecutionError("unknown local skill: %s" % skill_name)
        skill_input = self._build_skill_input(skill_name, entry_point, payload)
        errors: List[str] = []
        repair_note = ""
        for attempt in range(1, self.max_attempts + 1):
            prompt = self._prompt(skill_name, entry_point, skill_input, repair_note)
            try:
                raw_text = self._generate(prompt, self._max_tokens(skill_name))
                skill_output = self._parse_json_object(raw_text)
                skill_output = self._normalize_harness_owned_fields(
                    skill_name, entry_point, skill_input, skill_output
                )
                validation_errors = self._validators[skill_name](skill_output, skill_input)
                if validation_errors:
                    errors = validation_errors
                    repair_note = (
                        "Your previous JSON failed validation: "
                        + "; ".join(validation_errors)
                        + ". Return a corrected replacement JSON. Preserve valid fields and rebuild "
                        "linked_provision_ids from evidence_links. Previous JSON: "
                        + json.dumps(skill_output, ensure_ascii=False, separators=(",", ":"))
                    )
                    continue
                if skill_output.get("status") == "error":
                    error = skill_output.get("error", {})
                    raise SkillExecutionError(
                        "%s returned %s: %s"
                        % (skill_name, error.get("code", "UNKNOWN"), error.get("message", ""))
                    )
                return self._adapt_output(skill_name, entry_point, skill_output, skill_input)
            except (SkillExecutionError, ValueError) as exc:
                errors = [str(exc)]
                repair_note = "Your previous response was unusable: " + str(exc)
        raise SkillExecutionError(
            "%s did not produce a valid %s result after %d attempts: %s"
            % (skill_name, entry_point, self.max_attempts, "; ".join(errors))
        )
    def _normalize_harness_owned_fields(
        self,
        skill_name: str,
        entry_point: str,
        skill_input: Mapping[str, Any],
        output: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Assign run and request IDs; their values carry no legal judgment."""
        normalized = dict(output)
        normalized["run_id"] = skill_input["run_id"]
        if skill_name == "provision_coverage_assessment":
            return self._normalize_s2_output(normalized, skill_input)
        if skill_name != "legal_issue_and_query_planning":
            return normalized
        request_key = "gap_retrieval_requests" if entry_point == "GAP_QUERY_PLAN" else "retrieval_requests"
        requests = normalized.get(request_key)
        if not isinstance(requests, list):
            return normalized
        prefix = "GRQ" if entry_point == "GAP_QUERY_PLAN" else "RQ"
        for index, request in enumerate(requests, start=1):
            if isinstance(request, dict):
                request["request_id"] = ("GRQ-R%d-%d" % (int(skill_input.get("next_retrieval_round", 1)), index) if entry_point == "GAP_QUERY_PLAN" else "RQ%d" % index)
        if entry_point == "INITIAL_PLAN":
            issues_by_id = {
                issue.get("issue_id"): issue
                for issue in self._list(normalized, "legal_issues")
                if isinstance(issue, Mapping)
            }
            emitted_queries = set()
            for index, request in enumerate(requests, start=1):
                if not isinstance(request, dict):
                    continue
                query = request.get("query_text")
                contextual_query = self._with_source_context(query, skill_input)
                if not isinstance(query, str) or self._normalized_query(contextual_query) in emitted_queries:
                    issue = issues_by_id.get(request.get("issue_id"), {})
                    query = self._fallback_initial_query(issue, index, emitted_queries, skill_input)
                    contextual_query = self._with_source_context(query, skill_input)
                request["query_text"] = contextual_query
                emitted_queries.add(self._normalized_query(contextual_query))

        if entry_point == "GAP_QUERY_PLAN":
            unresolved = [item.get("evidence_item_id") for key in ("missing_evidence_items", "evidence_conflicts") for item in self._list(skill_input, key) if isinstance(item, Mapping)]
            evidence_by_id = {item.get("evidence_item_id"): item for item in self._list(skill_input, "required_evidence_items") if isinstance(item, Mapping)}
            prior_queries = {
                self._normalized_query(item.get("query_text") or item.get("normalized_query"))
                for item in self._list(skill_input, "query_history")
                if isinstance(item, Mapping) and isinstance(item.get("query_text") or item.get("normalized_query"), str)
            }
            emitted_queries = set(prior_queries)
            for index, request in enumerate(requests, start=1):
                if not isinstance(request, dict):
                    continue
                evidence_id = request.get("evidence_item_id")
                if evidence_id not in unresolved and len(unresolved) == 1:
                    evidence_id = unresolved[0]
                    request["evidence_item_id"] = evidence_id
                evidence = evidence_by_id.get(evidence_id)
                if not isinstance(evidence, Mapping):
                    continue
                request["issue_id"] = evidence.get("issue_id")
                query = request.get("query_text")
                contextual_query = self._with_source_context(query, skill_input)
                if not isinstance(query, str) or self._normalized_query(contextual_query) in emitted_queries:
                    query = self._fallback_gap_query(evidence, index, emitted_queries, skill_input)
                    contextual_query = self._with_source_context(query, skill_input)
                request["query_text"] = contextual_query
                emitted_queries.add(self._normalized_query(contextual_query))
            normalized["target_evidence_item_ids"] = list(dict.fromkeys(
                request.get("evidence_item_id") for request in requests if isinstance(request, dict)
            ))
        return normalized

    def _normalize_s2_output(
        self,
        output: Dict[str, Any],
        skill_input: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Canonicalize S2 transport structure without making legal judgments."""
        if output.get("status") != "ok":
            return output
        evidence = [
            item
            for item in self._list(skill_input, "required_evidence_items")
            if isinstance(item, Mapping)
        ]
        evidence_by_id = {item.get("evidence_item_id"): item for item in evidence}
        candidate_ids = {
            item.get("provision_id")
            for item in self._list(skill_input, "candidate_provisions")
            if isinstance(item, Mapping)
        }

        links = []
        seen_links = set()
        for raw in self._list(output, "evidence_links", required=False):
            if not isinstance(raw, Mapping):
                continue
            key = (
                raw.get("evidence_item_id"),
                raw.get("provision_id"),
                raw.get("relation"),
            )
            if key in seen_links:
                continue
            seen_links.add(key)
            link = dict(raw)
            link["link_id"] = "L%d" % (len(links) + 1)
            if key[0] in evidence_by_id and key[1] in candidate_ids:
                link["quoted_text"] = "[FULL_TEXT]"
            links.append(link)
        output["evidence_links"] = links

        links_by_evidence: Dict[str, List[str]] = {}
        for link in links:
            evidence_id = link.get("evidence_item_id")
            provision_id = link.get("provision_id")
            if isinstance(evidence_id, str) and isinstance(provision_id, str):
                links_by_evidence.setdefault(evidence_id, []).append(provision_id)

        first_assessment: Dict[str, Dict[str, Any]] = {}
        for raw in self._list(output, "coverage_assessments", required=False):
            if not isinstance(raw, Mapping):
                continue
            evidence_id = raw.get("evidence_item_id")
            if evidence_id in evidence_by_id and evidence_id not in first_assessment:
                assessment = dict(raw)
                if assessment.get("status") == "partially_covered":
                    if assessment.get("partial_kind") not in {
                        "factual_condition",
                        "legal_support_gap",
                    }:
                        assessment["partial_kind"] = "legal_support_gap"
                else:
                    assessment["partial_kind"] = "not_applicable"
                assessment["linked_provision_ids"] = list(
                    dict.fromkeys(links_by_evidence.get(evidence_id, []))
                )
                first_assessment[evidence_id] = assessment
        output["coverage_assessments"] = [
            first_assessment[evidence_id]
            for evidence_id in evidence_by_id
            if evidence_id in first_assessment
        ]

        prior_missing = {
            item.get("evidence_item_id"): item
            for item in self._list(output, "missing_evidence_items", required=False)
            if isinstance(item, Mapping)
        }
        missing = []
        for evidence_id, assessment in first_assessment.items():
            if assessment.get("status") == "covered":
                continue
            source = dict(prior_missing.get(evidence_id, {}))
            ledger = evidence_by_id[evidence_id]
            aspects = assessment.get("missing_aspects")
            if not isinstance(aspects, list) or not aspects:
                aspects = [
                    assessment.get("rationale") or ledger.get("completion_criteria")
                ]
            source.update(
                {
                    "evidence_item_id": evidence_id,
                    "issue_id": ledger.get("issue_id"),
                    "critical": ledger.get("critical"),
                    "missing_description": source.get("missing_description")
                    or "; ".join(str(item) for item in aspects),
                    "search_focus": source.get("search_focus")
                    or [str(item) for item in aspects if str(item).strip()],
                }
            )
            missing.append(source)
        output["missing_evidence_items"] = missing

        prior_conflicts = {
            item.get("evidence_item_id"): item
            for item in self._list(output, "evidence_conflicts", required=False)
            if isinstance(item, Mapping)
        }
        conflicts = []
        for evidence_id, assessment in first_assessment.items():
            if assessment.get("status") != "conflicting":
                continue
            source = dict(prior_conflicts.get(evidence_id, {}))
            source.update(
                {
                    "conflict_id": "CF%d" % (len(conflicts) + 1),
                    "evidence_item_id": evidence_id,
                    "provision_ids": list(
                        dict.fromkeys(links_by_evidence.get(evidence_id, []))
                    ),
                    "description": source.get("description")
                    or assessment.get("rationale")
                    or "후보 조문 간 적용 충돌",
                    "unresolved_question": source.get("unresolved_question")
                    or "어느 조문이 질문의 사실관계에 적용되는가",
                }
            )
            conflicts.append(source)
        output["evidence_conflicts"] = conflicts
        return output

    @staticmethod
    def _normalized_query(query: str) -> str:
        return " ".join(query.lower().split())

    @staticmethod
    def _source_context_excerpt(source: str) -> str:
        parts = [
            part.strip()
            for part in re.split(r"(?<=[.!?])\s+|\[질문\]", source.strip())
            if part.strip() and part.strip() != "[배경 시나리오]"
        ]
        return " ".join(parts[-2:])[-1200:]

    def _with_source_context(
        self, query: Any, skill_input: Mapping[str, Any]
    ) -> str:
        if not isinstance(query, str):
            return ""
        source = skill_input.get("normalized_question")
        if not isinstance(source, str) or not source.strip():
            return query
        excerpt = self._source_context_excerpt(source)
        query_normalized = self._normalized_query(query)
        source_normalized = self._normalized_query(excerpt)
        if source_normalized in query_normalized:
            return query
        return "%s\n[원문 맥락]\n%s" % (query.strip(), excerpt)

    def _fallback_initial_query(
        self,
        issue: Mapping[str, Any],
        index: int,
        seen: set,
        skill_input: Mapping[str, Any],
    ) -> str:
        base = issue.get("decision_question") or issue.get("issue_statement") or "관련 법률"
        return self._first_unique_contextual_query(
            ["%s 법률 조문" % base, "%s 적용 요건 조문" % base],
            base,
            index,
            seen,
            skill_input,
        )

    def _fallback_gap_query(
        self,
        evidence: Mapping[str, Any],
        index: int,
        seen: set,
        skill_input: Mapping[str, Any],
    ) -> str:
        base = evidence.get("completion_criteria") or evidence.get("description")
        return self._first_unique_contextual_query(
            ["%s 법률 조문" % base, "%s 적용 요건 조문" % base],
            base,
            index,
            seen,
            skill_input,
        )

    def _first_unique_contextual_query(
        self,
        candidates: List[str],
        base: str,
        index: int,
        seen: set,
        skill_input: Mapping[str, Any],
    ) -> str:
        for candidate in candidates:
            contextual = self._with_source_context(candidate, skill_input)
            if self._normalized_query(contextual) not in seen:
                return candidate
        for serial in range(1, 101):
            candidate = "%s 보완 검색 조문 %d-%d" % (base, index, serial)
            contextual = self._with_source_context(candidate, skill_input)
            if self._normalized_query(contextual) not in seen:
                return candidate
        raise SkillExecutionError("could not construct a unique contextual retrieval query")



    @staticmethod
    def _max_tokens(skill_name: str) -> int:
        return {"legal_issue_and_query_planning": 1600,
                "provision_coverage_assessment": 3072,
                "grounded_legal_answer_generation": 3072}[skill_name]

    def _load_skill(self, skill_name: str) -> None:
        directory = self.skills_root / skill_name
        paths = {
            "instructions": directory / "SKILL.md",
            "contract": directory / "references/contract.md",
            "input_schema": directory / "references/input.schema.json",
            "output_schema": directory / "references/output.schema.json",
            "validator": directory / "scripts/validate_output.py",
        }
        missing = [name for name, path in paths.items() if not path.is_file()]
        if missing:
            raise SkillExecutionError("%s is missing: %s" % (skill_name, ", ".join(missing)))
        self._resources[skill_name] = {
            name: path.read_text(encoding="utf-8")
            for name, path in paths.items()
            if name != "validator"
        }
        module_name = "legal_harness_%s_validator" % skill_name
        spec = importlib.util.spec_from_file_location(module_name, paths["validator"])
        if spec is None or spec.loader is None:
            raise SkillExecutionError("cannot load validator for %s" % skill_name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        validator = getattr(module, "validate", None)
        if not callable(validator):
            raise SkillExecutionError("validator for %s has no validate function" % skill_name)
        self._validators[skill_name] = validator

    def _build_skill_input(
        self,
        skill_name: str,
        entry_point: str,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        run_id = self._string(payload, "run_id")
        if skill_name == "legal_issue_and_query_planning":
            return self._planning_input(entry_point, payload, run_id)
        if skill_name == "provision_coverage_assessment":
            if entry_point != "ASSESS_COVERAGE":
                raise SkillExecutionError("S2 supports ASSESS_COVERAGE only")
            return {
                "schema_version": "1.0",
                "mode": entry_point,
                "run_id": run_id,
                "normalized_question": self._string(payload, "normalized_question"),
                "legal_issues": self._list(payload, "legal_issues"),
                "required_evidence_items": self._external_evidence(self._list(payload, "required_evidence_items")),
                "candidate_provisions": self._external_provisions(
                    self._list(payload, "candidate_provisions"), run_id
                ),
                "prior_coverage_assessments": self._list(
                    payload, "prior_coverage_assessments", required=False
                ),
            }
        if skill_name == "grounded_legal_answer_generation":
            if entry_point != "GENERATE_ANSWER":
                raise SkillExecutionError("S3 supports GENERATE_ANSWER only")
            return {
                "schema_version": "1.0",
                "mode": entry_point,
                "run_id": run_id,
                "normalized_question": self._string(payload, "normalized_question"),
                "legal_issues": self._list(payload, "legal_issues"),
                "required_evidence_items": self._external_evidence(self._list(payload, "required_evidence_items")),
                "coverage_assessments": self._list(payload, "coverage_assessments"),
                "accepted_provisions": self._external_provisions(
                    self._list(payload, "accepted_provisions"), run_id, accepted=True
                ),
                "authorization": {
                    "action": "GENERATE",
                    "authorized_by": "PROVISION_COVERAGE_POLICY",
                    "validated_state_version": int(payload.get("state_version", 0)),
                },
                "generation_constraints": {
                    "language": "ko",
                    "max_answer_chars": 6000,
                    "citation_marker_style": "citation_id",
                },
            }
        raise SkillExecutionError("unsupported skill: %s" % skill_name)

    def _planning_input(
        self,
        entry_point: str,
        payload: Mapping[str, Any],
        run_id: str,
    ) -> Dict[str, Any]:
        base = {
            "schema_version": "1.0",
            "mode": entry_point,
            "run_id": run_id,
            "normalized_question": self._string(payload, "normalized_question"),
            "constraints": {
                "allowed_query_channels": ["provision_style", "sparse_keywords", "statute_aware"],
                "max_requests_per_issue": 3,
            },
        }
        if entry_point == "INITIAL_PLAN":
            base.update(
                {
                    "original_question": self._string(payload, "question"),
                    "query_history": self._list(payload, "query_history", required=False),
                }
            )
            return base
        if entry_point != "GAP_QUERY_PLAN":
            raise SkillExecutionError("S1 entry point is invalid: %s" % entry_point)
        base.update(
            {
                "legal_issues": self._list(payload, "legal_issues"),
                "required_evidence_items": self._external_evidence(
                    self._list(payload, "required_evidence_items")
                ),
                "coverage_assessments": self._list(payload, "coverage_assessments"),
                "missing_evidence_items": self._list(payload, "missing_evidence_items"),
                "evidence_conflicts": self._list(payload, "evidence_conflicts"),
                "query_history": self._list(payload, "query_history"),
                "seen_provision_ids": self._list(payload, "seen_provision_ids"),
                "remaining_request_budget": payload.get("remaining_request_budget"),
            }
        )
        if not isinstance(base["remaining_request_budget"], int):
            raise SkillExecutionError("remaining_request_budget must be an integer")
        return base

    def _external_evidence(self, evidence_items: List[Any]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for item in evidence_items:
            if not isinstance(item, Mapping):
                raise SkillExecutionError("required_evidence_items must contain objects")
            result.append(
                {
                    "evidence_item_id": self._string(item, "evidence_item_id"),
                    "issue_id": self._string(item, "issue_id"),
                    "evidence_type": self._string(item, "evidence_type"),
                    "description": self._string(item, "description"),
                    "critical": item.get("critical"),
                    "completion_criteria": item.get("completion_criteria")
                    or self._string(item, "description"),
                }
            )
        return result

    def _external_provisions(
        self,
        candidates: List[Any],
        run_id: str,
        accepted: bool = False,
    ) -> List[Dict[str, Any]]:
        provisions: List[Dict[str, Any]] = []
        for index, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, Mapping):
                raise SkillExecutionError("candidate provisions must contain objects")
            text = self._string(candidate, "provision_text")
            source_provision_id = self._string(candidate, "provision_id")
            provision = {
                "provision_id": source_provision_id if accepted else "C%03d" % index,
                "statute_name": self._string(candidate, "statute_name"),
                "article_label": self._string(candidate, "statute_name"),
                "text": text,
                "source_snapshot_id": "sha256:%s" % hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
            if accepted:
                supported = candidate.get("supported_evidence_item_ids")
                if not isinstance(supported, list) or not supported:
                    supported = [self._string(candidate, "issue_id")]
                provision["supported_evidence_item_ids"] = supported
            else:
                provision["source_provision_id"] = source_provision_id
                provision["retrieval_metadata"] = {
                    "run_id": run_id,
                    "source_request_id": candidate.get("source_request_id"),
                    "retrieval_round": candidate.get("retrieval_round"),
                    "first_stage_score": candidate.get("first_stage_score"),
                    "rerank_score": candidate.get("rerank_score"),
                }
            provisions.append(provision)
        return provisions

    def _prompt(
        self,
        skill_name: str,
        entry_point: str,
        skill_input: Mapping[str, Any],
        repair_note: str,
    ) -> str:
        resources = self._resources[skill_name]
        return """You are executing one external skill inside a deterministic legal QA harness.
Return exactly one JSON object and nothing else. Do not use Markdown code fences.
The harness, not you, controls retrieval, policy, abstention, and citation validation.

SKILL INSTRUCTIONS:
{instructions}

CONTRACT:
{contract}

INPUT JSON SCHEMA:
{input_schema}

OUTPUT JSON SCHEMA:
{output_schema}

ENTRY POINT: {entry_point}
{repair_note}

INPUT:
{input_json}

FINAL OUTPUT INVARIANTS:
{output_invariants}
""".format(
            instructions=resources["instructions"],
            contract=resources["contract"],
            input_schema=resources["input_schema"],
            output_schema=resources["output_schema"],
            entry_point=entry_point,
            repair_note=repair_note,
            input_json=json.dumps(skill_input, ensure_ascii=False, separators=(",", ":")),
            output_invariants=self._output_invariants(skill_name, skill_input),
        )
    def _output_invariants(self, skill_name: str, skill_input: Mapping[str, Any]) -> str:
        if skill_name == "legal_issue_and_query_planning":
            return self._s1_output_invariants(skill_input)
        if skill_name == "grounded_legal_answer_generation":
            partial_ids = [
                item.get("evidence_item_id")
                for item in self._list(skill_input, "coverage_assessments")
                if isinstance(item, Mapping)
                and item.get("status") == "partially_covered"
            ]
            if partial_ids:
                return (
                    "Use only accepted provision IDs supplied in INPUT. Critical partial evidence IDs are %s. "
                    "Do not assert their missing facts. Include at least one cited conditional legal claim and a non-empty "
                    "limitations array that states each unresolved condition. Every claims[] item must set citation_required "
                    "true and have at least one claim_citation. Keep uncited missing-fact and limitation prose out of claims[]; "
                    "put it only in answer, assumptions[], or limitations[]."
                    % json.dumps(partial_ids)
                )
            return "Use only accepted provision IDs supplied in INPUT. Every claims[] item must set citation_required true and have at least one claim_citation; keep uncited factual or limitation prose out of claims[]."
        if skill_name != "provision_coverage_assessment":
            return "Use only the identifiers and fields supplied in INPUT."
        evidence_ledger = [
            {"evidence_item_id": item.get("evidence_item_id"), "issue_id": item.get("issue_id"), "critical": item.get("critical")}
            for item in self._list(skill_input, "required_evidence_items")
            if isinstance(item, Mapping)
        ]
        candidate_ids = [
            item.get("provision_id")
            for item in self._list(skill_input, "candidate_provisions")
            if isinstance(item, Mapping)
        ]
        return (
            "For S2, use only these evidence_item_id values: %s. Use only these candidate provision_id values: %s. Never invent an ID. Each evidence item appears in exactly one coverage assessment. For every non-covered item, copy issue_id and critical exactly from this evidence ledger: %s. Every evidence link must use quoted_text exactly '[FULL_TEXT]'. If the supplied provisions give complete alternative rules and only a missing question fact selects the branch (for example maritime versus air carriage), classify the item as partially_covered with partial_kind factual_condition, link every supported branch, and state the missing selector fact; do not classify that situation as conflicting. Use conflicting only for incompatible legal rules under the same established facts or unresolved legal interpretation."
            % (
                json.dumps([item["evidence_item_id"] for item in evidence_ledger]),
                json.dumps(candidate_ids),
                json.dumps(evidence_ledger, ensure_ascii=False, separators=(",", ":")),

            )
        )
    def _s1_output_invariants(self, skill_input: Mapping[str, Any]) -> str:
        if skill_input.get("mode") != "GAP_QUERY_PLAN":
            return "Copy run_id exactly from INPUT. Use only the identifiers and fields supplied in INPUT."
        prior_queries = []
        for item in self._list(skill_input, "query_history"):
            if isinstance(item, Mapping):
                query = item.get("query_text") or item.get("normalized_query")
                if isinstance(query, str):
                    prior_queries.append(query)
        unresolved = [
            item.get("evidence_item_id")
            for key in ("missing_evidence_items", "evidence_conflicts")
            for item in self._list(skill_input, key)
            if isinstance(item, Mapping)
        ]
        return (
            "For S1 GAP_QUERY_PLAN, target only these unresolved evidence IDs: %s. Every gap query must be genuinely new and must not equal any of these prior queries after lowercase and whitespace normalization: %s. Use the exact input run_id. Use GRQ-style request IDs, never a mode name."
            % (
                json.dumps(unresolved),
                json.dumps(prior_queries, ensure_ascii=False),
            )
        )

    def _generate(self, prompt: str, max_tokens: int) -> str:
        if self.generator is not None:
            return self.generator(prompt)
        request_data = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "keep_alive": "15m",
                "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": max_tokens},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=request_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise SkillExecutionError("local Ollama request failed: %s" % exc) from exc
        generated = payload.get("response")
        if not isinstance(generated, str) or not generated.strip():
            raise SkillExecutionError("local Ollama returned no JSON response")
        return generated

    @staticmethod
    def _parse_json_object(raw: str) -> Dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        decoder = json.JSONDecoder()
        first_brace = text.find("{")
        if first_brace < 0:
            raise ValueError("model response contains no JSON object")
        try:
            parsed, _ = decoder.raw_decode(text[first_brace:])
        except json.JSONDecodeError as exc:
            raise ValueError("model response is not valid JSON: %s" % exc) from exc
        if not isinstance(parsed, dict):
            raise ValueError("model response must be a JSON object")
        return parsed

    def _adapt_output(
        self,
        skill_name: str,
        entry_point: str,
        output: Mapping[str, Any],
        skill_input: Mapping[str, Any],
    ) -> Dict[str, Any]:
        if skill_name == "legal_issue_and_query_planning":
            return self._adapt_s1(entry_point, output)
        if skill_name == "provision_coverage_assessment":
            return self._adapt_s2(output, skill_input)
        if skill_name == "grounded_legal_answer_generation":
            return self._adapt_s3(output)
        raise SkillExecutionError("unsupported skill: %s" % skill_name)

    def _adapt_s1(self, entry_point: str, output: Mapping[str, Any]) -> Dict[str, Any]:
        request_key = "retrieval_requests" if entry_point == "INITIAL_PLAN" else "gap_retrieval_requests"
        requests: List[Dict[str, Any]] = []
        for request in self._list(output, request_key):
            if not isinstance(request, Mapping):
                raise SkillExecutionError("S1 request must be an object")
            channel = self._string(request, "query_channel")
            requests.append(
                {
                    "request_id": self._string(request, "request_id"),
                    "issue_id": self._string(request, "issue_id"),
                    "evidence_item_id": self._string(request, "evidence_item_id"),
                    "query_channel": INTERNAL_CHANNELS.get(channel, channel),
                    "query_text": self._string(request, "query_text"),
                    "top_k": 100,
                    "query_terms": [
                        item.strip()
                        for item in request.get("query_terms", [])
                        if isinstance(item, str) and item.strip()
                    ],
                    "statute_hints": [
                        item.strip()
                        for item in request.get("statute_hints", [])
                        if isinstance(item, str) and item.strip()
                    ],
                }
            )
        if entry_point == "GAP_QUERY_PLAN":
            return {"gap_retrieval_requests": requests}
        issues = []
        for issue in self._list(output, "legal_issues"):
            if not isinstance(issue, Mapping):
                raise SkillExecutionError("S1 issue must be an object")
            issues.append(
                {
                    "issue_id": self._string(issue, "issue_id"),
                    "description": issue.get("issue_statement") or self._string(issue, "decision_question"),
                }
            )
        evidence = []
        for item in self._list(output, "required_evidence_items"):
            if not isinstance(item, Mapping):
                raise SkillExecutionError("S1 evidence item must be an object")
            evidence.append(
                {
                    "evidence_item_id": self._string(item, "evidence_item_id"),
                    "issue_id": self._string(item, "issue_id"),
                    "evidence_type": self._string(item, "evidence_type"),
                    "description": self._string(item, "description"),
                    "critical": item.get("critical"),
                    "completion_criteria": self._string(item, "completion_criteria"),
                }
            )
        return {
            "legal_issues": issues,
            "required_evidence_items": evidence,
            "retrieval_requests": requests,
        }

    def _adapt_s2(self, output: Mapping[str, Any], skill_input: Mapping[str, Any]) -> Dict[str, Any]:
        evidence_by_id = {
            item["evidence_item_id"]: item
            for item in self._list(skill_input, "required_evidence_items")
            if isinstance(item, Mapping)
        }
        provisions = {
            item["provision_id"]: item
            for item in self._list(skill_input, "candidate_provisions")
            if isinstance(item, Mapping)
        }
        links = []
        for link in self._list(output, "evidence_links", required=False):
            if not isinstance(link, Mapping):
                raise SkillExecutionError("S2 evidence link must be an object")
            provision_id = self._string(link, "provision_id")
            evidence_id = self._string(link, "evidence_item_id")
            source = provisions.get(provision_id)
            if source is None:
                raise SkillExecutionError("S2 cited a provision outside the supplied candidates")
            quote = self._string(link, "quoted_text")
            if quote == "[FULL_TEXT]":
                quote = self._string(source, "text")
            start = source["text"].find(quote)
            if start < 0:
                raise SkillExecutionError("S2 quote is not in the supplied provision")
            links.append(
                {
                    "issue_id": evidence_by_id[evidence_id]["issue_id"],
                    "evidence_item_id": evidence_id,
                    "provision_id": self._source_provision_id(provisions, provision_id),
                    "support_spans": [{"start_char": start, "end_char": start + len(quote)}],
                    "assessment": "conflicting" if link.get("relation") == "conflicts" else "accepted",
                }
            )
        assessments = []
        for assessment in self._list(output, "coverage_assessments"):
            if not isinstance(assessment, Mapping):
                raise SkillExecutionError("S2 assessment must be an object")
            assessments.append(
                {
                    "evidence_item_id": self._string(assessment, "evidence_item_id"),
                    "status": self._string(assessment, "status"),
                    "linked_provision_ids": [
                        self._source_provision_id(provisions, provision_id)
                        for provision_id in self._list(assessment, "linked_provision_ids")
                    ],
                    "rationale": self._string(assessment, "rationale"),
                    "partial_kind": self._string(assessment, "partial_kind"),
                    "missing_aspects": [
                        self._string({"value": item}, "value")
                        for item in self._list(assessment, "missing_aspects")
                    ],
                }
            )
        conflicts = []
        for conflict in self._list(output, "evidence_conflicts", required=False):
            if not isinstance(conflict, Mapping):
                raise SkillExecutionError("S2 conflict must be an object")
            conflicts.append(
                {
                    "evidence_item_id": self._string(conflict, "evidence_item_id"),
                    "provision_ids": [
                        self._source_provision_id(provisions, provision_id)
                        for provision_id in self._list(conflict, "provision_ids")
                    ],
                    "description": self._string(conflict, "description"),
                    "resolved": False,
                }
            )
        return {
            "evidence_links": links,
            "coverage_assessments": assessments,
            "evidence_conflicts": conflicts,
        }

    def _source_provision_id(
        self, provisions: Mapping[str, Mapping[str, Any]], provision_id: Any
    ) -> str:
        if not isinstance(provision_id, str):
            raise SkillExecutionError("S2 provision_id must be a non-empty string")
        source = provisions.get(provision_id)
        if source is None:
            raise SkillExecutionError("S2 cited a provision outside the supplied candidates")
        return self._string(source, "source_provision_id")

    def _adapt_s3(self, output: Mapping[str, Any]) -> Dict[str, Any]:
        claims = []
        for claim in self._list(output, "claims"):
            if not isinstance(claim, Mapping):
                raise SkillExecutionError("S3 claim must be an object")
            claims.append(
                {"claim_id": self._string(claim, "claim_id"), "text": self._string(claim, "text")}
            )
        grouped: Dict[str, List[str]] = {}
        for citation in self._list(output, "claim_citations"):
            if not isinstance(citation, Mapping):
                raise SkillExecutionError("S3 citation must be an object")
            claim_id = self._string(citation, "claim_id")
            grouped.setdefault(claim_id, []).append(self._string(citation, "provision_id"))
        expected_claim_ids = {claim["claim_id"] for claim in claims}
        if set(grouped) != expected_claim_ids:
            raise SkillExecutionError("S3 must cite every claim for the harness citation check")
        return {
            "answer": self._string(output, "answer"),
            "claims": claims,
            "claim_citations": [
                {"claim_id": claim_id, "provision_ids": sorted(set(provision_ids))}
                for claim_id, provision_ids in sorted(grouped.items())
            ],
        }

    @staticmethod
    def _string(value: Mapping[str, Any], key: str) -> str:
        item = value.get(key)
        if not isinstance(item, str) or not item.strip():
            raise SkillExecutionError("%s must be a non-empty string" % key)
        return item.strip()

    @staticmethod
    def _list(value: Mapping[str, Any], key: str, required: bool = True) -> List[Any]:
        item = value.get(key)
        if item is None and not required:
            return []
        if not isinstance(item, list):
            raise SkillExecutionError("%s must be a list" % key)
        return item

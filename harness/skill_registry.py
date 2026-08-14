"""Layout checks for externally supplied skill packages; no skill is implemented here."""

from pathlib import Path
from typing import Dict, List


REQUIRED_SKILL_FILES = (
    "SKILL.md",
    "prompt_template.jinja",
    "input.schema.json",
    "output.schema.json",
    "failure_contract.json",
)

SKILL_DIRECTORIES: Dict[str, str] = {
    "legal_issue_and_query_planning": "legal_issue_and_query_planning",
    "provision_coverage_assessment": "provision_coverage_assessment",
    "grounded_legal_answer_generation": "grounded_legal_answer_generation",
}


class SkillLayoutError(RuntimeError):
    pass


def expected_skill_paths(skills_root: Path) -> Dict[str, Path]:
    return {
        skill_name: skills_root / directory
        for skill_name, directory in SKILL_DIRECTORIES.items()
    }


def missing_skill_files(skills_root: Path) -> Dict[str, List[str]]:
    missing: Dict[str, List[str]] = {}
    for skill_name, directory in expected_skill_paths(skills_root).items():
        absent = [
            filename
            for filename in REQUIRED_SKILL_FILES
            if not (directory / filename).is_file()
        ]
        if absent:
            missing[skill_name] = absent
    return missing


def assert_skill_layout_complete(skills_root: Path) -> None:
    missing = missing_skill_files(skills_root)
    if missing:
        details = "; ".join(
            "%s: %s" % (skill, ", ".join(files))
            for skill, files in sorted(missing.items())
        )
        raise SkillLayoutError("External skill packages are incomplete: %s" % details)

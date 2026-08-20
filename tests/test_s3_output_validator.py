import importlib.util
import unittest
from pathlib import Path


def _load_validator():
    path = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "grounded_legal_answer_generation"
        / "scripts"
        / "validate_output.py"
    )
    spec = importlib.util.spec_from_file_location("s3_output_validator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class S3OutputValidatorTest(unittest.TestCase):
    def test_success_without_input_reports_contract_error_instead_of_raising(self):
        validator = _load_validator()

        errors = validator.validate(
            {
                "schema_version": "1.0",
                "skill_id": "S3",
                "mode": "GENERATE_ANSWER",
                "status": "ok",
            },
            None,
        )

        self.assertEqual(errors, ["success validation requires --input"])

    def test_no_input_still_rejects_an_unknown_entry_point(self):
        validator = _load_validator()

        errors = validator.validate(
            {
                "schema_version": "1.0",
                "skill_id": "S3",
                "mode": "UNKNOWN",
                "status": "ok",
            },
            None,
        )

        self.assertEqual(
            errors,
            [
                "mode must be a supported S3 entry point",
                "success validation requires --input",
            ],
        )


if __name__ == "__main__":
    unittest.main()

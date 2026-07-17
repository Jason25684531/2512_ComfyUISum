import runpy
import subprocess
import sys
from pathlib import Path


VALIDATOR = Path(__file__).resolve().parents[2] / "scripts" / "validate_deployment_matrix.py"


def test_forbidden_literal_reports_file_and_value(tmp_path):
    literal = ".".join(("10", "10", "1", "18"))
    forbidden = tmp_path / "unsafe.py"
    forbidden.write_text(f"host = '{literal}'\n", encoding="utf-8")
    namespace = runpy.run_path(str(VALIDATOR))
    violations = []
    namespace["validate_forbidden_literals"](tmp_path, set(), violations)
    assert violations == [{
        "type": "forbidden-literal",
        "message": f"Found forbidden literal '{literal}'.",
        "file_path": "unsafe.py",
        "matched_literal": literal,
    }]


def test_cli_returns_nonzero_for_forbidden_literal():
    literal = ".".join(("10", "10", "1", "18"))
    forbidden = VALIDATOR.parents[1] / ".validator_forbidden_test.py"
    forbidden.write_text(f"host = '{literal}'\n", encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            cwd=VALIDATOR.parents[1],
            capture_output=True,
            text=True,
        )
    finally:
        forbidden.unlink()
    assert result.returncode == 1
    assert literal in result.stdout

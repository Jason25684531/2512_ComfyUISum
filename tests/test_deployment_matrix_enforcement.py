"""Tests for specs/deployment-matrix-enforcement/spec.md.

- Env example files validated against the matrix (missing required + undeclared extra).
- Compose-file roles consistent with the matrix; missing referenced paths fail.
- Gate fails closed on missing / unreadable / invalid-YAML matrix.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = PROJECT_ROOT / "scripts" / "validate_deployment_matrix.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_deployment_matrix", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_file(repo_root: Path, relative_path: str, content: str) -> None:
    target_path = repo_root / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")


def _violation_types(result) -> set[str]:
    return {item["type"] for item in result["violations"]}


# --------------------------------------------------------------------------- #
# Real repo stays compliant after the gate is extended
# --------------------------------------------------------------------------- #

def test_real_repo_still_compliant_with_extended_gate():
    module = load_validator_module()
    result = module.validate_deployment_matrix(PROJECT_ROOT)
    assert result["compliant"] is True, result["violations"]


# --------------------------------------------------------------------------- #
# Env example drift
# --------------------------------------------------------------------------- #

def _minimal_matrix(extra: str = "") -> str:
    return textwrap.dedent(
        f"""
        topologies:
          local-dev:
            canonical_entry:
              path: docker-compose.yml
              kind: compose
            env_file: .env.local
            services: []
            required_env: [DB_PASSWORD]
            optional_env: [NGROK_URL]
        {extra}
        """
    ).strip() + "\n"


def test_undeclared_extra_env_key_fails(tmp_path: Path):
    module = load_validator_module()
    write_file(tmp_path, "deployment_matrix.yaml", _minimal_matrix())
    write_file(tmp_path, "docker-compose.yml", "services: {}\n")
    write_file(tmp_path, ".env.local.example", "DB_PASSWORD=x\nNGROK_URL=y\nROGUE_KEY=z\n")

    result = module.validate_deployment_matrix(tmp_path)

    assert result["compliant"] is False
    assert any(
        item["type"] == "env-key-undeclared" and item["env_key"] == "ROGUE_KEY"
        for item in result["violations"]
    )


def test_common_optional_env_legitimizes_extra_key(tmp_path: Path):
    module = load_validator_module()
    write_file(tmp_path, "deployment_matrix.yaml", _minimal_matrix("common_optional_env: [LOG_DIR]"))
    write_file(tmp_path, "docker-compose.yml", "services: {}\n")
    write_file(tmp_path, ".env.local.example", "DB_PASSWORD=x\nNGROK_URL=y\nLOG_DIR=/var/log\n")

    result = module.validate_deployment_matrix(tmp_path)

    assert "env-key-undeclared" not in _violation_types(result)


def test_missing_required_env_key_fails(tmp_path: Path):
    module = load_validator_module()
    write_file(tmp_path, "deployment_matrix.yaml", _minimal_matrix())
    write_file(tmp_path, "docker-compose.yml", "services: {}\n")
    write_file(tmp_path, ".env.local.example", "NGROK_URL=y\n")  # DB_PASSWORD missing

    result = module.validate_deployment_matrix(tmp_path)

    assert result["compliant"] is False
    assert any(
        item["type"] == "env-key-missing" and item["env_key"] == "DB_PASSWORD"
        for item in result["violations"]
    )


# --------------------------------------------------------------------------- #
# Compose role consistency + missing referenced paths
# --------------------------------------------------------------------------- #

def test_canonical_marked_only_compatibility_conflicts(tmp_path: Path):
    module = load_validator_module()
    extra = textwrap.dedent(
        """
        legacy_entries:
          - path: docker-compose.yml
            role: compatibility
        """
    )
    write_file(tmp_path, "deployment_matrix.yaml", _minimal_matrix(extra))
    write_file(tmp_path, "docker-compose.yml", "services: {}\n")
    write_file(tmp_path, ".env.local.example", "DB_PASSWORD=x\nNGROK_URL=y\n")

    result = module.validate_deployment_matrix(tmp_path)

    assert any(item["type"] == "compose-role-conflict" for item in result["violations"])


def test_missing_referenced_legacy_path_fails(tmp_path: Path):
    module = load_validator_module()
    extra = textwrap.dedent(
        """
        legacy_entries:
          - path: docker-compose.ghost.yml
            role: compatibility
        """
    )
    write_file(tmp_path, "deployment_matrix.yaml", _minimal_matrix(extra))
    write_file(tmp_path, "docker-compose.yml", "services: {}\n")
    write_file(tmp_path, ".env.local.example", "DB_PASSWORD=x\nNGROK_URL=y\n")

    result = module.validate_deployment_matrix(tmp_path)

    assert any(
        item["type"] == "missing-legacy-entry" and item["file_path"] == "docker-compose.ghost.yml"
        for item in result["violations"]
    )


# --------------------------------------------------------------------------- #
# Fail closed
# --------------------------------------------------------------------------- #

def test_missing_matrix_fails_closed(tmp_path: Path):
    module = load_validator_module()
    result = module.validate_deployment_matrix(tmp_path)
    assert result["compliant"] is False
    assert "matrix-missing" in _violation_types(result)


def test_invalid_yaml_fails_closed_without_traceback(tmp_path: Path):
    module = load_validator_module()
    write_file(tmp_path, "deployment_matrix.yaml", "topologies: [this is: : not valid yaml\n")

    result = module.validate_deployment_matrix(tmp_path)

    assert result["compliant"] is False
    assert "matrix-invalid" in _violation_types(result)

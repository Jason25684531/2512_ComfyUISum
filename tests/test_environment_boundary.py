import importlib.util
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = PROJECT_ROOT / "scripts" / "validate_environment_boundary.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_environment_boundary", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_file(repo_root: Path, relative_path: str, content: str = "ok\n") -> None:
    target_path = repo_root / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")


def build_fake_repo(tmp_path: Path) -> Path:
    manifest_content = (PROJECT_ROOT / "environment_boundary_manifest.json").read_text(encoding="utf-8")
    write_file(tmp_path, "environment_boundary_manifest.json", manifest_content)

    required_files = {
        "openspec/config.yaml": "context: TWCC_GATEWAY_HOST\n",
        "shared/utils.py": "def load_env():\n    return None\n",
        "README.md": "boundary docs\n",
        ".env.local.example": "STUDIO_ENV=local\n",
        ".env.twcc.example": "STUDIO_ENV=twcc\n",
        ".env.unified.example": "ENV_CONTRACT_FILE=./.env.local\n",
        ".env.local": "STUDIO_ENV=local\n",
        ".env.twcc": "STUDIO_ENV=twcc\n",
        "docker-compose.yml": "services: {}\n",
        "docker-compose.unified.yml": "services: {}\n",
        "docker-compose.base.yml": "services: {}\n",
        "docs/Environment_Boundary_Guide.md": "guide\n",
        "docs/TWCC_HFS_COS_Mount_Guide.md": "mount guide\n",
        "docs/TWCC_Deployment_Guide.md": "deployment guide\n",
        "docs/TWCC_PRODUCTION_LAUNCH_SOP.md": "sop\n",
        "docs/Windows_BAT_Compatibility.md": "windows guide\n",
        "worker/worker.service.template": "Environment=STUDIO_ENV_FILE=.env.twcc\n",
        "scripts/start_unified_windows.bat": "set ENV_FILE=.env.local\n",
        "scripts/start_unified_linux.sh": "ENV_FILE=.env.local\n",
        "scripts/twcc_gpu_setup.sh": "echo gpu setup\n",
        "nginx/nginx.twcc.conf": "server {}\n",
        "ComfyUIworkflow/workflow.json": "{}\n",
    }

    for relative_path, content in required_files.items():
        write_file(tmp_path, relative_path, content)

    return tmp_path


def test_local_boundary_passes_with_explicit_local_env(tmp_path):
    module = load_validator_module()
    repo_root = build_fake_repo(tmp_path)

    result = module.validate_environment_boundary(repo_root, "local", env_file=".env.local")

    assert result["compliant"] is True
    assert result["violation_found"] is False


def test_twcc_boundary_rejects_local_env_file(tmp_path):
    module = load_validator_module()
    repo_root = build_fake_repo(tmp_path)

    result = module.validate_environment_boundary(repo_root, "twcc", env_file=".env.local")

    assert result["compliant"] is False
    assert any(item["type"] == "env-file-mismatch" for item in result["violations"])


def test_custom_required_paths_cannot_skip_twcc_canonical_assets(tmp_path):
    module = load_validator_module()
    repo_root = build_fake_repo(tmp_path)
    (repo_root / "docs" / "TWCC_HFS_COS_Mount_Guide.md").unlink()

    result = module.validate_environment_boundary(
        repo_root,
        "twcc",
        env_file=".env.twcc",
        required_paths=["docker-compose.unified.yml"],
    )

    assert result["compliant"] is False
    assert any(
        item["type"] == "required-path-missing"
        and item["file_path"] == "docs/TWCC_HFS_COS_Mount_Guide.md"
        for item in result["violations"]
    )


def test_local_boundary_rejects_cloud_only_runtime_inputs(tmp_path):
    module = load_validator_module()
    repo_root = build_fake_repo(tmp_path)

    result = module.validate_environment_boundary(
        repo_root,
        "local",
        env_file=".env.local",
        required_paths=["docker-compose.unified.yml", "nginx/"],
    )

    assert result["compliant"] is False
    assert any(
        item["type"] == "canonical-boundary-mismatch"
        and item["file_path"] == "docker-compose.unified.yml"
        for item in result["violations"]
    )
    assert any(
        item["type"] == "canonical-boundary-mismatch"
        and item["file_path"] == "nginx"
        for item in result["violations"]
    )


def test_validator_rejects_required_paths_outside_repo(tmp_path):
    module = load_validator_module()
    repo_root = build_fake_repo(tmp_path)

    result = module.validate_environment_boundary(
        repo_root,
        "local",
        env_file=".env.local",
        required_paths=["../escape.txt"],
    )

    assert result["compliant"] is False
    assert any(item["type"] == "path-outside-repo" for item in result["violations"])


def test_validator_detects_forbidden_literal_in_governed_file(tmp_path):
    module = load_validator_module()
    repo_root = build_fake_repo(tmp_path)
    write_file(repo_root, "README.md", "bad literal 202.5.255.9\n")

    result = module.validate_environment_boundary(repo_root, "local", env_file=".env.local")

    assert result["compliant"] is False
    assert any(item["type"] == "forbidden-literal" for item in result["violations"])


def test_json_payload_marks_strings_as_encoded(tmp_path):
    module = load_validator_module()
    repo_root = build_fake_repo(tmp_path)
    write_file(repo_root, "docs/a&b.md", "not canonical\n")

    result = module.validate_environment_boundary(
        repo_root,
        "local",
        env_file=".env.local",
        required_paths=["docs/a&b.md"],
    )
    payload = module.build_output_payload(result)

    assert payload["_encoding"]["violations[*].file_path"] is True
    assert payload["violations"][0]["file_path"] == "docs/a&amp;b.md"
    assert json.loads(json.dumps(payload))["compliant"] is False
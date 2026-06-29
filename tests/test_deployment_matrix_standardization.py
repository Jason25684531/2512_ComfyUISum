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


def test_deployment_matrix_validator_passes_real_repo() -> None:
    module = load_validator_module()

    result = module.validate_deployment_matrix(PROJECT_ROOT)

    assert result["compliant"] is True
    assert result["violations"] == []


def test_validator_detects_topology_and_proxy_contract_drift(tmp_path: Path) -> None:
    module = load_validator_module()

    write_file(
        tmp_path,
        "deployment_matrix.yaml",
        textwrap.dedent(
            """
            topologies:
              local-dev:
                canonical_entry:
                  path: docker-compose.yml
                  kind: compose
                env_file: .env.local
                services: [comfyui, redis, mysql, backend, worker]
              twcc-base-vm:
                canonical_entry:
                  path: docker-compose.base.yml
                  kind: compose
                env_file: .env.twcc
                services: [nginx, backend, redis, mysql]
                proxy_contract:
                  nginx_config: nginx/nginx.twcc.conf
                  required_headers:
                    - Host
                    - X-Real-IP
                    - X-Forwarded-For
                    - X-Forwarded-Proto
                    - X-Forwarded-Host
            """
        ).strip()
        + "\n",
    )
    write_file(
        tmp_path,
        ".env.local",
        "DEPLOYMENT_TOPOLOGY=local-dev\nENV_CONTRACT_FILE=./.env.local\nREDIS_PASSWORD=x\nMYSQL_ROOT_PASSWORD=x\nDB_PASSWORD=x\nSECRET_KEY=x\nCOMFYUI_SERVER_URL=http://127.0.0.1:8188\nCOMFY_HOST=127.0.0.1\n",
    )
    write_file(
        tmp_path,
        ".env.twcc",
        "DEPLOYMENT_TOPOLOGY=twcc-base-vm\nENV_CONTRACT_FILE=./.env.twcc\nREDIS_PASSWORD=x\nMYSQL_ROOT_PASSWORD=x\nDB_PASSWORD=x\nSECRET_KEY=x\nLB_DOMAIN=studio.example.com\nS3_ENDPOINT=https://cos.twcc.ai\nS3_BUCKET=bucket\nS3_ACCESS_KEY=x\nS3_SECRET_KEY=x\nTWCC_API_KEY=x\nTWCC_PROJECT_ID=x\nTWCC_GPU_VM_ID=x\nTWCC_GATEWAY_HOST=gateway\nTWCC_BASE_HOST=base\nTWCC_GPU_NODE_HOST=gpu\nGPU_VM_REDIS_HOST=10.0.0.1\nCOMFYUI_SERVER_URL=http://gpu:8188\nCOMFY_HOST=gpu\n",
    )
    write_file(tmp_path, "docker-compose.yml", "services: {}\n")
    write_file(tmp_path, "docker-compose.base.yml", "services:\n  backend: {}\n")
    write_file(
        tmp_path,
        "nginx/nginx.twcc.conf",
        textwrap.dedent(
            """
            server {
                location /api/ {
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }
            }
            """
        ).strip()
        + "\n",
    )
    write_file(
        tmp_path,
        "scripts/start_unified_linux.sh",
        'echo "[3] Infrastructure only (infra-only profile)"\n',
    )

    result = module.validate_deployment_matrix(tmp_path)

    assert result["compliant"] is False
    assert any(item["type"] == "missing-topology" and item["topology"] == "twcc-gpu-vm" for item in result["violations"])
    assert any(item["type"] == "proxy-header-missing" and item["header"] == "X-Forwarded-Host" for item in result["violations"])
    assert any(item["type"] == "script-profile-drift" for item in result["violations"])

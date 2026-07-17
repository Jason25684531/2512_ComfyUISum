# Deployment Matrix

本文件是 `cloud-infra-standardization` 的單一部署矩陣來源，用來對齊 compose、腳本、LB/Nginx 契約、env contract 與驗證 gate。

## Canonical Topologies

| Topology | Canonical Entry | Env File | Runtime Services | External Dependencies |
| --- | --- | --- | --- | --- |
| `local-dev` | `docker-compose.yml` | `.env.local` | `comfyui`, `redis`, `mysql`, `backend`, `worker` | none |
| `single-host-linux` | `docker-compose.unified.yml` with `linux-dev` / `linux-prod` profiles | `.env.local` | `comfyui`, `redis`, `mysql`, `backend`, `worker`, `nginx` | none |
| `twcc-base-vm` | `docker-compose.base.yml` | `.env.twcc` | `nginx`, `backend`, `redis`, `mysql` | `twcc-load-balancer`, `twcc-gpu-vm`, `twcc-cos` |
| `twcc-gpu-vm` | `scripts/twcc_gpu_setup.sh` + systemd (`comfyui`, `studio-worker`) | `.env.twcc` | `comfyui`, `studio-worker` | `twcc-base-vm`, `twcc-cos`, `twccli` |

## Canonical Vs Compatibility

| Asset | Role | Notes |
| --- | --- | --- |
| `docker-compose.yml` | canonical for `local-dev` | Full local stack with local ComfyUI service |
| `docker-compose.unified.yml` | canonical for `single-host-linux` | Profile-driven single-host Linux entry; also Windows docker-assisted compatibility |
| `docker-compose.base.yml` | canonical for `twcc-base-vm` | CPU Web Node only; must not include GPU-only services |
| `docker-compose.dev.yml` | compatibility | Infra-only local helper |
| `docker-compose.dev-s3.yml` | compatibility | Local MinIO / S3 simulation |
| `scripts/start_unified_windows.bat` | compatibility | Windows launcher for docker-assisted local startup |
| `scripts/start_unified_linux.sh` | compatibility helper | Single-host Linux launcher; `Infrastructure only` is a mode, not a compose profile |

## Env Contract

### Topology-required

- `local-dev`: `DEPLOYMENT_TOPOLOGY`, `ENV_CONTRACT_FILE`, `REDIS_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `DB_PASSWORD`, `SECRET_KEY`, `COMFYUI_SERVER_URL`, `COMFY_HOST`
- `single-host-linux`: `DEPLOYMENT_TOPOLOGY`, `ENV_CONTRACT_FILE`, `REDIS_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `DB_PASSWORD`, `SECRET_KEY`, `COMFYUI_SERVER_URL`, `COMFY_HOST`, `MODEL_PATH`
- `twcc-base-vm`: `DEPLOYMENT_TOPOLOGY`, `ENV_CONTRACT_FILE`, `REDIS_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `DB_PASSWORD`, `SECRET_KEY`, `LB_DOMAIN`, `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `TWCC_API_KEY`, `TWCC_PROJECT_ID`, `TWCC_GPU_VM_ID`, `TWCC_GATEWAY_HOST`, `TWCC_BASE_HOST`, `TWCC_GPU_NODE_HOST`, `GPU_VM_REDIS_HOST`, `COMFYUI_SERVER_URL`, `COMFY_HOST`
- `twcc-gpu-vm`: `DEPLOYMENT_TOPOLOGY`, `REDIS_PASSWORD`, `DB_PASSWORD`, `GPU_VM_REDIS_HOST`, `COMFYUI_SERVER_URL`, `COMFY_HOST`, `TWCC_GPU_NODE_HOST`, `TWCCLI_PATH`

### Optional / External

- `NGROK_URL`, `MODEL_PATH`, `WSL_MODEL_PATH` are local convenience settings.
- `S3_REGION`, `COMFY_HTTP_TIMEOUT`, `WORKER_TIMEOUT`, `COMFY_POLLING_INTERVAL` are tuning values, not topology identity.
- TWCC hostnames and COS credentials are operator-managed external dependencies and must not be hard-coded into compose, shell scripts, or docs.

## Proxy Contract

Canonical cloud ingress is always `TWCC Load Balancer -> Nginx -> Backend`.

- `nginx/nginx.twcc.conf` must define upstream `api_backend`.
- Required forwarded headers: `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`.
- WebSocket upgrade handling is required for `/ws/`.
- Long-running proxy paths must support `300s` read/connect/send timeout.
- Backend trusted proxy mode is controlled via `PROXY_FIX=true`.

## Validation Gates

### Preflight

- `local-dev`: `docker compose -f docker-compose.yml --env-file .env.local config`
- `single-host-linux`: `docker compose -f docker-compose.unified.yml --env-file .env.local --profile linux-dev config`
- `twcc-base-vm`: `docker compose -f docker-compose.base.yml --env-file .env.twcc config`
- `twcc-base-vm`: `python -m py_compile backend/src/app.py worker/src/main.py shared/storage_service.py`
- `twcc-base-vm`: validate Nginx config and forwarded-header contract
- `twcc-gpu-vm`: `python -m py_compile worker/src/main.py worker/src/comfy_client.py`

### Post-deploy

- `local-dev`: `curl http://127.0.0.1:5000/health`, `curl http://127.0.0.1:8188/system_stats`
- `single-host-linux`: `curl http://127.0.0.1:5000/health`, `curl http://127.0.0.1:8188/system_stats`
- `twcc-base-vm`: `curl http://127.0.0.1/health`, `curl http://127.0.0.1/api/health`, `bash scripts/twcc_healthcheck.sh`
- `twcc-gpu-vm`: `curl http://127.0.0.1:8188/system_stats`, `systemctl is-active comfyui`, `systemctl is-active studio-worker`

### Rollback

- `local-dev`: `docker compose -f docker-compose.yml --env-file .env.local down`
- `single-host-linux`: `docker compose -f docker-compose.unified.yml --env-file .env.local --profile linux-prod down`
- `twcc-base-vm`: `docker compose -f docker-compose.base.yml --env-file .env.twcc down`
- `twcc-gpu-vm`: `sudo systemctl stop studio-worker comfyui`

## Legacy Entry Policy

- Legacy compose variants remain available as compatibility assets until later cleanup work archives them.
- Compatibility assets must never be presented as the canonical source for TWCC production.
- New runbooks and deployment discussions should reference this matrix first, then the topology-specific guide.

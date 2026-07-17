# WSL2 Development Runbook

The supported local stack is Flask, Redis, MySQL, and the legacy worker.

```bash
docker compose -f docker-compose.yml --env-file .env.local up -d
python backend/src/app.py
python worker/src/main.py
```

Use `GET http://127.0.0.1:5000/health` to verify the backend. The retired FastAPI v2 backend and worker startup scripts are available only through git history.

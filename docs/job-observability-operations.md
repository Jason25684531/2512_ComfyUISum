# Job observability operations

Run migrations through the Backend container before starting Flask. MySQL is private; back it up according to the deployment owner's RPO/RTO policy.

`WORKER_ID` must be an explicit stable host/instance name in production. The Worker maintains Redis heartbeat and replays output receipts without rerunning ComfyUI. Pending dispatches are replayed by Flask; duplicate queue delivery is harmless because the MySQL claim is conditional.

Dashboard errors are sanitized. Prompt/base64/traceback are never stored in its tables or returned by its APIs. For a stuck job, inspect structured Worker logs, ComfyUI history using `comfyui_prompt_id`, then let the timeout reconciler mark it failed rather than re-running GPU work blindly.

All admin responses declare `output_encoded=false`. The browser must use context-safe DOM properties (`textContent` for text and same-origin allowlisted paths for output links); the server does not HTML-encode JSON. There is no authentication, user identity, JWT, API key, OAuth, or RBAC in this change.

Admin routes use the existing Flask port: `/admin`, `/api/admin/metrics/summary`, `/api/admin/metrics/timeseries`, `/api/admin/jobs`, `/api/admin/errors`, `/api/admin/workflows`, `/api/admin/workers`, and `/api/admin/system/health`. Queries default to 24 hours, are limited to 31 days, and page size is at most 200. Canonical states are `created`, `queued`, `running`, `completed`, `failed`, and `cancelled`; legacy status responses remain `queued`, `processing`, and `finished`.

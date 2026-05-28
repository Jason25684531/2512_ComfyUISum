# Single Server Local Storage Architecture

This repository currently targets one Flask Backend, one Worker, one local ComfyUI instance, Redis, MySQL, and local filesystem storage.

Generation flow:

1. Backend accepts `POST /api/generate`.
2. Backend records the job in MySQL and pushes Redis job data.
3. Worker consumes the Redis queue and parses the configured ComfyUI workflow.
4. Worker injects prompt, image, and audio inputs from `ComfyUIworkflow/config.json`.
5. Worker submits the workflow to the local ComfyUI instance and waits over WebSocket.
6. Worker recovers outputs through History API when needed, then copies local ComfyUI outputs into `storage/outputs`.
7. Backend serves generated files from local `storage/outputs` with safe filename and path containment checks.

Out of scope for this target:

- Multi-render-node scheduling
- Distributed rendering
- S3, COS, MinIO, or object storage
- Presigned output URLs
- Remote output synchronization

Adding a workflow should require adding the workflow JSON, a config entry with `file`, `prompt_map`, `image_map`, or `audio_map` as needed, and a fixture/test case that validates declared targets.

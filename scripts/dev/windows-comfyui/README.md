# Optional Windows ComfyUI Helper

This helper exists only for developers who keep ComfyUI on Windows while running Studio Core v2 from WSL2 or Linux.

## Rules

- Studio Core must treat ComfyUI as an external HTTP endpoint only.
- Set `COMFYUI_SERVER_URL` in `.env.local` and connect over HTTP.
- Do not make Studio Core depend on a Windows local ComfyUI filesystem path.
- Do not persist Windows paths into DB rows, Redis payloads, or output metadata.
- Use `--disable-metadata` when starting ComfyUI for StudioCore credential workflows. The Worker rejects submission without this flag because image save nodes can embed API credentials in media metadata.
- Use `--cache-ram 32` to keep 32 GB of system RAM free. The default (10 GB) let cached models fill RAM until MiniMax failed with `HostBuffer.read_file_slice failed`.
- Use `--verbose ERROR` to suppress ParallelGen INFO logs containing the configured endpoint. Check error logs and output metadata for credential values after validating the runtime.

## Usage

1. Optionally set `COMFYUI_DIR` (default `C:\ComfyUI_windows_portable_Multi_Workflows`).
2. Run `start-vwe.bat` in the repo root. It starts Docker services, the Cloudflare tunnel, and ComfyUI with the flags above.
3. Point `.env.local` at the exposed endpoint, for example `http://host.docker.internal:8188`.

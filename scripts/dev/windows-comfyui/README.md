# Optional Windows ComfyUI Helper

This helper exists only for developers who keep ComfyUI on Windows while running Studio Core v2 from WSL2 or Linux.

## Rules

- Studio Core must treat ComfyUI as an external HTTP endpoint only.
- Set `COMFYUI_BASE_URL` in the Linux-side env file and let WSL2 connect over HTTP.
- Do not make Studio Core depend on a Windows local ComfyUI filesystem path.
- Do not persist Windows paths into DB rows, Redis payloads, or output metadata.

## Usage

1. Set `COMFYUI_DIR` to your local Windows ComfyUI folder.
2. Run `start-comfyui.bat`.
3. Point WSL2 `.env.local-wsl` at the exposed endpoint, for example `http://host.docker.internal:8188`.

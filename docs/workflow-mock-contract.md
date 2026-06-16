# Workflow Mock Contract

The round-one workflow registry is JSON-manifest driven and intentionally minimal.

## Manifest Fields

- `task_type`: Stable workflow identifier used by `/api/v1/jobs`
- `display_name`: Human-readable catalog name
- `description`: Short purpose summary
- `version`: Manifest version string
- `required_inputs`: List of `{name, type}` entries
- `optional_inputs`: List of `{name, type}` entries
- `default_params`: Default parameter object returned by the catalog
- `output_type`: One of `image`, `video`, or `audio`
- `mock_output_filename`: Placeholder filename written by `MockEngine`

## Included Mock Workflows

- `text_to_image`
- `image_edit`
- `multi_image_blend`
- `image_upscale`
- `text_to_video`
- `image_to_video`
- `video_retake`
- `video_upscale`
- `tts`
- `avatar_talk`

## MockEngine Output Rules

- Image workflows write a minimal 1x1 PNG.
- Video workflows write a placeholder MP4 header file.
- Audio workflows write a placeholder WAV header file.
- Outputs are written to `storage/outputs/job_<job_id>/`.
- Returned `output_path` values are always relative, for example `outputs/job_<job_id>/result.png`.

## Queue Contract

- Queue key: `studio:v2:jobs`
- Cancel key: `studio:v2:cancel:{job_id}`
- Payload format: JSON string
- Payload validation: `json.loads()` plus Pydantic `JobPayload` validation
- Raw Redis exceptions must not be exposed to API consumers

## Asset Contract

- `POST /api/v1/assets` accepts multipart uploads only.
- Persisted asset paths look like `assets/<stored_filename>`.
- Stored filenames are sanitized and runtime metadata never keeps raw Windows absolute paths.

## Path Rules

- Never persist `C:\`, `D:\`, or any other Windows absolute path.
- Never persist UNC paths.
- Never persist backslashes.
- Never persist null bytes.
- Never persist `..` segments.
- Treat `STORAGE_ROOT` as the only filesystem trust boundary.

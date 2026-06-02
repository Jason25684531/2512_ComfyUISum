# Worker Parser Modular Facade Refactor

## Changed Files

- `worker/src/json_parser.py`
- `worker/src/workflow/__init__.py`
- `worker/src/workflow/loader.py`
- `worker/src/workflow/node_utils.py`
- `worker/src/workflow/injectors.py`
- `worker/src/workflow/video_trim.py`
- `worker/src/workflow/legacy_maps.py`
- `docs/worker_parser_modular_facade_refactor.md`

No `ComfyUIworkflow/*.json` workflow files were modified.

## New Module Tree

```text
worker/src/workflow/
  __init__.py
  injectors.py
  legacy_maps.py
  loader.py
  node_utils.py
  video_trim.py
```

`worker/src/json_parser.py` remains the compatibility facade for legacy imports and worker runtime calls.

## Function Move Map

| Original responsibility | New module | Public facade preserved |
| --- | --- | --- |
| `parse_workflow()` entrypoint | `json_parser.py` facade | Yes |
| `get_workflow_path()`, `load_workflow()` | `workflow/loader.py` | Yes |
| UI workflow API fallback detection | `workflow/loader.py` | Via `load_workflow()` |
| `get_workflow_node()` and input mutation helpers | `workflow/node_utils.py` | Yes |
| `set_configured_prompt_value()` | `workflow/node_utils.py` | Yes |
| `apply_prompt_map_if_configured()` | `workflow/injectors.py` | Yes |
| `apply_model_overrides()` | `workflow/injectors.py` | Yes |
| Prompt, seed, resolution, model, image, audio injection | `workflow/injectors.py` | Via `parse_workflow()` |
| `trim_veo3_workflow()` | `workflow/video_trim.py` | Yes |
| Legacy constants/maps | `workflow/legacy_maps.py` | Yes |

## Test Commands

Windows PowerShell:

```powershell
python -m pytest tests/test_comfy_workflow_runtime.py -q
python -m pytest tests -q
```

Linux shell:

```bash
python -m pytest tests/test_comfy_workflow_runtime.py -q
python -m pytest tests -q
```

The Windows/Linux runtime profile behavior remains controlled by `COMFYUI_RUNTIME_PROFILE` and `WorkflowRegistry`. Windows model overrides still apply only to the Windows profile; Linux/default profile does not apply Windows-only overrides.

## Test Results

- Phase 1: `python -m pytest tests/test_comfy_workflow_runtime.py -q` -> `24 passed`
- Phase 2: `python -m pytest tests/test_comfy_workflow_runtime.py -q` -> `24 passed`
- Phase 3: `python -m pytest tests/test_comfy_workflow_runtime.py -q` -> `24 passed`
- Phase 4: `python -m pytest tests/test_comfy_workflow_runtime.py -q` -> `24 passed`
- Phase 5: `python -m pytest tests/test_comfy_workflow_runtime.py -q` -> `24 passed`
- Phase 6 parser check: `python -m pytest tests/test_comfy_workflow_runtime.py -q` -> `24 passed`
- Final full suite: `python -m pytest tests -q` -> `60 passed, 1 warning`

The final warning is the existing Flask-Limiter in-memory storage warning during tests.

## Behavior Differences

No functional behavior differences are intended.

Protected `multi_image_blend` behavior remains covered:

- User prompt injects into `433:111.inputs.prompt`.
- `433:110.inputs.prompt` remains empty.
- `source`, `target`, and `extra` images map to `78`, `436`, and `437`.
- Logs retain the protected `prompt_map API 注入: Node 433:111.prompt` substring.
- Logs do not emit `Qwen Prompt 注入: Node 433:110.prompt` for the protected path.

## Rollback Note

To rollback this refactor, restore `worker/src/json_parser.py` to the pre-refactor monolithic parser and remove `worker/src/workflow/` plus this documentation file. No workflow JSON, Redis contract, backend API, DB schema, or frontend contract changes need rollback.

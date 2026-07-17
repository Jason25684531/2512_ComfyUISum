# Runtime Contract

`system-cleanup-and-refactor` 之後，Studio 的 runtime 與 workflow catalog 以 shared 層為單一來源：

- `shared/runtime_contract.py`
  - 統一解析 `runtime_profile`
  - 統一解析 API origin、Redis / DB endpoint
  - 驗證 `ComfyUIworkflow/config.json` 是否存在且可用
  - 在 TWCC 拓樸下缺少必要 secrets 時採 `fail-closed`
- `shared/workflow_catalog.py`
  - 統一 canonical workflow id
  - 統一 alias 規則
  - 統一 frontend metadata、image_map、prompt_map、audio_map

## Canonical Workflow IDs

- `image_edit`
  - aliases: `single_image_edit`, `single_edit`
- `multi_image_blend`
  - aliases: `multi_blend`
- `sketch_to_image`
  - aliases: `sketch`
- `t2v_veo3`
  - aliases: `T2V`
- `flf_veo3`
  - aliases: `FLF`

新寫入的 job 與 queue payload 都只應保存 canonical id。

## Frontend Contract

- `frontend/config.js` 會先載入 fallback catalog
- 若 `/api/runtime-config` 可用，前端會再以 backend 回傳的 catalog 覆寫本地 fallback
- `window.normalizeStudioWorkflowId(...)` 是前端唯一應使用的 workflow 正規化入口

## Validation

建議至少執行：

```powershell
python -m pytest tests/test_runtime_contract.py tests/test_workflow_catalog_contract.py tests/test_frontend_runtime_catalog.py tests/test_backend_contract.py tests/test_security_hardening.py tests/test_comfy_workflow_runtime.py -q
python -m pytest tests/test_backend_static_routes.py -q
python -m pytest tests/v2/test_frontend_serving.py -q
```

注意：`tests/v2/test_frontend_serving.py` 需要獨立執行，避免 legacy `backend/src/app.py` 模組名稱 `app` 與 v2 package import 互相污染。

## Rollback

若新 catalog 導致前端或 worker 異常：

1. 回退 `ComfyUIworkflow/config.json`
2. 回退 `shared/workflow_catalog.py` 與 `shared/runtime_contract.py`
3. 回退 `frontend/config.js`
4. 回退 `backend/src/app.py`、`worker/src/workflow_registry.py`、`worker/src/main.py`
5. 重新執行上面的驗證命令

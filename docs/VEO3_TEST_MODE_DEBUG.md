# [TEMP] Veo3 测试模式 - 调试指南

## 问题现象

任务仍然被推送到 Redis 队列并由 Worker 处理，测试模式的拦截没有生效。

## 调试步骤

### 1. 验证配置加载 ✅

```bash
cd d:\01_Project\2512_ComfyUISum
.\venv\Scripts\python.exe backend\test_config.py
```

**预期输出**：
```
VEO3_TEST_MODE: True (type: <class 'bool'>)
VEO3_TEST_VIDEO_PATH: tests/IU_Final/IU_Combine.mp4
VEO3_TEST_TRIGGER_PREFIX: IU
✅ 测试视频文件存在
```

### 2. 启动 Backend 并检查日志

```bash
cd backend
python src/app.py
```

**预期启动日志**：
```
🚀 Backend API 啟動中...
🔧 [TEST MODE] Veo3 測試模式已啟用！
🔧 [TEST MODE] 觸發前綴: IU
🔧 [TEST MODE] 測試視頻: tests/IU_Final/IU_Combine.mp4
```

### 3. 准备测试图片

- 创建或重命名任意图片为 `IU_test.jpg`
- 确保文件名以 `IU` 开头

### 4. 前端操作流程

1. 打开 `frontend/dashboard.html`
2. 点击 "Video Studio"
3. 选择 "Long Gen (长片生成)"
4. 上传 `IU_test.jpg` 到任意 Shot 位置（Shot 1-5）
5. 输入任意 Prompt（可选）
6. 点击 "Generate" 按钮

### 5. 检查前端控制台日志

**预期输出**：
```javascript
[Motion] [TEST MODE] Original filenames: {shot_0: "IU_test.jpg"}
[Motion] [TEST MODE] Filenames values: ["IU_test.jpg"]
```

**如果看到**：
```javascript
[Motion] [TEST MODE] No filenames recorded!
```
说明前端文件名记录有问题。

### 6. 检查 Backend 日志

**预期拦截日志**：
```
🔧 [TEST MODE] 測試模式已啟用，檢查文件名...
🔧 [TEST MODE] VEO3_TEST_MODE=True, workflow=veo3_long_video
🔧 [TEST MODE] 接收到的 filenames: {'shot_0': 'IU_test.jpg'}
🔧 [TEST MODE] 觸發前綴: IU
🔧 [TEST MODE] 檢測結果: has_trigger=True
🔧 [TEST MODE] ✅ 檢測到 IU 開頭的檔案，返回測試視頻: tests/IU_Final/IU_Combine.mp4
✓ [TEST MODE] 測試視頻已複製到 outputs: IU_Combine.mp4
```

**如果看到**：
```
🔧 [TEST MODE] 接收到的 filenames: {}
```
说明前端没有传递 filenames 字段。

**如果看到**：
```
🔧 [TEST MODE] ❌ 未檢測到 IU 開頭的檔案，繼續正常流程
```
说明文件名检测失败，检查文件名是否真的以 `IU` 开头。

### 7. 验证成功标志

- ✅ 前端立即显示视频预览
- ✅ 后端日志显示 `[TEST MODE]` 标记
- ✅ Worker **不应该**收到任务
- ✅ 浏览器网络面板看到返回 `status: 'completed'`

## 常见问题排查

### Q1: 前端 filenames 为空 `{}`

**原因**：文件名没有被记录到 `window.motionShotFilenames`

**检查**：
1. 查看 `handleMotionShotSelect` 函数是否被调用
2. 在浏览器控制台输入 `window.motionShotFilenames` 查看内容
3. 确认文件上传成功（有预览图）

**解决**：重新上传文件，确保调用了正确的上传函数

### Q2: Backend 日志显示 `VEO3_TEST_MODE=False`

**原因**：`.env` 文件未生效或配置错误

**检查**：
1. 确认 `.env` 文件在项目根目录
2. 确认 `VEO3_TEST_MODE=true`（小写）
3. 重启 Backend 服务

### Q3: 测试视频文件不存在错误

**原因**：路径配置错误或文件被移动

**检查**：
```bash
ls d:\01_Project\2512_ComfyUISum\tests\IU_Final\IU_Combine.mp4
```

**解决**：调整 `.env` 中的 `VEO3_TEST_VIDEO_PATH`

### Q4: Worker 仍然收到任务

**原因**：拦截逻辑未生效，任务被推送到 Redis

**检查**：
1. Backend 日志中是否有 `[TEST MODE]` 相关输出
2. 确认 workflow 是 `veo3_long_video`
3. 确认 filenames 字段正确传递

## 完整日志示例

### 成功的完整流程日志

**Frontend Console**:
```
[Motion] [TEST MODE] Original filenames: {shot_0: "IU_portrait.jpg"}
[Motion] Veo3 multi-segment mode, prompts: ["scene 1", "", "", "", ""]
```

**Backend Log**:
```
🔧 [TEST MODE] 測試模式已啟用，檢查文件名...
🔧 [TEST MODE] 接收到的 filenames: {'shot_0': 'IU_portrait.jpg'}
🔧 [TEST MODE] 檢測結果: has_trigger=True
🔧 [TEST MODE] ✅ 檢測到 IU 開頭的檔案，返回測試視頻
✓ [TEST MODE] 測試視頻已複製到 outputs: IU_Combine.mp4
```

**Worker Log**:
```
(应该没有任何新任务日志)
```

## 下一步

如果以上步骤都正常但仍然有问题，请：

1. **完整重启**所有服务（Backend、Worker、Redis）
2. **清空浏览器缓存**并重新加载前端页面
3. **检查 Redis**：`redis-cli` → `LLEN job_queue` 应该为 0
4. **抓包检查**：使用浏览器开发者工具查看 `/api/generate` 请求体

---

**创建日期**: 2026-01-30  
**用途**: 调试 Veo3 测试模式拦截失败问题

# Veo3 测试模式使用说明 (Veo3 Test Mode)

## 📋 概述

由于 Veo3 Token 已用罄，我们实现了一个临时的测试模式，专门用于"长片生成"工作流。当 veo3_long_video 工作流检测到上传了图片时，系统将自动返回预设的测试视频，而不会消耗实际的 Veo3 资源。

## 🔧 配置说明

### 环境变量 (`.env` 文件)

```env
# [TEMP] Veo3 測試模式 (Veo3 Test Mode)
VEO3_TEST_MODE=true                              # 开启/关闭测试模式
VEO3_TEST_VIDEO_PATH=tests/IU_Final/IU_Combine.mp4  # 测试视频路径
```

### 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `VEO3_TEST_MODE` | `false` | 设为 `true` 开启测试模式，`false` 关闭 |
| `VEO3_TEST_VIDEO_PATH` | `tests/IU_Final/IU_Combine.mp4` | 测试视频文件的相对路径 |

## 🚀 使用方法

### 1. 启用测试模式

确保 `.env` 文件中 `VEO3_TEST_MODE=true`

### 2. 上传任意图片

在"长片生成"(Long Gen) 工作流中，上传**任意图片**到 Shot 1-5 的任意位置。

### 3. 系统行为

- ✅ **检测到图片上传**：立即返回 `tests/IU_Final/IU_Combine.mp4` 测试视频
- ⏭️ **跳过队列**：不推送到 Redis 队列，不占用 Worker 资源
- 📊 **状态标记**：Redis 状态中添加 `test_mode: 'true'` 标记
- 📝 **日志记录**：后端日志会显示 `[TEST MODE]` 标记

### 4. 前端接收

前端照常接收视频 URL 并显示预览，用户体验与正常流程一致。

## 📂 文件修改清单

所有修改都使用 `[TEMP]` 注释标记，方便后续清理：

### Backend
### Backend
- **`backend/src/config.py`** (L43-45)：添加环境变量配置
- **`backend/src/app.py`** (L164-166)：导入测试配置
- **`backend/src/app.py`** (L772-815)：添加拦截逻辑（检测图片上传）

### Frontend
- **`frontend/motion-workspace.js`** (L15-17)：添加文件名存储变量（可选，不影响功能）
- **`frontend/motion-workspace.js`** (L353-356, L364-367, L376-378, L457-462)：文件名记录相关代码（保留用于未来扩展）

### Configuration
- **`.env`** (L38-40)：添加测试模式环境变量

## 🧪 测试流程

### 手动测试步骤

1. **启动服务**
   ```bash
   # 确保 Redis 和 MySQL 运行
   # 启动 Backend
   cd backend
   python src/app.py
   ```
   
   **查看启动日志**，应显示：
   ```
   🔧 [TEST MODE] Veo3 測試模式已啟用！
   🔧 [TEST MODE] 觸發條件: veo3_long_video + 上傳圖片
   🔧 [TEST MODE] 測試視頻: tests/IU_Final/IU_Combine.mp4
   ```

2. **访问前端**
   - 打开 `frontend/dashboard.html`
   - 点击 "Video Studio"
   - 选择 "Long Gen (长片生成)"

3. **上传任意图片**
   - 准备**任意图片文件**（不需要特定文件名）
   - 上传到 Shot 1-5 的任意位置

4. **验证结果**
   - 点击 "Generate" 按钮
   - 应立即返回视频预览（`IU_Combine.mp4`）
   - 检查后端日志应显示：
     ```
     🔧 [TEST MODE] 測試模式已啟用，檢查圖片上傳...
     🔧 [TEST MODE] 上傳圖片數量: 5
     🔧 [TEST MODE] 檢測結果: has_images=True
     ✓ [TEST MODE] 測試視頻已複製到 outputs
     ```
   - **Worker 不应该收到任何任务**

## 🔄 关闭测试模式

### 方法 1：修改环境变量
```env
VEO3_TEST_MODE=false  # 或删除此行
```

### 方法 2：重启 Backend
```bash
# 修改 .env 后重启 Backend 服务
```

## 🗑️ 完全移除测试功能

当 Veo3 Token 恢复后，可按以下步骤清理：

### 1. 删除 Backend 代码
- 删除 `backend/src/config.py` 第 43-45 行（VEO3_TEST_MODE 配置）
- 删除 `backend/src/app.py` 第 164-166 行的导入
- 删除 `backend/src/app.py` 第 772-815 行的拦截逻辑
- 删除 `backend/src/app.py` 第 1476-1482 行的启动日志

### 2. 删除 Frontend 代码（可选）
- 删除 `frontend/motion-workspace.js` 所有带 `[TEMP]` 注释的代码块（文件名记录相关）

### 3. 删除环境变量
- 删除 `.env` 文件第 38-40 行

### 4. 删除测试文件
```bash
rm backend/test_config.py
rm docs/VEO3_TEST_MODE_README.md
rm docs/VEO3_TEST_MODE_DEBUG.md
```

## ⚠️ 注意事项

1. **不影响其他工作流**：测试模式仅对 `veo3_long_video` 工作流生效
2. **自动触发**：只要上传图片就会触发，无需特定文件名
3. **视频文件存在性**：如果 `tests/IU_Final/IU_Combine.mp4` 不存在，会在日志中报错
4. **不写入数据库**：测试模式跳过 Job 数据库记录，不影响统计数据
5. **Redis 状态**：仍会在 Redis 中存储状态，但标记为 `test_mode: 'true'`

## 📊 日志示例

### Backend 日志（成功）
```
🔧 [TEST MODE] Veo3 測試模式已啟用！
🔧 [TEST MODE] 觸發條件: veo3_long_video + 上傳圖片
🔧 [TEST MODE] 測試視頻: tests/IU_Final/IU_Combine.mp4
...
🔧 [TEST MODE] 測試模式已啟用，檢查圖片上傳...
🔧 [TEST MODE] 上傳圖片數量: 5
🔧 [TEST MODE] 檢測結果: has_images=True
🔧 [TEST MODE] ✅ 檢測到圖片上傳，返回測試視頻: tests/IU_Final/IU_Combine.mp4
✓ [TEST MODE] 測試視頻已複製到 outputs: IU_Combine.mp4
```

## 🔗 相关文件

- 测试视频：[tests/IU_Final/IU_Combine.mp4](../tests/IU_Final/IU_Combine.mp4)
- 配置文件：[.env](../.env)
- Backend 配置：[backend/src/config.py](../backend/src/config.py)
- Backend API：[backend/src/app.py](../backend/src/app.py)
- Frontend 逻辑：[frontend/motion-workspace.js](../frontend/motion-workspace.js)

---

**创建日期**: 2026-01-30  
**版本**: v1.0  
**状态**: ✅ 已实现并测试

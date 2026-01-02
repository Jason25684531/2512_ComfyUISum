# 🔍 问题诊断清单

## 当前状态分析

### ✅ 正常运行的服务
- **Backend API**: 运行中 (http://127.0.0.1:5000)
- **MySQL 数据库**: 连接成功 (localhost:3307)
- **Redis**: 连接成功 (localhost:6379)
- **任务推送**: 成功写入 Redis 队列和 MySQL

### ❌ 发现的问题

#### 1. **Worker 未运行** (最严重)
**症状:**
- 任务已推送到 Redis 队列
- 任务已写入 MySQL 数据库
- 但没有看到 Worker 拉取任务的日志
- ComfyUI 没有收到任何请求

**解决方案:**
```powershell
# 在新的 PowerShell 终端运行
cd D:\01_Project\2512_ComfyUISum
python worker/src/main.py
```

**验证 Worker 启动成功的标志:**
```
[Worker] ✅ Redis 連接成功
[Worker] ✅ ComfyUI 連接成功
[Worker] 監聽佇列: job_queue
[Worker] 等待任務中...
```

---

#### 2. **页面刷新后视图跳转** (已修复但需验证)
**症状:**
- 刷新页面后回到 Dashboard
- localStorage 可能未正确保存

**已实施的修复:**
- 在 `navigateTo()` 中添加 `localStorage.setItem('currentView', viewId)`
- 在 DOMContentLoaded 中恢复视图状态

**验证方法:**
1. 切换到 Gallery 视图
2. 打开浏览器开发者工具 → Application → Local Storage
3. 检查是否有 `currentView: "gallery"`
4. 刷新页面，应该还在 Gallery 视图

**如果问题仍存在，检查:**
```javascript
// 打开浏览器控制台运行
localStorage.getItem('currentView')
// 应该返回当前视图名称
```

---

#### 3. **Tailwind CSS CDN 警告** (开发环境正常)
**症状:**
```
cdn.tailwindcss.com should not be used in production
```

**说明:**
- 这是**开发环境的正常警告**
- 不影响功能
- 生产环境才需要安装 Tailwind CLI

**生产环境解决方案 (Phase 4):**
```bash
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init
```

---

## 🚀 完整启动流程

### 1. 启动 Docker 服务 (MySQL + Redis)
```powershell
docker-compose up -d
docker ps  # 验证全部 healthy
```

### 2. 启动 Backend (终端 1)
```powershell
cd D:\01_Project\2512_ComfyUISum
python backend/src/app.py
```

**成功标志:**
```
✓ MySQL 連接池建立成功: localhost:3307/studio_db
✓ Redis 连接成功: localhost:6379
* Running on http://127.0.0.1:5000
```

### 3. 启动 Worker (终端 2)
```powershell
cd D:\01_Project\2512_ComfyUISum
python worker/src/main.py
```

**成功标志:**
```
[Worker] ✅ Redis 連接成功
[Worker] ✅ ComfyUI 連接成功
[Worker] 監聽佇列: job_queue
[Worker] 等待任務中...
```

### 4. 启动 ComfyUI (终端 3)
```powershell
cd D:\02_software\ComfyUI_windows_portable
.\run_nvidia_gpu.bat
```

**验证 ComfyUI 启动:**
- 浏览器打开: http://127.0.0.1:8188
- 或运行: `curl http://127.0.0.1:8188/system_stats`

### 5. 打开前端 (Live Server)
- 用 VS Code Live Server 打开 `frontend/index.html`
- 或直接双击 HTML 文件

---

## 🧪 测试完整流程

### 测试 1: 图像生成
1. 打开前端 → Image Composition → Text to Image
2. 输入 Prompt: "a beautiful sunset"
3. 点击 Generate
4. **观察 Worker 终端**，应该看到:
   ```
   [Worker] 📥 收到任務: job_id=xxx
   [Worker] 🎨 提交 ComfyUI: prompt_id=xxx
   [Worker] ⏳ 等待 ComfyUI 完成...
   ```
5. 前端应该显示生成的图片

### 测试 2: Personal Gallery
1. 切换到 Personal Gallery
2. 应该看到历史记录卡片（当前有 4 笔）
3. 点击"重新整理"按钮
4. **打开浏览器控制台**，不应该有错误
5. 点击 Remix 按钮，应该自动填充表单

### 测试 3: 页面刷新保持视图
1. 在 Gallery 视图刷新页面
2. 应该还在 Gallery（不跳回 Dashboard）
3. 切换到其他视图，刷新也应该保持

---

## 🐛 调试命令

### 检查 Redis 队列
```powershell
docker exec studio-redis redis-cli -a mysecret LLEN job_queue
# 应该返回队列中的任务数量
```

### 检查 MySQL 数据
```powershell
docker exec studio-mysql mysql -ustudio_user -pstudio_password studio_db -e "SELECT id, status, prompt, created_at FROM jobs ORDER BY created_at DESC LIMIT 5;"
```

### 检查 Worker 进程
```powershell
Get-Process python | Where-Object {$_.StartTime -gt (Get-Date).AddMinutes(-10)}
```

### 清空 Redis 队列（重置测试）
```powershell
docker exec studio-redis redis-cli -a mysecret FLUSHALL
```

---

## 📊 预期日志输出

### Backend 日志（正常）
```
✓ MySQL 連接池建立成功: localhost:3307/studio_db
✓ Redis 连接成功: localhost:6379
✓ 任务已推送到队列: job_id=xxx
✓ 任務記錄插入成功: xxx
```

### Worker 日志（正常）
```
[Worker] 📥 收到任務: job_id=xxx, workflow=text_to_image
[Worker] 📤 上傳圖片完成 (如有)
[Worker] 🎨 提交 ComfyUI: prompt_id=xxx
[Worker] ⏳ 等待 ComfyUI 完成...
[Worker] ✅ 任務完成: output_path=xxx.png
```

### 前端控制台（正常）
```
[Generate] 任務提交成功: job_id=xxx
[Status] 檢查狀態: queued
[Status] 檢查狀態: processing
[Status] 檢查狀態: completed
[Result] 顯示結果: [圖片URL]
```

---

## 🎯 立即行動

**最重要的一步: 启动 Worker！**

```powershell
# 打开新的 PowerShell 终端
cd D:\01_Project\2512_ComfyUISum
python worker/src/main.py
```

然后提交一个测试任务，观察 Worker 终端的输出。

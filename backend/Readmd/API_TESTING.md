# API 测试集合

用于 Postman、EchoAPI 或其他 API 测试工具的测试用例集合。

## 基础配置

- **Base URL**: `http://localhost:5000`
- **Content-Type**: `application/json`

## 测试用例

### 1. 健康检查

**请求:**
```
GET {{baseUrl}}/health
```

**预期响应:** 200 OK
```json
{
  "status": "ok",
  "redis": "healthy"
}
```

---

### 2. 提交文生图任务

**请求:**
```
POST {{baseUrl}}/api/generate
Content-Type: application/json

{
  "prompt": "a cyberpunk cat in neon city, highly detailed, 8k",
  "seed": 12345,
  "workflow": "sdxl"
}
```

**预期响应:** 202 Accepted
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued"
}
```

**说明:** 保存返回的 `job_id` 用于后续查询。

---

### 3. 查询任务状态

**请求:**
```
GET {{baseUrl}}/api/status/{{job_id}}
```

**预期响应:** 200 OK
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "progress": 0,
  "image_url": "",
  "error": ""
}
```

**状态说明:**
- `queued`: 等待处理
- `processing`: 正在生成
- `finished`: 已完成
- `failed`: 失败

---

### 4. 测试输入验证（空 prompt）

**请求:**
```
POST {{baseUrl}}/api/generate
Content-Type: application/json

{
  "prompt": "",
  "seed": 12345
}
```

**预期响应:** 400 Bad Request
```json
{
  "error": "prompt is required and cannot be empty"
}
```

---

### 5. 测试不存在的任务

**请求:**
```
GET {{baseUrl}}/api/status/00000000-0000-0000-0000-000000000000
```

**预期响应:** 404 Not Found
```json
{
  "error": "Job not found"
}
```

---

## Postman 环境变量

创建环境并设置以下变量：

| 变量名 | 值 | 类型 |
|--------|-----|------|
| baseUrl | http://localhost:5000 | default |
| job_id | (动态获取) | default |

## EchoAPI 使用步骤

1. 创建新集合 "Studio Core Backend"
2. 添加以上 5 个请求
3. 设置环境变量 `{{baseUrl}}`
4. 按顺序执行测试用例
5. 第 2 步后，复制返回的 `job_id` 用于第 3 步

## 自动化测试脚本

如果你更喜欢使用 Python 脚本测试，运行：

```powershell
python test_api.py
```

这将自动执行所有测试用例并生成报告。

## 常见问题

### Q: 提交任务后立即查询状态显示 "queued"？
A: 这是正常的。Worker 服务尚未实现，任务会停留在队列中。等 Day 3 完成 Worker 后，状态会自动更新。

### Q: Redis 连接失败？
A: 确保 Redis 容器正在运行：
```powershell
docker ps | findstr redis
```

### Q: 端口 5000 被占用？
A: 可以修改 `app.py` 中的端口号，或关闭占用该端口的程序。

## 下一步

完成 Day 3 Worker 实现后，你可以：
1. 提交任务
2. 轮询状态直到 `status` 变为 `finished`
3. 通过 `image_url` 获取生成的图片

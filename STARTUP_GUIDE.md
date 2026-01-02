# 🚀 启动方式选择指南

## 概述

ComfyUI Studio 提供三种启动方式，适用于不同场景。

---

## 📋 启动方式对比

| 方式 | 适用场景 | Docker | Backend | Worker | 优点 | 缺点 |
|------|---------|--------|---------|--------|------|------|
| **开发模式** | 本地开发调试 | MySQL+Redis | 本地 Python | 本地 Python | 即时生效，方便调试 | 需手动管理 |
| **混合模式** | 快速测试 | 仅基础服务 | 本地 Python | 本地 Python | 环境简单 | 依赖本地 Python |
| **生产模式** | 部署上线 | 全服务 | Docker | Docker | 环境隔离，一键部署 | 修改代码需重建 |

---

## 🛠️ 方式一：开发模式（推荐用于开发）

**使用脚本：** `start_all_with_docker.bat`

### 架构

```
┌─────────────────────────────────────────┐
│           Docker (基础服务)              │
│  ┌───────────┐      ┌──────────┐       │
│  │   MySQL   │      │  Redis   │       │
│  │  :3307    │      │  :6379   │       │
│  └───────────┘      └──────────┘       │
└─────────────────────────────────────────┘
           ↑                    ↑
           │                    │
┌──────────┴────────────────────┴─────────┐
│         本地 Python 环境                 │
│  ┌───────────┐      ┌──────────┐       │
│  │  Backend  │      │  Worker  │       │
│  │  :5000    │      │   本地    │       │
│  └───────────┘      └──────────┘       │
└─────────────────────────────────────────┘
```

### 启动步骤

```powershell
# 双击运行
.\start_all_with_docker.bat

# 或 PowerShell 运行
.\start_all_with_docker.bat
```

### 特点

✅ **优点：**
- 可直接在终端查看 Backend/Worker 日志
- 修改代码后只需重启 Python 进程（无需重建 Docker）
- 方便使用调试器（VS Code Debugger）
- Worker 可访问本地 ComfyUI（localhost:8188）

❌ **缺点：**
- 需要配置本地 Python 环境
- 需要手动管理多个终端窗口

### 适用场景

- 🔧 开发新功能
- 🐛 调试问题
- 🧪 测试新代码

---

## 🎯 方式二：仅基础服务（最简化）

**使用脚本：** `start_all.bat`

### 架构

```
┌─────────────────────────────────────────┐
│           Docker Compose                 │
│         (docker-compose.dev.yml)         │
│  ┌───────────┐      ┌──────────┐       │
│  │   MySQL   │      │  Redis   │       │
│  └───────────┘      └──────────┘       │
└─────────────────────────────────────────┘

本地手动启动：
  - python backend/src/app.py
  - python worker/src/main.py
```

### 启动步骤

```powershell
# 1. 先启动 Docker 基础服务
docker-compose -f docker-compose.dev.yml up -d

# 2. 双击运行（会自动启动 Backend + Worker）
.\start_all.bat
```

### 特点

✅ **优点：**
- 最简单的开发方式
- 完全控制 Python 进程

❌ **缺点：**
- 需要手动管理 Docker 服务

---

## 🏭 方式三：生产模式（全 Docker）

**使用脚本：** `start_production.bat`

### 架构

```
┌─────────────────────────────────────────────────┐
│             Docker Compose                       │
│         (docker-compose.yml + profiles)          │
│  ┌─────────┐ ┌────────┐ ┌─────────┐ ┌────────┐│
│  │  MySQL  │ │ Redis  │ │ Backend │ │ Worker ││
│  │  :3307  │ │ :6379  │ │  :5000  │ │        ││
│  └─────────┘ └────────┘ └─────────┘ └────────┘│
└─────────────────────────────────────────────────┘
```

### 启动步骤

```powershell
# 双击运行
.\start_production.bat

# 或手动运行
docker-compose --profile production up -d --build
```

### 特点

✅ **优点：**
- 一键启动所有服务
- 环境完全隔离
- 接近真实生产环境
- 可直接部署到服务器

❌ **缺点：**
- 修改代码需要重建 Docker 镜像
- 查看日志需要使用 `docker logs`
- Worker 无法访问本地 ComfyUI（需配置网络）

### 查看日志

```powershell
# 查看所有日志
docker-compose --profile production logs -f

# 查看单个服务
docker logs -f studio-backend
docker logs -f studio-worker
```

---

## 🔧 Docker Worker 配置说明

### 为什么默认不启动 Docker Worker？

在 `docker-compose.yml` 中，Worker 服务使用了 `profiles: [production]`：

```yaml
worker:
  ...
  profiles:
    - production  # 只在生产模式启动
```

**原因：**
1. **避免冲突：** 本地 Worker 和 Docker Worker 会竞争同一个 Redis 队列
2. **开发便利：** 本地 Worker 更方便查看日志和调试
3. **访问限制：** Docker Worker 无法轻松访问本地 ComfyUI

### 如何启用 Docker Worker？

```powershell
# 方式 1: 使用 profile（推荐）
docker-compose --profile production up -d

# 方式 2: 手动启动 Worker
docker-compose up -d worker

# 方式 3: 修改 docker-compose.yml
# 删除 worker 服务下的 profiles 配置
```

---

## 📊 配置文件说明

### docker-compose.yml（主配置）

包含所有服务，Worker 默认不启动（需 `--profile production`）

### docker-compose.dev.yml（开发配置）

只包含基础服务（MySQL + Redis），用于开发环境

---

## 🎯 推荐使用方式

### 日常开发

```powershell
.\start_all_with_docker.bat
```

**理由：** 方便调试，修改代码即时生效

### 快速测试

```powershell
.\start_all.bat
```

**理由：** 简单快速

### 生产部署

```powershell
.\start_production.bat
```

**理由：** 环境隔离，一键部署

---

## 🛑 停止服务

### 停止本地 Python 服务

直接关闭对应的命令窗口

### 停止 Docker 服务

```powershell
# 开发模式
docker-compose -f docker-compose.dev.yml down

# 生产模式
docker-compose --profile production down

# 停止所有（保留数据）
docker-compose down

# 停止并删除数据
docker-compose down -v
```

---

## 🔍 故障排查

### Worker 没有收到任务

**原因：** Docker Worker 和本地 Worker 同时运行

**解决：**
```powershell
# 停止 Docker Worker
docker stop studio-worker

# 或只启动基础服务
docker-compose -f docker-compose.dev.yml up -d
```

### 端口冲突

**MySQL 3306 冲突：** 已映射到 3307，检查本地 3307 是否被占用

**Redis 6379 冲突：** 检查本地 Redis 是否运行

**Backend 5000 冲突：** 检查是否有其他 Flask 应用

---

## 📝 总结

| 场景 | 推荐方式 | 命令 |
|------|---------|------|
| 开发新功能 | 开发模式 | `start_all_with_docker.bat` |
| 调试问题 | 开发模式 | `start_all_with_docker.bat` |
| 快速测试 | 仅基础服务 | `start_all.bat` |
| 部署上线 | 生产模式 | `start_production.bat` |

**核心原则：** 开发时用本地 Worker，生产时用 Docker Worker

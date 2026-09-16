# AITS 部署指南 · 总览

## 项目概述

AITS（AI Test System）是基于 Django + Vue.js 的 AI 测试系统，主要组件：

- **后端**：Django + Django REST Framework + ASGI（WebSocket）
- **前端**：Vue 3 + Element Plus + Vite
- **数据库**：SQLite（开发默认）
- **缓存**：Redis
- **异步任务**：Celery + Celery Beat
- **AI**：LangChain + OpenAI / DeepSeek / Ollama 等

### 主要功能模块

1. **API 测试**：OpenAPI/Swagger 解析、用例生成与执行  
2. **Web 测试**：Playwright UI 自动化、AI 用例与脚本  
3. **App 测试**：Sonic 云真机（**选修**，需单独部署 Sonic）  
4. **性能测试**：压测、大盘、AI 诊断  
5. **定时任务**：Web / API / App 套件调度  
6. **项目管理**、**知识库（RAG）**、**消息通知**

---

## 按平台选择文档

请**只打开与你环境匹配**的一份指南，无需交叉阅读其他平台章节。

| 文档 | 适用环境 | 推荐入口 |
|------|----------|----------|
| [AITS部署指南-Windows.md](./AITS部署指南-Windows.md) | Windows 10/11 本机（推荐） | `一键安装AITS.bat` / `一键启动AITS.bat`（**不走 Docker 主路径**） |
| [AITS部署指南-macOS.md](./AITS部署指南-macOS.md) | macOS 本机 | **Docker Compose**（`scripts/docker-init.sh`）或 Conda 手工 |
| [AITS部署指南-Linux云服务器.md](./AITS部署指南-Linux云服务器.md) | Linux 云主机 | **Docker Compose**（生产/演示）或 Part A Conda 远程开发 |

根目录 [本地开发环境部署文档.md](../../本地开发环境部署文档.md) 为**索引页**，指向以上文档。

---

## 公共环境要求

| 项 | 要求 |
|----|------|
| Python | 3.12（Conda 环境名 `aits-backend`） |
| Node.js | **24.16.0**（Windows 离线包 / Docker 构建镜像；手工路径 ≥18） |
| Redis | **5.0.14.1**（Windows 离线包）；Docker 镜像 `redis:5.0.14-alpine` |
| Git | 最新稳定版 |
| Conda | Miniconda 或 Anaconda |
| JDK | 1.8+（部分 App/Agent 场景） |
| Docker | macOS / Linux **核心栈推荐**；Windows 本机仍用 `.bat`；选修另含 Sonic、Prometheus/Grafana |

### 硬件建议

- 内存：≥ 4GB，推荐 8GB+  
- 磁盘：≥ 3GB（含 Conda 与 `node_modules`）  
- 网络：可访问 PyPI / npm 与 AI API

---

## 三端对照（速查）

| 项目 | Windows | macOS | Linux 云服务器 |
|------|---------|-------|----------------|
| **推荐部署方式** | `.bat` 一键安装/启动 | **Docker Compose** | **Docker Compose**（生产） |
| 包管理 / 前置 | winget（可选）、MSI | Docker Desktop +（可选）Homebrew | Docker Engine + Compose |
| 一键脚本 | 有（`.bat`） | `scripts/docker-init.sh` | 同左 |
| 对外访问端口 | 5173 / 8000 | **8080**（Nginx 反代） | **8080**（安全组放行） |
| Celery Worker | `-P solo`（与启动脚本一致） | Compose 内 prefork | Compose 内 prefork |
| Playwright | 默认有界面（`AITS_PLAYWRIGHT_HEADLESS=0`） | 容器内 **headless** | 容器内 **headless** |
| 数据持久化 | 工程目录 `backend/db.sqlite3` 等 | Docker 卷 `aits_data` | Docker 卷 `aits_data` |
| Redis | MSI **5.0.14.1** | Compose `redis:5.0.14-alpine` | 同左 |
| Node（前端构建） | MSI **24.16.0** | Docker `node:24.16.0-bookworm` | 同左 |
| 版本基准文件 | `tools/installers/versions.json` | `docker/versions.env` | 同左 |
| 手工 Conda 路径 | 可选（高级） | 文档第二节 | Part A 远程开发 |

---

## 选修模块（快速路径可跳过）

以下能力**不属于** API/Web 核心部署路径（快速上手可跳过）：

- **Sonic / App 测试**：见各平台文档末尾「选修附录 · Sonic」  
- **性能大盘 Prometheus + Grafana**：见 Windows 附录最完整，macOS/Linux 为简述  

---

## 通用验证清单

部署完成后，在**运行 AITS 的机器**上确认：

1. `redis-cli ping` → `PONG`  
2. 前端：http://localhost:5173（Linux 远程开发为 `http://<服务器IP>:5173`）  
3. 后端：http://localhost:8000/api/v1/health/  
4. Django Admin：http://localhost:8000/admin/（需已 `createsuperuser`）  
5. Celery：在 `python manage.py shell` 中执行 `debug_task.delay()` 无报错（可选）

---

## 定时任务 Cron 示例

```
0 9 * * 1-5        # 工作日 9:00
*/30 * * * *       # 每 30 分钟
0 0 1 * *          # 每月 1 日 0:00
```

详细说明见各平台文档中的 Celery Beat 章节。

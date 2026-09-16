# AITS - AI 赋能的智能测试平台（开源 v1）

以 LLM + RAG 驱动的 **API 接口自动化测试平台**，用 AI 把「读接口文档 → 写用例 → 编排场景 → 跑回归」这条链路自动化。

> **关于本仓库**：这是 AITS 的开源 v1 版本，聚焦 **API 接口测试** 与 **AI 能力**（LLM / RAG / MCP）。
> Web UI 自动化、App 移动端、性能测试、缺陷管理等模块属于 AITS 完整版，不包含在本仓库中。
> 详细差异见下方[功能对比](#功能对比开源-v1-vs-aits-完整版)。

---

## 项目简介

传统接口自动化最耗时的不是执行，而是**写用例**和**维护场景**。AITS 把大模型接入这条链路：

- 上传 OpenAPI / Swagger / Postman 文档，AI 直接产出可执行的 HttpRunner 用例
- 用自然语言描述业务流程，场景智能体自动完成多接口串联与参数传递
- 把需求文档、接口规范灌入知识库，AI 生成用例时带上业务上下文（RAG）

**适合谁**：需要落地接口自动化的测试工程师、测试开发，以及想动手实践 AI + 测试结合的学习者。

---

## 核心特性

| 能力 | 说明 |
|------|------|
| **规范导入** | 支持 OpenAPI / Swagger / Postman Collection，自动解析为模块与端点树 |
| **AI 生成用例** | 端点级批量生成正向 / 异常 / 边界用例，直接产出 HttpRunner 格式 |
| **AI 场景编排** | 基于 LangGraph 的场景智能体，结合 RAG 检索，WebSocket 流式输出生成过程 |
| **RAG 知识库** | 支持 Chroma / Milvus 向量库，嵌入模型可走国内镜像或完全离线加载 |
| **多模型接入** | LLM 配置中心统一管理 OpenAI / DeepSeek / Ollama 等，内置 MCP 工具协议支持 |
| **执行与报告** | Celery 异步执行、Allure 报告、免登录公开报告页，方便分享给非平台用户 |
| **Postman 脚本翻译** | AI 把 Postman 的 `pm.test()` JS 断言翻译成 HttpRunner 的 validate / extract |
| **平台基础能力** | 项目与成员管理、多环境配置、Cron 定时任务、钉钉 / 企微 / 邮件通知 |

---

## 功能对比：开源 v1 vs AITS 完整版

### 测试能力

| 功能模块 | 开源 v1 | AITS 完整版 |
|---------|:------:|:----------:|
| API 接口测试（规范导入 / 端点用例 / 场景编排 / HttpRunner 执行） | ✅ | ✅ |
| Web UI 自动化测试（Playwright / MidScene 脚本生成与执行） | ❌ | ✅ |
| App 移动端测试（Sonic 云真机 / 设备管理 / POM 元素库） | ❌ | ✅ |
| 性能测试（Locust 压测 / Prometheus + Grafana 大盘 / AI 告警诊断） | ❌ | ✅ |

### AI 能力

| 功能模块 | 开源 v1 | AITS 完整版 |
|---------|:------:|:----------:|
| LLM 模型配置与连接测试 | ✅ | ✅ |
| RAG 向量知识库（Chroma / Milvus） | ✅ | ✅ |
| MCP 配置与工具接入 | ✅ | ✅ |
| AI 生成 API 端点用例 | ✅ | ✅ |
| AI 场景编排智能体（流式输出） | ✅ | ✅ |
| Postman 脚本 AI 翻译 | ✅ | ✅ |
| AI 生成 Web UI 脚本与用例 | ❌ | ✅ |
| 提示词管理（Prompt Template 版本化） | ❌ | ✅ |
| AI 智能技能（失败根因分析 / 性能告警诊断） | ❌ | ✅ |
| 需求完备性评测（文档多维度打分） | ❌ | ✅ |
| 混合检索与重排（BM25 + RRF + Reranker） | ❌ | ✅ |

### 平台能力

| 功能模块 | 开源 v1 | AITS 完整版 |
|---------|:------:|:----------:|
| 用户注册 / 登录 / JWT 认证 | ✅ | ✅ |
| 项目管理与成员角色 | ✅ | ✅ |
| 系统级权限管理（部门 / 角色 / 菜单 / 审计日志） | ❌ | ✅ |
| 环境管理 | ✅ | ✅ |
| 知识库文档管理 | ✅ | ✅ |
| 定时任务调度（Cron） | ✅ 仅 API 类型 | ✅ API / Web / App |
| 消息通知（钉钉 / 企微 / 邮件） | ✅ | ✅ |
| 测试报告（Allure）与公开报告页 | ✅ | ✅ |
| 智能驾驶舱 Dashboard | ✅ 仅 API 项目维度 | ✅ 全测试域 |
| 缺陷管理（看板 / 追溯链 / 回归联动） | ❌ | ✅ |

### 部署方式

| 功能模块 | 开源 v1 | AITS 完整版 |
|---------|:------:|:----------:|
| Windows 一键安装（离线依赖包） | ✅ | ✅ |
| Docker Compose（macOS / Linux 云服务器） | ✅ | ✅ |

> AITS 完整版能力了解入口：<https://ai.lemonban.com>

---

## 技术栈

**后端**

- Django 4.2 + Django REST Framework 3.14
- Celery 5.3（异步任务）+ Channels 4.0（WebSocket 流式输出）
- SQLite（默认，开箱即用）/ Redis 5（缓存与消息队列）
- 内嵌 HttpRunner 执行引擎

**AI**

- LangChain 1.2 / LangGraph 1.0（场景智能体）
- ChromaDB 1.4 + sentence-transformers（向量检索）
- HuggingFace 嵌入模型，默认 `BAAI/bge-large-zh-v1.5`

**前端**

- Vue 3.3（`<script setup>`）+ Vite 5 + Element Plus 2.4
- Pinia（状态管理）、ECharts（图表）、Monaco Editor（代码编辑）

**运行环境**

- Python 3.12（Conda 环境 `aits-backend`）
- Node.js 24 / Redis 5

---

## 快速开始 · Windows（推荐）

### 1. 下载离线依赖包

出于仓库体积考虑，Miniconda / Node.js / Redis 三个安装包**不随代码分发**，需单独下载后放入 `tools/installers/`：

```
tools/installers/
├── Miniconda3-latest-Windows-x86_64.exe
├── node-v24.16.0-x64.msi
└── Redis-x64-5.0.14.1.msi
```

> 网盘下载地址（百度网盘）：<https://pan.baidu.com/s/192I_P15dfgY910cwg8AzeQ>，提取码 `369c`
>
> 文件名可用默认名，安装脚本会自动识别；也可放在 `tools/` 目录下。

### 2. 一键安装

双击项目根目录的 **`一键安装AITS.bat`**：

- 脚本会先确认离线包是否就位，**输入 `yes` 后继续**
- 若本机未安装 Miniconda，会列出可用盘符供你选择安装位置（默认系统盘）
- 自动完成：静默安装依赖 → 创建 Conda 环境 → `pip install` → 生成 `.env` → 数据库迁移 → `npm install`
- 可选创建管理员账号

> 首次安装 Miniconda 约需 10-30 分钟，界面长时间无输出属正常，脚本每 45 秒打印一次进度。
> 完整日志见项目根目录 `install.log`。

### 3. 启动服务

双击 **`一键启动AITS.bat`**，会依次拉起 Redis、Celery Worker / Beat、Django、Vite。

### 4. 访问

- 前端：<http://localhost:5173>
- 后端：<http://localhost:8000>

关停服务：双击 **`一键关闭AITS.bat`**（不会停止 Redis 服务）。

---

## 快速开始 · macOS / Linux（Docker）

```bash
chmod +x scripts/docker-init.sh
./scripts/docker-init.sh
```

访问 <http://localhost:8080>。

云服务器防火墙、环境变量与排错见 [AITS-Docker部署教程（macOS-Linux云服务器）.md](./AITS-Docker部署教程（macOS-Linux云服务器）.md)。

---

## 目录结构

```
aits-v1/
├── backend/                    Django 后端
│   ├── aits_backend/           项目配置（settings / urls / celery / asgi）
│   ├── apps/                   业务模块
│   │   ├── ai_core/            LLM / RAG / MCP 配置与 AI 智能体
│   │   ├── api_testing/        API 规范、用例、场景、套件、执行
│   │   ├── projects/           项目、成员、环境、知识库、Dashboard
│   │   ├── scheduled_tasks/    Cron 定时任务与执行日志
│   │   ├── notifications/      消息渠道与通知推送
│   │   ├── users/              用户与认证
│   │   ├── common/             WebSocket、文件存储、Celery 工具
│   │   └── httprunner/         内嵌 HttpRunner 执行引擎
│   ├── utils/                  通用工具函数
│   ├── env.example             后端环境变量模板
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   Vue 3 前端
│   ├── src/                    views / components / api / stores / router
│   └── Dockerfile
├── scripts/                    安装、启动、Docker 脚本
├── docker/                     组件版本定义（versions.env）
├── docs/deploy/                各平台部署指南
├── tools/installers/           离线依赖包目录（需自行下载填充）
└── docker-compose.yml          Docker Compose 编排入口
```

---

## 文档

| 文档 | 说明 |
|------|------|
| [部署指南 · 总览](./docs/deploy/AITS部署指南-总览.md) | 模块说明、公共要求、三端对照 |
| [部署指南 · Windows](./docs/deploy/AITS部署指南-Windows.md) | Windows 本机部署与完整排错表 |
| [部署指南 · macOS](./docs/deploy/AITS部署指南-macOS.md) | macOS 环境说明 |
| [部署指南 · Linux 云服务器](./docs/deploy/AITS部署指南-Linux云服务器.md) | 云服务器部署 |
| [Docker 部署教程](./AITS-Docker部署教程（macOS-Linux云服务器）.md) | Docker Compose 完整步骤 |
| [部署文档索引](./本地开发环境部署文档.md) | 按环境选择对应指南 |

---

## 常见问题

| 现象 | 处理方式 |
|------|----------|
| 提示离线安装包缺失 | 确认 Miniconda / Node / Redis 三个包已放入 `tools/installers/`，且未改动扩展名 |
| Node MSI 报错 **1603** | 未以管理员运行或本机有冲突版 Node；重新双击安装脚本并在 UAC 点「是」，或卸载旧 Node 后重装 |
| Redis 不可用 / 6379 无响应 | Redis MSI 需管理员权限；也可解压便携版 Redis 到 `tools/redis/`，脚本会自动拉起 |
| RAG 测试连接或文档入库超时 | 检查 `backend/.env` 是否含 `HF_ENDPOINT=https://hf-mirror.com`；完全断网时改用「本地离线加载」并指定模型目录 |
| pip 安装报 403 或超时 | 脚本会自动在阿里云 / 中科大 / 清华 / 官方 PyPI 之间切换，查看 `install.log` 中的 `pip: trying mirror` |

更多排错项见 [Windows 部署指南](./docs/deploy/AITS部署指南-Windows.md) 的「常见问题排查」表。

---

## 了解完整版

Web UI 自动化、App 移动端测试、性能测试、AI 智能技能、缺陷管理等完整能力，可访问 <https://ai.lemonban.com> 了解。

---

## License

本项目基于 [GNU Affero General Public License v3.0](./LICENSE)（AGPL-3.0）发布，版权归柠檬班所有。

- 你可以自由使用、修改和分发本软件
- 若你修改后**分发**给他人，或**通过网络提供服务**（如 SaaS），须以 AGPL-3.0 开源你的修改版本
- 商业使用如不希望开源衍生代码，请联系柠檬班获取单独商业授权：<http://www.lemonban.com>
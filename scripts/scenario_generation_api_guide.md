# AI 场景智能体 API 调用指南

> 文件名：`scenario_generation_api_guide.md`（ASCII 路径，便于 Windows 打包脚本识别）

本文档面向**大模型测评班**学员与自动化评测脚本开发者，说明如何通过 HTTP API 调用「AI 场景智能体」生成场景测试用例，并获取可用于 **LLM 语义相似度判定** 的生成结果。

配套示例脚本：[`scenario_generation_api_example.py`](./scenario_generation_api_example.py)

---

## 1. 背景与目标

### 1.1 业务场景

在 AITS「API 自动化」工作区中，**AI 场景智能体**可根据自然语言描述（如「用户注册、登录、申请成为普通用户」）自动生成 HttpRunner 格式的**场景测试用例**。

### 1.2 自动化评测诉求

评测方希望通过 API 完成：

1. 鉴权（JWT）
2. 提交场景描述
3. 拿到智能体生成的脚本内容（`generated_script`）
4. 与预期描述做 LLM 语义相似度对比

### 1.3 为何不能只看首次响应？

`POST generate-scenario` 为**异步任务**设计：

- 首次响应只返回 `task_id` 和 `PROCESSING` 状态
- 实际调用 LLM、生成脚本、入库用例在 **Celery Worker** 中执行（通常 30 秒～数分钟）
- UI 通过 WebSocket 推送进度；**API 调用方应轮询 `task-status` 获取最终结果**

---

## 2. 整体流程

```
┌─────────────┐     POST generate-scenario      ┌─────────────┐
│  调用方脚本  │ ──────────────────────────────► │   Django    │
└─────────────┘         返回 task_id             └──────┬──────┘
       │                                                │
       │         GET task-status/{task_id}              │ delay
       │ ◄────────────────────────────────────────────┤
       │         轮询直到 status=completed              ▼
       │                                        ┌─────────────┐
       │         返回 generated_script          │Celery Worker│
       └────────────────────────────────────────│ + Redis     │
                                                └─────────────┘
```

**前置条件**（缺一不可）：

| 条件 | 说明 |
|------|------|
| 后端 + Celery + Redis 已启动 | Windows 本机用「一键启动AITS.bat」 |
| 项目已创建 | 记下 `project_id` |
| 已导入 API 规范 | OpenAPI / Postman，否则生成接口会报错 |
| 已配置 LLM | 「AI 实验室配置」中填写可用 API Key |
| 有效账号 | 对该项目有编辑权限 |

---

## 3. API 说明

基础地址（Windows 本机默认）：

```
http://127.0.0.1:8000/api/v1
```

macOS Docker 部署请将主机改为 `http://localhost:8080`（经反向代理访问后端）。

### 3.1 获取 JWT Token

```http
POST /api/v1/auth/token/
Content-Type: application/json

{
  "username": "你的用户名",
  "password": "你的密码"
}
```

**响应示例**（SimpleJWT 标准格式）：

```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

后续请求在 Header 中携带：

```
Authorization: Bearer <access>
```

### 3.2 提交场景生成任务

```http
POST /api/v1/projects/{project_id}/api-testing/generate-scenario/
Authorization: Bearer <access>
Content-Type: application/json

{
  "user_request": "请针对系统的用户注册、登录、申请成为普通用户流程设计用例"
}
```

**响应示例**：

```json
{
  "success": true,
  "message": "智能场景生成任务已启动",
  "data": {
    "task_id": "f2daca38-5c2f-4ebd-88ac-f398c9f821a8",
    "status": "PROCESSING",
    "progress": 0,
    "message_detail": "正在初始化场景生成..."
  }
}
```

| 字段 | 说明 |
|------|------|
| `data.task_id` | Celery 任务 ID，用于轮询 |
| `data.status` | 初始为 `PROCESSING` |

**常见错误**：

| message | 原因 |
|---------|------|
| 必须提供业务场景描述 | `user_request` 为空 |
| 项目中没有API规范 | 未导入 OpenAPI/Postman |
| 数据库中没有可用的LLM配置 | 未在 AI 实验室配置 LLM |
| 您没有该项目的编辑权限 | 账号权限不足 |

### 3.3 轮询任务状态（获取生成结果）

```http
GET /api/v1/projects/{project_id}/api-testing/task-status/{task_id}/
Authorization: Bearer <access>
```

**进行中响应示例**：

```json
{
  "success": true,
  "data": {
    "task_id": "f2daca38-...",
    "status": "running",
    "progress": 40,
    "message": "正在分析业务场景并生成测试用例..."
  }
}
```

**完成响应示例**（评测所需字段）：

```json
{
  "success": true,
  "message": "任务执行完成",
  "data": {
    "task_id": "f2daca38-...",
    "status": "completed",
    "progress": 100,
    "message": "智能场景测试用例生成成功",
    "success": true,
    "test_case_id": 5,
    "generated_script": "{\"config\":{\"name\":\"...\"},\"teststeps\":[...]}",
    "result": {
      "success": true,
      "status": "completed",
      "test_case_id": 5,
      "generated_script": "{\"config\":{...},\"teststeps\":[...]}"
    }
  }
}
```

| 字段 | 用途 |
|------|------|
| `data.status` | `completed` 表示成功，`failed` 表示失败 |
| `data.generated_script` | **HttpRunner JSON 字符串**，作为评测 actual 输出 |
| `data.test_case_id` | 已入库的场景用例 ID |
| `data.result` | Celery 完整结果，与顶层字段一致 |

**轮询建议**：

- 间隔：2～3 秒
- 超时：5～10 分钟（LLM 慢时可适当加长）
- 终止条件：`status` 为 `completed` 或 `failed`

### 3.4 备用：通过用例详情获取脚本

若只需脚本、且已知 `test_case_id`：

```http
GET /api/v1/projects/{project_id}/api-testing/test-cases/{test_case_id}/
Authorization: Bearer <access>
```

响应 `data.script_content` 与 `generated_script` 内容同源（已入库的 HttpRunner 脚本）。

---

## 4. 示例脚本使用

项目提供可运行示例：[`scripts/scenario_generation_api_example.py`](./scenario_generation_api_example.py)

### 4.1 运行方式

在 **AITS 后端 Python 环境**（已安装 `requests`）中执行：

```bash
# 进入解压后的 AITS 根目录
python scripts/scenario_generation_api_example.py

# 自定义场景描述
python scripts/scenario_generation_api_example.py "请针对用户注册、登录流程设计用例"
```

### 4.2 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AITS_BASE_URL` | `http://127.0.0.1:8000` | 后端地址 |
| `AITS_USERNAME` | `admin` | 登录用户名 |
| `AITS_PASSWORD` | `admin123` | 登录密码 |
| `AITS_PROJECT_ID` | `1` | 项目 ID |

Windows CMD 示例：

```cmd
set AITS_BASE_URL=http://127.0.0.1:8000
set AITS_USERNAME=admin
set AITS_PASSWORD=你的密码
set AITS_PROJECT_ID=1
python scripts\scenario_generation_api_example.py
```

### 4.3 脚本输出

- 控制台打印任务进度与步骤摘要
- 将完整脚本保存为当前目录下的 `scenario_generated_script.json`

---

## 5. 接入 LLM 语义相似度评测

推荐评测流水线：

```
expected（预期）          actual（实际）
─────────────────        ─────────────────────────────
黄金场景描述 /            generated_script 解析后的
标准 HttpRunner 步骤      teststeps 列表或完整 JSON
        │                            │
        └──────────┬─────────────────┘
                   ▼
            LLM 语义相似度判定
            （相似度分数 + 是否通过）
```

**解析 teststeps 示例（Python）**：

```python
import json

def extract_step_names(generated_script: str) -> list[str]:
    doc = json.loads(generated_script)
    steps = doc.get("teststeps") or []
    return [s.get("name", "") for s in steps if isinstance(s, dict)]
```

可将步骤名称列表、请求路径、断言要点等作为 actual 文本，与 expected 一起送入你的评测 Prompt。

---

## 6. curl 快速验证

```bash
# 1. 登录
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"你的密码\"}"

# 2. 提交生成（将 TOKEN、PROJECT_ID 替换为实际值）
curl -s -X POST http://127.0.0.1:8000/api/v1/projects/1/api-testing/generate-scenario/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"user_request\":\"请针对用户注册登录流程设计用例\"}"

# 3. 轮询状态（将 TASK_ID 替换为实际值）
curl -s http://127.0.0.1:8000/api/v1/projects/1/api-testing/task-status/TASK_ID/ \
  -H "Authorization: Bearer TOKEN"
```

---

## 7. 常见问题

### Q1：轮询一直 `running`，没有 `completed`

- 确认 Celery Worker 窗口已启动且无报错
- 确认 Redis 正常运行
- 查看 Worker 日志是否有 LLM 调用失败

### Q2：`completed` 但没有 `generated_script`

- 确认使用的是**已更新**的测评包（`task-status` 已透传场景生成字段）
- 可用 `test_case_id` 调 3.4 备用接口读取 `script_content`

### Q3：生成失败 `failed`

- 检查 AI 实验室 LLM 配置与 API Key 余额
- 检查项目是否已导入 API 规范
- 查看 `data.error` 或 `data.message` 中的具体原因

### Q4：macOS Docker 环境地址不同

- 浏览器访问 `http://localhost:8080`
- API 基础地址一般为 `http://localhost:8080/api/v1`（以实际 docker-compose 配置为准）

---

## 8. 相关源码位置（供讲师参考）

| 模块 | 路径 |
|------|------|
| 提交接口 | `backend/apps/api_testing/views.py` → `ScenarioGenerateView` |
| Celery 任务 | `backend/apps/api_testing/tasks.py` → `generate_scenario_async` |
| 任务状态查询 | `backend/apps/api_testing/views.py` → `TaskStatusView` |
| 场景 Agent | `backend/apps/ai_core/api_scenario_agent.py` |
| 路由注册 | `backend/apps/api_testing/urls.py` |

---

*文档版本：适配大模型测评班 API-only 体验包 · 含 task-status 场景结果透传能力*

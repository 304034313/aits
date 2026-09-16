# AITS 部署指南 · Windows

> 适用：**Windows 10/11 本机**开发与日常运行。  
> 总览与模块说明见 [AITS部署指南-总览.md](./AITS部署指南-总览.md)。  
> **说明：** Windows 本机以本指南 `.bat` 为主路径；macOS / Linux 云服务器请使用 **Docker Compose**（见对应平台文档），Windows 本机暂不推荐 Docker 主路径。

---

## 一、快速路径（推荐）

适用于 **API / Web 自动化**，**不要求** App 测试（Sonic）。

### 只需两个入口

| 文件（项目根目录） | 何时使用 |
|-------------------|----------|
| **`一键安装AITS.bat`** | 首次或换机（可重复执行） |
| **`一键启动AITS.bat`** | 开启服务，双击启动 Django / Vite / Celery（日常开发） |
| **`一键关闭AITS.bat`** | 关停服务，双击停止 Django、Vite、Celery（**不停止** Redis 服务） |

`scripts/` 为内部实现，**无需手动打开**。

### 离线分发包须包含（网盘 ZIP）

`tools/installers/` 内三个安装包 + `versions.json`（**不需要 Git**）：

| 文件 | 版本 |
|------|------|
| `Miniconda3-latest-Windows-x86_64.exe` | conda 25.11.1 → 安装到 **`%LOCALAPPDATA%\AITS\miniconda3`**（不在工程目录内） |
| `node-v24.16.0-x64.msi` | Node v24.16.0 |
| `Redis-x64-5.0.14.1.msi` | Redis 5.0.14.1 |

> **版本单一来源：** `tools/installers/versions.json` 同时约束 macOS / Linux **Docker** 镜像（见 `docker/versions.env`）。升级离线安装包时请同步修改 `versions.json` 的 `docker` 段与 `docker/versions.env`，避免三端运行时版本漂移。

`tools/monitor/` 内性能监控离线三件套 + `versions.json`（**性能测试专用，勿与系统安全软件混淆**）：

| 文件 | 说明 |
|------|------|
| `prometheus-3.12.0.windows-amd64.zip` | Prometheus 便携包 |
| `grafana_13.0.2_26816849631_windows_amd64.msi` | Grafana 服务 |
| `windows_exporter-0.31.7-amd64.msi` | 发压机 CPU/内存等指标 |

性能监控三个一键脚本位于 **`perf-monitor\`** 文件夹（与根目录 AITS 三个 bat 分开）：**`一键安装性能监控.bat`**、**`一键启动性能监控.bat`**、**`一键停止性能监控.bat`**（打包脚本会自动校验）。

首次安装双击 **「一键安装AITS.bat」** 即可：脚本会 **自动弹出 UAC** 请求管理员（Node/Redis MSI 需要）。若点了「否」，Node 会尝试解压到 `tools\node`，Redis 可能仍失败。

### 一键安装会自动完成

- 从 `tools/installers/` **离线静默安装** Miniconda（默认 `%LOCALAPPDATA%\AITS\miniconda3`）、Node、Redis（版本见 `versions.json`）
- 失败时可选择 **winget 兜底**（不再安装 Git）
- 创建 Conda 环境 `aits-backend`（Python 3.12）、`pip install`、`playwright install chromium`
- 生成 `backend/.env`、`frontend/.env`，执行 `migrate`、`npm install`
- `backend/.env` 默认写入 **`HF_ENDPOINT=https://hf-mirror.com`**（RAG 嵌入模型国内镜像）
- 可选 **创建管理员**（`createsuperuser`）

日志：`install.log`（含 conda/node/redis 版本记录）。

### 一键启动会自动完成

- 未安装时提示并可在当前流程内继续安装
- 启动前尽量确保 Redis 可用
- 打开 Celery Worker / Beat、Django、Vite（Windows Terminal 多标签或独立 CMD；各服务由 `scripts\aits-run-*.bat` 启动，避免引号截断命令）
- 各 Python 服务窗口自动设置 **`HF_ENDPOINT`**（与 `scripts/aits-config.bat` 一致，默认 `https://hf-mirror.com`）

访问：**http://localhost:5173**（前端）、**http://localhost:8000**（后端）。

### RAG 嵌入模型与网络（部署前必读）

知识库/RAG 使用 **HuggingFace 嵌入模型**（默认 `BAAI/bge-large-zh-v1.5`），首次「测试连接」或文档入库时会下载权重（体积较大，需数 GB 磁盘与足够内存）。

| 方式 | 说明 |
|------|------|
| **默认（已配置）** | 安装/启动脚本 + `backend/.env` 设置 `HF_ENDPOINT=https://hf-mirror.com`，走国内镜像，**无需 VPN** |
| **完全断网** | 智能驾驶舱 → AI 配置 → RAG → **本地离线加载**，填写离线模型目录（含 `config.json` 与权重文件） |
| **弱机** | RAG 嵌入模型可改为 `BAAI/bge-small-zh-v1.5`（512 维，更小） |

**部署验收（建议）：**

1. 完成一键安装与一键启动  
2. 登录系统 → **智能驾驶舱 → AI 配置 → RAG 知识库**  
3. 创建/启用 RAG 配置后点击 **「测试连接」** 成功  
4. 再上传知识库文档或跑依赖 RAG 的 AI 功能  

若测试连接失败：确认 Celery Worker 窗口已启动；检查 `backend/.env` 是否有 `HF_ENDPOINT`；仍失败见下表「RAG 下载失败」。

### 一键关闭

双击 **`一键关闭AITS.bat`**：按端口（8000、5173）与项目路径结束 Django、Vite、Celery 进程，并尝试关闭标题为 `Celery Worker` 等的 CMD 窗口。**不会停止 Redis**（通常为系统服务，其它项目也可能在用）。

### 常见问题排查

| 情况 | 处理 |
|------|------|
| 提示分发包不完整 | 确认 ZIP 含 `tools/installers/` 三个文件，勿改名 |
| 找不到 Conda | 确认存在 `%LOCALAPPDATA%\AITS\miniconda3\Scripts\conda.exe`（或旧工程 `tools/miniconda3`）；无则管理员重跑安装 |
| Node MSI **1603** | 未管理员 / 本机已有冲突版 Node：重新双击安装 bat 并在 UAC 点「是」；或卸载旧 Node 后重装；日志 `%TEMP%\aits-msi-logs\Node.js-*.log`；新版脚本可回退 `tools\node` |
| Redis MSI 失败 | 必须管理员（UAC 点「是」）；或解压便携 Redis 到 `tools\redis` |
| 安装卡在 `npm` / `DEP0174 DeprecationWarning` | Node 24 警告被 PowerShell 误判为错误；更新 `scripts\aits-common.ps1` 后重跑安装，或设置 `NODE_OPTIONS=--no-deprecation` |
| `npm install failed` / `npm 7.x` + `EBADENGINE` | PowerShell 默认跑 `npm.ps1`（可能是旧版）；新版安装脚本改用 **`npm.cmd`**（与 Node 24 同目录）。仍失败则卸载旧 Node、清空 `C:\Program Files\nodejs` 后重装 |
| Redis 仍不可用 | 重跑安装；或解压便携版到 `tools/redis` |
| 报错 `'xxx' is not recognized` / PowerShell 乱码 | 勿用记事本改脚本；使用仓库自带 `.bat`/`.ps1` |
| winget 兜底后仍缺 conda | 关闭 CMD 重新打开再安装；或删除 `%LOCALAPPDATA%\AITS\miniconda3` 后重装 |
| pip 某镜像 403/超时 | 安装脚本会自动切换阿里云/中科大/清华/官方 PyPI；见 `install.log` 中 `pip: trying mirror` |
| pip 反复下载多个 playwright 版本 / greenlet 冲突 | 已锁定 `playwright==1.51.0`、`pyee==12.0.0`、`greenlet==3.2.2`（与 `gevent==25.9.1` 一致）；先 `Ctrl+C` 后重跑一键安装 |
| `createsuperuser` 报用户名/邮箱已存在 | 数据库里已有管理员；重装时会自动跳过。用原账号登录，或手动 `python manage.py createsuperuser` 换未占用的邮箱 |
| RAG 测试连接/入库超时、连 huggingface.co 失败 | 确认已用**新版**一键启动（带 `HF_ENDPOINT`）；检查 `backend/.env`；或 RAG 改**本地离线**并指定模型目录 |
| Django 窗口只有 `(aits-backend)` 提示符、无 `run_asgi` 日志 | 旧版 `一键启动` 在 WT 里嵌套引号导致命令被截断；更新 `一键启动AITS.bat` 与 `scripts\aits-run-*.bat` 后重开 |
| `conda activate` / `__conda_tmp_*.txt` 被占用或找不到 | 四个 WT 标签同时 `activate` 冲突；新版用 `%LOCALAPPDATA%\AITS\miniconda3\envs\aits-backend\python.exe` 直接启动，请更新 `aits-config.bat` 与 `scripts\aits-run-*.bat` |

与下文手工步骤冲突时，**以两个一键脚本为准**（Celery Worker 使用 **`-P solo`**）。

### 打包离线分发 ZIP（推荐：复制后打 ZIP，不改本机目录）

双击项目根目录 **`打包学员Zip.bat`**：将源码（含 **`sonic-server/`** App 模块）、离线安装包、文档等复制到临时目录并生成**全量** ZIP。

ZIP 默认输出到项目**上一级目录** `D:\...\aits-student-pack-<时间戳>\`（与项目在**同一盘**，不会自动找 E 盘；提示里的 `E:\` 仅为示例）。打包前请保证该盘 **≥400MB 可用**（建议 1GB+），并删除旧的 `aits-student-pack-*` 临时目录。也可指定输出：`打包学员Zip.bat D:\temp\aits-pack`。  
打包脚本会校验 **`一键安装/启动/停止性能监控.bat`** 三件套是否存在；若 `tools/monitor/` 内 MSI/ZIP 离线包缺失会**黄色警告**（打 ZIP 前请补齐三件套安装包）。  
包内自带 `STUDENT_README.txt`（纯英文，避免记事本乱码）。

**会复制（节选）：** `docs/deploy/` 全套部署指南（含 macOS / Linux 云服务器）、根目录 `AITS-Docker部署教程（macOS-Linux云服务器）.md`、`docker-compose.yml`、`docker-compose.monitor.yml`、`docker/`、`.env.docker.example`、`scripts/`（含 `docker-init.sh`）、`perf-monitor/`（含 `.sh` / `.bat`）等。

**不会复制：** `.gitignore`、`打包学员Zip.bat`、`scripts/aits-build-distribution-zip.ps1`、`docs` 下操作手册与 `images/`、`tools/miniconda3`（旧路径兼容）、`node_modules`、`.env`、`db.sqlite3`、工作区/媒体等。Miniconda 由一键安装写入 **`%LOCALAPPDATA%\AITS\miniconda3`**，删工程文件夹不会删除该目录。

可选参数（写在 bat 后面）：`-KeepStaging` 保留临时目录；`-IncludeBackendDevDocs` 包含 `backend/docs`。

---

## 二、环境要求

- Windows 10/11 x64  
- 离线分发包已含离线安装包时：**无需事先安装** Miniconda / Node / Redis / Git  
- 项目 Python 3.12（`aits-backend` 环境）、Node ≥ 18、Redis 5+  
- 路径尽量**无中文、无空格**；磁盘建议 ≥ 5GB（含 `%LOCALAPPDATA%\AITS\miniconda3` 与 `node_modules`）  

### 反复验证打包流程（删工程不换 Conda）

适合「解压 ZIP → 测一键脚本 → 删 `aits-system` → 再解压」的循环：

1. **首次**：解压后运行 `一键安装AITS.bat`（Conda 写入 `%LOCALAPPDATA%\AITS\miniconda3`）
2. **每轮调试**：只删除工程目录，保留 `%LOCALAPPDATA%\AITS\`；解压新 ZIP 后再跑 `一键安装AITS.bat`，将**跳过** Miniconda 安装与已就绪的 pip/Playwright 步骤
3. **彻底重来**：手动删除 `%LOCALAPPDATA%\AITS\miniconda3`
4. **自定义路径**：安装前设置环境变量 `AITS_CONDA_ROOT`（指向已有或目标 Miniconda 目录）

---

## 三、前置条件安装（手工）

一键安装已覆盖大部分步骤；仅在脚本失败或需手工演示时使用。

### 1. Miniconda

1. 下载 [Miniconda3 Windows x86_64](https://docs.conda.io/en/latest/miniconda.html) 并安装  
2. 打开 **Anaconda Prompt** 验证：

```bash
conda --version
python --version
```

若 `conda create` 报 TOS 协议错误，依次执行：

```bash
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2
```

可选清华镜像：

```bash
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/
conda config --set show_channel_urls yes
```

### 2. Node.js

从 [nodejs.org](https://nodejs.org/) 安装 LTS，验证：

```bash
node --version
npm --version
```

### 3. Redis

- 安装 [Redis for Windows MSI](https://github.com/tporadowski/redis/releases)，或  
- 解压 zip 到项目 **`tools/redis`**（含 `redis-server.exe`），由一键脚本自动拉起  

验证：

```bash
redis-cli ping
# PONG
```

`.env` 开发推荐：

```bash
REDIS_URL=redis://localhost:6379/0
```

### 4. Git

[git-scm.com/download/win](https://git-scm.com/download/win)

---

## 四、项目部署（手工）

### 1. 克隆项目

```bash
git clone <项目仓库地址>
cd aits-system
```

确认存在 `backend`、`frontend` 目录。

### 2. 后端

```bash
cd <项目根目录>
conda create -n aits-backend python=3.12 -y
conda activate aits-backend
cd backend
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
pip install -r requirements.txt
playwright install chromium
```

环境变量：

```bash
copy env.example .env
notepad .env
```

开发推荐（与一键安装一致）：

```bash
DEBUG=True
DJANGO_SECRET_KEY=dev-请改为随机字符串
ALLOWED_HOSTS=localhost,127.0.0.1,::1
REDIS_URL=redis://localhost:6379/0
```

数据库：

```bash
python manage.py migrate
python manage.py createsuperuser
```

启动后端（开发）：

```bash
python run_asgi.py
# http://localhost:8000  ws://localhost:8000/ws/
```

### 3. 前端

```bash
cd ..\frontend
npm install
copy .env.example .env
npm run dev
# http://localhost:5173
```

防火墙弹窗选「允许」。

### 4. Celery（手工启动时）

在 **backend** 目录、`aits-backend` 已激活前提下：

```bash
# Worker（Windows 必须用 solo，与 一键启动AITS.bat 一致）
celery -A aits_backend worker -l info -P solo

# Beat（另开终端）
celery -A aits_backend beat --loglevel=info
```

注意模块名是 **`aits_backend`**（下划线），环境名是 **`aits-backend`**（连字符）。

---

## 五、服务启动顺序（手工多窗口）

1. Redis（`redis-server` 或便携版 / 已安装服务）  
2. Celery Worker（`-P solo`）  
3. Celery Beat（可选，定时任务需要）  
4. Django：`python run_asgi.py`  
5. 前端：`npm run dev`  

检查 Redis：`netstat -an | findstr 6379`

---

## 六、验证部署

| 检查项 | 地址 / 命令 |
|--------|-------------|
| 前端 | http://localhost:5173 |
| 健康检查 | http://localhost:8000/api/v1/health/ |
| Admin | http://localhost:8000/admin/ |
| Redis | `redis-cli ping` |
| Celery | `python manage.py shell` → `from apps.projects.tasks import debug_task` → `debug_task.delay()` |

---

## 七、定时任务说明

- Beat 与 Worker 需同时运行  
- 配置存于数据库（`django_celery_beat`）  
- Cron 示例见 [总览](./AITS部署指南-总览.md)

---

## 选修附录 A · Sonic（App 测试）

> 仅 App 移动自动化需要；API/Web 快速路径**可跳过**。

### 架构

```text
浏览器 → AITS 前端 (Vite) → /sonic-api → Sonic :3000 /server/api
              └→ /api/v1 → Django :8000 → SONIC_BASE_URL → Sonic API
Celery Worker → SONIC_BASE_URL
真机 → Sonic Agent → Sonic Server
```

### Docker 部署 Sonic Server

```bash
cd sonic-server
docker compose -f docker-compose.build.yml build --no-cache
docker compose -f docker-compose.build.yml up -d
```

修改 `sonic-server/.env` 中 `SONIC_SERVER_HOST`、LDAP 等 IP。就绪约 3～5 分钟后访问 `http://<HOST>:<PORT>`。

注册账号（示例）：

```bash
curl -s -X POST "http://<HOST>:<PORT>/server/api/controller/users/register" ^
  -H "Content-Type: application/json" ^
  -d "{\"userName\":\"sonic\",\"password\":\"123456\"}"
```

`code` 为 `2000` 表示成功。同步配置 `backend/.env` 与 `frontend/.env` 中 Sonic 相关变量。

### Sonic Agent

见 [sonic-agent releases](https://github.com/SonicCloudOrg/sonic-agent/releases)，在控制台创建 Agent 并配置 `application-sonic-agent.yml`。

### App 验证

1. Sonic 控制台 Agent、设备在线  
2. AITS App 模块可登录 Sonic、绑定项目  
3. 设备列表可拉取  

---

## 选修附录 B · HuggingFace 镜像（已内置，可手工覆盖）

**默认已写入**：`一键安装` → `backend/.env`；`一键启动` → 各 Celery/Django 窗口环境变量（`scripts/aits-config.bat`）。

若需改用官方源或其它镜像，安装前在 CMD 执行：

```bat
set HF_ENDPOINT=https://hf-mirror.com
```

或编辑 `backend/.env` 中的 `HF_ENDPOINT=` 后重启服务。

---

## 选修附录 C · 性能大盘（一键性能监控，无需 Docker）

Windows 推荐路径：**离线三件套 + 三个性能监控一键脚本**，**无需**在 Grafana 里手工配置数据源或 PromQL。

### 离线包位置

`tools/monitor/`（勿改文件名）：

- `prometheus-3.12.0.windows-amd64.zip`
- `grafana_13.0.2_26816849631_windows_amd64.msi`
- `windows_exporter-0.31.7-amd64.msi`

### 三步验收

| 步骤 | 脚本 | 说明 |
|------|------|------|
| 1 首次 | **perf-monitor\一键安装性能监控.bat**（管理员） | 安装 exporter + Grafana 服务 + 解压 Prometheus；预置 Dashboard |
| 2 开启服务 | **perf-monitor\一键启动性能监控.bat** | 启动 Prometheus/Grafana；自动写入 AITS 默认大盘 URL |
| 3 压测验收 | AITS 内跑压测场景 → **性能大盘** | 压测后 Locust 曲线与主机 CPU/内存应有数据 |

关停服务：双击 **`perf-monitor\一键停止性能监控.bat`**（停 Prometheus；默认保留 exporter 服务）。

### 关键地址

- Prometheus Targets：http://localhost:9090/targets  
- Grafana：http://localhost:3000  
- AITS 性能大盘 iframe（自动 seed）：  
  `http://localhost:3000/d/aits-perf/aits-performance?kiosk=1`

### 与 AITS 主流程关系

- 可先装 AITS 再装监控，或反过来均可。  
- 建议顺序：`一键启动AITS.bat` → `perf-monitor\一键启动性能监控.bat`（seed 需要 Django/conda 环境）。  
- 若大盘空白：确认已压测（Locust `:8089` 才有指标）、`windows-exporter` target 为 UP。
- **Grafana MSI exit 112**：多为 **C: 系统盘或 `%TEMP%` 空间不足**（Grafana 装在 `C:\Program Files`，与工程是否在 G: 无关）。请清理 C: 与临时目录，保留约 **1GB** 可用空间后管理员重跑安装 bat；日志在 `%TEMP%\aits-msi-logs\Grafana-*.log`。
- **`Start-Service` Grafana 失败**：脚本会打印 `grafana.log` 尾部与端口占用提示。常见原因：**3000 端口被占用**、Grafana 安装损坏、**`custom.ini` 无效**（新版脚本已改为无 BOM 写入）、日志含 **`Only one datasource per organization can be marked as default`**（旧包同时加载了 Docker 专用 `prometheus.docker.yml`，请 `git pull` 后重跑安装 bat）。处理：管理员重跑 `perf-monitor\一键安装性能监控.bat`（会自动尝试 MSI repair）；仍失败则「设置 → 应用」卸载 Grafana 后重装，或查看 `C:\Program Files\GrafanaLabs\grafana\data\log\grafana.log`。

### 选修：Docker compose

`backend/aits_monitor/docker-compose.yml` 为本地选修方案，**不是 Windows 一键性能监控主路径**。

---

## 八、常见问题

### 数据库迁移：`table "xxx" already exists`

**现象：** 一键安装或启动时在 `Database migrate` 步骤失败，日志含 `OperationalError: table "ai_llm_configurations" already exists` 等。

**原因：** `backend/db.sqlite3` 里已有旧表，但 `django_migrations` 与当前代码版本不一致（上次半成品安装、旧版残留、手动拷贝库等）。版本升级后字段/表结构可能已变，旧数据往往无法直接沿用。

**脚本行为（新版）：** `一键安装AITS.bat` 与 `scripts/aits-run-django.bat` 在检测到迁移冲突时，会自动将旧库重命名为 `backend/db.sqlite3.bak-yyyyMMdd-HHmmss`，再在新库上执行 `migrate`。正常 migrate 成功时不会动现有库。

**手动处理（脚本未更新或需立即修复）：**

```cmd
ren backend\db.sqlite3 db.sqlite3.bak-manual
一键安装AITS.bat
```

或先复制备份再删除：

```cmd
copy backend\db.sqlite3 backend\db.sqlite3.bak-manual
del backend\db.sqlite3
一键安装AITS.bat
```

**说明：**

- 备份仅覆盖 SQLite 业务库；Chroma 知识库、测试媒体等仍在 `backend/media` 等目录，不在此次自动备份范围内。
- 若必须保留旧库且不自动重置，安装前设置 `set AITS_KEEP_DB=1`（冲突时将按原错误退出，需自行处理）。

### PyTorch 安装很慢 / 包很大

**默认：** 一键安装使用 **CPU 版** `torch`（环境变量 `AITS_TORCH_VARIANT=cpu`，可不设置）。知识库 RAG 功能正常，下载体积小于完整 CUDA 版。

**需 GPU 加速（高级，安装前设置）：**

```cmd
set AITS_TORCH_VARIANT=gpu
一键安装AITS.bat
```

改回 CPU 后若需重装依赖：删除 `%LOCALAPPDATA%\AITS\aits-backend-requirements.sha256` 再运行安装 bat。Docker 路径见 [AITS-Docker部署教程（macOS-Linux云服务器）.md](../../AITS-Docker部署教程（macOS-Linux云服务器）.md) 5.4 节。

---

## 相关文档

- [AITS部署指南-总览.md](./AITS部署指南-总览.md)  
- [AITS部署指南-macOS.md](./AITS部署指南-macOS.md)  
- [AITS部署指南-Linux云服务器.md](./AITS部署指南-Linux云服务器.md)

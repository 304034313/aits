# AITS 部署指南 · macOS

> 适用：**macOS 本机**开发。  
> Windows 本机请使用 [AITS部署指南-Windows.md](./AITS部署指南-Windows.md)（含一键 `.bat`，**不走 Docker**）。  
> 总览见 [AITS部署指南-总览.md](./AITS部署指南-总览.md)。

---

## 零、Docker 推荐路径（首选）

> **完整教程：** 项目根目录 [AITS-Docker部署教程（macOS-Linux云服务器）.md](../../AITS-Docker部署教程（macOS-Linux云服务器）.md)

适合不想在本机装 Conda/Node/Redis、或希望与 Linux 云服务器环境一致的场景。

### 前置

1. 安装 [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)（含 Compose v2）  
2. **安装后必做**：CLI 选 **System**、配置 **Docker Engine 镜像加速**（去掉失效镜像地址）、国内网络环境建议 **关 VPN** — 详见 [AITS-Docker部署教程（macOS-Linux云服务器）.md](../../AITS-Docker部署教程（macOS-Linux云服务器）.md)「macOS · Docker Desktop 安装后注意事项」  
3. 克隆项目：`git clone <仓库地址> && cd aits-system`

### 首次启动

```bash
chmod +x scripts/docker-init.sh scripts/docker-up.sh scripts/docker-down.sh
./scripts/docker-init.sh
```

脚本会：复制 `.env.docker.example` → `.env.docker`、构建镜像、`migrate`、后台启动全部服务。

**访问：** http://localhost:8080  
**管理后台：** http://localhost:8080/admin/

```bash
# 首次创建管理员
docker compose exec backend python manage.py createsuperuser
```

### 日常启停

```bash
./scripts/docker-up.sh    # 启动
./scripts/docker-down.sh  # 停止（保留数据卷）
```

### 配置说明

| 文件 | 作用 |
|------|------|
| `tools/installers/versions.json` | **全平台版本基准**（Windows 离线包 + Docker 镜像） |
| `docker/versions.env` | Docker 镜像 tag（与 `versions.json` 的 `docker` 段同步） |
| `.env.docker` | Django 密钥、`ALLOWED_HOSTS`、RAG 嵌入等（勿提交 Git） |
| `docker-compose.yml` | Redis、backend、celery-worker/beat、nginx（**8080**） |
| Docker 卷 `aits_data` | SQLite、`media`、Chroma 知识库持久化 |

**与 Windows 离线包对齐的版本：** Python **3.12**、Node **24.16.0**、Redis **5.0.14.1**（Windows MSI）；Docker 分别使用 `python:3.12-bookworm`、`node:24.16.0-bookworm`、`redis:5.0.14-alpine`。

容器内 Playwright 默认 **无界面**（`AITS_PLAYWRIGHT_HEADLESS=1`），Web 用例在 Celery Worker 中执行。

### 常见问题

- **端口占用**：修改 `docker-compose.yml` 中 `nginx` 的 `"8080:80"` 左侧端口。  
- **AI / RAG**：在 `.env.docker` 中配置模型相关变量，并在系统「AI 配置」页测试连接。  
- **需要弹窗调试 Playwright**：改用下文「Conda 手工路径」，或本地设置 `AITS_PLAYWRIGHT_HEADLESS=0`。

---

## 一、Conda 手工路径（命令清单）

在终端（Terminal / iTerm）中按顺序执行，项目路径以 `~/dev/aits-system` 为例。

```bash
# 0. 前置（Homebrew，首次）
brew install --cask miniconda
brew install node git redis
brew services start redis

# 1. 克隆
git clone <项目仓库地址>
cd ~/dev/aits-system

# 2. Conda 环境
conda create -n aits-backend python=3.12 -y
conda activate aits-backend

# 3. 后端
cd backend
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
pip install -r requirements.txt
playwright install chromium
cp env.example .env
# 编辑 .env：REDIS_URL=redis://localhost:6379/0 等
python manage.py migrate
python manage.py createsuperuser

# 4. 前端
cd ../frontend
npm config set registry https://registry.npmmirror.com
npm install
cp .env.example .env
```

**日常启动（4 个终端窗口，均需 `conda activate aits-backend`）：**

| 终端 | 目录 | 命令 |
|------|------|------|
| 1 | `backend` | `celery -A aits_backend worker --loglevel=info` |
| 2 | `backend` | `celery -A aits_backend beat --loglevel=info` |
| 3 | `backend` | `python run_asgi.py` |
| 4 | `frontend` | `npm run dev` |

访问：http://localhost:5173 、http://localhost:8000

---

## 二、环境要求

- macOS 12+（Intel / Apple Silicon）  
- Python 3.12、Node 18+、Redis 5+、Git  
- [Homebrew](https://brew.sh/) 推荐  
- 内存 ≥ 4GB，磁盘 ≥ 3GB  

> 仓库内 **`一键安装AITS.bat` / `一键启动AITS.bat` 仅适用于 Windows**，macOS 请按本文命令操作。

---

## 三、前置条件安装

### 1. Miniconda

```bash
brew install --cask miniconda
# 或
# wget .../Miniconda3-latest-MacOSX-x86_64.sh  # Intel
# wget .../Miniconda3-latest-MacOSX-arm64.sh   # Apple Silicon
# bash Miniconda3-*.sh

conda --version
```

初始化 shell（若 `conda` 不可用）：

```bash
conda init zsh   # 或 bash
source ~/.zshrc
```

可选清华 Conda 镜像（见 [总览](./AITS部署指南-总览.md)）。

### 2. Node.js

```bash
brew install node
node --version
npm --version
```

### 3. Redis

```bash
brew install redis
brew services start redis
redis-cli ping   # PONG
```

### 4. Git

```bash
brew install git
```

---

## 四、项目部署

### 1. 克隆

```bash
git clone <项目仓库地址>
cd aits-system
```

### 2. 后端

```bash
conda create -n aits-backend python=3.12 -y
conda activate aits-backend
cd backend
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
pip install -r requirements.txt
playwright install chromium
```

**环境变量** `backend/.env`：

```bash
cp env.example .env
nano .env
```

推荐开发配置：

```bash
DEBUG=True
DJANGO_SECRET_KEY=dev-请改为随机字符串
ALLOWED_HOSTS=localhost,127.0.0.1,::1
REDIS_URL=redis://localhost:6379/0
```

**数据库：**

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 3. 前端

```bash
cd ../frontend
npm install
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `VITE_SONIC_API_BASE` | 默认 `/sonic-api` |
| `VITE_SONIC_PROXY_TARGET` | Sonic 控制台地址（App 选修） |
| `VITE_SONIC_AUTO_*` | Sonic 自动登录（App 选修） |

### 4. Celery

macOS 使用**默认进程池**（无需 Windows 的 `-P solo`）：

```bash
cd backend
conda activate aits-backend
celery -A aits_backend worker --loglevel=info
```

另开终端 Beat：

```bash
celery -A aits_backend beat --loglevel=info
```

---

## 五、服务启动顺序

1. `brew services start redis`（若未运行）  
2. Celery Worker  
3. Celery Beat（定时任务需要）  
4. `python run_asgi.py`  
5. `npm run dev`  

---

## 六、验证部署

| 检查项 | 地址 / 命令 |
|--------|-------------|
| 前端 | http://localhost:5173 |
| 健康检查 | http://localhost:8000/api/v1/health/ |
| Admin | http://localhost:8000/admin/ |
| Redis | `redis-cli ping` |

---

## 选修附录 A · Sonic（App 测试）

与 Windows 相同，使用本仓库 `sonic-server/` + Docker Desktop for Mac：

```bash
cd sonic-server
docker compose -f docker-compose.build.yml build --no-cache
docker compose -f docker-compose.build.yml up -d
```

配置 `backend/.env`、`frontend/.env` 中 Sonic 变量；Agent 与 iOS 调试通常需额外 Xcode / WDA 配置，见 Sonic 官方文档。

---

## 选修附录 B · HuggingFace 镜像

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

写入 `~/.zshrc` 可在 Celery 终端持久生效。

---

## 选修附录 C · 性能大盘（Docker 一键）

与 Windows `perf-monitor\` 三件套对齐，Mac 使用 `perf-monitor/` 下三个 shell 脚本（需先完成 Docker 部署 AITS）。脚本兼容 **Bash 3.2+**（系统默认 bash 即可），请用 `./perf-monitor/...` 执行，勿用 `sh`。

```bash
# 1. AITS 主栈
./scripts/docker-init.sh

# 2. 监控栈（首次）
chmod +x perf-monitor/*.sh scripts/monitor-*.sh
./perf-monitor/一键安装性能监控.sh

# 3. 开启服务
./scripts/docker-up.sh
./perf-monitor/一键启动性能监控.sh
```

验收：`http://localhost:9090/targets`（`locust-performance`、`node-exporter` 为 UP）；压测运行后 Locust 面板才有曲线。详见 [AITS-Docker部署教程（macOS-Linux云服务器）.md](../../AITS-Docker部署教程（macOS-Linux云服务器）.md) 附录 A。

---

## 相关文档

- [AITS部署指南-总览.md](./AITS部署指南-总览.md)  
- [AITS部署指南-Windows.md](./AITS部署指南-Windows.md)  
- [AITS部署指南-Linux云服务器.md](./AITS部署指南-Linux云服务器.md)

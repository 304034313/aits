# AITS 部署指南 · Linux 云服务器

> 适用：**Ubuntu/Debian、CentOS Stream/Rocky/AlmaLinux 等 Linux 云主机**（远程开发机、个人 VPS、内网演示机）。  
> 本文 **Part A** 为远程开发调试，**Part B** 为生产/长期运行部署。  
> 总览见 [AITS部署指南-总览.md](./AITS部署指南-总览.md)。

---

# Part A · 云主机开发调试

适合：在云服务器上跑通与本地一致的开发栈，通过浏览器访问 `http://<公网IP>:5173` / `:8000`。

## A.1 环境要求

- Ubuntu 20.04+ / Debian 11+，或 CentOS Stream 8/9、Rocky/AlmaLinux 9（x86_64；**不推荐 CentOS 7**）  
- 安全组 / 防火墙开放：**5173、8000**（开发期；生产见 Part B）  
- 建议 2 核 4GB+ 内存  

## A.2 前置安装

```bash
sudo apt update
sudo apt install -y git curl wget build-essential

# Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Redis
sudo apt install -y redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
redis-cli ping   # PONG

# Miniconda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh
bash ~/miniconda.sh -b -p $HOME/miniconda3
source ~/miniconda3/etc/profile.d/conda.sh
conda --version
```

## A.3 克隆与后端

```bash
git clone <项目仓库地址>
cd aits-system

conda create -n aits-backend python=3.12 -y
conda activate aits-backend

cd backend
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
pip install -r requirements.txt
playwright install chromium
playwright install-deps   # Linux 无头浏览器系统依赖，必做
```

**`backend/.env`（远程开发示例）：**

```bash
cp env.example .env
nano .env
```

```bash
DEBUG=True
DJANGO_SECRET_KEY=dev-请改为随机字符串
ALLOWED_HOSTS=localhost,127.0.0.1,<你的公网IP>,<你的内网IP>
REDIS_URL=redis://127.0.0.1:6379/0
```

```bash
python manage.py migrate
python manage.py createsuperuser
```

## A.4 前端（对外监听）

```bash
cd ../frontend
npm config set registry https://registry.npmmirror.com
npm install
cp .env.example .env
```

使用 **tmux** 或 **screen** 保持会话，启动：

```bash
# 终端 1 - Worker
cd ~/aits-system/backend && conda activate aits-backend
celery -A aits_backend worker --loglevel=info

# 终端 2 - Beat
celery -A aits_backend beat --loglevel=info

# 终端 3 - Django
python run_asgi.py
# 默认 0.0.0.0:8000 以 run_asgi 配置为准；若仅监听 127.0.0.1 需改启动配置或反向代理

# 终端 4 - Vite（绑定所有网卡）
cd ~/aits-system/frontend
npm run dev -- --host 0.0.0.0
```

浏览器访问：`http://<公网IP>:5173`、`http://<公网IP>:8000`。

## A.5 防火墙与安全组

```bash
# UFW 示例
sudo ufw allow 22/tcp
sudo ufw allow 5173/tcp
sudo ufw allow 8000/tcp
sudo ufw enable
```

云厂商控制台安全组需同步放行上述端口。

## A.6 验证

同 [总览 · 通用验证](./AITS部署指南-总览.md)，将 `localhost` 换为服务器 IP。

---

# Part B · 生产 / 演示部署

适合：长期对外提供 AITS、关闭 DEBUG、前端静态资源 + Nginx 反代。

## B.0 Docker Compose 推荐路径（首选）

> **完整教程：** 项目根目录 [AITS-Docker部署教程（macOS-Linux云服务器）.md](../../AITS-Docker部署教程（macOS-Linux云服务器）.md)

与 macOS 相同，使用项目根目录 `docker-compose.yml` 一键拉起 Redis + Django ASGI + Celery + Nginx。

### 前置

Ubuntu/Debian、CentOS Stream/Rocky/AlmaLinux、**CentOS 7 遗留环境** 装 Docker 步骤见 [AITS-Docker部署教程（macOS-Linux云服务器）.md](../../AITS-Docker部署教程（macOS-Linux云服务器）.md)「二、前置要求 → Linux 云服务器」。

### 部署

```bash
git clone <项目仓库地址>
cd aits-system
chmod +x scripts/docker-init.sh scripts/docker-up.sh scripts/docker-down.sh

cp .env.docker.example .env.docker
nano .env.docker   # 修改 DJANGO_SECRET_KEY、ALLOWED_HOSTS（含公网 IP/域名）

./scripts/docker-init.sh
docker compose exec backend python manage.py createsuperuser
```

### 防火墙与安全组

对外只需放行 **8080**（Nginx 统一入口，已反代 `/api/`、`/ws/`、`/media/`）：

```bash
sudo ufw allow 22/tcp
sudo ufw allow 8080/tcp
sudo ufw enable
```

访问：`http://<公网IP>:8080`

### 版本对齐

Docker 镜像版本由 `docker/versions.env` 固定，与 Windows 离线包 `tools/installers/versions.json` 一致（Python 3.12、Node 24.16.0、Redis 5.0.14.1）。升级 Windows 离线安装包时请同步修改这两处。

### 数据与运维

| 项 | 说明 |
|----|------|
| 持久化卷 | `aits_data`（SQLite、`media`、Chroma） |
| 日志 | `docker compose logs -f backend celery-worker` |
| 更新 | `git pull && docker compose build && docker compose up -d` |
| Playwright | 容器内 headless，无需 `playwright install-deps` |

---

## B.1 手工 systemd 路径（原则）

> 若已采用 **B.0 Docker**，可跳过本节。以下为不使用 Docker、自行安装 Conda/Redis/Nginx 时的参考。

| 项 | 开发 (Part A) | 生产 (Part B 手工) |
|----|---------------|-------------------|
| `DEBUG` | `True` | **`False`** |
| 前端 | Vite dev server | **`npm run build` + Nginx 静态** |
| 后端 | `run_asgi.py` | **systemd 托管** ASGI |
| 数据库 | SQLite | 建议 **PostgreSQL**（见 `env.example`） |
| 端口暴露 | 5173/8000 直连 | **仅 80/443**（Nginx） |

## B.2 构建前端（手工路径）

```bash
cd /opt/aits-system/frontend   # 路径按实际
npm ci
npm run build
# 产物在 frontend/dist
```

## B.3 后端生产环境变量

```bash
# backend/.env 摘录
DEBUG=False
DJANGO_SECRET_KEY=<强随机密钥>
ALLOWED_HOSTS=your.domain.com,<服务器IP>
REDIS_URL=redis://127.0.0.1:6379/0

# PostgreSQL（推荐）
DB_NAME=aits_db
DB_USER=aits_user
DB_PASSWORD=<强密码>
DB_HOST=127.0.0.1
DB_PORT=5432
```

```bash
conda activate aits-backend
cd backend
python manage.py migrate --noinput
python manage.py collectstatic --noinput   # 若项目启用静态收集
```

## B.4 systemd 示例

以下路径请替换为实际部署目录（如 `/opt/aits-system`）及运行用户（如 `aits`）。

**`/etc/systemd/system/aits-django.service`**

```ini
[Unit]
Description=AITS Django ASGI
After=network.target redis-server.service

[Service]
Type=simple
User=aits
WorkingDirectory=/opt/aits-system/backend
Environment=PATH=/home/aits/miniconda3/envs/aits-backend/bin:/usr/bin
ExecStart=/home/aits/miniconda3/envs/aits-backend/bin/python run_asgi.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/aits-celery-worker.service`**

```ini
[Unit]
Description=AITS Celery Worker
After=network.target redis-server.service

[Service]
Type=simple
User=aits
WorkingDirectory=/opt/aits-system/backend
Environment=PATH=/home/aits/miniconda3/envs/aits-backend/bin:/usr/bin
ExecStart=/home/aits/miniconda3/envs/aits-backend/bin/celery -A aits_backend worker --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/aits-celery-beat.service`**

```ini
[Unit]
Description=AITS Celery Beat
After=network.target redis-server.service

[Service]
Type=simple
User=aits
WorkingDirectory=/opt/aits-system/backend
Environment=PATH=/home/aits/miniconda3/envs/aits-backend/bin:/usr/bin
ExecStart=/home/aits/miniconda3/envs/aits-backend/bin/celery -A aits_backend beat --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aits-django aits-celery-worker aits-celery-beat
sudo systemctl status aits-django
```

## B.5 Nginx 反向代理（示例）

```nginx
server {
    listen 80;
    server_name your.domain.com;

    root /opt/aits-system/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

按项目实际 API 前缀（如 `/api/v1/`）调整 `location`。HTTPS 建议使用 certbot 配置证书。

## B.6 运维建议

- 日志：`journalctl -u aits-django -f`  
- Redis：`systemctl enable redis-server`  
- 磁盘：监控 `backend/media`、`chroma_db`、日志目录  
- 密钥：`.env` 勿提交 Git；定期轮换 `DJANGO_SECRET_KEY`  
- 发压机监控：Linux 可用 **node_exporter** + Prometheus（非 Windows 的 windows_exporter）  

---

## 选修附录 · Sonic（云服务器 Docker）

```bash
cd /opt/aits-system/sonic-server
# 修改 .env 中 SONIC_SERVER_HOST 等为云主机 IP
docker compose -f docker-compose.build.yml up -d
```

确保 AITS 的 `SONIC_BASE_URL`、安全组端口与 Sonic 控制台可达。详见 [Windows 指南 · Sonic 附录](./AITS部署指南-Windows.md#选修附录-a--sonicapp-测试)（步骤通用）。

---

## 选修附录 · 性能大盘（Docker 一键）

云主机若采用 **Docker 部署 AITS**（见 [AITS-Docker部署教程（macOS-Linux云服务器）.md](../../AITS-Docker部署教程（macOS-Linux云服务器）.md)），性能监控与 Mac 相同：

```bash
./scripts/docker-init.sh
chmod +x perf-monitor/*.sh scripts/monitor-*.sh
./perf-monitor/一键安装性能监控.sh
# 开启服务
./perf-monitor/一键启动性能监控.sh
```

云主机公网访问可设 `export AITS_MONITOR_HOST=<公网IP>` 后执行启动脚本；安全组可选开放 3000/9090。主机资源由 **node_exporter** 采集（替代 Windows 的 windows_exporter）。

---

## 相关文档

- [AITS部署指南-总览.md](./AITS部署指南-总览.md)  
- [AITS部署指南-Windows.md](./AITS部署指南-Windows.md)  
- [AITS部署指南-macOS.md](./AITS部署指南-macOS.md)

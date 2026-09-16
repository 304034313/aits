# AITS Docker 部署教程（macOS / Linux 云服务器）

> **适用环境：** macOS 本机、Linux 云服务器（Ubuntu / Debian、CentOS Stream / Rocky / AlmaLinux 等）  
> **不适用：** Windows 本机请使用根目录 `一键安装AITS.bat`（不走 Docker 主路径）  
> **统一入口：** [http://localhost:8080（Nginx](http://localhost:8080（Nginx) 反代前端 + API + WebSocket）

**网络说明（重要）：** 脚本面向**国内网络环境**——构建时 **优先国内 pip/npm 镜像**。建议**关闭 VPN** 后再执行 `docker-init.sh`。若使用海外节点 VPN 自测，国内镜像可能 403，脚本会**自动改走官方 PyPI / npmjs.org**，能成功但较慢，属正常现象。

---

## 一、你会得到什么

一键拉起 AITS 核心栈，无需在本机安装 Conda、Node、Redis：


| 容器                   | 作用                           |
| -------------------- | ---------------------------- |
| `aits-redis`         | 缓存、Celery Broker             |
| `aits-backend`       | Django ASGI（API + WebSocket） |
| `aits-celery-worker` | 异步任务（含 Playwright Web 测试）    |
| `aits-celery-beat`   | 定时任务调度                       |
| `aits-nginx`         | 前端静态资源 + 反向代理                |


数据持久化在 Docker 卷 `aits_data`（SQLite、媒体文件、Chroma 知识库）和 `aits_redis_data`。

---

## 二、前置要求

### macOS

1. 安装 [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)（建议从 **docker.com 官网** 下载）
2. 完成下方 [macOS · Docker Desktop 安装后注意事项](#macos--docker-desktop-安装后注意事项)（**首次部署前建议做完**）
3. 打开 Docker Desktop，确认终端可执行：

```bash
docker compose version
docker info | grep -A3 'Registry Mirrors'   # 可选：检查镜像加速是否生效
```

#### macOS · Docker Desktop 安装后注意事项

以下设置均在 **Docker Desktop → Settings（齿轮）** 中完成；改完 Docker Engine 后务必点 **Apply & Restart**。

**1）CLI 工具安装范围：User → System（推荐）**

路径：**Settings → Advanced（高级）→ 选择如何配置 Docker 的 CLI 工具的安装**


| 选项             | 说明                                                                                   |
| -------------- | ------------------------------------------------------------------------------------ |
| **User**       | `docker` 装在 `$HOME/.docker/bin`，需自行把该目录加入 `PATH`，终端可能找不到 `docker` / `docker compose` |
| **System（推荐）** | CLI 链到 `/usr/local/bin`，终端直接可用；与「启用默认 Docker 套接字」等系统级选项配合更稳                          |


建议选 **System**。若切换后终端仍无 `docker`，重开终端或执行：

```bash
export PATH="$PATH:$HOME/.docker/bin"
```

**2）Docker Engine 镜像加速（国内拉 `python:3.12-bookworm` 等基础镜像）**

路径：**Settings → Docker Engine**，在 JSON 中配置 `registry-mirrors`（**勿保留已失效的镜像地址**）。

推荐示例（只保留 **1 个当前可用** 的即可，不要堆太多）：

```json
{
  "ipv6": false,
  "registry-mirrors": [
    "https://docker.m.daocloud.io"
  ]
}
```

- `registry-mirrors` 中若留有已失效的地址，拉镜像时会报 `lookup ... no such host`；请只保留当前可用的镜像加速。
- 配置后 **Apply & Restart**，验证：

```bash
docker pull python:3.12-bookworm
```

若仍超时，可不改 Engine、改用手动拉取并打标签（见 [十、排错](#十排错)）。

**3）代理与 VPN**

路径：**Settings → Resources → Proxies**

- Docker 会读取 macOS **系统代理**；若代理/VPN 导致连不上 `registry-1.docker.io`，可改为 **Manual proxy configuration** 并留空，或 **关闭 VPN** 后重试。
- **国内网络**：构建前建议 **关 VPN**，依赖 Engine 镜像加速 + 脚本内 pip/npm 国内源。

**4）资源与磁盘**

路径：**Settings → Resources → Advanced**

- 首次 `docker compose build` 建议 **Mac 可用磁盘 ≥ 20GB**、Docker 内存 ≥ 4GB（Playwright + Python 依赖较大）。**仅剩 2～5GB 时** Docker 易出现 `read-only file system`、`celery-worker Exited`、`docker rm` 失败。
- 构建日志里出现 `Uninstalling fsspec` / `filelock` 等，是容器内 **pip 对齐依赖版本**，属正常现象。

**5）与 AITS 脚本的关系**


| 层级                                               | 谁负责                                                                                     |
| ------------------------------------------------ | --------------------------------------------------------------------------------------- |
| 拉 `python` / `node` / `redis` / `nginx` **基础镜像** | Docker Desktop + 你配置的 **Engine 镜像加速**（本节）                                               |
| 容器内 **pip / npm** 依赖                             | `docker-pip-install.sh` / `docker-npm-install.sh`（国内 PyPI/npm 镜像，与 Hub 无关）              |
| **CPU 版 torch**                                  | `.env.docker` 中 `AITS_TORCH_VARIANT=cpu`（默认），见 [5.4 节](#54-pytorch-变体aitstorch_variant) |


**6）Shell 脚本与 Bash 版本**

`./scripts/docker-init.sh`、`perf-monitor/*.sh` 等使用 **bash** 编写，目标兼容 **Bash 3.2+**（macOS 系统默认即为 3.2.x）。

- 请用 `**./scripts/...` 或 `bash ./scripts/...`** 运行，**不要用 `sh`**（`sh` 可能是 dash，不支持数组等语法）。
- 脚本启动时会检测 Bash 版本；若报 `mapfile: command not found` 等，先 `**git pull**` 获取最新脚本（已避免 Bash 4+ 专有命令）。
- 可选查看版本：`bash --version`（3.2 即可；也可用 `brew install bash` 安装 5.x，非必须）。

**7）首次部署前自检**

```bash
bash --version                  # 建议 >= 3.2
docker compose version          # 有版本号
docker pull python:3.12-bookworm   # 能拉通或本地已有
cp .env.docker.example .env.docker # 若尚无 .env.docker
chmod +x scripts/docker-*.sh perf-monitor/*.sh scripts/monitor-*.sh
./scripts/docker-init.sh
```

### Linux 云服务器

**硬件建议：** 云主机推荐 **4 核 8GB、系统盘 60GB+ SSD**；最低试跑 2 核 4GB、磁盘 ≥ 40GB（首次 `docker compose build` 会下载基础镜像并安装 Playwright Chromium，需留足空间）。

**版本对齐：** 镜像版本与 Windows 离线包一致，见 `tools/installers/versions.json` 与 `docker/versions.env`（Python 3.12 / Node 24.16.0 / Redis 5.0.14.1）。

**国内云主机拉 Hub 慢：** 可在 `/etc/docker/daemon.json` 配置 `registry-mirrors`（与 macOS Docker Engine 同理，勿保留已失效地址），然后 `sudo systemctl restart docker`。验证：`docker pull python:3.12-bookworm`。

#### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # 重新登录后生效
docker compose version
```

#### CentOS Stream / Rocky Linux / AlmaLinux（RHEL 系）

> **不推荐 CentOS 7**（已 EOL）。建议 **Stream 8/9、Rocky 9、AlmaLinux 9** 等，架构 **x86_64**。  
> 以下命令与 `./scripts/docker-init.sh` 等脚本兼容；教程中 `apt` 手工安装段落在 RHEL 系需改用 `dnf`，**建议直接走 Docker 主路径**。

```bash
# 安装 Docker CE + Compose 插件（官方源）
sudo dnf install -y dnf-plugins-core git
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # 重新登录后生效
docker compose version
```

**镜像加速（可选，`/etc/docker/daemon.json`）：**

```json
{
  "registry-mirrors": ["https://docker.m.daocloud.io"]
}
```

```bash
sudo systemctl restart docker
docker pull python:3.12-bookworm
```

**SELinux：** 默认 `enforcing` 下 Docker 部署一般可直接用；若监控数据目录 `tools/monitor/runtime/docker/` 遇权限问题，再按需调整上下文或查阅排错章节。

#### CentOS 7（不推荐但可部署）

> **CentOS 7 已 EOL（无官方安全更新）**，仅适用于无法升级的老机器。**有条件请迁移到 Rocky 9 / AlmaLinux 9。**  
> AITS 应用跑在容器内（Debian bookworm），**不依赖**宿主机 Python 3.12；只要 Docker CE + Compose v2 可用即可。  
> 脚本使用 `docker compose`（有空格），**不要**只装旧的独立命令 `docker-compose`。

**前置检查：**

```bash
uname -r          # 建议 3.10+（CentOS 7 默认内核一般满足）
uname -m          # 须 x86_64
df -h /           # 可用建议 ≥ 40GB（构建镜像很占空间）
docker compose version 2>/dev/null || echo "尚未安装 Docker Compose 插件"
```

**1）卸载旧版 Docker（若曾装过 `docker` / `docker-engine`）：**

```bash
sudo yum remove -y docker docker-client docker-client-latest docker-common \
  docker-latest docker-latest-logrotate docker-logrotate docker-engine 2>/dev/null || true
```

**2）安装 Docker CE + Compose 插件（`yum`，非 `dnf`）：**

```bash
sudo yum install -y yum-utils device-mapper-persistent-data lvm2 git
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# 国内阿里云 ECS 若官方源慢，可改用（装完跳过下一行 sed）
# sudo wget -O /etc/yum.repos.d/docker-ce.repo http://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo

sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# SELinux 环境建议（CentOS 7 常见）
sudo yum install -y container-selinux 2>/dev/null || true

sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # 重新登录后生效
docker compose version          # 必须有版本号，例如 v2.x
```

若 `yum install docker-compose-plugin` 找不到包，可**手动安装 Compose v2 插件**（与脚本兼容）：

```bash
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version
```

**3）镜像加速（可选）：** 与上文相同，编辑 `/etc/docker/daemon.json` 后 `sudo systemctl restart docker`。

**4）部署 AITS（与 Ubuntu 完全相同）：**

```bash
git clone <你的仓库地址> #从git获取项目代码，若未托管git，可以将本地代码上传到云服务器上
cd aits-system #进入到项目根路径下，以实际项目名为准，如果是lemon-aits则使用：cd lemon-aits
chmod +x scripts/docker-init.sh scripts/docker-up.sh scripts/docker-down.sh
cp .env.docker.example .env.docker
vi .env.docker    # 设置DJANGO_SECRET_KEY、ALLOWED_HOSTS（把你的云服务器的公网IP加进去），设置完退出保存
./scripts/docker-init.sh
docker compose exec backend python manage.py createsuperuser
```

**5）防火墙：** 见 [六、Linux 云服务器对外暴露 → firewalld](#61-防火墙)。

**CentOS 7 常见问题：**


| 现象                                  | 处理                                                                                                      |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `docker compose: command not found` | 未装 `docker-compose-plugin` 或插件路径不对；见上文手动安装                                                              |
| `yum install docker-ce` 无可用包        | 检查 `/etc/yum.repos.d/docker-ce.repo` 中 `$releasever` 是否为 `7`；`sudo yum clean all && sudo yum makecache` |
| 构建极慢或 pull 失败                       | 配置 `registry-mirrors`；部署机器建议关 VPN                                                                       |
| 容器启动即退出                             | `docker logs aits-celery-worker`；常见仍为**磁盘满**，`df -h` 确认                                                 |
| SELinux 拒绝挂载                        | 临时验证：`sudo setenforce 0` 后重试；确认后可用 `chcon` 或按需调整策略（生产环境请规范配置）                                           |


---

## 三、首次部署（推荐脚本）

```bash
# 1. 获取代码
git clone <你的仓库地址>
cd aits-system

# 2. 赋予脚本执行权限
chmod +x scripts/docker-init.sh scripts/docker-up.sh scripts/docker-down.sh

# 3. 首次初始化（构建镜像 → 数据库迁移 → 后台启动）
./scripts/docker-init.sh
```

脚本会自动：

1. 若不存在则复制 `.env.docker.example` → `.env.docker`
2. 读取 `docker/versions.env` 固定镜像版本并 `docker compose build`
3. 执行 `python manage.py migrate`
4. `docker compose up -d` 启动全部服务

### 创建管理员（首次必做）

```bash
docker compose --env-file docker/versions.env --env-file .env.docker \
  exec backend python manage.py createsuperuser
```

按提示输入用户名、邮箱、密码。

### 访问地址


| 用途   | 地址                                                           |
| ---- | ------------------------------------------------------------ |
| 前端   | [http://localhost:8080](http://localhost:8080)               |
| 管理后台 | [http://localhost:8080/admin/](http://localhost:8080/admin/) |
| API  | [http://localhost:8080/api/](http://localhost:8080/api/)     |


---

## 四、日常启停

```bash
# 启动（已初始化过）
./scripts/docker-up.sh

# 停止（保留数据卷，数据不丢）
./scripts/docker-down.sh
```

等价手动命令：

```bash
docker compose --env-file docker/versions.env --env-file .env.docker up -d
docker compose --env-file docker/versions.env --env-file .env.docker down
```

---

## 五、配置说明

### 5.1 `.env.docker`（应用配置，勿提交 Git）

首次运行后编辑项目根目录 `.env.docker`：

```bash
cp .env.docker.example .env.docker   # docker-init.sh 已自动做过可跳过
nano .env.docker
```

**必改项：**

```bash
DJANGO_SECRET_KEY=<改为足够长的随机字符串>
```

**Linux 云服务器对外访问时，还要改：**

```bash
ALLOWED_HOSTS=localhost,127.0.0.1,backend,nginx,<你的公网IP>,<你的域名>
```

修改后重启：

```bash
./scripts/docker-down.sh && ./scripts/docker-up.sh
```

### 5.2 `docker/versions.env`（镜像版本）

与 Windows 离线安装包版本对齐，一般无需修改。升级 Windows 离线包时请同步更新此文件与 `tools/installers/versions.json`。

### 5.3 Playwright

容器内 Web 测试默认 **无界面**（`AITS_PLAYWRIGHT_HEADLESS=1`），由 Celery Worker 在后台执行，无需本机弹浏览器。

### 5.4 PyTorch 变体（`AITS_TORCH_VARIANT`）

知识库 RAG 依赖 `torch`。Docker 部署默认 **无 NVIDIA GPU**，`.env.docker` 中默认：

```bash
AITS_TORCH_VARIANT=cpu
```


| 值              | 行为                                                                                                            |
| -------------- | ------------------------------------------------------------------------------------------------------------- |
| `cpu`（默认）      | 构建时从 `download.pytorch.org/whl/cpu` 安装 CPU 版 torch，**跳过** `nvidia_cublas` / `nvidia_cudnn` 等约 2GB+ 依赖；知识库功能正常 |
| `gpu` 或 `cuda` | 从 PyPI 镜像安装完整 CUDA 版 torch（构建慢、镜像大）；需宿主机 NVIDIA 并自行配置 GPU                                                     |


**切换为 GPU（高级，须在 `docker compose build` 之前写入 `.env.docker`）：**

```bash
# .env.docker
AITS_TORCH_VARIANT=gpu
```

然后无缓存重建：

```bash
docker compose --env-file docker/versions.env --env-file .env.docker build --no-cache backend celery-worker celery-beat
```

已构建过的镜像不会自动换变体；修改后必须 `--no-cache` 重建 backend 相关服务。

---

## 六、Linux 云服务器对外暴露

对外只需放行 **8080**（Nginx 已反代 `/api/`、`/ws/`、`/media/` 等）。

### 6.1 防火墙

**Ubuntu / Debian（UFW）：**

```bash
sudo ufw allow 22/tcp
sudo ufw allow 8080/tcp
sudo ufw enable
```

**CentOS Stream / Rocky / AlmaLinux（firewalld）：**

```bash
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

选修性能监控若需公网访问 Grafana/Prometheus，可额外放行 `3000/tcp`、`9090/tcp`（通常只开 8080，在 AITS 内嵌 iframe 即可）。

### 6.2 云厂商安全组

在控制台安全组中放行入站 **TCP 8080**（来源按需设为 `0.0.0.0/0` 或指定 IP）。

### 6.3 访问

```
http://<公网IP>:8080
```

确保 `.env.docker` 的 `ALLOWED_HOSTS` 已包含该公网 IP 或域名。

---

## 七、AI 与知识库（RAG）

`.env.docker.example` 已预置国内 HuggingFace 镜像：

```bash
HF_ENDPOINT=https://hf-mirror.com
EMBEDDING_LOAD_MODE=remote
EMBEDDING_MODEL_REMOTE_NAME=BAAI/bge-large-zh-v1.5
```

**首次使用知识库前：**

1. 登录 AITS → **AI 配置**
2. 填写 LLM API Key 等信息
3. 点击 **测试连接**

视觉断言等功能若使用多模态模型，建议在 AI 配置中选择 `qwen-vl-max` 等 vision 模型。

---

## 八、代码更新后如何重建

```bash
git pull

# 重新构建并启动（数据库迁移如有变更会自动在下次 init 时处理）
docker compose --env-file docker/versions.env --env-file .env.docker build
docker compose --env-file docker/versions.env --env-file .env.docker up -d

# 若有 Django 迁移
docker compose --env-file docker/versions.env --env-file .env.docker \
  exec backend python manage.py migrate --noinput
```

---

## 九、常用运维命令

```bash
# 查看容器状态
docker compose --env-file docker/versions.env --env-file .env.docker ps

# 查看日志
docker compose --env-file docker/versions.env --env-file .env.docker logs -f backend
docker compose --env-file docker/versions.env --env-file .env.docker logs -f celery-worker

# 进入 backend 容器 shell
docker compose --env-file docker/versions.env --env-file .env.docker exec backend bash

# 手动执行 Django 命令
docker compose --env-file docker/versions.env --env-file .env.docker \
  exec backend python manage.py <子命令>
```

---

## 十、排错


| 现象                                                                | 处理                                                                                                                                                                                                                                                                                                                         |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docker pull` / `load metadata` 超时、`registry-1.docker.io` 连不上     | 见 [macOS · Docker Desktop 安装后注意事项](#macos--docker-desktop-安装后注意事项)：配 **Engine 镜像加速**、关 VPN；或 `docker.m.daocloud.io/library/...` 直拉后 `docker tag`                                                                                                                                                                           |
| 终端找不到 `docker` 命令                                                 | Docker Desktop → **Advanced** → CLI 安装选 **System**；或 `export PATH="$PATH:$HOME/.docker/bin"`                                                                                                                                                                                                                               |
| `pip install` / `HTTP error 403`（清华等）                             | **国内网络**：关 VPN 后重试。脚本顺序：阿里 → 中科大 → 清华 → **官方 PyPI**；海外 VPN 自测时前几项可能 403，会自动落到 `pypi.org`                                                                                                                                                                                                                                   |
| `lookup ... no such host`（拉基础镜像）                                  | 在 **Docker Engine** 检查 `registry-mirrors`，删除已失效条目后 **Apply & Restart**；或改用手动拉取并 `docker tag`（见上文）                                                                                                                                                                                                                          |
| `docker compose build` 很慢（pip 阶段）                                 | 国内关 VPN；日志见 `[pip] trying mirror`；确认 `AITS_TORCH_VARIANT=cpu` 避免 CUDA 大包                                                                                                                                                                                                                                                   |
| `playwright install-deps` / `install chromium` 极慢（`deb.debian.org`） | 默认已启用国内加速：`.env.docker` 中 `AITS_APT_MIRROR`（清华 Debian）、`PLAYWRIGHT_DOWNLOAD_HOST`（npmmirror）。日志应见 `[apt] applying mirror`、`[playwright] PLAYWRIGHT_DOWNLOAD_HOST=...`。海外构建设 `AITS_USE_CHINA_MIRROR=0`；改配置后需 `docker compose build --no-cache backend celery-worker celery-beat` 重建 Playwright 层 |
| build 中 `Uninstalling fsspec` / `filelock`                        | 正常：CPU torch 先装后，pip 在对齐依赖版本，无需中断                                                                                                                                                                                                                                                                                          |
| `base name (${NGINX_IMAGE}) should not be blank`                  | backend 已构建成功、仅 nginx 失败时常见：`NGINX_IMAGE` 构建参数为空。`git pull` 后重试；或 `grep NGINX_IMAGE docker/versions.env` 应有 `nginx:1.27-alpine`；**勿重跑整包 build**，只重建 nginx：`docker compose --env-file docker/versions.env --env-file .env.docker build nginx && docker compose --env-file docker/versions.env --env-file .env.docker up -d` |
| `mapfile: command not found` / 监控安装脚本报错                           | macOS 默认 Bash 3.2 无 `mapfile`（Bash 4+）。`git pull` 后重跑 `./perf-monitor/一键安装性能监控.sh`；勿用 `sh` 运行脚本                                                                                                                                                                                                                            |
| 监控启动后 `Failed to load .env.docker` / `seed_monitor_config failed` | 监控容器已起，但 AITS 内性能大盘 iframe 需 seed 写入 URL。`cp .env.docker.example .env.docker` 后重跑 `./perf-monitor/一键启动性能监控.sh`；或 `git pull` 后脚本会自动 `docker exec` 补 seed                                                                                                                                                                    |
| `read-only file system` / `overlay2` failed to remove             | **Docker Desktop 虚拟机存储只读**，`docker rm`/`pull`/建卷都会失败，**脚本无法修复**。先 `df -h /` 看 Mac 磁盘是否满；再 Docker Desktop → **Troubleshoot → Clean / Purge data**（会清空容器镜像，需重新 `./scripts/docker-init.sh`）。自检：`./scripts/docker-doctor.sh` 须显示 OK                                                                                            |
| 卷名含 `lemon-aits215311`                                            | 勿在废纸篓运行；最新代码监控数据在 `tools/monitor/runtime/docker/`                                                                                                                                                                                                                                                                          |
| 安装/启动报「未找到 AITS Docker 网络」                                        | 主栈未运行。同一目录先 `./scripts/docker-up.sh`（或首次 `./scripts/docker-init.sh`）                                                                                                                                                                                                                                                       |
| 一键停止报错                                                            | `git pull` 后重试；脚本会 fallback 直接 `docker rm` 监控容器                                                                                                                                                                                                                                                                            |
| `container name "/aits-node-exporter" is already in use`          | 旧目录 `lemon-aits` 残留的监控容器未删。`docker rm -f aits-prometheus aits-grafana aits-node-exporter` 后重跑一键启动；最新脚本 up 前会自动清理                                                                                                                                                                                                           |
| 一键停止报 `overlay2` / `c?: unbound variable`                         | 前者: Docker 只读须 Purge；后者: 旧脚本在 Bash 5 下 `$c，` 解析错误，`git pull` 或换新 ZIP。容器删不掉时停止脚本会提示 Purge 步骤                                                                                                                                                                                                                                |
| 8080 无法访问                                                         | `docker compose ps` 确认 `aits-nginx` 在运行；检查防火墙 / 安全组                                                                                                                                                                                                                                                                        |
| 502 / 前端能开但 API 报错                                                | `docker compose logs backend`；确认 `aits-backend` healthcheck 通过                                                                                                                                                                                                                                                             |
| `DisallowedHost`                                                  | 在 `.env.docker` 的 `ALLOWED_HOSTS` 加入访问用的 IP 或域名后重启                                                                                                                                                                                                                                                                         |
| Web 测试不执行                                                         | `docker compose logs celery-worker`；确认 worker 容器正常                                                                                                                                                                                                                                                                         |
| 知识库嵌入失败                                                           | 确认 `HF_ENDPOINT`；首次下载模型需时间与磁盘；在 AI 配置测试连接                                                                                                                                                                                                                                                                                  |
| 想彻底重来                                                             | `./scripts/docker-down.sh` 后执行 `docker volume rm aits-system_aits_data aits-system_aits_redis_data`（卷名以 `docker volume ls` 为准），再 `./scripts/docker-init.sh`                                                                                                                                                                |


**Hub 超时备用：镜像站直拉 + 打标签**

```bash
# 示例：python 基础镜像（版本以 docker/versions.env 为准）
docker pull docker.m.daocloud.io/library/python:3.12-bookworm
docker tag docker.m.daocloud.io/library/python:3.12-bookworm python:3.12-bookworm
```

再执行 `./scripts/docker-init.sh` 或 `docker compose build`。

**查看单容器健康：**

```bash
docker inspect --format='{{.State.Health.Status}}' aits-backend
```

---

## 附录 A · 性能监控（选修，Docker）

与 Windows `perf-monitor\` 三个 bat 对齐，Mac / Linux 使用 **独立 Docker Compose 监控栈**（Prometheus + Grafana + node_exporter），自动加入 AITS 主栈 Docker 网络，采集 `aits-celery-worker:8089` 的 Locust 指标。

**前提：** 已完成 [三、首次部署](#三首次部署推荐脚本)（`./scripts/docker-init.sh`）。

```bash
# 首次安装监控
chmod +x perf-monitor/*.sh scripts/monitor-*.sh
./perf-monitor/一键安装性能监控.sh

# 开启服务（AITS 已启动后）
./perf-monitor/一键启动性能监控.sh

# 关停服务
./perf-monitor/一键停止性能监控.sh
```


| 检查项                | 地址                                                                                                                       |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| Prometheus Targets | [http://localhost:9090/targets](http://localhost:9090/targets)                                                           |
| Grafana            | [http://localhost:3000](http://localhost:3000)                                                                           |
| AITS 性能大盘 iframe   | [http://localhost:3000/d/aits-perf/aits-performance?kiosk=1](http://localhost:3000/d/aits-perf/aits-performance?kiosk=1) |


云服务器若需用公网 IP 访问 Grafana，安装前可设：

```bash
export AITS_MONITOR_HOST=<你的公网IP>
./perf-monitor/一键启动性能监控.sh
```

安全组可选开放 **3000、9090**（管理端直连验收；日常使用 AITS 内嵌 iframe 即可）。

镜像版本见 `docker/monitor-versions.env`（与 `tools/monitor/versions.json` → `docker` 段对齐）。

**Shell 兼容：** 监控脚本与主栈相同，面向 **Bash 3.2+**；实现见 `scripts/bash-compat.sh`（入口自动检测，避免 Bash 4 专有语法）。

---

## 十一、与 Windows 一键安装的对照


| 项目         | Windows（`.bat`）                  | macOS / Linux（Docker）                                   |
| ---------- | -------------------------------- | ------------------------------------------------------- |
| 安装方式       | `一键安装AITS.bat`                   | `./scripts/docker-init.sh`                              |
| 日常启动       | `一键启动AITS.bat`                   | `./scripts/docker-up.sh`                                |
| 访问端口       | 5173（前端）+ 8000（后端）               | **8080**（统一入口）                                          |
| Python     | Conda `aits-backend` 3.12        | 容器内 3.12                                                |
| Playwright | 默认有界面                            | 容器内 headless                                            |
| 数据位置       | `backend/db.sqlite3` 等           | Docker 卷 `aits_data`                                    |
| 性能监控       | `perf-monitor\` 三个 bat + MSI/ZIP | `perf-monitor/` 三个 `.sh` + `docker-compose.monitor.yml` |


---

## 十二、相关文件索引


| 文件                                                              | 说明                          |
| --------------------------------------------------------------- | --------------------------- |
| `docker-compose.yml`                                            | 服务编排                        |
| `docker/versions.env`                                           | 镜像版本 pin                    |
| `.env.docker.example`                                           | 环境变量模板                      |
| `scripts/docker-init.sh`                                        | 首次初始化                       |
| `scripts/docker-up.sh` / `docker-down.sh`                       | 启停                          |
| `docker-compose.monitor.yml`                                    | 性能监控栈（选修）                   |
| `scripts/monitor-init.sh` / `monitor-up.sh` / `monitor-down.sh` | 监控启停                        |
| `perf-monitor/一键安装性能监控.sh` 等                                    | 性能监控入口脚本                    |
| `backend/Dockerfile`                                            | 后端镜像（含 Playwright Chromium） |
| `frontend/Dockerfile` + `nginx.conf`                            | 前端构建与反代                     |
| `docs/deploy/AITS部署指南-macOS.md`                                 | macOS 补充说明                  |
| `docs/deploy/AITS部署指南-Linux云服务器.md`                             | Linux 远程开发 / 手工部署补充         |


---

## 十三、最短命令备忘

```bash
# 首次
chmod +x scripts/docker-*.sh && ./scripts/docker-init.sh
docker compose --env-file docker/versions.env --env-file .env.docker exec backend python manage.py createsuperuser

# 日常
./scripts/docker-up.sh      # 启动 → http://localhost:8080
./scripts/docker-down.sh    # 停止
```


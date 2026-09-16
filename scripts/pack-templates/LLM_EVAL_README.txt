AITS 大模型测评班 · API 自动化体验包
====================================

本包仅开放 API 自动化与 AI 实验室配置，用于测评智能体生成测试用例的效果。
首页 Web / App / 性能测试卡片保留展示，报名完整课程后可体验。

【Windows 本机 · 推荐 Windows 学员】
1. 解压到无中文、无空格路径（如 D:/aits-llm-eval）
2. 首次以管理员运行：一键安装AITS.bat（约 15-30 分钟，需联网）
3. 日常运行：一键启动AITS.bat
4. 浏览器打开：http://localhost:5173
5. 结束使用：一键关闭AITS.bat

【macOS 本机 · Docker】
1. 安装 Docker Desktop for Mac
2. 终端进入解压目录，首次运行：chmod +x 一键*.sh && ./一键安装AITS.sh
3. 日常运行：./一键启动AITS.sh
4. 浏览器打开：http://localhost:8080
5. 首次创建管理员：docker compose exec backend python manage.py createsuperuser
6. 结束使用：./一键关闭AITS.sh
   详细排错见 docs/deploy/AITS部署指南-macOS.md

【测评步骤】
1. 登录后在「AI 实验室配置」填写 LLM API Key
2. 进入「API 自动化」创建项目
3. 导入 OpenAPI / Postman 规范
4. 使用「AI 场景智能体」或端点 AI 生成用例进行测评

【API 自动化评测（脚本调用智能体）】
本包支持通过 HTTP API 调用「AI 场景智能体」并获取生成脚本，用于 LLM 语义相似度评测：
1. 阅读文档：scripts/scenario_generation_api_guide.md
2. 运行示例：python scripts/scenario_generation_api_example.py
3. 流程概要：JWT 登录 → POST generate-scenario 拿 task_id → 轮询 GET task-status 直到 completed → 读取 generated_script
4. 前置：后端、Celery Worker、Redis 均已启动（一键启动AITS.bat）

【RAG 嵌入模型】
- 默认远程模式 BAAI/bge-large-zh-v1.5，首次使用经 HF 镜像下载
- 弱网环境可在 AI 配置中改为本地离线模型

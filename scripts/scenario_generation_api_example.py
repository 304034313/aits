#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 场景智能体 API 调用示例

流程：
  1. JWT 登录获取 access token
  2. POST generate-scenario 提交场景描述，拿到 task_id
  3. 轮询 GET task-status/{task_id} 直到 completed / failed
  4. 从响应中读取 generated_script，供后续 LLM 语义相似度评测使用

依赖：pip install requests（AITS backend 环境已包含）

用法：
  python scripts/scenario_generation_api_example.py

详细说明见同目录：scripts/scenario_generation_api_guide.md

环境变量（可选，也可直接改下方 DEFAULT_* 常量）：
  AITS_BASE_URL   默认 http://127.0.0.1:8000
  AITS_USERNAME   登录用户名
  AITS_PASSWORD   登录密码
  AITS_PROJECT_ID 项目 ID
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import requests

# ---------- 可配置参数 ----------
DEFAULT_BASE_URL = os.getenv("AITS_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_USERNAME = os.getenv("AITS_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("AITS_PASSWORD", "admin123")
DEFAULT_PROJECT_ID = int(os.getenv("AITS_PROJECT_ID", "1"))

# 轮询间隔（秒）与最大等待时间（秒）
POLL_INTERVAL_SEC = 3
POLL_TIMEOUT_SEC = 600

# 示例业务场景描述（可替换为你的评测用例输入）
SAMPLE_USER_REQUEST = (
    "请针对系统的用户注册、登录、申请成为普通用户流程设计用例"
)


class AitsApiClient:
    """AITS API 轻量客户端，封装鉴权与场景生成轮询。"""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_prefix = f"{self.base_url}/api/v1"
        self.session = requests.Session()
        self._access_token: str | None = None
        self._username = username
        self._password = password

    def login(self) -> str:
        """POST /api/v1/auth/token/ 获取 JWT access token。"""
        url = f"{self.api_prefix}/auth/token/"
        resp = self.session.post(
            url,
            json={"username": self._username, "password": self._password},
            timeout=30,
        )
        resp.raise_for_status()
        # SimpleJWT 直接返回 {"access": "...", "refresh": "..."}
        payload = resp.json()
        token = payload.get("access")
        if not token:
            raise RuntimeError(f"登录失败，未返回 access token: {payload}")
        self._access_token = token
        self.session.headers["Authorization"] = f"Bearer {token}"
        return token

    def _headers(self) -> dict[str, str]:
        if not self._access_token:
            raise RuntimeError("请先调用 login()")
        return {"Authorization": f"Bearer {self._access_token}"}

    def generate_scenario(self, project_id: int, user_request: str) -> str:
        """
        提交场景生成任务。

        POST /api/v1/projects/{project_id}/api-testing/generate-scenario/
        Body: {"user_request": "..."}

        返回 Celery task_id（异步任务，需轮询 task-status 拿结果）。
        """
        url = f"{self.api_prefix}/projects/{project_id}/api-testing/generate-scenario/"
        resp = self.session.post(
            url,
            json={"user_request": user_request},
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            raise RuntimeError(f"提交场景生成失败: {body}")

        data = body.get("data") or {}
        task_id = data.get("task_id")
        if not task_id:
            raise RuntimeError(f"响应中缺少 task_id: {body}")
        return str(task_id)

    def get_task_status(self, project_id: int, task_id: str) -> dict[str, Any]:
        """
        查询异步任务状态。

        GET /api/v1/projects/{project_id}/api-testing/task-status/{task_id}/

        任务完成时 data 中包含：
          - status: "completed"
          - test_case_id: 入库后的用例 ID
          - generated_script: HttpRunner JSON 字符串（评测用的 actual 输出）
          - result: 完整 Celery 结果（与顶层字段内容一致）
        """
        url = f"{self.api_prefix}/projects/{project_id}/api-testing/task-status/{task_id}/"
        resp = self.session.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            raise RuntimeError(f"查询任务状态失败: {body}")
        return body.get("data") or {}

    def wait_scenario_result(
        self,
        project_id: int,
        task_id: str,
        *,
        interval_sec: float = POLL_INTERVAL_SEC,
        timeout_sec: float = POLL_TIMEOUT_SEC,
    ) -> dict[str, Any]:
        """轮询 task-status，直到 completed / failed 或超时。"""
        deadline = time.time() + timeout_sec
        last_status = ""

        while time.time() < deadline:
            data = self.get_task_status(project_id, task_id)
            status = (data.get("status") or "").lower()
            progress = data.get("progress", 0)
            message = data.get("message", "")

            # 仅在状态变化时打印，避免刷屏
            if status != last_status:
                print(f"[poll] status={status}, progress={progress}%, message={message}")
                last_status = status

            if status == "completed":
                return data
            if status == "failed":
                error = data.get("error") or message
                raise RuntimeError(f"场景生成任务失败: {error}")

            time.sleep(interval_sec)

        raise TimeoutError(f"轮询超时（>{timeout_sec}s），task_id={task_id}")

    def get_test_case_script(self, project_id: int, test_case_id: int) -> str:
        """
        备用：通过用例详情接口获取 script_content。

        GET /api/v1/projects/{project_id}/api-testing/test-cases/{id}/
        当 task-status 未返回 generated_script 时可用此路径兜底。
        """
        url = f"{self.api_prefix}/projects/{project_id}/api-testing/test-cases/{test_case_id}/"
        resp = self.session.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        body = resp.json()
        # 详情接口可能走 detail 包装，兼容 data 或直接字段
        detail = body.get("data") if isinstance(body.get("data"), dict) else body
        return detail.get("script_content") or ""


def extract_teststeps(generated_script: str) -> list[dict[str, Any]]:
    """将 generated_script 解析为 teststeps 列表，便于做语义比对。"""
    if not generated_script:
        return []
    try:
        doc = json.loads(generated_script)
    except json.JSONDecodeError:
        return []
    steps = doc.get("teststeps") or []
    return steps if isinstance(steps, list) else []


def main() -> int:
    base_url = DEFAULT_BASE_URL
    username = DEFAULT_USERNAME
    password = DEFAULT_PASSWORD
    project_id = DEFAULT_PROJECT_ID
    user_request = SAMPLE_USER_REQUEST

    if len(sys.argv) > 1:
        # 支持命令行传入场景描述：python ... "你的场景描述"
        user_request = " ".join(sys.argv[1:])

    print(f"Base URL: {base_url}")
    print(f"Project ID: {project_id}")
    print(f"User request: {user_request[:80]}{'...' if len(user_request) > 80 else ''}")
    print()

    client = AitsApiClient(base_url, username, password)

    # Step 1: 登录
    print("[1/3] 登录获取 JWT...")
    client.login()
    print("      登录成功")
    print()

    # Step 2: 提交场景生成
    print("[2/3] 提交场景生成任务...")
    task_id = client.generate_scenario(project_id, user_request)
    print(f"      task_id = {task_id}")
    print()

    # Step 3: 轮询直到完成
    print("[3/3] 轮询任务状态...")
    result = client.wait_scenario_result(project_id, task_id)

    test_case_id = result.get("test_case_id")
    generated_script = result.get("generated_script") or ""

    # 若顶层无脚本，尝试从 result 嵌套或详情接口兜底
    if not generated_script:
        nested = result.get("result") or {}
        if isinstance(nested, dict):
            generated_script = nested.get("generated_script") or ""
    if not generated_script and test_case_id:
        print(f"      task-status 无 generated_script，尝试读取用例详情 id={test_case_id}...")
        generated_script = client.get_test_case_script(project_id, int(test_case_id))

    if not generated_script:
        print("错误: 任务已完成但未拿到 generated_script", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    steps = extract_teststeps(generated_script)
    print()
    print("========== 生成结果摘要 ==========")
    print(f"test_case_id     : {test_case_id}")
    print(f"script 字符数    : {len(generated_script)}")
    print(f"teststeps 步骤数 : {len(steps)}")
    if steps:
        print("步骤列表:")
        for i, step in enumerate(steps, 1):
            name = step.get("name") or step.get("request", {}).get("url") or "(未命名)"
            print(f"  {i}. {name}")

    # 将完整脚本写入本地文件，方便接入你的 LLM 评测流水线
    out_file = "scenario_generated_script.json"
    with open(out_file, "w", encoding="utf-8") as f:
        # 尽量格式化输出；若本身不是合法 JSON 则原样写入
        try:
            f.write(json.dumps(json.loads(generated_script), ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            f.write(generated_script)
    print()
    print(f"完整脚本已保存: {out_file}")
    print()
    print("下一步: 将 generated_script（或 teststeps）作为 actual，")
    print("        与你的 expected 描述一起做 LLM 语义相似度判定。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

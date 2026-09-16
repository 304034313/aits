"""
WebUI Playwright智能体
用于生成WebUI测试脚本的智能体
使用mcp-use集成MCP访问能力，支持流式输出
"""

import logging
import asyncio
import os
import re
import shutil
import platform
import subprocess
from collections import deque
from typing import TypedDict, Dict, Any, Optional
from datetime import datetime
from django.core.cache import cache
from .models import MCPConfiguration
from langgraph.graph import StateGraph, END
from common.websocket import websocket_message_service, send_node_start_notification_helper
from common.parsers import extract_python_from_output
from .model_manager import get_llm_manager
# ----------------------------------------------------------------------------
# 必须在 `from mcp_use import ...` 之前关掉匿名遥测，否则 mcp_use 导入时就会
# 在 celery worker 主进程里同步发起向远程 telemetry endpoint 的 HTTP 调用。
# 当用户开了 VPN 且 VPN 把该出站连接黑洞了，TCP connect 会阻塞到 OS 级别的
# 系统超时（Windows 通常 75s+），期间整个进程的 GIL 被 socket connect 持有，
# 任何 Python 代码都进不去，整个 worker 看似"卡死"。
# ----------------------------------------------------------------------------
os.environ.setdefault('MCP_USE_ANONYMIZED_TELEMETRY', 'false')
os.environ.setdefault('ANONYMIZED_TELEMETRY', 'false')
os.environ.setdefault('DO_NOT_TRACK', '1')

from mcp_use import MCPClient, MCPAgent
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class ExplorationPartialComplete(Exception):
    """MCP 探索在 LangGraph 递归上限前已完成关键浏览器操作，可基于回放记录合成脚本。"""


# ============================================================================
# Celery × mcp_use stdio 兼容补丁
# ----------------------------------------------------------------------------
# Celery worker 启动后会把 sys.stderr 替换成 `celery.utils.log.LoggingProxy`，
# 这不是真正的 file descriptor。而 `mcp_use.client.connectors.stdio.StdioConnector`
# 的 `__init__(errlog=sys.stderr, ...)` 默认参数是在模块加载时绑定的，于是
# 它绑定到了那个 LoggingProxy。
#
# 后续 mcp_use 启动 playwright MCP 子进程时，会把 LoggingProxy 作为子进程的
# stderr 透传给 anyio 的 `open_process(...)`。子进程握手阶段尝试写 stderr，
# 由于 stderr 不是合法 fd，会**永久阻塞**，且因为底层用 C 层 read/write，
# Python asyncio.wait_for 的 timeout 也打断不了。
#
# 修复：模块加载阶段（celery worker fork 之后）一次性把 StdioConnector
# 的默认 errlog 改成一个真实的、写到 devnull 的文件对象。这样任何后续从
# `MCPClient.from_dict(config)` 路径创建的 StdioConnector 都不会再用 LoggingProxy。
# ============================================================================
def _patch_mcp_use_stdio_errlog() -> None:
    try:
        import mcp_use.client.connectors.stdio as _stdio_mod
        import mcp_use.client.task_managers.stdio as _task_stdio_mod

        # 一个永远不阻塞、写到 devnull 的真实文件对象
        safe_errlog = open(os.devnull, 'w', buffering=1, encoding='utf-8')

        def _is_celery_logging_proxy(stream) -> bool:
            """**只**判断是否是 Celery LoggingProxy 实例，None / 真实文件均不算。"""
            if stream is None:
                return False
            try:
                return 'LoggingProxy' in str(type(stream))
            except Exception:  # noqa: BLE001
                return False

        def _replace_logging_proxy_in_defaults(func) -> int:
            """把 func.__defaults__ 中 *Celery LoggingProxy* 类型的项换成 safe_errlog，
            返回替换数量。其他类型（None、回调、字典等）保持原样。"""
            if not getattr(func, '__defaults__', None):
                return 0
            new = []
            replaced = 0
            for d in func.__defaults__:
                if _is_celery_logging_proxy(d):
                    new.append(safe_errlog)
                    replaced += 1
                else:
                    new.append(d)
            if replaced:
                func.__defaults__ = tuple(new)
            return replaced

        n1 = _replace_logging_proxy_in_defaults(_stdio_mod.StdioConnector.__init__)
        n2 = _replace_logging_proxy_in_defaults(_task_stdio_mod.StdioConnectionManager.__init__)

        # 再加一层 wrapper 兜底：即便后续有人以位置 / kw 参数显式传入了 LoggingProxy，
        # 也在 __init__ 进入前把它换成 safe_errlog。
        _orig_stdio_init = _stdio_mod.StdioConnector.__init__

        def _patched_stdio_init(self, *args, **kwargs):
            if 'errlog' in kwargs and _is_celery_logging_proxy(kwargs['errlog']):
                kwargs['errlog'] = safe_errlog
            # positional: self, command, args, env, errlog, ...
            if len(args) >= 4 and _is_celery_logging_proxy(args[3]):
                args = args[:3] + (safe_errlog,) + args[4:]
            return _orig_stdio_init(self, *args, **kwargs)

        _stdio_mod.StdioConnector.__init__ = _patched_stdio_init

        logger.info(
            f"[mcp-patch] 已替换 mcp_use StdioConnector/Manager 默认 errlog，"
            f"LoggingProxy 替换数={n1 + n2}，避免 Celery LoggingProxy 卡死 stdio 子进程"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[mcp-patch] 替换 mcp_use stdio errlog 默认参数失败: {exc}", exc_info=True)


_patch_mcp_use_stdio_errlog()


def _patch_mcp_use_drop_none_arguments() -> None:
    """修复 mcp_use 把 LangChain Pydantic 的 None 默认值透传给 MCP 服务器的 bug。

    背景：
        LangChain 在调用 BaseTool 时会用 Pydantic schema 验证 kwargs。对于
        ``Optional[T]`` 字段，如果调用方没传，Pydantic 会自动用 None 填默认值。
        mcp_use 的 ``LangChainAdapter._arun`` 把整份 kwargs 原样传给
        ``connector.call_tool``，connector 又原样透传给 MCP server 端。

        但许多 MCP server（包括 ``@playwright/mcp@latest``）的工具用 Zod 校验，
        ``z.string().optional()`` 接受**字段缺失**（undefined）但**不接受 null**。
        所以 LLM 调 ``browser_snapshot({})`` 时，4 个 optional 字段都被填成 None，
        然后被 Zod 全部拒绝（``Invalid input: expected string, received null``）。
        LLM 怎么改 input 都过不了 schema，最后撞 LangGraph recursion limit。

        参考：https://github.com/mcp-use/mcp-use/issues  (LangChain Pydantic Optional → null)

    修复：
        在 BaseConnector.call_tool 入口剔除 arguments 里 value 为 None 的键。
        BaseConnector 是所有 connector（stdio / sse / websocket / http）的公共父类，
        patch 一次所有传输层全部生效；同时 LangChain / OpenAI / Anthropic / Google
        各家 adapter 走的也都是它，覆盖完整。
    """
    try:
        from mcp_use.client.connectors import base as _base
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[mcp-patch] 导入 BaseConnector 失败，跳过 None 过滤补丁: {exc}")
        return

    BaseConnector = getattr(_base, 'BaseConnector', None)
    if BaseConnector is None or not hasattr(BaseConnector, 'call_tool'):
        logger.warning("[mcp-patch] BaseConnector.call_tool 未找到，跳过 None 过滤补丁")
        return

    if getattr(BaseConnector.call_tool, '_aits_none_filter_patched', False):
        return

    original_call_tool = BaseConnector.call_tool

    async def _patched_call_tool(self, name, arguments, read_timeout_seconds=None):
        if isinstance(arguments, dict) and arguments:
            cleaned = {k: v for k, v in arguments.items() if v is not None}
            if len(cleaned) != len(arguments):
                dropped = [k for k, v in arguments.items() if v is None]
                logger.debug(
                    f"[mcp-patch] tool={name} 剔除 None 参数: {dropped} "
                    f"(原 {len(arguments)} 个 → 实传 {len(cleaned)} 个)"
                )
            arguments = cleaned
        return await original_call_tool(self, name, arguments, read_timeout_seconds)

    _patched_call_tool._aits_none_filter_patched = True  # type: ignore[attr-defined]
    BaseConnector.call_tool = _patched_call_tool
    logger.info(
        "[mcp-patch] 已 patch BaseConnector.call_tool — "
        "调 MCP 服务器前自动剔除 None 值参数，避免 Zod schema 拒绝"
    )


_patch_mcp_use_drop_none_arguments()


def _enforce_script_guarantees(script: str, description: str = '') -> str:
    """轻量级草稿脚本兜底：仅保证基础导包合法"""
    if not script or not script.strip():
        return script
    required_import = 'from playwright.async_api import async_playwright, expect'
    if required_import not in script:
        script = required_import + '\n' + script
    return script


# AITS 自定义结构化断言围栏（在 LLM 输出里识别此围栏，提取 JSON 断言列表）
ASSERTION_FENCE_RE = re.compile(
    r'<aits_assertions>(.*?)</aits_assertions>',
    re.DOTALL | re.IGNORECASE,
)


def _extract_llm_assertions(raw_output: str) -> list:
    """从 LLM 原始输出里抽取 <aits_assertions>...</aits_assertions> 围栏内的 JSON 数组。

    兼容两种位置：在围栏内、或在围栏外的独立 ```json``` 区块（带 aits_assertions 标签）。
    解析失败时返回空 list。
    """
    if not raw_output:
        return []
    m = ASSERTION_FENCE_RE.search(raw_output)
    if m:
        body = m.group(1).strip()
        # 兼容把 JSON 写在 ```json ``` 里
        code_block = re.search(r'```json\s*(.+?)\s*```', body, re.DOTALL | re.IGNORECASE)
        json_text = code_block.group(1) if code_block else body
    else:
        # 退化：尝试在文末找一个 ```json aits_assertions``` 之类的注释
        code_block = re.search(
            r'```json\s+aits_assertions\s*(.+?)\s*```',
            raw_output,
            re.DOTALL | re.IGNORECASE,
        )
        if not code_block:
            return []
        json_text = code_block.group(1)
    try:
        import json as _json
        data = _json.loads(json_text)
        if isinstance(data, dict):
            data = data.get('assertions') or data.get('expectations') or []
        return data if isinstance(data, list) else []
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"LLM 断言 JSON 解析失败: {exc}; 原文片段: {json_text[:200]!r}")
        return []


def _strip_inline_expects(script: str) -> str:
    """删除 LLM 不小心写在 run(page) 里的 await expect(...) 行；保留 LLM 应输出的结构化断言。"""
    if not script:
        return script
    cleaned_lines = []
    for ln in script.splitlines():
        stripped = ln.strip()
        if stripped.startswith('await expect(') or stripped.startswith('await expect.soft('):
            continue
        cleaned_lines.append(ln)
    return '\n'.join(cleaned_lines)


def _inject_translated_assertions(script: str, raw_assertions: list) -> str:
    """把 LLM 给出的结构化断言列表翻译为 Playwright 代码并追加到 run(page) 末尾。

    使用统一的 assertion_translator，与路径 A 保持完全一致的代码风格（with allure.step + soft）。
    """
    if not script or not raw_assertions:
        return script
    try:
        from apps.web_testing.assertion_translator import translate_assertions, required_imports
        from apps.web_testing.assertion_schema import validate_assertions
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"导入 assertion_translator 失败: {exc}")
        return script
    specs = validate_assertions(raw_assertions)
    if not specs:
        return script

    # 1. 补缺失 import
    for imp in required_imports(specs):
        first = imp.split(' ', 2)
        if first[0] == 'from' and len(first) >= 3:
            module = first[1]
            if f'from {module} import' in script:
                continue
        if first[0] == 'import' and len(first) >= 2:
            module = first[1]
            if re.search(rf'^import\s+{re.escape(module)}\b', script, re.MULTILINE):
                continue
        # 插入到第一个 from playwright 之后
        anchor = re.search(r'^from\s+playwright\.async_api[^\n]*\n', script, re.MULTILINE)
        if anchor:
            script = script[:anchor.end()] + imp + '\n' + script[anchor.end():]
        else:
            script = imp + '\n' + script

    # 2. 找 run(page) 函数体追加翻译后的代码
    run_match = re.search(
        r'(async\s+def\s+run\s*\(\s*page\s*\)\s*:.*?)(?=\n\s*async\s+def\s+main|\Z)',
        script,
        re.DOTALL,
    )
    if not run_match:
        return script
    run_block = run_match.group(1).rstrip()
    code_chunk = translate_assertions(specs, indent='    ', wrap_with_allure=True)
    if code_chunk:
        run_block += '\n\n    # [AITS] LLM 结构化断言（统一翻译器生成）\n' + code_chunk
    return script[: run_match.start()] + run_block + script[run_match.end():]


def load_user_mcp_playwright_config(user_id: Optional[int]) -> Dict[str, Any]:
    """在 sync 上下文（Celery task 主线程）下加载某用户启用的 playwright MCP 配置。

    返回值结构与 ``_load_mcp_config_node`` 输出的 ``mcp_config`` 一致：
    ``{"mcpServers": {...}}``；如果找不到/不可用则返回 ``{"mcpServers": {}}``。

    将此函数在 ``asyncio.run(agent.run(...))`` 之前调用，把结果赋给
    ``agent.mcp_config``，可以让 ``_load_mcp_config_node`` 直接 short-circuit，
    彻底避开 Django ORM 在 LangGraph ainvoke async 上下文里被调用的问题。
    """
    try:
        query_filter = {'is_active': True}
        if user_id:
            query_filter['created_by_id'] = user_id

        mcp_configs = list(MCPConfiguration.objects.filter(**query_filter))
        if not mcp_configs:
            logger.info(f"[mcp-config] 用户 {user_id} 没有启用的 MCP 配置")
            return {"mcpServers": {}}

        playwright_config_obj = None
        for cfg in mcp_configs:
            try:
                cfg_dict = cfg.get_config_dict() or {}
                mcp_servers = cfg_dict.get('mcpServers', {}) or {}
                if 'playwright' not in mcp_servers:
                    continue
                if not mcp_servers['playwright'].get('is_active', True):
                    continue
                playwright_config_obj = cfg
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[mcp-config] 解析 MCP 配置 {cfg.id} 失败: {exc}")
                continue

        if not playwright_config_obj:
            logger.warning("[mcp-config] 未找到 playwright MCP 配置")
            return {"mcpServers": {}}

        cfg_dict = playwright_config_obj.get_config_dict() or {}
        mcp_servers = cfg_dict.get('mcpServers') or {}
        playwright_server = mcp_servers.get('playwright')
        if not playwright_server:
            return {"mcpServers": {}}

        # 注入默认环境变量 + timeout（与原 _load_mcp_config_node 逻辑保持一致）
        env = playwright_server.setdefault('env', {})
        env.setdefault('PYTHONUNBUFFERED', '1')
        env.setdefault('MCP_USE_ANONYMIZED_TELEMETRY', 'false')
        playwright_server.setdefault('timeout', 30)

        if 'command' not in playwright_server:
            logger.error("[mcp-config] playwright 配置缺少 command 字段")
            return {"mcpServers": {}}

        return {"mcpServers": mcp_servers}
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[mcp-config] 加载 playwright MCP 配置异常: {exc}", exc_info=True)
        return {"mcpServers": {}}


# POM 元素库未收录时塞给 prompt 的占位文案
EMPTY_POM_CONTEXT_TEXT = "当前项目暂无收录的标准页面元素，请基于 browser_snapshot 的实时观察自主选择稳定定位器。"


def load_project_pom_context(project_id: Optional[int]) -> str:
    """在 sync 上下文（Celery task 主线程）加载某项目的 POM 元素摘要文本。

    LangGraph ainvoke 的异步上下文里调用 Django ORM 在某些环境（Windows + Celery
    prefork + 嵌套事件循环）下会被 Django 的 ``async_unsafe`` 拦截，无论包
    ``sync_to_async`` 还是 ``asyncio.to_thread`` 都拦不住——根本原因是 main loop
    的 contextvars 会被复制到 worker thread，导致 ``asyncio.get_running_loop()``
    在 worker thread 里仍能找到 loop。

    最稳的做法是在 Celery task 主线程（纯 sync）阶段就把 POM 文本查出来，注入到
    ``agent.preloaded_pom_context``，async 节点只读字符串、绝不再碰 ORM。

    返回：可直接塞进 prompt 的多行字符串。无数据时返回 :data:`EMPTY_POM_CONTEXT_TEXT`。
    """
    if not project_id:
        return EMPTY_POM_CONTEXT_TEXT
    try:
        from web_testing.models import WebElement
        elements = list(
            WebElement.objects
            .filter(page__project_id=project_id)
            .select_related('page')
        )
        if not elements:
            return EMPTY_POM_CONTEXT_TEXT
        lines = [
            f"- 页面【{el.page.name}】| 元素: {el.name} | 定位器: {el.locator_type}={el.locator_value} | 推荐操作: {el.action_type or '自动识别'}"
            for el in elements
        ]
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[pom] 加载项目 {project_id} 的 POM 元素库失败（不阻塞主流程）: {exc}", exc_info=True)
        return EMPTY_POM_CONTEXT_TEXT


# 定义WebUI Playwright Agent状态数据结构
class WebUIPlaywrightAgentState(TypedDict):
    """WebUI Playwright测试脚本生成Agent的状态数据"""
    description: str                    # 用户需求描述
    url: str                           # 目标URL
    user_id: int                       # 用户ID
    project_id: Optional[int]          # 项目ID
    script_name: Optional[str]         # 脚本名称
    mcp_config: Dict[str, Any]         # MCP服务器配置
    test_case_id: Optional[int]        # 测试用例ID
    steps_info: Optional[str]          # 测试步骤（JSON 或结构化文本）
    expected_result: Optional[str]      # 预期结果
    yaml_test_script: Optional[str]     # 生成的yaml测试脚本
    test_script: Optional[str]          # 转换后的Python测试脚本
    script_id: Optional[int]            # 保存的脚本ID
    current_step: str                   # 当前执行步骤
    llm_assertions: Optional[list]      # LLM 输出的结构化断言（DSL）；用于回写到 WebUITestCase.expectations


class WebUIPlaywrightAgent:
    """WebUI Playwright测试脚本生成智能体"""
    
    def __init__(self, user_id: int, user=None, enable_streaming: bool = True):
        self.user = user
        self.user_id = user_id
        self.enable_streaming = enable_streaming
        self.project_id = None
        self.script_name = None
        self.mcp_config = {}
        self.test_case_id = None
        # 外部注入：当前Celery任务ID（用于协作式取消）
        self.celery_task_id: Optional[str] = None
        # 外部注入（推荐）：在 sync 阶段加载好的项目 POM 元素库摘要文本。
        # 若已注入，则 _call_mcp_node 不会再在异步上下文里查 ORM。
        # 值约定：None 表示"未预加载"，空串/"暂无收录..." 表示"已预加载但没有元素"。
        self.preloaded_pom_context: Optional[str] = None
        # 由 _save_script_node 异步阶段写入、agent.run() 返回时带给 task 层去 sync 持久化。
        # 结构：{"test_case_id": int, "user_id": int, "script": str, "expectations": list}
        self.pending_persistence: Optional[Dict[str, Any]] = None

        # 初始化LLM管理器
        try:
            self.llm_manager = get_llm_manager()
            logger.info(f"LLM管理器初始化成功: {self.llm_manager.get_model_info()}")
        except Exception as e:
            logger.error(f"LLM管理器初始化失败: {e}")
            raise RuntimeError(f"LLM管理器初始化失败: {e}") from e
        
        # 初始化MCP客户端
        self.mcp_client = None
        self.mcp_agent = None
        # MCP日志handler（避免重复挂载导致日志重复）
        self._mcp_log_handler = None
        # 最近输出去重：只在短窗口内去重，避免刷屏
        self._recent_log_hashes = deque(maxlen=200)
        # 已发送过的工具调用事件指纹（避免 stream dict 模式同一 action 被多个 chunk 重复推送）
        self._emitted_tool_fingerprints = set()
        # AI 实验室探索记录缓冲（task 层落库为 WebUILabExploration）
        self._exploration_agent_actions: List[Dict[str, Any]] = []
        self._exploration_streaming_log: str = ''

        # 构建LangGraph工作流
        self.workflow = self._build_workflow()

    def _reset_exploration_buffers(self) -> None:
        self._exploration_agent_actions = []
        self._exploration_streaming_log = ''

    def get_exploration_artifacts(self) -> Dict[str, Any]:
        return {
            'agent_actions': list(self._exploration_agent_actions),
            'streaming_log': self._exploration_streaming_log,
        }

    def _append_exploration_streaming(self, content: str) -> None:
        if not content:
            return
        from apps.web_testing.lab_exploration_service import STREAMING_LOG_MAX_CHARS
        combined = self._exploration_streaming_log + content
        if len(combined) > STREAMING_LOG_MAX_CHARS:
            combined = combined[-STREAMING_LOG_MAX_CHARS:]
        self._exploration_streaming_log = combined

    def _is_cancelled(self) -> bool:
        """通过cache标记判断是否已请求取消（由停止接口写入）。"""
        if not self.celery_task_id:
            return False
        return bool(cache.get(f"celery:cancel:{self.celery_task_id}"))

    async def _wait_cancel_signal(self, poll_interval: float = 0.5):
        """异步等待取消信号（用于并发取消 mcp_agent.run）。"""
        while True:
            if self._is_cancelled():
                return
            await asyncio.sleep(poll_interval)
    
    
    def _initialize_mcp_client(self, config: Dict[str, Any]) -> MCPClient:
        """初始化MCP客户端。

        注意：LoggingProxy 问题已通过模块加载时的 ``_patch_mcp_use_stdio_errlog()``
        从根上修掉了——StdioConnector 的默认 errlog 不再会绑定到 LoggingProxy。
        所以这里不再需要"临时把 sys.stderr 换成 subprocess.PIPE"那种早期 hack
        （那种 hack 反而会把一个 int(-1) 写到 sys.stderr，污染整个进程的日志）。
        """
        try:
            self._validate_mcp_config(config)
            client = MCPClient.from_dict(config)
            logger.info("MCP客户端创建成功")
            return client
        except Exception as e:
            logger.error(f"MCP客户端初始化失败: {e}", exc_info=True)
            raise RuntimeError(f"MCP客户端初始化失败: {e}") from e
    
    def _validate_mcp_config(self, config: Dict[str, Any]) -> None:
        """验证MCP配置（增强Windows平台支持）"""
        mcp_servers = config.get('mcpServers', {})
        if not mcp_servers:
            raise ValueError("MCP配置中没有找到mcpServers")
        
        is_windows = platform.system() == 'Windows'
        
        for server_name, server_config in mcp_servers.items():
            if 'command' not in server_config:
                raise ValueError(f"MCP服务器 {server_name} 缺少command字段")
            
            command = server_config['command']
            args = server_config.get('args', [])
            
            logger.info(f"验证MCP服务器 {server_name}: command={command}, args={args}")
            
            # 检查命令是否存在
            command_path = shutil.which(command)
            if not command_path:
                error_msg = f"MCP服务器命令 '{command}' 在PATH中未找到"
                logger.error(error_msg)
                
                # Windows平台特殊提示
                if is_windows:
                    if command == 'npx':
                        error_msg += "。请确保已安装Node.js，并且npx在PATH中可用。"
                    elif command.endswith('.sh') or command.endswith('.bash'):
                        error_msg += "。Windows系统不支持直接执行.sh脚本，请使用对应的Windows可执行文件。"
                
                raise ValueError(error_msg)
            
            # Windows平台额外验证
            if is_windows:
                # 检查文件是否存在且可执行
                if os.path.exists(command_path):
                    # 检查是否是有效的可执行文件
                    if command_path.endswith('.sh') or command_path.endswith('.bash'):
                        raise ValueError(f"Windows系统不支持执行Shell脚本: {command_path}。请使用Windows可执行文件或npx。")
                    
                    # 对于npx，检查Node.js是否可用
                    if command == 'npx':
                        try:
                            result = subprocess.run(
                                ['node', '--version'],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            if result.returncode != 0:
                                raise ValueError("Node.js未正确安装或不可用")
                            logger.info(f"Node.js版本: {result.stdout.strip()}")
                        except FileNotFoundError:
                            raise ValueError("Node.js未安装。请先安装Node.js才能使用npx命令。")
                        except Exception as e:
                            logger.warning(f"检查Node.js时出错: {e}")
                else:
                    logger.warning(f"命令路径不存在: {command_path}")
            
            logger.info(f"MCP服务器 {server_name} 验证通过: {command_path}")
    
    def _initialize_mcp_agent(self, client: MCPClient) -> MCPAgent:
        """初始化MCP智能体。

        说明：LoggingProxy 问题已通过 ``_patch_mcp_use_stdio_errlog()`` 从根解决，
        这里也不需要 sys.stderr / subprocess.PIPE 的早期 hack 了。

        max_steps / recursion_limit 策略：
        - AI 实验室探索：max_steps=10（对齐 prompt「≤8 次工具」+ 最终纯文本输出），
          recursion_limit 单独提高到 36（默认 max_steps*2=20 不足以支撑 7~8 次工具 + 收尾）。
        - 业务用例回归：max_steps=20，recursion_limit 沿用 mcp_use 默认 max_steps*2。
        """
        try:
            llm_model = self.llm_manager.current_llm
            if not llm_model:
                raise RuntimeError("LLM模型未初始化")

            model_info = self.llm_manager.get_model_info()
            logger.info(f"使用LLM模型: {model_info}")

            is_exploratory = not bool(getattr(self, 'test_case_id', None))
            max_steps = 10 if is_exploratory else 20
            logger.info(
                f"[mcp-agent] 模式={'AI实验室探索' if is_exploratory else '业务用例回归'}, "
                f"max_steps={max_steps}"
            )

            agent = MCPAgent(llm=llm_model, client=client, max_steps=max_steps)
            if is_exploratory:
                # mcp_use 默认 recursion_limit = max_steps * 2；8 次工具约需 24~30 个图节点
                agent.recursion_limit = 36
                logger.info(f"[mcp-agent] 探索模式 recursion_limit={agent.recursion_limit}")
            logger.info("MCP智能体初始化成功")
            return agent
        except Exception as e:
            logger.error(f"MCP智能体初始化失败: {e}", exc_info=True)
            raise RuntimeError(f"MCP智能体初始化失败: {e}") from e
    
    def _build_workflow(self) -> StateGraph:
        """构建LangGraph工作流"""
        # 创建状态图
        graph = StateGraph(WebUIPlaywrightAgentState)
        
        # 添加所有节点
        graph.add_node("load_mcp_config", self._load_mcp_config_node)
        graph.add_node("initialize_mcp", self._initialize_mcp_node)
        graph.add_node("call_mcp", self._call_mcp_node)
        graph.add_node("save_script", self._save_script_node)
        
        # 设置入口点
        graph.set_entry_point("load_mcp_config")
        
        # 添加条件边
        graph.add_conditional_edges(
            "load_mcp_config",
            self._decide_after_config_load,
            {
                "initialize_mcp": "initialize_mcp",
                "__end__": END
            }
        )
        
        graph.add_conditional_edges(
            "initialize_mcp",
            self._decide_after_mcp_init,
            {
                "call_mcp": "call_mcp",
                "__end__": END
            }
        )
        
        graph.add_conditional_edges(
            "call_mcp",
            self._decide_after_mcp_call,
            {
                "save_script": "save_script",
                "__end__": END
            }
        )

        graph.add_edge("save_script", END)
        
        return graph.compile()
    
    def _send_websocket_message(self, content: str, step: str = ""):
        """发送WebSocket流式消息"""
        if not self.enable_streaming or not self.user_id:
            return False
        
        try:
            timestamp = datetime.now().isoformat()
            
            # 检查WebSocket服务是否可用
            if not websocket_message_service.is_available():
                logger.error("WebSocket服务不可用，无法发送消息")
                return False
            
            success = websocket_message_service.send_streaming_output(
                user_id=self.user_id,
                step=step,
                content=content,
                timestamp=timestamp,
                room_type="webui_auto_test"
            )
            
            if not success:
                logger.warning(f"WebSocket流式消息发送失败: step={step}")

            self._append_exploration_streaming(content)
            return success
        except Exception as e:
            logger.error(f"WebSocket消息发送异常: {e}")
            return False
    
    def _send_node_start_notification(self, node_name: str, node_display_name: str):
        """发送节点开始执行通知（使用统一的辅助函数）"""
        return send_node_start_notification_helper(
            user_id=self.user_id,
            node_name=node_name,
            node_display_name=node_display_name,
            enable_streaming=self.enable_streaming,
            room_type="webui_auto_test"
        )
    
    def _send_task_completed_notification(self, state: WebUIPlaywrightAgentState):
        """发送任务完成通知"""
        if not self.enable_streaming or not self.user_id:
            return False
        
        try:
            timestamp = datetime.now().isoformat()
            
            # 检查WebSocket服务是否可用
            if not websocket_message_service.is_available():
                logger.error("WebSocket服务不可用，无法发送任务完成通知")
                return False
            
            # 构建任务结果
            result = {
                "test_script": state.get("test_script"),
                "script_id": state.get("script_id"),
                "test_case_id": state.get("test_case_id"),
                "current_step": state.get("current_step", "completed")
            }
            
            success = websocket_message_service.send_task_completed(
                user_id=self.user_id,
                task_id="webui_auto_test",
                result=result,
                message="任务完成",
                timestamp=timestamp,
                room_type="webui_auto_test"
            )
            
            if success:
                logger.info("任务完成通知发送成功")
            else:
                logger.warning("WebSocket任务完成通知发送失败")
            
            return success
        except Exception as e:
            logger.error(f"WebSocket任务完成通知发送异常: {e}")
            return False
    
    def _process_and_send_mcp_output(self, message: str, levelno: int = logging.INFO):
        """处理并发送MCP智能体输出到前端（带去重/过滤）"""
        if not message:
            return
        
        message = message.strip()
        if not message:
            return
        
        # 过滤掉过长/噪音内容
        if "📄 Tool result:" in message:
            return
        if "Anonymized telemetry enabled" in message or "MCP_USE_ANONYMIZED_TELEMETRY" in message:
            return

        # 去重：短窗口内相同消息只发一次（解决重复日志）
        msg_hash = hash(message)
        if msg_hash in self._recent_log_hashes:
            return
        self._recent_log_hashes.append(msg_hash)
        
        self._send_websocket_message(f"{message}\n", "MCP智能体运行")

    # ====== AI 操作回放：工具调用业务化翻译 ======

    # tool_name -> (icon_key, display_template)
    # display_template 支持 {summary}（业务化摘要） / {raw}（截断的原始入参）
    _TOOL_DISPLAY_MAP = {
        'browser_navigate': ('globe', '正在打开页面：{summary}'),
        'browser_navigate_back': ('back', '返回上一页'),
        'browser_navigate_forward': ('forward', '前进到下一页'),
        'browser_snapshot': ('search', '正在分析页面结构…'),
        'browser_take_screenshot': ('camera', '截取页面快照'),
        'browser_click': ('mouse', '模拟点击：{summary}'),
        'browser_hover': ('hover', '悬停元素：{summary}'),
        'browser_type': ('keyboard', '模拟输入：{summary}'),
        'browser_fill': ('keyboard', '模拟输入：{summary}'),
        'browser_press_key': ('keyboard', '按下按键：{summary}'),
        'browser_select_option': ('list', '选择下拉项：{summary}'),
        'browser_wait_for': ('clock', '等待页面元素：{summary}'),
        'browser_evaluate': ('code', '执行 JS 代码片段'),
        'browser_console_messages': ('terminal', '读取浏览器控制台输出'),
        'browser_network_requests': ('network', '查看网络请求'),
        'browser_close': ('close', '关闭浏览器'),
        'browser_resize': ('resize', '调整窗口尺寸：{summary}'),
        'browser_tabs': ('tab', '切换/管理浏览器标签页'),
    }

    @staticmethod
    def _summarize_tool_input(tool_name: str, tool_input: Any) -> str:
        """从 tool_input 里提取一个简短业务摘要（不含敏感大块 DOM）。"""
        if tool_input is None:
            return ''
        # 字符串入参直接截断
        if isinstance(tool_input, str):
            s = tool_input.strip()
            return s if len(s) <= 80 else s[:77] + '…'
        # 字典入参：按 tool 类型提取关键字段
        if isinstance(tool_input, dict):
            preferred_keys_by_tool = {
                'browser_navigate': ['url'],
                'browser_click': ['element', 'text', 'ref', 'selector', 'role', 'name'],
                'browser_hover': ['element', 'text', 'ref', 'selector'],
                'browser_type': ['text', 'value', 'element'],
                'browser_fill': ['text', 'value', 'element'],
                'browser_press_key': ['key'],
                'browser_select_option': ['values', 'value', 'element', 'text'],
                'browser_wait_for': ['text', 'selector', 'time'],
                'browser_resize': ['width', 'height'],
            }
            for key in preferred_keys_by_tool.get(tool_name, []):
                if key in tool_input and tool_input[key] not in (None, '', []):
                    val = tool_input[key]
                    if isinstance(val, (list, tuple)):
                        val = ', '.join(str(x) for x in val)
                    val = str(val).strip()
                    return val if len(val) <= 80 else val[:77] + '…'
            # 兜底：dump 一下短摘要
            try:
                import json as _json
                dump = _json.dumps(tool_input, ensure_ascii=False, default=str)
            except Exception:
                dump = str(tool_input)
            return dump if len(dump) <= 80 else dump[:77] + '…'
        # 其他类型 fallback
        s = str(tool_input)
        return s if len(s) <= 80 else s[:77] + '…'

    @staticmethod
    def _truncate(text: Any, limit: int = 500) -> str:
        if text is None:
            return ''
        try:
            s = text if isinstance(text, str) else str(text)
        except Exception:
            return ''
        if len(s) <= limit:
            return s
        return s[:limit] + f'…(已截断，原长 {len(s)} 字符)'

    def _emit_tool_call(self, tool_name: str, tool_input: Any, observation: Any = None) -> None:
        """把一次工具调用翻译成业务文案，并通过 tool_call WebSocket 事件推送。"""
        if not tool_name:
            return
        # 去重：相同 (tool_name, tool_input) 在 stream dict 模式下可能被多个 chunk 重复带出来
        try:
            import json as _json
            fingerprint_payload = _json.dumps([tool_name, tool_input], ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            fingerprint_payload = f'{tool_name}|{tool_input}'
        fingerprint = hash(fingerprint_payload)
        if fingerprint in self._emitted_tool_fingerprints:
            return
        self._emitted_tool_fingerprints.add(fingerprint)

        icon_key, template = self._TOOL_DISPLAY_MAP.get(
            tool_name,
            ('tool', '调用工具：{summary}' if not tool_name.startswith('browser_') else '浏览器工具：{summary}')
        )
        summary = self._summarize_tool_input(tool_name, tool_input)
        try:
            display_text = template.format(summary=summary, raw=summary, tool=tool_name)
        except Exception:
            display_text = f'{tool_name}: {summary}' if summary else tool_name
        # 如果 summary 为空但模板里又用了 {summary}，把多余的冒号清掉
        display_text = display_text.replace('：\n', '\n').rstrip('：').rstrip()

        raw_input_trunc = self._truncate(tool_input, 400)
        raw_output_trunc = self._truncate(observation, 500)

        # 诊断：如果工具返回了错误（### Error / Zod schema 错误），完整把错误写到 worker 日志，
        # 方便排查"为什么 LLM 一直调工具都失败"。截断的简短日志看不出 Zod path 等字段。
        try:
            obs_text_full = ''
            if observation is None:
                obs_text_full = ''
            elif isinstance(observation, str):
                obs_text_full = observation
            elif isinstance(observation, (list, tuple)):
                # mcp_use 一般返回 [TextContent(text=...)] 列表
                parts = []
                for it in observation:
                    text_attr = getattr(it, 'text', None)
                    if isinstance(text_attr, str):
                        parts.append(text_attr)
                    else:
                        parts.append(str(it))
                obs_text_full = '\n'.join(parts)
            else:
                obs_text_full = str(observation)

            if '### Error' in obs_text_full or '"code": "invalid' in obs_text_full:
                logger.error(
                    f"[mcp-tool-error] 工具 {tool_name} 调用失败 — 完整错误:\n"
                    f"  input  = {tool_input!r}\n"
                    f"  output = {obs_text_full[:2000]}"
                )
        except Exception as diag_exc:  # noqa: BLE001
            logger.debug(f"[mcp-tool-error] 诊断日志记录失败: {diag_exc}")

        # 1. 推送结构化 tool_call 事件（前端 AI 操作回放面板使用）
        try:
            if self.enable_streaming and self.user_id and websocket_message_service.is_available():
                websocket_message_service.send_tool_call(
                    user_id=self.user_id,
                    tool_name=tool_name,
                    display_text=display_text,
                    icon=icon_key,
                    raw_input=raw_input_trunc,
                    raw_output=raw_output_trunc,
                    timestamp=datetime.now().isoformat(),
                    room_type='webui_auto_test',
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f'发送 tool_call WebSocket 事件失败: {exc}')

        # 2. 同时往底层日志面板推一条人类可读的描述（兼容旧的 streaming_output 视图）
        self._send_websocket_message(f'🛠 {display_text}\n', 'MCP智能体生成')

        # 3. 实验室探索历史缓冲（与 tool_call 事件结构一致，供落库）
        if not getattr(self, 'test_case_id', None):
            self._exploration_agent_actions.append({
                'tool_name': tool_name,
                'display_text': display_text,
                'icon': icon_key,
                'raw_input': raw_input_trunc,
                'raw_output': raw_output_trunc,
                'timestamp': datetime.now().isoformat(),
            })

    @staticmethod
    def _extract_action_info(action_obj: Any) -> Optional[Dict[str, Any]]:
        """从 LangChain AgentAction / dict 等多种形态提取 (tool, tool_input)。"""
        if action_obj is None:
            return None
        # LangChain AgentAction
        tool_name = getattr(action_obj, 'tool', None)
        tool_input = getattr(action_obj, 'tool_input', None)
        if tool_name:
            return {'tool': tool_name, 'tool_input': tool_input}
        # dict 形态
        if isinstance(action_obj, dict):
            t = action_obj.get('tool') or action_obj.get('name')
            i = action_obj.get('tool_input', action_obj.get('args', action_obj.get('input')))
            if t:
                return {'tool': t, 'tool_input': i}
        return None

    def _emit_tool_calls_from_chunk(self, chunk: Any) -> None:
        """统一处理 mcp_use 1.5.x agent.stream() 各种 chunk 形态，抽出工具调用并推送。

        兼容形态：
        - dict（含 actions/steps/messages/output 等键）
        - tuple/list 长度 2：(AgentAction, observation)
        - AgentAction 单对象
        """
        if chunk is None:
            return
        # tuple/list 2 元
        if isinstance(chunk, (tuple, list)) and len(chunk) == 2 and not isinstance(chunk[0], (str, bytes)):
            action_info = self._extract_action_info(chunk[0])
            if action_info:
                self._emit_tool_call(action_info['tool'], action_info.get('tool_input'), chunk[1])
            return
        # dict（LangGraph astream 输出常见）
        if isinstance(chunk, dict):
            # 1) intermediate_steps
            steps = chunk.get('steps') or chunk.get('intermediate_steps')
            if isinstance(steps, list):
                for step in steps:
                    if isinstance(step, (tuple, list)) and len(step) == 2:
                        action_info = self._extract_action_info(step[0])
                        if action_info:
                            self._emit_tool_call(action_info['tool'], action_info.get('tool_input'), step[1])
            # 2) actions（无 observation）
            actions = chunk.get('actions')
            if isinstance(actions, list):
                for act in actions:
                    action_info = self._extract_action_info(act)
                    if action_info:
                        self._emit_tool_call(action_info['tool'], action_info.get('tool_input'), None)
            return
        # 单个 AgentAction
        action_info = self._extract_action_info(chunk)
        if action_info:
            self._emit_tool_call(action_info['tool'], action_info.get('tool_input'), None)

    @staticmethod
    def _extract_final_output_from_chunk(chunk: Any) -> Optional[str]:
        """从 chunk 中提取最终输出字符串；没有就返回 None。"""
        if chunk is None:
            return None
        if isinstance(chunk, str):
            return chunk
        if isinstance(chunk, dict):
            out = chunk.get('output')
            if isinstance(out, str) and out:
                return out
        return None

    async def _load_mcp_config_node(self, state: WebUIPlaywrightAgentState) -> Dict[str, Any]:
        """1. 加载MCP配置节点。

        要求 task 层在 sync 阶段通过 ``load_user_mcp_playwright_config(user_id)``
        预加载好配置，通过 ``state["mcp_config"]`` / ``agent.mcp_config`` 传入。

        本节点 **绝不**在异步上下文里调用 Django ORM——在某些环境（Windows +
        Celery prefork + 嵌套 asyncio.run + contextvars 复制）下，
        ``sync_to_async`` 和 ``asyncio.to_thread`` 都拦不住 Django 的
        ``async_unsafe`` 检查。
        """
        self._send_node_start_notification("load_mcp_config", "加载MCP配置")

        preloaded = state.get("mcp_config") or {}
        if isinstance(preloaded, dict) and preloaded.get("mcpServers"):
            servers = list(preloaded["mcpServers"].keys())
            logger.info(f"[load_mcp_config] 使用 task 层预加载配置: {servers}")
            self._send_websocket_message(
                f"✅ 已使用预加载的 MCP 配置: {servers}\n",
                "加载MCP配置",
            )
            return {"mcp_config": preloaded, "current_step": "config_loaded"}

        logger.error(
            "[load_mcp_config] 未检测到预加载 MCP 配置。请确保 Celery task 层在 "
            "asyncio.run(agent.run(...)) 之前调用 load_user_mcp_playwright_config(user_id) "
            "并把结果赋给 agent.mcp_config。"
        )
        self._send_websocket_message(
            "❌ MCP 配置未预加载（请检查 task 入口），无法在 async 上下文里查询数据库\n",
            "加载MCP配置",
        )
        return {
            "mcp_config": {"mcpServers": {}},
            "current_step": "config_load_failed",
        }
    
    def _initialize_mcp_node(self, state: WebUIPlaywrightAgentState) -> Dict[str, Any]:
        """2. 初始化MCP客户端和智能体节点"""
        self._send_node_start_notification("initialize_mcp", "初始化MCP客户端")
        
        try:
            # 验证MCP配置
            mcp_config = state.get("mcp_config", {})
            if not mcp_config:
                raise RuntimeError("MCP配置为空")
            
            # 初始化MCP客户端
            self.mcp_client = self._initialize_mcp_client(mcp_config)
            self._send_websocket_message("MCP客户端初始化完成\n", "初始化MCP客户端")
            
            # 初始化MCP智能体（会话将在调用时按需创建）
            self.mcp_agent = self._initialize_mcp_agent(self.mcp_client)
            
            return {
                "current_step": "mcp_initialized"
            }
        except Exception as e:
            logger.error(f"初始化MCP失败: {e}")
            self._send_websocket_message(f"❌ 初始化MCP失败: {str(e)}\n", "初始化MCP客户端")
            return {
                "current_step": "mcp_init_failed"
            }
    
    # MCP 会话创建（启动 playwright 浏览器子进程 + stdio 握手）的最长等待时间。
    # 在 Windows 上首次跑 `npx @playwright/mcp@latest` 通常 5-15s；
    # 如果超过这个时间还没握手成功，几乎可以判定是握手挂死，应当主动中断报错，
    # 而不是让 Celery 任务永远转圈。
    MCP_SESSION_INIT_TIMEOUT_SECONDS = 90

    async def _ensure_mcp_sessions(self) -> bool:
        """确保MCP会话已创建（异步版本，增强错误处理 + 超时保护）。"""
        if not self.mcp_client:
            raise RuntimeError("MCP客户端未初始化")

        import time
        import platform

        start_ts = time.monotonic()
        logger.info(
            f"[mcp-session] 正在启动 playwright MCP 子进程并建立会话（最长 "
            f"{self.MCP_SESSION_INIT_TIMEOUT_SECONDS}s）..."
        )
        self._send_websocket_message(
            "🚀 正在启动 playwright 浏览器子进程并建立 MCP 会话（首次启动可能需要数十秒）...\n",
            "MCP会话创建",
        )

        try:
            await asyncio.wait_for(
                self.mcp_client.create_all_sessions(),
                timeout=self.MCP_SESSION_INIT_TIMEOUT_SECONDS,
            )
            elapsed = time.monotonic() - start_ts
            logger.info(f"[mcp-session] 会话创建成功，耗时 {elapsed:.2f}s")
            self._send_websocket_message(
                f"✅ MCP 会话已就绪（耗时 {elapsed:.1f}s）\n",
                "MCP会话创建",
            )
            return True
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_ts
            detailed = (
                f"MCP 会话创建超时（{elapsed:.1f}s）。常见原因：\n"
                f"1. 首次运行 `npx @playwright/mcp@latest` 需要联网下载，但当前网络不通；\n"
                f"2. Node.js 子进程 stdio 握手卡死（mcp_use × Windows 偶发）；\n"
                f"3. 防火墙/杀软拦截 npx 启动的 node 进程；\n"
                f"建议：终端手动执行 `npx @playwright/mcp@latest --help` 确认能秒级返回。"
            )
            logger.error(f"[mcp-session] 超时: {detailed}")
            self._send_websocket_message(f"❌ {detailed}\n", "MCP会话创建")
            # 主动取消还在跑的子进程，避免僵尸进程
            await self._cleanup_mcp_resources()
            return False
        except Exception as e:
            elapsed = time.monotonic() - start_ts
            error_msg = str(e)
            logger.error(f"[mcp-session] 创建MCP会话失败（{elapsed:.2f}s）: {error_msg}", exc_info=True)

            if platform.system() == 'Windows':
                if 'WinError 193' in error_msg or '不是有效的 Win32 应用程序' in error_msg:
                    detailed_error = (
                        "MCP命令执行失败：不是有效的Win32应用程序。\n"
                        "可能的原因：\n"
                        "1. 命令路径不正确或文件不存在\n"
                        "2. 尝试执行了非Windows可执行文件（如.sh脚本）\n"
                        "3. 架构不匹配（32位/64位）\n"
                        "4. 如果使用npx，请确保Node.js已正确安装\n"
                        f"错误详情: {error_msg}"
                    )
                    logger.error(detailed_error)
                    self._send_websocket_message(f"❌ {detailed_error}\n", "MCP会话创建")
                else:
                    self._send_websocket_message(f"❌ MCP 会话创建失败: {error_msg}\n", "MCP会话创建")
            else:
                self._send_websocket_message(f"❌ MCP 会话创建失败: {error_msg}\n", "MCP会话创建")

            return False
    
    async def _cleanup_mcp_resources(self):
        """清理MCP资源（会话和客户端）"""
        try:
            if self.mcp_client:
                await self.mcp_client.close_all_sessions()
                logger.debug("MCP会话已关闭")
        except Exception as e:
            logger.warning(f"清理MCP资源时出错: {e}")
        finally:
            self.mcp_client = None
            self.mcp_agent = None
    
    # ============================================================
    # Prompt Builders
    # ------------------------------------------------------------
    # 两条产品线（AI 实验室探索 / 业务用例回归）的提示词诉求差别较大，
    # 拆成两个 builder 维护，更易演进。
    # ============================================================

    _COMMON_CODE_SPEC = """\
【代码编写规范】
1. 必须使用 `from playwright.async_api import async_playwright, expect`（文件头部强制导入）。
2. 使用 `pytest` 风格编写，测试函数定义为 `def test_xxx(page: Page):`，函数名需体现用户需求语义。
3. 只能使用 pytest fixture 提供的 `page`，禁止在代码内部使用 `with sync_playwright()`。
4. 优先使用 Playwright 稳定选择器（`get_by_role`, `get_by_label`, `get_by_placeholder`, `get_by_text` 等），selector 内容必须来源于你实地拿到的 snapshot。
5. 测试脚本必须包含至少一个断言（断言以下方"断言 DSL"规范输出，禁止在 Python 里直接写 expect）。
6. 必须使用相对路径访问页面，例如 `page.goto("/")`，以便支持外部传入的 base_url。
7. 脚本必须为完整、可直接运行的 Python 代码，严禁包含任何解释、说明文字或 Markdown 格式标记。
8. 严禁包含注释或未使用的 import。

【操作类型严格区分 - 必须遵守】
- 输入类操作（fill/输入）：需要传入文本参数，如 `page.get_by_placeholder("手机号").fill("13800138000")`。
- 点击/无参类操作（click、访问网站、导航等）：绝对不允许传递或定义任何参数。调用时仅 `page.get_by_role("button").click()`，禁止写成 `click(text="")` 或给无参方法定义 text 参数。
- 若定义 Fallback 类或降级处理方法，点击按钮、访问链接等无参操作的方法签名为 `def method(self):`，严禁 `def method(self, text):`。

【起步导航规范 - 显式化 - 必须遵守】
- 在 run(page) 或 test_xxx(page) 函数内部的第一行，必须显式生成 `await page.goto("/")`。
- 目的：即便底层有 BaseURL 注入，也必须在脚本中让用户看到起步动作。
- 绝对禁止在脚本中硬编码完整域名（如 http://...）。基地址(Base URL) 由 BrowserContext 统一管理。
"""

    # 注意：以下两个常量是**普通字符串**，不是 fstring。
    # 因此 JSON 示例里的花括号写**单**花括号 `{` `}` 就够了，
    # 双花括号 `{{` `}}` 只在外层 fstring (`_build_xxx_prompt`) 自身需要转义时才用。
    _COMMON_ASSERTION_SPEC = """\
【智能断言规范 - 死命令 - 必须遵守 - DSL 模式】
- 你的 Python 脚本里【严禁】直接写 `await expect(...)`、`expect.soft(...)`、`page.wait_for_response` 等断言代码。
- 断言必须以「结构化 JSON」形式输出，由系统统一的翻译器生成 Playwright 代码（保证软断言 + Allure step + 失败截图）。
- 在 Python 代码块之后，紧跟一段 `<aits_assertions>...</aits_assertions>` 围栏，内部用 ```json ... ``` 放置断言数组。
- 断言数组每条结构：
  {
    "type": "text_visible|text_equals|text_contains|text_not_exists|url_equals|url_matches|element_visible|element_hidden|element_enabled|element_disabled|attribute_equals|count_equals|count_at_least|network_response|vision_assert",
    "locator": {"by": "text|css|role|test_id|xpath", "value": "..."},
    "expected": "...",
    "timeout_ms": 5000,
    "soft": true,
    "description": "中文步骤描述，将显示在 Allure 报告里"
  }
- vision_assert 只在 DOM 难以表达（如『右上角显示用户头像和昵称』）时才用，且单脚本不要超过 2 条。
- 数量：1~5 条用例级断言，按需简洁，断言依据应来自你实地观察到的页面状态。
"""

    _COMMON_OUTPUT_EXAMPLE = """\
【最终输出形态（参考）】
```python
async def run(page):
    await page.goto("/")
    # ... 业务操作（selector 必须来自上面 browser_snapshot 真实拿到的元素）...
```
<aits_assertions>
```json
[
  {"type": "url_matches", "expected": "/result", "soft": true, "description": "搜索后应跳转到结果页"}
]
```
</aits_assertions>

【最重要提醒】
- 工具调用本身不需要在最终回答里描述，系统会自动展示。你只需要确保**最终回答**里有 Python 代码块和 aits_assertions 围栏。
- 不要把整段思考过程写进最终回答；最终回答里只放完整脚本 + 断言围栏。
"""

    def _build_exploratory_prompt(self, description: str, target_url: str) -> str:
        """AI 实验室 - 探索模式 prompt。

        特征：
        - 没有 POM 上下文（任意站点）；
        - 工具调用预算严格收紧（≤ 8 次）+ 显式停止条件，防止 LLM 漫游；
        - 强调"一次 snapshot 看清就动手"，杜绝反复看页面；
        - 明确 mcp-playwright 工具 target 参数的合法格式（ref / CSS selector），
          否则 LLM 会传 `[ref=e36]` 这种非法值导致死循环。
        """
        return f"""\
你是一名资深的 Web 自动化测试工程师，正在做**探索性测试**。你手上有一套连接到目标站点的 Playwright 浏览器工具集
（browser_navigate / browser_snapshot / browser_click / browser_type / browser_fill / browser_select_option / browser_press_key / browser_take_screenshot 等）。

【目标 URL】: {target_url}
【用户需求】: {description}

【最重要约束 - 工具调用预算】
- 整个任务**总工具调用次数 ≤ 8 次**。请像"成本"一样珍惜每一次调用。
- 其中**观察类工具**（browser_snapshot / browser_take_screenshot / browser_evaluate / browser_run_code_unsafe / browser_console_messages / browser_network_requests）合计 **≤ 3 次**。
- 剩余预算留给真正的交互（click / type / fill / select / press_key）。

【@playwright/mcp 工具参数规范 - 务必看清楚再调用】
1) `browser_navigate`: 只需 `url` 字段。
2) `browser_snapshot`: 不带任何参数即可（`{{}}`）。返回页面的无障碍树。
3) **`browser_click` / `browser_type` / `browser_hover` / `browser_select_option`** 等交互工具：
   - 关键参数是 **`target`（必填）**：可以是以下两种形式之一
     a. **snapshot 拿到的 ref 标识**（推荐，可绕过 visibility 反爬）。
        snapshot 输出里每个交互元素都带形如 `[ref=e36]` 的标记，**调用时 `target` 直接填裸 ref**：
        ✅ 正确：`{{"target": "e36", "text": "柠檬班"}}`
        ❌ 错误：`{{"target": "[ref=e36]", ...}}` / `{{"target": "ref=e36", ...}}` / `{{"target": "#ref=e36", ...}}`
     b. **唯一的 CSS selector**，例如 `"#kw"`、`"input[name='wd']"`、`"button.submit"`。
        ⚠️ 不要写 ARIA 角色描述如 `'textbox "xxx"'`，那不是合法 CSS。
   - `element` 字段是可选的，仅用于人类可读描述（不影响定位），可以省略。
   - `browser_type` 还需要 `text`（要输入的文字）；如果输完想直接回车搜索，加 `"submit": true`。
   - **优先使用 ref**：如果 snapshot 给了元素的 ref，永远用 ref 而不是 CSS selector，
     因为 ref 会跳过 visibility 检查（部分站点反爬会把交互元素的 visibility 隐藏掉）。

【强制工作流 - 严格按顺序执行】
第 1 步【打开页面】
- 调用 `browser_navigate` 一次，传 `url = "{target_url}"`。

第 2 步【拿一次快照，看清页面】
- 调用 `browser_snapshot` **一次**（`{{}}`）。仔细阅读返回的无障碍树，**圈出你需要交互的每个元素的 ref**（形如 `e36`）。
- ⚠️ 一次 snapshot 已经够你定位常规交互元素。**严禁**在同一页面状态下重复 snapshot / screenshot / evaluate / run_code_unsafe 来"再确认一下"。
- 如果一次 snapshot 里没找到目标元素，那一定是因为该元素在某次交互之后才出现 —— 直接进第 3 步，而不是反复看。

第 3 步【按用户需求动手交互】
- 把用户需求拆成动词序列（如"输入 XXX、点击 YYY"），**依次**用 `browser_type` / `browser_click` / `browser_select_option` / `browser_press_key` 执行。
- **每次调用 `target` 都用第 2 步 snapshot 里那个元素的 ref**（裸 eXX，不带方括号也不带 `ref=` 前缀）。
- 每个动作只调一次；只有当上一步交互之后页面 DOM 显著变化（跳转、弹窗、新区域）且你需要新元素时，才**额外**追加 1 次 `browser_snapshot`。
- ⚠️ **严禁**用 `browser_run_code_unsafe` 或 `browser_evaluate` 跑自定义 JS 来"代替"正常的 click/type，也严禁用它们做"额外探索"。

第 4 步【输出最终脚本】
- 完成用户需求里的全部交互动词后，**立刻停止调用工具**，输出 Playwright Python 脚本 + 断言 DSL。
- 典型登录流（点「我的订单」→ 弹窗 → 填账号密码 → 点登录）：**点击登录按钮后禁止再 browser_snapshot**，
  登录成功即视为目标达成，下一回合必须直接输出脚本，不要「再确认一下页面」。

【何时必须停止 - 不可违背】
- 一旦你已经走完用户需求里描述的最后一个动作 → 立刻停止调用工具，直接输出脚本。
- **最后一个动作执行成功后，禁止追加任何观察类工具**（多余 snapshot 会耗尽图节点预算导致任务失败）。
- 如果你最近连续 2 次调用都是观察类工具（snapshot/screenshot/evaluate/run_code）且没有任何 click/type 进展，说明你迷路了 → 立刻基于现有快照信息输出脚本，**不要继续看**。
- 如果同一个交互工具连续 2 次失败（schema 错 / 选择器找不到元素 / not visible 等）→ **立刻停止调用工具，基于 snapshot 看到的 DOM 结构直接编写 Python 脚本**。脚本里用稳定的 Playwright selector（`get_by_role`、`get_by_placeholder` 等），让用户在自己环境里重跑时去解决可见性问题，不要在探索阶段死磕。
- 接近预算上限时（已用 6 次以上），即使没完美探索，也必须基于现有信息输出脚本，禁止继续探索。

{self._COMMON_CODE_SPEC}
{self._COMMON_ASSERTION_SPEC}
{self._COMMON_OUTPUT_EXAMPLE}
"""

    def _build_regression_prompt(self, description: str, target_url: str, elements_context: str) -> str:
        """业务用例回归模式 prompt。

        特征：
        - POM 强约束：标准元素库优先，禁止 LLM 脑补选择器；
        - 探索预算稍宽（业务用例可能比较长，需要多走几步）；
        - 用户需求文本通常是结构化用例（标题/步骤/预期），LLM 不用大量探索。
        """
        return f"""\
你是一名资深的 Web 自动化测试工程师，正在为一条已有的业务用例生成稳定的回归脚本。你手上有一套连接到目标站点的 Playwright 浏览器工具集
（browser_navigate / browser_snapshot / browser_click / browser_type / browser_fill / browser_select_option / browser_press_key / browser_take_screenshot 等）。

【目标 URL】: {target_url}
【业务用例（已结构化）】:
{description}

【强制工作流 - 必须严格按顺序执行】
你不可以凭空臆测页面内容；必须先真实地探索过页面，再写脚本。**总工具调用次数预算：≤ 15 次**。

第 1 步【打开页面】
- 调用 `browser_navigate`，传入参数 `url = "{target_url}"`。

第 2 步【拿一次快照】
- 调用 `browser_snapshot` 一次，得到当前页面的无障碍树。阅读其中的 ref / role / name / placeholder。
- ⚠️ 严禁同一页面反复 snapshot/screenshot/run_code 收集"更多信息"——一次 snapshot 已经足够。

第 3 步【按业务步骤交互】
- 按用例里的步骤列表，**依次**调用 `browser_click` / `browser_type` / `browser_fill` / `browser_select_option` / `browser_press_key`。
- 仅当某次交互后页面 DOM 显著变化、且下一步需要新元素时，才**额外**追加 1 次 `browser_snapshot`。

第 4 步【输出脚本】
- 走完用例的所有步骤后，立刻停止调用工具，输出 Python 脚本 + 断言 DSL。

【核心准则：标准元素库 (POM) 优先 - 死命令】
在生成脚本时，**必须优先使用**以下已定义的标准元素定位器。如果库中存在匹配业务语义的元素，**严禁自行"脑补"其他选择器**：
{elements_context}

【POM 职责分离 - 必须遵守】
- POM 类的方法仅负责元素操作（点击、输入、选择、悬停），不负责页面跳转。
- 所有的页面跳转（goto）必须由 run(page) 主动发起，严禁在 POM 方法内部调用 page.goto。

{self._COMMON_CODE_SPEC}
- 若标准元素库中不存在所需元素，请遵循 Playwright 最佳实践，优先使用稳定选择器，且 selector 内容必须来源于第 2/3 步真实拿到的快照。

{self._COMMON_ASSERTION_SPEC}
{self._COMMON_OUTPUT_EXAMPLE}
"""

    async def _call_mcp_node(self, state: WebUIPlaywrightAgentState) -> Dict[str, Any]:
        """4. 调用MCP节点生成Playwright Python测试脚本"""
        self._send_node_start_notification("call_mcp", "调用MCP执行并生成Playwright Python脚本")
        
        try:
            if not self.mcp_agent:
                raise RuntimeError("MCP智能体未初始化")
            
            # 构建用户需求描述
            description = state['description']
            target_url = state['url']

            # ============================================================
            # 模式判定：业务用例回归（test_case_id 存在）vs AI 实验室探索
            # ------------------------------------------------------------
            # 两条产品线的提示词诉求是完全不同的：
            #
            # 1) 业务用例回归 (is_exploratory=False)
            #    - 目标：基于已有用例 + 标准 POM 元素库，产出稳定、可维护的回归脚本。
            #    - POM 是【强约束】：库内有的元素必须复用，禁止 LLM 脑补。
            #    - 用户需求文本是结构化的步骤/预期结果，LLM 通常无需大量探索。
            #
            # 2) AI 实验室探索 (is_exploratory=True)
            #    - 目标：用户给一个任意 URL + 自然语言描述，LLM 自主探索、产出原型脚本。
            #    - 不应注入项目 POM：因为目标站点可能跟项目 POM 描述的业务毫无关系
            #      （例：项目 POM 是电商页面，但 URL 是 baidu.com）。把无关 POM 塞进去
            #      会导致 LLM 反复 snapshot 想"找匹配"，陷入死循环（Recursion limit）。
            #    - 必须有严格的工具调用预算 + 明确的停止条件，避免 LLM 漫游。
            #
            # 判定方式：业务用例分支会在 task 层显式 `agent.test_case_id = ...`
            # 实验室分支没有这个属性。
            # ============================================================
            is_exploratory = not bool(getattr(self, 'test_case_id', None))

            elements_context = EMPTY_POM_CONTEXT_TEXT
            if not is_exploratory:
                if isinstance(self.preloaded_pom_context, str) and self.preloaded_pom_context:
                    elements_context = self.preloaded_pom_context
                    logger.info(
                        f"[pom] 业务用例回归模式：注入预加载 POM 上下文 {len(elements_context)} 字符"
                    )
                elif state.get("project_id"):
                    logger.warning(
                        "[pom] 业务用例回归模式但未检测到 preloaded_pom_context，"
                        "可能项目 POM 为空或 task 层未调 load_project_pom_context()。"
                    )
            else:
                logger.info("[pom] AI 实验室探索模式：不注入项目 POM，让 LLM 完全自主探索")

            if is_exploratory:
                mcp_prompt = self._build_exploratory_prompt(description, target_url)
            else:
                mcp_prompt = self._build_regression_prompt(description, target_url, elements_context)

            # 发送开始生成的消息
            self._send_websocket_message(f"用户需求: {description}\n", "MCP智能体生成")
            self._send_websocket_message(f"目标URL: {target_url}\n", "MCP智能体生成")
            
            # 调用MCP智能体生成脚本（异步调用）
            try:
                raw_output = await self._call_mcp_agent_async(mcp_prompt)
            except ExplorationPartialComplete:
                raw_output = await self._synthesize_script_from_exploration(
                    description, target_url,
                )
            except RuntimeError as e:
                # 如果是取消异常，返回明确的取消状态
                if "任务已被取消" in str(e):
                    self._send_websocket_message("⛔ 任务已被取消，已终止脚本生成\n", "MCP智能体生成")
                    return {
                        "current_step": "cancelled",
                        "test_script": None,
                        "cancelled": True
                    }
                # 其他RuntimeError继续抛出
                raise
            
            if not raw_output:
                logger.error("MCP生成脚本失败: 返回空内容")
                # 发送失败消息
                self._send_websocket_message("❌ MCP生成脚本失败: 返回空内容\n", "MCP智能体生成")
                return {
                    "current_step": "script_generation_failed",
                    "test_script": None
                }
            
            # 从MCP输出中提取Python脚本
            script = extract_python_from_output(raw_output)

            if script:
                script = _enforce_script_guarantees(script)

            if not script:
                logger.warning("从MCP输出中提取Playwright Python脚本失败")
                # 发送失败消息
                self._send_websocket_message("❌ 从MCP输出中提取Playwright Python脚本失败\n", "MCP智能体生成")
                return {
                    "current_step": "script_generation_failed",
                    "test_script": None
                }

            # 【DSL 模式】抽取 LLM 给的结构化断言并经统一翻译器追加；脚本里若仍有 await expect 则一律剔除
            llm_assertions_raw = _extract_llm_assertions(raw_output)
            if llm_assertions_raw:
                # 先把 LLM 误写在 run(page) 里的硬断言抹掉，再追加结构化版本，保证只走一条路
                script = _strip_inline_expects(script)
                script = _inject_translated_assertions(script, llm_assertions_raw)
                self._send_websocket_message(
                    f"🧪 已从 LLM 输出抽取 {len(llm_assertions_raw)} 条结构化断言并经统一翻译器拼接\n",
                    "MCP智能体生成",
                )

            # 发送脚本生成完成的消息
            self._send_websocket_message("🎉 脚本生成完成！\n", "MCP智能体生成")

            return {
                "test_script": script,
                "llm_assertions": llm_assertions_raw,
                "current_step": "script_generated"
            }
        except RuntimeError as e:
            if "任务已被取消" in str(e):
                self._send_websocket_message("⛔ 任务已被取消，已终止脚本生成\n", "MCP智能体生成")
                return {"current_step": "cancelled", "test_script": None, "cancelled": True}
            raise
        except Exception as e:
            logger.error(f"MCP生成Playwright Python测试脚本失败: {e}")
            self._send_websocket_message(f"❌ MCP生成Playwright Python测试脚本失败: {str(e)}\n", "MCP智能体生成")
            return {"current_step": "script_generation_failed", "test_script": None}
    
    @staticmethod
    def _is_graph_recursion_error(exc: BaseException) -> bool:
        name = type(exc).__name__
        if name in ('GraphRecursionError', 'RecursionError'):
            return True
        msg = str(exc)
        return 'Recursion limit' in msg or 'GRAPH_RECURSION_LIMIT' in msg

    @staticmethod
    def _is_retryable_mcp_connection_error(exc: BaseException) -> bool:
        """仅连接/会话类瞬时错误才值得重开浏览器；递归上限、业务失败不重试。"""
        if WebUIPlaywrightAgent._is_graph_recursion_error(exc):
            return False
        msg = str(exc).lower()
        keywords = (
            'connection', 'connect', 'session', 'timeout', 'timed out',
            'stdio', 'broken pipe', 'mcp会话', 'handshake', 'econnrefused',
        )
        return any(k in msg for k in keywords)

    def _has_sufficient_exploration_progress(self) -> bool:
        """判断是否已记录足够多的真实浏览器操作，可跳过「重开浏览器再探一遍」。"""
        actions = list(getattr(self, '_exploration_agent_actions', []) or [])
        if len(actions) >= 5:
            return True
        tool_names = {a.get('tool_name') for a in actions}
        interactive = tool_names & {
            'browser_click', 'browser_type', 'browser_fill_form',
            'browser_press_key', 'browser_select_option',
        }
        return 'browser_navigate' in tool_names and len(interactive) >= 2

    async def _synthesize_script_from_exploration(
        self, description: str, target_url: str,
    ) -> str:
        """探索已在浏览器里走完，但 MCP 图未正常收尾时，用 LLM 根据回放记录合成脚本。"""
        lines = []
        for idx, act in enumerate(self._exploration_agent_actions, 1):
            lines.append(
                f"{idx}. [{act.get('tool_name')}] {act.get('display_text') or ''} "
                f"input={act.get('raw_input') or ''}"
            )
        replay_text = '\n'.join(lines) if lines else '（无工具记录）'
        system = (
            '你是 Web 自动化测试工程师。用户已在真实浏览器中完成探索，'
            '请根据「已执行操作回放」和「用户需求」直接输出 Playwright Python 脚本与断言 DSL，'
            '不要再描述探索过程，也不要要求继续调用浏览器工具。'
        )
        human = f"""【目标 URL】{target_url}
【用户需求】{description}

【已在浏览器中完成的操作回放】
{replay_text}

请输出完整可运行的 pytest 风格脚本（含 page.goto("/") 起步）及 <aits_assertions> 围栏。
{self._COMMON_CODE_SPEC}
{self._COMMON_ASSERTION_SPEC}
{self._COMMON_OUTPUT_EXAMPLE}
"""
        self._send_websocket_message(
            '⚠️ 浏览器探索步骤已足够，正在根据回放记录生成脚本（不会再次打开浏览器）...\n',
            'MCP智能体生成',
        )
        if not self.llm_manager or not self.llm_manager.current_llm:
            raise RuntimeError('LLM 未初始化，无法根据探索回放合成脚本')
        return self.llm_manager.invoke([
            SystemMessage(content=system),
            HumanMessage(content=human),
        ])

    async def _call_mcp_agent_async(self, prompt: str) -> str:
        """异步调用MCP智能体生成脚本。

        优先使用 mcp_use 的 `agent.stream(prompt)` 流式接口：
        - 每次 LLM 决定调用一次 playwright 工具，都通过 `_emit_tool_call` 推送结构化事件给前端，
          前端的 "AI 操作回放" 面板按业务化文案展示。
        - 流式接口若不可用（例如老版本 mcp_use），自动回落到 `agent.run(prompt)` 单次返回。
        """
        # 重置工具去重指纹（每次新的脚本生成是独立场景）
        self._emitted_tool_fingerprints.clear()

        # 在开始前检查是否已取消
        if self._is_cancelled():
            self._send_websocket_message("已收到停止指令，终止MCP智能体执行\n", "MCP智能体运行")
            raise RuntimeError("任务已被取消")

        max_retries = 3
        base_retry_delay = 2  # 基础重试延迟（秒）
        # 是否使用 stream 路径（动态探测，避免老版本 mcp_use 没有 stream 方法）
        has_stream = callable(getattr(self.mcp_agent, 'stream', None))

        for attempt in range(max_retries):
            # 每次重试前检查是否已取消
            if self._is_cancelled():
                self._send_websocket_message("已收到停止指令，终止MCP智能体执行\n", "MCP智能体运行")
                raise RuntimeError("任务已被取消")

            try:
                # 确保MCP会话已创建
                if not await self._ensure_mcp_sessions():
                    raise RuntimeError("MCP会话创建失败")

                # 设置日志处理器捕获MCP输出
                mcp_handler = self._setup_mcp_output_handler()

                try:
                    self._send_websocket_message("📝 MCP智能体终端输出:\n", "MCP智能体运行")

                    if has_stream:
                        result = await self._stream_mcp_agent(prompt)
                    else:
                        result = await self._run_mcp_agent_legacy(prompt)

                    self._send_websocket_message("✅ MCP智能体运行完成\n", "MCP智能体运行")
                    return result

                finally:
                    # 清理日志处理器
                    self._cleanup_mcp_output_handler(mcp_handler)

            except RuntimeError as e:
                if "任务已被取消" in str(e):
                    raise
                if self._is_graph_recursion_error(e) and self._has_sufficient_exploration_progress():
                    logger.warning(
                        'MCP 递归上限，但探索步骤已足够，转为回放合成脚本: %s', e,
                    )
                    raise ExplorationPartialComplete(str(e)) from e
                logger.error(f"运行MCP智能体失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1 and self._is_retryable_mcp_connection_error(e):
                    retry_delay = base_retry_delay * (2 ** attempt)
                    self._send_websocket_message(
                        f"⚠️ MCP 连接异常，{retry_delay}秒后重试...\n",
                        "MCP智能体运行",
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    self._send_websocket_message(
                        f"❌ MCP智能体运行失败: {str(e)}\n",
                        "MCP智能体运行",
                    )
                    raise
            except Exception as e:
                if has_stream and isinstance(e, AttributeError) and 'stream' in str(e).lower():
                    logger.warning(f"agent.stream 不可用，降级到 agent.run: {e}")
                    has_stream = False
                    continue

                if self._is_graph_recursion_error(e) and self._has_sufficient_exploration_progress():
                    logger.warning(
                        'MCP 递归上限，但探索步骤已足够，转为回放合成脚本: %s', e,
                    )
                    raise ExplorationPartialComplete(str(e)) from e

                logger.error(f"运行MCP智能体失败 (尝试 {attempt + 1}/{max_retries}): {e}")

                if attempt < max_retries - 1 and self._is_retryable_mcp_connection_error(e):
                    retry_delay = base_retry_delay * (2 ** attempt)
                    self._send_websocket_message(
                        f"⚠️ MCP 连接异常，{retry_delay}秒后重试...\n",
                        "MCP智能体运行",
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    self._send_websocket_message(
                        f"❌ MCP智能体运行失败: {str(e)}\n",
                        "MCP智能体运行",
                    )
                    raise

        raise Exception("MCP智能体运行失败，已达到最大重试次数")

    async def _stream_mcp_agent(self, prompt: str) -> str:
        """使用 agent.stream() 异步迭代，按工具事件实时回放给前端。"""
        final_text = ''
        logger.info("[mcp-stream] 正在调用 mcp_agent.stream(prompt) 建立迭代器...")
        self._send_websocket_message("🤖 正在向 LLM 发送任务指令，准备开始页面探索...\n", "MCP智能体运行")
        stream_iter = self.mcp_agent.stream(prompt)
        logger.info("[mcp-stream] 迭代器创建完成，开始消费 chunk 流...")

        async def _consume() -> str:
            collected_final = ''
            collected_text_parts = []
            chunk_idx = 0
            async for chunk in stream_iter:
                chunk_idx += 1
                # 心跳日志：方便排查"卡住到底是 LLM 在思考还是工具卡死"
                if chunk_idx == 1 or chunk_idx % 10 == 0:
                    logger.info(
                        f"[mcp-stream] 收到第 {chunk_idx} 个 chunk, type={type(chunk).__name__}"
                    )

                # 协作式取消：每个 chunk 之间检查一次
                if self._is_cancelled():
                    raise RuntimeError("任务已被取消")

                # 1) 抽取工具调用并推送 tool_call 事件
                try:
                    self._emit_tool_calls_from_chunk(chunk)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"处理 stream chunk 工具事件失败: {exc}")

                # 2) 抽取最终输出（dict 形态 output / 终态 str）
                final_piece = self._extract_final_output_from_chunk(chunk)
                if final_piece:
                    collected_final = final_piece

                # 3) 兼容 dict 里的 messages 增量字符串（部分版本会在每个 chunk 增量返回）
                if isinstance(chunk, dict):
                    msg = chunk.get('messages')
                    if isinstance(msg, str) and msg:
                        collected_text_parts.append(msg)

            logger.info(
                f"[mcp-stream] 流式消费结束，共 {chunk_idx} 个 chunk, "
                f"final_len={len(collected_final)}, text_parts={len(collected_text_parts)}"
            )

            # 优先用 final/output；没有就拼 messages 增量
            if collected_final:
                return collected_final
            if collected_text_parts:
                return ''.join(collected_text_parts)
            return ''

        consume_task = asyncio.create_task(_consume())
        cancel_task = asyncio.create_task(self._wait_cancel_signal())
        try:
            done, _ = await asyncio.wait(
                {consume_task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_task in done and self._is_cancelled():
                self._send_websocket_message("已收到停止指令，正在尝试终止当前MCP执行...\n", "MCP智能体运行")
                consume_task.cancel()
                try:
                    await consume_task
                except (asyncio.CancelledError, Exception):
                    pass
                raise RuntimeError("任务已被取消")

            cancel_task.cancel()
            try:
                await cancel_task
            except asyncio.CancelledError:
                pass

            final_text = await consume_task
        finally:
            # 关闭底层异步迭代器，释放生成器资源
            aclose = getattr(stream_iter, 'aclose', None)
            if callable(aclose):
                try:
                    await aclose()
                except Exception:  # noqa: BLE001
                    pass

        return final_text

    async def _run_mcp_agent_legacy(self, prompt: str) -> str:
        """fallback：老版本 mcp_use 没有 stream 接口时，使用 agent.run。"""
        run_task = asyncio.create_task(self.mcp_agent.run(prompt))
        cancel_task = asyncio.create_task(self._wait_cancel_signal())

        done, _ = await asyncio.wait(
            {run_task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED
        )

        if cancel_task in done and self._is_cancelled():
            self._send_websocket_message("已收到停止指令，正在尝试终止当前MCP执行...\n", "MCP智能体运行")
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass
            raise RuntimeError("任务已被取消")

        cancel_task.cancel()
        try:
            await cancel_task
        except asyncio.CancelledError:
            pass

        return await run_task
    
    def _setup_mcp_output_handler(self):
        """设置MCP输出日志处理器（INFO/WARN/ERROR均捕获，避免重复挂载）"""
        import logging
        
        class MCPOutputHandler(logging.Handler):
            def __init__(self, agent_instance):
                super().__init__()
                self.agent = agent_instance
            
            def emit(self, record):
                try:
                    message = self.format(record)
                    self.agent._process_and_send_mcp_output(message, record.levelno)
                except Exception as e:
                    # 避免handler异常导致日志系统递归
                    logger.warning(f"MCP日志处理器异常: {e}")
        
        mcp_logger = logging.getLogger('mcp_use')

        # 如果已经挂了handler，直接复用，避免重复输出
        if self._mcp_log_handler and self._mcp_log_handler in mcp_logger.handlers:
            return self._mcp_log_handler

        handler = MCPOutputHandler(self)
        handler.setLevel(logging.INFO)  # 过滤DEBUG，减少噪音（需要DEBUG可改为DEBUG）
        handler.setFormatter(logging.Formatter("%(message)s"))
        mcp_logger.addHandler(handler)
        self._mcp_log_handler = handler
        return handler
    
    def _cleanup_mcp_output_handler(self, handler):
        """清理MCP输出日志处理器"""
        import logging
        mcp_logger = logging.getLogger('mcp_use')
        try:
            if handler and handler in mcp_logger.handlers:
                mcp_logger.removeHandler(handler)
        finally:
            if handler == self._mcp_log_handler:
                self._mcp_log_handler = None
    

    
    def _decide_after_config_load(self, state: WebUIPlaywrightAgentState) -> str:
        """配置加载后的决策"""
        if state.get("current_step") == "config_loaded":
            return "initialize_mcp"
        elif state.get("current_step") == "config_load_failed":
            return "__end__"
        else:
            return "__end__"
    
    def _decide_after_mcp_init(self, state: WebUIPlaywrightAgentState) -> str:
        """MCP初始化后的决策：当前Agent仅用于AI实验室，直接走自由探索节点"""
        if state.get("current_step") != "mcp_initialized":
            return "__end__"
        return "call_mcp"
    
    def _decide_after_mcp_call(self, state: WebUIPlaywrightAgentState) -> str:
        """MCP调用后的决策"""
        # 如果已取消，直接结束
        if state.get("current_step") == "cancelled" or state.get("cancelled"):
            return "__end__"
        if state.get("current_step") == "script_generated" and state.get("test_script"):
            return "save_script"
        else:
            return "__end__"
    
    
    
    async def _save_script_node(self, state: WebUIPlaywrightAgentState) -> WebUIPlaywrightAgentState:
        """收尾节点：准备好需要持久化的数据，由 task 层在 sync 上下文真正写库。

        ⚠️ 重要：本方法跑在 LangGraph ainvoke 的 async 事件循环里。在某些环境下
        （Windows + Celery prefork + 嵌套 asyncio.run + contextvars 复制），无论
        ``sync_to_async`` 还是 ``asyncio.to_thread`` 都拦不住 Django 的
        ``async_unsafe`` 检查。因此本节点 **绝不直接调用 Django ORM**，仅把脚本和
        要写入的字段塞进 ``self.pending_persistence``，由
        ``_execute_webui_script_generation`` / ``_execute_webui_script_generation_from_testcase``
        在 task 主线程（纯 sync）阶段统一持久化。
        """
        # 发送节点开始通知
        self._send_node_start_notification("save_script", "保存脚本到数据库")

        try:
            python_script = state.get("test_script")
            user_id = state.get("user_id")
            test_case_id = state.get("test_case_id")

            if not python_script:
                logger.warning("没有Python脚本内容需要保存")
                return {
                    **state,
                    "current_step": "save_failed"
                }

            if test_case_id:
                # 选择测试用例方式：把要写入的数据装进 pending_persistence，
                # 由 task 层 sync 阶段写 WebUITestCase。
                self._send_websocket_message("💾 已生成 Python 脚本，准备回写到测试用例...\n", "脚本保存")

                # 准备断言 expectations（纯内存计算，不涉及 ORM）
                llm_assertions = state.get('llm_assertions') or []
                cleaned_expectations = []
                if llm_assertions:
                    try:
                        from apps.web_testing.assertion_schema import validate_assertions, dump_assertion
                        cleaned_expectations = [dump_assertion(s) for s in validate_assertions(llm_assertions)]
                    except Exception as _e:
                        logger.warning(f"准备 expectations 失败: {_e}")
                        cleaned_expectations = []

                self.pending_persistence = {
                    "kind": "test_case",
                    "user_id": user_id,
                    "test_case_id": test_case_id,
                    "script": python_script,
                    "expectations": cleaned_expectations,
                }
                logger.info(
                    f"[save_script] 已准备 pending_persistence (test_case_id={test_case_id}, "
                    f"script_len={len(python_script)}, expectations_len={len(cleaned_expectations)})"
                )

                # 发送任务完成通知
                self._send_task_completed_notification(state)

                return {
                    **state,
                    "test_case_id": test_case_id,
                    "current_step": "saved"
                }
            else:
                # 手动填写方式：不需要持久化到数据库，前端拿 test_script 即可
                self._send_task_completed_notification(state)
                return {
                    **state,
                    "current_step": "saved"
                }

        except Exception as e:
            logger.error(f"准备脚本保存失败: {e}", exc_info=True)
            self._send_websocket_message(f"❌ 准备脚本保存失败: {str(e)}\n", "脚本保存")
            return {
                **state,
                "current_step": "save_failed"
            }
    
    

    async def run(self, description: str, url: str = "") -> Dict[str, Any]:
        """运行WebUI测试脚本生成智能体"""
        try:
            if not self.workflow:
                raise RuntimeError("LangGraph工作流未初始化，无法运行WebUI测试脚本生成智能体")
            return await self._run_with_langgraph(description, url)
                
        except RuntimeError as e:
            # 如果是取消异常，返回明确的取消状态
            if "任务已被取消" in str(e):
                return {
                    "success": False,
                    "cancelled": True,
                    "error": "任务已被取消",
                    "current_step": "cancelled",
                    "exploration_artifacts": self.get_exploration_artifacts(),
                }
            # 其他RuntimeError继续抛出
            raise
        except Exception as e:
            error_msg = f"运行WebUI测试脚本生成智能体失败: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "current_step": "failed",
                "exploration_artifacts": self.get_exploration_artifacts(),
            }
        finally:
            # 清理MCP资源
            await self._cleanup_mcp_resources()
    
    async def _run_with_langgraph(self, description: str, url: str) -> Dict[str, Any]:
        """使用LangGraph工作流运行"""
        self._reset_exploration_buffers()
        initial_state = {
            "description": description,
            "url": url,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "script_name": self.script_name,
            "mcp_config": self.mcp_config,
            "test_script": None,
            "script_id": None,
            "current_step": "initialized"
        }
        result = await self.workflow.ainvoke(initial_state)
        
        # 检查是否是因为取消
        artifacts = self.get_exploration_artifacts()
        if result.get("current_step") == "cancelled" or result.get("cancelled"):
            return {
                "success": False,
                "cancelled": True,
                "error": "任务已被取消",
                "current_step": "cancelled",
                "exploration_artifacts": artifacts,
            }
        
        # 检查是否有错误
        if not result.get("test_script"):
            return {
                "success": False,
                "error": "测试脚本生成失败",
                "current_step": result.get("current_step", "unknown"),
                "exploration_artifacts": artifacts,
            }
        
        # 返回成功结果。pending_persistence 是要 task 层在 sync 上下文里写库的数据，
        # async 节点不直接动 ORM（参见 _save_script_node 顶部说明）。
        return {
            "success": True,
            "test_script": result.get("test_script"),
            "script_id": result.get("script_id"),
            "model_info": self.llm_manager.get_model_info(),
            "model_type": "llm",
            "current_step": result.get("current_step", "completed"),
            "pending_persistence": self.pending_persistence,
            "exploration_artifacts": artifacts,
        }




def create_webui_playwright_agent(user, user_id: int = None, enable_streaming: bool = True) -> WebUIPlaywrightAgent:
    """创建WebUI Playwright智能体实例"""
    return WebUIPlaywrightAgent(user, user_id, enable_streaming)

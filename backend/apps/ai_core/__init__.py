# AI Core app package
#
# ⚠️ 重要：在 ai_core 任何子模块被 import 之前，先关闭 mcp_use 的匿名遥测。
# mcp_use 的 telemetry 模块在初始化时会创建 PostHog 客户端（连接
# https://eu.i.posthog.com），如果用户开了 VPN 且 VPN 出站规则把该域名
# 黑洞了，TCP connect 会卡到 Windows 系统级 socket 超时（75s+），期间
# 整个 celery 主进程的 GIL 被 socket connect 持有，所有 Python 代码都
# 进不去，整个 worker 看似"卡死数分钟无任何日志"。
#
# 必须放在所有 import 之前，且无条件设置（setdefault 优先尊重用户已设的值）。
import os as _os_for_telemetry_disable

_os_for_telemetry_disable.environ.setdefault('MCP_USE_ANONYMIZED_TELEMETRY', 'false')
_os_for_telemetry_disable.environ.setdefault('ANONYMIZED_TELEMETRY', 'false')
_os_for_telemetry_disable.environ.setdefault('DO_NOT_TRACK', '1')

del _os_for_telemetry_disable

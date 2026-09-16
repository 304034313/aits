from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

from django.conf import settings

_IPV4_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")

# 虚拟/隧道网卡常见关键字（应优先真实以太网/Wi-Fi）
_VIRTUAL_ADAPTER_HINTS = (
    "unknown",
    "未知",
    "tun",
    "wintun",
    "clash",
    "sing-box",
    "tap",
    "vpn",
    "loopback",
    "回环",
    "vmware",
    "hyper-v",
    "vethernet",
    "virtual",
    "虚拟",
    "docker",
    "wsl",
    "meta",
    "ppp",
)

_PREFERRED_ADAPTER_HINTS = (
    "ethernet",
    "以太网",
    "wlan",
    "wi-fi",
    "无线",
    "local area connection ii",
)


DEFAULT_MONITOR_HOST = "localhost"


def normalize_monitor_host(host: str | None) -> str:
    """统一本机访问主机名；URL 展示用 localhost，Prometheus scrape 用 127.0.0.1。"""
    h = (host or "").strip().split(":")[0].strip()
    if not h:
        return DEFAULT_MONITOR_HOST
    if h.lower() in ("localhost", "127.0.0.1", "::1"):
        return DEFAULT_MONITOR_HOST
    return h


def monitor_host_for_scrape(host: str | None) -> str:
    """Prometheus / windows_exporter 目标地址（localhost 场景用环回 IP）。"""
    normalized = normalize_monitor_host(host)
    if normalized == DEFAULT_MONITOR_HOST:
        return "127.0.0.1"
    return normalized


def _env_monitor_host() -> str | None:
    # AITS_CLASSROOM_HOST 为历史别名，请改用 AITS_MONITOR_HOST
    for key in ("AITS_MONITOR_HOST", "AITS_CLASSROOM_HOST"):
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        host = raw.split(":")[0].strip()
        if host.lower() in ("localhost", "127.0.0.1", "::1"):
            return DEFAULT_MONITOR_HOST
        if _is_routable_lan_ipv4(host):
            return host
    return None


def _is_routable_lan_ipv4(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.version != 4 or addr.is_loopback or addr.is_link_local or addr.is_multicast:
        return False
    # 198.18.0.0/15 常被 TUN/代理占用，不适合作为统一访问地址
    if addr in ipaddress.ip_network("198.18.0.0/15"):
        return False
    return True


def _lan_priority(ip: str) -> int:
    """分数越高越优先。优先 192.168 / 10 / 172.16-31 私网地址。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return -100
    if addr in ipaddress.ip_network("192.168.0.0/16"):
        return 300
    if addr in ipaddress.ip_network("10.0.0.0/8"):
        return 280
    if addr in ipaddress.ip_network("172.16.0.0/12"):
        return 260
    if addr.is_private:
        return 200
    return 50


def _adapter_hint_score(name: str) -> int:
    lowered = (name or "").lower()
    if any(h in lowered for h in _VIRTUAL_ADAPTER_HINTS):
        return -200
    if any(h in lowered for h in _PREFERRED_ADAPTER_HINTS):
        return 120
    return 0


def _collect_ipv4_from_hostname() -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM):
            ip = info[4][0]
            if _is_routable_lan_ipv4(ip):
                out.append((ip, _lan_priority(ip)))
    except OSError:
        pass
    return out


def _collect_ipv4_from_ipconfig() -> list[tuple[str, int]]:
    """Windows: 解析 ipconfig，优先以太网/Wi-Fi 上的 IPv4。"""
    if not sys.platform.startswith("win"):
        return []
    try:
        proc = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=8,
            check=False,
        )
        text = proc.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return []

    current_adapter = ""
    results: list[tuple[str, int]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ("adapter" in line.lower()) or ("适配器" in line):
            current_adapter = line.rstrip(":")
            continue
        if ("IPv4" in line) or ("IP Address" in line) or ("IP 地址" in line):
            match = _IPV4_RE.search(line)
            if not match:
                continue
            ip = match.group(1)
            if not _is_routable_lan_ipv4(ip):
                continue
            score = _lan_priority(ip) + _adapter_hint_score(current_adapter)
            results.append((ip, score))
    return results


def _detect_ipv4_by_default_route() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()
    if _is_routable_lan_ipv4(ip):
        return ip
    return None


def detect_monitor_host_ip() -> str:
    """
    监控栈对外访问主机名（Grafana/Prometheus/AITS iframe 共用）。

    默认 localhost（本机 Grafana/Prometheus 仅监听环回地址）。
    局域网内需在其他机器访问时，请设置环境变量 AITS_MONITOR_HOST=192.168.x.x。
    """
    override = _env_monitor_host()
    if override:
        return normalize_monitor_host(override)
    return DEFAULT_MONITOR_HOST


# 兼容旧调用名（已弃用）
def detect_classroom_host_ip() -> str:
    return detect_monitor_host_ip()


def _detect_lan_ipv4() -> str:
    return detect_monitor_host_ip()


def _write_prometheus_sd_target(port: int) -> Path:
    scrape_host = monitor_host_for_scrape(detect_monitor_host_ip())
    payload = [
        {
            "targets": [f"{scrape_host}:{port}"],
            "labels": {
                "instance": "AITS-Generator",
                "role": "load-generator",
            },
        }
    ]
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    target_file = Path(getattr(settings, "PROMETHEUS_SD_TARGET_FILE")).expanduser().resolve()
    target_file.parent.mkdir(parents=True, exist_ok=True)

    current = ""
    if target_file.exists():
        try:
            current = target_file.read_text(encoding="utf-8")
        except OSError:
            current = ""
    if current != content:
        target_file.write_text(content, encoding="utf-8")

    return target_file


def update_node_exporter_target() -> Path:
    """Mac/Linux：node_exporter 默认端口 9100（Docker 监控栈用 static scrape，此文件供 file_sd 选修）。"""
    return _write_prometheus_sd_target(9100)


def update_host_exporter_target() -> Path:
    if sys.platform.startswith("win"):
        return update_windows_exporter_target()
    return update_node_exporter_target()


def update_windows_exporter_target() -> Path:
    """
    生成 Prometheus file_sd_configs 目标文件。
    输出示例：
    [
      {
        "targets": ["192.168.1.10:9182"],
        "labels": {"instance":"AITS-Generator","role":"load-generator"}
      }
    ]
    """
    return _write_prometheus_sd_target(9182)

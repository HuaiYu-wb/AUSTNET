"""网络接口探测：判断有线 / 无线、读取 SSID、本机 IP 与 MAC。

只用标准库：解析 ipconfig /all 的文本输出，配合 netsh wlan 判断网卡类型。
中文和英文 Windows 的输出都能解析。
"""

from __future__ import annotations

import re
import socket
import subprocess
import urllib.parse
from dataclasses import dataclass

CREATE_NO_WINDOW = 0x08000000

_MAC_RE = re.compile(r"([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})")
_IPV4_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
_HEADER_RE = re.compile(r"^(.*?)\s*(?:适配器|adapter)\s+(.*?)\s*:\s*$", re.I)
_NOISE_RE = re.compile(r"[\s.．·、\u3000]+")


def run(args: list[str], timeout: float = 12.0) -> str:
    completed = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )
    for encoding in ("utf-8", "gb18030", "gbk", "cp1252"):
        try:
            return completed.stdout.decode(encoding)
        except UnicodeDecodeError:
            continue
    return completed.stdout.decode("utf-8", "replace")


def _normalize(head: str) -> str:
    return _NOISE_RE.sub("", head).lower()


def split_line(line: str) -> tuple[str | None, str]:
    """把 "描述. . . . : 值" 拆成 ("描述", "值")；不成立时返回 (None, "")。"""
    for separator in (":", "："):
        index = line.find(separator)
        if index > 0:
            key = _normalize(line[:index])
            return (key, line[index + 1 :].strip()) if key else (None, "")
    return None, ""


def _first_ipv4(value: str) -> str:
    match = _IPV4_RE.search(value or "")
    return match.group(1) if match else ""


def _first_mac(value: str) -> str:
    match = _MAC_RE.search(value or "")
    return match.group(1).replace("-", "").replace(":", "").upper() if match else ""


@dataclass
class Adapter:
    name: str = ""
    description: str = ""
    mac: str = ""
    ipv4: str = ""
    gateway: str = ""


def list_adapters(text: str | None = None) -> list[Adapter]:
    """逐行解析 ipconfig /all。

    适配器标题和它的字段之间隔着一个空行，所以不能按空行切块，
    只能遇到标题就开一个新适配器，后面的键值行都归它。
    """
    adapters: list[Adapter] = []
    current: Adapter | None = None
    for line in (text if text is not None else run(["ipconfig", "/all"])).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        header = _HEADER_RE.match(stripped)
        if header:
            current = Adapter(name=header.group(2).strip())
            adapters.append(current)
            continue
        if current is None:
            continue
        key, value = split_line(line)
        if not key:
            continue
        if key in ("描述", "description") and not current.description:
            current.description = value
        elif key in ("物理地址", "physicaladdress") and not current.mac:
            current.mac = _first_mac(value)
        elif key in ("ipv4地址", "ipv4address") and not current.ipv4:
            current.ipv4 = _first_ipv4(value)
        elif key in ("默认网关", "defaultgateway") and not current.gateway:
            current.gateway = _first_ipv4(value)
    return adapters


def wlan_interface(text: str | None = None) -> dict[str, str]:
    """netsh wlan show interfaces 的关键字段。"""
    info: dict[str, str] = {}
    wanted = {
        "名称": "name",
        "name": "name",
        "描述": "description",
        "description": "description",
        "状态": "state",
        "state": "state",
        "ssid": "ssid",
        "bssid": "bssid",
    }
    for line in (text if text is not None else run(["netsh", "wlan", "show", "interfaces"])).splitlines():
        key, value = split_line(line)
        field = wanted.get(key or "")
        if field and value and field not in info:
            info[field] = value
    return info


def wifi_connected() -> bool:
    state = (wlan_interface().get("state") or "").lower()
    return state in ("已连接", "connected")


def split_host_port(url: str, default_port: int = 80) -> tuple[str, int]:
    parsed = urllib.parse.urlsplit(url if "//" in url else "//" + url)
    return parsed.hostname or url, parsed.port or default_port


def default_route_ip(host: str, port: int = 80) -> str:
    """本机走默认路由到达 host 时使用的 IPv4；UDP connect 不产生真实流量。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(1.0)
        sock.connect((host, port))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


@dataclass
class Connection:
    kind: str = "none"  # wired / wifi / none
    name: str = ""
    description: str = ""
    ip: str = ""
    mac: str = ""
    gateway: str = ""
    ssid: str = ""

    @property
    def label(self) -> str:
        if self.kind == "wifi":
            return "无线 WiFi"
        if self.kind == "wired":
            return "有线"
        return "未连接"


def current_connection(host: str, port: int = 80) -> Connection:
    adapters = list_adapters()
    wlan = wlan_interface()
    ip = default_route_ip(host, port)

    chosen: Adapter | None = None
    if ip:
        chosen = next((item for item in adapters if item.ipv4 == ip), None)
    if chosen is None:
        chosen = next(
            (
                item
                for item in adapters
                if item.ipv4 and item.gateway and not item.ipv4.startswith("169.254.")
            ),
            None,
        )
    if chosen is None:
        return Connection()

    wlan_description = (wlan.get("description") or "").strip().lower()
    wlan_name = (wlan.get("name") or "").strip().lower()
    is_wifi = bool(wlan_description or wlan_name) and (
        (bool(wlan_description) and wlan_description in chosen.description.lower())
        or (bool(wlan_name) and wlan_name == chosen.name.lower())
    )
    return Connection(
        kind="wifi" if is_wifi else "wired",
        name=chosen.name,
        description=chosen.description,
        ip=chosen.ipv4,
        mac=chosen.mac,
        gateway=chosen.gateway,
        ssid=(wlan.get("ssid") or "") if is_wifi else "",
    )

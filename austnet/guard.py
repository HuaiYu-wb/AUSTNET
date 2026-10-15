"""后台守护线程：定时检查认证状态，掉线后自动重连。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from typing import Callable, Optional

from . import netinfo, portal


@dataclass
class Settings:
    portal: str = ""
    account: str = ""
    password: str = ""
    auto_reconnect: bool = True
    interval: int = 20


@dataclass
class Snapshot:
    kind: str = "none"
    ip: str = ""
    mac: str = ""
    ssid: str = ""
    connected: bool = False
    message: str = "尚未检测"


Event = Callable[[str, str], None]


class Guard:
    """一个线程 + 一个可中断的等待，避免同时跑两个守护。"""

    GRACE = 15.0

    def __init__(self, settings: Callable[[], Settings], emit: Optional[Event] = None):
        self._settings = settings
        self._emit = emit or (lambda level, message: None)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._snapshot = Snapshot()
        self._last_login = 0.0
        self._ever_connected = False
        self._failures = 0
        self._manual_logout = False

    # -- 生命周期 ---------------------------------------------------------

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="austnet-guard", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout)
        self._thread = None

    def poke(self) -> None:
        """请求立刻检查一次。"""
        self._wake.set()

    def suspend(self) -> None:
        """用户手动注销：暂停自动重连，直到用户再次要求连接。"""
        self._manual_logout = True
        self._wake.set()

    def resume(self) -> None:
        self._manual_logout = False
        self._wake.set()

    # -- 状态 -------------------------------------------------------------

    def snapshot(self) -> Snapshot:
        with self._lock:
            return replace(self._snapshot)

    def _update(self, **changes) -> None:
        with self._lock:
            self._snapshot = replace(self._snapshot, **changes)

    # -- 主循环 -----------------------------------------------------------

    def _loop(self) -> None:
        time.sleep(2.0)  # 让网卡和 DHCP 先稳定下来
        while not self._stop.is_set():
            try:
                wait = self._tick()
            except Exception as error:  # 守护线程不能因为单次异常退出
                self._emit("error", "守护线程异常：%s" % error)
                wait = 30.0
            self._wake.wait(max(1.0, wait))
            self._wake.clear()

    def _tick(self) -> float:
        settings = self._settings()
        base = (settings.portal or "").strip().rstrip("/")
        interval = max(5, int(settings.interval or 20))
        if not base:
            self._update(message=" 未配置认证服务器")
            return 10.0

        host, port = netinfo.split_host_port(base)
        connection = netinfo.current_connection(host, port)
        self._update(kind=connection.kind, ip=connection.ip, mac=connection.mac, ssid=connection.ssid)

        if connection.kind == "none":
            self._update(connected=False, message="没有检测到可用的有线或无线连接")
            return float(interval)

        state = portal.probe(base)

        if state == "online":
            self._ever_connected = True
            self._failures = 0
            self._update(connected=True, message="已认证，网络正常")
            return float(interval)

        if state == "offline":
            self._update(connected=False, message="未接入校园网，找不到认证网关")
            return float(max(interval, 30))

        if self._manual_logout:
            self._update(connected=False, message="已手动注销，自动重连已暂停")
            return float(interval)

        if not settings.account or not settings.password:
            self._update(connected=False, message="已连上校园网，等待填写账号密码")
            return float(interval)

        if not settings.auto_reconnect and self._ever_connected:
            self._update(connected=False, message="认证已掉线（自动重连已关闭）")
            return float(interval)

        if time.monotonic() - self._last_login < self.GRACE:
            return 3.0

        self._emit("info", "检测到未认证，正在自动登录…")
        ok, message = portal.login(
            base,
            settings.account,
            settings.password,
            kind=connection.kind,
            ip=connection.ip,
            mac=connection.mac,
            timeout=8.0,
        )
        if ok:
            self._last_login = time.monotonic()
            self._ever_connected = True
            self._failures = 0
            self._update(connected=True, message=message)
            self._emit("ok", "自动登录成功：%s" % message)
            return float(interval)

        self._failures += 1
        self._update(connected=False, message=message)
        self._emit("error", "自动登录失败：%s" % message)
        return float(min(180.0, interval * (2 ** min(self._failures, 3))))

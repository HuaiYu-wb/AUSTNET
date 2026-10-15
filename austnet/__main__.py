"""命令行入口：python -m austnet [--once | --selftest | --daemon | --tray]。"""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__, appconfig, autostart, netinfo, portal


def _prepare_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass


class _Tee:
    """打包成 --windowed 后没有控制台，顺手把输出留一份给弹窗。"""

    def __init__(self, stream) -> None:
        self._stream = stream
        self.text: list[str] = []

    def write(self, value: str) -> None:
        self.text.append(value)
        if self._stream is None:
            return
        try:
            self._stream.write(value)
        except Exception:
            pass

    def flush(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.flush()
        except Exception:
            pass


def _report(title: str, text: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(title, text.strip() or "（没有输出）")
        root.destroy()
    except Exception:
        pass


def _console_mode(selftest: bool) -> int:
    tee = _Tee(sys.stdout)
    original = sys.stdout
    sys.stdout = tee  # type: ignore[assignment]
    try:
        code = _selftest() if selftest else _once()
    finally:
        sys.stdout = original
    if getattr(sys, "frozen", False):
        _report("AUSTNET 诊断", "".join(tee.text))
    return code


def _selftest() -> int:
    config = appconfig.load_config()
    password = appconfig.load_password()
    host, port = netinfo.split_host_port(config.portal)
    connection = netinfo.current_connection(host, port)

    print("AUSTNET %s 自检" % __version__)
    print("  认证服务器 : %s" % config.portal)
    print(
        "  接入方式   : %s%s"
        % (connection.label, "（%s）" % connection.name if connection.name else "")
    )
    print("  本机地址   : %s" % (connection.ip or "未知"))
    print("  物理地址   : %s" % (connection.mac or "未知"))
    print("  无线网络   : %s" % (connection.ssid or "不适用"))
    account = appconfig.full_account(config.username, config.exit_suffix)
    print("  账号       : %s" % (account or "未配置"))
    print("  密码       : %s" % ("已保存" if password else "未保存"))
    print("  开机自启   : %s" % ("已开启" if autostart.is_enabled() else "未开启"))

    ok, message = portal.identify(config.portal)
    print("  门户识别   : %s" % message)
    if not ok:
        return 1
    options = portal.exit_options(config.portal)
    if options:
        print(
            "  出口候选   : %s"
            % ", ".join("%s=%s" % (name, suffix or "无后缀") for suffix, name in options)
        )
    try:
        data = portal.status(config.portal)
    except Exception as error:
        print("  认证状态   : 查询失败 %s" % error)
        return 1
    print(
        "  认证状态   : result=%s uid=%s ip=%s"
        % (
            data.get("result"),
            data.get("uid") or "—",
            data.get("v46ip") or data.get("v4ip") or "—",
        )
    )
    return 0


def _once() -> int:
    config = appconfig.load_config()
    password = appconfig.load_password()
    base = (config.portal or "").rstrip("/")
    state = portal.probe(base)
    if state == "online":
        print("已认证，无需登录")
        return 0
    if state == "offline":
        print("未接入校园网，找不到认证网关")
        return 1
    account = appconfig.full_account(config.username, config.exit_suffix)
    if not account or not password:
        print("未配置账号或密码")
        return 2
    host, port = netinfo.split_host_port(base)
    connection = netinfo.current_connection(host, port)
    ok, message = portal.login(
        base, account, password, kind=connection.kind, ip=connection.ip, mac=connection.mac
    )
    print(("成功：" if ok else "失败：") + message)
    return 0 if ok else 1


def _daemon() -> int:
    from .guard import Guard, Settings

    def settings() -> Settings:
        config = appconfig.load_config()
        return Settings(
            portal=config.portal,
            account=appconfig.full_account(config.username, config.exit_suffix),
            password=appconfig.load_password(),
            auto_reconnect=config.auto_reconnect,
            interval=config.interval,
        )

    guard = Guard(settings, lambda level, message: print("[%s] %s" % (level, message), flush=True))
    guard.start()
    print("守护模式已启动，Ctrl+C 停止")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print()
    finally:
        guard.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    _prepare_console()
    parser = argparse.ArgumentParser(description="安徽理工大学校园网自动登录客户端")
    parser.add_argument("--version", action="version", version="AUSTNET %s" % __version__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="检测并登录一次后退出")
    mode.add_argument("--selftest", action="store_true", help="只读自检，不提交账号密码")
    mode.add_argument("--daemon", action="store_true", help="命令行守护模式")
    mode.add_argument("--tray", action="store_true", help="启动后只留在系统托盘")
    args = parser.parse_args(argv)

    if args.selftest or args.once:
        return _console_mode(args.selftest)
    if args.daemon:
        return _daemon()

    from .gui import main as gui_main

    return gui_main(start_hidden=args.tray)


if __name__ == "__main__":
    raise SystemExit(main())

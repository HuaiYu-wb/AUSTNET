"""开机自启：写 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run。

只动当前用户，不需要管理员权限，注册表里也不会出现明文密码。
"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AUSTNET"


def entry_command() -> str:
    """自启要执行的命令行。"""
    if getattr(sys, "frozen", False):
        return '"%s" --tray' % sys.executable
    project_root = Path(__file__).resolve().parent.parent
    script = project_root / "austnet.pyw"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    return '"%s" "%s" --tray' % (interpreter, script)


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
        return bool(value)
    except (FileNotFoundError, OSError):
        return False


def enable() -> None:
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, entry_command())


def disable() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except (FileNotFoundError, OSError):
        pass


def apply(enabled: bool) -> None:
    if enabled:
        enable()
    else:
        disable()


def refresh() -> None:
    """程序位置变了就改写自启项。"""
    if is_enabled():
        enable()


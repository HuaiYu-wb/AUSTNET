"""配置读写与密码保护。

配置以 JSON 存放在 %LOCALAPPDATA%\\AUSTNET\\config.json，密码用 Windows
DPAPI 加密后单独存放，磁盘上不会出现明文。
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path

APP_NAME = "AUSTNET"

# 出口（运营商）预设。括号内是追加到学号后面的后缀。
EXIT_PRESETS: tuple[tuple[str, str], ...] = (
    ("@unicom", "联通"),
    ("@aust", "电信"),
    ("@cmcc", "移动"),
    ("@jzg", "教职工"),
    ("@xyw", "校园用户"),
    ("", "默认（不加后缀）"),
)

# 账号里可能已经带上的后缀，拼接前先剥掉，避免出现 name@a@b。
KNOWN_SUFFIXES: tuple[str, ...] = tuple(suffix for suffix, _ in EXIT_PRESETS) + (
    "@lt",
    "@dx",
    "@hfcmcc",
)

DEFAULT_PORTAL = "http://10.255.0.19"
DEFAULT_SSID = "AUST Student"


def data_dir() -> Path:
    """程序数据目录，安装到 Program Files 时也能写。"""
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = Path(root) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return data_dir() / "config.json"


def secret_path() -> Path:
    return data_dir() / "secret.bin"


@dataclass
class Config:
    username: str = ""
    exit_suffix: str = "@unicom"
    portal: str = DEFAULT_PORTAL
    ssid: str = DEFAULT_SSID
    interval: int = 20
    auto_reconnect: bool = True
    auto_start: bool = False
    remember_password: bool = True


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        return Config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Config()
    if not isinstance(raw, dict):
        return Config()
    config = Config()
    for name in asdict(config):
        if name in raw:
            setattr(config, name, raw[name])
    try:
        config.interval = max(5, int(config.interval))
    except (TypeError, ValueError):
        config.interval = 20
    config.auto_reconnect = bool(config.auto_reconnect)
    config.auto_start = bool(config.auto_start)
    config.remember_password = bool(config.remember_password)
    return config


def save_config(config: Config) -> None:
    payload = json.dumps(asdict(config), ensure_ascii=False, indent=2)
    config_path().write_text(payload, encoding="utf-8")


def full_account(username: str, suffix: str) -> str:
    """把学号和出口后缀拼成提交给网关的账号。"""
    name = (username or "").strip()
    lowered = name.lower()
    for known in KNOWN_SUFFIXES:
        if known and lowered.endswith(known):
            name = name[: -len(known)]
            break
    return name + (suffix or "")


# --------------------------------------------------------------------------
# Windows DPAPI
# --------------------------------------------------------------------------


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_Blob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data)) if data else ctypes.create_string_buffer(1)
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def dpapi_available() -> bool:
    return os.name == "nt" and hasattr(ctypes, "windll")


def _protect(data: bytes) -> bytes:
    blob_in, keepalive = _blob(data)
    blob_out = _Blob()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0x01, ctypes.byref(blob_out)
    )
    del keepalive
    if not ok:
        raise OSError("CryptProtectData 失败（错误码 %d）" % ctypes.GetLastError())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _unprotect(data: bytes) -> bytes:
    blob_in, keepalive = _blob(data)
    blob_out = _Blob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0x01, ctypes.byref(blob_out)
    )
    del keepalive
    if not ok:
        raise OSError("CryptUnprotectData 失败（错误码 %d）" % ctypes.GetLastError())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def save_password(password: str) -> None:
    if not password:
        clear_password()
        return
    if not dpapi_available():
        raise RuntimeError("密码保护依赖 Windows DPAPI，当前系统不支持")
    secret_path().write_bytes(base64.b64encode(_protect(password.encode("utf-8"))))


def load_password() -> str:
    path = secret_path()
    if not path.exists() or not dpapi_available():
        return ""
    try:
        return _unprotect(base64.b64decode(path.read_bytes())).decode("utf-8")
    except (OSError, ValueError, UnicodeDecodeError):
        return ""


def clear_password() -> None:
    try:
        secret_path().unlink()
    except (FileNotFoundError, OSError):
        pass

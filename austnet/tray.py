"""Windows 系统托盘图标。

用 ctypes 直接调用 Shell_NotifyIcon，不需要 pystray。托盘窗口和消息循环跑在
自己的线程里，菜单动作通过回调交回主线程处理。
"""

from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes
from typing import Callable, Optional

from . import icon

WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_TRAYICON_UPDATE = WM_USER + 21

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
IDI_APPLICATION = 32512

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

ERROR_CLASS_ALREADY_EXISTS = 1410

MENU_SHOW = 1001
MENU_RECONNECT = 1002
MENU_AUTOSTART = 1003
MENU_LOGOUT = 1004
MENU_EXIT = 1005

MENU_ACTIONS = {
    MENU_SHOW: "show",
    MENU_RECONNECT: "reconnect",
    MENU_AUTOSTART: "toggle_autostart",
    MENU_LOGOUT: "logout",
    MENU_EXIT: "exit",
}

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_loaded = False


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


def available() -> bool:
    return _loaded


def _setup_prototypes() -> None:
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.DefWindowProcW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.RegisterClassW.restype = wintypes.WORD
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    ]
    user32.LoadIconW.restype = wintypes.HICON
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.AppendMenuW.argtypes = [
        wintypes.HMENU,
        wintypes.UINT,
        ctypes.c_size_t,
        wintypes.LPCWSTR,
    ]
    user32.TrackPopupMenu.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [
        wintypes.HMENU,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        ctypes.c_void_p,
    ]
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    shell32.Shell_NotifyIconW.argtypes = [
        wintypes.DWORD,
        ctypes.POINTER(NOTIFYICONDATAW),
    ]


if os.name == "nt":
    try:
        _setup_prototypes()
        _loaded = True
    except Exception:  # 托盘是可选功能，初始化失败就降级
        _loaded = False


class Tray:
    """托盘图标。start() 返回 False 表示托盘不可用，调用方自行降级。"""

    CLASS_NAME = "AUSTNET_TrayWindow"

    def __init__(self, tooltip: str, on_action: Callable[[str], None]):
        self._tooltip = tooltip
        self._on_action = on_action
        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._icons: dict[str, int] = {}
        self._state = "off"
        self._autostart = False
        self._taskbar_created = 0
        self._wndproc = None

    # -- 生命周期 ---------------------------------------------------------

    def start(self) -> bool:
        if not available():
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._thread = threading.Thread(target=self._run, name="austnet-tray", daemon=True)
        self._thread.start()
        self._ready.wait(6.0)
        return self._hwnd is not None

    def stop(self) -> None:
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(3.0)
        self._thread = None
        self._hwnd = None

    # -- 更新 -------------------------------------------------------------

    def update(self, state: str, tooltip: str, autostart: bool = False) -> None:
        self._state = state
        self._tooltip = tooltip
        self._autostart = autostart
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_TRAYICON_UPDATE, 0, 0)

    # -- 内部 -------------------------------------------------------------

    def _run(self) -> None:
        try:
            message = wintypes.MSG()
            self._create_window()
            self._notify(NIM_ADD)
        except OSError:
            self._hwnd = None
            self._ready.set()
            return
        self._ready.set()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def _create_window(self) -> None:
        instance = kernel32.GetModuleHandleW(None)
        self._wndproc = WNDPROC(self._dispatch)
        window_class = WNDCLASSW()
        window_class.lpfnWndProc = self._wndproc
        window_class.hInstance = instance
        window_class.lpszClassName = self.CLASS_NAME
        if not user32.RegisterClassW(ctypes.byref(window_class)):
            if ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
                raise OSError(ctypes.get_last_error(), "RegisterClassW 失败")
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self._hwnd = user32.CreateWindowExW(
            0, self.CLASS_NAME, self._tooltip, 0, 0, 0, 0, 0, None, None, instance, None
        )
        if not self._hwnd:
            raise OSError(ctypes.get_last_error(), "CreateWindowExW 失败")

    def _dispatch(self, hwnd, message, wparam, lparam):
        if message == WM_TRAYICON:
            event = lparam & 0xFFFF
            if event == WM_RBUTTONUP:
                self._show_menu()
            elif event == WM_LBUTTONUP:
                self._action("show")
            return 0
        if message == WM_TRAYICON_UPDATE:
            self._notify(NIM_MODIFY)
            return 0
        if self._taskbar_created and message == self._taskbar_created:
            self._notify(NIM_ADD)
            return 0
        if message == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            self._notify(NIM_DELETE)
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _notify(self, operation: int) -> None:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_TRAYICON
        data.hIcon = self._load_icon(self._state)
        data.szTip = self._tooltip[:127]
        shell32.Shell_NotifyIconW(operation, ctypes.byref(data))

    def _load_icon(self, state: str) -> int:
        if state in self._icons:
            return self._icons[state]
        handle = 0
        path = icon.icon_path(state)
        if path is not None:
            handle = user32.LoadImageW(
                None, str(path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
            )
        if not handle:
            handle = user32.LoadIconW(
                None, ctypes.cast(ctypes.c_void_p(IDI_APPLICATION), wintypes.LPCWSTR)
            )
        self._icons[state] = handle
        return handle

    def _show_menu(self) -> None:
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        try:
            user32.AppendMenuW(menu, MF_STRING, MENU_SHOW, "打开主界面")
            user32.AppendMenuW(menu, MF_STRING, MENU_RECONNECT, "立即重连")
            flags = MF_STRING | (MF_CHECKED if self._autostart else 0)
            user32.AppendMenuW(menu, flags, MENU_AUTOSTART, "开机自动启动")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, MENU_LOGOUT, "注销当前认证")
            user32.AppendMenuW(menu, MF_STRING, MENU_EXIT, "退出")

            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(self._hwnd)
            command = user32.TrackPopupMenu(
                menu,
                TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                point.x,
                point.y,
                0,
                self._hwnd,
                None,
            )
            user32.PostMessageW(self._hwnd, WM_NULL, 0, 0)
            action = MENU_ACTIONS.get(command)
            if action:
                self._action(action)
        finally:
            user32.DestroyMenu(menu)

    def _action(self, action: str) -> None:
        try:
            self._on_action(action)
        except Exception:
            pass

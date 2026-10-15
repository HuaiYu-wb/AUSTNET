"""AUSTNET 主界面。"""

from __future__ import annotations

import queue
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import (
    __author__,
    __version__,
    appconfig,
    autostart,
    guard as guard_module,
    icon,
    portal,
    tray as tray_module,
)

FONT = ("Microsoft YaHei UI", 10)
FONT_TITLE = ("Microsoft YaHei UI", 14, "bold")
FONT_HINT = ("Microsoft YaHei UI", 9)
FONT_STATE = ("Microsoft YaHei UI", 12, "bold")
FONT_MONO = ("Consolas", 9)
FONT_CREDIT = ("Microsoft YaHei UI", 8)

COLOR_OK = "#3F7F5F"
COLOR_WARN = "#A9701F"
COLOR_BAD = "#B2453F"
COLOR_IDLE = "#6B7280"
COLOR_CREDIT = "#9AA0A6"

KIND_LABELS = {"wired": "有线", "wifi": "无线 WiFi", "none": "未连接"}

LOG_PREFIX = {"ok": "[成功]", "error": "[失败]", "warn": "[注意]", "info": "[提示]"}


class App:
    def __init__(self, start_hidden: bool = False):
        self.config = appconfig.load_config()
        self.password = appconfig.load_password()
        self.start_hidden = start_hidden
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.actions: queue.Queue[str] = queue.Queue()
        self.guard = guard_module.Guard(self._settings, self._emit)
        self.tray = None
        self._tray_signature: tuple[str, str] | None = None
        self._closing = False

        self.root = tk.Tk()
        self.root.title("安徽理工大学校园网助手")
        self.root.minsize(540, 640)
        self._build()
        self._apply_window_icon()
        self._sync_autostart()

    # -- 界面 -------------------------------------------------------------

    def _build(self) -> None:
        style = ttk.Style()
        for theme in ("vista", "winnative", "clam"):
            try:
                style.theme_use(theme)
                break
            except tk.TclError:
                continue
        style.configure("TLabel", font=FONT)
        style.configure("TButton", font=FONT, padding=(14, 6))
        style.configure("TCheckbutton", font=FONT)
        style.configure("TLabelframe.Label", font=FONT)
        style.configure("Title.TLabel", font=FONT_TITLE)
        style.configure("Hint.TLabel", font=FONT_HINT, foreground=COLOR_IDLE)
        style.configure("State.TLabel", font=FONT_STATE)
        style.configure("Credit.TLabel", font=FONT_CREDIT, foreground=COLOR_CREDIT)

        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(5, weight=1)

        header = ttk.Frame(root, padding=(18, 16, 18, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="安徽理工大学校园网助手", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header, text="%s · v%s" % (__author__, __version__), style="Credit.TLabel"
        ).grid(row=0, column=1, sticky="e")

        self._build_status(root, row=1)
        self._build_form(root, row=2)
        self._build_options(root, row=3)
        self._build_actions(root, row=4)
        self._build_log(root, row=5)

    def _build_status(self, root: tk.Misc, row: int) -> None:
        frame = ttk.LabelFrame(root, text="连接状态", padding=(14, 10))
        frame.grid(row=row, column=0, sticky="ew", padx=18)
        frame.columnconfigure(1, weight=1)

        self.var_kind = tk.StringVar(value="—")
        self.var_state = tk.StringVar(value="正在检测…")
        self.var_ip = tk.StringVar(value="—")
        self.var_ssid = tk.StringVar(value="—")

        rows = (
            ("接入方式", self.var_kind, None),
            ("认证状态", self.var_state, "state"),
            ("本机地址", self.var_ip, None),
            ("无线网络", self.var_ssid, None),
        )
        for index, (label, variable, tag) in enumerate(rows):
            ttk.Label(frame, text=label, style="Hint.TLabel", width=9).grid(
                row=index, column=0, sticky="w", pady=2
            )
            if tag == "state":
                self.lbl_state = ttk.Label(frame, textvariable=variable, style="State.TLabel")
                self.lbl_state.grid(row=index, column=1, sticky="w", pady=2)
            else:
                ttk.Label(frame, textvariable=variable).grid(
                    row=index, column=1, sticky="w", pady=2
                )

    def _build_form(self, root: tk.Misc, row: int) -> None:
        frame = ttk.LabelFrame(root, text="账号信息", padding=(14, 10))
        frame.grid(row=row, column=0, sticky="ew", padx=18, pady=(10, 0))
        frame.columnconfigure(1, weight=1)

        self.var_user = tk.StringVar(value=self.config.username)
        self.var_pass = tk.StringVar(value=self.password)
        self._exit_displays = [
            self._exit_display(suffix, name) for suffix, name in appconfig.EXIT_PRESETS
        ]
        self.var_exit = tk.StringVar(value=self._exit_text(self.config.exit_suffix))

        ttk.Label(frame, text="学号 / 工号").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.var_user).grid(
            row=0, column=1, columnspan=2, sticky="ew", pady=4
        )

        ttk.Label(frame, text="密码").grid(row=1, column=0, sticky="w", pady=4)
        self.entry_pass = ttk.Entry(frame, textvariable=self.var_pass, show="●")
        self.entry_pass.grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(frame, text="登录出口").grid(row=2, column=0, sticky="w", pady=4)
        self.combo_exit = ttk.Combobox(
            frame, textvariable=self.var_exit, values=self._exit_displays
        )
        self.combo_exit.grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="可手填", style="Hint.TLabel").grid(
            row=2, column=2, sticky="w", padx=(8, 0)
        )

    def _build_options(self, root: tk.Misc, row: int) -> None:
        frame = ttk.Frame(root, padding=(18, 8, 18, 0))
        frame.grid(row=row, column=0, sticky="ew")

        self.var_autostart = tk.BooleanVar(value=self.config.auto_start)
        self.var_reconnect = tk.BooleanVar(value=self.config.auto_reconnect)
        self.var_remember = tk.BooleanVar(value=self.config.remember_password)

        ttk.Checkbutton(
            frame,
            text="开机自动启动",
            variable=self.var_autostart,
            command=self._toggle_autostart,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            frame,
            text="断线自动重连",
            variable=self.var_reconnect,
            command=self._save_config_only,
        ).grid(row=0, column=1, sticky="w", padx=(20, 0))
        ttk.Checkbutton(
            frame,
            text="在本机保存密码",
            variable=self.var_remember,
            command=self._save_config_only,
        ).grid(row=0, column=2, sticky="w", padx=(20, 0))

    def _build_actions(self, root: tk.Misc, row: int) -> None:
        frame = ttk.Frame(root, padding=(18, 10, 18, 0))
        frame.grid(row=row, column=0, sticky="ew")

        self.btn_connect = ttk.Button(frame, text="保存并连接", command=self._save)
        self.btn_connect.grid(row=0, column=0, sticky="w")
        ttk.Button(frame, text="立即检测", command=self._reconnect).grid(
            row=0, column=1, sticky="w", padx=(10, 0)
        )
        ttk.Button(frame, text="注销认证", command=self._logout).grid(
            row=0, column=2, sticky="w", padx=(10, 0)
        )

    def _build_log(self, root: tk.Misc, row: int) -> None:
        frame = ttk.LabelFrame(root, text="运行日志", padding=(10, 8))
        frame.grid(row=row, column=0, sticky="nsew", padx=18, pady=(10, 16))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.log = tk.Text(
            frame,
            height=9,
            wrap="word",
            font=FONT_MONO,
            relief="flat",
            background="#FAFAFA",
            foreground="#333333",
            state="disabled",
        )
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

    # -- 运行时 -----------------------------------------------------------

    def run(self) -> int:
        self._start_tray()
        self.guard.start()
        self._append_log("info", "已启动，认证服务器 %s" % self.config.portal)
        if self.start_hidden and self.tray:
            self.root.withdraw()
        else:
            self._center()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(200, self._pump)
        self.root.after(400, self._poll_state)
        self.root.mainloop()
        return 0

    def _center(self) -> None:
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 3)
        self.root.geometry("+%d+%d" % (x, y))

    def _apply_window_icon(self) -> None:
        path = icon.icon_path("ok")
        if path is None:
            return
        try:
            self.root.iconbitmap(default=str(path))
        except tk.TclError:
            pass

    def _start_tray(self) -> None:
        if not tray_module.available():
            return
        try:
            tray = tray_module.Tray("安徽理工大学校园网助手", self._on_tray_action)
            if tray.start():
                self.tray = tray
            else:
                self._append_log("warn", "系统托盘不可用，关闭窗口将直接退出")
        except Exception as error:
            self.tray = None
            self._append_log("warn", "系统托盘初始化失败：%s" % error)

    def _settings(self) -> guard_module.Settings:
        return guard_module.Settings(
            portal=self.config.portal,
            account=appconfig.full_account(self.config.username, self.config.exit_suffix),
            password=self.password,
            auto_reconnect=self.config.auto_reconnect,
            interval=self.config.interval,
        )

    def _emit(self, level: str, message: str) -> None:
        self.events.put((level, message))

    def _on_tray_action(self, action: str) -> None:
        self.actions.put(action)

    def _pump(self) -> None:
        try:
            while True:
                level, message = self.events.get_nowait()
                self._append_log(level, message)
        except queue.Empty:
            pass
        try:
            while True:
                self._handle_action(self.actions.get_nowait())
        except queue.Empty:
            pass
        if not self._closing:
            self.root.after(250, self._pump)

    def _handle_action(self, action: str) -> None:
        if action == "show":
            self._show_window()
        elif action == "reconnect":
            self._reconnect()
        elif action == "toggle_autostart":
            self.var_autostart.set(not self.var_autostart.get())
            self._toggle_autostart()
        elif action == "logout":
            self._logout()
        elif action == "exit":
            self._quit()

    def _poll_state(self) -> None:
        try:
            snapshot = self.guard.snapshot()
            self.var_kind.set(KIND_LABELS.get(snapshot.kind, snapshot.kind))
            self.var_ip.set(snapshot.ip or "—")
            self.var_ssid.set(snapshot.ssid or "—")
            self.var_state.set(snapshot.message)
            self.lbl_state.configure(foreground=self._state_color(snapshot))
            self._update_tray(snapshot)
            if not self._closing:
                self.root.after(700, self._poll_state)
        except tk.TclError:
            pass  # 窗口已经销毁，轮询自然结束

    def _state_color(self, snapshot) -> str:
        if snapshot.connected:
            return COLOR_OK
        if snapshot.kind == "none" or "缺少" in snapshot.message:
            return COLOR_IDLE
        if "失败" in snapshot.message or "掉线" in snapshot.message:
            return COLOR_BAD
        return COLOR_WARN

    def _update_tray(self, snapshot) -> None:
        if self.tray is None:
            return
        state = "ok" if snapshot.connected else "off"
        tooltip = "安徽理工大学校园网助手 ｜ %s ｜ %s" % (
            KIND_LABELS.get(snapshot.kind, snapshot.kind),
            snapshot.message,
        )
        signature = (state, tooltip)
        if signature != self._tray_signature:
            self._tray_signature = signature
            self.tray.update(state, tooltip, bool(self.var_autostart.get()))

    def _append_log(self, level: str, message: str) -> None:
        prefix = LOG_PREFIX.get(level, "[提示]")
        line = "[%s] %s %s\n" % (time.strftime("%H:%M:%S"), prefix, message)
        self.log.configure(state="normal")
        self.log.insert("end", line)
        self.log.see("end")
        self.log.configure(state="disabled")

    # -- 操作 -------------------------------------------------------------

    @staticmethod
    def _exit_display(suffix: str, name: str) -> str:
        return "%s（%s）" % (name, suffix or "不加后缀")

    def _exit_text(self, suffix: str) -> str:
        for value, name in appconfig.EXIT_PRESETS:
            if value == suffix:
                return self._exit_display(value, name)
        return suffix

    def _parse_exit(self) -> str:
        text = self.var_exit.get().strip()
        for suffix, name in appconfig.EXIT_PRESETS:
            if text == self._exit_display(suffix, name):
                return suffix
        if not text:
            return ""
        return text if text.startswith("@") else "@" + text

    def _collect(self) -> None:
        self.config.username = self.var_user.get().strip()
        self.config.exit_suffix = self._parse_exit()
        self.config.auto_start = bool(self.var_autostart.get())
        self.config.auto_reconnect = bool(self.var_reconnect.get())
        self.config.remember_password = bool(self.var_remember.get())

    def _save_config_only(self) -> None:
        self._collect()
        try:
            appconfig.save_config(self.config)
        except OSError as error:
            self._append_log("error", "配置写入失败：%s" % error)

    def _save(self) -> None:
        self._collect()
        self.password = self.var_pass.get()
        if not self.config.username:
            messagebox.showwarning("信息不完整", "请填写学号或工号。", parent=self.root)
            return
        if not self.password:
            messagebox.showwarning("信息不完整", "请填写密码。", parent=self.root)
            return
        try:
            appconfig.save_config(self.config)
            if self.config.remember_password:
                appconfig.save_password(self.password)
            else:
                appconfig.clear_password()
        except (OSError, RuntimeError) as error:
            messagebox.showerror("保存失败", str(error), parent=self.root)
            return
        self._append_log(
            "ok", "配置已保存：%s%s" % (self.config.username, self.config.exit_suffix or "")
        )
        self._reconnect()

    def _reconnect(self) -> None:
        self._collect()
        self.password = self.var_pass.get()
        self.guard.resume()
        self.guard.poke()
        self._append_log("info", "已请求立即检测并登录")

    def _logout(self) -> None:
        base = (self.config.portal or "").rstrip("/")
        ok = portal.logout(base)
        self.guard.suspend()
        self._append_log(
            "ok" if ok else "error",
            "已注销认证，自动重连已暂停（点「立即检测」恢复）" if ok else "注销请求失败",
        )

    def _toggle_autostart(self) -> None:
        enabled = bool(self.var_autostart.get())
        try:
            autostart.apply(enabled)
        except OSError as error:
            self.var_autostart.set(not enabled)
            messagebox.showerror("设置失败", "写入开机自启失败：%s" % error, parent=self.root)
            return
        self._collect()
        self._save_config_only()
        self._append_log("ok", "开机自动启动已%s" % ("开启" if enabled else "关闭"))

    def _sync_autostart(self) -> None:
        try:
            enabled = autostart.is_enabled()
        except OSError:
            enabled = False
        self.var_autostart.set(enabled)
        self.config.auto_start = enabled
        if enabled:
            try:
                autostart.refresh()  # 程序位置变了就改写自启项
            except OSError:
                pass

    # -- 窗口 -------------------------------------------------------------

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(400, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def _on_close(self) -> None:
        if self.tray is not None:
            self.root.withdraw()
            self._append_log("info", "已最小化到系统托盘，右键托盘图标可退出")
            return
        self._quit()

    def _quit(self) -> None:
        self._closing = True
        self._collect()
        self.password = self.var_pass.get()
        try:
            appconfig.save_config(self.config)
            if self.config.remember_password and self.password:
                appconfig.save_password(self.password)
        except (OSError, RuntimeError):
            pass
        self.guard.stop()
        if self.tray is not None:
            self.tray.stop()
            self.tray = None
        self.root.destroy()


def main(start_hidden: bool = False) -> int:
    return App(start_hidden=start_hidden).run()

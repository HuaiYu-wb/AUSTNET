"""程序图标。

优先用随程序分发的 assets/*.ico；没有的话再用 Pillow 现场画一个缓存在数据目录；
两样都不行就返回 None，调用方回退到系统默认图标。
"""

from __future__ import annotations

import sys
from pathlib import Path

from .appconfig import data_dir

ICON_TEMPLATE = "austnet-%s.ico"

# 状态 -> 主色
COLORS = {
    "ok": (98, 140, 110),
    "off": (140, 146, 158),
    "busy": (198, 154, 84),
}


def _bundled(state: str) -> Path | None:
    """PyInstaller 会把 --add-data 的内容解到 _MEIPASS，源码运行时直接读仓库里的。"""
    candidates = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(Path(base) / "assets" / (ICON_TEMPLATE % state))
    candidates.append(Path(__file__).resolve().parent.parent / "assets" / (ICON_TEMPLATE % state))
    for path in candidates:
        if path.exists():
            return path
    return None


def icon_path(state: str = "off") -> Path | None:
    state = state if state in COLORS else "off"
    bundled = _bundled(state)
    if bundled is not None:
        return bundled
    path = data_dir() / (ICON_TEMPLATE % state)
    if path.exists():
        return path
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, size - 2, size - 2), radius=14, fill=COLORS[state] + (255,))

    white = (255, 255, 255, 255)
    for index, radius in enumerate((10, 20, 30)):
        box = (size // 2 - radius, size // 2 - radius + 10, size // 2 + radius, size // 2 + radius + 10)
        draw.arc(box, start=200, end=340, fill=white, width=5)
        if index == 0:
            draw.ellipse((size // 2 - 4, size // 2 + 8, size // 2 + 4, size // 2 + 16), fill=white)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    return path


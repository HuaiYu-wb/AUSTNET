"""生成打包用的图标到 assets/。

    python tools/make_icons.py
"""

from __future__ import annotations

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from austnet import icon  # noqa: E402

ASSETS = os.path.join(ROOT, "assets")


def main() -> int:
    os.makedirs(ASSETS, exist_ok=True)
    for state in ("ok", "off", "busy"):
        # 先清掉旧的，确保走生成分支
        target = os.path.join(ASSETS, icon.ICON_TEMPLATE % state)
        if os.path.exists(target):
            os.remove(target)
        source = icon.icon_path(state)
        if source is None or os.path.abspath(source) == os.path.abspath(target):
            print("生成失败（缺少 Pillow？）:", target)
            return 1
        shutil.copyfile(source, target)
        print("生成", os.path.relpath(target, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


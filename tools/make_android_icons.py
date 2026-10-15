"""从 android/art/icon-source.jpg 生成安卓启动图标。

    python tools/make_android_icons.py

自适应图标的前景会把粉色底抠成透明，只留标志本体，这样任何图标形状下都不会
出现背景色的接缝；抠图失败就退回"整张图按安全区缩放"的做法。
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "android", "art", "icon-source.jpg")
RES = os.path.join(ROOT, "android", "app", "src", "main", "res")

# 密度 -> (传统图标边长, 自适应图标前景边长)
DENSITIES = {
    "mdpi": (48, 108),
    "hdpi": (72, 162),
    "xhdpi": (96, 216),
    "xxhdpi": (144, 324),
    "xxxhdpi": (192, 432),
}

# 自适应图标只有中间 66.7% 是安全区，标志要缩进这个范围里
SAFE_ZONE = 0.66


def load_square() -> Image.Image:
    """把源图居中放进正方形画布，四周用背景色补齐，保证不被裁切。"""
    image = Image.open(SOURCE).convert("RGB")
    background = image.getpixel((3, 3))
    side = max(image.size)
    canvas = Image.new("RGB", (side, side), background)
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


def cut_background(image: Image.Image) -> Image.Image:
    """按背景色抠图，返回带 alpha 的前景。"""
    import numpy as np

    rgb = np.asarray(image.convert("RGB")).astype(int)
    background = np.array(image.getpixel((3, 3)), dtype=int)
    distance = np.abs(rgb - background).sum(axis=2)
    alpha = np.clip((distance - 14) * 10, 0, 255).astype("uint8")
    rgba = np.dstack([rgb.astype("uint8"), alpha])
    return Image.fromarray(rgba, "RGBA")


def rounded(image: Image.Image) -> Image.Image:
    size = image.size[0]
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    result = image.convert("RGBA")
    result.putalpha(mask.resize((size, size), Image.LANCZOS))
    return result


def main() -> int:
    if not os.path.exists(SOURCE):
        print("缺少源图：", SOURCE)
        return 1

    square = load_square()
    background = square.getpixel((3, 3))
    print("背景色 #%02X%02X%02X" % background)

    cutout = cut_background(square)
    opaque_ratio = sum(1 for a in cutout.getchannel("A").getdata() if a > 128) / float(
        square.width * square.height
    )
    use_cutout = 0.02 < opaque_ratio < 0.75
    print("抠图前景占比 %.1f%%，%s" % (opaque_ratio * 100, "采用抠图" if use_cutout else "改用整图缩放"))

    for density, (legacy, adaptive) in DENSITIES.items():
        folder = os.path.join(RES, "mipmap-%s" % density)
        os.makedirs(folder, exist_ok=True)

        legacy_png = square.resize((legacy, legacy), Image.LANCZOS)
        legacy_png.save(os.path.join(folder, "ic_launcher.png"))
        rounded(legacy_png).save(os.path.join(folder, "ic_launcher_round.png"))

        inner = int(round(adaptive * SAFE_ZONE))
        foreground = Image.new("RGBA", (adaptive, adaptive), (0, 0, 0, 0))
        source = cutout if use_cutout else square
        foreground.paste(
            source.resize((inner, inner), Image.LANCZOS),
            ((adaptive - inner) // 2, (adaptive - inner) // 2),
        )
        foreground.save(os.path.join(folder, "ic_launcher_foreground.png"))
        print("  mipmap-%s  图标 %dpx  前景 %dpx" % (density, legacy, adaptive))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


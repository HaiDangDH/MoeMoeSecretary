"""Tạo assets/icon.ico (biểu tượng cho file .exe) bằng Pillow. Có thể thay bằng icon riêng."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256


def build() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    # nền bo góc chuyển màu xanh
    grad = Image.new("RGBA", (SIZE, SIZE))
    gp = grad.load()
    top, bottom = (91, 178, 255), (47, 95, 214)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        col = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        for x in range(SIZE):
            gp[x, y] = col
    mask = Image.new("L", (SIZE, SIZE), 0)
    m = int(SIZE * 0.04)
    ImageDraw.Draw(mask).rounded_rectangle((m, m, SIZE - m, SIZE - m), radius=int(SIZE * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)

    # ngôi sao trắng
    cx, cy, outer, inner = SIZE / 2, SIZE * 0.53, SIZE * 0.34, SIZE * 0.14
    pts = []
    for i in range(10):
        r = outer if i % 2 == 0 else inner
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    ImageDraw.Draw(img).polygon(pts, fill=(255, 255, 255, 255))
    return img


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    build().save(out, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Đã tạo", out)

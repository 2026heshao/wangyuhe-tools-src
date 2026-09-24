# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck 应用图标生成器 —— 「日出甲板」（备选方案，当前未启用）
====================================================================
⚠ 现状（2026-09-24）：v2 采用 `tools/recolor_icon.py` 的「旧图案 + 暖色」
   方案。本脚本是此前设计过的「日出甲板」全新剪影方案，保留备查，
   重跑会覆盖 v2/111.ico 与 v2/111.png —— 想切回该方案时才执行。
   v1 已冻结，本脚本不再写 v1。

设计原则（参考 GitHub Octocat 的图标思路）：
  · 靠形状说话，不堆玻璃/内阴影/描边等材质
  · 暖色渐变背景 + 纯白剪影，明暗对比足
  · 按尺寸降级细节：16px 只留最简形，256px 才有完整构图

产出：
  · icon_1024.png  主图（用于 README / 网页 / 后续再导出）
  · 111.ico        多尺寸 Windows 图标（16/24/32/48/64/128/256，全部内嵌 PNG）
  · 111.png        512×512 预览图

改配色只动 PALETTE；改构图只动 build()。
运行：python tools/gen_icon.py
====================================================================
"""

import os
import math
import struct

from PIL import Image, ImageDraw

# ------------------------------------------------------------------
# 可调参数
# ------------------------------------------------------------------
# 日出暖橙渐变：顶（明亮金黄）→ 底（暖橙）
PALETTE = {
    "top":    (255, 206, 74),    # #FFCE4A 晨光金
    "mid":    (255, 158, 44),    # #FF9E2C 中段过渡
    "bottom": (247, 106, 26),    # #F76A1A 暖橙
}
SILHOUETTE = (255, 255, 255)     # 剪影白

SQUIRCLE_N = 4.2                 # 超椭圆指数：越大越接近矩形（Apple 约 4~5）
SQUIRCLE_FILL = 0.96             # 图形占画布比例（留 2% 边，避免贴边被裁）

SS = 4                           # 超采样倍数（抗锯齿）：最终 LANCZOS 缩回

# ICO 内嵌尺寸（Windows 常用全套）
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


# ------------------------------------------------------------------
# 几何工具
# ------------------------------------------------------------------
def squircle_points(cx, cy, half, n=SQUIRCLE_N, steps=1440):
    """超椭圆（squircle）轮廓采样点——现代 App 图标的圆角方基底。"""
    pts = []
    for i in range(steps):
        t = 2.0 * math.pi * i / steps
        ct, st = math.cos(t), math.sin(t)
        e = 2.0 / n
        x = math.copysign(abs(ct) ** e, ct)
        y = math.copysign(abs(st) ** e, st)
        pts.append((cx + x * half, cy + y * half))
    return pts


def lerp(a, b, t):
    return a + (b - a) * t


def vertical_gradient(size, stops):
    """纵向多段渐变，返回 RGB 画布。stops = [(pos0-1, (r,g,b)), ...] 按 pos 升序。"""
    img = Image.new("RGB", (1, size))
    px = img.load()
    for y in range(size):
        t = y / max(1, size - 1)
        # 定位所在区段
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if t <= p1 or i == len(stops) - 2:
                k = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
                k = max(0.0, min(1.0, k))
                px[0, y] = tuple(int(round(lerp(c0[j], c1[j], k))) for j in range(3))
                break
    return img


# ------------------------------------------------------------------
# 构图（归一化坐标，0..1 相对整张画布）
# ------------------------------------------------------------------
def draw_glyph(draw, S, level):
    """
    在 S×S 的超采样画布上绘制白色剪影。

    level（细节层级，按尺寸降级，保证小尺寸不糊）：
      2 = 完整：太阳圆 + 两道甲板横线
      1 = 中等：太阳圆 + 一道甲板横线
      0 = 最简：只留太阳圆（放大）
    """
    cx = S * 0.5

    if level == 0:
        # 16px：只留一个饱满的圆，放大占位，保证一眼可辨
        cy = S * 0.50
        r = S * 0.235
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SILHOUETTE)
        return

    if level == 1:
        cy = S * 0.415
        r = S * 0.180
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SILHOUETTE)
        # 单道甲板线
        hw, hh, yc = S * 0.190, S * 0.045, S * 0.725
        draw.rounded_rectangle(
            [cx - hw, yc - hh, cx + hw, yc + hh],
            radius=hh, fill=SILHOUETTE)
        return

    # ---- level 2：完整构图 ----
    # 太阳圆
    cy = S * 0.385
    r = S * 0.170
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SILHOUETTE)

    # 甲板两道横线：上长下短，形成"堆叠平台/日出地平线"的层次
    hh = S * 0.038
    for hw, yc in ((S * 0.205, S * 0.665), (S * 0.140, S * 0.785)):
        draw.rounded_rectangle(
            [cx - hw, yc - hh, cx + hw, yc + hh],
            radius=hh, fill=SILHOUETTE)


def render(size):
    """渲染单个尺寸的 RGBA 图标。"""
    level = 2 if size >= 48 else (1 if size >= 24 else 0)

    S = size * SS
    half = S * SQUIRCLE_FILL / 2.0
    c = S / 2.0

    # 1) 基底遮罩（squircle），作为整体 alpha
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon(
        squircle_points(c, c, half), fill=255)

    # 2) 渐变底：先做 1px 宽渐变条，再横向拉满
    grad = vertical_gradient(
        S, [(0.0, PALETTE["top"]),
            (0.55, PALETTE["mid"]),
            (1.0, PALETTE["bottom"])]).resize((S, S))

    # 3) 剪影
    draw = ImageDraw.Draw(grad)
    draw_glyph(draw, S, level)

    # 4) 合成：squircle 之外的区域透明
    out = grad.convert("RGBA")
    out.putalpha(mask)

    # 5) 缩回目标尺寸（LANCZOS 高质量抗锯齿）
    if SS != 1:
        out = out.resize((size, size), Image.LANCZOS)
    return out


# ------------------------------------------------------------------
# ICO 封装（全部内嵌 PNG，Vista+ 原生支持，alpha 无损）
# ------------------------------------------------------------------
def build_ico(images):
    """
    images: [(size, PIL.Image), ...] → ICO 二进制
    结构：ICONDIR(6B) + ICONDIRENTRY(16B×n) + 图像数据（PNG 原样内嵌）
    """
    blobs = []
    for size, img in images:
        buf = __import__("io").BytesIO()
        img.save(buf, format="PNG", optimize=True)
        blobs.append((size, buf.getvalue()))

    n = len(blobs)
    header = struct.pack("<HHH", 0, 1, n)
    offset = 6 + 16 * n
    entries, datas = b"", b""
    for size, data in blobs:
        b = 0 if size >= 256 else size     # 256 用 0 表示
        entries += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        datas += data
    return header + entries + datas


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(here, "v2")       # v2 为当前主版本
    os.makedirs(out_dir, exist_ok=True)

    # 主图 1024
    big = render(1024)
    big.save(os.path.join(out_dir, "icon_1024.png"), optimize=True)

    # 512 预览（替代原 111.png）
    big.resize((512, 512), Image.LANCZOS).save(
        os.path.join(out_dir, "111.png"), optimize=True)

    # 多尺寸 ICO
    images = [(s, render(s)) for s in ICO_SIZES]
    ico_bytes = build_ico(images)
    ico_path = os.path.join(out_dir, "111.ico")
    with open(ico_path, "wb") as f:
        f.write(ico_bytes)

    # ⚠ v1 已于 2026-09-24 冻结（保持旧版图标），本脚本只写 v2，不再同步 v1。

    print("icon sizes:", ", ".join(str(s) for s in ICO_SIZES))
    print("ico bytes :", len(ico_bytes))
    print("out       :", ico_path)


if __name__ == "__main__":
    main()

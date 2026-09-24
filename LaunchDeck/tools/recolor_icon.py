# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck v2 图标重着色器 —— 旧图案 + 阳光暖色
====================================================================
思路：**不重绘图案**，直接把旧版图标（玻璃球 + 中心图形）的像素做
色彩重映射，保证图案 100% 与旧版一致，只换配色 + 细节优化。

色彩映射（HSL 空间）：
  · 色相：旧图冷色区间 195°~285°（蓝→紫蓝）线性映射到 24°~58°（橙→金）
  · 近灰像素（高光/白色主体，S<0.12）保持原样 → 保住原图案的明暗对比
  · 饱和度 ×0.95（暖色在同等 S 下更艳，略收一点避免燥）
  · 明度 gamma 0.85（整体提亮，阳光气质）

图案细节优化（不改造型）：
  · alpha 低位清理（<20 归零），去掉缩放产生的杂边
  · 小尺寸（≤48px）加 UnsharpMask，避免缩小后发糊
  · 补全 16/24/32/48/64/128/256 全套尺寸（旧 ICO 只有 256 一层）

源图：默认从 git 提交 7c466a3（v1 基线冻结）取旧版 111.png，也可 --src 指定。
产出：v2/111.ico、v2/111.png、v2/icon_384.png、tools/icon_preview.png（配色对比）
运行：python tools/recolor_icon.py
====================================================================
"""

import os
import sys
import io
import math
import struct
import colorsys
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter

# ------------------------------------------------------------------
# 可调参数
# ------------------------------------------------------------------
HUE_SRC = (195.0, 285.0)     # 旧图冷色区间（度）
HUE_DST = (24.0, 58.0)       # 目标暖色区间（度）：24°橙 → 58°金
SAT_SCALE = 0.95             # 饱和度系数
LIGHT_GAMMA = 1.0            # 明度 gamma（1.0=只换色不调亮度；提亮交给 CUTE）
GREY_SAT = 0.12              # 低于此饱和度视为"近灰/白"，色相不动
ALPHA_FLOOR = 20             # alpha 下限，低于则归零（去杂边）

# ------------------------------------------------------------------
# 可爱化后处理（让图案更灵动）：设 CUTE = None 即关闭，得到纯暖色版
# ------------------------------------------------------------------
CUTE = {
    "gamma": 0.84,       # 明度 gamma：抬暗部提通透（越小越亮、越"果冻"）
    "sat_boost": 1.20,   # 饱和度增益：糖果化
    "gloss": 0.55,       # 高光光泽：亮部向纯白推 + 局部去饱和 → 水润反光
    "gloss_from": 0.85,  # 高光起算明度
    "core_lift": 0.035,  # 中心径向提亮（0=关）：球体通透内光
    "spot": 0.30,        # 左上高光斑强化（利用原图已有高光，不新增元素）
    "spot_center": (0.24, 0.26),
    "spot_radius": 0.30,
    "contrast": 0.12,    # 中间调轻微 S 曲线：提亮后补回层次，避免"发白"
}

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
SHARPEN_MAX = 48             # ≤ 该尺寸加锐化
SRC_COMMIT = "7c466a3"       # 旧图标所在提交（v1 基线冻结）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------------
# 取源图
# ------------------------------------------------------------------
def fetch_source(src=None):
    """取旧版图标 PNG。默认从 git 指定提交导出，避免依赖外部文件。"""
    if src:
        return Image.open(src).convert("RGBA"), src

    cache = os.path.join(tempfile.gettempdir(), "ld_old_icon_%s.png" % SRC_COMMIT)
    if not os.path.exists(cache):
        blob = subprocess.run(
            ["git", "show", "%s:v1/111.png" % SRC_COMMIT],
            cwd=ROOT, capture_output=True, check=True).stdout
        with open(cache, "wb") as f:
            f.write(blob)
    return Image.open(cache).convert("RGBA"), cache


# ------------------------------------------------------------------
# 核心：色相重映射
# ------------------------------------------------------------------
def remap_hue(h_deg):
    """把冷色相线性映射到暖色相；区间外按端点收敛。"""
    s0, s1 = HUE_SRC
    d0, d1 = HUE_DST
    t = (h_deg - s0) / (s1 - s0)
    t = max(0.0, min(1.0, t))
    return (d0 + t * (d1 - d0)) / 360.0


def recolor(im):
    """逐像素重着色。近白高光保持原样，其余按映射转换。"""
    im = im.copy()
    src = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = src[x, y]
            if a == 0:
                continue
            a2 = 0 if a < ALPHA_FLOOR else a
            hh, ll, ss = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
            if ss >= GREY_SAT:
                hh = remap_hue(hh * 360.0)
                ss = min(1.0, ss * SAT_SCALE)
                ll = ll ** LIGHT_GAMMA
            else:
                # 近灰/白：只提亮，不染色（保住白色主体图形）
                ll = min(1.0, ll ** (LIGHT_GAMMA * 1.02))
            rr, gg, bb = colorsys.hls_to_rgb(hh, ll, ss)
            src[x, y] = (int(rr * 255 + 0.5), int(gg * 255 + 0.5),
                         int(bb * 255 + 0.5), a2)
    return im


def cutify(im):
    """
    可爱化后处理：让图案更灵动。

    三项手段（均不改变图案几何，仅调像素）：
      1. 明度 gamma 提亮暗部 → 通透、轻快，去掉"沉"
      2. 饱和度增益 → 糖果质感，去掉"灰"
      3. 高光光泽：亮部向纯白推 + 局部去饱和 → 水润反光点
      4. 中心径向微弱提亮 → 球体有内透光感
      5. 左上高光斑强化 → 果冻球的反光亮点（复用原图已有高光位置）
      6. 中间调 S 曲线 → 提亮后补回层次，避免糊成一片
    """
    if not CUTE:
        return im

    im = im.copy()
    px = im.load()
    w, h = im.size
    cx, cy = w / 2.0, h / 2.0
    R = min(w, h) / 2.0

    g = CUTE["gamma"]
    sb = CUTE["sat_boost"]
    gl = CUTE["gloss"]
    gf = CUTE["gloss_from"]
    lift = CUTE["core_lift"]
    spot = CUTE["spot"]
    scx, scy = CUTE["spot_center"]
    sr = CUTE["spot_radius"]
    ct = CUTE["contrast"]

    for y in range(h):
        for x in range(w):
            r, gg, b, a = px[x, y]
            if a == 0:
                continue
            hh, ll, ss = colorsys.rgb_to_hls(r / 255.0, gg / 255.0, b / 255.0)

            ll = ll ** g                                  # 1) 提亮
            ss = min(1.0, ss * sb)                        # 2) 糖果化

            if lift:                                      # 3) 中心内透光
                d = math.hypot(x - cx, y - cy) / R
                ll = min(1.0, ll + lift * max(0.0, 1.0 - d) ** 2)

            if spot:                                      # 4) 左上高光斑
                d = math.hypot(x / w - scx, y / h - scy) / sr
                if d < 1.0:
                    k = (1.0 - d) ** 2 * spot
                    ll = min(1.0, ll + (1.0 - ll) * k)
                    ss = ss * (1.0 - 0.40 * k)

            if gl and ll > gf:                            # 5) 高光光泽
                t = (ll - gf) / (1.0 - gf)
                ll = ll + (1.0 - ll) * t * gl
                ss = ss * (1.0 - 0.55 * t * gl)

            if ct:                                        # 6) 中间调 S 曲线
                ll = max(0.0, min(1.0, ll + (ll - ll * ll) * ct))

            rr, g2, b2 = colorsys.hls_to_rgb(hh, ll, ss)
            px[x, y] = (int(rr * 255 + 0.5), int(g2 * 255 + 0.5),
                        int(b2 * 255 + 0.5), a)
    return im


def render_sizes(base):
    """按 ICO 尺寸表缩放；小尺寸加锐化。"""
    out = []
    for s in ICO_SIZES:
        img = base.resize((s, s), Image.LANCZOS)
        if s <= SHARPEN_MAX:
            img = img.filter(
                ImageFilter.UnsharpMask(radius=0.8, percent=70, threshold=2))
        out.append((s, img))
    return out


# ------------------------------------------------------------------
# ICO 封装（全尺寸内嵌 PNG）
# ------------------------------------------------------------------
def build_ico(images):
    blobs = []
    for size, img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        blobs.append((size, buf.getvalue()))

    n = len(blobs)
    header = struct.pack("<HHH", 0, 1, n)
    offset = 6 + 16 * n
    entries, datas = b"", b""
    for size, data in blobs:
        b = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        datas += data
    return header + entries + datas


# ------------------------------------------------------------------
# 对比预览图
# ------------------------------------------------------------------
def make_preview(old, warm, cute, images):
    """三栏对比：旧配色 / 暖色版 / 可爱版；下方列各小尺寸。"""
    cell = 180
    pad = 26
    show = 160
    panels = [(old, "旧配色"), (warm, "暖色版"), (cute, "可爱版 ★")]
    small = [(s, im) for s, im in images if s <= 64]

    W = pad * 2 + cell * 3 + pad * 2
    H = pad + show + 34 + 74 + pad
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(canvas)

    for i, (img, label) in enumerate(panels):
        x = pad + i * (cell + pad)
        thumb = img.convert("RGBA").resize((show, show), Image.LANCZOS)
        canvas.paste(thumb, (x + (cell - show) // 2, pad), thumb)
        d.text((x + cell // 2, pad + show + 10), label,
               fill=(70, 70, 70), anchor="ma")

    x = pad
    y = pad + show + 40
    for s, img in small:
        canvas.paste(img, (x, y), img)
        d.text((x + s // 2, y + 70), "%dpx" % s, fill=(120, 120, 120), anchor="ma")
        x += s + 16
    return canvas


def main():
    src_arg = None
    if "--src" in sys.argv:
        src_arg = sys.argv[sys.argv.index("--src") + 1]

    old, src_path = fetch_source(src_arg)
    print("源图:", src_path, old.size)

    warm = recolor(old)                 # 基础暖色版
    new = cutify(warm)                  # 可爱版（CUTE=None 时等同暖色版）

    v2 = os.path.join(ROOT, "v2")
    os.makedirs(v2, exist_ok=True)

    images = render_sizes(new)
    ico = build_ico(images)
    with open(os.path.join(v2, "111.ico"), "wb") as f:
        f.write(ico)

    new.save(os.path.join(v2, "111.png"), optimize=True)
    new.save(os.path.join(v2, "icon_384.png"), optimize=True)

    prev = make_preview(old, warm, new, images)
    prev.save(os.path.join(ROOT, "tools", "icon_preview.png"))

    print("可爱化:", "开启 %s" % CUTE if CUTE else "关闭")
    print("ico 尺寸:", ICO_SIZES)
    print("ico 字节:", len(ico))
    print("产出: v2/111.ico, v2/111.png, v2/icon_384.png, tools/icon_preview.png")


if __name__ == "__main__":
    main()

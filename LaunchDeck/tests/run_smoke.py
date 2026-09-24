# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck UI 冒烟测试（无窗口离屏跑，不改任何用户配置）
====================================================================
用法：python tests/run_smoke.py        （退出码 0 = 全过）

覆盖：
  · test_theme_constants   主题常量归一（theme.py 单一来源）
  · test_menu_style        右键菜单透底圆角（黑角回归防线）
  · test_icon_cache_clean  磁盘图标缓存孤儿清理（keep 保留/孤儿删除）
  · test_crash_log_rotate  crash.log 1MB 轮转

原理备注：offscreen 平台下 QWidget.grab() 可渲染出带效果的位图，
用像素 alpha 断言验证样式；但 DWM 相关问题（如弹窗原生阴影）只在
真机上屏出现，离屏测不出——真机验收仍不可省。
====================================================================
"""

import os
import sys
import tempfile

# 必须在导入 PyQt6 之前设置离屏平台
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _V2_ROOT)

from PyQt6.QtWidgets import QApplication   # noqa: E402

_app = QApplication([])                     # 模块级共享，仅初始化一次


# --------------------------------------------------------------------
# 1. 主题常量归一
# --------------------------------------------------------------------

def test_theme_constants() -> None:
    from ui import theme
    from ui import settings_dialog

    assert theme.TEXT_MAIN == "#D2D4D9", theme.TEXT_MAIN
    assert theme.TEXT_DIM == "#8A8D96", theme.TEXT_DIM
    assert theme.ACCENT == "#4C96FF", theme.ACCENT
    assert theme.ACCENT_HOVER == "#67A5FF", theme.ACCENT_HOVER
    # settings_dialog 引用的是同一对象（不是复制品）
    assert settings_dialog.TEXT_MAIN is theme.TEXT_MAIN
    assert settings_dialog.ACCENT is theme.ACCENT
    # 三套主题字段完整性（面板换肤依赖的全部键）
    required = {"label", "surface", "border_a", "hover", "text", "text_dim",
                "accent", "dot", "ball_bg", "ball_bg_hover", "ball_icon",
                "ball_glow", "ball_glow_core"}
    for name, t in theme.THEMES.items():
        missing = required - set(t)
        assert not missing, f"主题 {name} 缺字段: {missing}"


# --------------------------------------------------------------------
# 2. 右键菜单透底圆角
# --------------------------------------------------------------------

def test_menu_style() -> None:
    from PyQt6.QtCore import Qt
    from ui.settings_dialog import make_styled_menu

    menu = make_styled_menu()
    # 窗口层：透底 + 无 DWM 原生阴影（Windows 黑角三件套）
    assert menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert bool(menu.windowFlags() & Qt.WindowType.NoDropShadowWindowHint)

    # 渲染层：圆角外完全透明，中心不透明
    menu.addAction("打  开")
    menu.addAction("以管理员运行")
    menu.resize(160, 90)
    pm = menu.grab()
    img = pm.toImage()
    w, h = img.width(), img.height()
    for x, y in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)):
        a = img.pixelColor(x, y).alpha()
        assert a == 0, f"菜单角 ({x},{y}) alpha={a}，圆角透底失效"
    center = img.pixelColor(w // 2, h // 2).alpha()
    assert center > 200, f"菜单中心 alpha={center}，底色没画出来"


# --------------------------------------------------------------------
# 3. 磁盘图标缓存孤儿清理
# --------------------------------------------------------------------

def test_icon_cache_clean() -> None:
    import core.app_manager as am

    tmp = tempfile.mkdtemp(prefix="ld_iconcache_")
    orig_dir = am.ICON_CACHE_DIR
    am.ICON_CACHE_DIR = tmp                 # 只改模块变量，测试后还原
    try:
        src = os.path.join(tmp, "fake_app.exe")
        with open(src, "wb") as f:
            f.write(b"MZ fake")

        keep_name = os.path.basename(am._disk_cache_path(src))
        for name in (keep_name, "orphan_1.png", "orphan_2.png", "note.txt"):
            with open(os.path.join(tmp, name), "w") as f:
                f.write("x")

        removed = am.cleanup_icon_cache_disk([src])
        assert removed == 2, f"应删 2 个孤儿 png，实删 {removed}"
        assert os.path.exists(os.path.join(tmp, keep_name)), "有效缓存被误删"
        assert os.path.exists(os.path.join(tmp, "note.txt")), "非 png 被误删"

        # 空来源列表 → 全部 png 都是孤儿
        removed = am.cleanup_icon_cache_disk([])
        assert removed == 1, f"应删 1 个残留 png，实删 {removed}"
        # 不存在的缓存目录 → 安全返回 0
        am.ICON_CACHE_DIR = os.path.join(tmp, "not_exist_dir")
        assert am.cleanup_icon_cache_disk([src]) == 0
    finally:
        am.ICON_CACHE_DIR = orig_dir


# --------------------------------------------------------------------
# 4. crash.log 轮转
# --------------------------------------------------------------------

def test_crash_log_rotate() -> None:
    import main as ld_main

    tmp_log = os.path.join(tempfile.mkdtemp(prefix="ld_crash_"), "crash.log")
    orig = ld_main._crash_log_path
    ld_main._crash_log_path = lambda: tmp_log
    orig_hook = sys.__excepthook__
    sys.__excepthook__ = lambda *a: None      # 屏蔽默认 stderr 输出，保持输出干净
    try:
        with open(tmp_log, "w", encoding="utf-8") as f:
            f.write("x" * (ld_main._CRASH_LOG_MAX + 4096))   # 超 1MB

        ld_main._excepthook(ValueError, ValueError("test"), None)
        size = os.path.getsize(tmp_log)
        assert size < ld_main._CRASH_LOG_MAX, f"超限未轮转，size={size}"
        with open(tmp_log, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Unhandled exception" in content, "轮转后新日志未写入"
        assert "ValueError" in content
    finally:
        ld_main._crash_log_path = orig
        sys.__excepthook__ = orig_hook


# --------------------------------------------------------------------
# 5. 拆分后 FloatingBall 整链实例化（隔离配置，不碰真实 config.json）
# --------------------------------------------------------------------

def test_ball_split() -> None:
    import json
    import core.app_manager as am
    from core.app_manager import AppManager
    from ui.floating_ball import FloatingBall

    tmp = tempfile.mkdtemp(prefix="ld_cfg_")
    cfg = os.path.join(tmp, "config.json")
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump({"apps": [{"name": "T", "exe_path": "C:/no/such.exe"}],
                   "settings": {}}, f)
    orig_cfg, orig_legacy = am.CONFIG_PATH, am.LEGACY_CONFIG_PATH
    am.CONFIG_PATH = cfg
    am.LEGACY_CONFIG_PATH = os.path.join(tmp, "legacy_absent.json")
    try:
        mgr = AppManager()
        ball = FloatingBall(mgr)
        # 拆分后三模块协作：球视觉 / 菜单 Mixin / 面板都已就位
        assert ball._ball is not None, "BallVisual 未挂上"
        assert callable(ball._show_menu), "菜单 Mixin 未挂上"
        assert callable(ball._on_item_context_menu)
        assert ball._panel is not None
        # 【回归·v2.2.4】配置球径==默认42时控件也必须有正确几何
        # （set_ball_size 对 d==42 早退，曾致 BallVisual 停留在 100×30）
        assert (ball._ball.width(), ball._ball.height()) == \
            (ball._ball._win_d, ball._ball._win_d), \
            f"BallVisual 初始几何错误: {ball._ball.width()}x{ball._ball.height()}"
        assert ball.width() == ball.height() == ball._win_d, \
            f"浮球窗口初始几何错误: {ball.width()}x{ball.height()}"
        # 球体可离屏渲染出非空位图
        pm = ball._ball.grab()
        assert not pm.isNull() and pm.width() > 0, "BallVisual 渲染失败"
        # 不进入事件循环，手动停掉已启动的定时器后交还 GC
        ball._run_timer.stop()
        ball._hide_timer.stop()
        ball._ball._breath_timer.stop()
    finally:
        am.CONFIG_PATH = orig_cfg
        am.LEGACY_CONFIG_PATH = orig_legacy


# --------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------

ALL_TESTS = (
    test_theme_constants,
    test_menu_style,
    test_icon_cache_clean,
    test_crash_log_rotate,
    test_ball_split,
)


def main() -> int:
    failed = []
    for fn in ALL_TESTS:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed.append(fn.__name__)
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:                     # noqa: BLE001
            failed.append(fn.__name__)
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    total = len(ALL_TESTS)
    print(f"--- {total - len(failed)}/{total} passed ---")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck —— 桌面快捷启动悬浮球（独立应用入口）
====================================================================
形态（v4 方案）：
  · 42px 悬浮球贴桌面边缘，中心四方块图标
  · 悬停/点击浮球 → 72px 横滑面板滑出（图标 + 名称，横向滚动）
  · 右键浮球/面板 → 设置 / 退出
  · 设置窗：应用增删移 + 图标大小/面板透明度/动画速度

运行：python main.py
退出：右键菜单「退出」（关闭浮球窗口即退出）
====================================================================
"""

import sys
import os
import ctypes
import traceback
import datetime

from PyQt6.QtWidgets import QApplication

from core.app_manager import AppManager
from ui.floating_ball import FloatingBall

# 单实例锁：Windows 命名互斥体，防止重复启动
_MUTEX_NAME = "Global\\LaunchDeck_SingleInstance"
_mutex_handle = None


def _acquire_single_instance() -> bool:
    """尝试获取单实例锁；已运行则返回 False。"""
    global _mutex_handle
    kernel32 = ctypes.windll.kernel32
    kernel32.SetLastError(0)
    _mutex_handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(_mutex_handle)
        _mutex_handle = None
        return False
    return True


def _crash_log_path() -> str:
    """崩溃日志路径：exe 旁边（打包）/ 项目根（开发）。"""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "crash.log")


def _excepthook(exc_type, exc_value, exc_tb):
    """全局未捕获异常兜底：写崩溃日志，避免打包后异常静默丢失、程序闪退。"""
    try:
        lines = [
            "=" * 68,
            f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"Unhandled exception:",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        ]
        with open(_crash_log_path(), "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass    # 日志本身绝不二次崩溃
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def main():
    if not _acquire_single_instance():
        # 已有实例运行，弹出提示并退出
        ctypes.windll.user32.MessageBoxW(
            None, "LaunchDeck 已在运行中，请勿重复启动。",
            "LaunchDeck", 0x30 | 0x1000,  # MB_ICONWARNING | MB_SYSTEMMODAL
        )
        sys.exit(0)

    app = QApplication(sys.argv)
    # 全局异常兜底：尽早安装（含 QApplication 之后、业务逻辑之前）
    sys.excepthook = _excepthook
    app.setApplicationName("LaunchDeck")
    app.setQuitOnLastWindowClosed(True)   # 浮球窗口关闭 = 程序退出
    # Fusion 样式完整支持 QSS（Windows 原生样式对滑杆等控件的
    # QSS 支持不完整，会漏出原生黑色边框）
    app.setStyle("Fusion")

    manager = AppManager()
    ball = FloatingBall(manager)
    ball.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

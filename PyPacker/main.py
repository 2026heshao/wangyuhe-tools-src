# -*- coding: utf-8 -*-
"""
PyPacker - Python一键EXE打包工具
程序入口
基于 PyQt6 + PyInstaller 的可视化GUI打包工具
"""

import sys
import os
import ctypes

# 确保程序所在目录在搜索路径中
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon

from ui_main import MainWindow


def _resource_path(name):
    """兼容源码与打包(frozen)环境，返回资源文件的绝对路径"""
    if getattr(sys, "frozen", False):
        candidates = [
            getattr(sys, "_MEIPASS", ""),      # 打包捆绑资源目录
            os.path.dirname(sys.executable),   # exe 所在目录
        ]
    else:
        candidates = [os.path.dirname(os.path.abspath(__file__))]
    for base in candidates:
        if not base:
            continue
        path = os.path.join(base, name)
        if os.path.exists(path):
            return path
    return os.path.join(candidates[-1] if candidates else ".", name)


# 应用图标路径（兼容源码与打包环境，与程序同目录）
APP_ICON = _resource_path("PyPacker.ico")


def main():
    # Windows：设置 AppUserModelID，使任务栏显示自定义图标并独立分组（而非默认 Python 图标）
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PyPacker.App")
        except Exception:
            pass

    app = QApplication(sys.argv)

    # 设置应用全局字体
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # 设置应用信息
    app.setApplicationName("PyPacker")
    app.setApplicationDisplayName("PyPacker - Python一键EXE打包工具")
    app.setApplicationVersion("1.0.0")

    # 设置应用图标（窗口左上角标题栏 + 任务栏图标）
    if os.path.exists(APP_ICON):
        app.setWindowIcon(QIcon(APP_ICON))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

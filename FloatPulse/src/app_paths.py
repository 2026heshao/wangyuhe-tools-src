# -*- coding: utf-8 -*-
"""
====================================================================
路径与屏幕辅助函数  -  app_paths
====================================================================
集中管理「获取程序根目录 / 查找图标文件 / 获取主屏几何」等
与运行环境（开发 / PyInstaller 打包）相关的公共辅助逻辑。

从 main_window.py、card_window.py 抽出统一实现，消除重复定义，
便于全项目复用与一致性维护。
"""

import os
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect


def get_base_dir() -> str:
    """获取程序根目录（src/ 的父目录，打包时为 exe 所在目录）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_icon_file() -> str:
    """在多个候选位置查找图标文件，返回找到的第一个有效路径（找不到返回空串）。

    打包（PyInstaller onedir）后 ico 可能位于：
      - sys._MEIPASS（_internal）
      - exe 同级 / exe 父目录
      - png 备用
    开发环境则直接去项目根目录找。
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidates.append(os.path.join(meipass, "FloatPulse.ico"))
            candidates.append(os.path.join(meipass, "FloatPulse.png"))
        candidates.append(os.path.join(exe_dir, "FloatPulse.ico"))
        candidates.append(os.path.join(exe_dir, "FloatPulse.png"))
        candidates.append(os.path.join(exe_dir, "_internal", "FloatPulse.ico"))
        candidates.append(os.path.join(os.path.dirname(exe_dir), "FloatPulse.ico"))
    else:
        base = get_base_dir()
        candidates.append(os.path.join(base, "FloatPulse.ico"))
        candidates.append(os.path.join(base, "FloatPulse.png"))
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return ""


def get_screen_geometry() -> QRect:
    """获取主屏可用工作区。无屏幕环境回退到默认矩形，避免崩溃。"""
    screen = QApplication.primaryScreen()
    if screen is not None:
        return screen.availableGeometry()
    return QRect(0, 0, 1920, 1080)

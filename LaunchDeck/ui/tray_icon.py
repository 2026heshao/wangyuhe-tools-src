# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck v2.1  -  系统托盘图标（ui/tray_icon）
====================================================================
职责：
  · 常驻系统托盘的图标 + 右键菜单（对标 BoBar / Flow.Launcher 标配）
      - 显示 / 隐藏悬浮球（与全局热键同逻辑，复用 ball.toggle_visible）
      - 设置…（复用 ball._open_settings）
      - 退出
  · 左键 / 双击托盘图标 = 切换悬浮球显隐（隐藏后从托盘一键找回）

设计要点：
  · 只做"转发层"：所有行为都调用 FloatingBall 既有方法，不持有状态，
    保证托盘、热键、右键菜单三条入口行为完全一致
  · 图标来源：项目根目录 111.ico；缺失时回退 Qt 内置图标（不崩溃）
====================================================================
"""

import os

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QSystemTrayIcon, QApplication, QStyle

from ui.settings_dialog import make_styled_menu   # 【v2.2.2】统一深色菜单


def _default_icon() -> QIcon:
    """托盘图标：优先项目根目录 111.ico，缺失/失败回退内置通用图标。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ico_path = os.path.join(root, "111.ico")
    if os.path.exists(ico_path):
        icon = QIcon(ico_path)
        if not icon.isNull():
            return icon
    app = QApplication.instance()
    if app is not None:
        return app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    return QIcon()


class LaunchTray(QSystemTrayIcon):
    """系统托盘图标。所有动作转发给 FloatingBall，自身不持有业务状态。"""

    def __init__(self, ball, parent: QObject | None = None):
        super().__init__(_default_icon(), parent)
        self._ball = ball

        menu = make_styled_menu()        # 【v2.2.2】与设置窗统一的深色菜单
        act_toggle = QAction("显示 / 隐藏悬浮球", menu)
        act_toggle.triggered.connect(self._ball.toggle_visible)
        menu.addAction(act_toggle)

        act_settings = QAction("设置…", menu)
        act_settings.triggered.connect(self._ball._open_settings)
        menu.addAction(act_settings)

        menu.addSeparator()
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_quit)

        self.setContextMenu(menu)
        self.setToolTip("LaunchDeck 快捷启动")
        # 左键单击 / 双击托盘图标 = 切换悬浮球显隐
        self.activated.connect(self._on_activated)
        self.show()

    def _on_activated(self, reason):
        try:
            if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                          QSystemTrayIcon.ActivationReason.DoubleClick):
                self._ball.toggle_visible()
        except Exception:
            pass

# -*- coding: utf-8 -*-
"""
====================================================================
全局快速捕捉条  -  QuickCaptureWindow
====================================================================
热键呼出的屏幕居中迷你输入框：一句话 → 碎片池，Esc 消失。
不开主窗口即可随手记一笔。

设计要点：
  1. 无边框 + 置顶 + Tool 提示窗（不在任务栏出现）
  2. 回车提交：fragment_manager.add_clipboard_text(content, source="快速捕捉")
  3. Esc 或失焦自动隐藏
  4. 显示位置：鼠标当前所在屏幕居中（多显示器友好）
  5. 样式跟随主题（apply_theme 由外部在主题切换时调用）
====================================================================
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QCursor, QKeyEvent
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel

from src.theme import get_colors


class QuickCaptureWindow(QWidget):
    """全局快速捕捉输入条"""

    capture_submitted = pyqtSignal(str)   # 回车提交时发射（内容文本）
    capture_hidden = pyqtSignal()         # 隐藏时发射（可用于提示）

    WIDTH = 560
    HEIGHT = 56

    def __init__(self, fragment_manager, theme: str = "dark", parent=None):
        super().__init__(parent)
        self._fm = fragment_manager
        self._theme = theme

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool          # 不在任务栏显示
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        self._input = QLineEdit()
        self._input.setPlaceholderText("⚡ 快速捕捉：输入后回车存入碎片池，Esc 关闭")
        self._input.setFixedHeight(self.HEIGHT - 12)
        self._input.returnPressed.connect(self._submit)
        layout.addWidget(self._input, 1)

        hint = QLabel("Enter ↵")
        hint.setObjectName("quickCaptureHint")
        layout.addWidget(hint)

        self.apply_theme(self._theme)

    # ---------------- 显示 / 隐藏 ----------------
    def show_centered(self):
        """在鼠标所在屏幕居中显示并获得焦点"""
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(
                geo.x() + (geo.width() - self.WIDTH) // 2,
                geo.y() + (geo.height() - self.HEIGHT) // 3,
            )
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def toggle(self):
        """热键切换：可见 → 隐藏；隐藏 → 居中显示"""
        if self.isVisible():
            self.hide()
        else:
            self.show_centered()

    # ---------------- 提交 ----------------
    def _submit(self):
        text = self._input.text().strip()
        if not text:
            self.hide()
            return
        try:
            self._fm.add_clipboard_text(text, source="快速捕捉")
        except Exception:
            pass  # 写入失败不崩溃，窗口照常关闭
        self._input.clear()
        self.hide()
        self.capture_submitted.emit(text)

    # ---------------- 事件 ----------------
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self._input.clear()
            self.hide()
            self.capture_hidden.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        """点击其他区域自动收起"""
        super().focusOutEvent(event)
        if self.isVisible():
            self.hide()
            self.capture_hidden.emit()

    # ---------------- 主题 ----------------
    def apply_theme(self, theme_name: str):
        """跟随主题刷新配色"""
        self._theme = theme_name
        c = get_colors(theme_name)
        self._input.setStyleSheet(
            f"QLineEdit {{"
            f" background: {c.get('card_bg_solid', '#FFFFFF')};"
            f" color: {c.get('text', '#2C3E50')};"
            f" border: 1px solid {c.get('primary_border', 'transparent')};"
            f" border-radius: 14px;"
            f" padding: 0 16px;"
            f" font-size: 14px;"
            f" selection-background-color: {c.get('primary', '#5BC0BE')};"
            f" }}"
            f"QLineEdit::placeholder {{ color: {c.get('text_placeholder', '#AAB4BF')}; }}"
        )
        hint = self.findChild(QLabel, None)
        if hint is not None:
            hint.setStyleSheet(
                f"color: {c.get('text_secondary', '#8B96A3')};"
                f"font-size: 11px; padding-right: 12px; background: transparent;"
            )

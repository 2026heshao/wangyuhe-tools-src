# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck 悬浮球  -  BallMenus（右键菜单，v2.2.3 自 floating_ball 拆出）
====================================================================
职责：
  · 应用项右键菜单（打开/管理员/文件夹/重命名/图标/删除）
  · 浮球/面板共用菜单（设置/退出）
  · 菜单及其后续模态对话框关闭后的自动收回裁决

形态：Mixin —— 方法自 floating_ball 原样迁移挂到 FloatingBall 上，
self 语义与拆分前一致，通过宿主访问 _mgr/_panel/_menu_open/
_hide_timer/_dragging/_pinned/_ms/_apply_settings 等成员。
约束：菜单打开期间 _menu_open 置位（防面板误收），finally 统一裁决。
====================================================================
"""

import os

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QInputDialog, QFileDialog, QMessageBox

from core.app_manager import launch_app, _launch_elevated, clear_icon_cache
from ui import anim_tokens as atk
from ui.settings_dialog import make_styled_menu


class BallMenuMixin:
    """FloatingBall 的右键菜单能力（宿主提供 _mgr/_panel/_menu_open/
    _hide_timer/_dragging/_pinned/_ms/_apply_settings 等成员）。"""

    # ================================================================
    # 【右键应用项菜单】打开 / 管理员运行 / 打开所在文件夹 / 重命名 / 删除
    # ================================================================
    def _on_item_context_menu(self, index: int, global_pos):
        apps = self._mgr.apps
        if not (0 <= index < len(apps)):
            return
        app = apps[index]
        pos = QPoint(*global_pos) if isinstance(global_pos, tuple) else global_pos
        menu = make_styled_menu(self)    # 【v2.2.2】与设置窗统一的深色菜单
        act_open = menu.addAction("打  开")
        act_admin = menu.addAction("以管理员运行")
        act_folder = menu.addAction("打开所在文件夹")
        menu.addSeparator()
        act_rename = menu.addAction("重  命  名")
        # 【v2.1】自定义图标：仅当已设置时提供恢复项
        act_icon = menu.addAction("更换图标…")
        act_icon_reset = (
            menu.addAction("恢复默认图标")
            if app.get("custom_icon") else None)
        menu.addSeparator()
        act_delete = menu.addAction("删  除")

        # 【右键菜单防误收】置位 _menu_open 并停掉挂起的隐藏定时器；
        # exec 返回后仍保持置位，直到菜单动作处理（重命名/删除确认等
        # 后续模态对话框）全部完成，最后统一做位置裁决。
        self._menu_open = True
        self._hide_timer.stop()
        try:
            act = menu.exec(pos)
            if act == act_open:
                launch_app(app.get("exe_path", ""), app.get("name", ""), parent=self)
            elif act == act_admin:
                exe = app.get("exe_path", "")
                if exe and os.path.exists(exe):
                    _launch_elevated(exe, app.get("name", ""), self)
            elif act == act_folder:
                exe = app.get("exe_path", "")
                folder = os.path.dirname(exe) if exe else ""
                if folder and os.path.isdir(folder):
                    try:
                        os.startfile(folder)
                    except Exception:
                        pass
            elif act == act_rename:
                new_name, ok = QInputDialog.getText(
                    self, "重命名", "输入新的名称：", text=app.get("name", ""))
                if ok and new_name.strip():
                    app["name"] = new_name.strip()
                    self._mgr.save()
                    clear_icon_cache()
                    self._need_rebuild = True
                    self._apply_settings()
            elif act == act_icon:
                # 【v2.1】更换图标：PNG/ICO 任意尺寸自适应（render_app_icon 已内置
                # custom_icon 支持），落 custom_icon 字段并清缓存重建
                path, _ = QFileDialog.getOpenFileName(
                    self, "选择图标文件", "",
                    "图标文件 (*.png *.ico *.jpg *.jpeg *.bmp)")
                if path:
                    app["custom_icon"] = path
                    self._mgr.save()
                    clear_icon_cache()
                    self._need_rebuild = True
                    self._apply_settings()
            elif act_icon_reset is not None and act == act_icon_reset:
                app.pop("custom_icon", None)
                self._mgr.save()
                clear_icon_cache()
                self._need_rebuild = True
                self._apply_settings()
            elif act == act_delete:
                # 【v2】删除二次确认，防误触
                ret = QMessageBox.question(
                    self, "删除应用",
                    f"确定删除「{app.get('name', '')}」吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if ret != QMessageBox.StandardButton.Yes:
                    return
                apps.pop(index)
                self._mgr.save()
                clear_icon_cache()
                self._need_rebuild = True
                self._apply_settings()
                if self._panel.isVisible():
                    self._panel.place_beside(self.frameGeometry(),
                                             self._current_screen())
        finally:
            self._menu_open = False
            self._adjudicate_after_menu()

    # ================================================================
    # 右键菜单（浮球与面板共用）
    # ================================================================
    def _show_menu(self, global_pos):
        pos = QPoint(*global_pos) if isinstance(global_pos, tuple) else global_pos
        menu = make_styled_menu(self)    # 【v2.2.2】与设置窗统一的深色菜单
        act_settings = menu.addAction("设  置")
        menu.addSeparator()
        act_quit = menu.addAction("退  出")
        # 【右键菜单防误收】与 _on_item_context_menu 相同的置位/裁决包裹
        self._menu_open = True
        self._hide_timer.stop()
        try:
            act = menu.exec(pos)
            if act == act_settings:
                self._open_settings()
            elif act == act_quit:
                self._panel.close()
                QApplication.quit()
        finally:
            self._menu_open = False
            self._adjudicate_after_menu()

    def _adjudicate_after_menu(self):
        """【右键菜单防误收】菜单及其后续对话框全部关闭后的位置裁决。

        - 常驻面板 / 面板已不可见 / 拖拽中：维持原状，不做自动收回；
        - 鼠标仍停在球体或面板上：维持显示（后续 enter/leave 事件照常接管）；
        - 否则按原有 HIDE_DELAY 延迟收回，保持既有交互手感不残留。
        """
        try:
            if self._pinned or not self._panel.isVisible():
                return
            if self._dragging or self._panel._drag_active:
                return
            gp = QCursor.pos()
            if (self.frameGeometry().contains(gp)
                    or self._panel.frameGeometry().contains(gp)):
                return
            self._hide_timer.start(self._ms(atk.HIDE_DELAY_MS))
        except Exception:
            pass

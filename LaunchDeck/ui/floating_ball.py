# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck 悬浮球  -  FloatingBall（窗口 + 整体交互控制）
====================================================================
v4 方案规格：
  · 42px 正圆，背景 #24262D，悬停 #2C2F38 + scale 1.1
  · 中心 2×2 四方块图标（首次定稿样式）
  · 软投影 0 2px 8px rgba(0,0,0,0.35)，无发光无边框
  · 拖动松手自动吸附最近左右边缘（QPropertyAnimation）
  · 贴左缘 → 面板向右滑出；贴右缘 → 向左滑出
  · 左键点击 = 固定/取消固定面板；右键菜单 = 设置 / 退出
  · 悬停显示面板，鼠标移开（含面板）自动收回

【v2.2.3 拆分】
  · ui/ball_visual.py  —— BallVisual：球体纯视觉（绘制/动效/贴图/球径）
  · ui/ball_menus.py   —— BallMenuMixin：应用项/浮球右键菜单 + 收回裁决
  · 本文件             —— FloatingBall：窗口、吸附拖拽、面板调度、设置联动
====================================================================
"""

import os

from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QEvent,
    QAbstractAnimation,
)
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QApplication, QGraphicsDropShadowEffect, QMessageBox,
    QSystemTrayIcon,
)

from core.app_manager import (
    AppManager, launch_app, make_app_from_path, clear_icon_cache,
)
from core import process_utils
from core.hotkey import GlobalHotkeyFilter
from ui import anim_tokens as atk
from ui import theme as ui_theme
from ui.slide_panel import SlidePanel
from ui.settings_dialog import SettingsDialog
from ui.ball_visual import BallVisual, WIN_D
from ui.ball_menus import BallMenuMixin


class FloatingBall(BallMenuMixin, QWidget):
    """
    悬浮球窗口 + 全局交互控制（面板显示/吸附/菜单/设置）。
    """

    def __init__(self, manager: AppManager, hotkey_filter: "GlobalHotkeyFilter | None" = None):
        super().__init__()
        self._mgr = manager
        self._hotkey = hotkey_filter    # 【v2】全局热键过滤器（main 注入）
        self._tray = None               # 【v2.1】托盘图标引用（main 注入，用于隐藏气泡）
        self._pinned = False          # 面板是否固定
        # 【右键菜单防误收】任一菜单（应用项菜单/球菜单）打开期间为 True，
        # 所有自动隐藏入口（leaveEvent / hover_left / _hide_panel）一律跳过，
        # 防止鼠标从面板移向独立顶层菜单（含两者间空隙）时面板提前收起。
        self._menu_open = False
        self._dragging = False
        self._press_pos = QPoint()
        self._press_glob = QPoint()
        self._moved = False
        self._snap_anim = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._win_d = WIN_D              # 【v2.1.3】窗口边长随球径（球+24px）
        self.setFixedSize(self._win_d, self._win_d)
        self.setAcceptDrops(True)        # 拖文件到浮球也可直接添加

        # 球体子控件 + 投影
        # 【顿挫根修】球体占满整个窗口，缩放由 paintEvent 的
        # QPainter.scale 浮点完成，最大缩放不越界。
        self._ball = BallVisual(self)
        self._apply_ball_size()          # 【v2.1.3】按配置应用球径（窗口/缓存同步）
        self._ball_shadow = QGraphicsDropShadowEffect(self)
        self._ball_shadow.setBlurRadius(8)
        self._ball_shadow.setOffset(0, 2)
        self._ball_shadow.setColor(QColor(0, 0, 0, 89))     # rgba(0,0,0,0.35)
        self._ball.setGraphicsEffect(self._ball_shadow)

        # 面板
        self._panel = SlidePanel()
        self._panel.hover_entered.connect(self._on_panel_entered)
        self._panel.hover_left.connect(self._on_panel_left)
        self._panel.request_menu.connect(self._show_menu)
        self._panel.launch_requested.connect(self._on_launch)
        # 【拖拽添加 / 排序 / 右键菜单】
        self._panel.files_dropped.connect(self._on_files_dropped)
        self._panel.apps_reorder.connect(self._on_apps_reorder)
        self._panel.item_context_menu_requested.connect(self._on_item_context_menu)

        # 面板自动收回计时器
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_panel)

        # 面板重建脏标记（滑杆拖动时不重复重建，避免卡顿）
        self._need_rebuild = True
        self._applied_icon_size = -1

        # 【v2.1】运行状态轮询：每 2s 快照一次进程表（有缓存，开销极低）
        self._run_timer = QTimer(self)
        self._run_timer.setInterval(2000)
        self._run_timer.timeout.connect(self._refresh_running)
        self._run_timer.start()

        self._apply_settings()
        self._restore_position()

        # 【v2.1】智能排序开启时，启动即按使用频率重排一次
        #（在首次 set_apps 之前执行，保证初始显示顺序即频率序）
        if bool(self._mgr.settings.get("smart_sort", False)):
            self._mgr.resort_by_usage()

        # 恢复“面板常驻显示”状态：仅控制“展开后是否自动收回”，
        # 【修复·问题3】不再在启动时自动展开面板（用户未预期此行为）
        self._pinned = bool(self._mgr.settings.get("panel_pinned", False))

        # ----【新增·需求1】闲置呼吸调度 ----
        self._app_active = True
        try:
            QApplication.instance().applicationStateChanged.connect(
                self._on_app_state)
        except Exception:
            pass
        self._panel.installEventFilter(self)   # 监听面板显隐 → 联动呼吸
        # 【修复·约束3】hover 动画完全结束后，若已回到闲置态 → 接回呼吸
        self._ball.hover_anim_finished.connect(self._update_idle_pulse)
        self._update_idle_pulse()

    # ================================================================
    # 初始化辅助
    # ================================================================
    def _speed(self) -> float:
        return max(0.5, min(2.0, float(self._mgr.settings.get("anim_speed", 1.0))))

    def _ms(self, base_ms: int) -> int:
        return atk.dur(self._speed(), base_ms)

    def _apply_theme(self):
        """【v2.1.2】按当前设置把主题同步到面板与球体。"""
        name = str(self._mgr.settings.get("theme", "dark") or "dark")
        self._panel.set_theme(name)
        self._ball.set_theme_colors(ui_theme.get())

    def _apply_settings(self):
        """按配置刷新面板视觉；仅在列表/图标大小变化时重建图标项。"""
        icon_size = int(self._mgr.settings.get("icon_size", 40))
        opacity = float(self._mgr.settings.get("panel_opacity", 0.87))
        self._panel.set_anim_speed(self._speed())
        self._ball.set_anim_speed(self._speed())
        self._panel.set_opacity(opacity)
        # 【光影开关】设置同步到球体光效
        self._ball.set_glow_enabled(
            bool(self._mgr.settings.get("show_glow", True)))
        # 【v2.1.3】悬浮球大小同步（设置关闭兜底时也走这里）
        self._apply_ball_size()
        # 【v2.1】主题 + 鱼眼开关同步（v2.1.2 起球体一并换肤）
        self._apply_theme()
        # 【v2.2】悬浮球自定义贴图同步（路径失效时 set_ball_image 内部静默回退）
        self._ball.set_ball_image(
            str(self._mgr.settings.get("ball_image", "") or ""))
        self._panel.set_fisheye_enabled(
            bool(self._mgr.settings.get("hover_fisheye", True)))
        if self._need_rebuild or icon_size != self._applied_icon_size:
            self._panel.set_apps(self._mgr.apps, icon_size)
            self._applied_icon_size = icon_size
            self._need_rebuild = False
        self._resize_panel()

    def set_tray(self, tray):
        """【v2.1】注入托盘图标引用（首次隐藏气泡用）。"""
        self._tray = tray

    def _refresh_running(self):
        """【v2.1】刷新面板运行中指示（一次进程快照判断全部条目）。"""
        try:
            self._panel.update_running(
                process_utils.running_set_for(self._mgr.apps))
        except Exception:
            pass

    def _restore_position(self):
        """恢复上次位置；无记录时放主屏左缘垂直居中。"""
        screen = QApplication.primaryScreen().availableGeometry()
        x = self._mgr.settings.get("ball_x")
        y = self._mgr.settings.get("ball_y")
        if isinstance(x, int) and isinstance(y, int):
            self.move(x, y)
            self._clamp_into(screen)
        else:
            self.move(screen.left() + 2,
                      screen.center().y() - self._win_d // 2)

    def _clamp_into(self, avail):
        """把窗口位置夹进屏幕可用区域内。"""
        x = max(avail.left() - 6, min(self.x(), avail.right() - self._win_d + 6))
        y = max(avail.top() - 6, min(self.y(), avail.bottom() - self._win_d + 6))
        self.move(x, y)

    # ----【v2.1.3】悬浮球大小 ----
    def _apply_ball_size(self):
        """按配置应用悬浮球直径：窗口同步缩放，保持球心位置不动。"""
        try:
            d = int(self._mgr.settings.get("ball_size", 42))
        except (TypeError, ValueError):
            d = 42
        old = self._win_d
        if self._ball.set_ball_size(d):
            self._win_d = self._ball._win_d
        if self.width() != self._win_d or self.height() != self._win_d:
            dx = (old - self._win_d) // 2
            self.move(self.x() + dx, self.y() + dx)   # 球心不动
            self.setFixedSize(self._win_d, self._win_d)
            self._ball.setGeometry(0, 0, self._win_d, self._win_d)
            self._clamp_into(self._current_screen())

    def _current_screen(self):
        """浮球当前所在屏幕（跨屏拖动后以实际所在屏为准）。"""
        screen = QApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()
        return screen.availableGeometry()

    # ================================================================
    # 【新增·需求1】闲置呼吸动画调度
    # ================================================================
    def _idle_pulse_allowed(self) -> bool:
        """闲置判定：光影开关 + 呼吸开关 + 应用激活 + 无悬停 + 无拖拽 + 面板收回。
        【右键菜单防误收】菜单打开期间球体保持静止（不呼吸），视觉更稳定。"""
        try:
            return (self._ball._glow_enabled
                    and bool(self._mgr.settings.get("enable_idle_pulse", True))
                    and self._app_active
                    and not self._menu_open
                    and not self.underMouse()
                    and not self._dragging
                    and not self._panel.isVisible())
        except Exception:
            return False

    def _update_idle_pulse(self):
        """按当前状态启停呼吸动画（全部 try 包裹，任何异常不崩溃）。

        【修复·约束3】启动前置条件：hover 动画必须已完全停止——
        若淡出动画仍在运行则本次跳过，由 hover_anim_finished 信号
        触发再次评估后再启动，绝不与 hover 动画并发操作 scale。
        """
        try:
            if self._idle_pulse_allowed():
                if (self._ball._anim.state()
                        == QAbstractAnimation.State.Stopped):
                    self._ball.start_idle_pulse()
                # hover 未结束：等待 hover_anim_finished 回调接管
            else:
                self._ball.stop_idle_pulse()
        except Exception:
            pass

    def _on_app_state(self, state):
        """【修复·问题2】仅真正最小化/隐藏才暂停呼吸。

        悬浮球是桌面悬浮组件，点击其他窗口只会触发 ApplicationInactive
        （普通失焦），不应中断呼吸；只有 ApplicationHidden（最小化/收起）
        才暂停以降低 CPU。恢复激活后按闲置条件续播。
        """
        try:
            if state == Qt.ApplicationState.ApplicationHidden:
                self._app_active = False
                self._ball.pause_idle_pulse()     # 暂停保进度，不销毁
            elif state == Qt.ApplicationState.ApplicationActive:
                self._app_active = True
                self._update_idle_pulse()         # 满足闲置 → resume 原位续播
            # ApplicationInactive：刻意忽略，保持呼吸不中断
        except Exception:
            pass

    def eventFilter(self, obj, event):
        """监听面板显隐：面板显示→停呼吸；收回动画结束隐藏→恢复呼吸。"""
        try:
            if obj is self._panel and event.type() in (
                    QEvent.Type.Show, QEvent.Type.Hide):
                self._update_idle_pulse()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    # ================================================================
    # 面板控制
    # ================================================================
    def _resize_panel(self):
        icon_size = int(self._mgr.settings.get("icon_size", 40))
        avail = self._current_screen()
        self._panel.compute_size(self._mgr.apps, icon_size, avail.width())

    def _show_panel(self):
        if self._dragging or self._panel.isVisible():
            return
        self._hide_timer.stop()
        self._resize_panel()
        direction = self._panel.place_beside(self.frameGeometry(),
                                             self._current_screen())
        self._panel.slide_in(direction)
        self._update_idle_pulse()          # 【新增】面板打开 → 停呼吸

    def _hide_panel(self):
        # 【右键菜单防误收】菜单（或其后续模态对话框）打开期间禁止自动收回
        if self._menu_open:
            return
        self._panel.slide_out()

    def _on_ball_clicked(self):
        """左键点击浮球：仅在「展开 / 收回」面板间切换。

        【v2.1 变更】原实现点击会把面板置为常驻（_toggle_pin），
        用户反馈误触频繁，已按需求移除——面板常驻现在只能通过
        设置窗里的「面板常驻显示」开关控制。
        """
        if self._pinned:
            return                  # 常驻态由设置开关管理，点击不干预
        if self._panel.isVisible():
            self._hide_timer.stop()
            self._hide_panel()
        else:
            self._show_panel()

    def _set_pinned(self, pinned: bool):
        """切换面板固定态：固定→立即展开；取消→立即收回。"""
        self._pinned = pinned
        if pinned:
            self._show_panel()
        else:
            self._hide_timer.stop()
            self._hide_panel()

    def _on_panel_entered(self):
        self._hide_timer.stop()

    def _on_panel_left(self):
        # 【右键菜单防误收】鼠标离开面板去往右键菜单（含空隙）时不启动隐藏
        if self._menu_open:
            return
        if not self._pinned and not self._panel._drag_active:
            self._hide_timer.start(self._ms(atk.HIDE_DELAY_MS))

    def _on_launch(self, index: int):
        apps = self._mgr.apps
        if 0 <= index < len(apps):
            app = apps[index]
            exe = app.get("exe_path", "")
            # 【v2.1】已在运行 → 前置窗口而非重复启动（前置失败再正常启动）
            if process_utils.is_running(exe) and process_utils.activate_window(exe):
                self._mgr.record_launch(index)
                return
            launch_app(exe, app.get("name", ""), parent=self)
            # 【v2.1】使用频率统计：始终记录（count + last_launch）；
            # 智能排序开启且顺序确实变化时，重排列表并重建面板。
            self._mgr.record_launch(index)
            if (bool(self._mgr.settings.get("smart_sort", False))
                    and self._mgr.resort_by_usage()):
                self._need_rebuild = True
                self._apply_settings()
                if self._panel.isVisible():
                    self._panel.place_beside(self.frameGeometry(),
                                             self._current_screen())

    # ================================================================
    # 【拖拽添加】外部文件拖入面板/浮球 → 自动加入配置
    # ================================================================
    def _on_files_dropped(self, paths: list):
        """把拖入的文件列表转为应用条目并追加；有新增则重建面板。"""
        added = []
        for p in paths:
            app = make_app_from_path(p)
            if app is None:
                continue
            # 去重：相同 exe_path 不重复添加
            if any(a.get("exe_path", "") == app.get("exe_path", "")
                   for a in self._mgr.apps):
                continue
            self._mgr.apps.append(app)
            added.append(app.get("name", ""))
        if added:
            self._mgr.save()
            clear_icon_cache()
            self._need_rebuild = True
            self._apply_settings()
            if self._panel.isVisible():
                self._panel.place_beside(self.frameGeometry(),
                                         self._current_screen())

    # ================================================================
    # 【拖拽排序】面板内拖拽重排列表顺序
    # ================================================================
    def _on_apps_reorder(self, frm: int, to: int):
        apps = self._mgr.apps
        if not (0 <= frm < len(apps)):
            return
        # 计算实际插入位置（to 为落点下标，frm 移除后需修正）
        item = apps.pop(frm)
        if to > frm:
            to -= 1
        to = max(0, min(to, len(apps)))
        apps.insert(to, item)
        self._mgr.save()
        self._need_rebuild = True
        self._apply_settings()
        if self._panel.isVisible():
            self._panel.place_beside(self.frameGeometry(),
                                     self._current_screen())

    # ================================================================
    # 拖动 / 点击 / 吸附
    # ================================================================
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._press_glob = event.globalPosition().toPoint()
            self._moved = False
            self._ball.set_pressed(True)      # 【动效优化】按下缩小
            event.accept()   # 接受按下 → 获得隐式鼠标抓取，拖出窗口也不断流
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            glob = event.globalPosition().toPoint()
            if not self._moved and (glob - self._press_glob).manhattanLength() > 6:
                self._moved = True
                self._dragging = True
                self._ball.set_pressed(False)   # 【动效优化】拖拽开始 → 取消按下态
                self._ball.set_dragging(True)   # 【动效优化】拖拽态：放大+阴影增强
                self._ball_shadow.setBlurRadius(24)
                self._ball_shadow.setOffset(0, 8)
                # 拖动开始：面板立即收回（含固定态）
                self._hide_timer.stop()
                self._panel.hide()
                self._update_idle_pulse()      # 【新增】拖拽中 → 停呼吸
            if self._dragging:
                target = glob - self._press_pos
                avail = self._current_screen()
                # 【新增·拖拽弹性回弹】越界跟随衰减（橡皮筋）：鼠标拖出
                # 边界后，浮球只以约 25% 跟进，制造拉伸阻力感；松手由
                # _snap_to_edge 的 OutBack 弹性吸附归位。仍在界内行为不变。
                # 允许少量越界（1.5 倍窗口），避免彻底被拉出屏幕不可控。
                margin = 6
                xlo, xhi = avail.left() - margin, avail.right() - self._win_d + margin
                ylo, yhi = avail.top() - margin, avail.bottom() - self._win_d + margin
                x = self._rubber_band(target.x(), xlo, xhi)
                y = self._rubber_band(target.y(), ylo, yhi)
                self.move(x, y)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._ball.set_pressed(False)     # 【动效优化】释放回弹（拖拽/点击都触发）
            if self._dragging:
                self._dragging = False
                self._ball.set_dragging(False)  # 【动效优化】拖拽结束：恢复大小+阴影
                self._ball_shadow.setBlurRadius(8)
                self._ball_shadow.setOffset(0, 2)
                self._snap_to_edge()
                self._update_idle_pulse()      # 【新增】松手后按状态恢复
            elif not self._moved:
                self._on_ball_clicked()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _rubber_band(self, value: int, lo: int, hi: int) -> int:
        """橡皮筋：界内原样；越界后只跟 25% 位移，制造弹性拉伸感。"""
        if value < lo:
            return int(lo - (lo - value) * 0.25)
        if value > hi:
            return int(hi + (value - hi) * 0.25)
        return value

    def _snap_to_edge(self):
        """松手后吸附到最近的左右边缘（垂直位置保持），并记住位置。"""
        avail = self._current_screen()
        center_x = self.x() + self._win_d / 2
        target_x = (avail.left() + 2 if center_x <= avail.center().x()
                    else avail.right() - self._win_d + 2 - 2)
        # 【新增】拖拽可能已越界（橡皮筋），吸附时把 y 也夹回界内，
        # 保证松手后完整落回屏幕，不残留边界外。
        y = max(avail.top() - 6,
                min(self.y(), avail.bottom() - self._win_d + 6))

        self._snap_anim = atk.play(
            self, b"pos", "ball.snap", self._speed(),
            start=self.pos(), end=QPoint(target_x, y),
            on_finished=self._save_position)

        # 固定态下重新展开面板（方向随吸附边自动翻转）
        if self._pinned:
            QTimer.singleShot(self._ms(230), self._show_panel)

    def _save_position(self):
        self._mgr.set_setting("ball_x", self.x())
        self._mgr.set_setting("ball_y", self.y())

    # ================================================================
    # 悬停
    # ================================================================
    def enterEvent(self, event):
        self._ball.set_hover(True)
        self._update_idle_pulse()          # 悬停 → 停呼吸
        self._show_panel()                 # 【修复·问题3】hover 总是展开面板
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._ball.set_hover(False)
        self._update_idle_pulse()          # 离开后（面板收回时）恢复呼吸
        # 【右键菜单防误收】菜单打开期间鼠标移向菜单会触发本事件，不启动隐藏
        if not self._pinned and not self._menu_open:
            self._hide_timer.start(self._ms(atk.HIDE_DELAY_MS))
        super().leaveEvent(event)

    # ================================================================
    # 【拖拽添加】拖文件到浮球本体也能直接加入
    # ================================================================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasUrls():
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
            if paths:
                self._on_files_dropped(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    # ================================================================
    # 右键菜单（浮球与面板共用）—— 实现在 ui/ball_menus.py 的 Mixin
    # ================================================================
    def contextMenuEvent(self, event):
        self._show_menu(event.globalPos())

    # ================================================================
    # 【v2】全局热键：显示 / 隐藏悬浮球
    # ================================================================
    def toggle_visible(self):
        """全局热键/托盘触发：显示/隐藏悬浮球（隐藏时面板一并收回、动画停止省 CPU）。"""
        try:
            if self.isVisible():
                self._hide_timer.stop()
                self._panel.hide()
                self._ball.stop_idle_pulse()
                self.hide()
                self._maybe_show_hidden_tip()
            else:
                self.show()
                self.raise_()
                self._update_idle_pulse()
        except Exception:
            pass

    def _maybe_show_hidden_tip(self):
        """【v2.1】首次隐藏时托盘冒泡，防止用户以为程序消失了。只提示一次。"""
        try:
            if bool(self._mgr.settings.get("hidden_tip_shown", False)):
                return
            self._mgr.set_setting("hidden_tip_shown", True)
            if self._tray is not None:
                self._tray.showMessage(
                    "LaunchDeck",
                    "悬浮球已隐藏：点托盘图标或再按快捷键即可找回",
                    QSystemTrayIcon.MessageIcon.Information, 4000)
        except Exception:
            pass

    def _apply_hotkey(self, seq_str: str):
        """按设置重注册全局热键；失败弹提示（组合键被占用或无效）。"""
        if self._hotkey is None:
            return
        if not (seq_str or "").strip():
            self._hotkey.unregister()
            return
        if not self._hotkey.register_sequence(seq_str):
            QMessageBox.warning(
                self, "全局热键",
                f"快捷键「{seq_str}」注册失败（可能已被其他程序占用），"
                "请更换组合键。")

    # ================================================================
    # 设置
    # ================================================================
    def _open_settings(self):
        # 【修复】配置窗弹出 → 立即停呼吸；关闭后满足闲置再恢复
        try:
            self._ball.stop_idle_pulse()
        except Exception:
            pass
        dlg = SettingsDialog(self._mgr, parent=self)
        dlg.apps_changed.connect(self._on_apps_changed)
        dlg.setting_changed.connect(self._on_setting_changed)
        dlg.exec()
        # 兜底：设置关闭后无条件重建侧滑面板，杜绝任何信号时序遗漏
        # 导致面板残留旧列表（仅更改时重排布局，性能开销可忽略）
        self._need_rebuild = True
        self._applied_icon_size = -1
        self._apply_settings()
        self._update_idle_pulse()

    def _on_apps_changed(self):
        """软件列表增删移后：立即重建面板图标（无需重启）。"""
        self._need_rebuild = True
        self._apply_settings()
        if self._panel.isVisible():
            self._panel.place_beside(self.frameGeometry(),
                                     self._current_screen())

    def _on_setting_changed(self, key: str, value):
        if key == "panel_pinned":
            # 常驻开关：立即展开/收回面板
            self._set_pinned(bool(value))
            return
        if key == "smart_sort":         # 【v2.1】智能排序开关：开启即重排一次
            if bool(value):
                self._mgr.resort_by_usage()
            self._on_apps_changed()
            return
        if key == "hover_fisheye":      # 【v2.1】鱼眼开关：立即生效
            self._panel.set_fisheye_enabled(bool(value))
            return
        if key == "ball_size":          # 【v2.1.3】球径：立即生效并重摆面板
            self._apply_ball_size()
            if self._panel.isVisible():
                self._panel.place_beside(self.frameGeometry(),
                                         self._current_screen())
            return
        if key == "theme":              # 【v2.1】主题：面板+球体立即换肤
            self._apply_theme()
            return
        if key == "ball_image":       # 【v2.2】悬浮球贴图：立即切换渲染分支
            self._ball.set_ball_image(str(value or ""))
            return
        if key == "toggle_hotkey":          # 【v2】全局热键：立即重注册
            self._apply_hotkey(str(value))
            return
        if key == "enable_idle_pulse":        # 【新增】呼吸开关：立即生效
            self._update_idle_pulse()
            return
        if key == "show_glow":                # 【新增】光影开关：立即生效
            self._ball.set_glow_enabled(bool(value))
            self._update_idle_pulse()
            return
        # 滑杆类设置已即时持久化，这里即时刷新面板视觉
        self._apply_settings()
        if self._panel.isVisible():
            self._resize_panel()
            self._panel.place_beside(self.frameGeometry(),
                                     self._current_screen())

    # ================================================================
    # 退出清理
    # ================================================================
    def closeEvent(self, event):
        # 退出前停掉定时器/动画，避免销毁瞬间回调访问半销毁对象崩溃
        try:
            self._hide_timer.stop()
        except Exception:
            pass
        try:
            self._ball.stop_idle_pulse()
        except Exception:
            pass
        try:
            if self._snap_anim is not None:
                self._snap_anim.stop()
        except Exception:
            pass
        try:
            self._panel.close()
        except Exception:
            pass
        try:
            if self._hotkey is not None:
                self._hotkey.unregister()   # 【v2】退出注销全局热键
        except Exception:
            pass
        super().closeEvent(event)

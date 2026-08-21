# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck 横滑面板  -  SlidePanel / AppItem
====================================================================
v4 方案规格：
  · 固定高 72px、宽度自适应（上限约 60% 屏宽），圆角 12px
  · 背景 rgba(16,17,21,opacity)（可调），纯 Qt 半透明
  · 横向列表：每项 = 图标(可调 32-42px) + 下方小标签，悬停高亮
    rgba(52,56,66,0.65)
  · 仅横向滚动（滚轮映射），无纵向滚动条
  · 显示/隐藏：从浮球一侧滑入 + 淡入（时长受动画速度设置影响）

窗口外围黑框修复（根源级）：
  1. 顶层窗口只做透明载体：Frameless + Tool + StaysOnTop，
     并在顶层窗口对象上设置 WA_TranslucentBackground（四周
     SHADOW_MARGIN 边距区域因此真透明）
  2. 顶层窗口自身不设置任何 background / border QSS
  3. 背景、圆角、半透明、边框全部由内部唯一子容器 _surface 承载
  4. 已彻底移除 SetWindowCompositionAttribute（亚克力）调用：
     该系统调用作用于整个窗口矩形（含四周边距），会在半透明
     surface 外围染出一圈深色矩形，即顽固黑框的根源，且 QSS
     无法覆盖；也不用定时器/重绘掩盖
====================================================================
"""

from PyQt6.QtCore import (Qt, pyqtSignal, pyqtProperty, QPropertyAnimation,
                          QRect, QRectF, QVariantAnimation,
                          QPoint, QTimer, QSequentialAnimationGroup,
                          QAbstractAnimation, QEasingCurve)
from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QLabel, QHBoxLayout, QFrame,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics

import time

from core.app_manager import extract_app_icon
from ui import anim_tokens as atk

# 面板视觉常量
CLICK_COOLDOWN_MS = 650   # 【新增·需求3】单项点击冷却，防重复启动
PANEL_H = 72          # 面板可见高度
PANEL_RADIUS = 12     # 圆角
SHADOW_MARGIN = 14    # 窗口四周为投影预留的透明边距
ITEM_H = 56           # 单个应用项高度
HOVER_BG = QColor(52, 56, 66, 165)   # 悬停高亮 rgba(52,56,66,0.65)
TEXT_MAIN = QColor(210, 212, 217)
TEXT_DIM = QColor(138, 141, 150)


# ====================================================================
# 单个应用项（图标 + 标签，自绘悬停高亮）
# ====================================================================

class AppItem(QWidget):
    """面板里的一个应用项：上方图标、下方名称，悬停画圆角高亮层。"""

    clicked = pyqtSignal(int)   # 参数：应用在列表中的索引

    def __init__(self, app: dict, index: int, icon_size: int, parent=None):
        super().__init__(parent)
        self._app = app
        self._index = index
        self._icon_size = icon_size
        self._hovered = False
        self._hover_t = 0.0          # 【动效优化】悬停进度 0→1，驱动渐变插值
        self._last_click = 0.0          # 【新增·需求3】上次点击时间戳（monotonic）
        self._icon = extract_app_icon(
            app.get("exe_path", ""), icon_size, app.get("name", ""))

        self.setFixedSize(icon_size + 18, ITEM_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        # 【动效优化】悬停渐变动画：全程复用同一实例
        # 【令牌】时长/缓动统一来自 item.hover
        self._hover_anim = QVariantAnimation(self)
        atk.apply(self._hover_anim, "item.hover", 1.0)
        self._hover_anim.valueChanged.connect(self._on_hover_t)

        # 【动效优化】stagger 入场：透明度+上浮，默认已完全显示
        self._enter_t = 1.0
        self._enter_anim = QVariantAnimation(self)
        atk.apply(self._enter_anim, "item.enter", 1.0)
        self._enter_anim.valueChanged.connect(self._on_enter_t)

        # 【动效优化】启动发射反馈：收缩变淡→回弹
        self._launch_t = 0.0
        # 【新增·启动确认脉冲】单向波纹进度 0→1（仅扩散+淡出一次）
        self._ripple_t = 0.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        # 【动效优化】stagger 入场：整体透明度 + 上浮偏移
        if self._enter_t < 1.0:
            painter.setOpacity(self._enter_t)
            painter.translate(0, 8 * (1.0 - self._enter_t))
        # 【动效优化】启动发射反馈：整体收缩变淡（与入场透明度乘法叠加）
        launch_active = self._launch_t > 0.001
        if launch_active:
            painter.save()
            painter.setOpacity(painter.opacity() * (1.0 - 0.6 * self._launch_t))
            cx = w / 2.0
            cy = h / 2.0
            painter.translate(cx, cy)
            painter.scale(1.0 - 0.3 * self._launch_t, 1.0 - 0.3 * self._launch_t)
            painter.translate(-cx, -cy)
        t = self._hover_t

        # 【动效优化】悬停高亮层：alpha 随进度插值，非硬切
        if t > 0.001:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(52, 56, 66, int(165 * t)))
            painter.drawRoundedRect(1, 1, w - 2, h - 2, 8, 8)

        # 图标（水平居中，顶部留 3px；hover 时上浮 + 微缩放）
        # 用 painter.translate 承载浮点偏移，drawPixmap 用整数 QPoint，避免 QRectF 兼容问题
        icon_y = 3 - 2.0 * t          # 上浮 0→-2px
        ix = (w - self._icon_size) // 2
        icon_scale = 1.0 + 0.06 * t   # 缩放 1.0→1.06
        painter.save()
        painter.translate(ix, icon_y)
        if icon_scale != 1.0:
            cx = self._icon_size / 2.0
            cy = self._icon_size / 2.0
            painter.translate(cx, cy)
            painter.scale(icon_scale, icon_scale)
            painter.translate(-cx, -cy)
        painter.drawPixmap(QPoint(0, 0), self._icon)
        painter.restore()

        # 名称标签（图标下方，超出省略；亮度随 hover 插值）
        label_y = icon_y + self._icon_size + 2
        label_h = int(h - label_y - 2)
        font = QFont("Segoe UI")
        font.setPixelSize(11)
        painter.setFont(font)
        name = self._app.get("name", "")
        fm = QFontMetrics(font)
        elided = fm.elidedText(name, Qt.TextElideMode.ElideRight, w - 8)
        text_alpha = int(173 + (255 - 173) * t)
        painter.setPen(QPen(QColor(210, 212, 217, text_alpha)))
        painter.save()
        painter.translate(0, label_y)
        painter.drawText(QRect(4, 0, w - 8, label_h),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         elided)
        painter.restore()
        if launch_active:
            painter.restore()
        # 【新增·启动确认脉冲】单向波纹：点击后从图标处向外扩散一圈
        # 渐隐色环（仅扩散+淡出一次），作为"启动成功"的视觉确认。
        if self._ripple_t > 0.001:
            ripple_radius = 6.0 + self._ripple_t * (w * 0.42)
            ripple_alpha = int(150 * (1.0 - self._ripple_t))
            if ripple_alpha > 2:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(76, 150, 255, ripple_alpha), 3))
                painter.drawEllipse(
                    QRectF(w / 2.0 - ripple_radius, h / 2.0 - ripple_radius,
                           ripple_radius * 2, ripple_radius * 2))
        painter.end()

    def _on_hover_t(self, value):
        """【动效优化】悬停进度写入，触发重绘。"""
        self._hover_t = max(0.0, min(1.0, float(value)))
        self.update()

    # ----【动效优化】stagger 入场 ----
    def play_enter(self, delay_ms: int):
        """延迟后从透明+上浮状态动画到正常显示（面板打开时逐项调用）。"""
        self._enter_t = 0.0
        self.update()
        QTimer.singleShot(max(0, int(delay_ms)), self._start_enter_anim)

    def _start_enter_anim(self):
        self._enter_anim.stop()
        self._enter_anim.setStartValue(self._enter_t)
        self._enter_anim.setEndValue(1.0)
        self._enter_anim.start()

    def _on_enter_t(self, value):
        self._enter_t = max(0.0, min(1.0, float(value)))
        self.update()

    # ----【动效优化】启动发射反馈 ----
    def get_launchT(self) -> float:
        return self._launch_t

    def set_launchT(self, value: float):
        self._launch_t = max(0.0, min(1.0, float(value)))
        self.update()

    launchT = pyqtProperty(float, get_launchT, set_launchT)

    # ----【新增·启动确认脉冲】单向波纹 ----
    def get_rippleT(self) -> float:
        return self._ripple_t

    def set_rippleT(self, value: float):
        self._ripple_t = max(0.0, min(1.0, float(value)))
        self.update()

    rippleT = pyqtProperty(float, get_rippleT, set_rippleT)

    def play_launch(self):
        """点击启动时播放：收缩变淡(100ms InCubic) → OutBack 回弹恢复(150ms)。

        【新增·启动确认脉冲】同步播一个单向扩散波纹（160ms OutCubic），
        与收缩回弹并行，作为启动成功的视觉确认，不影响既有动画。
        """
        group = QSequentialAnimationGroup(self)
        shrink = QPropertyAnimation(self, b"launchT", self)
        atk.apply(shrink, "item.launch.shrink", 1.0)
        shrink.setStartValue(0.0)
        shrink.setEndValue(1.0)
        recover = QPropertyAnimation(self, b"launchT", self)
        atk.apply(recover, "item.launch.bounce", 1.0)
        recover.setStartValue(1.0)
        recover.setEndValue(0.0)
        group.addAnimation(shrink)
        group.addAnimation(recover)
        group.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

        # 波纹：0→1 单向扩散+淡出（160ms OutCubic）
        ripple = QPropertyAnimation(self, b"rippleT", self)
        ripple.setDuration(160)
        ripple.setEasingCurve(QEasingCurve.Type.OutCubic)
        ripple.setStartValue(0.0)
        ripple.setEndValue(1.0)
        ripple.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def enterEvent(self, event):
        self._hovered = True
        # 【动效优化】从当前进度动画到 1.0，避免方向切换时跳变
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_t)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        # 【动效优化】从当前进度动画回 0.0
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_t)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            print("[LD-DEBUG] AppItem.mouseReleaseEvent 触发, index=", self._index, flush=True)
            # 【新增·需求3】650ms 点击冷却：冷却期内直接丢弃，不发射启动；
            # 仅拦截点击动作，hover 高亮等其它鼠标事件不受影响。
            now = time.monotonic()
            if (now - self._last_click) * 1000.0 >= CLICK_COOLDOWN_MS:
                self._last_click = now
                self.play_launch()   # 【动效优化】发射反馈动画
                self.clicked.emit(self._index)
                print("[LD-DEBUG] AppItem 已 emit clicked, index=", self._index, flush=True)
            else:
                print("[LD-DEBUG] AppItem 冷却中, 丢弃点击", flush=True)
        super().mouseReleaseEvent(event)


# ====================================================================
# 仅横向滚动的滚动区域
# ====================================================================

class _HScrollArea(QScrollArea):
    """隐藏滚动条；鼠标滚轮的竖直滚动映射为横向平滑惯性滚动。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 【动效优化】平滑惯性滚动动画，实例复用
        self._scroll_anim = QPropertyAnimation(
            self.horizontalScrollBar(), b"value", self)
        atk.apply(self._scroll_anim, "panel.scroll", 1.0)

    def wheelEvent(self, event):
        bar = self.horizontalScrollBar()
        delta = event.angleDelta().y() + event.angleDelta().x()
        if delta:
            # 【动效优化】连续滚轮时更新目标值，实现惯性追随效果
            self._scroll_anim.stop()
            self._scroll_anim.setStartValue(bar.value())
            target = bar.value() - delta
            target = max(bar.minimum(), min(bar.maximum(), target))
            self._scroll_anim.setEndValue(target)
            self._scroll_anim.start()
        event.accept()


# ====================================================================
# 横滑面板窗口（独立顶层无边框窗口）
# ====================================================================

class SlidePanel(QWidget):
    """
    悬停浮球时滑出的横向面板窗口（独立顶层窗口，非子控件）。

    窗口结构（外围黑框修复关键）：
      SlidePanel（顶层窗口：纯透明载体，不设任何背景样式）
        └─ _surface（唯一子容器：承载背景色/圆角/半透明/边框/投影）
             └─ _HScrollArea → _content → AppItem...

    - 顶层：Frameless + Tool + StaysOnTop + WA_TranslucentBackground，
      四周 SHADOW_MARGIN 边距区域真透明（桌面直透）
    - 半透明背景由 _surface 的 QSS rgba 实现，不调用系统亚克力
      （亚克力作用于整个窗口矩形，会在面板外围染出深色矩形黑框）
    - 对外信号：hover_entered / hover_left / request_menu / launch_requested
    """

    hover_entered = pyqtSignal()
    hover_left = pyqtSignal()
    request_menu = pyqtSignal(object)          # 全局坐标，请求弹出右键菜单
    launch_requested = pyqtSignal(int)         # 点击了第 index 个应用

    def __init__(self, parent=None):
        super().__init__(parent)
        # ---- 顶层窗口属性（顺序：先 flags 再透明属性，均作用于顶层） ----
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        # 透明背景必须设置在顶层窗口对象上（不可设在子 widget）
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        # 注意：顶层窗口自身不设置任何 background / border QSS

        self._opacity = 0.87
        self._anim_speed = 1.0
        self._side = "left"          # 浮球贴的边：left → 面板向右出
        self._show_anim = None
        self._hide_anim = None
        self._hide_timer = None

        # ---- surface（唯一子容器：全部可见视觉由它承载） ----
        self._surface = QWidget(self)
        self._surface.setObjectName("slideSurface")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 107))   # rgba(0,0,0,0.42)
        self._surface.setGraphicsEffect(shadow)

        lay = QHBoxLayout(self._surface)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        self._scroll = _HScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        lay.addWidget(self._scroll)

        self._content = QWidget()
        self._content.setStyleSheet("background:transparent;")
        self._content_lay = QHBoxLayout(self._content)
        self._content_lay.setContentsMargins(0, 0, 0, 0)
        self._content_lay.setSpacing(4)
        self._content_lay.addStretch()
        self._scroll.setWidget(self._content)

        self._empty_label = QLabel("暂无应用 · 右击浮球打开设置添加")
        self._empty_label.setStyleSheet(
            "color:#8A8D96;font-size:12px;background:transparent;")
        self._empty_label.adjustSize()

        self._app_items = []   # 【动效优化】持有 AppItem 引用，供 stagger 入场
        self._apply_surface_style()

    # ---------------- 数据 ----------------
    def set_apps(self, apps: list, icon_size: int):
        """按应用列表重建全部项。"""
        # 先摘下空态标签（持久复用，不销毁）
        self._content_lay.removeWidget(self._empty_label)
        self._empty_label.hide()   # removeWidget 只摘布局，控件仍 visible，需显式隐藏
        # 清空旧项（末尾保留 stretch）
        while self._content_lay.count() > 1:
            item = self._content_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._app_items.clear()

        for i, app in enumerate(apps):
            widget = AppItem(app, i, icon_size)
            widget.clicked.connect(self.launch_requested.emit)
            self._content_lay.insertWidget(self._content_lay.count() - 1, widget)
            self._app_items.append(widget)

        # 空态提示
        if not apps:
            self._content_lay.insertWidget(self._content_lay.count() - 1,
                                           self._empty_label)
            self._empty_label.show()

    # ---------------- 视觉参数 ----------------
    def set_opacity(self, value: float):
        """设置背景不透明度（0-1），立即重绘 surface。"""
        self._opacity = max(0.05, min(1.0, value))
        self._apply_surface_style()

    def set_anim_speed(self, speed: float):
        self._anim_speed = max(0.5, min(2.0, speed))

    def _apply_surface_style(self):
        """
        半透明背景由 _surface 的 QSS 承载（顶层窗口保持完全透明，
        四周边距区域直透桌面，无任何系统级染色）。
        """
        self._surface.setStyleSheet(
            f"QWidget#slideSurface{{background:rgba(16,17,21,"
            f"{int(255 * self._opacity)});"
            f"border-radius:{PANEL_RADIUS}px;"
            f"border:1px solid rgba(255,255,255,0.09);}}"
        )

    # ---------------- 几何 ----------------
    def compute_size(self, apps: list, icon_size: int, screen_w: int):
        """根据应用数与图标大小计算窗口尺寸并调整布局。"""
        if apps:
            content_w = len(apps) * (icon_size + 18 + 4) + 20
        else:
            self._empty_label.adjustSize()
            content_w = self._empty_label.width() + 28
        max_w = int(screen_w * 0.6)
        panel_w = max(icon_size + 38, min(content_w, max_w))
        window_w = panel_w + SHADOW_MARGIN * 2
        window_h = PANEL_H + SHADOW_MARGIN * 2
        self.resize(window_w, window_h)
        self._surface.setGeometry(
            SHADOW_MARGIN, SHADOW_MARGIN, panel_w, PANEL_H)
        return window_w, window_h

    def place_beside(self, ball_rect, screen_avail):
        """
        把面板放到浮球旁边（不显示）。

        ball_rect   —— 浮球窗口全局几何
        screen_avail—— 浮球所在屏幕的可用区域
        返回面板出现的方向（"right"/"left"）。
        """
        w = self.width()
        h = self.height()
        # 垂直：面板中心对齐浮球中心，并夹在屏幕内
        cy = ball_rect.center().y()
        y = int(cy - h / 2)
        y = max(screen_avail.top() - SHADOW_MARGIN + 4,
                min(y, screen_avail.bottom() - h + SHADOW_MARGIN - 4))

        # 水平：浮球在屏幕左半 → 面板从右侧伸出；右半 → 从左侧伸出
        ball_cx = ball_rect.center().x()
        screen_cx = screen_avail.center().x()
        if ball_cx <= screen_cx:
            x = ball_rect.right() + 8 - SHADOW_MARGIN
            self._side = "left"
            direction = "right"
        else:
            x = ball_rect.left() - 8 - w + SHADOW_MARGIN
            self._side = "right"
            direction = "left"

        x = max(screen_avail.left() - SHADOW_MARGIN + 4,
                min(x, screen_avail.right() - w + SHADOW_MARGIN - 4))
        self.move(x, y)
        return direction

    # ---------------- 显示 / 隐藏（滑动 + 淡入淡出） ----------------
    def slide_in(self, direction: str):
        """从 direction 方向滑入并淡入（direction: 'right'=向右展开 / 'left'）。"""
        if self.isVisible():
            return
        final = self.pos()
        _travel = atk.motion("panel.slide_in").travel
        offset = -_travel if direction == "right" else _travel
        self.move(final.x() + offset, final.y())
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()

        # 【令牌】透明度 + 位移均用 panel.slide_in（OutCubic）
        atk.play(self, b"windowOpacity", "panel.slide_in", self._anim_speed,
                 start=0.0, end=1.0)
        atk.play(self, b"pos", "panel.slide_in", self._anim_speed,
                 start=self.pos(), end=final)

        # 【动效优化】AppItem stagger 入场：每项延迟 35ms，上限 300ms
        _step = atk.motion("item.enter").stagger_ms
        for i, item in enumerate(self._app_items):
            item.play_enter(atk.stagger_delay(i, _step))

    def slide_out(self):
        """淡出并滑回，结束后隐藏。"""
        if not self.isVisible():
            return
        # 【令牌】透明度 + 位移均用 panel.slide_out（InCubic），结束后隐藏
        atk.play(self, b"windowOpacity", "panel.slide_out", self._anim_speed,
                 start=self.windowOpacity(), end=0.0, on_finished=self.hide)
        _travel = atk.motion("panel.slide_out").travel
        offset = -_travel if self._side == "left" else _travel
        atk.play(self, b"pos", "panel.slide_out", self._anim_speed,
                 start=self.pos(), end=QPoint(self.x() + offset, self.y()))

    # ---------------- 事件 ----------------
    def enterEvent(self, event):
        self.hover_entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_left.emit()
        super().leaveEvent(event)

    def contextMenuEvent(self, event):
        self.request_menu.emit(event.globalPos().toTuple()
                               if hasattr(event.globalPos(), "toTuple")
                               else event.globalPos())
        super().contextMenuEvent(event)

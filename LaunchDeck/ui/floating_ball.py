# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck 悬浮球  -  FloatingBall（含整体交互控制）
====================================================================
v4 方案规格：
  · 42px 正圆，背景 #24262D，悬停 #2C2F38 + scale 1.1
  · 中心 2×2 四方块图标（首次定稿样式）
  · 软投影 0 2px 8px rgba(0,0,0,0.35)，无发光无边框
  · 拖动松手自动吸附最近左右边缘（QPropertyAnimation）
  · 贴左缘 → 面板向右滑出；贴右缘 → 向左滑出
  · 左键点击 = 固定/取消固定面板；右键菜单 = 设置 / 退出
  · 悬停显示面板，鼠标移开（含面板）自动收回
====================================================================
"""

import math

from PyQt6.QtCore import (
    Qt, QElapsedTimer, QTimer, QPoint, QEvent, QRect,
    pyqtProperty, pyqtSignal,
    QPropertyAnimation, QVariantAnimation, QRectF,
    QAbstractAnimation,
)
from PyQt6.QtGui import QPainter, QColor, QRadialGradient, QLinearGradient
from PyQt6.QtWidgets import (
    QWidget, QApplication, QMenu, QGraphicsDropShadowEffect,
)

from core.app_manager import AppManager, launch_app
from ui import anim_tokens as atk
from ui.slide_panel import SlidePanel
from ui.settings_dialog import SettingsDialog

# 浮球视觉常量
BALL_D = 42            # 球直径
WIN_D = 66             # 窗口边长（球 + 悬停放大 + 阴影余量）
BALL_BG = QColor("#24262D")
BALL_BG_HOVER = QColor("#2C2F38")
ICON_COLOR = QColor(210, 212, 217, 235)   # 四方块颜色（淡）


class BallVisual(QWidget):
    """
    球的可视部分（窗口内的子控件）：圆形底 + 四方块图标 + 悬停动效。

    【修复·约束3】hover 动画完全结束后发此信号，宿主据此接回呼吸动画，
    保证两套动画绝不同时操作 scale。

    - 悬停时通过 QVariantAnimation 同时插值：scale 1.0→1.1、底色渐变
    - 外层投影由 QGraphicsDropShadowEffect 提供

    【新增·需求1】闲置呼吸 pulse：
    - QElapsedTimer + 30ms QTimer 正弦驱动（周期 4.2s），连续无缝、永不回 0
    - 玻璃拟态辉光（内受光核/紧贴球缘柔光）在 __init__ 缓存，
      paintEvent 用 painter 变换驱动，不重建渐变
    - 光晕最大扩散受 GLOW_MAX_R 严格限制，只贴身小范围溢出
    - 局部区域重绘（update(QRect)），球体半径恒定
    """

    # 【修复·约束3】hover 动画结束信号：宿主接收后按闲置条件接回呼吸
    hover_anim_finished = pyqtSignal()

    IDLE_SCALE = 0.06        # 呼吸最大缩放增幅（1.0 → 1.06）
    # 呼吸周期 / 收平时长由动效令牌 ball.idle.pulse / ball.idle.settle 提供

    # ---- 辉光可调参数（集中在此，便于全局微调）----
    GLOW_BREATH_MS = 4200      # 呼吸周期(ms)（Factory 法则：连续正弦，慢而从容）
    GLOW_TIMER_MS = 30         # 呼吸驱动帧间隔(ms)
    GLOW_MAX_R = 0.68          # 光晕最大扩散(×BALL_D)，紧贴球体小范围溢出
    GLOW_POW = 1.0             # 呼吸亮度矫正：1.0 线性，峰谷对比更明显
    _GLOW_COLOR = (135, 185, 255)   # 冷蓝主色（更饱和鲜亮，呼吸起伏分明）
    _GLOW_CORE = (205, 222, 255)    # 玻璃内受光（稍带蓝色层次，避免过白）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._speed = 1.0      # 动效速度档（由宿主 _apply_settings 同步）
        self._t = 0.0          # 悬停进度 0→1
        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_t)
        # 【修复·约束3】hover 动画结束后回调（退出 hover → 交还呼吸接管）
        self._anim.finished.connect(self._hover_anim_finished)

        # ---- 呼吸辉光：30ms 正弦定时驱动（单峰呼吸 + 停顿，球体半径恒定）----
        # 仅改变光晕亮度 / 扩散半径，球体半径恒定不变（不再缩放球体）。
        self._idle_t = 0.0          # 呼吸因子 0→1（正弦单峰），只驱动光晕
        self._glow_enabled = True   # 光影开关（由宿主同步）
        self._glows = self._build_glow_layers()   # 三层辉光，__init__ 只建一次
        (self._sp_grad, self._in_sh_grad,
         self._edge_grad) = self._build_static_shades()
        self._glow_half = int(WIN_D * 0.52)       # 光晕最大半径(px)，用于局部重绘
        self._breath_clock = QElapsedTimer()
        self._breath_timer = QTimer(self)
        self._breath_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._breath_timer.setInterval(self.GLOW_TIMER_MS)
        self._breath_timer.timeout.connect(self._on_breath_tick)

        # 停止后的平滑回落（同一实例复用，不重建）
        # 【令牌】时长/缓动统一来自 ball.idle.settle
        _settle = atk.motion("ball.idle.settle")
        self._settle_anim = QPropertyAnimation(self, b"idleScale", self)
        self._settle_anim.setDuration(_settle.duration)
        self._settle_anim.setEndValue(0.0)
        self._settle_anim.setEasingCurve(_settle.easing)

        # 【修复·约束1】唯一运行标记：防重复 start 引发多实例并发抖动
        self._is_idle_pulse_running = False

        # 【动效优化】pressed 按下回弹态：按下快速缩小，释放 OutBack 回弹
        self._pressed_t = 0.0
        self._pressed_anim = QVariantAnimation(self)
        self._pressed_anim.valueChanged.connect(self._on_pressed_t)

        # 【动效优化】拖拽态：放大（被拿起感），与 hover/pressed 叠加
        self._drag_t = 0.0
        self._drag_anim = QVariantAnimation(self)
        # 【令牌】时长/缓动在 set_dragging 时经 atk.apply 注入（ball.drag）
        self._drag_anim.valueChanged.connect(self._on_drag_t)

    # ---- idleScale Qt 属性（供 settle 平滑收平 _idle_t → 0）----
    def get_idleScale(self) -> float:
        return self._idle_t

    def set_idleScale(self, value: float):
        """呼吸进度写入：仅驱动光晕，球体半径恒定；局部区域重绘。"""
        self._idle_t = max(0.0, min(1.0, float(value)))
        self._update_glow_region()

    idleScale = pyqtProperty(float, get_idleScale, set_idleScale)

    def _update_glow_region(self):
        """【性能】只重绘光晕所在局部区域，禁止整窗重绘。"""
        c = self.width() / 2.0
        half = self._glow_half
        self.update(QRect(int(c - half), int(c - half),
                          int(half * 2), int(half * 2)))

    # ---- 呼吸驱动：30ms 定时，连续无缝正弦 ----
    def _on_breath_tick(self):
        """Factory 法则：连续对称正弦呼吸，起止/峰值首尾相连、无缝循环。

        _idle_t 输出 ∈ [0,1]（对称 ease-in-out），永不回 0 → 无硬开关、
        不突兀。周期 GLOW_BREATH_MS，慢而从容。
        """
        p = (self._breath_clock.elapsed() % self.GLOW_BREATH_MS) \
            / self.GLOW_BREATH_MS
        self._idle_t = 0.5 - 0.5 * math.cos(2.0 * math.pi * p)  # 0→1→0 连续
        self._update_glow_region()

    def set_glow_enabled(self, enabled: bool):
        """光影开关：关闭时停止呼吸并立即清光，开启时按闲置条件续播。"""
        self._glow_enabled = bool(enabled)
        if not self._glow_enabled:
            self.stop_idle_pulse()
            self._idle_t = 0.0
            self._update_glow_region()

    # ---- 两层辉光：__init__ 一次性构建，paintEvent 只变换 + 加色混合，不重建 ----
    def _gaussian_stops(self, peak_pos, sigma, peak_a, n=24):
        """生成高斯平滑衰减止点：发光本质（内强外弱、自动归零）。

        用 pow-free 的高斯曲线 exp(-(u-u0)^2/2σ²) 在 [0,R] 上采样，
        替代硬分段止点 → 无同心圆盘/色带堆叠感，边缘自然归零无硬边。
        peak_pos ∈ [0,1]：高斯峰值所在归一化半径位置。
        sigma ∈ [0,1]：曲线宽度，越小越收拢（光贴得越紧）。
        返回值 (pos, alpha)，末点为 0 保证柔和消散。
        """
        stops = []
        for i in range(n + 1):
            u = i / n
            a = peak_a * math.exp(-((u - peak_pos) ** 2) / (2 * sigma * sigma))
            stops.append((u, a))
        stops[-1] = (1.0, 0.0)     # 强制边缘归零，避免发光硬边界
        return stops

    def _build_glow_layers(self):
        """加色高斯柔光辉光：玻璃体内部透亮白核 + 紧贴球缘的高斯柔光环。

        ⚠ 与全局结论一致：真正高级发光 = 高斯平滑衰减 + 加色(Additive)混合+
        - 内受光核：偏白透亮，高斯峰在球心，为玻璃体提供"自发光/透亮"底光
        - 紧贴球缘柔光环：冷蓝，高斯峰落在球缘(u≈球缘位置)，向外极短距离
          消散，严格受 GLOW_MAX_R 限制，绝不强铺大范围
        - 多层高斯叠加产生由内向外软扩散层次，无圆盘堆叠感
        """
        c = WIN_D / 2.0
        r, gg, b = self._GLOW_COLOR
        cr, cg, cb = self._GLOW_CORE

        def _rad(radius, stops, rr, ggg, bb):
            g = QRadialGradient(c, c, radius)
            for pos, a in stops:
                a = max(0.0, min(255.0, a))
                g.setColorAt(pos, QColor(rr, ggg, bb, int(a)))
            return g, radius

        layers = []
        # 1) 内受光核：高斯峰在球心，白色偏蓝，为玻璃体内部提供透亮底光。
        #    加色混合下 alpha 不宜过高，留叠加余量防过曝。
        layers.append(_rad(
            BALL_D * 0.50,
            self._gaussian_stops(peak_pos=0.00, sigma=0.32, peak_a=96),
            cr, cg, cb))
        # 2) 紧贴球缘柔光环：高斯峰落在球缘，向外极短扩散、贴合球体。
        #    ball_edge_u = 球半径/光晕半径 ≈ 0.5/0.68 ≈ 0.74 → 光贴身、范围偏小。
        R2 = BALL_D * self.GLOW_MAX_R
        ball_edge_u = (BALL_D * 0.5) / R2
        layers.append(_rad(
            R2,
            self._gaussian_stops(peak_pos=ball_edge_u, sigma=0.15, peak_a=118),
            r, gg, b))
        return layers

    def _build_static_shades(self):
        """缓存不变的顶部釉面高光 / 底部内收阴影 / 玻璃细亮边缘，
        避免 paintEvent 重建渐变。"""
        sp = QRadialGradient(
            WIN_D / 2 - BALL_D * 0.10, WIN_D / 2 - BALL_D * 0.14, BALL_D * 0.52)
        sp.setColorAt(0.0, QColor(255, 255, 255, 165))
        sp.setColorAt(0.55, QColor(255, 255, 255, 46))
        sp.setColorAt(1.0, QColor(255, 255, 255, 0))
        in_sh = QLinearGradient(
            WIN_D / 2 - BALL_D / 2, WIN_D / 2 - BALL_D * 0.20,
            WIN_D / 2 - BALL_D / 2, WIN_D / 2 + BALL_D / 2)
        in_sh.setColorAt(0.0, QColor(0, 0, 0, 0))
        in_sh.setColorAt(0.55, QColor(0, 0, 0, 0))
        in_sh.setColorAt(1.0, QColor(0, 0, 0, 118))
        # 玻璃细亮边缘：紧贴球缘的一道细亮环，模拟玻璃材质的高折射光边
        edge = QRadialGradient(WIN_D / 2, WIN_D / 2, BALL_D / 2)
        edge.setColorAt(0.0, QColor(255, 255, 255, 0))
        edge.setColorAt(0.78, QColor(255, 255, 255, 0))
        edge.setColorAt(0.90, QColor(230, 240, 255, 40))
        edge.setColorAt(0.99, QColor(255, 255, 255, 90))
        edge.setColorAt(1.0, QColor(255, 255, 255, 0))
        return sp, in_sh, edge

    # ---- 呼吸启停接口：控制 30ms 正弦定时器 ----
    def start_idle_pulse(self):
        """闲置满足时启动/恢复呼吸；标记防重复 start。"""
        if self._is_idle_pulse_running:
            if not self._breath_timer.isActive():
                self._settle_anim.stop()
                self._breath_clock.restart()
                self._breath_timer.start()
            return
        self._settle_anim.stop()
        self._is_idle_pulse_running = True
        self._breath_clock.restart()
        self._breath_timer.start()

    def stop_idle_pulse(self):
        """任意交互立即终止呼吸；残留光晕用预建回落动画收平。"""
        self._is_idle_pulse_running = False
        if self._breath_timer.isActive():
            self._breath_timer.stop()
        if self._idle_t > 0.001:
            self._settle_anim.stop()
            self._settle_anim.setStartValue(self._idle_t)
            self._settle_anim.start()

    def pause_idle_pulse(self):
        """最小化/后台：停止定时器（保留进度），降低 CPU 占用。"""
        if self._breath_timer.isActive():
            self._breath_timer.stop()
        if self._settle_anim.state() == QAbstractAnimation.State.Running:
            self._settle_anim.pause()

    def set_hover(self, hovered: bool):
        """开/关悬停动画（时长/缓动来自动效令牌 ball.hover.enter/exit）。

        【修复·约束3】严格互斥：
        - 进入 hover：先 idle_pulse_group.stop()（同步落地），hover 接管
        - 退出 hover：同样先停呼吸，淡出动画独占缩放；
          淡出 finished 信号后宿主按闲置条件接回呼吸——
          任一时刻两套动画绝不并发操作 scale。
        """
        self.stop_idle_pulse()
        # 【卡顿修复】进入 hover 时立即收平呼吸残留：避免退出时 settle(120ms)
        # 与 hover 淡出(140ms) 双动画叠加，在 120ms 处产生速率突变（卡顿感）。
        # 进入时 _idle_t 跳变幅度最大仅 0.06(2.5px)，被 hover 放大趋势掩盖。
        if hovered:
            self._settle_anim.stop()
            self._idle_t = 0.0
        self._anim.stop()
        # 时长/缓动由令牌注入：放大 OutCubic（快起缓到）、缩小 InOutCubic
        # （S 曲线对称均匀，避免缩小后半程"停住"的卡顿感）。
        atk.apply(self._anim,
                  "ball.hover.enter" if hovered else "ball.hover.exit",
                  self._speed)
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(1.0 if hovered else 0.0)
        self._anim.start()

    def _hover_anim_finished(self):
        """【修复·约束3】hover 动画结束后广播：宿主据此接回呼吸动画。"""
        try:
            self.hover_anim_finished.emit()
        except RuntimeError:
            pass

    # ----【动效优化】pressed 按下回弹态 ----
    def set_pressed(self, pressed: bool):
        """鼠标按下缩小、释放回弹（OutBack 过冲）。拖拽开始时应调用 set_pressed(False)。

        - 按下：100ms OutCubic 快速缩小到 scale-0.08
        - 释放：150ms OutBack 回弹（短暂过冲后回落，形成"弹性"触感）
        - 与 hover/呼吸共享 scale 公式，互不干扰（叠加计算）
        """
        self._pressed_anim.stop()
        atk.apply(self._pressed_anim,
                  "ball.press.down" if pressed else "ball.press.up",
                  self._speed)
        self._pressed_anim.setStartValue(self._pressed_t)
        self._pressed_anim.setEndValue(1.0 if pressed else 0.0)
        self._pressed_anim.start()

    def _on_pressed_t(self, value):
        """pressed 进度写入（OutBack 允许短暂负值形成过冲，不 clamp）。"""
        self._pressed_t = float(value)
        self.update()

    # ----【动效优化】拖拽态 ----
    def set_dragging(self, dragging: bool):
        """拖拽开始/结束：拖拽时 scale 额外 +0.08（被拿起感）。"""
        self._drag_anim.stop()
        atk.apply(self._drag_anim, "ball.drag", self._speed)
        self._drag_anim.setStartValue(self._drag_t)
        self._drag_anim.setEndValue(1.0 if dragging else 0.0)
        self._drag_anim.start()

    def _on_drag_t(self, value):
        self._drag_t = max(0.0, min(1.0, float(value)))
        self.update()

    def set_anim_speed(self, speed: float):
        """由宿主同步全局动效速度档（0.5–2.0）。"""
        self._speed = max(0.5, min(2.0, float(speed)))

    def _apply_geo(self):
        """【顿挫根修】几何固定，缩放交给 paintEvent 的浮点变换。"""
        self.update()

    def _on_t(self, t):
        self._t = float(t)
        self._apply_geo()

    def paintEvent(self, event):
        """【修复·问题1/4】纯矢量绘制 + QPainter.scale 浮点缩放。

        - 缩放连续浮点（绝不 round），由属性动画驱动 → 丝滑无顿挫
        - 直接用 drawEllipse/drawRoundedRect 矢量绘制，叠加 Antialiasing
          亚像素抗锯齿 → 边缘平滑，无 drawPixmap 位图插值锯齿
        - 几何固定，绘制内容仅 5 个矢量图元，每帧开销极低
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 呼吸微缩放：与辉光同源连续正弦 _idle_t，起止无缝，强化"活的"感
        breath_scale = self.IDLE_SCALE * self._idle_t if self._glow_enabled else 0.0
        scale = (1.0 + 0.1 * self._t + breath_scale
                 - 0.08 * self._pressed_t + 0.08 * self._drag_t)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        painter.translate(cx, cy)
        painter.scale(scale, scale)
        painter.translate(-cx, -cy)

        off = (self.width() - BALL_D) / 2.0
        offy = (self.height() - BALL_D) / 2.0

        # 圆形底：颜色随悬停进度插值
        r = self._t
        bg = QColor(
            int(BALL_BG.red() + (BALL_BG_HOVER.red() - BALL_BG.red()) * r),
            int(BALL_BG.green() + (BALL_BG_HOVER.green() - BALL_BG.green()) * r),
            int(BALL_BG.blue() + (BALL_BG_HOVER.blue() - BALL_BG.blue()) * r),
        )

        # 【玻璃拟态】体积渐变 + 内受光核 + 紧贴球缘柔光 + 顶部高光 + 底部内收阴影。
        # 渐变缓存在 __init__，paintEvent 只用 painter 变换驱动，不重建渐变。
        painter.setPen(Qt.PenStyle.NoPen)

        # 1) 体积渐变：磨砂半透明玻璃体——中央较透亮、边缘渐实，
        #    让内受光核透出（alpha 由内往外微变）。光影关闭时改为纯色下沉。
        if self._glow_enabled:
            c0 = QColor(bg.lighter(114))
            c0.setAlpha(198)                 # 高光区稍透（进一步降白减曝光）
            c1 = QColor(bg.lighter(102))
            c1.setAlpha(216)
            c2 = bg
            c3 = bg.darker(146)
        else:
            c0, c1, c2, c3 = bg, bg, bg, bg.darker(112)
        vol = QRadialGradient(
            off + BALL_D * 0.34, offy + BALL_D * 0.32, BALL_D * 0.72)
        vol.setColorAt(0.0, c0)
        vol.setColorAt(0.42, c1)
        vol.setColorAt(0.72, c2)
        vol.setColorAt(1.0, c3)
        painter.setBrush(vol)
        painter.drawEllipse(QRectF(off, offy, BALL_D, BALL_D))

        # 2) 加色高斯柔光辉光：内受光核 + 紧贴球缘柔光环。
        #    【全局结论】用 CompositionMode_Plus 加色混合：重叠处亮度累加
        #    而非覆盖 → "自发光/透亮"质感；高斯平滑衰减无圆盘色带。
        #    亮度经 pow(GLOW_POW) 矫正；扩散微变；悬停增强。光影范围受控。
        if self._glow_enabled:
            raw = self._idle_t                     # 0→1→0 连续
            breath = raw ** self.GLOW_POW          # 亮度矫正（不回0）
            base_op = 0.05 + 0.95 * breath   # 亮度 0.05↔1.0（最低点更暗，中心曝光更低）
            spread = 0.94 + 0.06 * breath          # 扩散半径随呼吸微变
            hover_boost = 1.0 + 0.5 * self._t      # 悬停整体增强光效
            painter.save()
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Plus)   # 加色混合
            for grad, ref_r in self._glows:
                op = min(1.0, base_op * hover_boost)
                op_r = ref_r * spread
                painter.setOpacity(op)
                painter.setBrush(grad)
                painter.drawEllipse(QRectF(cx - op_r, cy - op_r,
                                           op_r * 2, op_r * 2))
            painter.restore()   # 还原混合模式与透明度

        # 3) 底部内收阴影：已缓存，直接复用画笔（光影关闭时同样保留立体沉坠）
        painter.setBrush(self._in_sh_grad)
        painter.drawEllipse(QRectF(off, offy, BALL_D, BALL_D))

        # 4) 玻璃细亮边缘 + 顶部釉面高光：开启光影时绘制（细亮高折射光边）
        if self._glow_enabled:
            painter.setBrush(self._edge_grad)
            painter.drawEllipse(QRectF(off, offy, BALL_D, BALL_D))
            painter.setBrush(self._sp_grad)
            painter.drawEllipse(QRectF(
                off - BALL_D * 0.12, offy - BALL_D * 0.12,
                BALL_D * 1.24, BALL_D * 1.24))

        # 2×2 四方块图标
        total = BALL_D * 0.46
        gap = max(2.0, BALL_D * 0.05)
        cell = (total - gap) / 2.0
        radius = max(2.0, cell * 0.28)
        ox = off + (BALL_D - total) / 2.0
        oy = offy + (BALL_D - total) / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ICON_COLOR)
        painter.drawRoundedRect(QRectF(ox, oy, cell, cell), radius, radius)
        painter.drawRoundedRect(QRectF(ox + cell + gap, oy, cell, cell), radius, radius)
        painter.drawRoundedRect(QRectF(ox, oy + cell + gap, cell, cell), radius, radius)
        painter.drawRoundedRect(
            QRectF(ox + cell + gap, oy + cell + gap, cell, cell), radius, radius)
        painter.end()


class FloatingBall(QWidget):
    """
    悬浮球窗口 + 全局交互控制（面板显示/吸附/菜单/设置）。
    """

    def __init__(self, manager: AppManager):
        super().__init__()
        self._mgr = manager
        self._pinned = False          # 面板是否固定
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
        self.setFixedSize(WIN_D, WIN_D)

        # 球体子控件 + 投影
        # 【顿挫根修】球体占满整个 WIN_D 窗口，缩放由 paintEvent 的
        # QPainter.scale 浮点完成；最大缩放 1.16 倍(48.7px) 不越界。
        self._ball = BallVisual(self)
        self._ball.setGeometry(0, 0, WIN_D, WIN_D)
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

        # 面板自动收回计时器
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_panel)

        # 面板重建脏标记（滑杆拖动时不重复重建，避免卡顿）
        self._need_rebuild = True
        self._applied_icon_size = -1

        self._apply_settings()
        self._restore_position()

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
        if self._need_rebuild or icon_size != self._applied_icon_size:
            self._panel.set_apps(self._mgr.apps, icon_size)
            self._applied_icon_size = icon_size
            self._need_rebuild = False
        self._resize_panel()

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
                      screen.center().y() - WIN_D // 2)

    def _clamp_into(self, avail):
        """把窗口位置夹进屏幕可用区域内。"""
        x = max(avail.left() - 6, min(self.x(), avail.right() - WIN_D + 6))
        y = max(avail.top() - 6, min(self.y(), avail.bottom() - WIN_D + 6))
        self.move(x, y)

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
        """闲置判定：光影开关 + 呼吸开关 + 应用激活 + 无悬停 + 无拖拽 + 面板收回。"""
        try:
            return (self._ball._glow_enabled
                    and bool(self._mgr.settings.get("enable_idle_pulse", True))
                    and self._app_active
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
        self._panel.slide_out()

    def _toggle_pin(self):
        """左键点击浮球：固定/取消固定面板（状态同步写入配置）。"""
        self._set_pinned(not self._pinned)
        self._mgr.set_setting("panel_pinned", self._pinned)

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
        if not self._pinned:
            self._hide_timer.start(self._ms(atk.HIDE_DELAY_MS))

    def _on_launch(self, index: int):
        apps = self._mgr.apps
        print("[LD-DEBUG] _on_launch 调用, index=", index, "len(apps)=", len(apps), flush=True)
        if 0 <= index < len(apps):
            app = apps[index]
            print("[LD-DEBUG] 准备启动: name=", app.get("name", ""), "exe_path=", app.get("exe_path", ""), flush=True)
            launch_app(app.get("exe_path", ""), app.get("name", ""), parent=self)
        else:
            print("[LD-DEBUG] _on_launch index 越界，跳过", flush=True)

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
                xlo, xhi = avail.left() - margin, avail.right() - WIN_D + margin
                ylo, yhi = avail.top() - margin, avail.bottom() - WIN_D + margin
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
                self._toggle_pin()
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
        center_x = self.x() + WIN_D / 2
        target_x = (avail.left() + 2 if center_x <= avail.center().x()
                    else avail.right() - WIN_D + 2 - 2)
        # 【新增】拖拽可能已越界（橡皮筋），吸附时把 y 也夹回界内，
        # 保证松手后完整落回屏幕，不残留边界外。
        y = max(avail.top() - 6,
                min(self.y(), avail.bottom() - WIN_D + 6))

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
        if not self._pinned:               # 常驻则保持，不自动收回
            self._hide_timer.start(self._ms(atk.HIDE_DELAY_MS))
        super().leaveEvent(event)

    # ================================================================
    # 右键菜单（浮球与面板共用）
    # ================================================================
    def contextMenuEvent(self, event):
        self._show_menu(event.globalPos())

    def _show_menu(self, global_pos):
        pos = QPoint(*global_pos) if isinstance(global_pos, tuple) else global_pos
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: rgba(20,21,26,0.96);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px; padding: 6px;
            }
            QMenu::item {
                color: #D2D4D9; font-size: 13px;
                padding: 8px 22px 8px 12px; border-radius: 6px;
            }
            QMenu::item:selected { background: rgba(76,150,255,0.16); }
        """)
        act_settings = menu.addAction("设  置")
        menu.addSeparator()
        act_quit = menu.addAction("退  出")
        act = menu.exec(pos)
        if act == act_settings:
            self._open_settings()
        elif act == act_quit:
            self._panel.close()
            QApplication.quit()

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
        super().closeEvent(event)

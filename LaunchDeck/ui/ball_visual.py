# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck 悬浮球  -  BallVisual（球体视觉，v2.2.3 自 floating_ball 拆出）
====================================================================
职责：
  · 圆形底 + 四方块图标 + 自定义贴图的纯视觉子控件
  · 悬停/按下/拖拽缩放动效 + 闲置呼吸辉光（30ms 正弦驱动）
  · 球径调整（set_ball_size）/ 主题换肤（set_theme_colors）

约束（历史修复结论，勿破坏）：
  · 几何固定，缩放全靠 paintEvent 的 QPainter.scale 浮点变换
  · 呼吸与 hover 两套动画严格互斥（hover_anim_finished 信号交接）
  · 渐变在 __init__/set_* 时缓存，paintEvent 不重建
====================================================================
"""

import math
import os

from PyQt6.QtCore import (
    Qt, QElapsedTimer, QTimer, QRect,
    QPointF, QRectF,
    pyqtProperty, pyqtSignal,
    QPropertyAnimation, QVariantAnimation,
    QAbstractAnimation,
)
from PyQt6.QtGui import (
    QPainter, QColor, QRadialGradient, QLinearGradient, QPixmap,
)
from PyQt6.QtWidgets import QWidget

from core.app_manager import circular_cover_pixmap
from ui import anim_tokens as atk
from ui import theme as ui_theme

# 浮球视觉常量（默认值；v2.1.2 起实际配色随主题，见 BallVisual.set_theme_colors）
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
        # 【v2.1.2】球体配色（随主题）：初始取主题当前值，换肤经 set_theme_colors
        th = ui_theme.get()
        self._bg = QColor(*th["ball_bg"])
        self._bg_hover = QColor(*th["ball_bg_hover"])
        self._icon_color = QColor(*th["ball_icon"])
        self._glow_color = tuple(th["ball_glow"])
        self._glow_core = tuple(th["ball_glow_core"])
        # 【v2.1.3】球径实例化：默认 42，经 set_ball_size 动态调整
        # （辉光/釉面/内阴影渐变缓存均依赖球径与窗口尺寸，改径后必须重建）
        self._ball_d = float(BALL_D)
        self._win_d = WIN_D
        # 【修复·v2.2.4】初始尺寸必须在此定死：set_ball_size 对 d==BALL_D(42)
        # 会早退，_apply_ball_size 又以其返回值为前提 —— 配置球径恰为默认 42 时
        # （打包版全新 config 即如此），控件将保持 Qt 子控件默认 100×30，
        # 球体错位裁剪（真机截图实证）。任何配置值下都要有正确几何。
        self.setFixedSize(int(self._win_d), int(self._win_d))
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
        self._glow_half = int(self._win_d * 0.52)  # 光晕最大半径(px)，用于局部重绘
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

        # 【v2.2】自定义贴图状态：
        #   _img_src 为空 QPixmap = 矢量球（默认分支，绘制路径与旧版逐像素一致）
        #   非空 = 已加载原图；_img_cache 为圆形裁剪结果（带 DPR 标签）惰性缓存
        self._img_src = QPixmap()
        self._img_cache = QPixmap()
        self._img_cache_dpr = 0.0       # 缓存生成时的 devicePixelRatio

    # ----【v2.2】自定义贴图 ----
    def set_ball_image(self, path: str):
        """设置/清除悬浮球自定义贴图；路径失效或加载失败时静默回退矢量球。

        不弹窗、不报错（启动时配置路径可能已失效），只切换渲染分支。
        """
        path = (path or "").strip()
        pm = QPixmap()
        if path and os.path.exists(path):
            try:
                pm = QPixmap(path)
                if not pm.isNull():
                    pm.setDevicePixelRatio(1.0)   # 归一化物理像素语义
            except Exception:
                pm = QPixmap()
        self._img_src = pm
        self._img_cache = QPixmap()      # 换图后强制重建缓存
        self._img_cache_dpr = 0.0
        self.update()

    def _masked_ball_pixmap(self) -> QPixmap:
        """取圆形裁剪贴图缓存（按当前 DPR 惰性生成；无图/失败返回空）。

        缓存键 = 当前 devicePixelRatio：控件跨屏迁移（DPR 变化）时自动重建，
        保证高 DPI 下贴图边缘依然锐利。
        """
        if self._img_src.isNull():
            return QPixmap()
        dpr = self.devicePixelRatioF()
        if self._img_cache.isNull() or abs(dpr - self._img_cache_dpr) > 1e-3:
            t = max(1, int(round(self._ball_d * dpr)))
            self._img_cache = circular_cover_pixmap(self._img_src, t)
            self._img_cache.setDevicePixelRatio(dpr)
            self._img_cache_dpr = dpr
        return self._img_cache

    # ----【v2.1.3】球径调整 ----
    def set_ball_size(self, d: int) -> bool:
        """设置球直径（28-72px）。窗口边长按 42:66 比例同步（球+24px 余量）。

        辉光/釉面/内阴影渐变缓存与贴图缓存均依赖球径，改径后全部重建。
        返回是否发生了变化。
        """
        d = max(28, min(72, int(d)))
        if d == self._ball_d:
            return False
        self._ball_d = float(d)
        self._win_d = d + 24
        self._glow_half = int(self._win_d * 0.52)
        self._img_cache = QPixmap()          # 贴图缓存按新球径重建
        self._glows = self._build_glow_layers()
        self._sp_grad, self._in_sh_grad, self._edge_grad = \
            self._build_static_shades()
        self.setFixedSize(self._win_d, self._win_d)
        self.update()
        return True

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

    # ----【v2.1.2】球体随主题换肤 ----
    def set_theme_colors(self, th: dict):
        """按主题字典切换球体配色：底色/悬停底/图标/辉光。

        辉光渐变在 __init__ 缓存，换色后必须重建；其余即时生效。
        """
        self._bg = QColor(*th["ball_bg"])
        self._bg_hover = QColor(*th["ball_bg_hover"])
        self._icon_color = QColor(*th["ball_icon"])
        self._glow_color = tuple(th["ball_glow"])
        self._glow_core = tuple(th["ball_glow_core"])
        self._glows = self._build_glow_layers()
        self.update()

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
        c = self._win_d / 2.0
        r, gg, b = self._glow_color
        cr, cg, cb = self._glow_core

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
            self._ball_d * 0.50,
            self._gaussian_stops(peak_pos=0.00, sigma=0.32, peak_a=96),
            cr, cg, cb))
        # 2) 紧贴球缘柔光环：高斯峰落在球缘，向外极短扩散、贴合球体。
        #    ball_edge_u = 球半径/光晕半径 ≈ 0.5/0.68 ≈ 0.74 → 光贴身、范围偏小。
        R2 = self._ball_d * self.GLOW_MAX_R
        ball_edge_u = (self._ball_d * 0.5) / R2
        layers.append(_rad(
            R2,
            self._gaussian_stops(peak_pos=ball_edge_u, sigma=0.15, peak_a=118),
            r, gg, b))
        return layers

    def _build_static_shades(self):
        """缓存不变的顶部釉面高光 / 底部内收阴影 / 玻璃细亮边缘，
        避免 paintEvent 重建渐变。"""
        sp = QRadialGradient(
            self._win_d / 2 - self._ball_d * 0.10,
            self._win_d / 2 - self._ball_d * 0.14, self._ball_d * 0.52)
        sp.setColorAt(0.0, QColor(255, 255, 255, 165))
        sp.setColorAt(0.55, QColor(255, 255, 255, 46))
        sp.setColorAt(1.0, QColor(255, 255, 255, 0))
        in_sh = QLinearGradient(
            self._win_d / 2 - self._ball_d / 2,
            self._win_d / 2 - self._ball_d * 0.20,
            self._win_d / 2 - self._ball_d / 2,
            self._win_d / 2 + self._ball_d / 2)
        in_sh.setColorAt(0.0, QColor(0, 0, 0, 0))
        in_sh.setColorAt(0.55, QColor(0, 0, 0, 0))
        in_sh.setColorAt(1.0, QColor(0, 0, 0, 118))
        # 玻璃细亮边缘：紧贴球缘的一道细亮环，模拟玻璃材质的高折射光边
        edge = QRadialGradient(
            self._win_d / 2, self._win_d / 2, self._ball_d / 2)
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

        off = (self.width() - self._ball_d) / 2.0
        offy = (self.height() - self._ball_d) / 2.0

        # 【v2.2】自定义贴图分支：圆形裁剪贴图（cover 模式）+ 玻璃细亮边缘。
        #   · 缩放/呼吸/按下/拖拽全部走上面同一套 painter 变换 → 贴图与
        #     底盘动效完全同步，不脱节
        #   · 矢量辉光层对贴图会叠加出脏色 → 贴图分支合理降级：跳过辉光，
        #     仅保留呼吸缩放（breath_scale 已在 scale 公式内）
        #   · 贴图加载失败（空缓存）→ 自然落入下方矢量分支，静默回退
        img = self._masked_ball_pixmap()
        if not img.isNull():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPixmap(QPointF(off, offy), img)
            if self._glow_enabled:
                painter.setBrush(self._edge_grad)
                painter.drawEllipse(QRectF(off, offy,
                                           self._ball_d, self._ball_d))
            painter.end()
            return

        # 圆形底：颜色随悬停进度插值（配色随主题）
        r = self._t
        bg = QColor(
            int(self._bg.red() + (self._bg_hover.red() - self._bg.red()) * r),
            int(self._bg.green() + (self._bg_hover.green() - self._bg.green()) * r),
            int(self._bg.blue() + (self._bg_hover.blue() - self._bg.blue()) * r),
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
            off + self._ball_d * 0.34, offy + self._ball_d * 0.32,
            self._ball_d * 0.72)
        vol.setColorAt(0.0, c0)
        vol.setColorAt(0.42, c1)
        vol.setColorAt(0.72, c2)
        vol.setColorAt(1.0, c3)
        painter.setBrush(vol)
        painter.drawEllipse(QRectF(off, offy, self._ball_d, self._ball_d))

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
        painter.drawEllipse(QRectF(off, offy, self._ball_d, self._ball_d))

        # 4) 玻璃细亮边缘 + 顶部釉面高光：开启光影时绘制（细亮高折射光边）
        if self._glow_enabled:
            painter.setBrush(self._edge_grad)
            painter.drawEllipse(QRectF(off, offy, self._ball_d, self._ball_d))
            painter.setBrush(self._sp_grad)
            painter.drawEllipse(QRectF(
                off - self._ball_d * 0.12, offy - self._ball_d * 0.12,
                self._ball_d * 1.24, self._ball_d * 1.24))

        # 2×2 四方块图标
        total = self._ball_d * 0.46
        gap = max(2.0, self._ball_d * 0.05)
        cell = (total - gap) / 2.0
        radius = max(2.0, cell * 0.28)
        ox = off + (self._ball_d - total) / 2.0
        oy = offy + (self._ball_d - total) / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._icon_color)
        painter.drawRoundedRect(QRectF(ox, oy, cell, cell), radius, radius)
        painter.drawRoundedRect(QRectF(ox + cell + gap, oy, cell, cell), radius, radius)
        painter.drawRoundedRect(QRectF(ox, oy + cell + gap, cell, cell), radius, radius)
        painter.drawRoundedRect(
            QRectF(ox + cell + gap, oy + cell + gap, cell, cell), radius, radius)
        painter.end()

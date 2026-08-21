# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck 统一动效令牌  -  anim_tokens
====================================================================
单一事实来源：所有 UI 动画的时长 / 缓动 / 位移 / 顺次延迟。

设计原则（见 docs/动效令牌方案.md）：
  · 令牌按「意图」分组，不按控件分组，保证同类动作手感一致
  · 进场快(OutCubic)、退场缓(InCubic)、反馈弹出(OutBack)
  · 时长只存 base 值（@speed=1.0），取用统一走 dur() 换算
  · 强约束：同一 (target, prop) 属性的动画经 play() 串行化，
    从机制上杜绝双动画并发操作同一属性（历史卡顿根源）
====================================================================
"""

from dataclasses import dataclass

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QAbstractAnimation


@dataclass(frozen=True)
class Motion:
    """单个动效令牌：时长(base)、缓动、顺次延迟、位移幅度。"""
    key: str
    duration: int
    easing: QEasingCurve.Type
    stagger_ms: int = 0
    travel: int = 0
    pause_ms: int = 0     # 循环动画在末尾追加的静默停顿（如呼吸间隔）


# Easing 色板（收敛后的唯一集合，禁止新造）
_EC = QEasingCurve.Type

# ====================================================================
# 令牌注册表（唯一 source of truth）
# ====================================================================
TOKENS: dict = {
    # ---- MICRO：按下 / 悬停等微反馈（90–150ms, OutCubic）----
    "ball.press.down": Motion("ball.press.down", 100, _EC.OutCubic),
    "item.hover": Motion("item.hover", 120, _EC.OutCubic),

    # ---- ENTER：一切「出现」（160–220ms, OutCubic）----
    "ball.hover.enter": Motion("ball.hover.enter", 140, _EC.OutCubic),
    "item.enter": Motion("item.enter", 120, _EC.OutCubic, stagger_ms=35),
    "panel.slide_in": Motion("panel.slide_in", 180, _EC.OutCubic, travel=14),
    "dialog.enter": Motion("dialog.enter", 200, _EC.OutCubic, travel=8),

    # ---- EXIT：一切「消失」（140–180ms, InCubic）----
    "ball.hover.exit": Motion("ball.hover.exit", 140, _EC.InOutCubic),
    "ball.idle.settle": Motion("ball.idle.settle", 120, _EC.OutCubic),
    "panel.slide_out": Motion("panel.slide_out", 150, _EC.InCubic, travel=14),
    "dialog.exit": Motion("dialog.exit", 150, _EC.InCubic, travel=8),

    # ---- MOVE：位移 / 滚动 / 吸附（200–260ms, OutCubic）----
    "ball.drag": Motion("ball.drag", 150, _EC.OutCubic),
    "ball.snap": Motion("ball.snap", 220, _EC.OutBack),   # 贴边带弹性过冲
    "panel.scroll": Motion("panel.scroll", 200, _EC.OutCubic),

    # ---- SPRING：弹性回弹反馈（OutBack）----
    "ball.press.up": Motion("ball.press.up", 150, _EC.OutBack),
    "item.launch.shrink": Motion("item.launch.shrink", 100, _EC.InCubic),
    "item.launch.bounce": Motion("item.launch.bounce", 150, _EC.OutBack),

    # ---- DECOR：循环装饰（固定周期，不随速度缩放）----
    # 呼吸：每半程 1.4s + 末尾静默停顿 1.2s（两次呼吸间留白，观感更从容）
    "ball.idle.pulse": Motion("ball.idle.pulse", 2800, _EC.InOutSine,
                              pause_ms=1200),
}

# 逐项入场延迟封顶
STAGGER_CAP_MS = 300

# 悬停浮球后面板自动收回的延迟（timer，非动画）
HIDE_DELAY_MS = 260


def motion(key: str) -> Motion:
    """按 key 取令牌；key 拼错时立即 KeyError 暴露。"""
    return TOKENS[key]


def dur(speed: float, base_ms: int) -> int:
    """base 时长按下速度档换算；speed 越界（0.5–2.0）自动夹取。"""
    return max(1, int(base_ms / max(0.5, min(2.0, float(speed)))))


def stagger_delay(index: int, step_ms: int, cap_ms: int = STAGGER_CAP_MS) -> int:
    """列表第 index 项的顺次入场延迟（封顶）。"""
    return min(index * step_ms, cap_ms)


def apply(anim, key: str, speed: float = 1.0):
    """把令牌的时长/缓动配置到已构建动画（QVariantAnimation / QPropertyAnimation 通用）。"""
    m = motion(key)
    anim.setDuration(dur(speed, m.duration))
    anim.setEasingCurve(m.easing)
    return anim


def play(target, prop, key: str, speed: float = 1.0,
         start=0.0, end=1.0, on_finished=None):
    """
    统一入口：对 target 的 prop 属性构建并启动一个 QPropertyAnimation。

    单属性锁：同一 (target, prop) 上若已有动画在跑，先 stop 它再开新的，
    从机制上杜绝双动画并发操作同一属性（历史：呼吸 vs hover 卡顿根源）。
    """
    # 规范属性名（str/bytes 混用时不误判锁）
    prop = prop.encode() if isinstance(prop, str) else prop

    store = getattr(target, "_ld_anim_locks", None)
    if store is None:
        store = {}
        try:
            setattr(target, "_ld_anim_locks", store)
        except (AttributeError, TypeError):
            store = None
    if store is not None:
        # 取出并清除旧引用：旧动画若已被 DeleteWhenStopped 删除，
        # 残留引用会变成 dangling，访问即崩溃，这里先 pop 再安全 stop。
        old = store.pop(prop, None)
        if old is not None:
            try:
                old.stop()
            except RuntimeError:
                pass    # 旧对象已释放（C++ 已删），忽略

    m = motion(key)
    anim = QPropertyAnimation(target, prop, target)
    anim.setDuration(dur(speed, m.duration))
    anim.setEasingCurve(m.easing)
    anim.setStartValue(start)
    anim.setEndValue(end)
    if on_finished is not None:
        anim.finished.connect(on_finished)
    if store is not None:
        store[prop] = anim
        # finished 后清除引用：配合 DeleteWhenStopped，避免锁字典残留
        # dangling 包装器（history 崩溃隐患）。
        anim.finished.connect(lambda p=prop: store.pop(p, None))
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim
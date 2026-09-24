# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck v2  -  全局热键（core/hotkey）
====================================================================
职责：
  · GlobalHotkeyFilter —— Win32 RegisterHotKey 全局组合键监听
  · qt_seq_to_win()    —— QKeySequence → (修饰符, 虚拟键码) 解析

【实现方案·重要】2026-09-23 重写
  旧方案「RegisterHotKey(hwnd=NULL) + QAbstractNativeEventFilter」在本机实测失效：
    · RegisterHotKey 返回 True（注册成功）
    · SendInput 注入组合键后，纯 Win32 PeekMessage 能收到 WM_HOTKEY
    · 但 Qt 事件分发器会把 hwnd==NULL 的**线程消息**从队列取走却不转发：
      实测过滤器收到 windows_* 消息 0 条，事后 PeekMessage 队列残留也是 0 条
      → 结论：WM_HOTKEY 被 Qt 吞掉了，过滤器永远收不到
  现方案：**独立工作线程 + GetMessageW 消息泵**（避坑，实测可用）
    · 热键由工作线程注册 → WM_HOTKEY 投递到该线程队列 → 该线程 GetMessage 取出
    · 通过 pyqtSignal 跨线程通知 GUI（跨线程自动 QueuedConnection，线程安全）
    · 退出：向工作线程 PostThreadMessage(WM_QUIT) → GetMessage 返回 0 → 自然退出

其它已踩过的坑：
  · PyQt6 的 QAbstractNativeEventFilter 不是 QObject，无法承载 pyqtSignal
  · Qt 的 installNativeEventFilter 不接管所有权，宿主须自行持有对象引用

  · MOD_NOREPEAT：按住不重复触发
  · Alt+Space 会全局屏蔽系统窗口菜单（RegisterHotKey 固有行为），可在设置里换键
====================================================================
"""

import ctypes
import threading
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QKeySequence

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# 热键 ID（进程内唯一即可）
HOTKEY_ID = 0xB00B

# Qt 修饰符 → Win32 修饰符
_MOD_MAP = {
    0x02000000: MOD_SHIFT,      # ShiftModifier
    0x04000000: MOD_CONTROL,    # ControlModifier
    0x08000000: MOD_ALT,        # AltModifier
    0x10000000: MOD_WIN,        # MetaModifier
}

# Qt.Key 基址（F1 = 0x01000030）
_QT_KEY_F1 = 0x01000030
_VK_F1 = 0x70


def _u32():
    """延迟获取 user32（模块导入时不触碰 Win32 API，便于单测）。"""
    return ctypes.WinDLL("user32", use_last_error=True)


def _k32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


class MSG(ctypes.Structure):
    """Windows MSG 结构。"""
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


# ==================================================================
# QKeySequence 解析
# ==================================================================
def qt_seq_to_win(seq: QKeySequence):
    """
    把 QKeySequence 解析为 Win32 (modifiers, virtual_key)。

    返回 None 表示无法解析（空序列 / 无修饰符的裸键 / 多键序列 / 不支持的键）。
    """
    if seq is None or seq.isEmpty() or seq.count() != 1:
        return None
    combo = seq[0]
    key = combo.key()
    mods = combo.keyboardModifiers()

    win_mods = 0
    for m in mods:
        v = getattr(m, "value", m)     # PyQt6 枚举成员需取 .value
        win_mods |= _MOD_MAP.get(int(v), 0)

    k = int(key) & 0x01FFFFFF          # 去掉枚举高位标记
    if _QT_KEY_F1 <= k <= _QT_KEY_F1 + 0x0F:      # F1~F16
        vk = _VK_F1 + (k - _QT_KEY_F1)
    elif 0x20 <= k <= 0x5A:                        # Space / 字母 / 数字等
        vk = k
    else:
        return None

    if win_mods == 0:
        return None        # 不允许无修饰符的裸键做全局热键
    return win_mods, vk


# ==================================================================
# 工作线程：注册热键 + 消息泵
# ==================================================================
class _HotkeyWorker(threading.Thread):
    """
    在**独立线程**里 RegisterHotKey 并跑 GetMessage 消息泵。

    为什么必须独立线程：Qt 主线程的事件分发器会吞掉 hwnd==NULL 的 WM_HOTKEY
    （既不转发给 nativeEventFilter，也不投递给任何窗口），详见模块文档。
    独立线程的消息泵不受 Qt 干扰，实测可靠。

    退出方式：向本线程 PostThreadMessage(WM_QUIT) → GetMessage 返回 0 → 自然退出。
    """

    def __init__(self, mods: int, vk: int, on_hit):
        super().__init__(daemon=True, name="LaunchDeck-Hotkey")
        self._mods = mods
        self._vk = vk
        self._on_hit = on_hit
        self._ready = threading.Event()
        self._tid = 0
        self.ok = False            # 注册是否成功（run 启动后有效）

    @property
    def thread_id(self) -> int:
        return self._tid

    def stop(self, timeout: float = 2.0):
        """请求线程退出并等待；绝不抛异常。"""
        try:
            if self._tid:
                _u32().PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        except Exception:
            pass
        try:
            self.join(timeout)
        except Exception:
            pass

    def run(self):
        try:
            self._tid = _k32().GetCurrentThreadId()
            self._ready.set()

            if not _u32().RegisterHotKey(
                    None, HOTKEY_ID,
                    self._mods | MOD_NOREPEAT, self._vk):
                self.ok = False
                return
            self.ok = True

            msg = MSG()
            # GetMessageW：>0 正常 / 0 = WM_QUIT / -1 = 错误
            while True:
                ret = _u32().GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret <= 0:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    try:
                        self._on_hit()
                    except Exception:
                        pass        # 回调异常绝不能杀死消息泵
        except Exception:
            pass
        finally:
            try:
                _u32().UnregisterHotKey(None, HOTKEY_ID)
            except Exception:
                pass
            self.ok = False


# ==================================================================
# 对外主类
# ==================================================================
class GlobalHotkeyFilter(QObject):
    """
    全局热键管理对象（QObject，承载 pyqtSignal）。

    注意：本类**不再**继承 QAbstractNativeEventFilter，因此不需要（也不应）
    调用 installNativeEventFilter —— 热键由内部工作线程独立监听。

    用法：
        hk = GlobalHotkeyFilter()
        hk.toggled.connect(ball.toggle_visible)
        hk.register_sequence("Alt+Space")
        # 退出前：
        hk.unregister()

    宿主需持有本对象引用直至退出（Qt 不接管所有权，被 GC 后热键失效）。
    """

    toggled = pyqtSignal()      # 热键触发（显示/隐藏语义由宿主决定）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._seq_str = ""
        self._registered = False
        self._lock = threading.Lock()

    # ---------- 属性 ----------
    @property
    def registered(self) -> bool:
        return self._registered

    @property
    def sequence_text(self) -> str:
        return self._seq_str

    # ---------- 注册 / 注销 ----------
    def register_sequence(self, seq_str: str) -> bool:
        """
        按字符串（如 "Alt+Space"）注册热键；先注销旧的再注册新的。

        返回是否注册成功。失败时保持未注册状态（组合键被其它程序占用等）。
        """
        with self._lock:
            self._stop_worker()

            parsed = qt_seq_to_win(QKeySequence(seq_str or ""))
            if parsed is None:
                self._registered = False
                self._seq_str = ""
                return False

            mods, vk = parsed
            w = _HotkeyWorker(mods, vk, self._emit_toggled)
            self._worker = w
            w.start()
            w._ready.wait(2.0)      # 等线程拿到 tid（stop 时要用）

            # RegisterHotKey 在 run() 中执行，短暂等待落地结果
            for _ in range(50):
                if w.ok:
                    break
                if not w.is_alive():
                    break
                threading.Event().wait(0.02)

            if not w.ok:
                # 注册失败（多半被占用）：收尾并报错，不留下僵尸线程
                w.stop()
                self._worker = None
                self._registered = False
                self._seq_str = ""
                return False

            self._registered = True
            self._seq_str = seq_str
            return True

    def unregister(self):
        """注销全局热键（未注册时静默）。"""
        with self._lock:
            self._stop_worker()
            self._registered = False
            self._seq_str = ""

    # ---------- 内部 ----------
    def _stop_worker(self):
        w, self._worker = self._worker, None
        if w is not None:
            w.stop()

    def _emit_toggled(self):
        """工作线程回调 → 跨线程 emit（Qt 自动 QueuedConnection，线程安全）。"""
        try:
            self.toggled.emit()
        except Exception:
            pass

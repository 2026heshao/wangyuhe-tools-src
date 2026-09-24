# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck v2.1  -  进程探测（core/process_utils）
====================================================================
职责：
  · running_exe_names()  —— 枚举当前所有进程的 exe 文件名集合
  · is_running(exe_path) —— 判断某应用是否正在运行（按 exe 文件名匹配）
  · activate_window(exe_path) —— 前置该应用的可见窗口（点击不重复启动）

实现说明：
  · 用 kernel32 CreateToolhelp32Snapshot 枚举进程（wmic 已被系统策略
    拉黑、psutil 不引入依赖，此为标准库方案）
  · 只按「exe 文件名」匹配（不比对完整路径）：即使程序从别处再开
    一个实例也能识别；代价是同名不同路径的罕见情况会误判（可接受）
  · .lnk / 文档类条目无法匹配（拿不到目标进程名），不显示运行点
  · 结果带 2 秒缓存，避免面板高频刷新时反复快照
====================================================================
"""

import os
import time
import ctypes
from ctypes import wintypes

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value or -1
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# 运行状态缓存：(时间戳, 名字集合)
_proc_cache = (0.0, frozenset())
_CACHE_TTL = 2.0


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),   # ULONG_PTR
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _u32():
    return ctypes.WinDLL("user32", use_last_error=True)


def _k32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def running_exe_names() -> frozenset:
    """当前所有进程 exe 文件名的小写集合（带 2 秒缓存）。"""
    global _proc_cache
    now = time.monotonic()
    if now - _proc_cache[0] < _CACHE_TTL:
        return _proc_cache[1]
    names = set()
    try:
        k32 = _k32()
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap not in (0, -1, INVALID_HANDLE_VALUE):
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            ok = k32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                try:
                    names.add(entry.szExeFile.lower())
                except Exception:
                    pass
                ok = k32.Process32NextW(snap, ctypes.byref(entry))
            k32.CloseHandle(snap)
    except Exception:
        pass
    _proc_cache = (now, frozenset(names))
    return _proc_cache[1]


def is_running(exe_path: str) -> bool:
    """该应用是否正在运行（仅对 .exe 条目有效；.lnk/文档返回 False）。"""
    name = os.path.basename(exe_path or "").strip().lower()
    if not name or not name.endswith(".exe"):
        return False
    return name in running_exe_names()


def running_set_for(apps: list) -> set:
    """批量判断：返回 apps 中正在运行的条目下标集合（一次快照多次判断）。"""
    names = running_exe_names()
    result = set()
    for i, app in enumerate(apps):
        name = os.path.basename((app or {}).get("exe_path", "") or "").lower()
        if name and name.endswith(".exe") and name in names:
            result.add(i)
    return result


# ---------------- 窗口前置 ----------------
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def activate_window(exe_path: str) -> bool:
    """
    找到该 exe 的一个可见顶层窗口并前置（还原最小化）。

    返回是否找到并尝试前置。注意：Windows 前台锁定策略可能拒绝
    后台进程直接抢焦点，此时任务栏会闪烁提示（标准行为，非 bug）。
    """
    target = os.path.basename(exe_path or "").strip().lower()
    if not target or not target.endswith(".exe"):
        return False
    try:
        user32 = _u32()
        k32 = _k32()
        found = []

        def _proc_image(pid: int) -> str:
            h = k32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                return ""
            try:
                size = wintypes.DWORD(1024)
                buf = ctypes.create_unicode_buffer(1024)
                if k32.QueryFullProcessImageNameW(
                        h, 0, buf, ctypes.byref(size)):
                    return os.path.basename(buf.value).lower()
            finally:
                k32.CloseHandle(h)
            return ""

        @EnumProc
        def _cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            # 跳过工具窗口（无标题小窗，如托盘浮层）
            if user32.GetWindowLongW(hwnd, -20) & 0x00000080:  # WS_EX_TOOLWINDOW
                return True
            if user32.GetWindowTextLengthW(hwnd) == 0:
                return True
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value and _proc_image(pid.value) == target:
                found.append(hwnd)
                return False     # 找到即停
            return True

        user32.EnumWindows(_cb, 0)
        if not found:
            return False
        hwnd = found[0]
        if user32.IsIconic(hwnd):                 # 最小化 → 先还原
            user32.ShowWindowAsync(hwnd, 9)       # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False

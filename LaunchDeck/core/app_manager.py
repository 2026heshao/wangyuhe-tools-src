# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck 核心  -  app_manager
====================================================================
职责：
  · AppManager       —— config.json 读写（apps 软件列表 + settings 设置项）
  · get_exe_name     —— 从 exe 版本资源识别软件名称
                        （FileDescription → ProductName → 文件名去扩展名）
  · extract_app_icon —— 从 exe 提取图标（保留原始颜色，平滑缩放），带缓存
  · launch_app       —— 异步启动外部程序（含 740 需提权回退）
====================================================================
"""

import os
import sys
import json
import ctypes
import subprocess

from PyQt6.QtCore import Qt, QSize, QFileInfo
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QFont
from PyQt6.QtWidgets import QFileIconProvider, QMessageBox


# 项目根目录（core/ 的上一级）。注意：打包成 exe 后此目录指向 PyInstaller
# 临时解压目录（_MEIPASS），不可持久写，仅作旧配置迁移源使用。
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ====================================================================
# 数据目录 / 配置文件路径解析
# ====================================================================
# 目标：打包后配置可持久存放、且程序运行位置固定。
#   · 打包成 exe → 使用 exe 所在目录（旁边），升级/搬家随程序走
#   · 脚本开发   → 使用项目根目录（行为与旧版一致）
#   · 目标目录只读（如安装到 Program Files）→ 自动回退到用户数据目录
# 缺失时自动生成默认配置并落盘；检测到旧位置配置 → 自动迁移。
# ====================================================================

APP_DIR_NAME = "LaunchDeck"


def _is_frozen() -> bool:
    """当前是否运行在 PyInstaller 打包后的 exe 中。"""
    return bool(getattr(sys, "frozen", False))


def _resolve_data_dir() -> str:
    """
    确定配置持久化目录：exe 所在目录（打包）或项目根（开发）。

    若首选目录不可写，自动回退到用户数据目录
    （%LOCALAPPDATA%\\LaunchDeck），保证始终有可写位置。
    """
    # 1) 首选：exe 旁（打包）/ 项目根（开发）
    if _is_frozen():
        preferred = os.path.dirname(os.path.abspath(sys.executable))
    else:
        preferred = BASE_DIR
    if _is_writable(preferred):
        return preferred

    # 2) 回退：用户本地数据目录（%LOCALAPPDATA%\LaunchDeck）
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    fallback = os.path.join(base, APP_DIR_NAME)
    try:
        os.makedirs(fallback, exist_ok=True)
    except OSError:
        pass
    if _is_writable(fallback):
        return fallback

    # 3) 再失败：程序内临时目录（仅内存有效，尽力而为）
    return os.path.dirname(os.path.abspath(sys.executable)) \
        if _is_frozen() else BASE_DIR


def _is_writable(directory: str) -> bool:
    """写探针：目录存在且可创建/删除临时文件。"""
    try:
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        probe = os.path.join(directory, ".ld_write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("")
        os.remove(probe)
        return True
    except OSError:
        return False


# 最终数据目录与配置文件路径（import 时解析一次）
DATA_DIR = _resolve_data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

# 旧版配置路径（打包前项目根，或旧 exe 目录），用于首次迁移
LEGACY_CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# 设置项默认值
DEFAULT_SETTINGS = {
    "icon_size":     40,     # 面板图标边长（32-42）
    "panel_opacity": 0.87,   # 面板背景不透明度（0.50-1.00）
    "anim_speed":    1.0,    # 动画速度倍率（0.5-2.0，越大越快）
    "enable_idle_pulse": True,   # 【新增·需求1】闲置呼吸动画开关
    "show_glow":          True,  # 【新增】悬浮球光影开关（三层辉光）
    "ball_x":        None,   # 浮球窗口位置（None = 左缘垂直居中）
    "ball_y":        None,
}


# ====================================================================
# 配置管理
# ====================================================================

class AppManager:
    """
    config.json 的读写封装。

    数据结构：
      {
        "apps":     [{"name": "...", "exe_path": "..."}, ...],
        "settings": {"icon_size": 40, "panel_opacity": 0.87,
                     "anim_speed": 1.0, "ball_x": null, "ball_y": null}
      }
    """

    def __init__(self):
        self._data = {"apps": [], "settings": dict(DEFAULT_SETTINGS)}
        self.load()

    # ---------------- 读写 ----------------
    def load(self):
        """
        从磁盘加载配置；缺失 / 损坏时使用默认值。

        自动生成与迁移：
          · 目标 config 不存在，但旧位置（LEGACY_CONFIG_PATH）存在
            → 首次自动迁移（复制后删除旧文件）
          · 目标 config 不存在，旧位置也不存在 → 生成一份默认配置并落盘
          · 缺失字段永远用 DEFAULT_SETTINGS 补齐
        """
        loaded = None
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (OSError, ValueError):
            loaded = None

        # 【新增】目标缺失 → 尝试从旧位置迁移
        if loaded is None and self._migrate_legacy():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
            except (OSError, ValueError):
                loaded = None

        if isinstance(loaded, dict):
            self._data = loaded

        # 补齐缺失字段
        if not isinstance(self._data.get("apps"), list):
            self._data["apps"] = []
        settings = self._data.get("settings")
        if not isinstance(settings, dict):
            settings = {}
        merged = dict(DEFAULT_SETTINGS)
        merged.update(settings)
        self._data["settings"] = merged

        # 【新增】文件缺失 → 生成默认并落盘，保证打包后首启即可持久化
        if not os.path.exists(CONFIG_PATH):
            self.save()

    @staticmethod
    def _migrate_legacy() -> bool:
        """
        从旧位置迁移 config.json 到新数据目录（复制成功 → 删除旧文件）。

        旧位置与新位置相同时无需迁移。任何失败均静默回退（不影响启动）。
        """
        try:
            legacy = os.path.normpath(LEGACY_CONFIG_PATH)
            target = os.path.normpath(CONFIG_PATH)
            if legacy == target or not os.path.exists(legacy):
                return False
            os.makedirs(os.path.dirname(target), exist_ok=True)
            import shutil
            shutil.copy2(legacy, target)
            try:
                os.remove(legacy)
            except OSError:
                pass            # 删不掉不影响（旧文件残留无害）
            return True
        except OSError:
            return False

    def save(self):
        """将内存配置写回磁盘（缩进 2，保留中文）。失败静默，不崩溃。"""
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ---------------- 属性访问 ----------------
    @property
    def apps(self) -> list:
        """软件列表：[{"name": str, "exe_path": str}, ...]"""
        return self._data["apps"]

    @apps.setter
    def apps(self, value: list):
        self._data["apps"] = [a for a in value if isinstance(a, dict)]

    @property
    def settings(self) -> dict:
        return self._data["settings"]

    def set_setting(self, key: str, value):
        """更新单个设置项并立即持久化。"""
        self._data["settings"][key] = value
        self.save()


# ====================================================================
# exe 名称识别（Win32 版本资源）
# ====================================================================

def get_exe_name(exe_path: str) -> str:
    """
    从 exe 的版本资源里识别软件显示名称。

    优先级：FileDescription → ProductName → 文件名去扩展名。
    任何失败（非 Windows / 无版本信息 / 路径无效）都回退到文件名。
    """
    fallback = os.path.splitext(os.path.basename(exe_path))[0] if exe_path else ""
    if not exe_path or not os.path.exists(exe_path):
        return fallback
    try:
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(exe_path, None)
        if not size:
            return fallback
        data = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(exe_path, 0, size, data):
            return fallback

        # 取翻译表 → 拼出 StringFileInfo 的语言码 (如 080404b0)
        buf = ctypes.c_void_p()
        buf_len = ctypes.c_uint()
        if not ver.VerQueryValueW(data, "\\VarFileInfo\\Translation",
                                  ctypes.byref(buf), ctypes.byref(buf_len)):
            return fallback
        if not buf.value or buf_len.value < 4:
            return fallback
        lang, codepage = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint16))[0:2]
        lang_id = f"{lang:04X}{codepage:04X}"

        # 依次查询 FileDescription / ProductName
        for key in ("FileDescription", "ProductName"):
            vbuf = ctypes.c_void_p()
            vlen = ctypes.c_uint()
            sub = f"\\StringFileInfo\\{lang_id}\\{key}"
            if ver.VerQueryValueW(data, sub,
                                  ctypes.byref(vbuf), ctypes.byref(vlen)) and vbuf.value:
                text = ctypes.wstring_at(vbuf.value, vlen.value - 1).strip()
                if text:
                    return text
    except Exception:
        pass
    return fallback


# ====================================================================
# 图标提取（保留原始颜色）
# ====================================================================

# 图标缓存：(exe_path, size) → QPixmap（原始颜色）
_icon_cache: dict = {}


def _placeholder_icon(size: int, name_hint: str = "") -> QPixmap:
    """兜底图标：深灰圆角块 + 名称首字（对应原型"未收录"样式）。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#3A3E48"))
    r = max(3.0, size * 0.22)
    painter.drawRoundedRect(0, 0, size, size, r, r)

    letter = (name_hint or "?").strip()[:1].upper() or "?"
    painter.setPen(QPen(QColor("#C9CBD2")))
    font = QFont("Segoe UI", pointSize=max(6, int(size * 0.42)))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, letter)
    painter.end()
    return pixmap


def extract_app_icon(exe_path: str, size: int, name_hint: str = "") -> QPixmap:
    """
    从 exe 提取图标（QFileIconProvider 系统图标），保留原始颜色，结果缓存。

    - 请求大尺寸位图（128px）再平滑缩放到目标尺寸，
      避免小位图被直接放大导致发糊
    - 提取失败 / 路径无效 → 字母占位图标
    """
    cache_key = (exe_path or "", size, name_hint or "")
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    pixmap = QPixmap()
    if exe_path and os.path.exists(exe_path):
        try:
            provider = QFileIconProvider()
            icon = provider.icon(QFileInfo(exe_path))
            big = icon.pixmap(QSize(128, 128))
            if not big.isNull():
                dpr = big.devicePixelRatioF() or 1.0
                target = max(1, int(size * dpr))
                pixmap = big.scaled(
                    target, target,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                pixmap.setDevicePixelRatio(dpr)
        except Exception:
            pixmap = QPixmap()

    if pixmap.isNull():
        result = _placeholder_icon(size, name_hint or os.path.basename(exe_path or ""))
    else:
        result = pixmap

    _icon_cache[cache_key] = result
    return result


def clear_icon_cache():
    """清空图标缓存（配置变更后重建面板前调用）。"""
    _icon_cache.clear()


# ====================================================================
# 【新增·需求2】Windows 开机自启（HKCU\...\Run 注册表，内置 winreg）
# ====================================================================

AUTOSTART_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_REG_NAME = "LaunchDeck"


def is_frozen_app() -> bool:
    """是否为打包后的 exe（开发脚本模式 sys.frozen 不存在）。"""
    return bool(getattr(sys, "frozen", False))


def is_autostart_enabled() -> bool:
    """
    实时读注册表判断自启状态（不以 json 存储为准）。
    非 Windows / 键不存在 / 任何异常 → False。
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            AUTOSTART_REG_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_REG_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_autostart(enabled: bool):
    """
    写入/删除注册表自启键，返回 (成功?, 提示消息)。

    - 仅 Windows；开发模式（py 脚本运行）不写入并返回提示
    - exe 路径用引号包裹，兼容含空格路径
    - 无注册表权限等所有异常均捕获，不崩溃
    """
    if sys.platform != "win32":
        return False, "当前系统不是 Windows，不支持开机自启。"
    if not is_frozen_app():
        return False, ("当前为开发模式（脚本运行），不写入注册表。\n"
                       "打包为 exe 后即可使用开机自启功能。")
    try:
        import winreg
        if enabled:
            # 引号包裹完整 exe 路径，防止路径含空格被截断
            exe = f'"{os.path.abspath(sys.executable)}"'
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                AUTOSTART_REG_PATH, 0,
                                winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, AUTOSTART_REG_NAME, 0,
                                  winreg.REG_SZ, exe)
            return True, "已开启开机自启。"
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                    AUTOSTART_REG_PATH, 0,
                                    winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, AUTOSTART_REG_NAME)
            except FileNotFoundError:
                pass   # 本就不存在 → 视为已关闭
            return True, "已关闭开机自启。"
    except OSError as e:
        return False, f"注册表操作失败（可能无权限）：\n{e}"
    except Exception as e:
        return False, f"注册表操作异常：\n{e}"


# ====================================================================
# 启动外部程序
# ====================================================================

def launch_app(exe_path: str, name: str, parent=None) -> bool:
    """
    异步启动外部 exe（Popen 不等待，不阻塞事件循环）。

    Windows 错误 740（需要管理员权限）→ ShellExecuteW "runas" 提权重试，
    其余失败弹中文提示。

    【修复·打包崩溃】打包环境下 close_fds=True 会强制关闭子进程继承的
    句柄，导致父进程崩溃；改用 CREATE_NO_WINDOW + 重定向 std 句柄到
    DEVNULL，安全隔离子进程。
    """
    exe_path = (exe_path or "").strip()
    print("[LD-DEBUG] launch_app 调用: name=", name, "exe_path=", exe_path, flush=True)
    if not exe_path:
        QMessageBox.warning(parent, "启动失败", f"「{name}」的可执行文件路径为空。")
        return False
    if not os.path.exists(exe_path):
        print("[LD-DEBUG] launch_app 路径不存在: ", exe_path, flush=True)
        QMessageBox.warning(
            parent, "启动失败",
            f"找不到「{name}」的可执行文件：\n{exe_path}\n\n"
            "文件可能已被移动或删除，请在设置中修正路径。",
        )
        return False

    try:
        # 【修复·打包崩溃】去掉 close_fds=True（PyInstaller + Windows 下
        # 强制关闭继承句柄会导致父进程崩溃）；改用 DEVNULL 重定向标准句柄
        # 隔离子进程，不影响 GUI 窗口正常显示。
        p = subprocess.Popen(
            [exe_path],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("[LD-DEBUG] launch_app Popen 成功, pid=", p.pid, flush=True)
        return True
    except FileNotFoundError:
        QMessageBox.warning(parent, "启动失败",
                            f"找不到「{name}」的可执行文件。\n路径：{exe_path}")
        return False
    except OSError as e:
        if getattr(e, "winerror", None) == 740:
            return _launch_elevated(exe_path, name, parent)
        QMessageBox.critical(parent, "启动异常",
                             f"启动「{name}」时发生异常：\n{str(e)}")
        return False
    except Exception as e:
        QMessageBox.critical(parent, "启动异常",
                             f"启动「{name}」时发生异常：\n{str(e)}")
        return False


def _launch_elevated(exe_path: str, name: str, parent=None) -> bool:
    """以管理员权限启动（UAC 确认框由系统弹出）。"""
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe_path, None, None, 1,
        )
        if ret > 32:
            return True
        QMessageBox.information(parent, "已取消",
                                f"已取消以管理员权限启动「{name}」。")
        return False
    except Exception as e:
        QMessageBox.critical(parent, "启动异常",
                             f"以管理员权限启动「{name}」失败：\n{str(e)}")
        return False

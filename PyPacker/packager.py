# -*- coding: utf-8 -*-
"""
打包核心逻辑模块
- PyInstaller命令拼接
- 环境检测（PyInstaller是否安装）
- 异步打包子线程（QThread），实时流式输出日志
- 前置校验：主文件合法性、输出目录权限
"""

import os
import sys
import subprocess
import shutil

from PyQt6.QtCore import QThread, pyqtSignal

# 是否在 PyInstaller 打包后的 exe 中运行
IS_FROZEN = getattr(sys, "frozen", False)


# ========== 命令拼接 ==========
def build_command(config):
    """
    根据UI配置拼接完整的PyInstaller命令行
    返回: list[str] （便于subprocess调用，避免空格转义问题）
    """
    main_py = config.get("main_py", "").strip()
    if not main_py:
        return []

    # 确定python解释器（优先虚拟环境）
    venv_path = config.get("venv_path", "").strip()
    python_exe = _get_python_executable(venv_path)
    if not python_exe:
        return []  # 未找到Python解释器，无法打包

    cmd = [python_exe, "-m", "PyInstaller"]

    # 重复打包时自动覆盖已有同名产物，无需手动删除或交互确认
    cmd.append("-y")

    # 输出模式
    if config.get("output_mode") == "onefile":
        cmd.append("-F")
    else:
        cmd.append("-D")

    # 控制台模式
    if config.get("console_mode") == "gui":
        cmd.append("-w")
    else:
        cmd.append("-c")

    # 自定义图标
    icon = config.get("icon_path", "").strip()
    if icon and os.path.isfile(icon):
        cmd.extend(["-i", icon])

    # 自定义输出程序名称（-n）
    exe_name = config.get("exe_name", "").strip()
    if exe_name:
        cmd.extend(["-n", exe_name])

    # 附加依赖收集（--collect-all）- 仅当复选框启用且内容非空
    if config.get("collect_enabled"):
        collect = config.get("collect_imports", "").strip()
        if collect:
            for line in collect.splitlines():
                line = line.strip()
                if line:
                    cmd.extend(["--collect-all", line])

    # 排除库（--exclude-module）- 仅当复选框启用且内容非空
    if config.get("exclude_enabled"):
        exclude = config.get("exclude_imports", "").strip()
        if exclude:
            for line in exclude.splitlines():
                line = line.strip()
                if line:
                    cmd.extend(["--exclude-module", line])

    # 调试日志
    if config.get("debug_log"):
        cmd.extend(["--log-level", "DEBUG"])
    else:
        cmd.extend(["--log-level", "INFO"])

    # 输出目录
    output_dir = config.get("output_dir", "").strip()
    if output_dir:
        cmd.extend(["--distpath", os.path.join(output_dir, "dist")])
        cmd.extend(["--workpath", os.path.join(output_dir, "build")])
        cmd.extend(["--specpath", output_dir])

    # 项目根目录（作为工作目录）
    project_root = config.get("project_root", "").strip()
    if project_root and os.path.isdir(project_root):
        cmd.extend(["--paths", project_root])

    # 主入口文件
    cmd.append(main_py)

    return cmd


def build_command_str(config):
    """
    返回可读的完整命令字符串（用于复制到剪贴板）
    带引号包裹含空格的路径
    """
    cmd = build_command(config)
    if not cmd:
        return ""
    quoted = []
    for part in cmd:
        if " " in part and not part.startswith('"'):
            quoted.append(f'"{part}"')
        else:
            quoted.append(part)
    return " ".join(quoted)


def _get_python_executable(venv_path=""):
    """获取Python解释器路径，优先虚拟环境"""
    if venv_path and os.path.isdir(venv_path):
        candidate = os.path.join(venv_path, "Scripts", "python.exe")
        if os.path.isfile(candidate):
            return candidate
        candidate = os.path.join(venv_path, "bin", "python")
        if os.path.isfile(candidate):
            return candidate
    # PyInstaller 打包后 sys.executable 是 exe 自身，不是 Python 解释器
    # 必须查找系统 Python，否则会递归启动 exe 自身导致无限循环
    if IS_FROZEN:
        return _find_system_python()
    return sys.executable


# 缓存已解析的系统 Python 解释器，保证检测与打包使用同一个
_cached_system_python = None


def _find_all_python_candidates():
    """收集系统里所有候选 Python 解释器路径（已去重）"""
    candidates = []
    # 1. 从 PATH 中查找
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            # 排除自身（frozen 时 sys.executable 是 exe）
            abs_found = os.path.abspath(found)
            if os.path.normcase(abs_found) != os.path.normcase(os.path.abspath(sys.executable)):
                if abs_found not in candidates:
                    candidates.append(abs_found)
    # 2. 常见 Windows 安装位置
    # %LOCALAPPDATA%\Programs\Python
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        base = os.path.join(local_appdata, "Programs", "Python")
        if os.path.isdir(base):
            for d in sorted(os.listdir(base), reverse=True):
                exe = os.path.join(base, d, "python.exe")
                if os.path.isfile(exe) and exe not in candidates:
                    candidates.append(exe)
    # C:\Python3x
    import glob
    for pattern in (r"C:\Python3*", r"C:\Program Files\Python3*"):
        for d in sorted(glob.glob(pattern), reverse=True):
            exe = os.path.join(d, "python.exe")
            if os.path.isfile(exe) and exe not in candidates:
                candidates.append(exe)
    return candidates


def _has_pyinstaller(python_exe):
    """检查指定 Python 是否已安装 PyInstaller，返回版本号或空串"""
    try:
        result = subprocess.run(
            [python_exe, "-m", "PyInstaller", "--version"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _find_system_python():
    """在 PyInstaller frozen 环境下查找系统 Python 解释器

    遍历所有候选解释器，优先选中真正安装有 PyInstaller 的那个；
    都不满足时回退到第一个（版本最高的）。结果缓存避免重复检测。
    """
    global _cached_system_python
    if _cached_system_python is not None:
        return _cached_system_python

    candidates = _find_all_python_candidates()
    chosen = ""
    for exe in candidates:
        if _has_pyinstaller(exe):
            chosen = exe
            break
    if not chosen and candidates:
        chosen = candidates[0]

    _cached_system_python = chosen
    return chosen


# ========== 环境检测 ==========
# 以 python 解释器路径为 key 缓存检测结果，避免每次弹出主窗口都启动子进程导致界面卡顿
_pyinstaller_cache = {}


def check_pyinstaller(venv_path="", _force=False):
    """
    检测PyInstaller是否已安装
    返回: (installed: bool, version: str)
    结果按 python 解释器缓存；_force=True 时强制重新检测
    """
    python_exe = _get_python_executable(venv_path)
    if not _force and python_exe in _pyinstaller_cache:
        return _pyinstaller_cache[python_exe]
    installed, version = False, ""
    try:
        result = subprocess.run(
            [python_exe, "-m", "PyInstaller", "--version"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            installed, version = True, result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        installed, version = False, ""
    _pyinstaller_cache[python_exe] = (installed, version)
    return installed, version


def install_pyinstaller(venv_path=""):
    """
    一键pip安装PyInstaller
    返回: (success: bool, output: str)
    """
    python_exe = _get_python_executable(venv_path)
    global _cached_system_python
    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "install", "pyinstaller", "--upgrade"],
            capture_output=True, text=True, timeout=180
        )
        output = result.stdout + result.stderr
        if result.returncode == 0:
            # 安装成功后清掉该解释器的缓存，让下一次检测拿到最新结果
            _pyinstaller_cache.pop(python_exe, None)
            _cached_system_python = None
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "安装超时，请检查网络连接"
    except (FileNotFoundError, OSError) as e:
        return False, f"安装失败：{str(e)}"


# ========== 前置校验 ==========
def validate_config(config):
    """
    打包前前置校验
    返回: (valid: bool, errors: list[str], warnings: list[str])
    """
    errors = []
    warnings = []

    main_py = config.get("main_py", "").strip()
    if not main_py:
        errors.append("未选择主入口PY文件")
    elif not os.path.isfile(main_py):
        errors.append(f"主入口文件不存在：{main_py}")
    elif not main_py.lower().endswith(".py"):
        errors.append("主入口文件必须是 .py 后缀")

    output_dir = config.get("output_dir", "").strip()
    if output_dir:
        if not os.path.isdir(output_dir):
            errors.append(f"输出目录不存在：{output_dir}")
        elif not os.access(output_dir, os.W_OK):
            errors.append(f"输出目录无写入权限：{output_dir}")
    else:
        # 未指定输出目录，默认使用项目根目录，给出警告
        warnings.append("未指定输出目录，将默认输出到项目根目录下的 dist 文件夹")

    venv_path = config.get("venv_path", "").strip()
    if venv_path and not os.path.isdir(venv_path):
        errors.append(f"虚拟环境路径不存在：{venv_path}")

    icon = config.get("icon_path", "").strip()
    if icon and not os.path.isfile(icon):
        warnings.append(f"图标文件不存在，将使用默认图标：{icon}")

    return (len(errors) == 0), errors, warnings


# ========== 异步打包子线程 ==========
class PackagerThread(QThread):
    """
    打包子线程，完全不卡死UI主线程
    信号:
        log_signal(level, message)  level: info/warning/error/success
        finished_signal(success, output_dir)
    """
    log_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._process = None
        self._cancelled = False

    def cancel(self):
        """取消打包（终止子进程）"""
        self._cancelled = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except OSError:
                pass

    def run(self):
        """线程主函数：执行打包并流式输出日志"""
        config = self.config
        cmd = build_command(config)
        if not cmd:
            self.log_signal.emit("error", "命令拼接失败：未找到主入口文件")
            self.finished_signal.emit(False, "")
            return

        # 工作目录
        project_root = config.get("project_root", "").strip()
        work_dir = project_root if project_root and os.path.isdir(project_root) else None

        # 输出目录
        output_dir = config.get("output_dir", "").strip()
        if not output_dir and work_dir:
            output_dir = work_dir

        self.log_signal.emit("info", "=" * 60)
        self.log_signal.emit("info", "PyPacker 开始打包")
        self.log_signal.emit("info", f"主入口: {config.get('main_py', '')}")
        self.log_signal.emit("info", f"工作目录: {work_dir or '（未指定）'}")
        self.log_signal.emit("info", f"输出目录: {output_dir or '（默认）'}")
        self.log_signal.emit("info", f"执行命令: {build_command_str(config)}")
        self.log_signal.emit("info", "=" * 60)

        # 检测PyInstaller
        venv_path = config.get("venv_path", "").strip()
        installed, version = check_pyinstaller(venv_path)
        if not installed:
            self.log_signal.emit("error", "未检测到 PyInstaller，请先在环境中安装 pyinstaller")
            self.log_signal.emit("error", "可点击「安装PyInstaller」按钮一键安装，或手动执行: pip install pyinstaller")
            self.finished_signal.emit(False, "")
            return
        self.log_signal.emit("info", f"PyInstaller 版本: {version}")

        try:
            # 启动子进程，实时流式读取
            self._process = subprocess.Popen(
                cmd,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True,
            )
        except FileNotFoundError:
            self.log_signal.emit("error", "无法启动Python解释器，请检查虚拟环境路径配置")
            self.finished_signal.emit(False, "")
            return
        except OSError as e:
            self.log_signal.emit("error", f"启动打包进程失败：{str(e)}")
            self.finished_signal.emit(False, "")
            return

        # 流式读取输出
        success = True
        try:
            for line in self._process.stdout:
                if self._cancelled:
                    break
                line = line.rstrip("\n\r")
                if not line:
                    continue
                level = self._classify_line(line)
                self.log_signal.emit(level, line)
                # 检测关键错误
                if level == "error":
                    success = False
        except Exception as e:
            self.log_signal.emit("error", f"读取日志异常：{str(e)}")
            success = False

        # 等待进程结束
        try:
            return_code = self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            return_code = -1

        if self._cancelled:
            self.log_signal.emit("warning", "打包已被用户取消")
            self.finished_signal.emit(False, "")
            return

        # 最终判定
        if return_code == 0 and success:
            dist_path = os.path.join(output_dir, "dist") if output_dir else "dist"
            self.log_signal.emit("success", "=" * 60)
            self.log_signal.emit("success", "打包成功！EXE已生成")
            self.log_signal.emit("success", f"输出路径: {os.path.abspath(dist_path)}")
            self.log_signal.emit("success", "=" * 60)
            self.finished_signal.emit(True, os.path.abspath(dist_path))
        else:
            self.log_signal.emit("error", "=" * 60)
            self.log_signal.emit("error", f"打包失败，退出码: {return_code}")
            self.log_signal.emit("error", "请查看上方错误日志，常见原因：依赖缺失、路径含特殊字符、虚拟环境配置错误")
            self.log_signal.emit("error", "=" * 60)
            self.finished_signal.emit(False, "")

    @staticmethod
    def _classify_line(line):
        """根据行内容分类日志级别"""
        lower = line.lower()
        # 成功关键词
        if "building completed successfully" in lower or "completed successfully" in lower:
            return "success"
        # 错误关键词
        error_keywords = ["error:", "fatal:", "traceback", "exception", "failed",
                          "no module named", "permission denied", "cannot find",
                          "importerror", "modulenotfounderror", "oserror"]
        for kw in error_keywords:
            if kw in lower:
                return "error"
        # 警告关键词
        warning_keywords = ["warning:", "warn:", "could not", "not found",
                            "skipping", "deprecated", "missing"]
        for kw in warning_keywords:
            if kw in lower:
                return "warning"
        return "info"

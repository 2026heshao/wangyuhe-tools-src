"""CacheSweep 外置软件缓存规则加载器（纯数据解析，无任何 UI 代码）。

对外暴露两个函数：
- load_rules()      读取内置规则 + 用户规则，彻底过滤 forbidden，返回规则定义列表
- scan_by_rules()   依据规则扫描磁盘，返回结构化扫描结果列表

设计约束：
1. 只扫描规则给出的目录前缀，绝不递归扫描盘符根目录或系统目录
2. Windows 路径大小写不敏感
3. 任何单条规则 / 单个文件异常只跳过，绝不使程序崩溃
4. risk_level == "forbidden" 的条目在进入任何扫描前就被丢弃，不对外返回

用法示例：
    from rule_loader import load_rules, scan_by_rules
    rules = load_rules()
    results = scan_by_rules(rules)   # 建议在主程序的工作线程中调用
"""

from __future__ import annotations

import fnmatch
import glob
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

__all__ = ["load_rules", "scan_by_rules", "SUPPORTED_ENV_VARS"]

# 允许在 glob_patterns / exclude_patterns 中出现的环境变量（%VAR% 形式，大小写不敏感）
SUPPORTED_ENV_VARS = (
    "LOCALAPPDATA",
    "APPDATA",
    "USERPROFILE",
    "TEMP",
    "TMP",
    "ProgramData",
    "SystemDrive",
)

_VALID_RISK_LEVELS = {"safe", "caution", "forbidden"}

_BASE_DIR = Path(__file__).resolve().parent
# 内置规则库：打包后由 datas 放进 _internal（与本模块同级），源码运行时位于项目根
_BUILTIN_RULES_PATH = _BASE_DIR / "software_cache_rules.json"

_ENV_RE = re.compile(r"%([^%]+)%")


def _user_rules_path() -> Path:
    """可选外置叠加层 user_rules.json 的位置。

    打包后放在可执行文件（CacheClear.exe）同级，便于用户自行放置/编辑；
    源码运行（如 Start_Cache_Manager.cmd）时回退到本模块同级（项目根）。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "user_rules.json"
    return _BASE_DIR / "user_rules.json"


def _normcase(path: str) -> str:
    """Windows 上把路径规范化到小写，保证大小写不敏感；其它平台原样返回。"""
    return os.path.normcase(path)


def _lookup_env(name: str) -> Optional[str]:
    """按大小写不敏感方式查找环境变量；不存在返回 None。"""
    upper = name.upper()
    for key, value in os.environ.items():
        if key.upper() == upper:
            return value
    return None


def _expand_env(pattern: str) -> Optional[str]:
    """展开 %VAR% 形式的环境变量；任一变量缺失返回 None（调用方跳过该条）。"""
    result: List[str] = []
    last = 0
    for match in _ENV_RE.finditer(pattern):
        result.append(pattern[last:match.start()])
        value = _lookup_env(match.group(1))
        if value is None:
            return None
        result.append(value)
        last = match.end()
    result.append(pattern[last:])
    return "".join(result)


def _read_rules(path: Path) -> List[Dict[str, Any]]:
    """读取一个规则 JSON；损坏、缺失、非 UTF-8 都返回空列表，绝不抛异常。"""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return []
    rules = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(rules, list):
        return []
    return [rule for rule in rules if isinstance(rule, dict)]


def _normalize_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    """把规则补齐为统一字段结构，非法枚举值在调用方过滤。"""
    return {
        "app_name": rule.get("app_name", ""),
        "app_alias": list(rule.get("app_alias") or []),
        "category": rule.get("category", ""),
        "glob_patterns": list(rule.get("glob_patterns") or []),
        "exclude_patterns": list(rule.get("exclude_patterns") or []),
        "risk_level": str(rule.get("risk_level", "")).lower(),
        "default_check": bool(rule.get("default_check", False)),
        "confidence": str(rule.get("confidence", "")).lower(),
        "note": rule.get("note", ""),
    }


def load_rules() -> List[Dict[str, Any]]:
    """读取内置规则 + 用户规则（user_rules.json），过滤 forbidden 与非法条目。

    返回的每条规则包含：
    app_name / app_alias / category / glob_patterns / exclude_patterns /
    risk_level / default_check / confidence / note
    """
    raw = _read_rules(_BUILTIN_RULES_PATH) + _read_rules(_user_rules_path())
    rules: List[Dict[str, Any]] = []
    for rule in raw:
        risk = str(rule.get("risk_level", "")).lower()
        # forbidden 一律不对外返回；非合法枚举值同样跳过
        if risk == "forbidden" or risk not in _VALID_RISK_LEVELS:
            continue
        if not rule.get("glob_patterns"):
            continue
        rules.append(_normalize_rule(rule))
    return rules


def _dangerous_prefix(pattern: str) -> bool:
    """判断规则是否指向盘符根目录或 Windows 系统目录，禁止这类扫描前缀。"""
    wildcard_pos = []
    for ch in ("*", "?", "["):
        pos = pattern.find(ch)
        if pos != -1:
            wildcard_pos.append(pos)
    cut = min(wildcard_pos) if wildcard_pos else len(pattern)
    prefix = pattern[:cut].rstrip("\\/")
    if not prefix:
        return True
    normalized = _normcase(os.path.normpath(prefix))
    # 盘符根目录，如 C:\ 或 C:
    if len(normalized) <= 3 and normalized.endswith(":"):
        return True
    if len(normalized) == 2 and normalized[1] == ":":
        return True
    # 系统 Windows 目录
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if system_root and _normcase(os.path.normpath(system_root)) == normalized:
        return True
    return False


def _safe_glob(pattern: str) -> List[str]:
    """展开后的 glob 匹配，带危险前缀防御；异常一律返回空列表。"""
    if _dangerous_prefix(pattern):
        return []
    try:
        # glob.glob 在 Windows 上经由 fnmatch.normcase 已大小写不敏感
        return glob.glob(pattern, recursive=False)
    except Exception:
        return []


def _is_excluded(path: str, exclude_patterns: Iterable[str]) -> bool:
    """判断真实路径是否命中任一 exclude 模式（全路径 glob 匹配，大小写不敏感）。"""
    normalized_path = _normcase(os.path.normpath(path))
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(normalized_path, _normcase(pattern)):
            return True
    return False


def _measure(root: str) -> Tuple[int, int]:
    """统计目录下的文件数与总字节数（不跟随符号链接/目录联接，跳过锁定文件）。"""
    file_count = 0
    size_bytes = 0
    stack: List[str] = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            file_count += 1
                            try:
                                size_bytes += entry.stat(follow_symlinks=False).st_size
                            except OSError:
                                pass
                    except OSError:
                        # 单个条目被占用 / 无权限：跳过该条目继续
                        continue
        except OSError:
            # 目录整体不可访问：跳过该目录继续
            continue
    return file_count, size_bytes


def _scan_rule(rule: Dict[str, Any], results: List[Dict[str, Any]], seen: set) -> None:
    """扫描单条规则；任何异常都在外层被捕获，保证单条失败不影响整体。"""
    app_name = rule.get("app_name", "")
    category = rule.get("category", "")
    risk_level = rule.get("risk_level", "")
    default_check = bool(rule.get("default_check", False))
    note = rule.get("note", "")

    exclude_compiled: List[str] = []
    for exclude in rule.get("exclude_patterns") or []:
        expanded = _expand_env(exclude)
        if expanded is not None:
            exclude_compiled.append(expanded)

    for pattern in rule.get("glob_patterns") or []:
        expanded = _expand_env(pattern)
        if expanded is None:
            continue
        for real_path in _safe_glob(expanded):
            if _is_excluded(real_path, exclude_compiled):
                continue
            if not os.path.isdir(real_path):
                continue
            key = _normcase(os.path.normpath(real_path))
            if key in seen:
                continue
            seen.add(key)
            file_count, size_bytes = _measure(real_path)
            results.append({
                "app_name": app_name,
                "category": category,
                "real_path": real_path,
                "file_count": file_count,
                "size_bytes": size_bytes,
                "risk_level": risk_level,
                "note": note,
                "default_check": default_check,
            })


def scan_by_rules(rules: Optional[Iterable[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """依据规则扫描磁盘，返回结构化结果列表。

    参数 rules 缺省时内部调用 load_rules()。返回每项包含：
    app_name / category / real_path / file_count / size_bytes /
    risk_level / note / default_check

    注意：本函数可能对 pip/npm/Temp 等大目录做遍历统计，建议在主程序的工作线程中调用。
    """
    if rules is None:
        rules = load_rules()
    results: List[Dict[str, Any]] = []
    seen: set = set()
    for rule in rules:
        try:
            _scan_rule(rule, results, seen)
        except Exception:
            # 单条规则失败仅跳过该条，绝不崩溃
            continue
    return results

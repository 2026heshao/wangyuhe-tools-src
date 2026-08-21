"""CacheSweep 纯启发式扫描模块。

特性与约束：
- 不读取任何 json/csv 配置，不产生任何磁盘持久化文件，不写用户模板。
- 按文件夹名关键词发现"疑似缓存"，只匹配文件夹、忽略普通文件。
- 不做安全判定：risk_level 固定 unknown（准确分级交给上层深度判定），默认不勾选。
- 所有数据只在内存中返回给上层。

扫描范围（多根）：
1. %LOCALAPPDATA%：整体遍历；
2. %APPDATA%(Roaming)：整体遍历；
3. 用户主目录 (%USERPROFILE%) 下所有"点目录"（以 . 开头，如 ~/.cache、~/.npm、~/.cargo、~/.config 等）：
   - 若点目录名本身命中关键词（如 .cache），则整个目录作为一项缓存返回，不再下潜；
   - 否则仅在其内部继续按关键词发现疑似缓存；
   - 绝不进入桌面/文档/下载等个人目录，避免误扫个人文件与过度耗时。

对外函数：scan_heuristic() -> list[dict]
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["scan_heuristic"]

# 命中关键词（文件夹名，大小写不敏感，包含子串即命中）
KEYWORDS = (
    "cache", "cache2", "gpucache", "shadercache",
    "blob_storage", "__pycache__",
    "tmp", "temp", "logs",
)

# 子串误伤排除：目录名（casefold 后）虽命中关键词，但实为别的东西，跳过
EXCLUDED_NAMES = {
    "templates", "template", "temperature", "temporarily", "tempo",
    "catalogs", "blogs", "backlogs", "analogs", "dialogues",
}

# app_name 回溯时要跳过的"通用词"目录名
GENERIC_NAMES = {
    "cache", "cache2", "gpucache", "shadercache", "blob_storage", "__pycache__",
    "tmp", "temp", "logs", "log",
    "data", "default", "user data", "profile", "profiles", "cache_data",
    "cacheddata", "code cache", "gpu cache", "shader cache", "storage",
    "files", "file", "content", "contents",
}


def _match_keyword(name: str) -> Optional[str]:
    """判断目录名是否命中关键词；返回命中的关键词，未命中返回 None。"""
    folded = name.casefold()
    if folded in EXCLUDED_NAMES:
        return None
    for keyword in KEYWORDS:
        if keyword in folded:
            return keyword
    return None


def _extract_app(parts: Tuple[str, ...]) -> str:
    """从相对扫描根的路径段里回溯取软件名。

    parts[-1] 是命中目录本身；从其父级向上跳过通用词，取最近的有意义目录名。
    顶层命中（无父级）时回退用命中目录自身名。
    """
    for part in reversed(parts[:-1]):
        if part.casefold() not in GENERIC_NAMES:
            return part
    return parts[0] if parts else ""


def _measure(folder: Path) -> Tuple[int, int]:
    """统计目录下的文件数与总字节数；不跟随符号链接/联接，逐项跳过异常。"""
    count = 0
    size = 0
    stack: List[Path] = [folder]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            count += 1
                            try:
                                size += entry.stat(follow_symlinks=False).st_size
                            except OSError:
                                pass
                    except OSError:
                        continue
        except OSError:
            continue
    return count, size


def _scan_roots() -> List[Tuple[Path, str]]:
    """返回待扫描的根列表：(路径, 类型)。

    类型取值：localappdata / roaming / home_dot。
    """
    roots: List[Tuple[Path, str]] = []

    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append((Path(local), "localappdata"))

    roaming = os.environ.get("APPDATA")
    if roaming:
        roots.append((Path(roaming), "roaming"))

    home = os.environ.get("USERPROFILE")
    if home:
        home_path = Path(home)
        try:
            entries = list(home_path.iterdir())
        except OSError:
            entries = []
        for entry in entries:
            try:
                if (
                    entry.name.startswith(".")
                    and entry.is_dir()
                    and not entry.is_symlink()
                ):
                    roots.append((entry, "home_dot"))
            except OSError:
                continue
    return roots


def _walk(root: Path, kind: str) -> List[Tuple[Path, str]]:
    """在单个根下按关键词发现疑似缓存目录。

    home_dot 类型特殊：若点目录名本身命中关键词（如 .cache），
    整个目录即视为一项缓存（并不再下潜），避免对一个大缓存根做无用下沉。
    返回 [(绝对路径, app_name)]。
    """
    matched: List[Tuple[Path, str]] = []

    if kind == "home_dot":
        hit = _match_keyword(root.name)
        if hit is not None:
            app = root.name[1:] if root.name.startswith(".") else root.name
            return [(root, app)]

    try:
        for base, dirs, _files in os.walk(root, topdown=True, followlinks=False):
            keep: List[str] = []
            for name in dirs:
                full = Path(base) / name
                try:
                    if full.is_symlink():
                        continue
                except OSError:
                    continue
                if _match_keyword(name):
                    try:
                        parts = full.relative_to(root).parts
                    except ValueError:
                        parts = full.parts
                    matched.append((full, _extract_app(parts)))
                    # 命中目录不再向下寻找匹配，剪枝
                    continue
                keep.append(name)
            dirs[:] = keep
    except OSError:
        pass
    return matched


def scan_heuristic() -> List[Dict[str, Any]]:
    """遍历本地应用数据 + Roaming + 用户主目录点缓存，返回疑似缓存目录列表。

    返回每项结构：
    {
        "app_name": 自动提取的软件文件夹名,
        "real_path": 绝对路径,
        "file_count": 文件数,
        "size_bytes": 占用字节数,
        "risk_level": "unknown",
        "source": "heuristic_scan",
        "is_from_roaming": 是否来自 Roaming,
        "root": 来源根类型 localappdata/roaming/home_dot,
        "note": "启发式探测，未验证，请人工确认是否为可清理缓存",
    }
    """
    results: List[Dict[str, Any]] = []
    for root, kind in _scan_roots():
        try:
            if not root.is_dir():
                continue
        except OSError:
            continue
        for folder, app_name in _walk(root, kind):
            count, size = _measure(folder)
            results.append({
                "app_name": app_name,
                "real_path": str(folder),
                "file_count": count,
                "size_bytes": size,
                "risk_level": "unknown",
                "source": "heuristic_scan",
                "is_from_roaming": kind == "roaming",
                "root": kind,
                "note": "启发式探测，未验证，请人工确认是否为可清理缓存",
            })
    return results
"""CacheSweep 全局缓存安全判定模块（所有扫描方式共用）。

对每条扫描结果统一做“深度确认”：
1) 路径黑名单：绝对路径任一段命中敏感词 → 风险。
2) 深度内容探测：递归查看候选目录内部（每目录最多 max_files 个文件），
   按文件类型给出四档结论：
   - risky   含配置/敏感文件
   - caution 含用户数据（图片/视频/文档等）
   - safe    仅缓存类文件或空目录
   - unknown 无法确认（访问失败 / 内容混杂 / 目录过大未扫完）

本模块只做判定，不删除、不写盘，数据仅在内存传递。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

__all__ = ["judge_directory", "deep_judge_directory"]

MAX_FILES = 50000

# 路径段黑名单（casefold 后命中即风险）
PATH_KEYWORDS = {
    "credential", "credentials", "password", "passwords", "token", "tokens",
    ".ssh", ".gnupg", "msg", "msgattach", "nt_qq",
    "wechat files", "xwechat_files", "tencent files",
}

# 敏感文件名（文件/目录名，casefold 后匹配）
SENSITIVE_NAMES = {
    "login data", "cookies", "history", "bookmarks", "web data", "local state",
    "settings.json", "keybindings.json", "preferences", "credentials", "passwords",
    "token", "tokens", "id_rsa", "id_ed25519", "secrets", ".env", "config.json",
}

# 敏感子目录名（出现在候选目录任意层级即风险）
SENSITIVE_DIR_NAMES = {
    "config", "configuration", "settings", "credentials", "passwords",
    ".ssh", ".gnupg",
}

# 敏感扩展名（配置/凭据类）
SENSITIVE_SUFFIXES = {
    ".db", ".sqlite", ".sqlite3", ".ini", ".cfg", ".conf", ".yaml", ".yml",
    ".pem", ".key", ".p12", ".pfx", ".reg", ".rdp",
}

# 用户数据扩展名（图片/音视频/文档/归档/安装包）
USERDATA_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".svg",
    ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".mp3", ".wav", ".flac",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pdf", ".txt", ".md", ".csv", ".rtf",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".apk", ".exe", ".msi",
}

# 缓存类扩展名（可再生的临时/缓存数据；含网页/元数据类缓存常见类型）
CACHE_SUFFIXES = {
    ".tmp", ".temp", ".log", ".cache", ".bin", ".toc", ".ldb", ".lock",
    ".blob", ".pack", ".idx", ".old", ".bak", ".chk", ".part", ".crdownload",
    ".download", ".opdownload",
    ".dat", ".js", ".json", ".html", ".htm", ".css", ".xml", ".map",
}

# 缓存类文件名提示（无扩展名的缓存文件常见名/前缀）
CACHE_NAME_EXACT = {"index", "manifest", "current", "lock", "journal", "meta"}
CACHE_NAME_PREFIXES = ("data_", "f_", "file_")


def _is_symlink(path: Path) -> bool:
    try:
        return path.is_symlink()
    except OSError:
        return True


def _path_risk(path: str) -> List[str]:
    reasons: List[str] = []
    try:
        parts = [p.casefold() for p in Path(path).parts]
    except Exception:
        parts = [str(path).casefold()]
    for keyword in PATH_KEYWORDS:
        if keyword in parts:
            reasons.append(f"路径含敏感片段“{keyword}”")
    return reasons


def _content_risk(path: str) -> List[str]:
    """一层内容探测（供 judge_directory 快速使用）。"""
    reasons: List[str] = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                folded = entry.name.casefold()
                if folded in SENSITIVE_NAMES or folded in SENSITIVE_DIR_NAMES:
                    reasons.append(f"包含敏感文件/目录“{entry.name}”")
                elif entry.is_file(follow_symlinks=False):
                    if Path(entry.name).suffix.casefold() in SENSITIVE_SUFFIXES:
                        reasons.append(f"包含敏感类型文件“{entry.name}”")
    except OSError:
        pass
    return reasons


def judge_directory(path) -> Dict[str, Any]:
    """快速一层判定，返回 {'risky': bool, 'reasons': [str]}。"""
    reasons = _path_risk(str(path)) + _content_risk(str(path))
    seen = set()
    uniq: List[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            uniq.append(reason)
    return {"risky": bool(uniq), "reasons": uniq}


def _cache_name_hint(folded_name: str) -> bool:
    if folded_name in CACHE_NAME_EXACT:
        return True
    return folded_name.startswith(CACHE_NAME_PREFIXES)


def deep_judge_directory(path, max_files: int = MAX_FILES) -> Dict[str, Any]:
    """深度确认：递归查看目录内容，返回四档结论。

    返回 {"verdict": "safe|caution|risky|unknown", "reasons": [str], "truncated": bool}。
    """
    path_reasons = _path_risk(str(path))
    if path_reasons:
        return {"verdict": "risky", "reasons": path_reasons, "truncated": False}

    config_hits: List[str] = []
    userdata_hits: List[str] = []
    cache_signal = 0
    seen = 0
    truncated = False

    try:
        for root, dirs, files in os.walk(path, topdown=True, followlinks=False):
            dirs[:] = [d for d in dirs if not _is_symlink(Path(root) / d)]
            for d in dirs:
                if d.casefold() in SENSITIVE_DIR_NAMES:
                    config_hits.append(d + "/")
            for name in files:
                folded = name.casefold()
                suffix = os.path.splitext(name)[1].casefold()
                if folded in SENSITIVE_NAMES or suffix in SENSITIVE_SUFFIXES:
                    config_hits.append(name)
                elif suffix in USERDATA_SUFFIXES:
                    userdata_hits.append(name)
                elif suffix in CACHE_SUFFIXES or _cache_name_hint(folded) or not suffix:
                    # 命中缓存扩展名 / 缓存常见名 / 无扩展名（浏览器缓存多为无扩展名数据块）
                    cache_signal += 1
                seen += 1
                if seen >= max_files:
                    truncated = True
                    break
            if truncated:
                break
    except OSError:
        pass

    if config_hits:
        return {
            "verdict": "risky",
            "reasons": [f"包含配置/敏感项：{', '.join(config_hits[:5])}"],
            "truncated": truncated,
        }
    if userdata_hits:
        return {
            "verdict": "caution",
            "reasons": [f"包含用户数据文件：{', '.join(userdata_hits[:5])}"],
            "truncated": truncated,
        }
    if truncated:
        if cache_signal > 0:
            return {
                "verdict": "safe",
                "reasons": [f"目录较大，抽样确认（抽查前 {max_files} 个文件均为缓存类）"],
                "truncated": True,
            }
        return {
            "verdict": "unknown",
            "reasons": [f"目录过大，仅抽查前 {max_files} 个文件，未能完全确认"],
            "truncated": True,
        }
    if cache_signal > 0 or seen == 0:
        return {"verdict": "safe", "reasons": [], "truncated": False}
    return {"verdict": "unknown", "reasons": ["内容无法识别，未确认是否为缓存"], "truncated": False}

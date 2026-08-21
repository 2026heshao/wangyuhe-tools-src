# -*- coding: utf-8 -*-
"""
====================================================================
共享常量定义  -  constants
====================================================================
集中定义跨模块复用的业务/UI 常量，消除散落在各文件中的魔法数字
与魔法字符串，便于统一维护与一致性校验。

仅收纳「确实被多个模块共用」或「语义明确、易误改」的常量；
单一模块内独有的尺寸常量仍保留在各自模块（如 MainWindow 的
窗口尺寸、CardWindow 的标签栏宽度等），避免过度集中。
"""

# ---- 笔记自动保存防抖间隔（毫秒）----
# card_window（小卡片笔记）与 notes_panel（大窗口笔记）共用同一语义：
# 文本停止编辑后延迟该时长再落盘，合并连续输入、降低写盘频率。
NOTE_AUTOSAVE_INTERVAL_MS = 800

# ---- 时间字符串切片常量 ----
# 时间戳统一格式为 "YYYY-MM-DD HH:MM"（见各 manager 的 strftime），
# 以下切片位置用于从完整时间戳中拆分日期与时分，避免散落的魔法下标。
DATETIME_DATE_LEN = 10        # "YYYY-MM-DD" 长度
DATETIME_TIME_START = 11       # 时分起始下标（跳过 " "）
DATETIME_TIME_LEN = 5          # "HH:MM" 长度
DATETIME_MIN_LEN = 16          # 完整日期+时分的最小长度

# ---- 碎片列表预览长度 ----
# 碎片/段落预览截断长度，多处 UI 复用，统一在此定义。
FRAGMENT_PREVIEW_LEN = 60
PARAGRAPH_PREVIEW_LEN = 80
NOTE_PREVIEW_LEN = 80

# ---- 文件名非法字符净化 ----
# Windows 不允许出现在文件名中的字符（含保留设备名前缀风险由调用方规避）。
# 集中定义便于各落盘点（拖拽落盘、素材复制）复用同一套净化规则。
_ILLEGAL_FILENAME_CHARS = ["\\", "/", ":", "*", "?", "\"", "<", ">", "|"]


def sanitize_filename(name: str, replacement: str = "_") -> str:
    """将文件名中的 Windows 非法字符替换为安全字符。

    仅替换会导致落盘失败/语义异常的字符，不改动合法内容。
    空字符串或净化后为空时回退为 "file"。
    """
    if not name:
        return "file"
    cleaned = name
    for ch in _ILLEGAL_FILENAME_CHARS:
        cleaned = cleaned.replace(ch, replacement)
    cleaned = cleaned.strip()
    return cleaned or "file"

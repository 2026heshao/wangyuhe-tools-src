# -*- coding: utf-8 -*-
"""
模板管理模块
内置两套官方固定模板 + 用户自定义模板
官方模板禁止删除，仅用户自定义模板可删除
"""

import copy
from config import load_templates, save_templates


# ========== 内置官方模板（不可删除） ==========
BUILTIN_TEMPLATES = {
    "普通Python脚本模板": {
        "builtin": True,
        "config": {
            "output_mode": "folder",
            "console_mode": "console",
            "icon_path": "",
            "collect_enabled": False,
            "collect_imports": "",
            "exclude_enabled": False,
            "exclude_imports": "",
            "exe_name": "",
            "debug_log": False,
        }
    },
    "PyQt6-WebEngine模板": {
        "builtin": True,
        "config": {
            "output_mode": "folder",
            "console_mode": "gui",
            "icon_path": "",
            "collect_enabled": True,
            "collect_imports": "PyQt6.QtWebEngine\nPyQt6.QtWebEngineCore\nPyQt6.QtWebEngineWidgets",
            "exclude_enabled": False,
            "exclude_imports": "",
            "exe_name": "",
            "debug_log": False,
        }
    },
}


def get_all_templates():
    """获取所有模板（内置 + 用户自定义），返回有序字典"""
    user_templates = load_templates()
    all_tpl = {}
    # 内置模板在前
    for name, data in BUILTIN_TEMPLATES.items():
        all_tpl[name] = data
    # 用户自定义模板在后
    for name, data in user_templates.items():
        if name not in all_tpl:  # 避免重名覆盖内置
            all_tpl[name] = data
    return all_tpl


def get_template_names():
    """获取所有模板名称列表"""
    return list(get_all_templates().keys())


def is_builtin(name):
    """判断是否为内置官方模板"""
    return name in BUILTIN_TEMPLATES


def get_template_config(name):
    """获取指定模板的配置（返回副本）"""
    all_tpl = get_all_templates()
    if name in all_tpl:
        return copy.deepcopy(all_tpl[name]["config"])
    return None


def save_user_template(name, config):
    """
    保存用户自定义模板
    name: 模板名称
    config: 要保存的配置字典（仅打包参数部分）
    返回: (success: bool, msg: str)
    """
    if not name or not name.strip():
        return False, "模板名称不能为空"
    name = name.strip()
    if name in BUILTIN_TEMPLATES:
        return False, "不能覆盖内置官方模板"

    user_templates = load_templates()
    # 仅保存打包相关参数，不保存路径类配置
    save_data = {
        "builtin": False,
        "config": {
            "output_mode": config.get("output_mode", "folder"),
            "console_mode": config.get("console_mode", "console"),
            "icon_path": config.get("icon_path", ""),
            "collect_enabled": config.get("collect_enabled", False),
            "collect_imports": config.get("collect_imports", ""),
            "exclude_enabled": config.get("exclude_enabled", False),
            "exclude_imports": config.get("exclude_imports", ""),
            "exe_name": config.get("exe_name", ""),
            "debug_log": config.get("debug_log", False),
        }
    }
    user_templates[name] = save_data
    ok = save_templates(user_templates)
    if ok:
        return True, f"模板「{name}」保存成功"
    return False, "模板保存失败，请检查目录写入权限"


def delete_user_template(name):
    """
    删除用户自定义模板
    返回: (success: bool, msg: str)
    """
    if name in BUILTIN_TEMPLATES:
        return False, "内置官方模板禁止删除"
    user_templates = load_templates()
    if name not in user_templates:
        return False, f"模板「{name}」不存在"
    del user_templates[name]
    ok = save_templates(user_templates)
    if ok:
        return True, f"模板「{name}」已删除"
    return False, "模板删除失败"

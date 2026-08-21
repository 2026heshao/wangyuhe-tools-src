# -*- coding: utf-8 -*-
"""
配置持久化模块
负责所有表单参数、路径、选项的本地JSON保存与加载
软件重启自动恢复上次配置
"""

import os
import json
import copy

# 配置文件存放路径（与程序同目录）
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "pypacker_config.json")
TEMPLATE_FILE = os.path.join(APP_DIR, "pypacker_templates.json")


# 默认配置（首次启动时使用）
DEFAULT_CONFIG = {
    "main_py": "",
    "project_root": "",
    "requirements": "",
    "venv_path": "",
    "output_mode": "folder",       # "onefile" | "folder"
    "console_mode": "console",     # "gui" | "console"
    "icon_path": "",
    "collect_enabled": False,      # 附加依赖收集开关
    "collect_imports": "",         # 多行文本
    "exclude_enabled": False,      # 排除打包库开关
    "exclude_imports": "",         # 多行文本
    "exe_name": "",                # 自定义输出程序名称
    "output_dir": "",
    "debug_log": False,
    "last_template": ""
}


def load_config():
    """加载本地配置，不存在则返回默认配置"""
    if not os.path.exists(CONFIG_FILE):
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 合并默认值，防止新增字段缺失
        merged = copy.deepcopy(DEFAULT_CONFIG)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, IOError):
        return copy.deepcopy(DEFAULT_CONFIG)


def save_config(config):
    """保存配置到本地JSON"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False


def load_templates():
    """加载用户自定义模板列表"""
    if not os.path.exists(TEMPLATE_FILE):
        return {}
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_templates(templates):
    """保存用户自定义模板"""
    try:
        with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False


def get_app_dir():
    """返回程序所在目录"""
    return APP_DIR

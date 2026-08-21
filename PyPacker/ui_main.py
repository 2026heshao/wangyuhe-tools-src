# -*- coding: utf-8 -*-
"""
PyPacker 主窗口UI
深色极简开发工具风，固定尺寸 960x720
布局：顶部模板栏 → 左右双配置面板 → 日志区 → 底部按钮栏
"""

import os
import sys

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox,
    QRadioButton, QButtonGroup, QCheckBox, QTextEdit, QFileDialog,
    QMessageBox, QFrame, QSizePolicy, QApplication, QInputDialog,
    QPlainTextEdit, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QIcon

import config as cfg
import templates as tpl
from packager import (
    PackagerThread, build_command_str, validate_config,
    check_pyinstaller, install_pyinstaller,
)


# ========== 全局配色常量 ==========
COLOR_BG_WINDOW = "#242629"
COLOR_BG_PANEL = "#2d2f33"
COLOR_BTN_PRIMARY = "#3680e8"
COLOR_BTN_PRIMARY_HOVER = "#4a90f0"
COLOR_SUCCESS = "#47d165"
COLOR_WARNING = "#ffaa33"
COLOR_ERROR = "#ff5c5c"
COLOR_TEXT = "#e8e8e8"
COLOR_TEXT_DIM = "#9a9a9a"
COLOR_BORDER = "#3a3d42"
COLOR_INPUT_BG = "#1e1f22"


# ========== 全局QSS样式 ==========
GLOBAL_QSS = f"""
QMainWindow, QWidget {{
    background-color: {COLOR_BG_WINDOW};
    color: {COLOR_TEXT};
    font-family: "Segoe UI", "Consolas", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}}

QGroupBox {{
    background-color: {COLOR_BG_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: bold;
    color: {COLOR_TEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {COLOR_TEXT};
}}

QLabel {{
    background-color: transparent;
    color: {COLOR_TEXT};
}}

QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {COLOR_INPUT_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    color: {COLOR_TEXT};
    selection-background-color: {COLOR_BTN_PRIMARY};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {COLOR_BTN_PRIMARY};
}}
QLineEdit[error="true"] {{
    border: 1px solid {COLOR_ERROR};
}}

QComboBox {{
    background-color: {COLOR_INPUT_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    color: {COLOR_TEXT};
    min-width: 160px;
}}
QComboBox:hover {{
    border: 1px solid {COLOR_BTN_PRIMARY};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {COLOR_TEXT_DIM};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLOR_INPUT_BG};
    border: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT};
    selection-background-color: {COLOR_BTN_PRIMARY};
    outline: none;
}}

QPushButton {{
    background-color: {COLOR_BG_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 6px 16px;
    color: {COLOR_TEXT};
    font-weight: normal;
}}
QPushButton:hover {{
    background-color: #36383d;
    border: 1px solid #4a4d52;
}}
QPushButton:pressed {{
    background-color: #26282b;
}}
QPushButton:disabled {{
    background-color: #2a2c2f;
    color: #5a5c5f;
    border: 1px solid #333538;
}}

QPushButton#btnPrimary {{
    background-color: {COLOR_BTN_PRIMARY};
    border: 1px solid {COLOR_BTN_PRIMARY};
    color: #ffffff;
    font-weight: bold;
    padding: 8px 24px;
}}
QPushButton#btnPrimary:hover {{
    background-color: {COLOR_BTN_PRIMARY_HOVER};
}}
QPushButton#btnPrimary:disabled {{
    background-color: #2a5a9e;
    border: 1px solid #2a5a9e;
    color: #8ab4e8;
}}

QPushButton#btnDanger {{
    color: {COLOR_ERROR};
}}
QPushButton#btnDanger:hover {{
    background-color: #3a2626;
    border: 1px solid {COLOR_ERROR};
}}

QRadioButton {{
    color: {COLOR_TEXT};
    spacing: 6px;
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {COLOR_BORDER};
    border-radius: 9px;
    background-color: {COLOR_INPUT_BG};
}}
QRadioButton::indicator:checked {{
    border: 2px solid {COLOR_BTN_PRIMARY};
    background-color: {COLOR_INPUT_BG};
}}
QRadioButton::indicator::indicator {{
    width: 8px;
    height: 8px;
    border-radius: 4px;
    background-color: {COLOR_BTN_PRIMARY};
}}
QRadioButton::indicator:checked {{
    background-color: {COLOR_INPUT_BG};
    border: 2px solid {COLOR_BTN_PRIMARY};
}}

QCheckBox {{
    color: {COLOR_TEXT};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
    background-color: {COLOR_INPUT_BG};
}}
QCheckBox::indicator:checked {{
    background-color: {COLOR_BTN_PRIMARY};
    border: 1px solid {COLOR_BTN_PRIMARY};
}}

QFrame#topBar, QFrame#bottomBar {{
    background-color: {COLOR_BG_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
}}

QScrollBar:vertical {{
    background-color: {COLOR_INPUT_BG};
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background-color: #4a4d52;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: #5a5d62;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background-color: {COLOR_INPUT_BG};
    height: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background-color: #4a4d52;
    border-radius: 5px;
    min-width: 30px;
}}
"""


class MainWindow(QMainWindow):
    """PyPacker 主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyPacker - Python一键EXE打包工具")
        self.resize(960, 720)
        self.setMinimumSize(900, 680)
        self.setStyleSheet(GLOBAL_QSS)

        # 状态变量
        self.packager_thread = None
        self.is_packaging = False
        self.last_output_dir = ""
        self._config_dirty = False

        # 自动保存定时器（防抖）
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)
        self._save_timer.timeout.connect(self._auto_save_config)

        # 构建UI
        self._build_ui()
        # 加载本地配置
        self._load_saved_config()
        # 刷新模板下拉
        self._refresh_template_combo()
        # 连接信号
        self._connect_signals()
        # 初始校验
        self._validate_main_py()

    # ==================== UI构建 ====================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ---- 顶部模板栏 ----
        main_layout.addWidget(self._build_top_bar())

        # ---- 中间配置区（左右双面板） ----
        mid_widget = QWidget()
        mid_layout = QHBoxLayout(mid_widget)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(8)
        mid_layout.addWidget(self._build_left_panel(), 1)
        mid_layout.addWidget(self._build_right_panel(), 1)
        main_layout.addWidget(mid_widget, 3)

        # ---- 日志区 ----
        main_layout.addWidget(self._build_log_panel(), 4)

        # ---- 底部按钮栏 ----
        main_layout.addWidget(self._build_bottom_bar())

    def _build_top_bar(self):
        """顶部模板栏"""
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(50)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        lbl = QLabel("模板：")
        lbl.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-weight: bold;")
        layout.addWidget(lbl)

        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(200)
        layout.addWidget(self.template_combo)

        self.btn_load_template = QPushButton("加载模板")
        layout.addWidget(self.btn_load_template)

        self.btn_save_template = QPushButton("保存为模板")
        layout.addWidget(self.btn_save_template)

        self.btn_delete_template = QPushButton("删除模板")
        self.btn_delete_template.setObjectName("btnDanger")
        layout.addWidget(self.btn_delete_template)

        layout.addStretch()

        # 环境状态指示
        self.env_label = QLabel("环境检测中...")
        self.env_label.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 12px;")
        layout.addWidget(self.env_label)

        return bar

    def _build_left_panel(self):
        """左上：项目源设置面板"""
        group = QGroupBox("项目源设置")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(10)

        # 1. 主入口PY文件
        layout.addWidget(QLabel("主入口PY文件："))
        row = QHBoxLayout()
        self.main_py_edit = QLineEdit()
        self.main_py_edit.setPlaceholderText("选择 .py 主入口文件...")
        row.addWidget(self.main_py_edit)
        self.btn_browse_main = QPushButton("浏览...")
        self.btn_browse_main.setFixedWidth(80)
        row.addWidget(self.btn_browse_main)
        layout.addLayout(row)

        # 2. 项目根目录
        layout.addWidget(QLabel("项目根目录："))
        row = QHBoxLayout()
        self.project_root_edit = QLineEdit()
        self.project_root_edit.setPlaceholderText("自动识别，可手动修改")
        row.addWidget(self.project_root_edit)
        self.btn_browse_root = QPushButton("浏览...")
        self.btn_browse_root.setFixedWidth(80)
        row.addWidget(self.btn_browse_root)
        layout.addLayout(row)

        # 3. requirements.txt
        layout.addWidget(QLabel("requirements.txt（可选）："))
        row = QHBoxLayout()
        self.req_edit = QLineEdit()
        self.req_edit.setPlaceholderText("选择依赖清单文件，辅助依赖校验")
        row.addWidget(self.req_edit)
        self.btn_browse_req = QPushButton("浏览...")
        self.btn_browse_req.setFixedWidth(80)
        row.addWidget(self.btn_browse_req)
        layout.addLayout(row)

        # 4. 虚拟环境路径
        layout.addWidget(QLabel("虚拟环境路径（可选）："))
        row = QHBoxLayout()
        self.venv_edit = QLineEdit()
        self.venv_edit.setPlaceholderText("选择venv目录，为空则使用系统Python")
        row.addWidget(self.venv_edit)
        self.btn_browse_venv = QPushButton("浏览...")
        self.btn_browse_venv.setFixedWidth(80)
        row.addWidget(self.btn_browse_venv)
        layout.addLayout(row)

        layout.addStretch()
        return group

    def _build_right_panel(self):
        """右上：PyInstaller打包参数面板（内嵌纵向滚动区）"""
        group = QGroupBox("PyInstaller打包参数")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(12, 18, 12, 12)
        outer.setSpacing(8)

        # 纵向滚动区：仅垂直滚动，禁用水平滚动；背景透明以承袭分组框面板色
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        scroll.viewport().setStyleSheet("background-color: transparent;")

        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. 打包输出模式（互斥单选）
        layout.addWidget(QLabel("打包输出模式："))
        row = QHBoxLayout()
        row.setSpacing(12)
        self.radio_onefile = QRadioButton("单文件模式 (-F)")
        self.radio_onefile.setAutoExclusive(False)
        self.radio_folder = QRadioButton("文件夹模式 (-D)")
        self.radio_folder.setAutoExclusive(False)
        self.radio_onefile.setChecked(True)  # 默认锁定单文件模式
        # 排他完全交给手动 clicked 互斥处理，关闭 Qt 组自带排他以免状态抢先回写干扰
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(False)
        self.mode_group.addButton(self.radio_onefile)
        self.mode_group.addButton(self.radio_folder)
        row.addWidget(self.radio_onefile)
        row.addWidget(self.radio_folder)
        row.addStretch()
        layout.addLayout(row)

        # 2. 控制台模式（互斥单选）
        layout.addWidget(QLabel("控制台模式："))
        row = QHBoxLayout()
        row.setSpacing(12)
        self.radio_gui = QRadioButton("GUI无控制台 (-w)")
        self.radio_gui.setAutoExclusive(False)
        self.radio_console = QRadioButton("保留控制台 (-c)")
        self.radio_console.setAutoExclusive(False)
        self.radio_gui.setChecked(True)  # 默认锁定GUI无控制台
        # 排他完全交给手动 clicked 互斥处理，关闭 Qt 组自带排他以免状态抢先回写干扰
        self.console_group = QButtonGroup(self)
        self.console_group.setExclusive(False)
        self.console_group.addButton(self.radio_gui)
        self.console_group.addButton(self.radio_console)
        row.addWidget(self.radio_gui)
        row.addWidget(self.radio_console)
        row.addStretch()
        layout.addLayout(row)

        # 3. 自定义ICO图标
        layout.addWidget(QLabel("自定义ICO图标（可选）："))
        row = QHBoxLayout()
        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText("仅支持 .ico 图标文件")
        row.addWidget(self.icon_edit)
        self.btn_browse_icon = QPushButton("浏览...")
        self.btn_browse_icon.setFixedWidth(80)
        row.addWidget(self.btn_browse_icon)
        layout.addLayout(row)

        # 4. 自定义输出程序名称（-n）
        layout.addWidget(QLabel("自定义输出程序名称（可选）："))
        self.exe_name_edit = QLineEdit()
        self.exe_name_edit.setPlaceholderText("留空则使用PyInstaller默认命名")
        layout.addWidget(self.exe_name_edit)

        # 5. 附加依赖收集（高级选项，复选框控制显隐）
        self.collect_check = QCheckBox("附加依赖收集（--collect-all）")
        layout.addWidget(self.collect_check)
        self.collect_edit = QPlainTextEdit()
        self.collect_edit.setFixedHeight(55)
        self.collect_edit.setPlaceholderText("每行一个库名，例如：PyQt6.QtWebEngine\n用于强制收集缺失的依赖库")
        self.collect_edit.setVisible(False)
        layout.addWidget(self.collect_edit)

        # 6. 排除打包库（高级选项，复选框控制显隐）
        self.exclude_check = QCheckBox("排除打包库（--exclude-module）")
        layout.addWidget(self.exclude_check)
        self.exclude_edit = QPlainTextEdit()
        self.exclude_edit.setFixedHeight(55)
        self.exclude_edit.setPlaceholderText("每行一个库名，例如：tkinter\n用于精简体积、排除冗余依赖")
        self.exclude_edit.setVisible(False)
        layout.addWidget(self.exclude_edit)

        # 7. EXE输出目录
        layout.addWidget(QLabel("EXE输出目录："))
        row = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("自定义打包文件输出路径")
        row.addWidget(self.output_dir_edit)
        self.btn_browse_output = QPushButton("浏览...")
        self.btn_browse_output.setFixedWidth(80)
        row.addWidget(self.btn_browse_output)
        layout.addLayout(row)

        # 8. 调试日志开关
        self.debug_check = QCheckBox("启用调试日志（输出完整PyInstaller底层日志）")
        layout.addWidget(self.debug_check)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return group

    def _build_log_panel(self):
        """下半区：实时打包日志窗口"""
        group = QGroupBox("打包日志")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(6)

        # 日志文本框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #1a1b1e;
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                color: {COLOR_TEXT};
            }}
        """)
        layout.addWidget(self.log_text)

        # 清空按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_clear_log = QPushButton("清空日志")
        self.btn_clear_log.setFixedWidth(100)
        btn_row.addWidget(self.btn_clear_log)
        layout.addLayout(btn_row)

        return group

    def _build_bottom_bar(self):
        """底部核心操作按钮栏"""
        bar = QFrame()
        bar.setObjectName("bottomBar")
        bar.setFixedHeight(56)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self.btn_start = QPushButton("开始打包")
        self.btn_start.setObjectName("btnPrimary")
        self.btn_start.setMinimumWidth(140)
        self.btn_start.setMinimumHeight(36)
        layout.addWidget(self.btn_start)

        self.btn_open_output = QPushButton("打开输出目录")
        self.btn_open_output.setEnabled(False)
        self.btn_open_output.setMinimumHeight(36)
        layout.addWidget(self.btn_open_output)

        self.btn_copy_cmd = QPushButton("复制完整PyInstaller命令")
        self.btn_copy_cmd.setMinimumHeight(36)
        layout.addWidget(self.btn_copy_cmd)

        layout.addStretch()

        self.btn_install_pyinstaller = QPushButton("安装PyInstaller")
        self.btn_install_pyinstaller.setMinimumHeight(36)
        layout.addWidget(self.btn_install_pyinstaller)

        return bar

    # ==================== 信号连接 ====================
    def _connect_signals(self):
        # 模板栏
        self.btn_load_template.clicked.connect(self._on_load_template)
        self.btn_save_template.clicked.connect(self._on_save_template)
        self.btn_delete_template.clicked.connect(self._on_delete_template)

        # 浏览按钮
        self.btn_browse_main.clicked.connect(self._browse_main_py)
        self.btn_browse_root.clicked.connect(self._browse_project_root)
        self.btn_browse_req.clicked.connect(self._browse_requirements)
        self.btn_browse_venv.clicked.connect(self._browse_venv)
        self.btn_browse_icon.clicked.connect(self._browse_icon)
        self.btn_browse_output.clicked.connect(self._browse_output_dir)

        # 输入变化 → 自动保存
        self.main_py_edit.textChanged.connect(self._on_config_changed)
        self.project_root_edit.textChanged.connect(self._on_config_changed)
        self.req_edit.textChanged.connect(self._on_config_changed)
        self.venv_edit.textChanged.connect(self._on_config_changed)
        self.icon_edit.textChanged.connect(self._on_config_changed)
        self.collect_edit.textChanged.connect(self._on_config_changed)
        self.exclude_edit.textChanged.connect(self._on_config_changed)
        self.output_dir_edit.textChanged.connect(self._on_config_changed)
        self.radio_onefile.toggled.connect(self._on_config_changed)
        self.radio_gui.toggled.connect(self._on_config_changed)
        # 输出/控制台模式互相排斥：点击某未选项即选中它并自动取消另一项（不允许空选）
        self.radio_onefile.clicked.connect(self._on_radio_mode_clicked)
        self.radio_folder.clicked.connect(self._on_radio_mode_clicked)
        self.radio_gui.clicked.connect(self._on_radio_console_clicked)
        self.radio_console.clicked.connect(self._on_radio_console_clicked)
        self.collect_check.toggled.connect(self._on_collect_toggled)
        self.exclude_check.toggled.connect(self._on_exclude_toggled)
        self.exe_name_edit.textChanged.connect(self._on_config_changed)
        self.debug_check.stateChanged.connect(self._on_config_changed)

        # 主文件变化 → 校验
        self.main_py_edit.textChanged.connect(self._validate_main_py)

        # 日志
        self.btn_clear_log.clicked.connect(self.log_text.clear)

        # 底部按钮
        self.btn_start.clicked.connect(self._on_start_packaging)
        self.btn_open_output.clicked.connect(self._on_open_output)
        self.btn_copy_cmd.clicked.connect(self._on_copy_command)
        self.btn_install_pyinstaller.clicked.connect(self._on_install_pyinstaller)

    # ==================== 配置读写 ====================
    def _collect_config(self):
        """从UI收集当前所有配置"""
        return {
            "main_py": self.main_py_edit.text().strip(),
            "project_root": self.project_root_edit.text().strip(),
            "requirements": self.req_edit.text().strip(),
            "venv_path": self.venv_edit.text().strip(),
            "output_mode": "onefile" if self.radio_onefile.isChecked() else "folder",
            "console_mode": "gui" if self.radio_gui.isChecked() else "console",
            "icon_path": self.icon_edit.text().strip(),
            "exe_name": self.exe_name_edit.text().strip(),
            "collect_enabled": self.collect_check.isChecked(),
            "collect_imports": self.collect_edit.toPlainText().strip(),
            "exclude_enabled": self.exclude_check.isChecked(),
            "exclude_imports": self.exclude_edit.toPlainText().strip(),
            "output_dir": self.output_dir_edit.text().strip(),
            "debug_log": self.debug_check.isChecked(),
        }

    def _apply_config(self, config):
        """将配置应用到UI控件"""
        self.main_py_edit.setText(config.get("main_py", ""))
        self.project_root_edit.setText(config.get("project_root", ""))
        self.req_edit.setText(config.get("requirements", ""))
        self.venv_edit.setText(config.get("venv_path", ""))

        # 每次打开默认锁定：单文件模式 + GUI无控制台（运行时仍可切换）
        self.radio_onefile.setChecked(True)
        self.radio_gui.setChecked(True)

        self.icon_edit.setText(config.get("icon_path", ""))
        self.exe_name_edit.setText(config.get("exe_name", ""))

        collect_on = config.get("collect_enabled", False)
        self.collect_check.setChecked(collect_on)
        self.collect_edit.setPlainText(config.get("collect_imports", ""))
        self.collect_edit.setVisible(collect_on)
        exclude_on = config.get("exclude_enabled", False)
        self.exclude_check.setChecked(exclude_on)
        self.exclude_edit.setPlainText(config.get("exclude_imports", ""))
        self.exclude_edit.setVisible(exclude_on)

        self.output_dir_edit.setText(config.get("output_dir", ""))
        self.debug_check.setChecked(config.get("debug_log", False))

    def _load_saved_config(self):
        """启动时加载本地保存的配置"""
        saved = cfg.load_config()
        self._apply_config(saved)
        self._log("info", "配置已从本地恢复")

    def _on_config_changed(self):
        """配置变化 → 防抖自动保存"""
        self._config_dirty = True
        self._save_timer.start()

    def _auto_save_config(self):
        """自动保存配置到本地JSON"""
        if not self._config_dirty:
            return
        config = self._collect_config()
        cfg.save_config(config)
        self._config_dirty = False

    # ==================== 高级选项显隐 ====================
    def _on_radio_mode_clicked(self, checked):
        """输出模式互斥：点击某项即选中它并取消另一项，不允许空选"""
        if self.sender() is self.radio_onefile:
            self.radio_onefile.setChecked(True)
            self.radio_folder.setChecked(False)
        else:
            self.radio_folder.setChecked(True)
            self.radio_onefile.setChecked(False)
        self._on_config_changed()

    def _on_radio_console_clicked(self, checked):
        """控制台模式互斥：点击某项即选中它并取消另一项，不允许空选"""
        if self.sender() is self.radio_gui:
            self.radio_gui.setChecked(True)
            self.radio_console.setChecked(False)
        else:
            self.radio_console.setChecked(True)
            self.radio_gui.setChecked(False)
        self._on_config_changed()

    def _on_collect_toggled(self, checked):
        """附加依赖收集复选框：控制输入框显隐"""
        self.collect_edit.setVisible(checked)
        self._on_config_changed()

    def _on_exclude_toggled(self, checked):
        """排除打包库复选框：控制输入框显隐"""
        self.exclude_edit.setVisible(checked)
        self._on_config_changed()

    # ==================== 模板操作 ====================
    def _refresh_template_combo(self):
        """刷新模板下拉列表"""
        current = self.template_combo.currentText()
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        names = tpl.get_template_names()
        self.template_combo.addItems(names)
        # 恢复上次选择
        if current and current in names:
            self.template_combo.setCurrentText(current)
        self.template_combo.blockSignals(False)

    def _on_load_template(self):
        """加载模板：全覆盖右侧打包参数配置"""
        name = self.template_combo.currentText().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请先选择一个模板")
            return
        tpl_config = tpl.get_template_config(name)
        if not tpl_config:
            QMessageBox.warning(self, "提示", f"模板「{name}」加载失败")
            return
        # 仅覆盖打包参数，保留路径类配置
        current = self._collect_config()
        current.update(tpl_config)
        self._apply_config(current)
        self._log("info", f"已加载模板：{name}")

    def _on_save_template(self):
        """保存当前配置为用户自定义模板"""
        name, ok = QInputDialog.getText(self, "保存模板", "请输入模板名称：")
        if not ok or not name.strip():
            return
        config = self._collect_config()
        success, msg = tpl.save_user_template(name.strip(), config)
        if success:
            self._refresh_template_combo()
            self.template_combo.setCurrentText(name.strip())
            self._log("success", msg)
            QMessageBox.information(self, "成功", msg)
        else:
            self._log("error", msg)
            QMessageBox.warning(self, "失败", msg)

    def _on_delete_template(self):
        """删除用户自定义模板"""
        name = self.template_combo.currentText().strip()
        if not name:
            return
        if tpl.is_builtin(name):
            QMessageBox.warning(self, "禁止删除", "内置官方模板禁止删除")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除模板「{name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        success, msg = tpl.delete_user_template(name)
        if success:
            self._refresh_template_combo()
            self._log("info", msg)
        else:
            self._log("error", msg)
            QMessageBox.warning(self, "失败", msg)

    # ==================== 文件浏览 ====================
    def _browse_main_py(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择主入口PY文件", "", "Python文件 (*.py);;所有文件 (*.*)"
        )
        if path:
            self.main_py_edit.setText(path)
            # 自动识别项目根目录
            root = os.path.dirname(os.path.abspath(path))
            if not self.project_root_edit.text().strip():
                self.project_root_edit.setText(root)

    def _browse_project_root(self):
        path = QFileDialog.getExistingDirectory(self, "选择项目根目录")
        if path:
            self.project_root_edit.setText(path)

    def _browse_requirements(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择requirements.txt", "", "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if path:
            self.req_edit.setText(path)

    def _browse_venv(self):
        path = QFileDialog.getExistingDirectory(self, "选择虚拟环境目录")
        if path:
            self.venv_edit.setText(path)

    def _browse_icon(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择ICO图标", "", "图标文件 (*.ico);;所有文件 (*.*)"
        )
        if path:
            self.icon_edit.setText(path)

    def _browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择EXE输出目录")
        if path:
            self.output_dir_edit.setText(path)

    # ==================== 校验 ====================
    def _validate_main_py(self):
        """校验主入口文件合法性，不合法则标红并锁定打包按钮"""
        path = self.main_py_edit.text().strip()
        valid = bool(path) and os.path.isfile(path) and path.lower().endswith(".py")
        self.main_py_edit.setProperty("error", "true" if path and not valid else "false")
        self.main_py_edit.style().unpolish(self.main_py_edit)
        self.main_py_edit.style().polish(self.main_py_edit)
        self._update_start_button_state()

    def _update_start_button_state(self):
        """根据校验状态更新开始按钮可用性"""
        if self.is_packaging:
            self.btn_start.setEnabled(False)
            return
        path = self.main_py_edit.text().strip()
        valid = bool(path) and os.path.isfile(path) and path.lower().endswith(".py")
        self.btn_start.setEnabled(valid)

    # ==================== 打包操作 ====================
    def _on_start_packaging(self):
        """开始打包"""
        config = self._collect_config()

        # 前置校验
        valid, errors, warnings = validate_config(config)
        for w in warnings:
            self._log("warning", w)
        if not valid:
            for e in errors:
                self._log("error", e)
            QMessageBox.critical(self, "配置错误", "\n".join(errors))
            return

        # 检测PyInstaller
        venv = config.get("venv_path", "")
        installed, version = check_pyinstaller(venv)
        if not installed:
            reply = QMessageBox.question(
                self, "环境缺失",
                "未检测到 PyInstaller，是否立即一键安装？\n\n"
                "点击「是」将执行 pip install pyinstaller",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_install_pyinstaller()
            return

        # 锁定UI
        self._set_ui_locked(True)
        self.is_packaging = True
        self.btn_start.setText("打包进行中...")
        self.btn_start.setEnabled(False)
        self.btn_open_output.setEnabled(False)
        self.last_output_dir = ""

        # 启动打包线程
        self.packager_thread = PackagerThread(config)
        self.packager_thread.log_signal.connect(self._on_log)
        self.packager_thread.finished_signal.connect(self._on_packaging_finished)
        self.packager_thread.start()

    def _on_packaging_finished(self, success, output_dir):
        """打包完成回调"""
        self.is_packaging = False
        self._set_ui_locked(False)
        self.btn_start.setText("开始打包")
        self._update_start_button_state()

        if success and output_dir:
            self.last_output_dir = output_dir
            self.btn_open_output.setEnabled(True)
            self._log("success", "打包完成，可点击「打开输出目录」查看EXE文件")
        else:
            self._log("error", "打包未成功，请查看上方日志排查问题")

    def _on_open_output(self):
        """打开输出目录"""
        if self.last_output_dir and os.path.isdir(self.last_output_dir):
            try:
                if sys.platform == "win32":
                    os.startfile(self.last_output_dir)
                elif sys.platform == "darwin":
                    os.system(f'open "{self.last_output_dir}"')
                else:
                    os.system(f'xdg-open "{self.last_output_dir}"')
            except OSError as e:
                QMessageBox.warning(self, "错误", f"无法打开目录：{str(e)}")
        else:
            QMessageBox.information(self, "提示", "输出目录不存在或尚未打包成功")

    def _on_copy_command(self):
        """复制完整PyInstaller命令到剪贴板"""
        config = self._collect_config()
        cmd = build_command_str(config)
        if not cmd:
            QMessageBox.warning(self, "提示", "请先选择主入口PY文件")
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(cmd)
        self._log("info", "完整打包命令已复制到剪贴板")
        self._log("info", cmd)

    def _on_install_pyinstaller(self):
        """一键安装PyInstaller（先二次确认）"""
        reply = QMessageBox.question(
            self, "确认安装",
            "即将开始安装PyInstaller打包依赖库，是否继续？",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )
        if reply != QMessageBox.StandardButton.Ok:
            return
        config = self._collect_config()
        venv = config.get("venv_path", "")
        self._log("info", "正在安装 PyInstaller，请稍候...")
        self.btn_install_pyinstaller.setEnabled(False)
        self.btn_install_pyinstaller.setText("安装中...")

        # 用子线程避免卡死
        from PyQt6.QtCore import QThread, pyqtSignal

        class InstallThread(QThread):
            done = pyqtSignal(bool, str)
            def run(self_inner):
                ok, out = install_pyinstaller(venv)
                self_inner.done.emit(ok, out)

        self._install_thread = InstallThread()
        self._install_thread.done.connect(self._on_install_done)
        self._install_thread.start()

    def _on_install_done(self, success, output):
        """PyInstaller安装完成"""
        self.btn_install_pyinstaller.setEnabled(True)
        self.btn_install_pyinstaller.setText("安装PyInstaller")
        if success:
            self._log("success", "PyInstaller 安装成功！现在可以开始打包了")
            self._check_env()
            QMessageBox.information(self, "成功", "PyInstaller 安装成功！")
        else:
            self._log("error", f"PyInstaller 安装失败：{output}")
            QMessageBox.critical(self, "失败", f"安装失败：\n{output}")

    # ==================== UI锁定/解锁 ====================
    def _set_ui_locked(self, locked):
        """打包期间锁定/解锁所有配置控件"""
        widgets = [
            self.template_combo, self.btn_load_template, self.btn_save_template,
            self.btn_delete_template,
            self.main_py_edit, self.btn_browse_main,
            self.project_root_edit, self.btn_browse_root,
            self.req_edit, self.btn_browse_req,
            self.venv_edit, self.btn_browse_venv,
            self.radio_onefile, self.radio_folder,
            self.radio_gui, self.radio_console,
            self.icon_edit, self.btn_browse_icon,
            self.exe_name_edit,
            self.collect_check, self.collect_edit,
            self.exclude_check, self.exclude_edit,
            self.output_dir_edit, self.btn_browse_output,
            self.debug_check,
            self.btn_copy_cmd, self.btn_install_pyinstaller,
        ]
        for w in widgets:
            w.setEnabled(not locked)

    # ==================== 日志输出 ====================
    def _on_log(self, level, message):
        """接收子线程日志信号"""
        self._log(level, message)

    def _log(self, level, message):
        """彩色日志输出"""
        color_map = {
            "info": COLOR_TEXT,
            "warning": COLOR_WARNING,
            "error": COLOR_ERROR,
            "success": COLOR_SUCCESS,
        }
        color = color_map.get(level, COLOR_TEXT)
        # HTML转义
        escaped = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f'<span style="color:{color};">{escaped}</span>'
        self.log_text.append(html)
        # 自动滚动到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

    # ==================== 环境检测 ====================
    def _check_env(self):
        """检测PyInstaller环境并更新状态标签"""
        config = self._collect_config()
        venv = config.get("venv_path", "")
        installed, version = check_pyinstaller(venv)
        if installed:
            self.env_label.setText(f"PyInstaller {version} ✓")
            self.env_label.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 12px;")
        else:
            self.env_label.setText("PyInstaller 未安装 ✗")
            self.env_label.setStyleSheet(f"color: {COLOR_WARNING}; font-size: 12px;")

    def showEvent(self, event):
        """窗口显示时检测环境"""
        super().showEvent(event)
        QTimer.singleShot(100, self._check_env)

    def closeEvent(self, event):
        """关闭窗口前保存配置"""
        self._auto_save_config()
        if self.packager_thread and self.packager_thread.isRunning():
            reply = QMessageBox.question(
                self, "确认退出",
                "打包正在进行中，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.packager_thread.cancel()
                self.packager_thread.wait(3000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

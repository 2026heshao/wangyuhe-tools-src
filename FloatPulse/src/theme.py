# -*- coding: utf-8 -*-
"""
====================================================================
主题系统模块  -  theme
====================================================================
配色字典 + QSS 模板，支持浅色/深色两套主题。
切换主题时调用 get_xxx_qss(theme_name) 重新应用 QSS 即可。

设计要点：
  1. 用 string.Template + $var 占位符（QSS 中无 $ 符号，安全）
  2. 所有颜色集中在 THEMES 字典，便于扩展新主题
  3. 提供 get_main_window_qss / get_card_window_qss / get_menu_qss
     三套 QSS 分别用于大窗口、小卡片、右键菜单
  4. 沿用原 #5BC0BE 青色主调，深色模式提高对比度
====================================================================
"""

from string import Template


# ====================================================================
# 配色字典
# ====================================================================
THEMES = {
    "light": {
        # 背景
        "bg":               "#F8F9FA",   # 主背景
        "card_bg":          "rgba(255, 255, 255, 245)",   # 卡片半透明背景
        "card_bg_solid":    "#FFFFFF",   # 卡片实色背景
        "input_bg":         "#FFFFFF",   # 输入框背景
        "menu_bg":          "rgba(255, 255, 255, 250)",   # 菜单背景
        "list_bg":          "rgba(255, 255, 255, 180)",  # 列表半透明背景
        "bg_level2":        "#EEF0F2",   # 二级背景（稍深，用于层级区分）
        # 主色
        "primary":          "#5BC0BE",
        "primary_hover":    "#6FFFE9",
        "primary_pressed":  "#4AA8A6",
        "primary_alpha":    "rgba(91, 192, 190, 0.12)",
        "primary_border":   "rgba(91, 192, 190, 0.30)",
        "primary_border_strong": "rgba(91, 192, 190, 0.40)",
        "list_border":      "rgba(91, 192, 190, 0.25)",
        "list_item_hover":  "rgba(91, 192, 190, 0.10)",
        "list_item_selected": "rgba(91, 192, 190, 0.15)",
        # 文字
        "text":             "#2C3E50",
        "text_secondary":   "#9AA5B1",
        "text_placeholder":  "#B0B8C0",
        "text_disabled":    "#C0C8D0",
        "app_name_text":    "#1A1A1A",   # 软件导航小卡片软件名称（黑色）
        # 危险/成功
        "danger":           "#C0392B",
        "danger_hover":     "#E74C3C",
        "danger_alpha":     "rgba(192, 57, 43, 0.12)",
        "danger_border":    "rgba(192, 57, 43, 0.30)",
        "success":          "#27AE60",
        # 阴影
        "shadow":           "rgba(0, 0, 0, 70)",
        # 侧栏
        "side_bar_bg":      "#FFFFFF",
        "side_bar_btn":     "#9AA5B1",
    },
    "dark": {
        # 背景
        "bg":               "#1E1E2E",   # 深背景
        "card_bg":          "rgba(45, 45, 63, 245)",
        "card_bg_solid":    "#2D2D3F",
        "input_bg":         "#3D3D52",
        "menu_bg":          "rgba(45, 45, 63, 250)",
        "list_bg":          "rgba(45, 45, 63, 180)",
        "bg_level2":        "#2A2A3C",   # 二级背景（稍亮，用于层级区分）
        # 主色（深色模式提高亮度）
        "primary":          "#6FFFE9",
        "primary_hover":    "#5BC0BE",
        "primary_pressed":  "#4AA8A6",
        "primary_alpha":    "rgba(111, 255, 233, 0.15)",
        "primary_border":   "rgba(111, 255, 233, 0.30)",
        "primary_border_strong": "rgba(111, 255, 233, 0.45)",
        "list_border":      "rgba(111, 255, 233, 0.20)",
        "list_item_hover":  "rgba(111, 255, 233, 0.10)",
        "list_item_selected": "rgba(111, 255, 233, 0.18)",
        # 文字
        "text":             "#E0E0E0",
        "text_secondary":   "#9AA5B1",
        "text_placeholder":  "#6C7380",
        "text_disabled":    "#5A6170",
        "app_name_text":    "#E0E0E0",   # 软件导航小卡片软件名称（深色主题保持浅色可读）
        # 危险/成功
        "danger":           "#E74C3C",
        "danger_hover":     "#FF6B5B",
        "danger_alpha":     "rgba(231, 76, 60, 0.15)",
        "danger_border":    "rgba(231, 76, 60, 0.35)",
        "success":          "#2ECC71",
        # 阴影
        "shadow":           "rgba(0, 0, 0, 120)",
        # 侧栏
        "side_bar_bg":      "#2A2A3A",
        "side_bar_btn":     "#9AA5B1",
    },
}


# ====================================================================
# QSS 模板
# ====================================================================

# 大窗口主UI QSS
_QSS_MAIN_WINDOW = Template("""
* {
    font-family: 'Microsoft YaHei', '微软雅黑';
}

QWidget#mainWindow {
    background-color: $bg;
}

/* ---- 侧边栏 ---- */
QWidget#sideBar {
    background-color: $side_bar_bg;
    border-right: 1px solid $list_border;
}

QPushButton#navBtn {
    background-color: transparent;
    color: $side_bar_btn;
    border: none;
    border-radius: 10px;
    padding: 12px 14px;
    text-align: left;
    font-size: 13px;
}
QPushButton#navBtn:hover {
    background-color: $list_item_hover;
    color: $primary;
}
QPushButton#navBtn:checked {
    background-color: $primary_alpha;
    color: $primary;
    font-weight: bold;
}

QLabel#sideBarTitle {
    color: $primary;
    font-size: 15px;
    font-weight: bold;
    padding: 10px 14px;
}

/* ---- 内容区 ---- */
QWidget#contentArea {
    background-color: $bg;
}

QLabel#pageTitle {
    color: $text;
    font-size: 18px;
    font-weight: bold;
}

QLabel {
    color: $text;
}

QLabel#hintLabel {
    color: $text_secondary;
    font-size: 11px;
}

QLabel#sectionLabel {
    color: $text;
    font-size: 13px;
    font-weight: bold;
}

/* 设置页分隔线 */
QFrame#settingsSeparator {
    background-color: $list_border;
    max-height: 1px;
    min-height: 1px;
    border: none;
    margin: 4px 0px;
}

/* ---- 通用按钮 ---- */
QPushButton {
    background-color: $primary;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    font-size: 13px;
}
QPushButton:hover { background-color: $primary_hover; }
QPushButton:pressed { background-color: $primary_pressed; }
QPushButton:disabled { background-color: $text_disabled; color: white; }

QPushButton#secondaryBtn {
    background-color: $primary_alpha;
    color: $primary;
    border: 1px solid $primary_border;
}
QPushButton#secondaryBtn:hover {
    background-color: $primary;
    color: white;
}

QPushButton#dangerBtn {
    background-color: $danger_alpha;
    color: $danger;
    border: 1px solid $danger_border;
}
QPushButton#dangerBtn:hover {
    background-color: $danger;
    color: white;
}

QPushButton#iconBtn {
    background-color: $primary_alpha;
    color: $primary;
    border: 1px solid $primary_border;
    padding: 6px;
    font-size: 16px;
    border-radius: 10px;
}
QPushButton#iconBtn:hover {
    background-color: $primary;
    color: white;
    border: 1px solid $primary;
}
QPushButton#iconBtn:pressed {
    background-color: $primary_pressed;
    color: white;
}

/* ---- 输入控件 ---- */
QLineEdit, QTextEdit, QPlainTextEdit, QDateEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: $input_bg;
    border: 1px solid $primary_border_strong;
    border-radius: 8px;
    padding: 6px 10px;
    color: $text;
    font-size: 13px;
    selection-background-color: $list_item_selected;
    selection-color: $text;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid $primary;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
    color: $text_disabled;
}

QLineEdit::placeholder, QTextEdit::placeholder {
    color: $text_placeholder;
}

QComboBox::drop-down {
    width: 20px;
    border: none;
}
QComboBox QAbstractItemView {
    background-color: $menu_bg;
    border: 1px solid $primary_border;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: $list_item_selected;
    color: $text;
    outline: none;
}

/* ---- 列表 ---- */
QListWidget {
    background-color: $list_bg;
    border: 1px solid $list_border;
    border-radius: 10px;
    padding: 4px;
    color: $text;
    font-size: 13px;
    outline: none;
}
QListWidget::item {
    padding: 8px 10px;
    border-radius: 6px;
}
QListWidget::item:hover {
    background-color: $list_item_hover;
}
QListWidget::item:selected {
    background-color: $list_item_selected;
    color: $text;
}

/* ---- 表格 ---- */
QTableWidget {
    background-color: $card_bg_solid;
    border: 1px solid $list_border;
    border-radius: 10px;
    gridline-color: transparent;
    color: $text;
    font-size: 13px;
    outline: none;
}
QTableWidget QWidget {
    background-color: $card_bg_solid;
}
QTableWidget::item {
    padding: 6px;
    background-color: transparent;
}
QTableWidget::item:selected {
    background-color: $list_item_selected;
    color: $text;
}
/* 表头 */
QHeaderView {
    background-color: $card_bg_solid;
    border: none;
}
QHeaderView::section {
    background-color: $primary_alpha;
    color: $primary;
    padding: 8px 10px;
    border: none;
    border-right: 1px solid $card_bg_solid;
    font-weight: bold;
    font-size: 13px;
}
QHeaderView::section:last {
    border-right: none;
}
/* 滚动条区域 */
QTableWidget QScrollBar:vertical {
    background-color: transparent;
    border: none;
}
QTableWidget QScrollBar::handle:vertical {
    background-color: $text_disabled;
    border-radius: 3px;
    min-height: 30px;
}
QTableWidget QScrollBar::handle:vertical:hover {
    background-color: $primary;
}
/* 表格内操作按钮（紧凑型，确保文字完整显示） */
QPushButton#tableOpenBtn {
    background-color: $primary_alpha;
    color: $primary;
    border: 1px solid $primary_border;
    border-radius: 6px;
    padding: 2px 10px;
    font-size: 12px;
    min-width: 50px;
    max-width: 70px;
}
QPushButton#tableOpenBtn:hover {
    background-color: $primary;
    color: white;
}

/* ---- 复选框 ---- */
QCheckBox {
    color: $text;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid $primary_border_strong;
    background-color: $input_bg;
}
QCheckBox::indicator:hover {
    border: 1px solid $primary;
}
QCheckBox::indicator:checked {
    background-color: $primary;
    border: 1px solid $primary;
}

/* ---- 滚动条 ---- */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: $primary_border;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: $primary; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: $primary_border;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: $primary; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* ---- 菜单 ---- */
QMenu {
    background-color: $menu_bg;
    border: 1px solid $primary_border;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 30px 8px 18px;
    border-radius: 6px;
    font-size: 13px;
    color: $text;
}
QMenu::item:selected {
    background-color: $list_item_selected;
    color: $primary;
}
QMenu::separator {
    height: 1px;
    background: $list_border;
    margin: 4px 8px;
}

/* ---- 状态栏 ---- */
QStatusBar {
    background-color: $card_bg_solid;
    color: $text_secondary;
    border-top: 1px solid $list_border;
}

/* ---- 分割器 ---- */
QSplitter::handle {
    background-color: $list_border;
}
QSplitter::handle:hover {
    background-color: $primary;
}

/* ---- 分组框 ---- */
QGroupBox {
    border: 1px solid $list_border;
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 10px;
    color: $text;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: $primary;
}

/* ---- 标签页 ---- */
QTabWidget::pane {
    border: 1px solid $list_border;
    border-radius: 10px;
    background-color: $card_bg_solid;
}
QTabBar::tab {
    background-color: transparent;
    color: $text_secondary;
    padding: 8px 16px;
    border-radius: 8px;
    margin-right: 4px;
}
QTabBar::tab:hover {
    background-color: $list_item_hover;
    color: $primary;
}
QTabBar::tab:selected {
    background-color: $primary_alpha;
    color: $primary;
    font-weight: bold;
}

/* ---- 进度条 ---- */
QProgressBar {
    background-color: $input_bg;
    border: 1px solid $list_border;
    border-radius: 6px;
    text-align: center;
    color: $text;
}
QProgressBar::chunk {
    background-color: $primary;
    border-radius: 5px;
}

/* ---- 设置页滚动区（视口透明，防止透明分层窗口下渲染成黑色） ---- */
QScrollArea#settingsScroll {
    background-color: transparent;
    border: none;
}
QScrollArea#settingsScroll > QWidget > QWidget {
    background-color: transparent;
}
""")


# 小卡片弹窗 QSS
_QSS_CARD_WINDOW = Template("""
QWidget#cardContainer {
    background-color: $card_bg;
    border-radius: 22px;
    border: 1px solid $primary_border;
}

/* ---- 左侧 Tab 导航栏 ---- */
QWidget#sideTabBar {
    background-color: transparent;
    border-right: 1px solid $primary_border;
    border-top-left-radius: 22px;
    border-bottom-left-radius: 22px;
}
QPushButton#sideTabIconBtn {
    background-color: transparent;
    color: $text_secondary;
    border: none;
    border-radius: 10px;
    font-size: 18px;
    padding: 0px;
}
QPushButton#sideTabIconBtn:hover {
    background-color: $primary_alpha;
    color: $primary;
}
QPushButton#sideTabIconBtn:pressed {
    background-color: $primary_pressed;
    color: white;
}
QPushButton#sideTabIconBtn:checked {
    background-color: $primary_alpha;
    color: $primary;
}

QLabel#titleLabel {
    color: $primary;
    font-size: 14px;
    font-weight: bold;
    font-family: 'Microsoft YaHei', '微软雅黑';
}
QLabel#contentLabel {
    color: $text;
    font-size: 15px;
    font-family: 'Microsoft YaHei', '微软雅黑';
}
QLabel#hintLabel {
    color: $text_secondary;
    font-size: 11px;
    font-family: 'Microsoft YaHei', '微软雅黑';
}
QPushButton#modeBtn {
    background-color: $primary_alpha;
    color: $primary;
    border: 1px solid $primary_border;
    border-radius: 12px;
    padding: 5px 14px;
    font-size: 12px;
    font-family: 'Microsoft YaHei', '微软雅黑';
}
QPushButton#modeBtn:checked {
    background-color: $primary;
    color: white;
    border: 1px solid $primary;
}
QPushButton#closeBtn {
    background-color: $danger_alpha;
    color: $danger;
    border: 1px solid $danger_border;
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 14px;
    font-weight: bold;
    min-width: 26px;
}
QPushButton#closeBtn:hover {
    background-color: $danger;
    color: white;
}
QPushButton#nextBtn {
    background-color: $primary;
    color: white;
    border: none;
    border-radius: 14px;
    padding: 9px 26px;
    font-size: 13px;
    font-family: 'Microsoft YaHei', '微软雅黑';
}
QPushButton#nextBtn:hover { background-color: $primary_hover; }
QPushButton#nextBtn:pressed { background-color: $primary_pressed; }
QLineEdit#taskInput {
    background-color: $input_bg;
    border: 1px solid $primary_border_strong;
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 13px;
    font-family: 'Microsoft YaHei', '微软雅黑';
    color: $text;
}
QLineEdit#taskInput:focus {
    border: 1px solid $primary;
}
QDateEdit#taskDate {
    background-color: $input_bg;
    border: 1px solid $primary_border_strong;
    border-radius: 10px;
    padding: 5px 4px;
    font-size: 12px;
    font-family: 'Microsoft YaHei', '微软雅黑';
    color: $text;
}
QDateEdit#taskDate::drop-down {
    width: 18px;
}
QPushButton#taskAddBtn {
    background-color: $primary;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 7px 16px;
    font-size: 12px;
    font-family: 'Microsoft YaHei', '微软雅黑';
}
QPushButton#taskAddBtn:hover { background-color: $primary_hover; }
QPushButton#taskAddBtn:pressed { background-color: $primary_pressed; }
QListWidget#taskList {
    background-color: $list_bg;
    border: 1px solid $list_border;
    border-radius: 10px;
    padding: 4px;
    font-family: 'Microsoft YaHei', '微软雅黑';
    font-size: 13px;
    color: $text;
    outline: none;
}
QListWidget#taskList::item {
    padding: 6px 8px;
    border-radius: 6px;
}
QListWidget#taskList::item:hover {
    background-color: $list_item_hover;
}
QListWidget#taskList::item:selected {
    background-color: $list_item_selected;
    color: $text;
}
QTextEdit#noteEdit {
    background-color: $input_bg;
    border: 1px solid $primary_border_strong;
    border-radius: 10px;
    padding: 8px;
    font-family: 'Microsoft YaHei', '微软雅黑';
    font-size: 13px;
    color: $text;
}
QTextEdit#noteEdit:focus {
    border: 1px solid $primary;
}

/* ---- 滚动条（与主窗口一致，柔和主题色） ---- */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: $list_border;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: $primary; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

/* ---- 网址导航小卡片 ---- */
QScrollArea#navScroll {
    background-color: transparent;
    border: none;
}
QScrollArea#navScroll > QWidget > QWidget {
    background-color: transparent;
}
QWidget#navContent {
    background-color: transparent;
}
QPushButton#navSiteBtn {
    background-color: $primary_alpha;
    color: $primary;
    border: 1px solid $primary_border;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 13px;
    font-family: 'Microsoft YaHei', '微软雅黑';
    min-width: 70px;
}
QPushButton#navSiteBtn:hover {
    background-color: $primary;
    color: white;
    border: 1px solid $primary;
}
QPushButton#navSiteBtn:pressed {
    background-color: $primary_pressed;
}

/* ---- 碎片工作台小卡片（与主窗口列表风格一致：透明背景 + 淡色悬停） ---- */
QScrollArea#fragScrollArea {
    background-color: transparent;
    border: none;
}
QScrollArea#fragScrollArea > QWidget > QWidget {
    background-color: transparent;
}
QWidget#fragItemRow {
    background-color: transparent;
    border-radius: 6px;
}
QWidget#fragItemRow:hover {
    background-color: $list_item_hover;
}
QLabel#fragPreview {
    color: $text;
    font-size: 14px;
    font-family: 'Microsoft YaHei', '微软雅黑';
    padding: 4px 6px;
    background: transparent;
    border: none;
}
QPushButton#fragCopyBtn {
    background-color: $primary_alpha;
    color: $primary;
    border: 1px solid $primary_border;
    border-radius: 4px;
    font-size: 12px;
    font-family: 'Microsoft YaHei', '微软雅黑';
    padding: 0px;
}
QPushButton#fragCopyBtn:hover {
    background-color: $primary;
    color: white;
    border: 1px solid $primary;
}
QPushButton#fragDelBtn {
    background-color: $danger_alpha;
    color: $danger;
    border: 1px solid $danger_border;
    border-radius: 4px;
    font-size: 12px;
    font-family: 'Microsoft YaHei', '微软雅黑';
    padding: 0px;
}
QPushButton#fragDelBtn:hover {
    background-color: $danger;
    color: white;
    border: 1px solid $danger;
}

/* ---- 小卡片保持显示模式关闭按钮 ---- */
QPushButton#cardCloseBtn {
    background-color: $danger_alpha;
    color: $danger;
    border: 1px solid $danger_border;
    border-radius: 11px;
    font-size: 14px;
    font-weight: bold;
    padding: 0px;
}
QPushButton#cardCloseBtn:hover {
    background-color: $danger;
    color: white;
    border: 1px solid $danger;
}

/* ---- 临时素材小卡片 ---- */
QScrollArea#assetScroll {
    background-color: transparent;
    border: none;
}
QScrollArea#assetScroll > QWidget > QWidget {
    background-color: transparent;
}
QWidget#assetContent {
    background-color: transparent;
}
QWidget#assetGrid {
    background-color: transparent;
}
QLabel#assetName {
    color: $text_secondary;
    font-size: 11px;
}

/* ---- 软件导航小卡片（只读浏览：图标 + 名称，点击启动） ---- */
QScrollArea#appScroll {
    background-color: transparent;
    border: none;
}
QScrollArea#appScroll > QWidget > QWidget {
    background-color: transparent;
}
QWidget#appContent {
    background-color: transparent;
}
QToolButton#appLaunchBtn {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 4px;
    /* 软件名称文字：浅色主题为黑色，深色主题为浅色（保证可读） */
    color: $app_name_text;
}
QToolButton#appLaunchBtn:hover {
    background-color: $list_item_hover;
    border: 1px solid $primary_border;
}
QToolButton#appLaunchBtn:pressed {
    background-color: $list_item_selected;
}
QToolButton#appLaunchBtn:disabled {
    color: $text_disabled;
}
""")


# 右键菜单 QSS（悬浮球用）
_QSS_MENU = Template("""
QMenu {
    background-color: $menu_bg;
    border: 1px solid $primary_border;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 30px 8px 18px;
    border-radius: 6px;
    font-family: 'Microsoft YaHei', '微软雅黑';
    font-size: 13px;
    color: $text;
}
QMenu::item:selected {
    background-color: $list_item_selected;
    color: $primary;
}
QMenu::separator {
    height: 1px;
    background: $list_border;
    margin: 4px 8px;
}
""")


# ====================================================================
# 公开接口
# ====================================================================
def get_colors(theme_name: str = "light") -> dict:
    """获取指定主题的配色字典，未知主题回退到 light"""
    return THEMES.get(theme_name, THEMES["light"])


def get_main_window_qss(theme_name: str = "light") -> str:
    """获取大窗口主UI的QSS"""
    return _QSS_MAIN_WINDOW.substitute(get_colors(theme_name))


def get_card_window_qss(theme_name: str = "light") -> str:
    """获取小卡片弹窗的QSS"""
    return _QSS_CARD_WINDOW.substitute(get_colors(theme_name))


def get_menu_qss(theme_name: str = "light") -> str:
    """获取右键菜单的QSS"""
    return _QSS_MENU.substitute(get_colors(theme_name))


def available_themes() -> list:
    """返回可用主题列表"""
    return list(THEMES.keys())

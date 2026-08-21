# -*- coding: utf-8 -*-
"""
====================================================================
大窗口主UI模块  -  MainWindow
====================================================================
生活悬浮球的主窗口，承载复杂批量编辑功能。

设计原则：
  - 小卡片做高频轻量操作，大窗口做复杂批量管理
  - 左侧导航栏 + 右侧 QStackedWidget 五面板切换
  - 无边框圆角窗口 + 自定义标题栏（与小卡片风格一致）
  - 主题系统统一管理（浅色/深色），切换时发 theme_changed 信号
  - 关闭=隐藏（不退出程序，悬浮球仍在运行）

五个面板：
  0. 🧩 碎片工作台  - 碎片列表/筛选/搜索/合并/删除
  1. 📋 日程任务    - 任务输入/列表/批量勾选/右键编辑
  2. 📝 笔记管理    - 笔记列表 + 编辑区 + 自动保存
  3. 📚 知识库     - 段落列表/勾选加入碎片池/段落增删改
  4. ⚙️ 设置       - 主题切换/剪贴板上限/自动隐藏秒数/关于

依赖：
  - task_manager.TaskManager
  - note_manager.NoteManager
  - fragment_manager.FragmentManager
  - docx_manager.DocxManager
  - config.ConfigManager
  - clipboard_monitor.ClipboardMonitor
  - theme.get_main_window_qss
====================================================================
"""

import os
import sys
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QStackedWidget, QButtonGroup,
    QListWidget, QListWidgetItem, QComboBox, QLineEdit, QTextEdit,
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QSpinBox,
    QFrame, QMessageBox, QMenu, QSplitter, QApplication,
    QScrollArea, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QInputDialog, QSlider,
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QDate, QTimer, QRect, QRectF, QSize, QEvent
from PyQt6.QtGui import QColor, QPainter, QAction, QIcon, QPixmap, QShortcut, QKeySequence

from src.theme import get_main_window_qss, get_colors
from src.fragment_manager import TYPE_LABELS, TYPE_ICONS


# ====================================================================
# 辅助函数：获取程序根目录（兼容 PyInstaller 打包）
# ====================================================================
def _get_base_dir() -> str:
    """获取程序根目录（src/ 的父目录，打包时为 exe 所在目录）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_icon_file() -> str:
    """在多个候选位置查找图标文件，返回找到的第一个有效路径（找不到返回空串）。

    打包（PyInstaller onedir）后 ico 可能位于：
      - sys._MEIPASS（_internal）
      - exe 同级 / exe 父目录
      - png 备用
    开发环境则直接去项目根目录找。
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidates.append(os.path.join(meipass, "FloatPulse.ico"))
            candidates.append(os.path.join(meipass, "FloatPulse.png"))
        candidates.append(os.path.join(exe_dir, "FloatPulse.ico"))
        candidates.append(os.path.join(exe_dir, "FloatPulse.png"))
        candidates.append(os.path.join(exe_dir, "_internal", "FloatPulse.ico"))
        candidates.append(os.path.join(os.path.dirname(exe_dir), "FloatPulse.ico"))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates.append(os.path.join(base, "FloatPulse.ico"))
        candidates.append(os.path.join(base, "FloatPulse.png"))
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return ""


# ====================================================================
# 辅助函数：获取可用屏幕几何（与 card_window 一致，防止无屏幕环境崩溃）
# ====================================================================
def _get_screen_geometry() -> QRect:
    """获取主屏可用工作区。无屏幕环境回退到默认矩形，避免崩溃。"""
    screen = QApplication.primaryScreen()
    if screen is not None:
        return screen.availableGeometry()
    return QRect(0, 0, 1920, 1080)


class MainWindow(QWidget):
    """生活悬浮球大窗口主UI"""

    # ---- 窗口尺寸常量 ----
    DEFAULT_WIDTH = 920
    DEFAULT_HEIGHT = 620
    # 当前默认尺寸即最小尺寸：窗口可放大自适应，不可小于默认尺寸
    MIN_WIDTH = DEFAULT_WIDTH
    MIN_HEIGHT = DEFAULT_HEIGHT
    SIDE_BAR_WIDTH = 168
    TITLE_BAR_HEIGHT = 48
    SHADOW_MARGIN = 18           # 阴影留白边距

    # ---- 信号 ----
    theme_changed = pyqtSignal(str)   # 主题切换时发射，参数为 "light"/"dark"
    data_changed = pyqtSignal(str)    # 数据变更时发射，参数为数据类型标识
    ball_visibility_changed = pyqtSignal(bool)  # 悬浮球显示/隐藏切换
    card_always_show_changed = pyqtSignal(bool)  # 小卡片保持显示模式切换
    asset_limits_changed = pyqtSignal(int, int)  # 临时素材上限变更（max_count, max_days）
    anim_speed_changed = pyqtSignal(float)       # 悬浮球动画速度变更
    auto_hide_seconds_changed = pyqtSignal(int)  # 悬浮球空闲吸边隐藏秒数变更

    def __init__(self, task_manager, note_manager, fragment_manager,
                 docx_manager, config_manager, clipboard_monitor,
                 temp_asset_manager=None, nav_manager=None):
        super().__init__()
        # 业务管理器实例（与悬浮球共享同一实例）
        self._task_manager = task_manager
        self._note_manager = note_manager
        self._fragment_manager = fragment_manager
        self._docx_manager = docx_manager
        self._config = config_manager
        self._clipboard_monitor = clipboard_monitor
        self._temp_asset_manager = temp_asset_manager
        self._nav_manager = nav_manager

        # 当前主题
        self._theme = self._config.get("theme", "light")

        # 拖动状态
        self._dragging = False
        self._drag_offset = QPoint()
        # 惰性还原状态：最大化时按下标题栏不立即还原窗口，
        # 等真正开始拖动才还原（修复双击标题栏闪动卡死 BUG）
        self._drag_pending_restore = False
        self._drag_press_ratio = 0.0

        # 最大化前的正常窗口几何（还原时精确恢复，不强制回默认尺寸）
        self._normal_geometry = None

        # 边缘缩放状态（方向字符串，None 表示非缩放中）
        self._resizing = None
        self._resize_start_global = QPoint()
        self._resize_start_geom = QRect()

        # 允许关闭标志（程序退出时使用）
        self._allow_close = False

        # 使用说明对话框（F1 切换用）
        self._help_dialog = None

        # 软件导航页面（嵌入 QStackedWidget 的页面组件，非弹窗）
        self._page_app_launcher = None

        # 初始化
        self._init_window()
        self._init_ui()
        self._init_shortcuts()
        self._init_context_menu()
        self._apply_theme()
        # 安装子控件事件过滤器：防止缩放指针残留在子控件上
        self._install_cursor_filter()
        # 默认首页：碎片工作台
        self._stack.setCurrentIndex(0)
        self._refresh_fragments_page()

    # ==================================================================
    # 快捷键初始化
    # ==================================================================
    def _init_shortcuts(self):
        """初始化主窗口快捷键"""
        # ESC: 退出整个程序（主窗口打开时也能生效）
        quit_shortcut = QShortcut(QKeySequence("Escape"), self)
        quit_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        quit_shortcut.activated.connect(self._quit_app)

        # Ctrl+W 或 Ctrl+H: 隐藏主窗口（不用 Ctrl+Q，它是 Qt 默认退出快捷键）
        hide_shortcut1 = QShortcut(QKeySequence("Ctrl+W"), self)
        hide_shortcut1.setContext(Qt.ShortcutContext.ApplicationShortcut)
        hide_shortcut1.activated.connect(self.hide)
        hide_shortcut2 = QShortcut(QKeySequence("Ctrl+H"), self)
        hide_shortcut2.setContext(Qt.ShortcutContext.ApplicationShortcut)
        hide_shortcut2.activated.connect(self.hide)

        # Ctrl+T: 切换主题
        theme_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        theme_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        theme_shortcut.activated.connect(self._toggle_theme)

        # F1: 显示/关闭使用说明（应用级，对话框打开时也能触发）
        help_shortcut = QShortcut(QKeySequence("F1"), self)
        help_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        help_shortcut.activated.connect(self._toggle_help_dialog)

        # Ctrl+1~7: 切换到对应页面
        for i in range(7):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i+1}"), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(lambda idx=i: self._switch_page(idx))

    def _quit_app(self):
        """退出整个程序：重置页面为首页，然后退出"""
        # 重置页面状态为默认首页（碎片工作台）
        if hasattr(self, '_stack'):
            self._stack.setCurrentIndex(0)
        self._allow_close = True
        QApplication.quit()

    def _init_context_menu(self):
        """初始化右键菜单：退出程序"""
        self._menu = QMenu(self)
        self._menu.setStyleSheet(get_main_window_qss(self._theme))

        show_ball_action = QAction("显示/隐藏悬浮球", self._menu)
        show_ball_action.triggered.connect(self._toggle_ball_visibility)
        self._menu.addAction(show_ball_action)

        self._menu.addSeparator()

        quit_action = QAction("退出程序", self._menu)
        quit_action.triggered.connect(self._quit_app)
        self._menu.addAction(quit_action)

    def contextMenuEvent(self, event):
        self._menu.exec(event.globalPos())

    def _toggle_ball_visibility(self):
        """切换悬浮球显示/隐藏"""
        # 从 config 读取当前状态并切换
        current = self._config.get("ball_visible", True)
        new_val = not current
        self._config.set("ball_visible", new_val)
        self._config.save()
        self.ball_visibility_changed.emit(new_val)

    # ==================================================================
    # 窗口初始化
    # ==================================================================
    def _init_window(self):
        """窗口标志：无边框 + 普通窗口层级（不置顶）"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        # 开启鼠标跟踪：悬停时实时检测边缘并切换缩放指针
        self.setMouseTracking(True)
        # 初始位置：屏幕中央偏左，确保完全在可视区内
        self._ensure_on_screen(init=True)
        # 修复：无边框窗口默认缺少 WS_MINIMIZEBOX/WS_MAXIMIZEBOX 样式，
        # 导致点击任务栏按钮只能激活/还原、无法最小化/最大化隐藏
        try:
            import ctypes
            GWL_STYLE = -16
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000
            WS_SYSMENU = 0x00080000
            hwnd = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_STYLE,
                style | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
        except Exception:
            pass

    # ==================================================================
    # 窗口层级容错：确保窗口位置始终在屏幕可视区内
    # ==================================================================
    def _ensure_on_screen(self, init: bool = False):
        """
        将窗口位置修正到主屏可视区内。
        - init=True：首次显示，主动定位到屏幕中央
        - init=False：仅做边界修正，保留用户原位置
        屏幕分辨率变化 / 外接显示器拔出 / 多屏坐标漂移等场景下兜底。
        """
        try:
            screen = _get_screen_geometry()
            if init:
                # 初始居中
                x = screen.left() + (screen.width() - self.width()) // 2
                y = screen.top() + (screen.height() - self.height()) // 2
                self.move(max(screen.left(), x), max(screen.top(), y))
                return
            # 仅做边界修正
            pos = self.pos()
            w = self.width()
            h = self.height()
            x = pos.x()
            y = pos.y()
            # 至少保证窗口 100px 宽度在屏内，避免完全跑出屏幕
            if x + w - 100 < screen.left():
                x = screen.left()
            if x + 100 > screen.right():
                x = screen.right() - w
            if y + h - 60 < screen.top():
                y = screen.top()
            if y + 60 > screen.bottom():
                y = screen.bottom() - h
            self.move(max(screen.left(), x), max(screen.top(), y))
        except Exception:
            # 任何异常都不应阻塞窗口显示
            pass

    def showEvent(self, event):
        """窗口显示前确保位置在屏幕内"""
        super().showEvent(event)
        self._ensure_on_screen(init=False)

    # ==================================================================
    # 全屏/还原切换
    # ==================================================================
    def _toggle_maximize(self):
        """
        全屏/还原切换：最大化铺满屏幕 ⇄ 还原到最大化前的尺寸位置。

        修复：还原时不再强制回到默认尺寸，而是精确恢复用户最大化前的
        自定义几何（未记录时才回退默认尺寸居中），消除大小来回跳变。
        """
        if self.isMaximized():
            self.showNormal()
            # 延迟到窗口状态切换完成后再恢复记忆几何，
            # 避免连续几何变更叠加造成卡顿/画面重叠
            QTimer.singleShot(0, self._restore_normal_geometry)
        else:
            # 最大化前记住当前正常几何（normalGeometry 在最大化时
            # 也能返回还原态几何，这里在非最大化分支直接取 geometry）
            geom = self._normal_geometry if self._normal_geometry else self.geometry()
            self._normal_geometry = QRect(geom)
            self.showMaximized()

    def _restore_normal_geometry(self):
        """
        还原为最大化前记住的正常几何。

        - 有记忆几何 → 精确恢复（尺寸 + 位置），不做强制居中
        - 无记忆几何 → 回退默认尺寸并居中
        - 不调用 repaint()，避免与 changeEvent 重绘叠加造成闪动
        """
        if self._normal_geometry is not None and not self._normal_geometry.isNull():
            geom = self._normal_geometry
            # 保证恢复位置在屏幕可视区内（防止分辨率变化后跑出屏幕）
            screen = _get_screen_geometry()
            x = max(screen.left(), min(geom.x(), screen.right() - geom.width()))
            y = max(screen.top(), min(geom.y(), screen.bottom() - geom.height()))
            self.setGeometry(x, y, geom.width(), geom.height())
        else:
            self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
            self._center_on_screen()

    def _center_on_screen(self):
        """窗口居中到主屏工作区"""
        try:
            screen = _get_screen_geometry()
            x = screen.left() + (screen.width() - self.width()) // 2
            y = screen.top() + (screen.height() - self.height()) // 2
            self.move(max(screen.left(), x), max(screen.top(), y))
        except Exception:
            pass

    def _update_max_btn(self):
        """根据窗口状态更新全屏/还原按钮的图标和提示"""
        if not hasattr(self, '_max_btn'):
            return
        if self.isMaximized():
            self._max_btn.setText("❐")
            self._max_btn.setToolTip("还原默认尺寸")
        else:
            self._max_btn.setText("⛶")
            self._max_btn.setToolTip("最大化窗口")

    def _apply_window_state_margins(self):
        """最大化时去除阴影边距（避免四周留白），还原时恢复"""
        if not hasattr(self, '_outer_layout'):
            return
        maximized = self.isMaximized()
        margin = 0 if maximized else self.SHADOW_MARGIN
        self._outer_layout.setContentsMargins(margin, margin, margin, margin)

    def paintEvent(self, event):
        """手动绘制窗口外圈柔和阴影（最大化时不绘制）。

        不用 QGraphicsDropShadowEffect：其在窗口状态切换/缩放时
        有离屏缓存残影 bug，且大尺寸重渲染卡顿。
        """
        if self.isMaximized():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        m = self.SHADOW_MARGIN
        # 阴影基于容器区域（窗口内缩一个阴影边距），向下偏移模拟光源
        base = QRectF(self.rect()).adjusted(m, m, -m, -m)
        rings = 8  # 多圈半透明圆角矩形叠加成柔和渐变
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(rings, 0, -1):
            t = i / rings                       # 外圈 t→1，内圈 t→0
            expand = 2.0 + (m - 2.0) * t        # 内圈贴边，外圈扩到窗口边缘
            alpha = int(6 + 42 * (1.0 - t) ** 1.5)  # 内浓外淡
            r = base.adjusted(-expand, -expand + 4.0, expand, expand + 4.0)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(r, 10.0, 10.0)
        painter.end()
        super().paintEvent(event)

    def changeEvent(self, event):
        """窗口状态变化（最大化/还原，含任务栏/系统快捷键触发）时同步 UI"""
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._update_max_btn()
            self._apply_window_state_margins()

    def closeEvent(self, event):
        """关闭窗口的智能处理：
        - _allow_close=True（程序主动退出）→ 直接关闭
        - 悬浮球可见 → 只隐藏主窗口（保持后台运行）
        - 悬浮球不可见 → 退出程序（避免无窗口的僵尸进程）
        """
        if self._allow_close:
            event.accept()
            return
        # 检查悬浮球是否可见
        ball_visible = self._config.get("ball_visible", True)
        if ball_visible:
            # 悬浮球还在 → 只隐藏主窗口
            event.ignore()
            self.hide()
        else:
            # 悬浮球已隐藏 → 退出程序（否则用户无法再次唤起）
            event.accept()
            self._quit_app()

    def _init_ui(self):
        """构建主UI：阴影容器 + 标题栏 + 侧栏 + 内容区"""
        # 主容器：承载圆角背景 + 阴影
        self._container = QWidget(self)
        self._container.setObjectName("mainWindow")

        # 用 QGridLayout 让容器跟随窗口大小，并留出阴影边距
        # （保存引用：最大化时需把边距动态改为 0）
        outer = QGridLayout(self)
        self._outer_layout = outer
        outer.setContentsMargins(
            self.SHADOW_MARGIN, self.SHADOW_MARGIN,
            self.SHADOW_MARGIN, self.SHADOW_MARGIN
        )
        outer.addWidget(self._container)
        # 注意：不使用 QGraphicsDropShadowEffect —— 它在窗口最大化/还原
        # 切换和缩放时会产生离屏缓存残影（鼠标划过按钮触发重绘时显形），
        # 且大尺寸离屏重渲染导致卡顿。阴影改为在 paintEvent 中手动绘制。

        # 主布局
        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部标题栏
        layout.addWidget(self._build_title_bar())

        # 中部：侧栏 + 内容区
        center = QHBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)
        center.addWidget(self._build_side_bar())
        center.addWidget(self._build_content_area(), 1)
        layout.addLayout(center, 1)

    # ==================================================================
    # 顶部标题栏
    # ==================================================================
    def _build_title_bar(self):
        bar = QWidget()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(self.TITLE_BAR_HEIGHT)
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 0, 16, 0)
        h.setSpacing(8)

        # 左侧标题：FloatPulse 图标 + 文字
        # 用 QIcon 加载（比 QPixmap 更可靠），候选位置见 _find_icon_file
        icon_path = _find_icon_file()
        if icon_path:
            _qicon = QIcon(icon_path)
            pm = _qicon.pixmap(22, 22)
            if not pm.isNull():
                icon_label = QLabel()
                icon_label.setPixmap(pm)
                icon_label.setFixedSize(22, 22)
                icon_label.setScaledContents(True)
                h.addWidget(icon_label)
        title = QLabel("生活悬浮球")
        title.setObjectName("titleBarLabel")
        h.addWidget(title)
        h.addStretch()

        # 主题切换按钮
        self._theme_btn = QPushButton("🌙")
        self._theme_btn.setObjectName("iconBtn")
        self._theme_btn.setToolTip("切换深色/浅色主题")
        self._theme_btn.setFixedSize(36, 36)
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.clicked.connect(self._toggle_theme)
        h.addWidget(self._theme_btn)

        # 最小化按钮
        min_btn = QPushButton("—")
        min_btn.setObjectName("iconBtn")
        min_btn.setToolTip("最小化")
        min_btn.setFixedSize(36, 36)
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.clicked.connect(self.showMinimized)
        h.addWidget(min_btn)

        # 全屏/还原切换按钮：最大化铺满屏幕 ⇄ 还原默认尺寸
        self._max_btn = QPushButton("⛶")
        self._max_btn.setObjectName("iconBtn")
        self._max_btn.setToolTip("最大化窗口")
        self._max_btn.setFixedSize(36, 36)
        self._max_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._max_btn.clicked.connect(self._toggle_maximize)
        h.addWidget(self._max_btn)

        # 关闭按钮（触发 closeEvent 智能判断：悬浮球可见则隐藏，不可见则退出）
        close_btn = QPushButton("×")
        close_btn.setObjectName("iconBtn")
        close_btn.setToolTip("关闭窗口")
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        h.addWidget(close_btn)

        return bar

    # ==================================================================
    # 左侧导航栏
    # ==================================================================
    def _build_side_bar(self):
        side = QWidget()
        side.setObjectName("sideBar")
        side.setFixedWidth(self.SIDE_BAR_WIDTH)
        v = QVBoxLayout(side)
        v.setContentsMargins(12, 20, 12, 16)
        v.setSpacing(6)

        # 导航按钮组（互斥）
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        # 上半段导航：碎片 / 任务 / 笔记 / 知识库 / 素材
        nav_items_top = [
            ("🧩  碎片工作台", 0),
            ("📋  日程任务",  1),
            ("📝  笔记管理",  2),
            ("📚  知识库",    3),
            ("📎  临时素材",  4),
        ]
        for text, idx in nav_items_top:
            btn = QPushButton(text)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # 悬停切换页面（不再依赖点击）
            btn.setProperty("pageIndex", idx)
            self._nav_group.addButton(btn, idx)
            v.addWidget(btn)

        # 软件导航按钮（嵌入 QStackedWidget 第8页，索引 7）
        self._app_launcher_btn = QPushButton("🚀  软件导航")
        self._app_launcher_btn.setObjectName("navBtn")
        self._app_launcher_btn.setCheckable(True)
        self._app_launcher_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 悬停切换页面
        self._app_launcher_btn.setProperty("pageIndex", 7)
        self._nav_group.addButton(self._app_launcher_btn, 7)
        v.addWidget(self._app_launcher_btn)

        # 下半段导航：网址导航 / 设置
        nav_items_bottom = [
            ("🌐  网址导航",  5),
            ("⚙️  设置",      6),
        ]
        for text, idx in nav_items_bottom:
            btn = QPushButton(text)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # 悬停切换页面
            btn.setProperty("pageIndex", idx)
            self._nav_group.addButton(btn, idx)
            v.addWidget(btn)

        v.addStretch()

        # 使用说明按钮
        help_btn = QPushButton("❓  使用说明")
        help_btn.setObjectName("navBtn")
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.clicked.connect(self._show_help_dialog)
        v.addWidget(help_btn)

        # 底部版本信息
        ver = QLabel("v2.0 · PyQt6")
        ver.setObjectName("hintLabel")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(ver)

        return side

    # ==================================================================
    # 右侧内容区（QStackedWidget 五面板）
    # ==================================================================
    def _build_content_area(self):
        content = QWidget()
        content.setObjectName("contentArea")
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)

        self._stack = QStackedWidget()

        # 七个面板：碎片 / 任务 / 笔记 / 知识库 / 临时素材 / 网址导航 / 设置
        self._page_fragments = self._build_fragments_page()
        self._page_tasks = self._build_tasks_page()
        self._page_notes = self._build_notes_page()
        self._page_knowledge = self._build_knowledge_page()
        self._page_assets = self._build_assets_page()
        self._page_nav = self._build_nav_page()
        self._page_settings = self._build_settings_page()
        self._page_app_launcher = self._build_app_launcher_page()

        self._stack.addWidget(self._page_fragments)   # 0
        self._stack.addWidget(self._page_tasks)        # 1
        self._stack.addWidget(self._page_notes)       # 2
        self._stack.addWidget(self._page_knowledge)    # 3
        self._stack.addWidget(self._page_assets)       # 4
        self._stack.addWidget(self._page_nav)          # 5
        self._stack.addWidget(self._page_settings)     # 6
        self._stack.addWidget(self._page_app_launcher) # 7

        # 软件导航页面信号：启动软件后请求回到首页
        self._page_app_launcher.request_switch_to_home.connect(
            lambda: self._switch_page(0)
        )

        v.addWidget(self._stack)
        return content

    # ==================================================================
    # 五个面板（占位实现，P1-8 任务填充完整功能）
    # ==================================================================
    def _build_fragments_page(self):
        """碎片工作台面板：列表/筛选/搜索/合并/删除"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # ---- 顶部标题 + 计数 ----
        header = QHBoxLayout()
        title = QLabel("🧩 碎片工作台")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self._frag_count_label = QLabel("共 0 条")
        self._frag_count_label.setObjectName("hintLabel")
        header.addWidget(self._frag_count_label)
        v.addLayout(header)

        # ---- 工具栏：筛选 + 搜索 + 刷新 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._frag_filter = QComboBox()
        self._frag_filter.addItem("全部类型", "all")
        self._frag_filter.addItem("📋 剪贴板文本", "clipboard_text")
        self._frag_filter.addItem("📁 剪贴板路径", "clipboard_path")
        self._frag_filter.addItem("📥 文件拾取",   "file_pickup")
        self._frag_filter.addItem("📚 知识段落",   "knowledge_segment")
        self._frag_filter.currentIndexChanged.connect(self._refresh_fragments_page)
        toolbar.addWidget(self._frag_filter)

        self._frag_search = QLineEdit()
        self._frag_search.setPlaceholderText("🔍 搜索碎片内容...")
        self._frag_search.textChanged.connect(self._refresh_fragments_page)
        toolbar.addWidget(self._frag_search, 1)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.clicked.connect(self._refresh_fragments_page)
        toolbar.addWidget(refresh_btn)
        v.addLayout(toolbar)

        # ---- 碎片列表（多选） ----
        self._frag_list = QListWidget()
        self._frag_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._frag_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._frag_list.customContextMenuRequested.connect(self._on_frag_context_menu)
        # 双击碎片查看详情
        self._frag_list.itemDoubleClicked.connect(self._on_frag_double_click)
        v.addWidget(self._frag_list, 1)

        # ---- 底部按钮栏 ----
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        merge_btn = QPushButton("🔗 合并选中")
        merge_btn.clicked.connect(self._on_merge_fragments)
        bottom.addWidget(merge_btn)

        copy_btn = QPushButton("📋 复制选中")
        copy_btn.setObjectName("secondaryBtn")
        copy_btn.clicked.connect(self._on_copy_fragments)
        bottom.addWidget(copy_btn)

        bottom.addStretch()

        del_btn = QPushButton("🗑 删除选中")
        del_btn.setObjectName("dangerBtn")
        del_btn.clicked.connect(self._on_delete_fragments)
        bottom.addWidget(del_btn)

        clear_btn = QPushButton("清空全部")
        clear_btn.setObjectName("dangerBtn")
        clear_btn.clicked.connect(self._on_clear_fragments)
        bottom.addWidget(clear_btn)

        v.addLayout(bottom)
        return page

    # ---- 碎片工作台业务方法 ----
    def _refresh_fragments_page(self):
        """刷新碎片列表显示：按日期分组，每条只显示内容+时间(时分)"""
        if not hasattr(self, '_frag_list'):
            return
        ftype = self._frag_filter.currentData()
        keyword = self._frag_search.text().strip()

        if ftype == "all":
            fragments = (self._fragment_manager.search_fragments(keyword)
                         if keyword else self._fragment_manager.get_all_fragments())
        else:
            all_of_type = self._fragment_manager.get_fragments_by_type(ftype)
            if keyword:
                kw = keyword.lower()
                fragments = [f for f in all_of_type
                             if kw in f.content.lower() or kw in f.source.lower()]
            else:
                fragments = all_of_type

        self._frag_list.clear()

        # 按日期分组：created_at 格式 "YYYY-MM-DD HH:MM"
        # get_all_fragments 已按 created_at 倒序，同日内最新在前
        current_date = None
        for f in fragments:
            # 解析日期与时分
            created = f.created_at or ""
            # 兼容 "YYYY-MM-DD HH:MM" / "YYYY-MM-DDTHH:MM:SS" 等
            date_part = created[:10] if len(created) >= 10 else created
            time_part = created[11:16] if len(created) >= 16 else created[11:]

            # 日期分组标题（同一天只显示一次）
            if date_part != current_date:
                current_date = date_part
                date_item = QListWidgetItem(f"�  {date_part}")
                date_item.setData(Qt.ItemDataRole.UserRole, None)  # 无 fragment_id
                # 日期标题样式：禁用选中、加粗、改颜色
                flags = date_item.flags()
                date_item.setFlags(flags & ~Qt.ItemFlag.ItemIsSelectable
                                   & ~Qt.ItemFlag.ItemIsEnabled)
                date_item.setForeground(
                    QColor("#5BC0BE") if self._theme == "light"
                    else QColor("#6FFFE9")
                )
                f_font = date_item.font()
                f_font.setBold(True)
                date_item.setFont(f_font)
                # 占位高度
                date_item.setSizeHint(QSize(0, 30))
                self._frag_list.addItem(date_item)

            # 碎片内容行：只显示内容预览 + 时间
            preview_text = f.preview(60)
            text = f"   {preview_text}    {time_part}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, f.fragment_id)
            # 路径类碎片用蓝色高亮
            if f.type in ("clipboard_path", "file_pickup"):
                item.setForeground(QColor("#1976D2") if self._theme == "light"
                                   else QColor("#64B5F6"))
            # tooltip 显示完整信息：类型/来源/完整内容/时间
            icon = TYPE_ICONS.get(f.type, "📄")
            label = TYPE_LABELS.get(f.type, "未知")
            tip_lines = [f"{icon} 类型: {label}"]
            if f.source:
                tip_lines.append(f"🔗 来源: {f.source}")
            tip_lines.append(f"🕐 时间: {created}")
            tip_lines.append(f"📝 内容:\n{f.content}")
            item.setToolTip("\n".join(tip_lines))
            self._frag_list.addItem(item)

        total = self._fragment_manager.count()
        self._frag_count_label.setText(f"显示 {len(fragments)} 条 / 共 {total} 条")
        # 通知小卡片碎片页刷新
        self.data_changed.emit("fragment")

    def _on_frag_context_menu(self, pos):
        """碎片列表右键菜单：查看详情 / 复制 / 转存 / 删除（日期分组标题行无 id 时跳过）"""
        item = self._frag_list.itemAt(pos)
        if not item:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        if fid is None:
            return  # 日期分组标题行，不弹菜单
        menu = QMenu(self)
        menu.setStyleSheet(self._container.styleSheet())
        act_detail = menu.addAction("🔍 查看详情")
        act_copy = menu.addAction("📋 复制内容")
        menu.addSeparator()
        act_to_note = menu.addAction("💾 存为笔记")
        act_to_kb = menu.addAction("📚 加入知识库")
        act_to_nav = menu.addAction("🌐 添加至网址导航")
        menu.addSeparator()
        act_delete = menu.addAction("🗑 删除")
        action = menu.exec(self._frag_list.mapToGlobal(pos))
        if action == act_detail:
            self._show_frag_detail(fid)
        elif action == act_copy:
            frag = self._fragment_manager.get_fragment(fid)
            if frag:
                self._clipboard_monitor.put_text(frag.content)
        elif action == act_to_note:
            self._frag_to_note(fid)
        elif action == act_to_kb:
            self._frag_to_knowledge(fid)
        elif action == act_to_nav:
            self._frag_to_nav(fid)
        elif action == act_delete:
            if self._fragment_manager.delete_fragment(fid):
                self._refresh_fragments_page()

    def _frag_to_note(self, fragment_id: int):
        """将碎片转存为一条新笔记"""
        frag = self._fragment_manager.get_fragment(fragment_id)
        if not frag:
            return
        # 用碎片内容前 20 字作为标题
        title_text = frag.content.replace("\n", " ").strip()[:20]
        title = f"💾 {title_text}{'...' if len(frag.content) > 20 else ''}"
        self._note_manager.add_note(frag.content, title=title)
        self._refresh_notes_page()
        self.data_changed.emit("note")
        QMessageBox.information(self, "已转存", f"碎片已存为新笔记：\n{title}")

    def _frag_to_knowledge(self, fragment_id: int):
        """将碎片内容追加到知识库 docx 末尾"""
        frag = self._fragment_manager.get_fragment(fragment_id)
        if not frag:
            return
        ret = QMessageBox.question(
            self, "确认加入知识库",
            f"将以下碎片内容追加到知识库末尾？\n\n"
            f"{frag.content[:80]}{'...' if len(frag.content) > 80 else ''}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        new_idx = self._docx_manager.append_paragraph(frag.content)
        if new_idx >= 0:
            if self._docx_manager.save():
                self._refresh_knowledge_page()
                self.data_changed.emit("knowledge")
                QMessageBox.information(
                    self, "已加入",
                    f"碎片已追加为知识库段落（编号 {new_idx+1}）。"
                )
            else:
                QMessageBox.warning(self, "保存失败", "docx 保存失败。")
        else:
            QMessageBox.warning(self, "失败", "追加段落失败。")

    def _frag_to_nav(self, fragment_id: int):
        """将 URL 碎片添加到网址导航"""
        if not self._nav_manager:
            QMessageBox.warning(self, "提示", "网址导航管理器未初始化")
            return
        frag = self._fragment_manager.get_fragment(fragment_id)
        if not frag:
            return
        url = frag.content.strip()
        # 检查是否已有分组，没有则先创建一个默认分组
        groups = self._nav_manager.get_groups()
        if not groups:
            self._nav_manager.add_group("默认")
            groups = self._nav_manager.get_groups()
        gid = groups[0].group_id
        # 检查是否已存在相同 URL
        _, existing = self._nav_manager.find_site_by_url(url)
        if existing:
            QMessageBox.information(self, "已存在", f"该 URL 已在网址导航中：\n{existing.title}")
            return
        # 用 URL 域名作为标题
        title = url.split("//")[-1].split("/")[0] if "//" in url else url[:20]
        self._nav_manager.add_site(gid, title, url)
        self._refresh_nav_page()
        self.data_changed.emit("nav")
        QMessageBox.information(self, "已添加", f"已将 URL 添加到网址导航：\n{title}")

    def _on_frag_double_click(self, item):
        """双击碎片查看详情（日期分组标题行无 id 跳过）"""
        fid = item.data(Qt.ItemDataRole.UserRole)
        if fid is None:
            return
        self._show_frag_detail(fid)

    def _show_frag_detail(self, fragment_id):
        """碎片详情对话框：显示完整内容 + 元数据 + 复制按钮"""
        frag = self._fragment_manager.get_fragment(fragment_id)
        if not frag:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("碎片详情")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dialog.resize(560, 460)

        v = QVBoxLayout(dialog)
        v.setContentsMargins(20, 20, 20, 16)
        v.setSpacing(10)

        # 元数据区
        icon = TYPE_ICONS.get(frag.type, "")
        label = TYPE_LABELS.get(frag.type, "未知")
        meta_lines = [
            f"{icon} 类型: {label}",
            f"🆔 ID: {frag.fragment_id}",
            f"🕐 时间: {frag.created_at}",
        ]
        if frag.source:
            meta_lines.append(f"🔗 来源: {frag.source}")
        meta_label = QLabel("\n".join(meta_lines))
        meta_label.setObjectName("hintLabel")
        meta_label.setWordWrap(True)
        v.addWidget(meta_label)

        # 分割线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        v.addWidget(sep)

        # 内容区（完整可滚动可复制）
        content_label = QLabel("📝 完整内容：")
        content_label.setObjectName("sectionLabel")
        v.addWidget(content_label)

        content_edit = QTextEdit()
        content_edit.setReadOnly(True)
        content_edit.setPlainText(frag.content)
        v.addWidget(content_edit, 1)

        # 底部按钮
        btns = QHBoxLayout()
        btns.addStretch()

        copy_btn = QPushButton("📋 复制全部内容")
        copy_btn.clicked.connect(
            lambda: self._clipboard_monitor.put_text(frag.content)
            or QMessageBox.information(dialog, "已复制", "完整内容已复制到剪贴板。")
        )
        btns.addWidget(copy_btn)

        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryBtn")
        close_btn.clicked.connect(dialog.accept)
        btns.addWidget(close_btn)

        v.addLayout(btns)

        dialog.exec()

    def _get_selected_fragment_ids(self) -> list:
        """获取当前选中的碎片 id 列表（过滤日期分组标题行 None id）"""
        return [item.data(Qt.ItemDataRole.UserRole)
                for item in self._frag_list.selectedItems()
                if item.data(Qt.ItemDataRole.UserRole) is not None]

    def _on_merge_fragments(self):
        """合并选中的碎片"""
        ids = self._get_selected_fragment_ids()
        if len(ids) < 2:
            QMessageBox.information(self, "提示", "请至少选择 2 条碎片进行合并。")
            return
        fragments = self._fragment_manager.get_fragments_by_ids(ids)
        if not fragments:
            return
        dialog = MergePreviewDialog(fragments, self._note_manager,
                                    self._clipboard_monitor, self)
        dialog.exec()

    def _on_copy_fragments(self):
        """复制选中的碎片内容到剪贴板"""
        ids = self._get_selected_fragment_ids()
        if not ids:
            return
        fragments = self._fragment_manager.get_fragments_by_ids(ids)
        text = "\n\n".join(f.content for f in fragments)
        self._clipboard_monitor.put_text(text)

    def _on_delete_fragments(self):
        """删除选中的碎片"""
        ids = self._get_selected_fragment_ids()
        if not ids:
            return
        ret = QMessageBox.question(
            self, "确认删除",
            f"确认删除选中的 {len(ids)} 条碎片？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            self._fragment_manager.delete_fragments(ids)
            self._refresh_fragments_page()

    def _on_clear_fragments(self):
        """清空全部碎片"""
        ret = QMessageBox.question(
            self, "确认清空",
            "确认清空全部碎片？此操作不可撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            self._fragment_manager.clear_all()
            self._refresh_fragments_page()

    def _build_tasks_page(self):
        """日程任务面板：输入/列表/批量勾选/右键编辑"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # ---- 顶部标题 + 计数 ----
        header = QHBoxLayout()
        title = QLabel("📋 日程任务")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self._task_count_label = QLabel("共 0 条")
        self._task_count_label.setObjectName("hintLabel")
        header.addWidget(self._task_count_label)
        v.addLayout(header)

        # ---- 输入区 ----
        input_bar = QHBoxLayout()
        input_bar.setSpacing(8)

        self._task_title_input = QLineEdit()
        self._task_title_input.setPlaceholderText("输入任务标题，回车添加...")
        self._task_title_input.returnPressed.connect(self._on_add_task)
        input_bar.addWidget(self._task_title_input, 1)

        self._task_deadline = QLineEdit()
        self._task_deadline.setPlaceholderText("截止日期 YYYY-MM-DD")
        self._task_deadline.setFixedWidth(160)
        self._task_deadline.setText(QDate.currentDate().toString("yyyy-MM-dd"))
        input_bar.addWidget(self._task_deadline)

        add_btn = QPushButton("➕ 添加")
        add_btn.clicked.connect(self._on_add_task)
        input_bar.addWidget(add_btn)
        v.addLayout(input_bar)

        # ---- 任务列表（多选） ----
        self._task_list = QListWidget()
        self._task_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._task_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._task_list.customContextMenuRequested.connect(self._on_task_context_menu)
        v.addWidget(self._task_list, 1)

        # ---- 底部批量操作 ----
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        toggle_btn = QPushButton("✓ 批量完成")
        toggle_btn.setObjectName("secondaryBtn")
        toggle_btn.clicked.connect(self._on_batch_toggle_task)
        bottom.addWidget(toggle_btn)

        del_btn = QPushButton("🗑 批量删除")
        del_btn.setObjectName("dangerBtn")
        del_btn.clicked.connect(self._on_batch_delete_task)
        bottom.addWidget(del_btn)

        bottom.addStretch()

        clear_done_btn = QPushButton("清除已完成")
        clear_done_btn.setObjectName("secondaryBtn")
        clear_done_btn.clicked.connect(self._on_clear_done_tasks)
        bottom.addWidget(clear_done_btn)

        v.addLayout(bottom)
        return page

    # ---- 任务管理业务方法 ----
    def _refresh_tasks_page(self):
        """刷新任务列表显示：未完成任务按 deadline 颜色高亮"""
        if not hasattr(self, '_task_list'):
            return
        from datetime import date as _date
        today_str = _date.today().isoformat()  # "YYYY-MM-DD"

        self._task_list.clear()
        for t in self._task_manager.get_all_tasks():
            status = "✓" if t.done else "☐"
            text = f"{status}  {t.title}"
            if t.deadline:
                text += f"   ｜ 截止: {t.deadline}"
            if t.note:
                text += f"   ｜ 备注: {t.note}"
            text += f"   ｜ 创建: {t.created_at}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, t.task_id)

            # 颜色高亮：已完成灰色；未完成按 deadline 高亮
            if t.done:
                item.setForeground(QColor("#9AA5B1"))
            elif t.deadline:
                # 逾期：红色（深色/浅色主题不同色阶）
                if t.deadline < today_str:
                    item.setForeground(
                        QColor("#E74C3C") if self._theme == "light"
                        else QColor("#FF6B5B")
                    )
                    # 加粗强调
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                # 今日到期：橙色
                elif t.deadline == today_str:
                    item.setForeground(
                        QColor("#E67E22") if self._theme == "light"
                        else QColor("#F39C12")
                    )
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
            self._task_list.addItem(item)

        total = len(self._task_manager.get_all_tasks())
        self._task_count_label.setText(f"共 {total} 条")

    def _on_add_task(self):
        """添加任务"""
        title = self._task_title_input.text().strip()
        if not title:
            return
        deadline = self._task_deadline.text().strip()
        self._task_manager.add_task(title, "", deadline)
        self._task_title_input.clear()
        self._refresh_tasks_page()
        self.data_changed.emit("task")

    def _on_task_context_menu(self, pos):
        """任务列表右键菜单：完成/编辑/删除"""
        item = self._task_list.itemAt(pos)
        if not item:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        task = self._task_manager.get_task(task_id)
        if not task:
            return

        menu = QMenu(self)
        menu.setStyleSheet(self._container.styleSheet())
        act_toggle = menu.addAction("取消完成" if task.done else "标记完成")
        act_edit = menu.addAction("✏️ 编辑...")
        menu.addSeparator()
        act_delete = menu.addAction("🗑 删除")
        action = menu.exec(self._task_list.mapToGlobal(pos))

        if action == act_toggle:
            self._task_manager.toggle_task(task_id)
            self._refresh_tasks_page()
            self.data_changed.emit("task")
        elif action == act_edit:
            self._edit_task_dialog(task)
        elif action == act_delete:
            self._task_manager.delete_task(task_id)
            self._refresh_tasks_page()
            self.data_changed.emit("task")

    def _edit_task_dialog(self, task):
        """编辑任务对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑任务")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dialog.setFixedSize(360, 220)

        form = QFormLayout(dialog)
        form.setContentsMargins(20, 20, 20, 16)
        form.setSpacing(10)

        title_edit = QLineEdit(task.title)
        note_edit = QLineEdit(task.note)
        note_edit.setPlaceholderText("备注（可选）")
        deadline_edit = QLineEdit(task.deadline)
        deadline_edit.setPlaceholderText("YYYY-MM-DD")

        form.addRow("标题:", title_edit)
        form.addRow("备注:", note_edit)
        form.addRow("截止:", deadline_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        form.addRow(btns)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._task_manager.update_task(
                task.task_id,
                title_edit.text().strip(),
                note_edit.text().strip(),
                deadline_edit.text().strip(),
            )
            self._refresh_tasks_page()
            self.data_changed.emit("task")

    def _get_selected_task_ids(self) -> list:
        """获取选中的任务 id 列表"""
        return [item.data(Qt.ItemDataRole.UserRole)
                for item in self._task_list.selectedItems()]

    def _on_batch_toggle_task(self):
        """批量切换任务完成状态"""
        ids = self._get_selected_task_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先选择要操作的任务。")
            return
        for tid in ids:
            self._task_manager.toggle_task(tid)
        self._refresh_tasks_page()
        self.data_changed.emit("task")

    def _on_batch_delete_task(self):
        """批量删除任务"""
        ids = self._get_selected_task_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先选择要删除的任务。")
            return
        ret = QMessageBox.question(
            self, "确认删除",
            f"确认删除选中的 {len(ids)} 条任务？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            for tid in ids:
                self._task_manager.delete_task(tid)
            self._refresh_tasks_page()
            self.data_changed.emit("task")

    def _on_clear_done_tasks(self):
        """清除所有已完成的任务"""
        done_ids = [t.task_id for t in self._task_manager.get_all_tasks() if t.done]
        if not done_ids:
            QMessageBox.information(self, "提示", "没有已完成的任务。")
            return
        ret = QMessageBox.question(
            self, "确认清除",
            f"确认清除 {len(done_ids)} 条已完成的任务？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            for tid in done_ids:
                self._task_manager.delete_task(tid)
            self._refresh_tasks_page()
            self.data_changed.emit("task")

    def _build_notes_page(self):
        """笔记管理面板：列表 + 编辑区 + 自动保存"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # ---- 顶部标题 + 计数 ----
        header = QHBoxLayout()
        title = QLabel("📝 笔记管理")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self._note_count_label = QLabel("共 0 条")
        self._note_count_label.setObjectName("hintLabel")
        header.addWidget(self._note_count_label)
        v.addLayout(header)

        # ---- 工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        new_btn = QPushButton("＋ 新建笔记")
        new_btn.clicked.connect(self._on_new_note)
        toolbar.addWidget(new_btn)

        del_btn = QPushButton("🗑 删除当前")
        del_btn.setObjectName("dangerBtn")
        del_btn.clicked.connect(self._on_delete_note)
        toolbar.addWidget(del_btn)

        toolbar.addStretch()

        self._note_status_label = QLabel("")
        self._note_status_label.setObjectName("hintLabel")
        toolbar.addWidget(self._note_status_label)

        v.addLayout(toolbar)

        # ---- 搜索框 ----
        self._note_search = QLineEdit()
        self._note_search.setPlaceholderText("🔍 搜索标题或内容...")
        self._note_search.textChanged.connect(self._refresh_notes_page)
        v.addWidget(self._note_search)

        # ---- 左右分栏：列表 + 编辑区 ----
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._note_list = QListWidget()
        self._note_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._note_list.customContextMenuRequested.connect(self._on_note_context_menu)
        self._note_list.currentItemChanged.connect(self._on_note_selected)
        splitter.addWidget(self._note_list)

        self._note_edit = QTextEdit()
        self._note_edit.setPlaceholderText("选择左侧笔记查看/编辑，或点「新建笔记」开始...")
        self._note_edit.textChanged.connect(self._on_note_text_changed)
        splitter.addWidget(self._note_edit)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([240, 600])
        v.addWidget(splitter, 1)

        # 自动保存防抖定时器
        self._note_save_timer = QTimer(self)
        self._note_save_timer.setSingleShot(True)
        self._note_save_timer.setInterval(800)
        self._note_save_timer.timeout.connect(self._on_save_note)
        # 加载笔记时防止触发自动保存
        self._loading_note = False
        self._current_note_id = None

        return page

    # ---- 笔记管理业务方法 ----
    def _refresh_notes_page(self):
        """刷新笔记列表显示：标题 + 修改时间，支持关键字搜索（标题+内容）"""
        if not hasattr(self, '_note_list'):
            return
        current_id = self._current_note_id
        # 搜索关键字过滤（匹配标题或内容，大小写不敏感）
        keyword = (self._note_search.text().strip().lower()
                   if hasattr(self, '_note_search') else "")
        self._note_list.clear()
        notes = self._note_manager.get_all_notes()
        shown = 0
        for n in notes:
            # 关键字过滤
            if keyword:
                in_title = keyword in (n.title or "").lower()
                in_content = keyword in (n.content or "").lower()
                if not (in_title or in_content):
                    continue
            title = n.title or "（无标题）"
            # 提取日期与时分
            updated = n.update_time or ""
            date_part = updated[:10] if len(updated) >= 10 else updated
            time_part = updated[11:16] if len(updated) >= 16 else updated[11:]
            time_display = f"{date_part} {time_part}".strip()
            text = f"📝 {title}   · {time_display}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, n.note_id)
            # tooltip 显示内容预览
            preview = (n.content or "").replace("\n", " ").strip()[:80]
            item.setToolTip(f"标题: {title}\n时间: {time_display}\n内容预览: {preview}")
            self._note_list.addItem(item)
            if n.note_id == current_id:
                self._note_list.setCurrentItem(item)
            shown += 1

        # 计数：有搜索时显示「显示 X / 共 Y 条」
        if keyword:
            self._note_count_label.setText(f"显示 {shown} / 共 {len(notes)} 条")
        else:
            self._note_count_label.setText(f"共 {len(notes)} 条")

        # 无笔记时清空编辑区
        if not notes:
            self._loading_note = True
            self._note_edit.clear()
            self._loading_note = False
            self._current_note_id = None

    def _on_note_selected(self, current, previous):
        """列表项切换：加载笔记内容"""
        if current is None:
            return
        note_id = current.data(Qt.ItemDataRole.UserRole)
        note = self._note_manager.get_note(note_id)
        if not note:
            return
        # 先保存当前编辑中的笔记
        if self._note_save_timer.isActive():
            self._note_save_timer.stop()
            self._on_save_note()
        self._loading_note = True
        self._current_note_id = note_id
        self._note_edit.setPlainText(note.content)
        self._loading_note = False
        self._note_status_label.setText(f"编辑中: {note.update_time}")

    def _on_note_text_changed(self):
        """文本变化 → 启动防抖定时器"""
        if self._loading_note:
            return
        if self._current_note_id is None and not self._note_edit.toPlainText().strip():
            return
        self._note_save_timer.start()
        self._note_status_label.setText("● 未保存")

    def _on_save_note(self):
        """自动保存当前笔记"""
        if self._current_note_id is None:
            # 无当前 id：若编辑区有内容则新建
            content = self._note_edit.toPlainText()
            if content.strip():
                self._current_note_id = self._note_manager.add_note(content)
                self._refresh_notes_page()
                self._note_status_label.setText("已保存")
                self.data_changed.emit("note")
        else:
            content = self._note_edit.toPlainText()
            if not self._note_manager.update_note(self._current_note_id, content):
                # id 失效：新建
                if content.strip():
                    self._current_note_id = self._note_manager.add_note(content)
                    self._refresh_notes_page()
            else:
                self._note_status_label.setText("已保存")
                self.data_changed.emit("note")

    def _on_new_note(self):
        """新建笔记"""
        # 先保存当前编辑中的
        if self._note_save_timer.isActive():
            self._note_save_timer.stop()
            self._on_save_note()
        self._current_note_id = None
        self._loading_note = True
        self._note_edit.clear()
        self._loading_note = False
        self._note_edit.setFocus()
        self._note_status_label.setText("新建笔记，输入内容自动保存")

    def _on_delete_note(self):
        """删除当前笔记"""
        if self._current_note_id is None:
            QMessageBox.information(self, "提示", "未选中任何笔记。")
            return
        ret = QMessageBox.question(
            self, "确认删除",
            "确认删除当前笔记？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            self._note_manager.delete_note(self._current_note_id)
            self._current_note_id = None
            self._loading_note = True
            self._note_edit.clear()
            self._loading_note = False
            self._refresh_notes_page()
            self.data_changed.emit("note")

    def _on_note_context_menu(self, pos):
        """笔记列表右键菜单：编辑标题 / 删除"""
        item = self._note_list.itemAt(pos)
        if not item:
            return
        note_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet(self._container.styleSheet())
        act_rename = menu.addAction("✏️ 编辑标题...")
        act_delete = menu.addAction("🗑 删除此笔记")
        action = menu.exec(self._note_list.mapToGlobal(pos))
        if action == act_rename:
            self._rename_note_dialog(note_id)
        elif action == act_delete:
            ret = QMessageBox.question(
                self, "确认删除", "确认删除此笔记？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ret == QMessageBox.StandardButton.Yes:
                self._note_manager.delete_note(note_id)
                if self._current_note_id == note_id:
                    self._current_note_id = None
                    self._loading_note = True
                    self._note_edit.clear()
                    self._loading_note = False
                self._refresh_notes_page()
                self.data_changed.emit("note")

    def _rename_note_dialog(self, note_id: int):
        """编辑笔记标题对话框"""
        note = self._note_manager.get_note(note_id)
        if not note:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑笔记标题")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dialog.setFixedSize(360, 140)

        v = QVBoxLayout(dialog)
        v.setContentsMargins(20, 20, 20, 16)
        v.setSpacing(10)

        hint = QLabel("请输入新标题（1-50 字）：")
        hint.setObjectName("hintLabel")
        v.addWidget(hint)

        title_edit = QLineEdit(note.title or "")
        title_edit.setMaxLength(50)
        title_edit.returnPressed.connect(dialog.accept)
        v.addWidget(title_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        v.addWidget(btns)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_title = title_edit.text().strip()
            if new_title and new_title != note.title:
                self._note_manager.update_title(note_id, new_title)
                self._refresh_notes_page()
                self.data_changed.emit("note")

    def _build_knowledge_page(self):
        """知识库面板：段落列表/勾选加入碎片池/段落增删改"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # ---- 顶部标题 + 计数 ----
        header = QHBoxLayout()
        title = QLabel("📚 知识库")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self._kb_count_label = QLabel("共 0 段")
        self._kb_count_label.setObjectName("hintLabel")
        header.addWidget(self._kb_count_label)
        v.addLayout(header)

        # ---- 工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        add_btn = QPushButton("➕ 新增知识")
        add_btn.clicked.connect(self._on_kb_append_paragraph)
        toolbar.addWidget(add_btn)

        add_frag_btn = QPushButton("📥 加入碎片池")
        add_frag_btn.setObjectName("secondaryBtn")
        add_frag_btn.clicked.connect(self._on_kb_add_to_fragments)
        toolbar.addWidget(add_frag_btn)

        reload_btn = QPushButton("🔄 重新加载")
        reload_btn.setObjectName("secondaryBtn")
        reload_btn.clicked.connect(self._on_kb_reload)
        toolbar.addWidget(reload_btn)

        toolbar.addStretch()

        # 外部修改提示标签
        self._kb_modify_label = QLabel("")
        self._kb_modify_label.setObjectName("hintLabel")
        toolbar.addWidget(self._kb_modify_label)

        v.addLayout(toolbar)

        # ---- 搜索框 ----
        self._kb_search = QLineEdit()
        self._kb_search.setPlaceholderText("🔍 搜索段落内容...")
        self._kb_search.textChanged.connect(self._refresh_knowledge_page)
        v.addWidget(self._kb_search)

        # ---- 段落列表（多选） ----
        self._kb_list = QListWidget()
        self._kb_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._kb_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._kb_list.customContextMenuRequested.connect(self._on_kb_context_menu)
        v.addWidget(self._kb_list, 1)

        # ---- 底部提示 ----
        hint = QLabel("右键段落：编辑 / 删除 / 在此后新增 / 加入碎片池")
        hint.setObjectName("hintLabel")
        v.addWidget(hint)

        return page

    # ---- 知识库业务方法 ----
    def _refresh_knowledge_page(self):
        """刷新知识库段落列表"""
        if not hasattr(self, '_kb_list'):
            return
        # 搜索关键字过滤
        keyword = (self._kb_search.text().strip().lower()
                   if hasattr(self, '_kb_search') else "")
        self._kb_list.clear()
        paragraphs = self._docx_manager.get_paragraphs()
        shown = 0
        for p in paragraphs:
            # 关键字过滤（空关键字显示全部）
            if keyword and keyword not in (p.text or "").lower():
                continue
            # ParagraphInfo.preview 是字符串属性（非方法），直接截断 80 字
            preview_text = (p.text or "").replace("\n", " ").strip()[:80]
            text = f"[{p.index+1}] {preview_text}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, p.index)
            item.setToolTip(p.text)
            self._kb_list.addItem(item)
            shown += 1
        # 计数显示：有搜索时显示「显示 X / 共 Y 段」
        if keyword:
            self._kb_count_label.setText(f"显示 {shown} / 共 {len(paragraphs)} 段")
        else:
            self._kb_count_label.setText(f"共 {len(paragraphs)} 段")

        # 检测外部修改
        if self._docx_manager.check_external_modification():
            self._kb_modify_label.setText("⚠️ 检测到外部修改，建议重新加载")
            self._kb_modify_label.setStyleSheet("color: #E67E22;" if self._theme == "light"
                                                else "color: #F39C12;")
        else:
            self._kb_modify_label.setText("✓ 文件无外部修改")
            self._kb_modify_label.setStyleSheet("")

    def _on_kb_context_menu(self, pos):
        """段落右键菜单：编辑/删除/新增/加入碎片池"""
        item = self._kb_list.itemAt(pos)
        if not item:
            return
        index = item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self)
        menu.setStyleSheet(self._container.styleSheet())
        act_edit = menu.addAction("✏️ 编辑此段...")
        act_add_frag = menu.addAction("📥 加入碎片池")
        menu.addSeparator()
        act_insert = menu.addAction("➕ 在此后新增段落...")
        act_delete = menu.addAction("🗑 删除此段")
        action = menu.exec(self._kb_list.mapToGlobal(pos))

        if action == act_edit:
            self._edit_kb_paragraph(index)
        elif action == act_add_frag:
            self._add_kb_paragraph_to_fragments(index)
        elif action == act_insert:
            self._insert_kb_paragraph_after(index)
        elif action == act_delete:
            self._delete_kb_paragraph(index)

    def _edit_kb_paragraph(self, index: int):
        """编辑段落对话框"""
        text = self._docx_manager.get_paragraph_text(index)
        if not text:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"编辑段落 {index+1}")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dialog.resize(460, 240)

        v = QVBoxLayout(dialog)
        v.setContentsMargins(20, 20, 20, 16)
        v.setSpacing(10)

        edit = QTextEdit()
        edit.setPlainText(text)
        v.addWidget(edit, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        v.addWidget(btns)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_text = edit.toPlainText().strip()
            if new_text and new_text != text:
                if self._docx_manager.update_paragraph_text(index, new_text):
                    if self._docx_manager.save():
                        self._refresh_knowledge_page()
                        self.data_changed.emit("knowledge")
                    else:
                        QMessageBox.warning(self, "保存失败", "docx 保存失败，请检查文件权限。")
                else:
                    QMessageBox.warning(self, "修改失败", "段落修改失败。")

    def _insert_kb_paragraph_after(self, index: int):
        """在指定段落后新增段落"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"在段落 {index+1} 后新增")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dialog.resize(460, 240)

        v = QVBoxLayout(dialog)
        v.setContentsMargins(20, 20, 20, 16)
        v.setSpacing(10)

        edit = QTextEdit()
        edit.setPlaceholderText("输入新段落内容...")
        v.addWidget(edit, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        v.addWidget(btns)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_text = edit.toPlainText().strip()
            if new_text:
                new_idx = self._docx_manager.insert_paragraph_after(index, new_text)
                if new_idx >= 0:
                    if self._docx_manager.save():
                        self._refresh_knowledge_page()
                        self.data_changed.emit("knowledge")
                    else:
                        QMessageBox.warning(self, "保存失败", "docx 保存失败。")
                else:
                    QMessageBox.warning(self, "新增失败", "段落新增失败。")

    def _delete_kb_paragraph(self, index: int):
        """删除段落"""
        ret = QMessageBox.question(
            self, "确认删除",
            f"确认删除段落 {index+1}？此操作将修改 docx 文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        if self._docx_manager.delete_paragraph(index):
            if self._docx_manager.save():
                self._refresh_knowledge_page()
                self.data_changed.emit("knowledge")
            else:
                QMessageBox.warning(self, "保存失败", "docx 保存失败，已尝试回滚备份。")
                self._docx_manager.restore_backup()
                self._docx_manager.reload()
                self._refresh_knowledge_page()

    def _add_kb_paragraph_to_fragments(self, index: int):
        """加入段落到碎片池"""
        text = self._docx_manager.get_paragraph_text(index)
        if not text:
            return
        from fragment_manager import TYPE_KNOWLEDGE_SEGMENT
        fid = self._fragment_manager.add_knowledge_segment(text, source=f"知识库#{index+1}")
        QMessageBox.information(self, "已加入", f"段落已加入碎片池（id={fid}）。")

    def _on_kb_add_to_fragments(self):
        """批量加入选中段落到碎片池"""
        ids = [item.data(Qt.ItemDataRole.UserRole) for item in self._kb_list.selectedItems()]
        if not ids:
            QMessageBox.information(self, "提示", "请先选择要加入的段落。")
            return
        from fragment_manager import TYPE_KNOWLEDGE_SEGMENT
        count = 0
        for idx in ids:
            text = self._docx_manager.get_paragraph_text(idx)
            if text:
                self._fragment_manager.add_knowledge_segment(text, source=f"知识库#{idx+1}")
                count += 1
        QMessageBox.information(self, "已加入", f"已加入 {count} 段到碎片池。")

    def _on_kb_append_paragraph(self):
        """新增知识：弹窗输入内容，追加到 docx 末尾"""
        dialog = QDialog(self)
        dialog.setWindowTitle("新增知识")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dialog.resize(460, 260)

        v = QVBoxLayout(dialog)
        v.setContentsMargins(20, 20, 20, 16)
        v.setSpacing(10)

        hint = QLabel("📝 输入新知识内容（将追加到知识库末尾）：")
        hint.setObjectName("sectionLabel")
        v.addWidget(hint)

        edit = QTextEdit()
        edit.setPlaceholderText("输入新段落内容...")
        v.addWidget(edit, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        v.addWidget(btns)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_text = edit.toPlainText().strip()
            if not new_text:
                QMessageBox.information(self, "提示", "内容为空，未新增。")
                return
            new_idx = self._docx_manager.append_paragraph(new_text)
            if new_idx >= 0:
                if self._docx_manager.save():
                    self._refresh_knowledge_page()
                    self.data_changed.emit("knowledge")
                    QMessageBox.information(
                        self, "新增成功",
                        f"已追加为新段落（编号 {new_idx+1}）。"
                    )
                else:
                    QMessageBox.warning(self, "保存失败", "docx 保存失败，请检查文件权限。")
            else:
                QMessageBox.warning(self, "新增失败", "段落追加失败。")

    def _on_kb_reload(self):
        """重新加载 docx"""
        ret = QMessageBox.question(
            self, "确认重新加载",
            "重新加载将丢弃当前未保存的内存修改，并重新读取 docx 文件。确认？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        paragraphs, err = self._docx_manager.reload()
        if err:
            QMessageBox.warning(self, "加载失败", err)
        else:
            self._refresh_knowledge_page()
            self.data_changed.emit("knowledge")

    # ==================================================================
    # 临时素材面板
    # ==================================================================
    def _build_assets_page(self):
        """临时素材面板：列表 / 双击打开 / 右键删除/另存为 / 清空"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # ---- 顶部标题 + 计数 ----
        header = QHBoxLayout()
        title = QLabel("📎 临时素材")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self._asset_count_label = QLabel("共 0 条 / 上限 10")
        self._asset_count_label.setObjectName("hintLabel")
        header.addWidget(self._asset_count_label)
        v.addLayout(header)

        # ---- 提示 ----
        hint = QLabel("💡 拖拽图片/文件到悬浮球即可自动复制保存到此处")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        v.addWidget(hint)

        # ---- 工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        open_folder_btn = QPushButton("📁 打开素材文件夹")
        open_folder_btn.setObjectName("secondaryBtn")
        open_folder_btn.clicked.connect(self._on_open_assets_folder)
        toolbar.addWidget(open_folder_btn)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.clicked.connect(self._refresh_assets_page)
        toolbar.addWidget(refresh_btn)

        toolbar.addStretch()

        clear_btn = QPushButton("🗑 清空全部")
        clear_btn.setObjectName("dangerBtn")
        clear_btn.clicked.connect(self._on_clear_assets)
        toolbar.addWidget(clear_btn)

        v.addLayout(toolbar)

        # ---- 素材列表 ----
        self._asset_list = QListWidget()
        self._asset_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._asset_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._asset_list.customContextMenuRequested.connect(self._on_asset_context_menu)
        self._asset_list.itemDoubleClicked.connect(self._on_asset_double_click)
        v.addWidget(self._asset_list, 1)

        return page

    # ---- 临时素材业务方法 ----
    def _refresh_assets_page(self):
        """刷新临时素材列表显示"""
        if not hasattr(self, '_asset_list') or self._temp_asset_manager is None:
            return
        # 校验失效记录
        self._temp_asset_manager.refresh()

        self._asset_list.clear()
        assets = self._temp_asset_manager.get_all_assets()
        for a in assets:
            icon = "🖼️" if a.is_image else "📄"
            size_str = a.size_display()
            # 时间只显示到时分
            added = a.added_time or ""
            time_display = added[:16] if len(added) >= 16 else added
            text = f"{icon}  {a.original_name}   · {size_str}   · {time_display}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, a.asset_id)
            # tooltip 显示完整信息
            tip = (f"原文件名: {a.original_name}\n"
                   f"类型: {'图片' if a.is_image else '文件'}\n"
                   f"大小: {size_str}\n"
                   f"添加时间: {added}\n"
                   f"存储路径: {a.stored_path}")
            item.setToolTip(tip)
            self._asset_list.addItem(item)

        count = self._temp_asset_manager.count()
        max_assets = self._temp_asset_manager._max_assets
        self._asset_count_label.setText(f"共 {count} 条 / 上限 {max_assets}")

    def _on_asset_context_menu(self, pos):
        """素材右键菜单：打开 / 另存为 / 删除"""
        item = self._asset_list.itemAt(pos)
        if not item:
            return
        aid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet(self._container.styleSheet())
        act_open = menu.addAction("📂 打开")
        act_save_as = menu.addAction("💾 另存为...")
        menu.addSeparator()
        act_delete = menu.addAction("🗑 删除")
        action = menu.exec(self._asset_list.mapToGlobal(pos))
        if action == act_open:
            self._temp_asset_manager.open_asset(aid)
        elif action == act_save_as:
            self._asset_save_as(aid)
        elif action == act_delete:
            if self._temp_asset_manager.delete_asset(aid):
                self._refresh_assets_page()
                self.data_changed.emit("asset")

    def _on_asset_double_click(self, item):
        """双击素材 → 用系统默认程序打开"""
        aid = item.data(Qt.ItemDataRole.UserRole)
        if not self._temp_asset_manager.open_asset(aid):
            QMessageBox.warning(self, "打开失败", "无法打开此素材，文件可能已被删除。")

    def _asset_save_as(self, asset_id: int):
        """另存为：用 QFileDialog 选目标位置，复制一份过去"""
        from PyQt6.QtWidgets import QFileDialog
        asset = self._temp_asset_manager.get_asset(asset_id)
        if not asset:
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "另存为", asset.original_name, "All Files (*.*)"
        )
        if not target:
            return
        import shutil
        try:
            shutil.copy2(asset.stored_path, target)
            QMessageBox.information(self, "已另存为", f"文件已保存到：\n{target}")
        except OSError as e:
            QMessageBox.warning(self, "另存失败", f"另存失败：{e}")

    def _on_open_assets_folder(self):
        """在资源管理器中打开 temp_assets 文件夹"""
        if self._temp_asset_manager is None:
            return
        folder = self._temp_asset_manager._assets_dir
        try:
            os.startfile(folder)
        except OSError:
            QMessageBox.warning(self, "打开失败", f"无法打开文件夹：\n{folder}")

    def _on_clear_assets(self):
        """清空所有临时素材"""
        if self._temp_asset_manager is None:
            return
        count = self._temp_asset_manager.count()
        if count == 0:
            QMessageBox.information(self, "提示", "当前没有临时素材。")
            return
        ret = QMessageBox.question(
            self, "确认清空",
            f"确认清空所有 {count} 个临时素材？\n（仅删除程序目录下的副本，不影响原文件）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            cleared = self._temp_asset_manager.clear_all()
            self._refresh_assets_page()
            self.data_changed.emit("asset")
            QMessageBox.information(self, "已清空", f"已清理 {cleared} 个临时素材。")

    # ==================================================================
    # 网址导航面板
    # ==================================================================
    def _build_nav_page(self):
        """网址导航面板：站点增删改 / 拖拽排序（简化版，无分组）"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # ---- 顶部标题 + 计数 ----
        header = QHBoxLayout()
        title = QLabel("🌐 网址导航")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self._nav_count_label = QLabel("共 0 个站点")
        self._nav_count_label.setObjectName("hintLabel")
        header.addWidget(self._nav_count_label)
        v.addLayout(header)

        # ---- 添加站点行 ----
        add_row = QHBoxLayout()
        add_row.setSpacing(6)

        self._nav_title_input = QLineEdit()
        self._nav_title_input.setPlaceholderText("站点名称...")
        self._nav_url_input = QLineEdit()
        self._nav_url_input.setPlaceholderText("URL（如 baidu.com，自动补全 https://）")

        nav_add_btn = QPushButton("添加站点")
        nav_add_btn.setObjectName("taskAddBtn")
        nav_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        nav_add_btn.clicked.connect(self._on_nav_add_site)

        add_row.addWidget(self._nav_title_input, 1)
        add_row.addWidget(self._nav_url_input, 2)
        add_row.addWidget(nav_add_btn)
        v.addLayout(add_row)

        # ---- 站点列表 ----
        self._nav_table = QTableWidget()
        self._nav_table.setColumnCount(3)
        self._nav_table.setHorizontalHeaderLabels(["标题", "URL", "操作"])
        self._nav_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._nav_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._nav_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._nav_table.horizontalHeader().resizeSection(2, 90)
        self._nav_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._nav_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._nav_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._nav_table.customContextMenuRequested.connect(self._on_nav_context_menu)
        self._nav_table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        v.addWidget(self._nav_table, 1)

        # ---- 底部提示 ----
        hint = QLabel("右键站点：打开 / 编辑 / 删除 | 拖拽行可排序 | URL 自动补全 http/https")
        hint.setObjectName("hintLabel")
        v.addWidget(hint)

        return page

    def _refresh_nav_page(self):
        """刷新网址导航面板（简化版，平铺所有站点）"""
        if not self._nav_manager:
            return
        sites = self._nav_manager.get_all_sites_flat()

        self._nav_table.setRowCount(len(sites))
        for row, site in enumerate(sites):
            title_item = QTableWidgetItem(site.title)
            title_item.setData(Qt.ItemDataRole.UserRole, site.nav_id)
            url_item = QTableWidgetItem(site.url)
            open_btn = QPushButton("打开")
            open_btn.setObjectName("tableOpenBtn")
            open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            open_btn.setFixedHeight(28)
            open_btn.clicked.connect(lambda checked=False, url=site.url: self._open_nav_url(url))
            self._nav_table.setItem(row, 0, title_item)
            self._nav_table.setItem(row, 1, url_item)
            self._nav_table.setCellWidget(row, 2, open_btn)

        self._nav_count_label.setText(f"共 {len(sites)} 个站点")

    def _on_nav_add_site(self):
        """添加站点（简化版，自动放入默认分组）"""
        if not self._nav_manager:
            return
        title = self._nav_title_input.text().strip()
        url = self._nav_url_input.text().strip()
        if not title or not url:
            QMessageBox.warning(self, "提示", "请填写站点名称和 URL")
            return
        self._nav_manager.add_site_simple(title, url)
        self._nav_title_input.clear()
        self._nav_url_input.clear()
        self._refresh_nav_page()
        self.data_changed.emit("nav")

    def _on_nav_context_menu(self, pos):
        """站点列表右键菜单"""
        if not self._nav_manager:
            return
        item = self._nav_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        nav_id = self._nav_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        g, site = self._nav_manager.find_site_by_id(nav_id)
        if not site:
            return

        menu = QMenu(self)
        menu.setStyleSheet(self._container.styleSheet())
        act_open = menu.addAction("🌐 打开")
        act_edit = menu.addAction("✏️ 编辑...")
        menu.addSeparator()
        act_delete = menu.addAction("🗑 删除")

        action = menu.exec(self._nav_table.mapToGlobal(pos))
        if action == act_open:
            self._open_nav_url(site.url)
        elif action == act_edit:
            self._edit_nav_site(site)
        elif action == act_delete:
            self._nav_manager.delete_site_simple(nav_id)
            self._refresh_nav_page()
            self.data_changed.emit("nav")

    def _edit_nav_site(self, site):
        """编辑站点（简化版，自动查找所在分组）"""
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑站点")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dialog.setFixedSize(360, 160)

        form = QFormLayout(dialog)
        form.setContentsMargins(20, 20, 20, 16)
        form.setSpacing(10)

        title_edit = QLineEdit(site.title)
        url_edit = QLineEdit(site.url)

        form.addRow("标题:", title_edit)
        form.addRow("URL:", url_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        form.addRow(btns)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._nav_manager.update_site_simple(site.nav_id, title_edit.text(), url_edit.text())
            self._refresh_nav_page()
            self.data_changed.emit("nav")

    def _open_nav_url(self, url: str):
        """用系统默认浏览器打开 URL（优先 os.startfile，回退 QDesktopServices）"""
        if not url:
            return
        try:
            os.startfile(url)
            return
        except Exception:
            pass
        try:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(url))
        except Exception:
            pass

    def _build_settings_page(self):
        """
        设置面板：主题/行为配置/关于。

        外层使用 QScrollArea 纵向滚动包裹：
        - 设置内容高度超过窗口可视高度时自动出现垂直滚动条
        - 滚动区域本身最小尺寸提示很小，不会把顶层窗口"顶大"
          （修复：切到设置页后拖动边缘窗口不受控自动拉长的 BUG）
        - 内部所有设置控件放入滚动内容的纵向布局，排版整齐
        """
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 纵向滚动区域：按需显示垂直滚动条，禁用水平滚动条
        # objectName 对应 theme QSS 中的透明背景样式——
        # 必须显式透明，否则透明分层窗口下视口会渲染成黑色
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 滚动内容容器：全部设置控件放这里
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 8, 0)   # 右侧留出滚动条空间
        v.setSpacing(8)

        # ---- 顶部标题 ----
        title = QLabel("⚙️ 设置")
        title.setObjectName("pageTitle")
        v.addWidget(title)

        # ---- 主题设置 ----
        theme_box = QWidget()
        tb_v = QVBoxLayout(theme_box)
        tb_v.setContentsMargins(14, 8, 14, 10)
        tb_v.setSpacing(6)

        theme_title = QLabel("🎨 主题外观")
        theme_title.setObjectName("sectionLabel")
        tb_v.addWidget(theme_title)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(8)
        self._set_theme_light = QPushButton("☀️ 浅色主题")
        self._set_theme_light.setObjectName("secondaryBtn")
        self._set_theme_light.setCheckable(True)
        self._set_theme_light.setFixedHeight(28)
        self._set_theme_light.clicked.connect(lambda: self._on_set_theme("light"))
        theme_row.addWidget(self._set_theme_light)

        self._set_theme_dark = QPushButton("🌙 深色主题")
        self._set_theme_dark.setObjectName("secondaryBtn")
        self._set_theme_dark.setCheckable(True)
        self._set_theme_dark.setFixedHeight(28)
        self._set_theme_dark.clicked.connect(lambda: self._on_set_theme("dark"))
        theme_row.addWidget(self._set_theme_dark)
        theme_row.addStretch()
        tb_v.addLayout(theme_row)

        theme_box.setObjectName("settingsGroup")
        v.addWidget(theme_box)

        # ---- 行为设置 ----
        behavior_box = QWidget()
        bb_v = QVBoxLayout(behavior_box)
        bb_v.setContentsMargins(14, 8, 14, 10)
        bb_v.setSpacing(6)

        behavior_title = QLabel("⚙️ 行为配置")
        behavior_title.setObjectName("sectionLabel")
        bb_v.addWidget(behavior_title)

        # 使用网格布局确保标签和控件对齐，避免数字被截断
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.setColumnStretch(0, 0)
        form.setColumnStretch(1, 1)

        # 第一行：剪贴板历史上限
        cb_label = QLabel("剪贴板历史上限:")
        cb_label.setFixedWidth(110)
        self._set_clipboard_max = QSpinBox()
        self._set_clipboard_max.setRange(10, 10000)
        self._set_clipboard_max.setValue(self._config.get("clipboard_max_items", 200))
        self._set_clipboard_max.setSuffix(" 条")
        self._set_clipboard_max.setFixedHeight(28)
        self._set_clipboard_max.setMinimumWidth(140)
        form.addWidget(cb_label, 0, 0)
        form.addWidget(self._set_clipboard_max, 0, 1)

        # 第二行：悬浮球自动隐藏
        ah_label = QLabel("悬浮球自动隐藏:")
        ah_label.setFixedWidth(110)
        self._set_auto_hide = QSpinBox()
        self._set_auto_hide.setRange(1, 60)
        self._set_auto_hide.setValue(self._config.get("auto_hide_seconds", 3))
        self._set_auto_hide.setSuffix(" 秒")
        self._set_auto_hide.setFixedHeight(28)
        self._set_auto_hide.setMinimumWidth(140)
        form.addWidget(ah_label, 1, 0)
        form.addWidget(self._set_auto_hide, 1, 1)

        # 第三行：悬浮球显示开关
        self._set_ball_visible = QCheckBox("显示悬浮球")
        self._set_ball_visible.setChecked(self._config.get("ball_visible", True))
        self._set_ball_visible.stateChanged.connect(self._on_ball_visibility_changed)
        form.addWidget(self._set_ball_visible, 2, 1)

        # 第四行：小卡片保持显示开关
        self._set_card_always_show = QCheckBox("小卡片保持显示（不自动关闭）")
        self._set_card_always_show.setChecked(self._config.get("card_always_show", False))
        self._set_card_always_show.stateChanged.connect(self._on_card_always_show_preview)
        form.addWidget(self._set_card_always_show, 3, 1)

        # 第五行：临时素材数量上限
        ta_count_label = QLabel("临时素材上限:")
        ta_count_label.setFixedWidth(110)
        self._set_temp_asset_max_count = QSpinBox()
        self._set_temp_asset_max_count.setRange(5, 500)
        self._set_temp_asset_max_count.setValue(self._config.get("temp_asset_max_count", 50))
        self._set_temp_asset_max_count.setSuffix(" 个")
        self._set_temp_asset_max_count.setFixedHeight(28)
        self._set_temp_asset_max_count.setMinimumWidth(140)
        form.addWidget(ta_count_label, 4, 0)
        form.addWidget(self._set_temp_asset_max_count, 4, 1)

        # 第六行：临时素材自动清理天数
        ta_days_label = QLabel("素材保留天数:")
        ta_days_label.setFixedWidth(110)
        self._set_temp_asset_max_days = QSpinBox()
        self._set_temp_asset_max_days.setRange(0, 365)
        self._set_temp_asset_max_days.setValue(self._config.get("temp_asset_max_days", 30))
        self._set_temp_asset_max_days.setSuffix(" 天")
        self._set_temp_asset_max_days.setFixedHeight(28)
        self._set_temp_asset_max_days.setMinimumWidth(140)
        self._set_temp_asset_max_days.setToolTip("0 表示不按天数自动清理")
        form.addWidget(ta_days_label, 5, 0)
        form.addWidget(self._set_temp_asset_max_days, 5, 1)

        # 第七行：软件导航卡片尺寸（滑动条已从导航页面迁移至此）
        cs_label = QLabel("软件卡片尺寸:")
        cs_label.setFixedWidth(110)
        self._set_card_size_slider = QSlider(Qt.Orientation.Horizontal)
        self._set_card_size_slider.setRange(60, 140)   # 范围 60-140，int 类型
        self._set_card_size_slider.setValue(self._config.get("app_card_size", 96))
        self._set_card_size_slider.setFixedHeight(28)
        self._set_card_size_slider.setMinimumWidth(140)
        self._set_card_size_slider.setToolTip("调整软件导航页面的卡片大小，实时生效")
        self._set_card_size_slider.valueChanged.connect(self._on_card_size_setting_changed)

        self._set_card_size_label = QLabel(f"{self._set_card_size_slider.value()}px")
        self._set_card_size_label.setObjectName("hintLabel")
        self._set_card_size_label.setFixedWidth(40)

        cs_row = QHBoxLayout()
        cs_row.setSpacing(8)
        cs_row.addWidget(self._set_card_size_slider, 1)
        cs_row.addWidget(self._set_card_size_label)
        form.addWidget(cs_label, 6, 0)
        form.addLayout(cs_row, 6, 1)

        # 第八行：悬浮球动画速度档位（0.5-2.0，滑动条用 50-200 表示除以 100）
        as_label = QLabel("动画速度:")
        as_label.setFixedWidth(110)
        self._set_anim_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._set_anim_speed_slider.setRange(50, 200)
        init_speed = self._config.get("anim_speed", 1.0)
        self._set_anim_speed_slider.setValue(int(round(max(0.5, min(2.0, init_speed)) * 100)))
        self._set_anim_speed_slider.setFixedHeight(28)
        self._set_anim_speed_slider.setMinimumWidth(140)
        self._set_anim_speed_slider.setToolTip("悬浮球动画速度档位：0.5 慢速 - 2.0 快速，实时生效")
        self._set_anim_speed_slider.valueChanged.connect(self._on_anim_speed_setting_changed)

        self._set_anim_speed_label = QLabel(f"{self._set_anim_speed_slider.value() / 100.0:.1f}x")
        self._set_anim_speed_label.setObjectName("hintLabel")
        self._set_anim_speed_label.setFixedWidth(40)

        as_row = QHBoxLayout()
        as_row.setSpacing(8)
        as_row.addWidget(self._set_anim_speed_slider, 1)
        as_row.addWidget(self._set_anim_speed_label)
        form.addWidget(as_label, 7, 0)
        form.addLayout(as_row, 7, 1)

        bb_v.addLayout(form)

        save_btn = QPushButton("💾 保存配置")
        save_btn.setFixedHeight(30)
        save_btn.clicked.connect(self._on_save_settings)
        bb_v.addWidget(save_btn)

        behavior_box.setObjectName("settingsGroup")
        v.addWidget(behavior_box)

        # 注：【管理软件列表】按钮已迁移至软件导航页面顶部，
        #     全局设置页不再出现软件管理相关入口。

        # ---- 关于 ----
        about_box = QWidget()
        ab_v = QVBoxLayout(about_box)
        ab_v.setContentsMargins(14, 8, 14, 10)
        ab_v.setSpacing(4)

        about_title = QLabel("ℹ️ 关于")
        about_title.setObjectName("sectionLabel")
        ab_v.addWidget(about_title)

        about_text = QLabel(
            "生活悬浮球 v2.0 | PyQt6 + python-docx\n"
            "功能：知识卡片 / 日程任务 / 临时笔记 / 碎片合并\n\n"
            "快捷键：Esc 退出 | Ctrl+W/Q 隐藏 | Ctrl+T 主题 | F1 帮助 | Ctrl+1~7 切换面板\n"
            "右键悬浮球 / 右键卡片也可退出"
        )
        about_text.setObjectName("hintLabel")
        about_text.setWordWrap(True)
        ab_v.addWidget(about_text)

        # 日志查看按钮行
        log_row = QHBoxLayout()
        log_row.setSpacing(8)
        view_log_btn = QPushButton("📄 查看日志")
        view_log_btn.setObjectName("secondaryBtn")
        view_log_btn.setFixedHeight(28)
        view_log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_log_btn.clicked.connect(self._on_view_log)
        log_row.addWidget(view_log_btn)

        open_log_dir_btn = QPushButton("📁 打开日志目录")
        open_log_dir_btn.setObjectName("secondaryBtn")
        open_log_dir_btn.setFixedHeight(28)
        open_log_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_log_dir_btn.clicked.connect(self._on_open_log_dir)
        log_row.addWidget(open_log_dir_btn)
        log_row.addStretch()
        ab_v.addLayout(log_row)

        about_box.setObjectName("settingsGroup")
        v.addWidget(about_box)

        v.addStretch()

        # 将全部设置内容装入滚动区域，再把滚动区域装入页面
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    # ---- 软件导航页面 ----
    def _build_app_launcher_page(self):
        """构建软件导航页面（嵌入 QStackedWidget 第8页）。"""
        from src.widget_app_launcher import AppLauncherPage
        return AppLauncherPage(
            self._config, parent=self, theme=self._theme
        )

    # ---- 设置业务方法 ----
    def _refresh_settings_page(self):
        """刷新设置面板当前值"""
        if not hasattr(self, '_set_theme_light'):
            return
        # 主题按钮选中态
        self._set_theme_light.setChecked(self._theme == "light")
        self._set_theme_dark.setChecked(self._theme == "dark")
        # 数值
        self._set_clipboard_max.setValue(self._config.get("clipboard_max_items", 200))
        self._set_auto_hide.setValue(self._config.get("auto_hide_seconds", 3))
        # 小卡片保持显示
        if hasattr(self, '_set_card_always_show'):
            self._set_card_always_show.setChecked(self._config.get("card_always_show", False))
        # 悬浮球显示开关
        if hasattr(self, '_set_ball_visible'):
            self._set_ball_visible.setChecked(self._config.get("ball_visible", True))
        # 软件卡片尺寸滑动条（blockSignals 避免触发重复保存）
        if hasattr(self, '_set_card_size_slider'):
            self._set_card_size_slider.blockSignals(True)
            self._set_card_size_slider.setValue(self._config.get("app_card_size", 96))
            self._set_card_size_slider.blockSignals(False)
            self._set_card_size_label.setText(
                f"{self._set_card_size_slider.value()}px")
        # 动画速度滑动条（blockSignals 避免触发重复保存）
        if hasattr(self, '_set_anim_speed_slider'):
            self._set_anim_speed_slider.blockSignals(True)
            sp = self._config.get("anim_speed", 1.0)
            self._set_anim_speed_slider.setValue(int(round(max(0.5, min(2.0, sp)) * 100)))
            self._set_anim_speed_slider.blockSignals(False)
            self._set_anim_speed_label.setText(f"{self._set_anim_speed_slider.value() / 100.0:.1f}x")

    def _on_set_theme(self, theme_name: str):
        """设置面板切换主题"""
        self.apply_external_theme(theme_name)
        self._refresh_settings_page()
        self.theme_changed.emit(theme_name)

    def _on_save_settings(self):
        """保存配置"""
        self._config.set("clipboard_max_items", self._set_clipboard_max.value())
        self._config.set("auto_hide_seconds", self._set_auto_hide.value())
        new_always_show = self._set_card_always_show.isChecked()
        old_always_show = self._config.get("card_always_show", False)
        self._config.set("card_always_show", new_always_show)
        # 悬浮球显示开关
        self._config.set("ball_visible", self._set_ball_visible.isChecked())
        # 临时素材上限配置
        new_max_count = self._set_temp_asset_max_count.value()
        new_max_days = self._set_temp_asset_max_days.value()
        old_max_count = self._config.get("temp_asset_max_count", 50)
        old_max_days = self._config.get("temp_asset_max_days", 30)
        self._config.set("temp_asset_max_count", new_max_count)
        self._config.set("temp_asset_max_days", new_max_days)
        self._config.save()
        # 保持显示模式发生变化时，实时通知悬浮球应用
        if new_always_show != old_always_show:
            self.card_always_show_changed.emit(new_always_show)
        # 临时素材上限变更 → 通知悬浮球更新管理器并清理
        if new_max_count != old_max_count or new_max_days != old_max_days:
            self.asset_limits_changed.emit(new_max_count, new_max_days)
        # 空闲吸边隐藏秒数变更 → 实时通知悬浮球更新
        self.auto_hide_seconds_changed.emit(int(self._set_auto_hide.value()))
        QMessageBox.information(self, "已保存", "配置已保存，部分设置需重启生效。")

    def _on_ball_visibility_changed(self, state):
        """悬浮球显示/隐藏切换（立即生效并持久化）"""
        is_visible = (state == Qt.CheckState.Checked.value)
        old = self._config.get("ball_visible", True)
        if is_visible != old:
            self._config.set("ball_visible", is_visible)
            self._config.save()
        self.ball_visibility_changed.emit(is_visible)

    def _on_card_always_show_preview(self, state):
        """勾选/取消勾选时实时预览效果（无需点保存即生效）"""
        always_show = bool(state)
        old = self._config.get("card_always_show", False)
        if always_show != old:
            # 立即更新内存配置，让 _check_hover_state 实时读取
            self._config.set("card_always_show", always_show)
            self._config.save()
            self.card_always_show_changed.emit(always_show)

    # ==================================================================
    # 软件卡片尺寸设置（滑动条已从导航页迁移至全局设置页）
    # ==================================================================
    def _on_card_size_setting_changed(self, value: int):
        """
        设置页卡片尺寸滑动条拖动时实时处理。

        - 立即更新 config["app_card_size"] 并保存到磁盘
        - 若软件导航页面已实例化（无论当前是否显示），实时刷新其全部卡片尺寸
        - 若导航页面尚未创建，下次进入导航页面时读取新尺寸渲染
        """
        # 更新数值标签
        self._set_card_size_label.setText(f"{value}px")
        # 持久化到配置（ConfigManager 会按 _CONFIG_RANGES 钳制）
        self._config.set("app_card_size", int(value))
        self._config.save()
        # 导航页面已实例化 → 实时刷新卡片尺寸
        if self._page_app_launcher is not None:
            self._page_app_launcher.apply_card_size(int(value))

    def _on_anim_speed_setting_changed(self, value: int):
        """设置页动画速度滑动条拖动时实时处理并广播到悬浮球"""
        speed = value / 100.0
        self._set_anim_speed_label.setText(f"{speed:.1f}x")
        self._config.set("anim_speed", round(speed, 2))
        self._config.save()
        self.anim_speed_changed.emit(round(speed, 2))

    # ==================================================================
    # 日志查看
    # ==================================================================
    def _on_view_log(self):
        """内置日志查看器：弹窗显示最近 500 行日志"""
        from src.logger import get_log_file_path
        log_path = get_log_file_path()
        if not log_path or not os.path.exists(log_path):
            QMessageBox.information(self, "查看日志", "暂无日志文件。")
            return

        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # 只显示最后 500 行，避免大文件卡顿
            recent_lines = lines[-500:] if len(lines) > 500 else lines
            log_content = "".join(recent_lines)
            if len(lines) > 500:
                log_content = f"...（仅显示最近 500 行，共 {len(lines)} 行）\n\n" + log_content
        except OSError as e:
            QMessageBox.warning(self, "查看日志", f"读取日志失败：{e}")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("程序日志")
        dialog.resize(700, 500)
        v = QVBoxLayout(dialog)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # 顶部信息行
        info = QLabel(f"日志文件：{log_path}")
        info.setObjectName("hintLabel")
        info.setWordWrap(True)
        v.addWidget(info)

        # 日志内容（只读）
        log_view = QTextEdit()
        log_view.setReadOnly(True)
        log_view.setPlainText(log_content)
        # 光标移到末尾，显示最新日志
        cursor = log_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        log_view.setTextCursor(cursor)
        v.addWidget(log_view, 1)

        # 底部按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dialog.reject)
        v.addWidget(btn_box)

        dialog.exec()

    def _on_open_log_dir(self):
        """在资源管理器中打开日志所在目录"""
        from src.logger import get_log_file_path
        log_path = get_log_file_path()
        if not log_path:
            QMessageBox.information(self, "打开日志目录", "暂无日志文件。")
            return
        log_dir = os.path.dirname(log_path)
        if not os.path.exists(log_dir):
            QMessageBox.information(self, "打开日志目录", "日志目录不存在。")
            return
        try:
            os.startfile(log_dir)
        except Exception:
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))
            except Exception:
                QMessageBox.warning(self, "打开日志目录", "无法打开目录，请手动访问：\n" + log_dir)

    # ==================================================================
    # 页面切换
    # ==================================================================
    def _switch_page(self, index: int):
        """切换到指定页面，并刷新对应面板数据"""
        self._stack.setCurrentIndex(index)
        # 默认选中对应的导航按钮
        btn = self._nav_group.button(index)
        if btn is not None:
            btn.setChecked(True)
        # 刷新对应面板
        self._refresh_page(index)

    def _refresh_page(self, index: int):
        """刷新指定页面数据"""
        if index == 0:
            self._refresh_fragments_page()
        elif index == 1:
            self._refresh_tasks_page()
        elif index == 2:
            self._refresh_notes_page()
        elif index == 3:
            self._refresh_knowledge_page()
        elif index == 4:
            self._refresh_assets_page()
        elif index == 5:
            self._refresh_nav_page()
        elif index == 6:
            self._refresh_settings_page()
        elif index == 7:
            # 软件导航页面：重新加载配置并刷新 UI
            if self._page_app_launcher:
                self._page_app_launcher.load_apps_from_config()
                self._page_app_launcher.reload_settings()

    # ==================================================================
    # 公开接口：供外部调用刷新指定面板
    # ==================================================================
    def refresh_fragments(self):
        """外部通知碎片数据变化时调用"""
        if self._stack.currentIndex() == 0:
            self._refresh_fragments_page()

    def refresh_tasks(self):
        """外部通知任务数据变化时调用"""
        if self._stack.currentIndex() == 1:
            self._refresh_tasks_page()

    def refresh_notes(self):
        """外部通知笔记数据变化时调用"""
        if self._stack.currentIndex() == 2:
            self._refresh_notes_page()

    def refresh_knowledge(self):
        """外部通知知识库变化时调用"""
        if self._stack.currentIndex() == 3:
            self._refresh_knowledge_page()

    def refresh_temp_assets(self):
        """外部通知临时素材变化时调用（拖文件到悬浮球后）"""
        if self._stack.currentIndex() == 4:
            self._refresh_assets_page()

    def refresh_nav(self):
        """外部通知网址导航变化时调用"""
        if self._stack.currentIndex() == 5:
            self._refresh_nav_page()

    def show_fragments_page(self):
        """打开并跳转到碎片工作台"""
        self.show()
        self.raise_()
        self.activateWindow()
        self._switch_page(0)

    def show_tasks_page(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self._switch_page(1)

    def show_notes_page(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self._switch_page(2)

    def show_knowledge_page(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self._switch_page(3)

    def show_assets_page(self):
        """快速跳转到临时素材面板"""
        self.show()
        self.raise_()
        self.activateWindow()
        self._switch_page(4)

    def show_nav_page(self):
        """快速跳转到网址导航面板"""
        self.show()
        self.raise_()
        self.activateWindow()
        self._switch_page(5)

    def show_settings_page(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self._switch_page(6)

    # ==================================================================
    # 主题系统
    # ==================================================================
    def _apply_theme(self):
        """应用当前主题的 QSS"""
        qss = get_main_window_qss(self._theme)
        self._container.setStyleSheet(qss)
        # 更新主题切换按钮图标
        self._theme_btn.setText("☀️" if self._theme == "dark" else "🌙")
        # 更新右键菜单样式
        if hasattr(self, '_menu'):
            self._menu.setStyleSheet(qss)
        # 同步更新软件导航页面的主题
        if hasattr(self, '_page_app_launcher') and self._page_app_launcher is not None:
            self._page_app_launcher._theme = self._theme
            self._page_app_launcher._apply_style()

    def _toggle_theme(self):
        """切换浅色/深色主题"""
        self._theme = "dark" if self._theme == "light" else "light"
        self._config.set("theme", self._theme)
        self._config.save()
        self._apply_theme()
        # 通知外部（悬浮球、小卡片）刷新主题
        self.theme_changed.emit(self._theme)

    def apply_external_theme(self, theme_name: str):
        """外部（如设置面板）切换主题时调用"""
        if theme_name not in ("light", "dark"):
            return
        if theme_name == self._theme:
            return
        self._theme = theme_name
        self._config.set("theme", self._theme)
        self._config.save()
        self._apply_theme()

    def current_theme(self) -> str:
        return self._theme

    # ==================================================================
    # 使用说明对话框
    # ==================================================================
    def _toggle_help_dialog(self):
        """F1 切换使用说明对话框的显示/关闭"""
        # 对话框存在且可见 → 关闭它
        if self._help_dialog is not None and self._help_dialog.isVisible():
            self._help_dialog.close()
            return
        # 对话框不存在或已关闭 → 重新创建并显示
        if self._help_dialog is not None:
            # 清理已关闭但未置 None 的旧引用
            self._help_dialog = None
        self._show_help_dialog()

    def _show_help_dialog(self):
        """弹出使用说明对话框"""
        dlg = QDialog(self)
        dlg.setWindowTitle("使用说明")
        dlg.setFixedSize(560, 600)
        self._help_dialog = dlg

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        # 标题
        title = QLabel("📖 生活悬浮球 - 使用说明")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 说明内容（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        # 获取主题色，确保对话框所有元素跟随主题
        colors = get_colors(self._theme)
        text_color = colors.get("text", "#2C3E50")
        bg_color = colors.get("bg", "#F8F9FA")

        content = QLabel()
        content.setWordWrap(True)
        content.setTextFormat(Qt.TextFormat.RichText)
        content.setText(f"""
        <h3>⌨️ 快捷键</h3>
        <p>• <b>Esc</b>：退出程序<br>
        • <b>Ctrl+W / Ctrl+Q</b>：隐藏主窗口<br>
        • <b>Ctrl+T</b>：切换浅色/深色主题<br>
        • <b>F1</b>：打开/关闭使用说明<br>
        • <b>Ctrl+1~7</b>：快速切换到对应面板（碎片/任务/笔记/知识库/素材/网址导航/设置）</p>

        <h3> 悬浮球</h3>
        <p>• <b>鼠标悬停</b>：自动弹出小卡片（恢复上次关闭时的模式）<br>
        • <b>鼠标离开</b>：球+卡片区域外即自动关闭卡片<br>
        • <b>左键点击</b>：切换下一张知识卡片<br>
        • <b>拖拽悬浮球</b>：移动位置；拖动期间卡片保持显示不关闭<br>
        • <b>拖到屏幕边缘</b>：自动吸边隐藏一半；鼠标移近滑出<br>
        • <b>右键悬浮球</b>：打开主窗口 / 退出程序<br>
        • <b>拖文件/图片到悬浮球</b>：自动收录到临时素材（上限10个）</p>

        <h3>🃏 小卡片</h3>
        <p>• <b>三种模式</b>：知识卡片 / 日程任务 / 临时笔记（顶部切换）<br>
        • <b>三模式统一</b>：鼠标离开球+卡片区域即自动关闭<br>
        • <b>卡片可拖动</b>：在顶部空白条或内容区空白处按住左键可拖动整个卡片<br>
        • <b>协同移动</b>：拖动卡片或悬浮球时，二者一起移动保持相对位置<br>
        • <b>拖动期间不关闭</b>：拖动卡片或悬浮球时卡片保持显示<br>
        • <b>模式记忆</b>：关闭时所处的模式会被记住，下次悬停弹出时恢复<br>
        • <b>日程任务</b>：可直接勾选完成，右键菜单编辑/删除<br>
        • <b>临时笔记</b>：输入后 800ms 自动保存，关闭也不丢数据<br>
        • <b>右键卡片</b>：退出程序</p>

        <h3>🧩 碎片工作台</h3>
        <p>• <b>自动收集</b>：复制/划词时自动收集文本碎片<br>
        • <b>按日期分组</b>：同一天的碎片归在一组<br>
        • <b>双击碎片</b>：查看完整内容<br>
        • <b>右键碎片</b>：复制 / 删除 / 存为笔记 / 加入知识库<br>
        • <b>多选 + 合并</b>：选中多条碎片后点击「合并选中」可存为笔记<br>
        • <b>筛选 + 搜索</b>：顶部可按类型筛选或关键词搜索</p>

        <h3>📋 日程任务</h3>
        <p>• 输入标题 + 截止日期后点击「添加」<br>
        • <b>红色</b>：已逾期 &nbsp; <b>橙色</b>：今日到期 &nbsp; <b>灰色</b>：已完成<br>
        • 右键任务：编辑 / 删除</p>

        <h3>📝 笔记管理</h3>
        <p>• 左侧列表显示所有笔记（标题 + 时间）<br>
        • 点击列表项 → 右侧编辑区修改 → 自动保存<br>
        • 顶部搜索框可搜索标题和内容<br>
        • 右键笔记：删除</p>

        <h3> 知识库</h3>
        <p>• 从「知识库.docx」加载段落<br>
        • 顶部「➕ 新增知识」按钮：追加到 docx 末尾<br>
        • 右键段落：编辑 / 删除 / 在此后新增 / 加入碎片池<br>
        • 搜索框：实时过滤段落</p>

        <h3>📎 临时素材</h3>
        <p>• 拖图片/文件到悬浮球 → 自动收录（上限10个，超出淘汰最旧）<br>
        • 双击：用系统默认程序打开<br>
        • 右键：打开 / 另存为 / 删除<br>
        • 「打开素材文件夹」：资源管理器打开 temp_assets/</p>

        <h3>🌐 网址导航</h3>
        <p>• <b>主窗口</b>：分组管理 / 站点增删改 / 拖拽排序<br>
        • URL 自动补全 http:// 或 https://<br>
        • 点击「打开」按钮 → 系统默认浏览器打开链接<br>
        • 碎片工作台 URL 碎片右键 → 「添加至网址导航」<br>
        • <b>小卡片 Tab 4</b>：仅展示和跳转，编辑在主窗口</p>

        <h3>⚙️ 设置</h3>
        <p>• 主题切换（浅色/深色）<br>
        • 剪贴板历史上限<br>
        • 悬浮球自动隐藏秒数<br>
        • 悬浮球显示开关（可隐藏/显示悬浮球）</p>
        """)
        # 内联样式指定 color，确保富文本文字跟随主题
        content.setStyleSheet(
            f"font-size: 13px; line-height: 1.6; color: {text_color}; background: transparent;"
        )
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # 关闭按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        # 应用主题：主窗口 QSS + 对话框背景补充（QDialog/QScrollArea 跟随主题）
        qss = get_main_window_qss(self._theme)
        dialog_extra = (
            f"QDialog {{ background-color: {bg_color}; }}"
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QLabel { background: transparent; }"
        )
        dlg.setStyleSheet(qss + dialog_extra)

        dlg.finished.connect(lambda: setattr(self, '_help_dialog', None))

        # 主窗口的 F1 快捷键已设为 ApplicationShortcut，全局有效，
        # 对话框打开时按 F1 会触发 _toggle_help_dialog 关闭对话框，无需重复绑定

        # 使用非模态 show() 而非 exec()，避免阻塞父窗口事件循环导致 F1 快捷键失效
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ==================================================================
    # 无边框窗口拖动 + 边缘自由缩放
    # ==================================================================
    RESIZE_EDGE = 18  # 边缘缩放感应宽度（与阴影边距一致，透明边缘区可拖拽缩放）
    CORNER_SIZE = 24  # 四角对角线缩感应区（稍大于边缘，提升四角命中率）

    _CURSOR_MAP = {
        "left":         Qt.CursorShape.SizeHorCursor,
        "right":        Qt.CursorShape.SizeHorCursor,
        "top":          Qt.CursorShape.SizeVerCursor,
        "bottom":       Qt.CursorShape.SizeVerCursor,
        "top-left":     Qt.CursorShape.SizeFDiagCursor,
        "bottom-right": Qt.CursorShape.SizeFDiagCursor,
        "top-right":    Qt.CursorShape.SizeBDiagCursor,
        "bottom-left":  Qt.CursorShape.SizeBDiagCursor,
    }

    # ==================================================================
    # 子控件指针残留防护：遍历安装事件过滤器
    # ==================================================================
    def _install_cursor_filter(self):
        """为所有子控件递归安装事件过滤器，鼠标进入子控件时主动清除主窗口缩放指针。
        这是解决"缩放指针残留在按钮/列表等内容区控件上卡住不消失"的核心方案。"""
        def _recursive_install(widget: QWidget):
            widget.installEventFilter(self)
            widget.setMouseTracking(True)  # 子控件也开启鼠标跟踪，指针切换更实时
            for child in widget.findChildren(QWidget):
                _recursive_install(child)
        _recursive_install(self)

    def eventFilter(self, obj, event):
        """事件过滤器：鼠标进入任意子控件 → 清除主窗口的缩放指针残留"""
        etype = event.type()
        # 鼠标进入子控件 / 子控件内部移动 时，都清理一次主窗口指针
        if etype == QEvent.Type.Enter:
            self._clear_resize_cursor()
            # 导航按钮悬停切换页面
            page_index = obj.property("pageIndex")
            stack = getattr(self, "_stack", None)
            if page_index is not None and stack is not None and page_index != stack.currentIndex():
                self._switch_page(page_index)
        elif etype == QEvent.Type.MouseMove and obj is not self:
            # 子控件内部鼠标移动时，若主窗口还有缩放指针则清理
            if self.testAttribute(Qt.WidgetAttribute.WA_SetCursor):
                self._clear_resize_cursor()
        return super().eventFilter(obj, event)

    def _clear_resize_cursor(self):
        """安全清除主窗口上的缩放指针（带状态校验，避免重复调用）"""
        if self.testAttribute(Qt.WidgetAttribute.WA_SetCursor):
            # 非缩放拖动中才清除，避免缩放拖动过程中指针被误还原导致闪烁
            if not self._resizing:
                self.unsetCursor()

    # ==================================================================
    # 边缘缩放命中检测（改进版：更精准的判定 + 最大化快速短路）
    # ==================================================================
    def _edge_hit(self, pos) -> str:
        """判断位置是否落在窗口边缘缩放区。返回方向字符串，非边缘返回空串。

        精度改进：
        1. 最大化直接短路返回（之前已有，此处保留）
        2. 四角使用 CORNER_SIZE 稍大的命中区，提升对角线缩放命中率
        3. 先判断四角再判断四边，避免靠近四角时被四边先匹配导致方向错误
        4. 使用局部坐标与窗口尺寸严格比较，排除浮点数误差
        """
        if self.isMaximized():
            return ""  # 最大化时不允许边缘缩放
        e = self.RESIZE_EDGE
        c = self.CORNER_SIZE
        x, y = int(pos.x()), int(pos.y())
        w, h = self.width(), self.height()
        # 先判四角（命中区稍大，优先于四边）
        in_left = x <= c
        in_right = x >= w - c
        in_top = y <= c
        in_bottom = y >= h - c
        if in_top and in_left:
            return "top-left"
        if in_top and in_right:
            return "top-right"
        if in_bottom and in_left:
            return "bottom-left"
        if in_bottom and in_right:
            return "bottom-right"
        # 再判四边（标准宽度 e）
        if x <= e:
            return "left"
        if x >= w - e:
            return "right"
        if y <= e:
            return "top"
        if y >= h - e:
            return "bottom"
        return ""

    def _update_resize_cursor(self, pos):
        """悬停时根据边缘方向切换鼠标指针形状。

        改进：
        1. 进入非边缘区前先判断光标是否真正被主窗口设置过（WA_SetCursor）
        2. 子控件命中检测：若当前位置下方有子控件（非主窗口本身），直接清除缩放指针
        3. 保留 shape 去重逻辑，避免重复 setCursor 造成的 Windows 下指针抖动
        """
        # 若该位置下是子控件（通过 childAt 查），不显示缩放指针，直接清理并返回
        child = self.childAt(pos.toPoint())
        if child is not None and child is not self._container and child is not self:
            self._clear_resize_cursor()
            return
        edge = self._edge_hit(pos)
        if edge:
            shape = self._CURSOR_MAP[edge]
            # WA_SetCursor=True 表示主窗口设置过指针；否则 cursor() 返回的是默认继承值
            if not self.testAttribute(Qt.WidgetAttribute.WA_SetCursor) or self.cursor().shape() != shape:
                self.setCursor(shape)
        else:
            self._clear_resize_cursor()

    def _do_resize(self, global_pos):
        """按住边缘拖动：按全局位移计算新窗口几何（受最小尺寸约束）"""
        dx = global_pos.x() - self._resize_start_global.x()
        dy = global_pos.y() - self._resize_start_global.y()
        start = self._resize_start_geom
        x, y = start.x(), start.y()
        w, h = start.width(), start.height()
        edge = self._resizing
        if "right" in edge:
            w = max(self.MIN_WIDTH, w + dx)
        if "bottom" in edge:
            h = max(self.MIN_HEIGHT, h + dy)
        if "left" in edge:
            w = max(self.MIN_WIDTH, w - dx)
            x = start.right() + 1 - w  # 锁定右边界
        if "top" in edge:
            h = max(self.MIN_HEIGHT, h - dy)
            y = start.bottom() + 1 - h  # 锁定下边界
        self.setGeometry(x, y, w, h)

    def mousePressEvent(self, event):
        """左键按下：优先边缘缩放，其次标题栏拖动。按下时先清理一次残留指针。"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 开始交互前主动清一次指针：防止上次交互的指针状态未还原
            if not self._resizing:
                self._clear_resize_cursor()
            # 1. 边缘缩放区 → 开始自由缩放
            edge = self._edge_hit(event.position())
            if edge:
                self._resizing = edge
                self._resize_start_global = event.globalPosition().toPoint()
                self._resize_start_geom = self.geometry()
                # 缩放开始时强制设置一次指针，避免瞬时切到错误形状
                self.setCursor(self._CURSOR_MAP[edge])
                event.accept()
                return
            # 2. 标题栏区域 = 阴影边距 ~ 阴影边距 + 标题栏高度
            #    （最大化时边距为 0，动态计算避免内容区顶部误判为拖动）
            margin = 0 if self.isMaximized() else self.SHADOW_MARGIN
            y = event.position().y()
            if y <= self.TITLE_BAR_HEIGHT + margin:
                # 拖动窗口开始时：确保没有缩放指针残留
                self._clear_resize_cursor()
                if self.isMaximized():
                    # 最大化状态下按下标题栏 → 不立即还原窗口！
                    # 仅记录"待还原"状态，等 mouseMoveEvent 检测到真正拖动
                    # 才还原。这样双击（按下+双击事件）不会触发
                    # "还原→又最大化"的来回闪动（修复双击标题栏抖动卡死）
                    self._drag_pending_restore = True
                    self._drag_press_ratio = (event.position().x()
                                              / max(1, self.width()))
                self._dragging = True
                self._drag_offset = (event.globalPosition().toPoint()
                                     - self.frameGeometry().topLeft())
                event.accept()
            else:
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击标题栏：全屏/还原切换（边缘区不触发）"""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._edge_hit(event.position()):
                margin = 0 if self.isMaximized() else self.SHADOW_MARGIN
                y = event.position().y()
                if y <= self.TITLE_BAR_HEIGHT + margin:
                    self._toggle_maximize()
                    # 切换最大化后立即清理指针（最大化没有边缘缩放，防止残留）
                    QTimer.singleShot(0, self._clear_resize_cursor)
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        """拖动中：移动窗口 / 缩放窗口；悬停时：切换边缘指针。

        额外防护：鼠标未按住且有子控件时，强制清除主窗口上的缩放指针，
        防止从边缘快速滑入内容区时的指针残影。
        """
        if self._resizing and (event.buttons() & Qt.MouseButton.LeftButton):
            self._do_resize(event.globalPosition().toPoint())
            event.accept()
        elif self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            # 惰性还原：最大化窗口被真正拖动时才还原尺寸位置
            # （按下不动 / 双击时不还原，避免窗口大小来回跳变）
            if self._drag_pending_restore:
                self._drag_pending_restore = False
                self.showNormal()
                # 先恢复记忆几何（或默认尺寸），再把窗口挂到鼠标下方
                self._restore_normal_geometry()
                gx = event.globalPosition().x()
                gy = event.globalPosition().y()
                self.move(int(gx - self.width() * self._drag_press_ratio),
                          int(gy - self.TITLE_BAR_HEIGHT / 2))
                # 窗口跳转后重算拖动偏移，保证继续拖动跟手
                self._drag_offset = (event.globalPosition().toPoint()
                                     - self.frameGeometry().topLeft())
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            # 非拖动状态：更新指针，且若下方是子控件则额外清一次（双保险）
            self._update_resize_cursor(event.position())
            child = self.childAt(event.position().toPoint())
            if child is not None and child is not self._container and child is not self:
                self._clear_resize_cursor()
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """释放鼠标：结束拖动/缩放，立即清理指针。

        无论事件在哪个子控件上方，释放后都必须确保缩放指针被清除，
        这是解决"松开鼠标后指针还保持缩放形状"的关键一步。
        """
        released_resizing = bool(self._resizing)
        released_dragging = bool(self._dragging)
        if self._resizing:
            self._resizing = None
            event.accept()
        elif self._dragging:
            self._dragging = False
            # 未发生真正拖动就松开（如单击/双击标题栏）→ 取消待还原标记
            self._drag_pending_restore = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            return
        # 释放后清理指针：优先根据当前位置判断，若释放点在子控件上则无条件清
        if released_resizing or released_dragging:
            child = self.childAt(event.position().toPoint())
            if child is not None and child is not self._container and child is not self:
                self._clear_resize_cursor()
            else:
                self._update_resize_cursor(event.position())
            # 兜底：延迟 10ms 再清一次，处理 OS 级指针缓存导致的偶发残留
            QTimer.singleShot(10, self._clear_resize_cursor)

    def leaveEvent(self, event):
        """鼠标离开窗口：恢复默认指针。

        与原实现的区别：
        1. 调用统一的 _clear_resize_cursor() 而非直接 unsetCursor，
           确保不会在缩放拖动中途误清除导致指针抖动。
        2. 离开时若仍然 WA_SetCursor（极少数情况），再做一次强制 unset。
        """
        self._clear_resize_cursor()
        # 强制兜底：离开窗口后必须无自定义指针
        if self.testAttribute(Qt.WidgetAttribute.WA_SetCursor):
            # 仅当不在缩放拖动中才强制清除
            if not self._resizing:
                self.unsetCursor()
        super().leaveEvent(event)

    def enterEvent(self, event):
        """鼠标重新进入窗口：若有残留指针立即清除，根据当前位置重建正确形状。"""
        self._clear_resize_cursor()
        super().enterEvent(event)


# ====================================================================
# 碎片合并预览对话框（独立类）
# ====================================================================
class MergePreviewDialog(QDialog):
    """
    碎片合并预览对话框。

    作用：
      - 将多个碎片按选中顺序拼接成一段文本
      - 提供预览编辑区（用户可微调合并结果）
      - 两个去向：复制到剪贴板 / 存为一条新笔记
    """

    def __init__(self, fragments, note_manager, clipboard_monitor, parent=None):
        super().__init__(parent)
        self._fragments = fragments
        self._note_manager = note_manager
        self._clipboard_monitor = clipboard_monitor

        self.setWindowTitle("合并碎片预览")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(520, 420)

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 16)
        v.setSpacing(10)

        # 顶部信息
        info = QLabel(f"🔗 已选 {len(fragments)} 条碎片，合并后预览（可编辑）：")
        info.setObjectName("sectionLabel")
        v.addWidget(info)

        # 来源列表（紧凑显示）
        source_lines = []
        for i, f in enumerate(fragments, 1):
            icon = TYPE_ICONS.get(f.type, "📄")
            preview = f.preview(40)
            source_lines.append(f"{i}. {icon} {preview}")
        source_label = QLabel("\n".join(source_lines))
        source_label.setObjectName("hintLabel")
        source_label.setWordWrap(True)
        v.addWidget(source_label)

        # 预览编辑区（可编辑）
        self._preview_edit = QTextEdit()
        merged = "\n\n".join(f.content for f in fragments)
        self._preview_edit.setPlainText(merged)
        v.addWidget(self._preview_edit, 1)

        # 按钮区
        btns = QHBoxLayout()
        btns.addStretch()

        copy_btn = QPushButton("📋 复制到剪贴板")
        copy_btn.clicked.connect(self._on_copy)
        btns.addWidget(copy_btn)

        save_btn = QPushButton("💾 存为笔记")
        save_btn.setObjectName("secondaryBtn")
        save_btn.clicked.connect(self._on_save_note)
        btns.addWidget(save_btn)

        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryBtn")
        close_btn.clicked.connect(self.reject)
        btns.addWidget(close_btn)

        v.addLayout(btns)

    def _on_copy(self):
        """复制合并内容到剪贴板"""
        text = self._preview_edit.toPlainText()
        if self._clipboard_monitor:
            self._clipboard_monitor.put_text(text)
        QMessageBox.information(self, "已复制", "合并内容已复制到剪贴板。")

    def _on_save_note(self):
        """保存合并内容为一条新笔记"""
        text = self._preview_edit.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "提示", "合并内容为空，无法保存。")
            return
        if self._note_manager:
            self._note_manager.add_note(text)
        QMessageBox.information(self, "已保存", "合并内容已存为一条新笔记。")
        self.accept()

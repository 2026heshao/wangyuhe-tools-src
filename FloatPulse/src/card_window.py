# -*- coding: utf-8 -*-
"""
====================================================================
卡片弹窗模块  -  CardWindow
====================================================================
小卡片弹窗窗口（440×340），左侧微型 Tab 导航 + 右侧内容区。

Tab 列表（数字序号）：
  1. 📚 知识卡片  - 随机知识卡片，「下一张」切换
  2. 📋 日程任务  - 任务输入 + 列表，右键菜单管理
  3. 📝 临时笔记  - 单条便签，800ms 防抖自动保存
  4.  网址导航  - 平铺展示所有站点，点击跳转浏览器（锁定常驻，仅展示）

统一行为：
  - 鼠标离开「球+卡片」区域 → 自动关闭
  - 拖动卡片或悬浮球期间 → 不自动关闭
  - 记住上次关闭时的 Tab，下次弹出时恢复

特性：
  - 无系统原生标题栏 (FramelessWindowHint)
  - 始终置顶 (WindowStaysOnTopHint)
  - 半透明背景 + 大圆角容器 + 柔和阴影
  - 非交互区域可拖动
  - 右键卡片 → 退出菜单

依赖：
  - task_manager.TaskManager
  - note_manager.NoteManager
  - nav_manager.NavManager
====================================================================
"""

import html
import os
import random

from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QMenu, QToolButton,
    QStackedWidget, QListWidget, QListWidgetItem, QLineEdit, QDateEdit,
    QDialog, QDialogButtonBox, QFormLayout, QTextEdit, QScrollArea,
    QFrame, QSizePolicy, QGridLayout, QSystemTrayIcon, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, QDate, QPoint, QSize, pyqtSignal, QVariantAnimation, QEasingCurve, QRectF, QMimeData, QEvent
from PyQt6.QtGui import QColor, QAction, QDesktopServices, QPainter, QBrush, QPainterPath, QPixmap, QFontMetrics, QFont, QIcon, QDrag
from PyQt6.QtCore import QUrl

from src.task_manager import TaskManager
from src.note_manager import NoteManager
from src.nav_manager import NavManager
from src.theme import get_card_window_qss, get_menu_qss


# ====================================================================
# 辅助函数：获取可用屏幕几何（判空防止无屏幕环境崩溃）
# ====================================================================
def _get_screen_geometry():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QRect
    screen = QApplication.primaryScreen()
    if screen is not None:
        return screen.availableGeometry()
    return QRect(0, 0, 1920, 1080)


# Tab 定义（纯图标，无数字）
_TABS = [
    ("🧩", "碎片"),
    ("💡", "知识卡片"),
    ("📋", "日程任务"),
    ("📝", "临时笔记"),
    ("🌐", "网址导航"),
    ("📎", "临时素材"),
    ("🚀", "软件导航"),
]
_TAB_KEYS = ["fragment", "card", "task", "note", "nav", "asset", "app"]

# 左侧 Tab 栏尺寸（固定宽度，不再展开收起）
_TAB_BAR_WIDTH = 48         # 固定宽度
_TAB_BTN_SIZE = 40          # 图标按钮尺寸
_TAB_INDICATOR_W = 3        # 选中竖条指示器宽度
_TAB_INDICATOR_H = 24       # 选中竖条指示器高度


# ====================================================================
# 选中 Tab 指示器（圆角竖条，通过 move 驱动滑动）
# ====================================================================
class _TabIndicator(QWidget):
    """左侧选中指示器：3px 宽圆角竖条"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(91, 192, 190)   # 默认主色（浅主题 #5BC0BE）

    def set_indicator_y(self, y: int):
        """直接设置指示器 Y 位置（无动画）"""
        self.move(0, int(y))
        self.update()

    def get_indicator_y(self) -> int:
        """获取当前指示器 Y 位置"""
        return self.y()

    def set_color(self, color: QColor):
        """设置指示器颜色（主题切换时调用）"""
        self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 绘制圆角竖条
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 2, 2)
        painter.setBrush(QBrush(self._color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)


# ====================================================================
# 素材项组件：支持拖拽出去（拖拽时携带文件路径）
# ====================================================================
class _AssetItemWidget(QWidget):
    """单个素材项，显示缩略图/图标 + 文件名，支持拖拽取出"""

    DOUBLE_CLICK_THRESHOLD = 300  # 双击判定时间（毫秒）

    def __init__(self, asset, parent=None):
        super().__init__(parent)
        self._asset = asset
        self._drag_start = None
        self._last_click_time = 0
        self._is_valid = os.path.exists(asset.stored_path) if asset else False

        self.setFixedSize(72, 84)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._is_valid
                       else Qt.CursorShape.ForbiddenCursor)
        self.setToolTip(self._build_tooltip())

        v = QVBoxLayout(self)
        v.setContentsMargins(2, 4, 2, 2)
        v.setSpacing(2)

        # 图标/缩略图区域
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(64, 64)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setObjectName("assetIcon")
        self._load_icon()
        v.addWidget(self._icon_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 文件名
        name = asset.original_name if asset else ""
        if len(name) > 10:
            name = name[:9] + "…"
        self._name_label = QLabel(name)
        self._name_label.setObjectName("assetName")
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setWordWrap(False)
        v.addWidget(self._name_label)

        if not self._is_valid:
            self._name_label.setStyleSheet("color: #999;")

    def _build_tooltip(self):
        if not self._asset:
            return ""
        tip = f"{self._asset.original_name}\n"
        tip += f"大小: {self._asset.size_display()}\n"
        tip += f"收录: {self._asset.added_time}\n"
        tip += "拖拽取出 | 双击打开 | 右键菜单"
        if not self._is_valid:
            tip += "\n⚠ 文件已失效"
        return tip

    def _load_icon(self):
        """加载缩略图或文件类型图标"""
        if not self._is_valid:
            self._icon_label.setText("⚠️")
            self._icon_label.setStyleSheet("font-size: 24px; color: #999;")
            return

        if self._asset.is_image:
            pix = QPixmap(self._asset.stored_path)
            if not pix.isNull():
                # 保持比例缩放到 64×64
                pix = pix.scaled(
                    64, 64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._icon_label.setPixmap(pix)
            else:
                self._icon_label.setText("🖼️")
                self._icon_label.setStyleSheet("font-size: 28px;")
        else:
            # 非图片文件：根据扩展名显示图标
            ext = os.path.splitext(self._asset.original_name)[1].lower()
            icon_map = {
                ".txt": "📄", ".pdf": "📕", ".doc": "📘", ".docx": "📘",
                ".xls": "📗", ".xlsx": "📗", ".ppt": "📙", ".pptx": "📙",
                ".zip": "📦", ".rar": "📦", ".7z": "📦",
                ".mp3": "🎵", ".wav": "🎵", ".mp4": "🎬", ".avi": "🎬",
                ".py": "🐍", ".js": "📜", ".json": "📋",
            }
            icon = icon_map.get(ext, "📄")
            self._icon_label.setText(icon)
            self._icon_label.setStyleSheet("font-size: 28px;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._is_valid:
            self._drag_start = event.pos()
        # 双击检测
        if event.button() == Qt.MouseButton.LeftButton:
            import time
            now = int(time.time() * 1000)
            if now - self._last_click_time < self.DOUBLE_CLICK_THRESHOLD:
                self._on_double_click()
                self._last_click_time = 0
            else:
                self._last_click_time = now
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._drag_start is None or not self._is_valid:
            return
        if (event.pos() - self._drag_start).manhattanLength() < 10:
            return
        # 构造拖拽
        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(self._asset.stored_path)])
        mime.setText(self._asset.stored_path)
        drag.setMimeData(mime)
        # 图片设置拖拽预览
        if self._asset.is_image:
            preview = QPixmap(self._asset.stored_path)
            if not preview.isNull():
                drag.setPixmap(preview.scaled(
                    80, 80,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
                drag.setHotSpot(QPoint(40, 40))
        drag.exec(Qt.DropAction.CopyAction)
        self._drag_start = None

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def _on_double_click(self):
        """双击用系统默认程序打开"""
        if self._is_valid:
            try:
                os.startfile(self._asset.stored_path)
            except Exception:
                try:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(self._asset.stored_path))
                except Exception:
                    pass

    def contextMenuEvent(self, event):
        """右键菜单"""
        if not self._asset:
            return
        menu = QMenu(self)
        menu.setStyleSheet(get_menu_qss("light"))

        act_open = menu.addAction("📂 打开")
        act_copy = menu.addAction("📋 复制路径")
        menu.addSeparator()
        act_delete = menu.addAction("🗑 删除")

        action = menu.exec(event.globalPos())
        if action == act_open:
            self._on_double_click()
        elif action == act_copy:
            from PyQt6.QtWidgets import QApplication
            cb = QApplication.clipboard()
            cb.setText(self._asset.stored_path)
        elif action == act_delete:
            # 通过顶层 CardWindow 处理数据层删除
            top = self.window()
            if isinstance(top, CardWindow):
                top._delete_asset(self._asset.asset_id)


# ====================================================================
# 卡片弹窗类
# ====================================================================
class CardWindow(QWidget):

    data_changed = pyqtSignal(str)
    request_quit = pyqtSignal()
    card_moved = pyqtSignal()
    card_closed = pyqtSignal()   # 保持显示模式下用户点击关闭按钮

    WINDOW_WIDTH = 440
    WINDOW_HEIGHT = 340

    def __init__(self, theme: str = "light"):
        super().__init__()
        self._theme = theme
        self._cards = []
        self._current_index = -1
        self._task_manager = None
        self._note_manager = None
        self._nav_manager = None
        self._config_manager = None
        self._asset_manager = None
        self._fragment_manager = None
        self._current_note_id = None
        self._loading_note = False
        self._last_mode = "fragment"
        self._dragging = False
        self._drag_offset = QPoint()
        self._note_save_timer = QTimer(self)
        self._note_save_timer.setSingleShot(True)
        self._note_save_timer.setInterval(800)
        self._note_save_timer.timeout.connect(self._on_save_note)

        # 指示器初始化守卫（防止首次显示时动画到错误位置）
        self._indicator_ready = False

        self._init_window()
        self._init_ui()
        self._init_context_menu()

    # ---------------- 初始化 ----------------
    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

    def _init_ui(self):
        self._container = QWidget(self)
        self._container.setObjectName("cardContainer")
        self._container.setGeometry(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        outer = QHBoxLayout(self._container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- 左侧固定图标导航栏 + 滑动指示器 ----
        self._side_tab = QWidget()
        self._side_tab.setObjectName("sideTabBar")
        self._side_tab.setFixedWidth(_TAB_BAR_WIDTH)
        side_v = QVBoxLayout(self._side_tab)
        side_v.setContentsMargins(0, 12, 0, 12)
        side_v.setSpacing(4)

        # 选中竖条指示器（用 QWidget + paintEvent 实现平滑滑动）
        self._indicator = _TabIndicator(self._side_tab)
        self._indicator.setFixedSize(_TAB_INDICATOR_W, _TAB_INDICATOR_H)
        self._indicator.raise_()

        # 图标按钮（始终显示，固定布局）
        self._tab_buttons = []
        for i, (icon, name) in enumerate(_TABS):
            btn = QPushButton(icon)
            btn.setObjectName("sideTabIconBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(name)
            btn.setFixedSize(_TAB_BTN_SIZE, _TAB_BTN_SIZE)
            key = _TAB_KEYS[i]
            # 鼠标悬停即切换 Tab（不再依赖点击）
            btn.setProperty("tabKey", key)
            btn.installEventFilter(self)
            self._tab_buttons.append(btn)
            side_v.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        side_v.addStretch()

        # 指示器滑动动画（QVariantAnimation + valueChanged 回调，不依赖 pyqtProperty）
        self._indicator_anim = QVariantAnimation(self)
        self._indicator_anim.setDuration(220)
        self._indicator_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._indicator_anim.valueChanged.connect(self._indicator.set_indicator_y)

        outer.addWidget(self._side_tab)

        # ---- 右侧内容区 ----
        content_area = QWidget()
        content_area.setObjectName("contentArea")
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(16, 14, 16, 14)
        content_layout.setSpacing(8)

        self._stack = QStackedWidget()
        content_layout.addWidget(self._stack, 1)

        # 页面0：碎片（新增）
        self._stack.addWidget(self._build_fragment_page())
        # 页面1：知识卡片
        self._stack.addWidget(self._build_card_page())
        # 页面2：日程任务
        self._stack.addWidget(self._build_task_page())
        # 页面3：临时笔记
        self._stack.addWidget(self._build_note_page())
        # 页面4：网址导航
        self._stack.addWidget(self._build_nav_page())
        # 页面5：临时素材
        self._stack.addWidget(self._build_asset_page())
        # 页面6：软件导航（小卡片内嵌只读浏览页，图标+名称，点击启动）
        self._stack.addWidget(self._build_app_page())

        # 给所有页面铺实色背景：grab() 快照不再黑底，切页也不透黑
        self._apply_pages_background()

        outer.addWidget(content_area, 1)

        # 保持显示模式下的关闭按钮（右上角，默认隐藏）
        self._close_btn = QPushButton("×", self._container)
        self._close_btn.setObjectName("cardCloseBtn")
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip("关闭卡片")
        self._close_btn.clicked.connect(self._on_close_button_clicked)
        self._close_btn.setVisible(False)

        self._apply_style()

        # 初始化指示器颜色（匹配主题主色）
        from src.theme import get_colors
        colors = get_colors(self._theme)
        self._indicator.set_color(QColor(colors["primary"]))

        # 柔和悬浮阴影：宽模糊 + 低透明度 + 下偏置，营造 Web 卡片悬浮感
        shadow = QGraphicsDropShadowEffect(self._container)
        shadow.setBlurRadius(42)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 10)
        self._container.setGraphicsEffect(shadow)

        self._switch_mode("fragment")

    # ==================================================================
    # 碎片页面（小卡片：仅复制 + 删除 + 拖拽复制）
    # ==================================================================
    def _build_fragment_page(self):
        """构建碎片工作台小卡片页面"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # 滚动区域包裹碎片列表（仅纵向滚动，禁止横向滚动条）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("fragScrollArea")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_widget = QWidget()
        scroll_v = QVBoxLayout(scroll_widget)
        scroll_v.setContentsMargins(0, 0, 0, 0)
        scroll_v.setSpacing(0)

        self._frag_content_layout = QVBoxLayout()
        self._frag_content_layout.setSpacing(8)
        scroll_v.addLayout(self._frag_content_layout)
        scroll_v.addStretch()
        scroll.setWidget(scroll_widget)
        v.addWidget(scroll)
        return page

    def _refresh_fragment_page(self):
        """刷新碎片列表：每条显示内容预览 + 复制/删除按钮"""
        # 清除旧内容
        while self._frag_content_layout.count():
            item = self._frag_content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._fragment_manager:
            empty = QLabel("暂无碎片")
            empty.setObjectName("hintLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._frag_content_layout.addWidget(empty)
            return

        fragments = self._fragment_manager.get_all_fragments()
        if not fragments:
            empty = QLabel("暂无碎片，复制文本即可收集")
            empty.setObjectName("hintLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._frag_content_layout.addWidget(empty)
            return

        # 取最近 20 条显示（小卡片不宜过多）
        display_frags = fragments[:20]

        # 预览文本可用宽度：内容区360 - 按钮(40×2) - 间距(6×2) - 行边距(左4右12) - 滚动条预留12
        text_width = self.WINDOW_WIDTH - _TAB_BAR_WIDTH - 32 - 40 * 2 - 6 * 2 - 4 - 12 - 12
        font = QFont("Microsoft YaHei")
        font.setPixelSize(14)  # 与 QSS 中 fragPreview 字号一致
        fm = QFontMetrics(font)

        for frag in display_frags:
            row = QWidget()
            row.setObjectName("fragItemRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 2, 12, 2)  # 右侧多留空间，防止删除按钮被卡片边缘遮挡
            row_layout.setSpacing(6)

            # 内容预览（按可用宽度省略截断，允许显示不完全）
            preview = fm.elidedText(
                frag.preview(max_len=120),
                Qt.TextElideMode.ElideRight, text_width)
            label = QLabel(preview)
            label.setObjectName("fragPreview")
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            row_layout.addWidget(label)

            # 复制按钮
            copy_btn = QPushButton("复制")
            copy_btn.setObjectName("fragCopyBtn")
            copy_btn.setFixedSize(40, 24)
            copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.setToolTip("复制碎片内容")
            copy_btn.clicked.connect(lambda checked=False, c=frag.content: self._copy_fragment(c))
            row_layout.addWidget(copy_btn)

            # 删除按钮
            del_btn = QPushButton("删除")
            del_btn.setObjectName("fragDelBtn")
            del_btn.setFixedSize(40, 24)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setToolTip("删除此碎片")
            del_btn.clicked.connect(lambda checked=False, fid=frag.fragment_id: self._delete_fragment(fid))
            row_layout.addWidget(del_btn)

            self._frag_content_layout.addWidget(row)

    def _copy_fragment(self, content: str):
        """复制碎片内容到剪贴板"""
        QApplication.clipboard().setText(content)

    def _delete_fragment(self, fragment_id: int):
        """删除碎片并刷新列表"""
        if self._fragment_manager:
            self._fragment_manager.delete_fragment(fragment_id)
            self._refresh_fragment_page()
            self.data_changed.emit("fragment")

    def _flash_tray_msg(self, msg: str):
        """通过托盘图标显示短暂提示（如果存在）"""
        try:
            app = QApplication.instance()
            if app:
                for w in app.topLevelWidgets():
                    if isinstance(w, QSystemTrayIcon):
                        w.showMessage("生活悬浮球", msg, QSystemTrayIcon.MessageIcon.NoIcon, 1500)
                        break
        except Exception:
            pass

    # ==================================================================
    # 知识卡片页面
    # ==================================================================
    def _build_card_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(10)

        self._title_label = QLabel("💡 知识卡片")
        self._title_label.setObjectName("titleLabel")
        v.addWidget(self._title_label)

        self._content_label = QLabel()
        self._content_label.setObjectName("contentLabel")
        self._content_label.setWordWrap(True)
        self._content_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._content_label.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self._content_label, 1)

        self._next_btn = QPushButton("下一张  ➜")
        self._next_btn.setObjectName("nextBtn")
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self.next_card)
        v.addWidget(self._next_btn, 0, Qt.AlignmentFlag.AlignRight)
        return page

    # ==================================================================
    # 日程任务页面
    # ==================================================================
    def _build_task_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(8)

        input_bar = QHBoxLayout()
        input_bar.setSpacing(6)

        self._task_title_input = QLineEdit()
        self._task_title_input.setObjectName("taskInput")
        self._task_title_input.setPlaceholderText("输入任务标题，回车添加...")
        self._task_title_input.returnPressed.connect(self._on_add_task)

        self._task_deadline = QDateEdit()
        self._task_deadline.setObjectName("taskDate")
        self._task_deadline.setCalendarPopup(True)
        self._task_deadline.setDisplayFormat("yyyy-MM-dd")
        self._task_deadline.setDate(QDate.currentDate())
        self._task_deadline.setFixedWidth(120)

        self._task_add_btn = QPushButton("添加")
        self._task_add_btn.setObjectName("taskAddBtn")
        self._task_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._task_add_btn.clicked.connect(self._on_add_task)

        input_bar.addWidget(self._task_title_input, 1)
        input_bar.addWidget(self._task_deadline)
        input_bar.addWidget(self._task_add_btn)
        v.addLayout(input_bar)

        self._task_list = QListWidget()
        self._task_list.setObjectName("taskList")
        self._task_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._task_list.customContextMenuRequested.connect(self._on_task_context_menu)
        v.addWidget(self._task_list, 1)

        hint = QLabel("右键任务：标记完成 / 编辑 / 删除")
        hint.setObjectName("hintLabel")
        v.addWidget(hint)
        return page

    # ==================================================================
    # 临时笔记页面
    # ==================================================================
    def _build_note_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(8)

        self._note_edit = QTextEdit()
        self._note_edit.setObjectName("noteEdit")
        self._note_edit.setPlaceholderText("临时笔记：随手记录，自动保存...")
        self._note_edit.textChanged.connect(self._on_note_text_changed)
        v.addWidget(self._note_edit, 1)
        return page

    # ==================================================================
    # 网址导航页面（锁定常驻，仅跳转展示）
    # ==================================================================
    def _build_nav_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(6)

        self._nav_title = QLabel("🌐 网址导航")
        self._nav_title.setObjectName("titleLabel")
        v.addWidget(self._nav_title)

        # 可滚动区域展示分组和站点（仅纵向滚动，禁止横向滚动条）
        self._nav_scroll = QScrollArea()
        self._nav_scroll.setWidgetResizable(True)
        self._nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._nav_scroll.setObjectName("navScroll")
        self._nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._nav_content = QWidget()
        self._nav_content.setObjectName("navContent")
        self._nav_content_layout = QVBoxLayout(self._nav_content)
        self._nav_content_layout.setContentsMargins(0, 0, 0, 0)
        self._nav_content_layout.setSpacing(8)
        self._nav_scroll.setWidget(self._nav_content)

        v.addWidget(self._nav_scroll, 1)

        hint = QLabel("点击站点用浏览器打开 | 编辑请打开主窗口")
        hint.setObjectName("hintLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(hint)

        return page

    def _refresh_nav_page(self):
        """刷新网址导航页面显示（不分分组，平铺所有站点）
        流式布局：短标题按钮保持固定宽度（一行3个），
        长标题按钮自适应加宽，该行放不下自动换行，窗口宽度不变。
        """
        # 清除旧内容
        while self._nav_content_layout.count():
            item = self._nav_content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._nav_manager:
            empty = QLabel("暂无网址，请在主窗口添加")
            empty.setObjectName("hintLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._nav_content_layout.addWidget(empty)
            return

        sites = self._nav_manager.get_all_sites_flat()
        if not sites:
            empty = QLabel("暂无网址，请在主窗口添加")
            empty.setObjectName("hintLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._nav_content_layout.addWidget(empty)
            return

        # 计算可用宽度：卡片宽440 - 侧栏48 - 内容区左右margin各16 = 360
        available_width = self.WINDOW_WIDTH - _TAB_BAR_WIDTH - 32
        cols = 3
        spacing = 6
        default_btn_w = (available_width - spacing * (cols - 1)) // cols

        # 按钮字体度量（与 QSS 中 navSiteBtn 的 13px 一致）
        font = QFont("Microsoft YaHei")
        font.setPixelSize(13)
        fm = QFontMetrics(font)

        # 创建按钮：短标题用固定宽度，长标题自适应加宽（上限为一整行，防止横向溢出）
        btn_infos = []
        for site in sites:
            btn = QPushButton(site.title)
            btn.setObjectName("navSiteBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(site.url)
            btn.clicked.connect(lambda checked=False, url=site.url: self._open_url(url))
            text_w = fm.horizontalAdvance(site.title) + 28  # padding 12×2 + border 2
            btn_w = min(max(default_btn_w, text_w), available_width)
            btn.setFixedWidth(btn_w)
            btn_infos.append((btn, btn_w))

        # 流式布局：逐个排列，放不下换行
        grid_container = QWidget()
        grid_container.setObjectName("navContent")
        outer_v = QVBoxLayout(grid_container)
        outer_v.setContentsMargins(0, 0, 0, 0)
        outer_v.setSpacing(spacing)

        row = QHBoxLayout()
        row.setSpacing(spacing)
        row_width = 0
        for btn, w in btn_infos:
            extra = spacing if row.count() > 0 else 0
            if row.count() > 0 and row_width + extra + w > available_width:
                # 当前行放不下 → 换行
                outer_v.addLayout(row)
                row = QHBoxLayout()
                row.setSpacing(spacing)
                row_width = 0
                extra = 0
            row.addWidget(btn)
            row_width += extra + w
        if row.count() > 0:
            outer_v.addLayout(row)

        self._nav_content_layout.addWidget(grid_container)
        self._nav_content_layout.addStretch()

    def _open_url(self, url: str):
        """用系统默认浏览器打开 URL（优先 os.startfile，回退 QDesktopServices）"""
        if not url:
            return
        # 优先使用 os.startfile（Windows 系统级打开，更稳定）
        try:
            os.startfile(url)
            return
        except Exception:
            pass
        # 回退到 QDesktopServices
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception:
            pass

    # ==================================================================
    # 软件导航页面（小卡片内嵌只读浏览：图标 + 名称，点击启动）
    # ==================================================================
    def _build_app_page(self):
        """
        构建软件导航小卡片页面。

        - 只读浏览：与主窗口 AppLauncherPage 共用同一份 config["apps"] 数据
        - 仅显示软件图标 + 软件名称（QToolButton 文字在图标下方）
        - 点击卡片 → 调用公共 launch_app() 异步启动（含 740 提权处理）
        - exe 失效的条目置灰禁用
        - 新增/编辑/删除仍只在主窗口导航页完成，本页无任何管理入口
        """
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(6)

        self._app_title = QLabel("🚀 软件导航")
        self._app_title.setObjectName("titleLabel")
        v.addWidget(self._app_title)

        # 可滚动区域展示软件网格（仅纵向滚动）
        self._app_scroll = QScrollArea()
        self._app_scroll.setWidgetResizable(True)
        self._app_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._app_scroll.setObjectName("appScroll")
        self._app_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._app_content = QWidget()
        self._app_content.setObjectName("appContent")
        self._app_grid = QGridLayout(self._app_content)
        self._app_grid.setContentsMargins(0, 0, 4, 0)
        self._app_grid.setSpacing(6)
        # 网格从左上角开始排列：列不拉伸铺满容器宽度，
        # 按钮按行从左到右、从上到下逐一排列（修复居中/散开问题）
        self._app_grid.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._app_scroll.setWidget(self._app_content)

        v.addWidget(self._app_scroll, 1)

        hint = QLabel("点击卡片启动软件 | 编辑请打开主窗口")
        hint.setObjectName("hintLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(hint)

        return page

    def _refresh_app_page(self):
        """刷新软件导航小卡片页面：重读 config apps 并重建网格。"""
        # 清空旧网格内容
        while self._app_grid.count():
            item = self._app_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 数据来源：宿主 ConfigManager（与主窗口导航页共用）
        apps = []
        if self._config_manager:
            raw = self._config_manager.get("apps", [])
            if isinstance(raw, list):
                apps = raw

        if not apps:
            empty = QLabel("暂无软件，请在主窗口软件导航中添加")
            empty.setObjectName("hintLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._app_grid.addWidget(empty, 0, 0)
            return

        # 图标/名称工具来自 widget_app_launcher（与主窗口卡片同一套）
        from src.widget_app_launcher import (
            extract_exe_icon, load_icon_pixmap, draw_placeholder_icon, launch_app,
        )

        # 小卡片内容区可用宽度：440 - 侧栏48 - 内容边距32 - 内层边距8 ≈ 352
        btn_size = 76
        available = self.WINDOW_WIDTH - _TAB_BAR_WIDTH - 40
        cols = max(1, available // (btn_size + 6))

        icon_px = 36  # 小卡片图标尺寸（小于主窗口）

        placed = 0  # 实际放置计数（非法条目跳过不留洞）
        for app in apps:
            # 容错：字段残缺自动补默认（禁止闪退）
            if not isinstance(app, dict):
                continue
            name = str(app.get("name") or "未命名")
            exe_path = str(app.get("exe_path") or "")
            icon_path = str(app.get("icon_path") or "")
            valid = bool(exe_path) and os.path.exists(exe_path)

            # 图标：自定义图标 > exe 内嵌图标 > 占位图标
            pixmap = None
            if icon_path and os.path.exists(icon_path):
                pixmap = load_icon_pixmap(icon_path, icon_px)
            if pixmap is None or pixmap.isNull():
                pixmap = extract_exe_icon(exe_path, icon_px)
            if pixmap is None or pixmap.isNull():
                pixmap = draw_placeholder_icon(icon_px)

            btn = QToolButton()
            btn.setObjectName("appLaunchBtn")
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(icon_px, icon_px))
            btn.setIcon(QIcon(pixmap))
            # 名称过长截断（超6字符省略）
            display = name if len(name) <= 6 else name[:5] + "…"
            btn.setText(display)
            btn.setFixedSize(btn_size, btn_size)
            btn.setToolTip(f"{name}\n{exe_path}")

            if valid:
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(
                    lambda checked=False, a=dict(app): launch_app(a, parent=self)
                )
            else:
                # exe 失效：置灰禁用，悬浮提示说明原因
                btn.setEnabled(False)
                btn.setToolTip(f"{name}\n{exe_path}\n⚠ 可执行文件不存在")

            self._app_grid.addWidget(btn, placed // cols, placed % cols)
            placed += 1

    # ==================================================================
    # 临时素材页面（网格布局，支持拖拽取出）
    # ==================================================================
    def _build_asset_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(6)

        # 顶部标题 + 计数
        header = QHBoxLayout()
        self._asset_title = QLabel("📎 临时素材")
        self._asset_title.setObjectName("titleLabel")
        header.addWidget(self._asset_title)
        header.addStretch()
        self._asset_count_label = QLabel("共 0 个")
        self._asset_count_label.setObjectName("hintLabel")
        header.addWidget(self._asset_count_label)
        v.addLayout(header)

        # 可滚动区域
        self._asset_scroll = QScrollArea()
        self._asset_scroll.setWidgetResizable(True)
        self._asset_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._asset_scroll.setObjectName("assetScroll")

        self._asset_content = QWidget()
        self._asset_content.setObjectName("assetContent")
        self._asset_content_layout = QVBoxLayout(self._asset_content)
        self._asset_content_layout.setContentsMargins(0, 0, 0, 0)
        self._asset_content_layout.setSpacing(8)
        self._asset_scroll.setWidget(self._asset_content)

        v.addWidget(self._asset_scroll, 1)

        hint = QLabel("拖拽素材到任意位置即可取出 | 双击打开 | 右键菜单")
        hint.setObjectName("hintLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(hint)

        return page

    def _refresh_asset_page(self):
        """刷新临时素材页面"""
        # 清除旧内容
        while self._asset_content_layout.count():
            item = self._asset_content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        if not self._asset_manager:
            empty = QLabel("暂无素材，拖文件到悬浮球收录")
            empty.setObjectName("hintLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._asset_content_layout.addWidget(empty)
            self._asset_count_label.setText("共 0 个")
            return

        assets = self._asset_manager.get_all_assets()
        if not assets:
            empty = QLabel("暂无素材，拖文件到悬浮球收录")
            empty.setObjectName("hintLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._asset_content_layout.addWidget(empty)
            self._asset_count_label.setText("共 0 个")
            return

        # 网格布局：每行 4 个
        grid_container = QWidget()
        grid_container.setObjectName("assetGrid")
        grid = QGridLayout(grid_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        cols = 4
        for i, asset in enumerate(assets):
            item_widget = _AssetItemWidget(asset)
            grid.addWidget(item_widget, i // cols, i % cols)
        # 补齐末行空白，让网格居中对齐
        total = len(assets)
        last_row = (total - 1) // cols
        if total % cols != 0:
            for j in range(total % cols, cols):
                placeholder = QWidget()
                placeholder.setFixedSize(72, 84)
                grid.addWidget(placeholder, last_row, j)

        self._asset_content_layout.addWidget(grid_container)
        self._asset_content_layout.addStretch()
        self._asset_count_label.setText(f"共 {total} 个")

    @staticmethod
    def _clear_layout(layout):
        """递归清除布局中的所有项"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                CardWindow._clear_layout(item.layout())

    def _delete_asset(self, asset_id: int):
        """删除素材（由 _AssetItemWidget 右键菜单调用）"""
        if not self._asset_manager:
            return
        if self._asset_manager.delete_asset(asset_id):
            self._refresh_asset_page()
            self.data_changed.emit("asset")

    # ---------------- 样式 ----------------
    def _apply_pages_background(self):
        """给 QStackedWidget 内所有页面铺实色背景。

        页面默认是透明 QWidget，在 WA_TranslucentBackground 无边框窗口里：
          - grab() 快照会得到黑底（导致转场黑色闪屏）；
          - 切页瞬间 contentArea/stack 透明，透出黑色。
        用 autoFillBackground + palette 给页面实色底，颜色与半透明容器 card_bg 一致。
        """
        from src.theme import get_colors
        solid = QColor(get_colors(self._theme)["card_bg_solid"])
        stack = getattr(self, "_stack", None)
        if stack is None:
            return
        for i in range(stack.count()):
            page = stack.widget(i)
            if page is None:
                continue
            page.setAutoFillBackground(True)
            pal = page.palette()
            pal.setColor(pal.ColorRole.Window, solid)
            page.setPalette(pal)

    def _apply_style(self):
        self._container.setStyleSheet(get_card_window_qss(self._theme))

    def apply_theme(self, theme_name: str):
        if theme_name not in ("light", "dark"):
            return
        if theme_name == self._theme:
            return
        self._theme = theme_name
        self._apply_style()
        self._apply_pages_background()
        self._menu.setStyleSheet(get_menu_qss(self._theme))
        # 同步指示器颜色
        from src.theme import get_colors
        colors = get_colors(theme_name)
        self._indicator.set_color(QColor(colors["primary"]))

    def showEvent(self, event):
        """窗口显示后初始化指示器位置，并刷新当前页数据"""
        super().showEvent(event)
        # 延迟一帧，确保布局完成后再计算位置
        QTimer.singleShot(0, self._init_indicator_position)
        # 刷新当前页数据（确保展开时显示最新内容）
        mode = getattr(self, '_last_mode', 'card')
        if mode == "fragment":
            self._refresh_fragment_page()
        elif mode == "task":
            self._refresh_task_list()
        elif mode == "note":
            self._load_temp_note()
        elif mode == "nav":
            self._refresh_nav_page()
        elif mode == "asset":
            self._refresh_asset_page()
        elif mode == "app":
            self._refresh_app_page()

    def _init_context_menu(self):
        self._menu = QMenu(self)
        self._menu.setStyleSheet(get_menu_qss(self._theme))
        exit_action = QAction("退出程序", self._menu)
        exit_action.triggered.connect(self._request_quit)
        self._menu.addAction(exit_action)

    def contextMenuEvent(self, event):
        self._menu.exec(event.globalPos())

    def eventFilter(self, obj, event):
        """Tab 按钮悬停切换：鼠标进入按钮即切换到对应模式。"""
        if event.type() == QEvent.Type.Enter:
            key = obj.property("tabKey")
            if key and key != getattr(self, "_last_mode", None):
                self._switch_mode(key)
        return super().eventFilter(obj, event)

    # ---------------- 模式切换 ----------------
    def _switch_mode(self, mode: str):
        """切换 Tab 模式（带水平滑入淡入淡出转场）"""
        if mode != "note":
            self._note_save_timer.stop()
        self._last_mode = mode

        try:
            idx = _TAB_KEYS.index(mode)
        except ValueError:
            idx = 0

        # 更新 Tab 按钮选中状态
        for i, btn in enumerate(self._tab_buttons):
            btn.setChecked(i == idx)

        # 滑动指示器到目标位置
        self._move_indicator_to(idx)

        old_idx = self._stack.currentIndex()

        # 窗口尚未显示时 grab() 抓不到内容，直接切换不做转场
        if idx != old_idx and self.isVisible():
            # 先刷新新页内容，确保快照与真实页面一致
            self._apply_mode_init(mode)
            self._animate_page_transition(old_idx, idx)
        else:
            self._stack.setCurrentIndex(idx)
            self._apply_mode_init(mode)

    def _apply_mode_init(self, mode: str):
        """模式切换标签的内容初始化（新页可见后调用）"""
        if mode == "fragment":
            self._refresh_fragment_page()
        elif mode == "task":
            self._refresh_task_list()
        elif mode == "note":
            self._load_temp_note()
        elif mode == "nav":
            self._refresh_nav_page()
        elif mode == "asset":
            self._refresh_asset_page()
        elif mode == "app":
            self._refresh_app_page()

    def _finalize_page_transition(self):
        """清理上一次转场遗留的覆盖层，避免快速连续点击时叠加残留。"""
        for label in getattr(self, "_trans_labels", []):
            # 先隐藏再延迟删除，绝不 setParent(None)（会顶成独立窗口闪现黑框）
            label.hide()
            label.deleteLater()
        self._trans_labels = []
        for eff in getattr(self, "_trans_effects", []):
            eff.deleteLater()
        self._trans_effects = []
        anim = getattr(self, "_page_transition_anim", None)
        if anim is not None:
            try:
                anim.stop()
            except Exception:
                pass
            anim.deleteLater()
            self._page_transition_anim = None

    def _animate_page_transition(self, old_idx: int, new_idx: int):
        """
        Tab 页水平滑入淡入转场（单新页快照覆盖法）。

        关键：动画期间底层保持旧页不动，只让「新页快照」从右侧滑入并淡入，
        直到动画结束才真正 setCurrentIndex 切到新页。这样：
          - 不再有「底层新页提前到位」的闪屏（旧问题根因）；
          - 快照半透明时透出的是同位置的旧页，形成自然的滑入溶解，无黑闪/重影；
          - 只叠加一个覆盖层，无旧页移动导致的内容撕裂或偏移。

        方向随 Tab 前进(新>旧)/后退(新<旧)自动切换（前进新页从右，后退从左）。
        """
        self._finalize_page_transition()

        stack = self._stack
        if stack is None:
            return
        parent = stack.parentWidget()          # content_area，覆盖层挂这里
        pos = stack.pos()                      # stack 在 content_area 中的位置
        size = stack.size()
        w, h = size.width(), size.height()
        x0, y0 = pos.x(), pos.y()

        new_page = stack.widget(new_idx)

        # 新页内容已在 _switch_mode 里事先刷新；临时切到新页抓快照，
        # 再立刻切回旧页（同步过程屏幕不重绘，底层始终保持旧页）。
        stack.setCurrentIndex(new_idx)
        new_snap = new_page.grab()
        stack.setCurrentIndex(old_idx)

        lab = QLabel(parent)
        lab.setPixmap(new_snap)
        lab.setScaledContents(True)            # 快照缩放到覆盖层尺寸，无黑边白边
        lab.setGeometry(x0, y0, w, h)
        lab.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lab.show()
        lab.raise_()

        eff = QGraphicsOpacityEffect(lab)
        lab.setGraphicsEffect(eff)
        eff.setOpacity(0.0)

        direction = 1 if new_idx > old_idx else -1   # 前进→新页从右滑入
        slide = 46 * direction

        self._trans_labels = [lab]
        self._trans_effects = [eff]

        anim = QVariantAnimation(self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _on_progress(value: float):
            # 新页快照从右侧滑入，同时淡入
            lab.move(x0 + int(slide * (1.0 - value)), y0)
            eff.setOpacity(value)

        def _on_finished():
            # 此刻新页快照已完全不透明并覆盖旧页，切到真实新页无感
            stack.setCurrentIndex(new_idx)
            self._finalize_page_transition()

        anim.valueChanged.connect(_on_progress)
        anim.finished.connect(_on_finished)
        self._page_transition_anim = anim
        anim.start()

    def _move_indicator_to(self, idx: int):
        """将选中指示器平滑滑动到指定 Tab 索引位置"""
        if not self._indicator_ready:
            # 指示器未就绪时（初始化阶段），直接设置位置不做动画
            return
        if idx < 0 or idx >= len(self._tab_buttons):
            return
        btn = self._tab_buttons[idx]
        # 计算指示器目标 Y 坐标（按钮中心对齐）
        btn_geom = btn.geometry()
        target_y = btn_geom.y() + btn_geom.height() // 2 - _TAB_INDICATOR_H // 2

        self._indicator_anim.stop()
        self._indicator_anim.setStartValue(self._indicator.get_indicator_y())
        self._indicator_anim.setEndValue(target_y)
        self._indicator_anim.start()

    def _init_indicator_position(self):
        """初始化指示器位置（在 showEvent 后调用）"""
        if not self._tab_buttons:
            return
        idx = self._stack.currentIndex()
        if idx < 0 or idx >= len(self._tab_buttons):
            return
        btn = self._tab_buttons[idx]
        btn_geom = btn.geometry()
        target_y = btn_geom.y() + btn_geom.height() // 2 - _TAB_INDICATOR_H // 2
        # 直接设置，不带动画
        self._indicator.set_indicator_y(target_y)
        # 标记指示器已就绪，允许后续动画
        self._indicator_ready = True

    def is_locked(self) -> bool:
        return self._dragging

    # ---------------- 数据注入 ----------------
    def set_cards(self, cards):
        self._cards = cards if cards else []

    def set_task_manager(self, tm: TaskManager):
        self._task_manager = tm

    def set_note_manager(self, nm: NoteManager):
        self._note_manager = nm

    def set_nav_manager(self, nm: NavManager):
        self._nav_manager = nm

    def set_config_manager(self, cm):
        self._config_manager = cm

    def set_asset_manager(self, am):
        """注入临时素材管理器"""
        self._asset_manager = am

    def set_fragment_manager(self, fm):
        """注入碎片管理器"""
        self._fragment_manager = fm

    def is_always_show(self) -> bool:
        """是否处于保持显示模式"""
        if self._config_manager:
            return self._config_manager.get("card_always_show", False)
        return False

    def _on_close_button_clicked(self):
        """保持显示模式下点击关闭按钮"""
        self.hide()
        self.card_closed.emit()

    def has_shown_content(self) -> bool:
        return self._current_index >= 0

    # ---------------- 知识卡片 ----------------
    def show_next_random(self):
        if not self._cards:
            self._content_label.setText(
                '<div style="line-height:180%;color:#999;">'
                '（暂无知识卡片，请检查「知识库.docx」内容）</div>'
            )
            return
        if len(self._cards) > 1:
            new_index = self._current_index
            while new_index == self._current_index:
                new_index = random.randint(0, len(self._cards) - 1)
            self._current_index = new_index
        else:
            self._current_index = 0
        safe_text = html.escape(self._cards[self._current_index])
        self._content_label.setText(
            f'<div style="line-height:180%;">{safe_text}</div>'
        )

    def next_card(self):
        self.show_next_random()

    def popup_near(self, ball_rect):
        self._switch_mode(self._last_mode)
        screen = _get_screen_geometry()
        x = ball_rect.left() - self.width() - 12
        y = ball_rect.top() - (self.height() - ball_rect.height()) // 2
        if x < screen.left():
            x = ball_rect.right() + 12
        if y < screen.top():
            y = screen.top() + 10
        if y + self.height() > screen.bottom():
            y = screen.bottom() - self.height() - 10
        self.move(int(x), int(y))
        # 保持显示模式下显示关闭按钮
        self._close_btn.setVisible(self.is_always_show())
        # 定位关闭按钮到右上角
        self._close_btn.move(self.WINDOW_WIDTH - 30, 8)
        self._close_btn.raise_()
        self.show()
        self.raise_()
        self.activateWindow()

    # ---------------- 日程任务 ----------------
    def _on_add_task(self):
        if not self._task_manager:
            return
        title = self._task_title_input.text().strip()
        if not title:
            return
        deadline = self._task_deadline.date().toString("yyyy-MM-dd")
        self._task_manager.add_task(title, "", deadline)
        self._task_title_input.clear()
        self._refresh_task_list()
        self.data_changed.emit("task")

    def _refresh_task_list(self):
        self._task_list.clear()
        if not self._task_manager:
            return
        for t in self._task_manager.get_all_tasks():
            status = "✓" if t.done else "☐"
            text = f"{status}  {t.title}"
            if t.deadline:
                text += f"   ｜ 截止: {t.deadline}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, t.task_id)
            if t.done:
                item.setForeground(QColor(150, 150, 150))
            self._task_list.addItem(item)

    def _on_task_context_menu(self, pos):
        item = self._task_list.itemAt(pos)
        if not item or not self._task_manager:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        task = self._task_manager.get_task(task_id)
        if not task:
            return

        menu = QMenu(self)
        menu.setStyleSheet(self._menu.styleSheet())
        act_toggle = menu.addAction("取消完成" if task.done else "标记完成")
        act_edit = menu.addAction("编辑...")
        menu.addSeparator()
        act_delete = menu.addAction("删除")

        action = menu.exec(self._task_list.mapToGlobal(pos))
        if action == act_toggle:
            self._task_manager.toggle_task(task_id)
            self._refresh_task_list()
            self.data_changed.emit("task")
        elif action == act_edit:
            self._edit_task(task)
        elif action == act_delete:
            self._task_manager.delete_task(task_id)
            self._refresh_task_list()
            self.data_changed.emit("task")

    def _edit_task(self, task):
        if not self._task_manager:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑任务")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dialog.setFixedSize(320, 200)

        form = QFormLayout(dialog)
        form.setContentsMargins(20, 20, 20, 16)
        form.setSpacing(10)

        title_edit = QLineEdit(task.title)
        note_edit = QLineEdit(task.note)
        note_edit.setPlaceholderText("备注（可选）")
        deadline_edit = QDateEdit()
        deadline_edit.setCalendarPopup(True)
        deadline_edit.setDisplayFormat("yyyy-MM-dd")
        if task.deadline:
            d = QDate.fromString(task.deadline, "yyyy-MM-dd")
            if d.isValid():
                deadline_edit.setDate(d)
            else:
                orig = f"（原始截止: {task.deadline}）"
                note_edit.setText(f"{task.note} {orig}" if task.note else orig)

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
                title_edit.text(),
                note_edit.text(),
                deadline_edit.date().toString("yyyy-MM-dd"),
            )
            self._refresh_task_list()
            self.data_changed.emit("task")

    # ---------------- 临时笔记 ----------------
    def _load_temp_note(self):
        if not self._note_manager:
            return
        self._loading_note = True
        try:
            temp = self._note_manager.get_temp_note()
            if temp is not None:
                self._current_note_id = temp.note_id
                self._note_edit.setPlainText(temp.content)
            else:
                self._current_note_id = None
                self._note_edit.clear()
        except Exception:
            self._current_note_id = None
            self._note_edit.clear()
        self._loading_note = False
        self._note_edit.setFocus()

    def _on_note_text_changed(self):
        if self._loading_note:
            return
        self._note_save_timer.start()

    def _on_save_note(self):
        if not self._note_manager:
            return
        content = self._note_edit.toPlainText()
        if self._current_note_id is None or self._note_manager.get_note(self._current_note_id) is None:
            try:
                temp = self._note_manager.get_temp_note()
                self._current_note_id = temp.note_id if temp else None
            except Exception:
                self._current_note_id = None
        if self._current_note_id is None:
            return
        self._note_manager.update_note(self._current_note_id, content, title=None)
        self.data_changed.emit("note")

    # ---------------- 退出 ----------------
    def _request_quit(self):
        self.request_quit.emit()

    # ==================================================================
    # 卡片拖动
    # ==================================================================
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = (event.globalPosition().toPoint()
                                 - self.frameGeometry().topLeft())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self.card_moved.emit()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()

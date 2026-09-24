# -*- coding: utf-8 -*-
"""
====================================================================
LaunchDeck 设置  -  SettingsDialog(460×320) / AddAppDialog(340宽)
====================================================================
v4 方案规格：
  · 设置窗 460×320 固定，圆角 14，背景 rgba(20,21,26,0.90)
  · 上半部：快捷方式列表（32px 行：17px 图标 + 名称 + 路径省略）
            右侧工具列：添加 / 删除 / 上移 / 下移（状态自动启停）
  · 下半部：三个滑杆 —— 图标大小(32-42) / 面板透明度(50-100%) / 动画速度(0.5-2.0×)
  · 底部：说明 + 保存并关闭；关闭途径：✕ / Esc / 保存按钮
  · 添加面板 340 宽：图标预览(32px) + 名称 + 路径 + 浏览
            路径输入 → 名称自动识别（手动改过则不覆盖）+ 图标实时提取预览
  · 所有更改即时持久化并即时同步面板（保存并关闭 仅收尾）
  · 深色控件：主文字 #D2D4D9，次要 #8A8D96，Win11 蓝主按钮 #4C96FF
====================================================================
"""

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QPoint
from PyQt6.QtGui import QColor, QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QDialog, QWidget, QLabel, QPushButton, QToolButton, QSlider,
    QListWidget, QListWidgetItem, QLineEdit, QFileDialog, QFrame,
    QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect,
    QSizePolicy, QCheckBox, QStyleFactory, QMessageBox,
)

from core.app_manager import (
    AppManager, get_exe_name, extract_app_icon, render_app_icon, clear_icon_cache,
    is_autostart_enabled, set_autostart,        # 【新增·需求2】
)
from ui import anim_tokens as atk

# 深色主题常量
TEXT_MAIN = "#D2D4D9"
TEXT_DIM = "#8A8D96"
ACCENT = "#4C96FF"
ACCENT_HOVER = "#67A5FF"

# 模块级持有 Fusion 样式实例（setStyle 不转移所有权，
# 必须保持引用防止 Python 侧回收导致退出时崩溃）
_FUSION = QStyleFactory.create("Fusion")

_DARK_QSS = f"""
QLabel {{ color: {TEXT_MAIN}; font-size: 12px; background: transparent; }}
QLabel#dim {{ color: {TEXT_DIM}; font-size: 11px; }}
QLabel#title {{ color: {TEXT_MAIN}; font-size: 13px; font-weight: 600; }}

QListWidget {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 8px; padding: 4px; outline: none;
}}
QListWidget::item {{ border-radius: 6px; }}
QListWidget::item:hover {{ background: rgba(255,255,255,0.05); }}
QListWidget::item:selected {{ background: rgba(76,150,255,0.16); color: {TEXT_MAIN}; }}

QLineEdit {{
    background: rgba(255,255,255,0.055);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 8px; color: {TEXT_MAIN};
    padding: 0 10px; font-size: 13px; selection-background-color: rgba(76,150,255,0.4);
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit::placeholder {{ color: rgba(210,212,217,0.35); }}

QSlider {{ background: transparent; border: none; }}
QSlider::groove:horizontal {{
    height: 4px; border-radius: 2px; background: rgba(255,255,255,0.14);
}}
QSlider::sub-page:horizontal {{ background: rgba(255,255,255,0.28); border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
    border: none; background: {TEXT_MAIN};
}}
QSlider::sub-page:horizontal:hover {{ background: {ACCENT}; }}

QCheckBox {{ color: {TEXT_MAIN}; font-size: 12px; background: transparent; spacing: 6px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.28);
    background: rgba(255,255,255,0.05);
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QToolButton {{
    background: transparent; border: none; border-radius: 6px;
    color: {TEXT_DIM}; font-size: 15px; font-weight: 600;
}}
QToolButton:hover:enabled {{ background: rgba(255,255,255,0.08); color: {TEXT_MAIN}; }}
QToolButton:disabled {{ color: rgba(138,141,150,0.3); }}

QPushButton#primary {{
    background: {ACCENT}; color: #FFFFFF; border: none;
    border-radius: 8px; padding: 7px 20px; font-size: 12px; font-weight: 700;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#ghost {{
    background: rgba(255,255,255,0.055); color: {TEXT_MAIN};
    border: 1px solid rgba(255,255,255,0.10); border-radius: 8px;
    padding: 6px 14px; font-size: 12px;
}}
QPushButton#ghost:hover {{ background: rgba(255,255,255,0.09); }}
QPushButton#closeX {{
    background: transparent; border: none; border-radius: 6px;
    color: {TEXT_DIM}; font-size: 13px; font-weight: 600;
}}
QPushButton#closeX:hover {{ background: rgba(255,255,255,0.08); color: {TEXT_MAIN}; }}
"""


class _TitleBar(QWidget):
    """弹窗标题栏：标题文字 + 关闭按钮 + 按住拖动窗口。"""

    def __init__(self, title: str, shell: "_FramelessShell"):
        super().__init__(shell)
        self._shell = shell
        self.setFixedHeight(38)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 10, 0)
        title_label = QLabel(title)
        title_label.setObjectName("title")
        lay.addWidget(title_label)
        lay.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setObjectName("closeX")
        btn_x.setFixedSize(28, 26)
        btn_x.clicked.connect(shell.reject)
        lay.addWidget(btn_x)

        self._drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (event.globalPosition().toPoint()
                              - self._shell.frameGeometry().topLeft())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            self._shell.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class _FramelessShell(QDialog):
    """
    深色圆角无边框弹窗骨架：内容 surface + 投影 + 可拖动标题栏 + ✕。

    子类通过 _build_body() 填充内容区。
    """

    SURFACE_RADIUS = 14
    SHADOW = 20

    def __init__(self, width: int, height: int, title: str, parent=None):
        super().__init__(parent)
        # 强制 Fusion（含子控件）：Windows 原生样式会给 QSS 滑杆
        # 画一层深黑色底块，Fusion 完整支持 QSS 无此问题
        self.setStyle(_FUSION)
        self.setWindowFlags(Qt.WindowType.Dialog
                            | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self.resize(width + self.SHADOW * 2, height + self.SHADOW * 2)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.SHADOW, self.SHADOW,
                                 self.SHADOW, self.SHADOW)

        self._surface = QFrame()
        self._surface.setObjectName("shellSurface")
        self._surface.setStyleSheet(
            f"QFrame#shellSurface {{ background: rgba(20,21,26,0.95);"
            f" border-radius: {self.SURFACE_RADIUS}px;"
            f" border: 1px solid rgba(255,255,255,0.10); }}")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 115))
        self._surface.setGraphicsEffect(shadow)
        outer.addWidget(self._surface)

        root = QVBoxLayout(self._surface)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 标题栏（可拖动窗口）
        root.addWidget(_TitleBar(title, self))

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.07); border: none;")
        root.addWidget(sep)

        # 内容区（不设无选择器样式表，避免覆盖 dialog 级 QSS 的级联）
        self._body = QWidget()
        root.addWidget(self._body, 1)

        self._build_body()

    # ---------------- 入场/出场动画 ----------------
    def showEvent(self, event):
        """首次显示时播放入场动画：淡入 + 轻微上移（200ms OutCubic）。"""
        super().showEvent(event)
        if not getattr(self, "_entered", False):
            self._entered = True
            self.setWindowOpacity(0.0)
            QTimer.singleShot(0, self._play_enter_anim)

    def _play_enter_anim(self):
        orig = self.pos()
        _travel = atk.motion("dialog.enter").travel
        self.move(orig.x(), orig.y() + _travel)
        # 【令牌】淡入 + 上移，统一 dialog.enter（OutCubic）
        atk.play(self, b"windowOpacity", "dialog.enter", 1.0,
                 start=0.0, end=1.0)
        atk.play(self, b"pos", "dialog.enter", 1.0,
                 start=self.pos(), end=orig)

    def done(self, result):
        """拦截所有关闭路径（accept/reject/Esc/✕），先播放退场动画再真正关闭。"""
        if getattr(self, "_exiting", False):
            super().done(result)
            return
        self._exiting = True
        orig = self.pos()
        _travel = atk.motion("dialog.exit").travel
        # 【令牌】淡出 + 下移，统一 dialog.exit（InCubic）
        atk.play(self, b"windowOpacity", "dialog.exit", 1.0,
                 start=self.windowOpacity(), end=0.0)
        atk.play(self, b"pos", "dialog.exit", 1.0,
                 start=self.pos(), end=QPoint(orig.x(), orig.y() + _travel),
                 on_finished=lambda: QDialog.done(self, result))

    # ---------------- 子类实现 ----------------
    def _build_body(self):
        raise NotImplementedError


# ====================================================================
# 列表行（17px 图标 + 名称 + 路径省略）
# ====================================================================

class _ListRow(QWidget):
    """设置窗列表里的一行：图标 + 名称 + 灰色路径（超出省略）。"""

    ROW_H = 30   # 行高（列表 item 的 sizeHint 也用它，保持一致）

    def __init__(self, app: dict, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.ROW_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(8)

        icon_label = QLabel()
        icon_label.setFixedSize(17, 17)
        icon_label.setPixmap(render_app_icon(app, 17))
        lay.addWidget(icon_label)

        name_label = QLabel(app.get("name", ""))
        name_label.setStyleSheet(
            f"color:{TEXT_MAIN};font-size:12px;font-weight:500;background:transparent;")
        name_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay.addWidget(name_label)

        path = app.get("exe_path", "") or "（空路径）"
        fm = QFontMetrics(QFont("Segoe UI", 9))
        path_label = QLabel(fm.elidedText(path, Qt.TextElideMode.ElideMiddle, 260))
        path_label.setStyleSheet(f"color:{TEXT_DIM};font-size:11px;background:transparent;")
        path_label.setToolTip(path)
        lay.addWidget(path_label, 1)


# ====================================================================
# 设置窗（460×320）
# ====================================================================

class SettingsDialog(_FramelessShell):
    """
    LaunchDeck 设置窗。

    信号：
      apps_changed()            —— 列表增删移后发射
      setting_changed(key, val) —— 滑杆变动后发射（已即时持久化）
    """

    apps_changed = pyqtSignal()
    setting_changed = pyqtSignal(str, object)

    def __init__(self, manager: AppManager, parent=None):
        self._mgr = manager
        super().__init__(460, 320, "LaunchDeck 设置", parent)

    def _build_body(self):
        root = QVBoxLayout(self._body)
        root.setContentsMargins(16, 10, 16, 14)
        root.setSpacing(6)

        # ---- 快捷方式 ----
        label = QLabel("快捷方式")
        label.setObjectName("dim")
        root.addWidget(label)

        mid = QHBoxLayout()
        mid.setSpacing(8)
        root.addLayout(mid, 1)

        self._list = QListWidget()
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.itemSelectionChanged.connect(self._sync_buttons)
        mid.addWidget(self._list, 1)

        # 右侧工具列：竖排（添加/删除/上移/下移，从上到下）
        tools = QVBoxLayout()
        tools.setSpacing(4)
        mid.addLayout(tools)

        self._btn_add = QToolButton()
        self._btn_add.setText("＋")
        self._btn_add.setFixedSize(28, 28)
        self._btn_add.setToolTip("添加应用")
        self._btn_add.clicked.connect(self._on_add)
        tools.addWidget(self._btn_add)

        self._btn_del = QToolButton()
        self._btn_del.setText("－")
        self._btn_del.setFixedSize(28, 28)
        self._btn_del.setToolTip("删除选中项")
        self._btn_del.clicked.connect(self._on_delete)
        tools.addWidget(self._btn_del)

        self._btn_up = QToolButton()
        self._btn_up.setText("↑")
        self._btn_up.setFixedSize(28, 28)
        self._btn_up.setToolTip("上移选中项")
        self._btn_up.clicked.connect(lambda: self._on_move(-1))
        tools.addWidget(self._btn_up)

        self._btn_down = QToolButton()
        self._btn_down.setText("↓")
        self._btn_down.setFixedSize(28, 28)
        self._btn_down.setToolTip("下移选中项")
        self._btn_down.clicked.connect(lambda: self._on_move(1))
        tools.addWidget(self._btn_down)

        # ---- 面板常驻开关 + 呼吸动画开关（同一行） ----
        checks = QHBoxLayout()
        checks.setSpacing(16)
        root.addLayout(checks)

        self._pin_cb = QCheckBox("面板常驻显示（不自动收回）")
        self._pin_cb.setChecked(bool(self._mgr.settings.get("panel_pinned", False)))
        self._pin_cb.toggled.connect(self._on_pin_toggled)
        checks.addWidget(self._pin_cb)

        # 【合并】呼吸光影：绑定「呼吸动画」与「光影特效」为一个开关
        self._breath_glow_cb = QCheckBox("呼吸光影")
        self._breath_glow_cb.setChecked(
            bool(self._mgr.settings.get("enable_idle_pulse", True)) and
            bool(self._mgr.settings.get("show_glow", True)))
        self._breath_glow_cb.toggled.connect(self._on_breath_glow_toggled)
        checks.addWidget(self._breath_glow_cb)

        # 【新增·需求2】开机自启开关（初始状态实时读注册表，不存 json）
        self._auto_cb = QCheckBox("开机自动启动")
        self._auto_cb.setChecked(is_autostart_enabled())
        self._auto_cb.toggled.connect(self._on_autostart_toggled)
        root.addWidget(self._auto_cb)

        # ---- 滑杆区 ----
        root.addSpacing(2)
        root.addWidget(self._make_slider("图标大小", 32, 42, 2,
                                         "icon_size", self._fmt_px))
        root.addWidget(self._make_slider("面板透明度", 50, 100, 1,
                                         "panel_opacity", self._fmt_opa))
        root.addWidget(self._make_slider("动画速度", 5, 20, 1,
                                         "anim_speed", self._fmt_speed))

        # ---- 底部 ----
        foot = QHBoxLayout()
        note = QLabel("更改即时保存并同步到面板")
        note.setObjectName("dim")
        foot.addWidget(note)
        foot.addStretch()
        btn_save = QPushButton("保存并关闭")
        btn_save.setObjectName("primary")
        btn_save.clicked.connect(self.accept)
        foot.addWidget(btn_save)
        root.addLayout(foot)

        self.setStyleSheet(_DARK_QSS)
        self._reload_list()

    # ---------------- 滑杆构建 ----------------
    def _make_slider(self, name: str, lo: int, hi: int, step: int,
                     key: str, fmt) -> QWidget:
        """构建一行：名称 + 滑杆 + 数值显示；变动即时持久化并广播。"""
        settings = self._mgr.settings
        raw = settings.get(key)
        if raw is None:
            # 各 key 的滑杆默认值
            value = {"icon_size": 40, "panel_opacity": 87, "anim_speed": 10}.get(key, lo)
        elif key == "panel_opacity":
            value = int(float(raw) * 100)
        elif key == "anim_speed":
            value = int(float(raw) * 10)
        else:
            value = int(raw)
        if not (lo <= value <= hi):
            value = (lo + hi) // 2

        row = QWidget()
        row.setFixedHeight(28)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        label = QLabel(name)
        label.setFixedWidth(72)
        label.setObjectName("dim")
        lay.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setSingleStep(step)
        slider.setPageStep(step)
        slider.setValue(value)
        lay.addWidget(slider, 1)

        value_label = QLabel(fmt(value))
        value_label.setFixedWidth(42)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight |
                                 Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(value_label)

        def on_change(v: int):
            value_label.setText(fmt(v))
            stored = (v / 100.0 if key == "panel_opacity"
                      else v / 10.0 if key == "anim_speed" else v)
            self._mgr.set_setting(key, stored)
            self.setting_changed.emit(key, stored)

        slider.valueChanged.connect(on_change)
        return row

    @staticmethod
    def _fmt_px(v: int) -> str:
        return f"{v}px"

    @staticmethod
    def _fmt_opa(v: int) -> str:
        return f"{v / 100:.2f}"

    @staticmethod
    def _fmt_speed(v: int) -> str:
        return f"{v / 10:.1f}×"

    # ---------------- 列表 ----------------
    def _reload_list(self):
        self._list.clear()
        for app in self._mgr.apps:
            row = _ListRow(app, self._list)
            item = QListWidgetItem()
            # 显式指定行高：row.sizeHint() 在未完成布局时返回无效值，
            # 会导致 item 行高与行控件高度不一致（高亮条错位）
            item.setSizeHint(QSize(0, _ListRow.ROW_H))
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        self._sync_buttons()

    def _selected_row(self) -> int:
        return self._list.currentRow()

    def _sync_buttons(self):
        row = self._selected_row()
        count = self._list.count()
        self._btn_del.setEnabled(0 <= row < count)
        self._btn_up.setEnabled(0 < row < count)
        self._btn_down.setEnabled(0 <= row < count - 1)

    # ---------------- 增删移 ----------------
    def _on_pin_toggled(self, checked: bool):
        """面板常驻开关：即时持久化并广播给悬浮球。"""
        self._mgr.set_setting("panel_pinned", bool(checked))
        self.setting_changed.emit("panel_pinned", bool(checked))

    # 【合并】呼吸光影开关：同时写入呼吸动画与光影，两者强绑定
    def _on_breath_glow_toggled(self, checked: bool):
        try:
            self._mgr.set_setting("enable_idle_pulse", bool(checked))
            self._mgr.set_setting("show_glow", bool(checked))
            self.setting_changed.emit("enable_idle_pulse", bool(checked))
            self.setting_changed.emit("show_glow", bool(checked))
        except Exception:
            pass

    # 【新增·需求2】开机自启开关：直接操作注册表，状态不落 json
    def _on_autostart_toggled(self, checked: bool):
        try:
            ok, msg = set_autostart(checked)
            if not ok:
                # 失败（无权限/开发模式等）：提示并回弹到注册表实际状态
                QMessageBox.information(self, "开机自启", msg)
                self._auto_cb.blockSignals(True)
                self._auto_cb.setChecked(is_autostart_enabled())
                self._auto_cb.blockSignals(False)
        except Exception:
            pass

    def _on_add(self):
        dlg = AddAppDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_app:
            self._mgr.apps.append(dlg.result_app)
            self._mgr.save()
            clear_icon_cache()
            self._reload_list()
            self.apps_changed.emit()

    def _on_delete(self):
        row = self._selected_row()
        apps = self._mgr.apps
        if 0 <= row < len(apps):
            del apps[row]
            self._mgr.save()
            clear_icon_cache()
            self._reload_list()
            self.apps_changed.emit()

    def _on_move(self, delta: int):
        row = self._selected_row()
        apps = self._mgr.apps
        target = row + delta
        if 0 <= row < len(apps) and 0 <= target < len(apps):
            apps[row], apps[target] = apps[target], apps[row]
            self._mgr.save()
            self._reload_list()
            self._list.setCurrentRow(target)
            self.apps_changed.emit()


# ====================================================================
# 添加应用面板（340 宽）
# ====================================================================

class AddAppDialog(_FramelessShell):
    """
    添加应用弹窗：图标预览 + 名称 + 路径 + 浏览 + 添加。

    - 路径输入/选择后：名称自动识别（用户手动改过名称则不覆盖），
      图标实时从 exe 提取（降饱和）显示
    - 确认后 result_app = {"name": ..., "exe_path": ...}
    """

    PREVIEW_SIZE = 32

    def __init__(self, parent=None):
        self.result_app = None
        self._name_touched = False
        self._custom_icon = ""     # 自定义图标路径（.ico/.png），可选
        super().__init__(340, 272, "添加应用", parent)

    def _build_body(self):
        root = QVBoxLayout(self._body)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(8)

        # ---- 图标预览 ----
        preview = QFrame()
        preview.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.03);"
            " border: 1px solid rgba(255,255,255,0.07); border-radius: 8px; }")
        p_lay = QHBoxLayout(preview)
        p_lay.setContentsMargins(12, 8, 12, 8)
        p_lay.setSpacing(12)

        self._preview_icon = QLabel()
        self._preview_icon.setFixedSize(self.PREVIEW_SIZE, self.PREVIEW_SIZE)
        self._preview_icon.setPixmap(extract_app_icon("", self.PREVIEW_SIZE, "L"))
        p_lay.addWidget(self._preview_icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self._preview_t1 = QLabel("图标预览")
        self._preview_t1.setObjectName("dim")
        text_col.addWidget(self._preview_t1)
        self._preview_t2 = QLabel("输入路径后自动从 exe 提取图标")
        self._preview_t2.setObjectName("dim")
        text_col.addWidget(self._preview_t2)
        p_lay.addLayout(text_col, 1)

        # 自定义图标按钮（可选）：选 .ico/.png 覆盖默认图标
        btn_icon = QPushButton("换图标")
        btn_icon.setObjectName("ghost")
        btn_icon.setFixedHeight(32)
        btn_icon.setToolTip("选择自定义图标（.ico / .png）")
        btn_icon.clicked.connect(self._on_pick_icon)
        p_lay.addWidget(btn_icon)
        root.addWidget(preview)

        # ---- 名称 ----
        name_label = QLabel("名称")
        name_label.setObjectName("dim")
        root.addWidget(name_label)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("留空可从 exe 自动识别")
        self._name_edit.setFixedHeight(32)
        self._name_edit.textChanged.connect(self._on_name_typed)
        root.addWidget(self._name_edit)

        # ---- 路径 ----
        path_label = QLabel("路径")
        path_label.setObjectName("dim")
        root.addWidget(path_label)
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("C:\\Program Files\\...\\app.exe")
        self._path_edit.setFixedHeight(32)
        self._path_edit.textChanged.connect(self._on_path_changed)
        path_row.addWidget(self._path_edit, 1)
        btn_browse = QPushButton("浏览")
        btn_browse.setObjectName("ghost")
        btn_browse.setFixedHeight(32)
        btn_browse.clicked.connect(self._on_browse)
        path_row.addWidget(btn_browse)
        root.addLayout(path_row)

        root.addStretch()

        # ---- 底部 ----
        foot = QHBoxLayout()
        note = QLabel("图标与名称均从 exe 自动识别")
        note.setObjectName("dim")
        foot.addWidget(note)
        foot.addStretch()
        btn_ok = QPushButton("添  加")
        btn_ok.setObjectName("primary")
        btn_ok.clicked.connect(self._on_confirm)
        foot.addWidget(btn_ok)
        root.addLayout(foot)

        self.setStyleSheet(_DARK_QSS)

    # ---------------- 交互 ----------------
    def _on_name_typed(self):
        self._name_touched = True

    def _refresh_preview(self, path: str, exists: bool):
        """统一刷新图标预览：优先自定义图标，否则 exe 系统图标。"""
        import os
        if self._custom_icon and os.path.exists(self._custom_icon):
            tmp = {"name": self._name_edit.text().strip(),
                   "exe_path": path, "custom_icon": self._custom_icon}
            self._preview_icon.setPixmap(render_app_icon(tmp, self.PREVIEW_SIZE))
            self._preview_t1.setText("自定义图标")
            self._preview_t2.setText(os.path.basename(self._custom_icon))
            return
        if exists:
            self._preview_icon.setPixmap(
                extract_app_icon(path, self.PREVIEW_SIZE,
                                 self._name_edit.text().strip()))
            self._preview_t1.setText("已识别图标")
        else:
            self._preview_icon.setPixmap(
                extract_app_icon("", self.PREVIEW_SIZE,
                                 os.path.basename(path) if path else "L"))
            self._preview_t1.setText("路径不存在 · 显示占位图标")
        self._preview_t2.setText(os.path.basename(path) if path else "输入路径后自动提取")

    def _on_path_changed(self, text: str):
        """路径变化：自动识别名称（未手动改过时）+ 实时提取图标预览。"""
        path = text.strip()
        if not path:
            self._preview_t1.setText("图标预览")
            self._preview_t2.setText("输入路径后自动从 exe 提取图标")
            self._preview_icon.setPixmap(
                extract_app_icon("", self.PREVIEW_SIZE, "L"))
            if not self._name_touched:
                self._name_edit.blockSignals(True)
                self._name_edit.clear()
                self._name_edit.blockSignals(False)
            return

        import os
        exists = os.path.exists(path)
        if not self._name_touched:
            name = get_exe_name(path) if exists else \
                os.path.splitext(os.path.basename(path))[0]
            self._name_edit.blockSignals(True)
            self._name_edit.setText(name)
            self._name_edit.blockSignals(False)
        self._refresh_preview(path, exists)

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择可执行文件", self._path_edit.text().strip() or "",
            "可执行文件 (*.exe);;所有文件 (*.*)")
        if path:
            self._path_edit.setText(path)

    def _on_pick_icon(self):
        """选择自定义图标（.ico / .png）；选后刷新预览。"""
        import os
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图标", self._custom_icon or "",
            "图标文件 (*.ico *.png);;所有文件 (*.*)")
        if path:
            self._custom_icon = path
            self._refresh_preview(self._path_edit.text().strip(),
                                  os.path.exists(self._path_edit.text().strip()))

    def _on_confirm(self):
        import os
        path = self._path_edit.text().strip()
        if not path:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "请填写或选择可执行文件路径。")
            return
        name = self._name_edit.text().strip()
        if not name:
            name = (get_exe_name(path) if os.path.exists(path)
                    else os.path.splitext(os.path.basename(path))[0])
        app = {"name": name, "exe_path": path}
        if self._custom_icon:
            app["custom_icon"] = self._custom_icon
        self.result_app = app
        self.accept()

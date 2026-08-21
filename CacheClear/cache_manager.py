import json
import os
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

try:
    from rule_loader import scan_by_rules
except Exception:  # 规则库文件缺失/损坏时，程序仍可用旧流程运行
    scan_by_rules = None

try:
    from heuristic_scanner import scan_heuristic
except Exception:  # 启发式模块缺失/损坏时，程序仍可运行其它流程
    scan_heuristic = None

try:
    from cache_safety import deep_judge_directory
except Exception:  # 全局判定模块缺失/损坏时，跳过深度确认
    deep_judge_directory = None

from PyQt6.QtCore import QSize, Qt, QUrl, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

APP_TITLE = "软件缓存管理器"
APP_ID = "OKClaw.CacheManager"
APP_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = APP_DIR / "settings.json"
ICON_PATH = APP_DIR / "favicon.ico"
DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 720
MIN_WIDTH = 1000
MIN_HEIGHT = 600
APP_SIZE_COLUMN = 3
CACHE_SIZE_COLUMN = 5
SCAN_METHODS_HELP = (
    "两种扫描方式：\n"
    "① 一键扫描规则库：按规则文件的已知路径精确扫描，结果标“已确认·可清理/谨慎”；准但不全。\n"
    "② 启发式扫描：按文件夹名在本地应用数据、Roaming、用户主目录点缓存下自动发现并深度确认，分“确认缓存/含用户数据/含配置/未验证”四档；覆盖面最大但最耗时、属推断。"
)

ROLE_ROW_ID = Qt.ItemDataRole.UserRole
ROLE_SORT = Qt.ItemDataRole.UserRole + 1
ROLE_KIND = Qt.ItemDataRole.UserRole + 2
ROLE_PATH = Qt.ItemDataRole.UserRole + 3


def human_size(value):
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024


def stat_path(path):
    if not path.exists():
        return 0, 0, None
    try:
        if path.is_file():
            s = path.stat()
            return s.st_size, 1, datetime.fromtimestamp(s.st_mtime)
    except OSError:
        return 0, 0, None
    total = count = 0
    latest = None
    try:
        for base, dirs, files in os.walk(path, followlinks=False):
            dirs[:] = [d for d in dirs if not Path(base, d).is_symlink()]
            for filename in files:
                try:
                    s = Path(base, filename).stat()
                    total += s.st_size
                    count += 1
                    stamp = datetime.fromtimestamp(s.st_mtime)
                    latest = stamp if latest is None or stamp > latest else latest
                except OSError:
                    pass
    except OSError:
        pass
    return total, count, latest


def dir_mtime(path):
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime)
    except OSError:
        return None


def _annotate_deep(results, path_key="real_path"):
    """在后台线程给一批结果附加深度确认结论（四档 verdict）。"""
    for item in results:
        if deep_judge_directory is None:
            verdict = {"verdict": "unknown", "reasons": [], "truncated": False}
        else:
            try:
                verdict = deep_judge_directory(str(item.get(path_key, "")))
            except Exception:
                verdict = {"verdict": "unknown", "reasons": [], "truncated": False}
        item["deep_verdict"] = verdict.get("verdict", "unknown")
        item["deep_reasons"] = verdict.get("reasons") or []
        item["deep_truncated"] = bool(verdict.get("truncated"))
    return results


def move_to_recycle_bin(path):
    """把目录/文件移入 Windows 回收站；返回 (ok: bool, err: str)。"""
    import ctypes
    if os.name != "nt":
        return False, "仅支持 Windows 回收站"

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_uint),
            ("fAnyOperationsAborted", ctypes.c_int),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x40
    FOF_NOCONFIRMATION = 0x10
    FOF_NOERRORUI = 0x400
    FOF_WANTNUKEWARNING = 0x4000
    try:
        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = str(path) + "\0"
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_WANTNUKEWARNING
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if rc != 0:
            return False, f"回收站删除失败（错误码 {rc}）"
        if op.fAnyOperationsAborted:
            return False, "操作被系统中止"
        return True, ""
    except OSError as exc:
        return False, str(exc)


class WorkerBridge(QObject):
    rules_ready = pyqtSignal(object)
    heuristic_ready = pyqtSignal(object)


class SortItem(QTableWidgetItem):
    def __lt__(self, other):
        left = self.data(ROLE_SORT)
        right = other.data(ROLE_SORT)
        if left is not None and right is not None:
            try:
                return left < right
            except TypeError:
                pass
        return super().__lt__(other)


class CacheManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        if ICON_PATH.is_file():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)

        self.backup_enabled = True
        self.discovery_rows = {}
        self.cache_rows = {}
        self.busy = False
        self.discovered = False
        self.rule_results_cache = []
        self.heuristic_results_cache = []

        self.bridge = WorkerBridge()
        self.bridge.rules_ready.connect(self.populate_rules)
        self.bridge.heuristic_ready.connect(self.populate_heuristic)

        self.load_settings()
        self.build_ui()
        self.apply_flow_lock()
        self.set_status("请点击“一键扫描规则库”或“启发式扫描”。", "wait")

    def center_on_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(area.center())
        self.move(frame.topLeft())

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 10)
        root_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel(APP_TITLE)
        title_font = QFont("Microsoft YaHei UI", 16)
        title_font.setBold(True)
        title.setFont(title_font)
        hint = QLabel("扫描 → 选择 → 清理（可备份）")
        hint.setStyleSheet("color: #555555;")
        title_row.addWidget(title)
        title_row.addSpacing(12)
        title_row.addWidget(hint)
        title_row.addStretch(1)
        root_layout.addLayout(title_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.hide()
        root_layout.addWidget(self.progress)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        root_layout.addWidget(self.splitter, 1)

        # ----- Left panel -----
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(10)

        scan_box = QGroupBox()
        scan_layout = QVBoxLayout(scan_box)
        scan_layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        scan_title = QLabel("扫描配置")
        scan_title.setStyleSheet("font-weight: bold;")
        self.info_btn = QToolButton()
        self.info_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self.info_btn.setIconSize(QSize(16, 16))
        self.info_btn.setFixedSize(22, 22)
        self.info_btn.setAutoRaise(True)
        self.info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.info_btn.setToolTip(SCAN_METHODS_HELP)
        self.info_btn.clicked.connect(self.show_scan_methods_help)
        header_row.addWidget(scan_title)
        header_row.addWidget(self.info_btn)
        header_row.addStretch(1)
        scan_layout.addLayout(header_row)

        self.btn_scan_rules = QPushButton("一键扫描规则库（推荐）")
        self.btn_scan_rules.setMinimumHeight(40)
        self.btn_scan_rules.setStyleSheet(
            "QPushButton { background-color: #185a9d; color: white; border: none; border-radius: 4px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #c8c8c8; color: #666666; }"
        )
        self.btn_scan_rules.clicked.connect(self.scan_rules)
        scan_layout.addWidget(self.btn_scan_rules)

        self.btn_scan_heuristic = QPushButton("启发式扫描（未确认缓存）")
        self.btn_scan_heuristic.setMinimumHeight(36)
        self.btn_scan_heuristic.setStyleSheet(
            "QPushButton { background-color: #00897b; color: white; border: none; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #00796b; }"
            "QPushButton:disabled { background-color: #c8c8c8; color: #666666; }"
        )
        self.btn_scan_heuristic.clicked.connect(self.start_heuristic_scan)
        scan_layout.addWidget(self.btn_scan_heuristic)

        note = QLabel("仅扫描当前用户的 C 盘应用缓存，不读取文件内容；备份时由你手动选择位置。")
        note.setWordWrap(True)
        note.setStyleSheet("color: #777777; font-size: 12px;")
        scan_layout.addWidget(note)
        left_layout.addWidget(scan_box)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索软件名称")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.refresh_app_list)
        left_layout.addWidget(self.search_edit)

        app_tools = QHBoxLayout()
        app_tools.addStretch(1)
        self.btn_select_all_apps = QPushButton("全选软件")
        self.btn_clear_apps = QPushButton("取消选择")
        self.btn_select_all_apps.clicked.connect(self.select_all_apps)
        self.btn_clear_apps.clicked.connect(self.clear_apps)
        app_tools.addWidget(self.btn_select_all_apps)
        app_tools.addWidget(self.btn_clear_apps)
        left_layout.addLayout(app_tools)

        self.apps = QTableWidget(0, 4)
        self.apps.setHorizontalHeaderLabels(["选择", "软件/来源", "数据位置数", "已识别数据占用"])
        self.apps.verticalHeader().setVisible(False)
        self.apps.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.apps.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.apps.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.apps.setAlternatingRowColors(True)
        self.apps.setSortingEnabled(True)
        self.apps.horizontalHeader().setStretchLastSection(False)
        self.apps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.apps.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.apps.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.apps.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.apps.cellClicked.connect(self.on_app_cell_clicked)
        self.apps.itemChanged.connect(self.on_app_item_changed)
        left_layout.addWidget(self.apps, 1)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(48)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        left_layout.addWidget(self.status_label)

        # ----- Right panel -----
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(10)

        cache_tools = QHBoxLayout()
        cache_tools.addStretch(1)
        self.btn_select_safe = QPushButton("全选安全缓存")
        self.btn_select_logs = QPushButton("全选日志")
        self.btn_clear_cache = QPushButton("取消选择")
        self.btn_select_safe.clicked.connect(self.select_safe)
        self.btn_select_logs.clicked.connect(self.select_logs)
        self.btn_clear_cache.clicked.connect(self.clear_cache_selection)
        cache_tools.addWidget(self.btn_select_safe)
        cache_tools.addWidget(self.btn_select_logs)
        cache_tools.addWidget(self.btn_clear_cache)
        right_layout.addLayout(cache_tools)

        self.cache_search = QLineEdit()
        self.cache_search.setPlaceholderText("搜索缓存目录 / 软件 / 状态")
        self.cache_search.setClearButtonEnabled(True)
        self.cache_search.textChanged.connect(self.sync_rules_right)
        right_layout.addWidget(self.cache_search)

        self.tree = QTableWidget(0, 8)
        self.tree.setHorizontalHeaderLabels(
            ["选择", "软件", "类别", "缓存目录", "文件数", "占用", "最近修改", "状态"]
        )
        self.tree.verticalHeader().setVisible(False)
        self.tree.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tree.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        header = self.tree.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 150)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 90)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        tooltips = {
            0: "勾选后参与备份或清理",
            1: "所属软件或来源",
            2: "明确缓存或日志",
            3: "双击可打开本地文件夹",
            4: "目录内文件数量",
            5: "占用空间（自动格式化为 KB/MB/GB）",
            6: "目录内最近修改时间",
            7: "清理策略说明",
        }
        for col, tip in tooltips.items():
            item = self.tree.horizontalHeaderItem(col)
            if item:
                item.setToolTip(tip)
        self.tree.cellChanged.connect(self.on_cache_cell_changed)
        self.tree.cellDoubleClicked.connect(self.on_cache_double_clicked)
        right_layout.addWidget(self.tree, 1)

        action_bar = QHBoxLayout()
        action_bar.setSpacing(12)
        self.chk_backup = QCheckBox("清理前自动备份")
        self.chk_backup.setChecked(self.backup_enabled)
        self.chk_backup.toggled.connect(self.on_settings_changed)
        self.selection_summary = QLabel("已选择：0 项 / 0 B")
        self.selection_summary.setStyleSheet("color: #185a9d;")
        self.selection_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_backup = QPushButton("备份选中项")
        self.btn_clean = QPushButton("清理选中项（移入回收站）")
        self.btn_clean.setStyleSheet(
            "QPushButton { border: 1px solid #c42b1c; color: #c42b1c; padding: 6px 12px; }"
            "QPushButton:disabled { border: 1px solid #c8c8c8; color: #999999; }"
        )
        self.btn_backup.clicked.connect(self.backup_selected)
        self.btn_clean.clicked.connect(self.clean_selected)
        action_bar.addWidget(self.chk_backup)
        action_bar.addStretch(1)
        action_bar.addWidget(self.selection_summary)
        action_bar.addStretch(1)
        action_bar.addWidget(self.btn_backup)
        action_bar.addWidget(self.btn_clean)
        right_layout.addLayout(action_bar)

        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setSizes([320, 880])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

    def load_settings(self):
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            self.backup_enabled = bool(data.get("backupEnabled", True))
        except (OSError, ValueError, TypeError):
            pass

    def save_settings(self):
        data = {
            "backupEnabled": bool(self.chk_backup.isChecked()),
        }
        try:
            SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def on_settings_changed(self, *_):
        self.save_settings()

    def show_scan_methods_help(self):
        QMessageBox.information(self, "扫描方式说明", SCAN_METHODS_HELP)

    def set_status(self, text, level="wait"):
        colors = {
            "wait": "#666666",
            "run": "#185a9d",
            "warn": "#9a5d00",
            "error": "#c42b1c",
        }
        self.status_label.setStyleSheet(f"color: {colors.get(level, '#666666')};")
        self.status_label.setText(text)

    def set_busy(self, busy, text=None, level="run"):
        self.busy = busy
        if busy:
            self.progress.show()
            self.progress.setRange(0, 0)
        else:
            self.progress.hide()
            self.progress.setRange(0, 1)
        if text:
            self.set_status(text, level if busy else "wait")
        self.apply_flow_lock()

    def apply_flow_lock(self):
        ready = self.discovered and not self.busy
        self.btn_scan_rules.setEnabled(not self.busy)
        self.btn_scan_heuristic.setEnabled(not self.busy)
        self.btn_backup.setEnabled(ready)
        self.btn_clean.setEnabled(ready)
        self.btn_select_all_apps.setEnabled(self.discovered and not self.busy)
        self.btn_clear_apps.setEnabled(self.discovered and not self.busy)
        self.btn_select_safe.setEnabled(bool(self.cache_rows) and not self.busy)
        self.btn_select_logs.setEnabled(bool(self.cache_rows) and not self.busy)
        self.btn_clear_cache.setEnabled(bool(self.cache_rows) and not self.busy)

    def closeEvent(self, event):
        if self.busy:
            reply = QMessageBox.question(
                self,
                "扫描仍在进行",
                "扫描正在进行。确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.save_settings()
        event.accept()

    def refresh_app_list(self, *_):
        """View-only filter for software table; does not touch underlying data or checks."""
        query = self.search_edit.text().strip().casefold()
        for row in range(self.apps.rowCount()):
            name_item = self.apps.item(row, 1)
            name = name_item.text() if name_item else ""
            visible = (not query) or (query in name.casefold())
            self.apps.setRowHidden(row, not visible)

    def on_app_cell_clicked(self, row, column):
        if column != 0:
            check = self.apps.item(row, 0)
            if check:
                new_state = (
                    Qt.CheckState.Unchecked
                    if check.checkState() == Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
                check.setCheckState(new_state)

    def on_app_item_changed(self, item):
        if item.column() == 0:
            self.sync_rules_right()

    def checked_software_names(self):
        names = []
        for _row, row_id, check in self.iter_app_rows():
            if check.checkState() == Qt.CheckState.Checked:
                entry = self.discovery_rows.get(row_id)
                if entry:
                    names.append(entry["name"])
        return names

    def sync_rules_right(self):
        """统一右侧明细可见性：软件勾选过滤 + 搜索过滤。"""
        query = self.cache_search.text().strip().casefold()
        checked = set(self.checked_software_names())
        for row in range(self.tree.rowCount()):
            software_item = self.tree.item(row, 1)
            software = software_item.text() if software_item else ""
            hidden = software not in checked
            if not hidden and query:
                texts = []
                for col in (1, 2, 3, 7):
                    item = self.tree.item(row, col)
                    if item:
                        texts.append(item.text())
                hidden = query not in " ".join(texts).casefold()
            self.tree.setRowHidden(row, hidden)
        self.update_selection_summary()

    def iter_app_rows(self):
        for row in range(self.apps.rowCount()):
            check = self.apps.item(row, 0)
            if not check:
                continue
            row_id = check.data(ROLE_ROW_ID)
            if row_id in self.discovery_rows:
                yield row, row_id, check

    def select_all_apps(self):
        self.apps.blockSignals(True)
        for _row, _row_id, check in self.iter_app_rows():
            check.setCheckState(Qt.CheckState.Checked)
        self.apps.blockSignals(False)
        self.sync_rules_right()

    def clear_apps(self):
        self.apps.blockSignals(True)
        for _row, _row_id, check in self.iter_app_rows():
            check.setCheckState(Qt.CheckState.Unchecked)
        self.apps.blockSignals(False)
        self.sync_rules_right()

    def scan_rules(self):
        if self.busy:
            return
        if scan_by_rules is None:
            QMessageBox.warning(self, "规则库不可用", "未找到 rule_loader.py 或规则库文件损坏，无法进行规则库扫描。")
            return
        self.save_settings()
        self.heuristic_results_cache = []
        self.set_busy(True, "正在按规则库扫描软件缓存…", "run")
        self.apps.setSortingEnabled(False)
        self.apps.setRowCount(0)
        self.discovery_rows.clear()
        self.discovered = False
        threading.Thread(target=self.scan_rules_worker, daemon=True).start()

    def scan_rules_worker(self):
        try:
            results = scan_by_rules()
        except Exception:
            results = []
        _annotate_deep(results)
        self.rule_results_cache = results
        self.bridge.rules_ready.emit(results)

    def populate_rules(self, results):
        self.apps.blockSignals(True)
        self.apps.setSortingEnabled(False)
        self.apps.setRowCount(0)
        self.discovery_rows.clear()

        grouped = {}
        for r in results:
            grouped.setdefault(r.get("app_name", ""), []).append(r)

        for name in sorted(grouped, key=str.lower):
            items = grouped[name]
            total_bytes = sum(int(x.get("size_bytes", 0)) for x in items)
            row_id = str(uuid.uuid4())
            row = self.apps.rowCount()
            self.apps.insertRow(row)

            check = SortItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(
                Qt.CheckState.Checked if any(x.get("default_check") for x in items) else Qt.CheckState.Unchecked
            )
            check.setData(ROLE_ROW_ID, row_id)
            check.setData(ROLE_SORT, 0)
            self.apps.setItem(row, 0, check)

            name_item = SortItem(name)
            name_item.setData(ROLE_ROW_ID, row_id)
            name_item.setData(ROLE_SORT, name.casefold())
            self.apps.setItem(row, 1, name_item)

            loc_item = SortItem(str(len(items)))
            loc_item.setData(ROLE_SORT, len(items))
            loc_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.apps.setItem(row, 2, loc_item)

            size_item = SortItem(human_size(total_bytes))
            size_item.setData(ROLE_SORT, int(total_bytes))
            self.apps.setItem(row, 3, size_item)

            self.discovery_rows[row_id] = {"name": name, "locations": [Path(x["real_path"]) for x in items]}

        self.apps.setSortingEnabled(True)
        self.apps.sortItems(APP_SIZE_COLUMN, Qt.SortOrder.DescendingOrder)
        self.apps.blockSignals(False)

        self.tree.blockSignals(True)
        self.tree.setSortingEnabled(False)
        self.tree.setRowCount(0)
        self.cache_rows.clear()

        for r in results:
            software = r.get("app_name", "")
            category = r.get("category", "")
            path = Path(r.get("real_path", ""))
            count = int(r.get("file_count", 0))
            size = int(r.get("size_bytes", 0))
            risk = r.get("risk_level", "safe")
            note = r.get("note", "")
            deep_verdict = r.get("deep_verdict", "unknown")
            risky = deep_verdict == "risky"
            risk_reason = "; ".join(r.get("deep_reasons") or [])
            kind = "cache" if risk == "safe" else "caution"
            is_log = path.name.casefold() in ("logs", "log")
            if is_log:
                kind = "log"
            row_id = str(uuid.uuid4())
            row = self.tree.rowCount()
            self.tree.insertRow(row)

            check = SortItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(
                Qt.CheckState.Unchecked
                if (risky or not r.get("default_check"))
                else Qt.CheckState.Checked
            )
            check.setData(ROLE_ROW_ID, row_id)
            check.setData(ROLE_SORT, 0)
            self.tree.setItem(row, 0, check)

            soft_item = SortItem(software)
            soft_item.setData(ROLE_SORT, software.casefold())
            if risky:
                soft_item.setForeground(QColor("#c42b1c"))
            else:
                soft_item.setForeground(QColor("#167136") if risk == "safe" else QColor("#9a5d00"))
            self.tree.setItem(row, 1, soft_item)

            cat_item = SortItem("日志" if is_log else category)
            cat_item.setData(ROLE_SORT, "日志" if is_log else category)
            cat_item.setData(ROLE_KIND, kind)
            self.tree.setItem(row, 2, cat_item)

            path_item = SortItem(str(path))
            path_item.setData(ROLE_SORT, str(path).casefold())
            path_item.setData(ROLE_PATH, str(path))
            path_item.setToolTip(f"{path}\n\n{note}\n\n双击打开本地文件夹")
            self.tree.setItem(row, 3, path_item)

            files_item = SortItem(str(count))
            files_item.setData(ROLE_SORT, int(count))
            files_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tree.setItem(row, 4, files_item)

            size_item = SortItem(human_size(size))
            size_item.setData(ROLE_SORT, int(size))
            self.tree.setItem(row, 5, size_item)

            modified = dir_mtime(path)
            modified_text = modified.strftime("%Y-%m-%d %H:%M") if modified else "—"
            modified_item = SortItem(modified_text)
            modified_item.setData(ROLE_SORT, modified.timestamp() if modified else 0)
            self.tree.setItem(row, 6, modified_item)

            if risky:
                status_text = "含配置·风险"
                status_color = QColor("#c42b1c")
            elif is_log:
                status_text = "日志·可清理"
                status_color = QColor("#167136")
            elif risk == "safe":
                status_text = "已确认·可清理"
                status_color = QColor("#167136")
            else:
                status_text = "已确认·谨慎清理"
                status_color = QColor("#9a5d00")
            status_item = SortItem(status_text)
            status_item.setData(ROLE_SORT, status_text)
            status_item.setForeground(status_color)
            status_item.setToolTip(note + (f"\n\n{risk_reason}" if risk_reason else ""))
            self.tree.setItem(row, 7, status_item)

            self.cache_rows[row_id] = {
                "software": software,
                "path": path,
                "kind": kind,
                "size": size,
                "count": count,
                "risk_level": risk,
                "note": note,
                "risky": risky,
                "risk_reason": risk_reason,
            }

        self.tree.setSortingEnabled(True)
        self.tree.sortItems(CACHE_SIZE_COLUMN, Qt.SortOrder.DescendingOrder)
        self.tree.blockSignals(False)
        self.discovered = True
        self.refresh_app_list()
        self.sync_rules_right()
        self.set_busy(
            False,
            f"规则库扫描完成：发现 {len(results)} 个缓存目录。绿色=安全（默认勾选），橙色=谨慎，红色=疑似含配置（需确认）。",
            "wait",
        )

    def start_heuristic_scan(self):
        if self.busy:
            return
        if scan_heuristic is None:
            QMessageBox.warning(self, "启发式扫描不可用", "未找到 heuristic_scanner.py，无法进行启发式扫描。")
            return
        self.set_busy(True, "正在启发式扫描（本地应用数据 / Roaming / 主目录点缓存）…", "run")
        threading.Thread(target=self.heuristic_worker, daemon=True).start()

    def heuristic_worker(self):
        try:
            results = scan_heuristic()
        except Exception:
            results = []
        _annotate_deep(results)
        self.heuristic_results_cache = results
        self.bridge.heuristic_ready.emit(results)

    def populate_heuristic(self, results):
        # 追加左侧软件分组（已存在的软件名不重复添加）
        existing_names = {entry["name"] for entry in self.discovery_rows.values()}
        grouped = {}
        for r in results:
            grouped.setdefault(r.get("app_name", ""), []).append(r)

        self.apps.blockSignals(True)
        self.apps.setSortingEnabled(False)
        for name in sorted(grouped, key=str.lower):
            if name in existing_names:
                continue
            items = grouped[name]
            total_bytes = sum(int(x.get("size_bytes", 0)) for x in items)
            row_id = str(uuid.uuid4())
            row = self.apps.rowCount()
            self.apps.insertRow(row)

            check = SortItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(Qt.CheckState.Checked)
            check.setData(ROLE_ROW_ID, row_id)
            check.setData(ROLE_SORT, 0)
            self.apps.setItem(row, 0, check)

            name_item = SortItem(name)
            name_item.setData(ROLE_ROW_ID, row_id)
            name_item.setData(ROLE_SORT, name.casefold())
            self.apps.setItem(row, 1, name_item)

            loc_item = SortItem(str(len(items)))
            loc_item.setData(ROLE_SORT, len(items))
            loc_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.apps.setItem(row, 2, loc_item)

            size_item = SortItem(human_size(total_bytes))
            size_item.setData(ROLE_SORT, int(total_bytes))
            self.apps.setItem(row, 3, size_item)

            self.discovery_rows[row_id] = {
                "name": name,
                "locations": [Path(x["real_path"]) for x in items],
            }
            existing_names.add(name)
        self.apps.setSortingEnabled(True)
        self.apps.sortItems(APP_SIZE_COLUMN, Qt.SortOrder.DescendingOrder)
        self.apps.blockSignals(False)

        # 追加右侧明细（每项默认不勾选，标“未验证”）
        self.tree.blockSignals(True)
        self.tree.setSortingEnabled(False)
        for r in results:
            software = r.get("app_name", "")
            path = Path(r.get("real_path", ""))
            count = int(r.get("file_count", 0))
            size = int(r.get("size_bytes", 0))
            note = r.get("note", "")
            deep_verdict = r.get("deep_verdict", "unknown")
            risky = deep_verdict == "risky"
            risk_reason = "; ".join(r.get("deep_reasons") or [])
            is_log = path.name.casefold() in ("logs", "log")
            row_id = str(uuid.uuid4())
            row = self.tree.rowCount()
            self.tree.insertRow(row)

            check = SortItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(Qt.CheckState.Unchecked)
            check.setData(ROLE_ROW_ID, row_id)
            check.setData(ROLE_SORT, 0)
            self.tree.setItem(row, 0, check)

            soft_item = SortItem(software)
            soft_item.setData(ROLE_SORT, software.casefold())
            if deep_verdict == "risky":
                soft_item.setForeground(QColor("#c42b1c"))
            elif deep_verdict == "caution":
                soft_item.setForeground(QColor("#9a5d00"))
            elif deep_verdict == "safe":
                soft_item.setForeground(QColor("#167136"))
            else:
                soft_item.setForeground(QColor("#6f6f6f"))
            self.tree.setItem(row, 1, soft_item)

            cat_item = SortItem("日志" if is_log else "疑似缓存")
            cat_item.setData(ROLE_SORT, "日志" if is_log else "疑似缓存")
            cat_item.setData(ROLE_KIND, "log" if is_log else "heuristic")
            cat_item.setForeground(QColor("#6f6f6f"))
            self.tree.setItem(row, 2, cat_item)

            path_item = SortItem(str(path))
            path_item.setData(ROLE_SORT, str(path).casefold())
            path_item.setData(ROLE_PATH, str(path))
            path_item.setToolTip(f"{path}\n\n{note}\n\n双击打开本地文件夹")
            self.tree.setItem(row, 3, path_item)

            files_item = SortItem(str(count))
            files_item.setData(ROLE_SORT, int(count))
            files_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tree.setItem(row, 4, files_item)

            size_item = SortItem(human_size(size))
            size_item.setData(ROLE_SORT, int(size))
            self.tree.setItem(row, 5, size_item)

            modified = dir_mtime(path)
            modified_text = modified.strftime("%Y-%m-%d %H:%M") if modified else "—"
            modified_item = SortItem(modified_text)
            modified_item.setData(ROLE_SORT, modified.timestamp() if modified else 0)
            self.tree.setItem(row, 6, modified_item)

            if deep_verdict == "risky":
                status_text = "含配置·风险"
                status_color = QColor("#c42b1c")
            elif is_log:
                status_text = "日志·未验证"
                status_color = QColor("#6f6f6f")
            elif deep_verdict == "caution":
                status_text = "含用户数据·谨慎"
                status_color = QColor("#9a5d00")
            elif deep_verdict == "safe":
                status_text = "确认缓存(抽样)" if r.get("deep_truncated") else "确认缓存"
                status_color = QColor("#167136")
            else:
                status_text = "未验证"
                status_color = QColor("#6f6f6f")
            status_item = SortItem(status_text)
            status_item.setData(ROLE_SORT, status_text)
            status_item.setForeground(status_color)
            status_item.setToolTip(note + (f"\n\n{risk_reason}" if risk_reason else ""))
            self.tree.setItem(row, 7, status_item)

            self.cache_rows[row_id] = {
                "software": software,
                "path": path,
                "kind": "log" if is_log else "heuristic",
                "size": size,
                "count": count,
                "risk_level": "unknown",
                "note": note,
                "risky": risky,
                "risk_reason": risk_reason,
            }
        self.tree.setSortingEnabled(True)
        self.tree.sortItems(CACHE_SIZE_COLUMN, Qt.SortOrder.DescendingOrder)
        self.tree.blockSignals(False)

        self.discovered = True
        self.refresh_app_list()
        self.sync_rules_right()
        self.set_busy(
            False,
            f"启发式扫描完成：新增 {len(results)} 项。绿色=确认缓存，橙色=含用户数据，红色=含配置，灰色=未验证（均默认不勾选）。",
            "wait",
        )

    def iter_cache_rows(self):
        for row in range(self.tree.rowCount()):
            check = self.tree.item(row, 0)
            if not check:
                continue
            row_id = check.data(ROLE_ROW_ID)
            if row_id in self.cache_rows:
                yield row, row_id, check

    def on_cache_cell_changed(self, row, column):
        if column == 0:
            self.update_selection_summary()

    def on_cache_double_clicked(self, row, column):
        if column != 3:
            return
        path_item = self.tree.item(row, 3)
        if not path_item:
            return
        path = path_item.data(ROLE_PATH) or path_item.text()
        target = Path(path)
        if not target.exists():
            self.set_status(f"目录不存在：{path}", "warn")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def select_safe(self):
        self.tree.blockSignals(True)
        for row, row_id, check in self.iter_cache_rows():
            if self.cache_rows[row_id]["kind"] == "cache":
                check.setCheckState(Qt.CheckState.Checked)
        self.tree.blockSignals(False)
        self.update_selection_summary()

    def select_logs(self):
        self.tree.blockSignals(True)
        for row, row_id, check in self.iter_cache_rows():
            if self.cache_rows[row_id]["kind"] == "log":
                check.setCheckState(Qt.CheckState.Checked)
        self.tree.blockSignals(False)
        self.update_selection_summary()

    def clear_cache_selection(self):
        self.tree.blockSignals(True)
        for _row, _row_id, check in self.iter_cache_rows():
            check.setCheckState(Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)
        self.update_selection_summary()

    def update_selection_summary(self):
        splitter_sizes = self.splitter.sizes()
        rows = self.selected_rows() if self.cache_rows else []
        self.selection_summary.setText(
            f"已选择：{len(rows)} 项 / {human_size(sum(row['size'] for row in rows))}"
        )
        if splitter_sizes and sum(splitter_sizes) > 0:
            self.splitter.setSizes(splitter_sizes)

    def selected_rows(self):
        result = []
        for row, row_id, check in self.iter_cache_rows():
            if check.checkState() == Qt.CheckState.Checked and not self.tree.isRowHidden(row):
                result.append(self.cache_rows[row_id])
        return result

    def make_backup(self, rows):
        destination = QFileDialog.getExistingDirectory(self, "选择本次备份位置（建议选择 D 盘）")
        if not destination:
            return None, ["未选择备份目录"]
        root = Path(destination) / f"SoftwareCacheBackup_{datetime.now():%Y%m%d_%H%M%S}"
        errors = []
        try:
            root.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            return None, [f"无法创建备份目录：{exc}"]
        for index, row in enumerate(rows, 1):
            try:
                shutil.copytree(row["path"], root / f"{index:03d}_{row['path'].name}")
            except OSError as exc:
                errors.append(f"{row['path']}: {exc}")
        return root, errors

    def backup_selected(self):
        rows = self.selected_rows()
        if not rows:
            QMessageBox.information(self, "没有选择", "请先选择明细项目。")
            return
        root, errors = self.make_backup(rows)
        if root:
            text = f"备份位置：\n{root}"
            if errors:
                text += "\n\n失败：\n" + "\n".join(errors[:10])
                QMessageBox.warning(self, "备份完成", text)
            else:
                QMessageBox.information(self, "备份完成", text)

    def clean_selected(self):
        rows = self.selected_rows()
        if not rows:
            QMessageBox.information(self, "没有选择", "请先选择明细项目。")
            return
        reply = QMessageBox.question(
            self,
            "确认清理",
            "将把选中的缓存目录移入回收站（可还原）。\n\n橙色“谨慎清理”项可能丢失本地图片、日志或会话缓存，请确认已备份或不再需要。\n\n请先关闭相关软件。继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        risky_rows = [row for row in rows if row.get("risky")]
        if risky_rows:
            typed, ok = QInputDialog.getText(
                self,
                "二次确认",
                f"选中项中有 {len(risky_rows)} 个目录疑似含配置/敏感数据。\n请输入“确认删除”后继续：",
            )
            if not ok or (typed or "").strip() != "确认删除":
                self.set_status("已取消：未输入正确的确认文字。", "warn")
                return
        backup = None
        if self.chk_backup.isChecked():
            backup, errors = self.make_backup(rows)
            if backup is None:
                return
            if errors:
                cont = QMessageBox.question(
                    self,
                    "备份不完整",
                    "备份有失败项目，仍然继续清理吗？\n\n" + "\n".join(errors[:8]),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if cont != QMessageBox.StandardButton.Yes:
                    return
        released = removed = 0
        errors = []
        selected_iids = {iid for iid, candidate in self.cache_rows.items() if candidate in rows}
        for row in rows:
            before_bytes, before_count, _ = stat_path(row["path"])
            ok, err = move_to_recycle_bin(row["path"])
            if not ok:
                after_bytes, after_count, _ = stat_path(row["path"])
                released += max(0, before_bytes - after_bytes)
                removed += max(0, before_count - after_count)
                errors.append(f"{row['path']}: {err}")
            else:
                released += before_bytes
                removed += before_count
        # Remove only successfully selected rows; leave unselected scan results visible.
        rows_to_delete = []
        for row, row_id, _check in self.iter_cache_rows():
            if row_id not in selected_iids:
                continue
            if row_id not in self.cache_rows:
                continue
            if self.cache_rows[row_id]["path"].exists():
                continue
            rows_to_delete.append((row, row_id))
        self.tree.blockSignals(True)
        for row, row_id in sorted(rows_to_delete, key=lambda x: x[0], reverse=True):
            self.tree.removeRow(row)
            del self.cache_rows[row_id]
        self.tree.blockSignals(False)

        text = f"处理完成：移入回收站约 {removed} 个文件，预计释放 {human_size(released)}。"
        if backup:
            text += f"\n\n备份位置：\n{backup}"
        if errors:
            text += "\n\n失败：\n" + "\n".join(errors[:10])
            QMessageBox.warning(self, "完成但有失败", text)
            self.set_status("清理完成，但部分项目失败。", "warn")
        else:
            QMessageBox.information(self, "清理完成", text)
            self.set_status(
                "清理完成。未选中的缓存仍保留在列表中；如需确认，可点击“扫描选中软件”重新扫描。",
                "wait",
            )
        self.update_selection_summary()
        self.apply_flow_lock()

if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except (AttributeError, OSError):
            pass

    app = QApplication(sys.argv)
    if ICON_PATH.is_file():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    window = CacheManager()
    window.show()
    window.center_on_screen()
    sys.exit(app.exec())

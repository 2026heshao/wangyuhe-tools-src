# FloatPulse · 生活悬浮球

基于 **PyQt6 原生控件 + QSS** 开发的 Windows 桌面常驻悬浮球工具。
圆形悬浮球 + 420×320 无边框置顶小卡片弹窗 + 独立完整大窗口主 UI，三层架构、业务与 UI 完全解耦。

> 安装包（免安装 ZIP）见 [Releases](https://github.com/2026heshao/wangyuhe-tools-src/releases/tag/floatpulse-v3.0)；
> 产品宣传页见 [`宣传页/index.html`](宣传页/index.html)。

---

## 〇、目录结构

本仓库中的 `FloatPulse/` 目录是**可直接运行的项目根**（v3 当前主线，扁平结构）：

```
FloatPulse/                        # 项目根（本目录）
├── knowledge_ball.py              # 程序入口：FloatingBall + main + 全局异常钩子
├── src/                           # 源码模块（36 个，详见「五、模块职责」）
├── tests/                         # pytest 测试（5 个文件，121 用例）
├── tools/                         # 设计验证脚本（14 个，离屏渲染 / 交互回归）
├── conftest.py                    # pytest 路径配置（保证可直接 import src）
├── test_init.py                   # 初始化自检（管理器 + 窗口实例化）
├── requirements.txt               # 运行依赖
├── pyrightconfig.json             # 类型检查配置
├── FloatPulse.spec                # PyInstaller 打包配置（onedir + 轻量过滤）
├── FloatPulse.ico / .png          # 图标与展示图
├── generate_knowledge.py          # 「知识库.docx」批量生成脚本
├── 知识库.docx                     # 知识卡片数据源（用户数据，可外部编辑）
└── 宣传页/index.html               # 产品宣传页
```

首次运行时会**自动创建**（已被 `.gitignore` 排除，不进版本管理）：

```
├── data/                          # config / schedule / notes / fragments / nav / docx_meta / temp_assets.json
└── temp_assets/                   # 拖入的临时素材实体文件
```

路径定位见 `src/app_paths.py::get_project_root()`（打包运行时自动回退到 exe 同级目录）。

---

## 一、功能特性

### 悬浮球（高频轻量入口）
| 特性 | 说明 |
|------|------|
| 圆形悬浮球 | 可拖拽、始终置顶、半透明背景、柔和阴影 |
| 悬停触发卡片 | 鼠标放到球上 → 自动弹出卡片；离开球+卡片 → 自动关闭 |
| 拖拽过程不显示卡片 | 拖动悬浮球时已显示的卡片自动隐藏 |
| 四向吸边隐藏 | 靠近上/下/左/右任一边缘 → 隐藏一半；鼠标移近滑出 |
| 悬停反馈 | 鼠标悬停变色（#5BC0BE → #6FFFE9） |
| 文件拖拽拾取 | 拖文件到悬浮球 → 自动加入碎片池 |
| 右键菜单 | 打开主窗口 / 退出程序 |

### 小卡片（420×320，三模式）
| 模式 | 行为 |
|------|------|
| 📚 知识卡片 | 「下一张」切换随机卡片，悬停自动关闭 |
| 📋 日程任务 | 输入区 + 任务列表 + 右键菜单，锁定不自动关闭 |
| 📝 随时笔记 | 单条便签体验，800ms 防抖自动保存，锁定不自动关闭 |

### 大窗口主 UI（920×620，八面板）
| 面板 | 功能 |
|------|------|
| 🧩 碎片工作台 | 列表/筛选/搜索/合并/复制/删除/清空 |
| 📋 日程任务 | 输入/列表/批量勾选/右键编辑/批量删除/清除已完成 |
| 📝 笔记管理 | 列表 + 编辑区 + 自动保存 + 右键删除 |
| 📚 知识库 | 段落列表/勾选加入碎片池/右键增删改/外部修改检测/重新加载 |
| 🗂️ 临时素材 | 文件拖拽拾取/去重清理/预览/导入碎片池 |
| 🌐 网址导航 | 收藏网址增删改/一键打开 |
| 💻 软件导航 | 本地软件快捷方式增删改/图标提取/一键启动 |
| ⚙️ 设置 | 主题切换/剪贴板上限/自动隐藏秒数/卡片尺寸/关于 |

### 业务能力
| 特性 | 说明 |
|------|------|
| 全局划词捕获 | 被动监听剪贴板，自动收集文本/路径碎片 |
| 多槽剪贴板历史 | 上限可配置（默认 200 条），LRU 自动淘汰 |
| 知识卡片碎片标记 | 知识库段落可勾选加入碎片池 |
| 碎片合并 | 多选碎片 → 预览编辑 → 复制到剪贴板 / 存为笔记 |
| 文件拾取 | 拖文件到悬浮球生成文件路径碎片 |
| docx 增量更新 | mtime + sha1 指纹检测外部修改，段落 hash 检测内容变更 |
| 主题系统 | 浅色 / 深色双主题，QSS 模板 + 颜色字典统一管理，**初始默认深色**（改 `src/constants.py` 的 `DEFAULT_THEME` 即可换默认） |
| 单实例防护 | Windows 互斥量（CreateMutexW）防重复启动 |
| 原子写入 | 临时文件 + os.replace，避免写一半损坏 |
| 全局异常钩子 | 未捕获异常弹窗提示而非静默崩溃 |
| 窗口层级容错 | 屏幕分辨率变化/多屏漂移时位置自动兜底 |

### 退出方式（四选一）
- 按 **Esc** 键
- 右键悬浮球 → 退出程序
- 右键卡片 → 退出程序
- 大窗口设置面板的关闭按钮（仅隐藏，不退出）

---

## 二、环境要求

- **操作系统**：Windows 10 / 11
- **Python**：3.9 及以上（推荐 3.10 / 3.11 / 3.12）

---

## 三、安装依赖

```bash
pip install -r requirements.txt
```

依赖清单：
- PyQt6==6.7.1
- python-docx==1.1.2

---

## 四、启动方式

```bash
# 在 FloatPulse/ 目录下
python knowledge_ball.py
```

> 首次运行会在**本目录**自动创建 `data/`（含 `config.json` / `schedule.json` / `notes.json` /
> `fragments.json` / `nav.json` / `docx_meta.json` / `temp_assets.json`），无需手动准备；
> `知识库.docx` 也放在本目录，作为知识卡片的数据源。

---

## 五、模块职责

源码模块均位于 `src/`：

| 模块 | 职责 |
|------|------|
| `knowledge_ball.py`（入口） | FloatingBall 悬浮球 + main 入口 + 全局异常钩子 |
| `src/main_window.py` | 大窗口主 UI（容器 + 面板调度 + 无边框拖动/缩放） |
| `src/card_window.py` | 小卡片弹窗（7 个 Tab 页 + 页转场动画） |
| `src/fragments_panel.py` | 碎片工作台面板 |
| `src/tasks_panel.py` | 日程任务面板 |
| `src/notes_panel.py` | 笔记管理面板 |
| `src/knowledge_panel.py` | 知识库面板 |
| `src/assets_panel.py` | 临时素材面板 |
| `src/nav_panel.py` | 网址导航面板 |
| `src/settings_panel.py` | 设置面板 |
| `src/widget_app_launcher.py` | 软件导航（图标提取 / 启动 / 页面） |
| `src/merge_preview_dialog.py` | 碎片合并预览对话框 |
| `src/fragment_edit_dialog.py` | 碎片编辑对话框 |
| `src/glass_dialog.py` | 玻璃壳风格对话框基类 |
| `src/global_search_dialog.py` | 全局搜索对话框 |
| `src/quick_capture.py` | 快速捕获（划词即存） |
| `src/theme.py` | 主题系统（颜色字典 + QSS 模板） |
| `src/app_paths.py` | 路径 / 图标 / 屏幕尺寸工具（含项目根定位） |
| `src/controls.py` | 设置页可复用控件（`Stepper` 数字步进器：± 按钮 / 长按连续调整 / 直接键入） |
| `src/glass.py` | 玻璃壳组件（GlassPanel 高光/描边/噪点、NavIndicator 指示条、柔和阴影） |
| `src/constants.py` | 共享常量 + 容错工具（safe_int / 损坏备份 / 文件名净化） |
| `src/config.py` | 配置管理器 |
| `src/json_store.py` | JSON 原子读写底层 |
| `src/task_manager.py` | 日程任务管理器 |
| `src/task_delegate.py` | 任务委派（列表项绘制/交互代理） |
| `src/note_manager.py` | 笔记管理器 |
| `src/fragment_manager.py` | 碎片管理器（统一模型 + 去抖写盘） |
| `src/nav_manager.py` | 网址导航数据管理 |
| `src/docx_manager.py` | docx 读取 / 可控写入 / 增量同步 |
| `src/clipboard_monitor.py` | 剪贴板被动监听 |
| `src/temp_asset_manager.py` | 临时素材管理（去重 / 淘汰 / 过期清理） |
| `src/global_hotkey.py` | 全局热键注册（独立消息泵线程） |
| `src/fullscreen_watcher.py` | 全屏检测（全屏时自动隐藏） |
| `src/autostart.py` | 开机自启注册表读写 |
| `src/single_instance.py` | 单实例锁（Windows 互斥量） |
| `src/logger.py` | 日志与全局异常钩子 |

资源与数据不在源码目录内，统一放在项目根（见「〇、目录结构」）。

---

## 六、数据文件说明

### 6.1 知识库.docx（知识卡片数据源）
- **仅支持 `.docx` 格式**，不支持旧版 `.doc`
- 每个非空段落（去首尾空格后长度 ≥ 4）作为一张知识卡片
- 空段落、过短段落自动过滤
- 文件名固定为 `知识库.docx`，支持运行中编辑：右键段落 → 编辑/新增/删除，修改后自动写回 docx

**文件位置（与运行方式绑定，不可改名/移动）**：

| 运行方式 | docx 应放的位置 |
|----------|----------------|
| 源码运行（`python knowledge_ball.py`） | **项目根**（与 `src/`、`data/` 同级） |
| 打包运行（FloatPulse.exe） | **exe 同一文件夹** |

- 位置由 `src/app_paths.py::get_base_dir()` 定位：源码运行自动向上找到项目根，打包运行自动取 exe 所在目录
- 文件缺失或没有有效段落时**程序仍可启动**，知识卡片模式提示无内容
- **外部编辑**：直接用 Word/WPS 打开该 docx 修改并保存 → 主窗口知识库面板提示「⚠️ 检测到外部修改」→ 点「🔄 重新加载」立即生效；程序启动时也会自动检测
- `data/docx_meta.json` 是 docx 的指纹缓存（mtime + sha1 + 段落哈希），由程序自动生成与维护，**请勿手工编辑**（删掉后会自动重建，仅丢失"外部修改"检测基准）

### 6.2 schedule.json（日程任务）
- 字段：task_id / title / note / deadline / done / created_at
- task_id 自增不复用，删除严格按 id 过滤
- JSON 损坏时自动初始化空列表，不崩溃

### 6.3 notes.json（笔记）
- 字段：note_id / content / create_time / update_time
- note_id 自增不复用，删除严格按 id 过滤
- 与 schedule.json 完全隔离

### 6.4 fragments.json（碎片统一存储）
- 字段：fragment_id / type / content / source / created_at
- type 取值：`clipboard_text` / `clipboard_path` / `file_pickup` / `knowledge_segment`
- 统一承载剪贴板文本/路径、文件拾取、知识段落四类碎片

### 6.5 temp_assets.json（临时素材索引）
- 记录 `temp_assets/` 下素材的元信息，用于去重、淘汰与过期清理
- 素材实体文件存放在 `temp_assets/` 目录

### 6.6 docx_meta.json（docx 指纹）
- 存放 mtime + sha1 指纹，用于检测外部修改
- 启动时若发现 docx 被外部修改，弹窗询问是否重新加载

### 6.7 config.json（配置）
- 字段：theme / clipboard_max_items / auto_hide_seconds 等
- 修改后通过 ConfigManager.save() 原子写入

---

## 七、交互操作速查

### 悬浮球
| 操作 | 行为 |
|------|------|
| 鼠标悬停 | 自动弹出卡片 |
| 拖拽球 | 移动位置；拖拽中不显示卡片 |
| 拖到屏幕边缘释放 | 吸边隐藏一半（上/下/左/右均可） |
| 鼠标移近吸边的球 | 自动滑出 |
| 点击球（未拖动） | 知识卡片模式：切换下一张 |
| 右键球 | 菜单：打开主窗口 / 退出程序 |
| 拖文件到球 | 自动加入碎片池 |

### 小卡片
| 操作 | 行为 |
|------|------|
| 顶部「📚 知识卡片」 | 切换到知识卡片模式（悬停自动关闭） |
| 顶部「📋 日程任务」 | 切换到日程任务模式（锁定不关闭） |
| 顶部「📝 随时笔记」 | 切换到笔记模式（锁定不关闭） |
| 日程/笔记模式右上角「×」 | 手动关闭卡片 |
| 右键卡片 | 退出菜单 |

### 大窗口
| 操作 | 行为 |
|------|------|
| 左侧导航按钮 | 切换八个面板 |
| 顶部 🌙 按钮 | 切换深色/浅色主题 |
| 顶部 — 按钮 | 最小化 |
| 顶部 × 按钮 | 关闭窗口（仅隐藏，不退出程序） |
| 拖动顶部标题栏 | 移动窗口 |
| 各列表右键 | 上下文菜单（编辑/删除等） |

---

## 八、PyInstaller 打包

> 采用 **onedir（文件夹）** 方式打包，运行时需保证整个 `FloatPulse/` 目录完整；不推荐 `--onefile` 单文件方式。

### 1. 安装打包工具

```bash
pip install pyinstaller
```

### 2. 打包

```bash
# 在 FloatPulse/ 目录下
pyinstaller --noconfirm --clean FloatPulse.spec
```

### 3. 获取产物

```
dist/FloatPulse/FloatPulse.exe        # 主程序
dist/FloatPulse/_internal/            # PyQt6 等依赖
```

打包后需**手动把 `知识库.docx` 拷到 exe 同级**（用户数据，外部可改）。

### 4. spec 的轻量过滤说明

`FloatPulse.spec` 针对纯 Widgets 应用做了精简（约 44 MB → 31 MB）：

| 过滤项 | 体积 | 原因 |
|---|---|---|
| `opengl32sw.dll` | 19.7 MB | 软件 OpenGL 渲染器，仅 QML/3D 需要 |
| `Qt6Pdf.dll` | 5.1 MB | 项目无 PDF 渲染需求 |
| `Qt6Svg.dll` + 插件 | 0.7 MB | 项目无 svg 资源 |
| `translations/` | ~6 MB | UI 全自绘中文，不需要 Qt 翻译 |
| `ssl` / `unicodedata` | ~14 MB | 程序只用 socket 不用 ssl |

> 过滤项均经冒烟验证；若后续引入 PDF 预览、SVG 图标或 HTTPS 请求，
> 需从 `excludes` / `_SKIP_PREFIXES` 中回滚对应条目。

---

## 九、部署注意事项（重要）

1. **exe 必须和 `知识库.docx` 放在同一文件夹**，否则知识卡片模式无内容（程序仍可运行）。
2. **`schedule.json` / `notes.json` / `fragments.json` / `docx_meta.json` / `config.json` 会自动生成在 exe 同目录**，跨电脑迁移时一起拷贝即可保留数据。
3. **仅支持 `.docx` 格式**，不支持旧版 `.doc`。
4. 单实例限制：重复双击 exe 会弹「已在运行中」提示。
5. 跨电脑部署：将 `dist\FloatPulse\` 整个文件夹 + `知识库.docx`（+ 可选 json 数据文件）拷贝到目标电脑同一文件夹即可运行，**目标电脑无需安装 Python**。

---

## 十、三层架构

### UI 层
| 类 | 文件 | 职责 |
|----|------|------|
| `FloatingBall` | knowledge_ball.py | 悬浮球（拖拽、吸边、悬停、文件拾取） |
| `CardWindow` | card_window.py | 小卡片弹窗（三模式切换） |
| `MainWindow` | main_window.py | 大窗口主 UI（八面板容器 + 调度） |
| `FragmentsPanel` | fragments_panel.py | 碎片工作台面板 |
| `TasksPanel` | tasks_panel.py | 日程任务面板 |
| `NotesPanel` | notes_panel.py | 笔记管理面板 |
| `KnowledgePanel` | knowledge_panel.py | 知识库面板 |
| `AssetsPanel` | assets_panel.py | 临时素材面板 |
| `NavPanel` | nav_panel.py | 网址导航 + 软件导航面板 |
| `SettingsPanel` | settings_panel.py | 设置面板 |
| `MergePreviewDialog` | merge_preview_dialog.py | 碎片合并预览对话框 |
| `GlobalSearchDialog` | global_search_dialog.py | 全局搜索对话框 |

### 业务层
| 类 | 文件 | 职责 |
|----|------|------|
| `TaskManager` | task_manager.py | 任务 CRUD + schedule.json 持久化 |
| `NoteManager` | note_manager.py | 笔记 CRUD + notes.json 持久化 |
| `FragmentManager` | fragment_manager.py | 碎片 CRUD + fragments.json 持久化 |
| `DocxManager` | docx_manager.py | docx 读取/写入 + 增量同步 |
| `ClipboardMonitor` | clipboard_monitor.py | 剪贴板被动监听 + 碎片入库 |
| `TempAssetManager` | temp_asset_manager.py | 临时素材去重/淘汰 |
| `ConfigManager` | config.py | 配置读写 + 校验 |
| `SingleInstance` | single_instance.py | Windows 互斥量单实例锁 |
| `GlobalHotkey` | global_hotkey.py | 全局热键注册 |

### 数据层
- docx（知识库）/ schedule.json / notes.json / fragments.json / docx_meta.json / temp_assets.json / config.json

---

## 十一、设计要点

- **三层架构**：UI 层 / 业务层 / 数据层严格分离，UI 不直接碰数据文件
- **模块化拆分**：原巨型 main_window.py（3000+ 行）已按功能拆分为 8 个独立面板模块 + 工具/常量模块，便于维护
- **数据隔离**：七类数据文件各自独立，互不干扰
- **id 主键**：task_id / note_id / fragment_id 均自增不复用，删除严格按 id
- **内存优先**：所有改动先操作内存列表，完毕统一 `_save()` 写盘
- **原子写入**：临时文件 + `os.replace`，避免写一半损坏
- **异常防护**：JSON 解析失败 / 文件缺失均不崩溃，自动初始化空数据
- **路径兼容**：`get_project_root()` 自动适配源码运行与 PyInstaller 打包环境
- **全局异常钩子**：未捕获异常弹窗提示而非静默崩溃
- **窗口层级容错**：屏幕分辨率变化 / 多屏坐标漂移时位置自动兜底
- **主题系统**：浅色/深色双主题，QSS 模板 + 颜色字典统一管理，大小窗口联动切换
- **信号槽桥梁**：大小窗口通过信号槽双向同步数据，避免直接耦合

---

## 十二、测试与验证

### 单元测试（pytest）

```bash
pip install pytest

cd FloatPulse && pytest tests/            # 在项目目录下
# 或从仓库根：
pytest FloatPulse/tests/
```

覆盖 121 个用例 / 3 个跳过，包括：

| 测试文件 | 覆盖内容 |
|---|---|
| `tests/test_logic.py` | 碎片/任务/笔记/配置核心逻辑、边界与容错 |
| `tests/test_json_store_guard.py` | JSON 存储守卫（损坏、并发、原子性） |
| `tests/test_host_attribute_contract.py` | UI 宿主属性契约（静态 AST 扫描） |
| `tests/test_nav_drag_invariants.py` | 导航拖拽不变式（不越界、不重排丢失） |
| `tests/test_theme_contrast.py` | 双主题对比度与关键 token 完备性 |

### 初始化自检

```bash
python test_init.py
```

创建所有管理器实例 + 大窗口 + 悬浮球，500ms 后自动退出，验证：
- 各 manager 初始化正常
- 大窗口 + 悬浮球显示无异常
- 信号槽桥梁连接成功
- 8 个面板切换正常
- 主题切换（深色/浅色）正常

### 设计验证脚本（`tools/`）

离屏渲染 + 交互回归，用于对照 `宣传页/` 与实机效果图：

| 脚本 | 用途 |
|---|---|
| `shot_ui.py light` / `dark` | 把主窗口 / 卡片 / 悬浮球渲染成 PNG（自动合成到模拟桌面上，便于评估半透明观感） |
| `verify_nav_drag.py` / `verify_nav_live_letway.py` | 导航拖拽行为与实时让位回归 |
| `verify_card_nav_grid.py` | 小卡片网址导航双列布局与溢出护栏 |
| `verify_card_asset_perf.py` | 素材页加载性能 |
| `verify_asset_thumb_setting.py` | 缩略图尺寸设置项 |
| `verify_quick_capture.py` | 快速捕获流程 |
| `verify_ball_drop_apps.py` | 拖拽应用到悬浮球 |
| `demo_acrylic.py` / `demo_bg_preview.py` | 亚克力/背景叠加预览 |
| `check_transition.py` / `qa_verify_nav_drag.py` | 页转场与 QA 校验 |

> 脚本输出统一落在 `设计稿/`（不存在时自动创建）。运行需本机安装 PyQt6。

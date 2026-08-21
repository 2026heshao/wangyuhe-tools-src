# 生活悬浮球

基于 **PyQt6 原生控件 + QSS** 开发的 Windows 桌面常驻悬浮球工具。
圆形悬浮球 + 420×320 无边框置顶小卡片弹窗 + 独立完整大窗口主 UI，三层架构、业务与 UI 完全解耦。

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

### 大窗口主 UI（920×620，五面板）
| 面板 | 功能 |
|------|------|
| 🧩 碎片工作台 | 列表/筛选/搜索/合并/复制/删除/清空 |
| 📋 日程任务 | 输入/列表/批量勾选/右键编辑/批量删除/清除已完成 |
| 📝 笔记管理 | 列表 + 编辑区 + 自动保存 + 右键删除 |
| 📚 知识库 | 段落列表/勾选加入碎片池/右键增删改/外部修改检测/重新加载 |
| ⚙️ 设置 | 主题切换/剪贴板上限/自动隐藏秒数/关于 |

### 业务能力
| 特性 | 说明 |
|------|------|
| 全局划词捕获 | 被动监听剪贴板，自动收集文本/路径碎片 |
| 多槽剪贴板历史 | 上限可配置（默认 200 条），LRU 自动淘汰 |
| 知识卡片碎片标记 | 知识库段落可勾选加入碎片池 |
| 碎片合并 | 多选碎片 → 预览编辑 → 复制到剪贴板 / 存为笔记 |
| 文件拾取 | 拖文件到悬浮球生成文件路径碎片 |
| docx 增量更新 | mtime + sha1 指纹检测外部修改，段落 hash 检测内容变更 |
| 主题系统 | 浅色 / 深色双主题，QSS 模板 + 颜色字典统一管理 |
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

## 四、直接运行

确保数据文件与 `knowledge_ball.py` 在**同一文件夹**，然后：

```bash
python knowledge_ball.py
```

> 首次运行会自动创建 `schedule.json` / `notes.json` / `fragments.json` / `docx_meta.json` / `config.json`，无需手动准备。

---

## 五、文件结构

```
生活悬浮球/
├── knowledge_ball.py        # 主程序入口（FloatingBall + main + 全局异常钩子）
├── card_window.py           # 小卡片弹窗（CardWindow + 三模式）
├── main_window.py           # 大窗口主 UI（MainWindow + 五面板 + MergePreviewDialog）
├── single_instance.py       # 单实例锁（Windows 互斥量）
├── theme.py                 # 主题系统（颜色字典 + QSS 模板）
├── config.py                # 配置管理器（ConfigManager）
├── task_manager.py          # 日程任务管理器（Task + TaskManager）
├── note_manager.py          # 笔记管理器（Note + NoteManager）
├── fragment_manager.py      # 碎片管理器（Fragment + FragmentManager，统一模型）
├── clipboard_monitor.py     # 剪贴板监听器（被动捕获 + 碎片入库）
├── docx_manager.py          # docx 管理器（读取 + 可控写入 + 增量同步）
├── test_init.py             # 初始化测试脚本
├── requirements.txt         # Python 依赖清单
├── 知识卡片悬浮球.spec       # PyInstaller 打包配置
├── README.md                # 本说明文档
├── 知识库.docx              # 知识库数据源（需用户自备）
├── schedule.json            # 日程任务数据（自动生成）
├── notes.json               # 笔记数据（自动生成）
├── fragments.json           # 碎片数据（自动生成）
├── docx_meta.json           # docx 指纹元数据（自动生成）
└── config.json              # 配置数据（自动生成）
```

---

## 六、数据文件说明

### 6.1 知识库.docx（知识卡片数据源）
- **仅支持 `.docx` 格式**，不支持旧版 `.doc`
- 每个非空段落（去首尾空格后长度 ≥ 4）作为一张知识卡片
- 空段落、过短段落自动过滤
- 文件名固定为 `知识库.docx`，与程序同目录
- 支持运行中编辑：右键段落 → 编辑/新增/删除，修改后自动写回 docx

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

### 6.5 docx_meta.json（docx 指纹）
- 存放 mtime + sha1 指纹，用于检测外部修改
- 启动时若发现 docx 被外部修改，弹窗询问是否重新加载

### 6.6 config.json（配置）
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
| 左侧导航按钮 | 切换五个面板 |
| 顶部 🌙 按钮 | 切换深色/浅色主题 |
| 顶部 — 按钮 | 最小化 |
| 顶部 × 按钮 | 关闭窗口（仅隐藏，不退出程序） |
| 拖动顶部标题栏 | 移动窗口 |
| 各列表右键 | 上下文菜单（编辑/删除等） |

---

## 八、PyInstaller 打包为单 exe

### 1. 安装打包工具

```bash
pip install pyinstaller==6.10.0
```

### 2. 使用 spec 文件打包（推荐）

```bash
pyinstaller "知识卡片悬浮球.spec"
```

### 3. 或使用命令行打包

```bash
pyinstaller --onefile --windowed --name "知识卡片悬浮球" knowledge_ball.py
```

> 所有 manager 模块作为同目录 import，PyInstaller 会自动识别并打包进 exe。

### 4. 获取 exe

打包完成后位于：

```
dist\知识卡片悬浮球.exe
```

---

## 九、部署注意事项（重要）

1. **exe 必须和 `知识库.docx` 放在同一文件夹**，否则知识卡片模式无内容（程序仍可运行）。
2. **`schedule.json` / `notes.json` / `fragments.json` / `docx_meta.json` / `config.json` 会自动生成在 exe 同目录**，跨电脑迁移时一起拷贝即可保留数据。
3. **仅支持 `.docx` 格式**，不支持旧版 `.doc`。
4. 单实例限制：重复双击 exe 会弹「已在运行中」提示。
5. 跨电脑部署：将 `知识卡片悬浮球.exe` + `知识库.docx`（+ 可选 json 数据文件）拷贝到目标电脑同一文件夹即可运行，**目标电脑无需安装 Python**。

---

## 十、三层架构

### UI 层
| 类 | 文件 | 职责 |
|----|------|------|
| `FloatingBall` | knowledge_ball.py | 悬浮球（拖拽、吸边、悬停、文件拾取） |
| `CardWindow` | card_window.py | 小卡片弹窗（三模式切换） |
| `MainWindow` | main_window.py | 大窗口主 UI（五面板） |
| `MergePreviewDialog` | main_window.py | 碎片合并预览对话框 |

### 业务层
| 类 | 文件 | 职责 |
|----|------|------|
| `TaskManager` | task_manager.py | 任务 CRUD + schedule.json 持久化 |
| `NoteManager` | note_manager.py | 笔记 CRUD + notes.json 持久化 |
| `FragmentManager` | fragment_manager.py | 碎片 CRUD + fragments.json 持久化 |
| `DocxManager` | docx_manager.py | docx 读取/写入 + 增量同步 |
| `ClipboardMonitor` | clipboard_monitor.py | 剪贴板被动监听 + 碎片入库 |
| `ConfigManager` | config.py | 配置读写 + 校验 |
| `SingleInstance` | single_instance.py | Windows 互斥量单实例锁 |

### 数据层
- docx（知识库）/ schedule.json / notes.json / fragments.json / docx_meta.json / config.json

---

## 十一、设计要点

- **三层架构**：UI 层 / 业务层 / 数据层严格分离，UI 不直接碰数据文件
- **模块化拆分**：原 monolithic 文件已拆为 12+ 独立模块，便于维护
- **数据隔离**：六类数据文件各自独立，互不干扰
- **id 主键**：task_id / note_id / fragment_id 均自增不复用，删除严格按 id
- **内存优先**：所有改动先操作内存列表，完毕统一 `_save()` 写盘
- **原子写入**：临时文件 + `os.replace`，避免写一半损坏
- **异常防护**：JSON 解析失败 / 文件缺失均不崩溃，自动初始化空数据
- **路径兼容**：`_get_base_dir()` 自动适配源码运行与 PyInstaller 打包环境
- **全局异常钩子**：未捕获异常弹窗提示而非静默崩溃
- **窗口层级容错**：屏幕分辨率变化 / 多屏坐标漂移时位置自动兜底
- **主题系统**：浅色/深色双主题，QSS 模板 + 颜色字典统一管理，大小窗口联动切换
- **信号槽桥梁**：大小窗口通过信号槽双向同步数据，避免直接耦合

---

## 十二、测试与验证

### 语法检查
```bash
python _syntax_check.py
```
对所有 12 个模块逐一 `py_compile`，输出 `[OK]/[FAIL]` 列表。

### 初始化测试
```bash
python test_init.py
```
创建所有管理器实例 + 大窗口 + 悬浮球，500ms 后自动退出，验证：
- 各 manager 初始化正常
- 大窗口 + 悬浮球显示无异常
- 信号槽桥梁连接成功
- 5 个面板切换正常
- 主题切换（深色/浅色）正常

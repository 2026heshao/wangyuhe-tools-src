# PyPacker - Python一键EXE打包工具

基于 **PyQt6 + PyInstaller** 开发的 Windows 平台可视化 GUI 打包工具。图形化配置所有打包参数，替代手写命令行，一键将 Python 源码编译为 Windows EXE 可执行程序。

## 功能特性

- 图形化配置 PyInstaller 全部核心参数，无需手写命令行
- 内置两套官方模板：普通Python脚本模板、PyQt6-WebEngine模板
- 支持用户自定义模板的保存、加载、删除（本地JSON持久化）
- 主入口文件自动校验，非法路径标红提示并锁定打包按钮
- 支持虚拟环境（venv）打包，优先使用干净独立环境
- 附加依赖收集（--collect-all）与排除库（--exclude-module）可视化配置
- 后台子线程异步打包，完全不卡死UI，实时流式日志输出
- 日志彩色分层：普通信息（白）、警告（橙）、错误（红）、成功（绿）
- 一键复制完整PyInstaller命令，方便手动调试
- 打包前自动检测PyInstaller，未安装支持一键pip安装
- 所有配置本地JSON持久化，重启软件自动恢复
- 打包期间UI完全锁定，防止参数错乱
- 深色极简开发工具风，固定960×720窗口

## 项目结构

```
PyPacker/
├── main.py              # 程序入口
├── ui_main.py           # 主窗口UI（深色主题、所有面板、交互逻辑）
├── packager.py          # 打包核心逻辑（命令拼接、环境检测、异步子线程）
├── templates.py         # 模板管理（内置模板 + 用户自定义模板）
├── config.py            # 配置持久化（本地JSON读写）
├── requirements.txt     # 依赖清单
└── README.md            # 说明文档
```

## 安装与运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

或手动安装：

```bash
pip install PyQt6 pyinstaller
```

### 2. 运行程序

```bash
python main.py
```

## 使用说明

### 快速开始

1. **选择主入口PY文件**：点击「浏览」选择你的Python主程序（.py文件），项目根目录会自动识别填充
2. **配置打包参数**：
   - 输出模式：单文件(-F) 或 文件夹(-D)，默认文件夹模式
   - 控制台模式：GUI无控制台(-w) 或 保留控制台(-c)，默认保留控制台
   - 可选：自定义ICO图标、附加依赖收集、排除库、输出目录
3. **点击「开始打包」**：程序自动校验配置、检测环境，然后后台异步打包
4. **查看日志**：下半区实时显示打包过程，成功后「打开输出目录」按钮自动解锁

### 模板使用

- **加载模板**：下拉选择模板 → 点击「加载模板」，自动覆盖右侧打包参数
- **保存模板**：配置好参数后 → 点击「保存为模板」→ 输入名称，永久保存到本地
- **删除模板**：选择用户自定义模板 → 点击「删除模板」（内置官方模板不可删除）

### PyQt6-WebEngine项目打包

直接选择「PyQt6-WebEngine模板」并加载，程序会自动：
- 切换为GUI无控制台模式
- 预填 `PyQt6.QtWebEngine`、`PyQt6.QtWebEngineCore`、`PyQt6.QtWebEngineWidgets` 依赖收集
- 解决WebEngine打包缺库报错问题

### 虚拟环境打包

在「虚拟环境路径」中选择本地venv目录，程序将优先使用该环境中的Python解释器和依赖进行打包，确保环境干净独立。留空则使用系统全局Python。

## 配置文件说明

程序运行后会在同目录生成两个JSON文件：

- `pypacker_config.json`：保存所有表单配置，重启自动恢复
- `pypacker_templates.json`：保存用户自定义模板

## 常见问题

**Q: 提示未检测到PyInstaller？**
A: 点击底部「安装PyInstaller」按钮一键安装，或手动执行 `pip install pyinstaller`

**Q: 打包后EXE运行提示缺库？**
A: 在「附加依赖收集」中逐行填写缺失的库名（如 `PyQt6.QtWebEngine`），程序会自动添加 `--collect-all` 参数

**Q: 打包体积太大？**
A: 在「排除打包库」中填写不需要的第三方库（如 `tkinter`、`test`），程序会自动添加 `--exclude-module` 参数

**Q: 打包过程中想修改参数？**
A: 打包期间所有配置控件自动锁定，需等待打包完成或关闭程序重新打开

## 技术栈

- **GUI框架**：PyQt6
- **打包引擎**：PyInstaller
- **异步执行**：QThread + subprocess 流式读取
- **持久化**：JSON本地存储
- **平台**：Windows 10/11

## 版本

v1.0.0

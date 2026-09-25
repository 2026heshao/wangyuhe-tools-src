# WangYuHe 工具箱（源码）

本仓库包含作者开发的几款 Windows 小工具的源码，均基于 Python 构建，以 **MIT 许可证**开源。

## 包含工具

| 工具 | 说明 | 最新版本 | 安装包（Release） | 宣传页 |
|------|------|------|------|------|
| **LaunchDeck** | 桌面快捷启动悬浮球 | **v2.2.4** | [下载 ZIP](https://github.com/2026heshao/wangyuhe-tools-src/releases/download/launchdeck-v2.2.4/LaunchDeck_v2.2.4.zip)（约 51 MB，免安装） | [查看](LaunchDeck/宣传页/) |
| **FloatPulse** | 知识库悬浮球 | **v3.0** | [下载 ZIP](https://github.com/2026heshao/wangyuhe-tools-src/releases/download/floatpulse-v3.0/FloatPulse.zip)（约 43 MB，免安装） | [查看](FloatPulse/宣传页/) |
| **CacheClear** | 软件缓存清理工具 | v1.2 | [下载 EXE](https://github.com/2026heshao/wangyuhe-tools-src/releases/download/cacheclear-v1.2/CacheClear_setup_v1.2.exe)（约 25 MB） | — |
| **PyPacker** | Python 打包辅助工具 | v1.0 | [下载 EXE](https://github.com/2026heshao/wangyuhe-tools-src/releases/download/pypacker-v1.0/PyPacker_setup_v1.0.exe)（约 26 MB） | — |

> 安装包通过 GitHub Releases 分发；源码在本仓库各子目录中。
>
> LaunchDeck 与 FloatPulse 已改为**免安装 ZIP**，解压即用，无需管理员权限；CacheClear、PyPacker 仍为安装包 EXE。

<details>
<summary>历史版本（旧版安装包，仍可下载）</summary>

| 工具 | 版本 | 安装包（Release） |
|------|------|------|
| LaunchDeck | v1.0 | [下载 EXE](https://github.com/2026heshao/wangyuhe-tools-src/releases/download/launchdeck-v1.0/LaunchDeck_setup_v1.0.exe) |
| FloatPulse | v1.1 | [下载 EXE](https://github.com/2026heshao/wangyuhe-tools-src/releases/download/floatpulse-v1.1/FloatPulse_set_up1.2.exe) |

</details>

## 宣传页

每个工具都有一份可独立打开的宣传页（纯 HTML，双击即看，无外部依赖）：

- **LaunchDeck** → [`LaunchDeck/宣传页/index.html`](LaunchDeck/宣传页/)
- **FloatPulse** → [`FloatPulse/宣传页/index.html`](FloatPulse/宣传页/)

> 页内下载按钮指向本仓库对应 Release 的直链。本地另有一份「相对路径版」用于其他服务器托管，两者内容一致、仅下载链接不同。

## 目录结构

```
wangyuhe-tools-src/
├── LaunchDeck/    # 桌面快捷启动悬浮球（含 core/ ui/ 与 宣传页/）
├── CacheClear/    # 软件缓存清理
├── FloatPulse/    # 知识库悬浮球（含 src/ 与 宣传页/）
└── PyPacker/      # Python 打包辅助
```

每个子目录是独立项目，运行所需依赖见各子目录的 `README.md` / `requirements.txt`。

## 相关链接

- 宣传页（GitHub Pages）：https://2026heshao.github.io/wangyuhe-tools/
- 全部发行版本：https://github.com/2026heshao/wangyuhe-tools-src/releases

## 许可证

[MIT](LICENSE) © 2026 WangYuHe

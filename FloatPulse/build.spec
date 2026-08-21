# -*- mode: python ; coding: utf-8 -*-
"""
====================================================================
PyInstaller 打包配置文件  -  build.spec
====================================================================
使用方式：
  pyinstaller build.spec

打包产物（dist/ 目录）：
  ├── 生活悬浮球.exe        主程序
  ├── 知识库.docx           知识库数据文件（用户可自由替换）
  ├── favicon.ico           程序图标
  └── _internal/            PyQt6 及其他依赖

设计要点：
  1. docx 和 ico 作为外部资源放在 exe 同目录，用户可自由替换 docx
  2. data/ 和 temp_assets/ 目录运行时自动创建，无需打包
  3. 控制台隐藏（--noconsole），双击 exe 不弹黑窗
  4. 单实例限制由程序内部 Windows mutex 实现
  5. 图标使用 favicon.ico

更换知识库：
  1. 关闭程序
  2. 用新的"知识库.docx"替换 dist/ 目录里的同名文件
  3. 重新启动 exe
====================================================================
"""

import os

block_cipher = None

a = Analysis(
    ['knowledge_ball.py'],
    pathex=[],
    binaries=[],
    datas=[
        # (源文件, 目标目录)  '.' 表示 exe 同目录
        ('知识库.docx', '.'),
        ('FloatPulse.ico', '.'),
    ],
    hiddenimports=[
        # 显式声明可能被遗漏的模块
        'src.logger',
        'src.config',
        'src.task_manager',
        'src.note_manager',
        'src.fragment_manager',
        'src.clipboard_monitor',
        'src.docx_manager',
        'src.nav_manager',
        'src.temp_asset_manager',
        'src.single_instance',
        'src.card_window',
        'src.main_window',
        'src.theme',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的模块，减小体积
        'tkinter',
        'unittest',
        'pydoc',
        'doctest',
        'argparse',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='生活悬浮球',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                    # 使用 UPX 压缩，减小体积
    upx_exclude=[
        # UPX 压缩排除项（某些 dll 压缩后会出问题）
        'vcruntime140.dll',
        'vcruntime140_1.dll',
        'python3.dll',
    ],
    runtime_tmpdir=None,
    console=False,               # 隐藏控制台
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='FloatPulse.ico',       # 程序图标
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        'vcruntime140.dll',
        'vcruntime140_1.dll',
        'python3.dll',
    ],
    name='生活悬浮球',
)

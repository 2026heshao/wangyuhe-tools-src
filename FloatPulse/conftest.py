# -*- coding: utf-8 -*-
"""pytest 配置：保证 `tests/` 下可以直接 `from src.xxx import`。

无论从项目目录还是仓库根运行 pytest，都把本项目根（本文件所在目录）
加入 sys.path：

    cd FloatPulse && pytest tests/
    cd <repo root> && pytest FloatPulse/tests/
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

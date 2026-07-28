# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置文件。

严格遵循设计文档 8.4 节与规范文档 8.1 节。
使用 --onedir 模式（启动快于 onefile），产物为 dist/XieFengShiYing/ 目录。

打包命令::

    pyinstaller XieFengShiYing.spec --noconfirm

产物验证::

    dist/XieFengShiYing/XieFengShiYing.exe
    dist/XieFengShiYing/_internal/ui/assets/style.qss
    dist/XieFengShiYing/_internal/ui/assets/cookie_tutorial/
    dist/XieFengShiYing/_internal/assets/icon.ico
"""

from pathlib import Path

block_cipher = None

# 项目根目录（SPECPATH 由 PyInstaller 运行时注入）
_PROJECT_ROOT = Path(SPECPATH)

# 附加资源：(源路径, 目标路径)
_datas = [
    ("ui/assets", "ui/assets"),
    ("assets", "assets"),
]

# PyInstaller 静态分析可能漏掉的动态导入模块
_hiddenimports = [
    # PySide6 子模块
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "PySide6.QtGui",
    # httpx 及 HTTP/2 依赖
    "httpx",
    "h2",
    "hpack",
    "hyperframe",
    "downloader.constants",
    "app.preview_models",
]

# 排除的模块（减小体积：测试专用依赖与未使用的工具链）
_excludes = [
    "pytest",
    "pytest_asyncio",
    "pytest_cov",
    "pytest_qt",
    "vcrpy",
    "respx",
    "ruff",
    "black",
    "mypy",
    "pip",
    "setuptools",
    "wheel",
]

a = Analysis(
    ["main.py"],
    pathex=[str(_PROJECT_ROOT)],
    binaries=[],
    datas=_datas,
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
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
    name="XieFengShiYing",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # --windowed：无控制台窗口
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="XieFengShiYing",
)

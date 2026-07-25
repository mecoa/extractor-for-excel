# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置 —— Windows onefile exe
#
# 用法 (在 Windows 上):
#   uv run pyinstaller build/windows.spec
# 产物: dist/ExtractorForExcel.exe
#
# 说明:
#   - datas 把前端 web/static 打进 exe (运行时解包到 sys._MEIPASS/web/static)
#   - hiddenimports 覆盖 uvicorn / pandas / openpyxl 的动态导入
import os

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# 项目根目录 (spec 位于 packaging/ 下, SPECPATH 由 PyInstaller 注入)
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

hiddenimports = []
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("pandas")
hiddenimports += collect_submodules("openpyxl")
hiddenimports += [
    "core", "models", "web",
    "web.server", "web.service",
]

datas = [
    (os.path.join(ROOT, "web", "static"), os.path.join("web", "static")),
]
datas += collect_data_files("openpyxl")

a = Analysis(
    [os.path.join(ROOT, "desktop_main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ExtractorForExcel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

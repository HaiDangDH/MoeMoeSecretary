# -*- mode: python ; coding: utf-8 -*-
# Đóng gói: một file MoeMoeSecretary.exe duy nhất, không cửa sổ CMD (console=False).
# Build:  pyinstaller --noconfirm --clean MoeMoeSecretary.spec   (hoặc nhấp đúp build_exe.bat)
#
# Lưu ý: config.yaml và cache/ KHÔNG nằm trong .exe - chương trình tạo/đọc chúng ngay
# cạnh file .exe (xem src/paths.py, dùng Path(sys.executable).parent, không dùng _MEIPASS).
import os

from PyInstaller.utils.hooks import collect_data_files

ICON = os.path.join(SPECPATH, "assets", "icon.ico")

# ---- Loại bỏ module nặng / không dùng để .exe nhỏ gọn, khởi động nhanh -----------
EXCLUDES = [
    # Qt: không dùng trình duyệt nhúng, 3D, QML/Quick, đa phương tiện, SQL, biểu đồ...
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D", "PySide6.QtQuickControls2",
    "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtSql", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtNetwork",
    "PySide6.QtPrintSupport", "PySide6.QtConcurrent", "PySide6.QtDBus", "PySide6.QtXml",
    # Thư viện khoa học / giao diện khác
    "matplotlib", "numpy", "scipy", "pandas", "tkinter", "PyQt5", "PyQt6", "PySide2",
    "IPython", "jupyter", "notebook", "pytest", "unittest", "setuptools", "pip",
    "psutil", "pydoc", "doctest",
]

HIDDEN = [
    "_cffi_backend",      # miniaudio dùng cffi
    "lxml.etree", "lxml._elementpath",
    "yaml",
    "h2", "hpack", "hyperframe",   # HTTP/2 cho httpx
]

a = Analysis(
    ["main.py"],
    pathex=[SPECPATH],
    binaries=[],
    datas=collect_data_files("certifi"),   # kho chứng chỉ HTTPS cho httpx
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

# Bỏ các DLL lớn không cần cho ứng dụng Widgets dùng raster (tiết kiệm hàng chục MB)
_DROP_PREFIXES = (
    "opengl32sw", "d3dcompiler", "qt6quick", "qt6qml", "qt6pdf", "qt6virtualkeyboard",
    "qt6webengine", "qt63d", "qt6multimedia", "qt6opengl",
)
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).lower().startswith(_DROP_PREFIXES)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MoeMoeSecretary",
    icon=ICON if os.path.exists(ICON) else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX hay làm Qt DLL lỗi và dễ bị antivirus báo nhầm
    runtime_tmpdir=None,
    console=False,          # --windowed / --noconsole: không hiện cửa sổ CMD đen
    disable_windowed_traceback=False,
)

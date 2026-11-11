# -*- mode: python ; coding: utf-8 -*-
# Empaquetado portable del Programa Maestro — Jenway 6705.
# Dos ejecutables que comparten la misma carpeta (_internal):
#   Programa_Maestro.exe  ->  GUI de escritorio (ventana, sin consola)
#   Escanear_Serie.exe    ->  banco de pruebas RS-232 (consola)
#
# Uso:  pyinstaller --clean --noconfirm maestro_portable.spec
import os

RAIZ = os.path.abspath(SPECPATH)  # carpeta del spec (la raiz de maestro/)
os.chdir(RAIZ)

EXCLUSIONES = [
    # scipy solo se usa como oraculo en los tests; pytest solo para probar.
    "scipy",
    "pytest",
    # Modulos Qt que la app no toca (recortan ~150 MB del paquete).
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngine",
    "PySide6.QtPdf",
    "PySide6.QtMultimedia",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.QtNetwork",
    # Paquetes de pruebas de numpy/matplotlib.
    "numpy._core.tests",
    "numpy.f2py",
    "matplotlib.tests",
    "PIL.ImageTk",
    "tkinter",
]

COMUN = dict(
    pathex=[RAIZ],
    datas=[],
    binaries=[],
    hiddenimports=[],
    excludes=EXCLUSIONES,
    noarchive=False,
    optimize=0,
)

a_gui = Analysis(["Script/maestro_gui.py"], **COMUN)
a_serie = Analysis(["Script/escanear_serie.py"], **COMUN)

pyz_gui = PYZ(a_gui.pure)
pyz_serie = PYZ(a_serie.pure)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="Programa_Maestro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,   # ventana de escritorio: sin consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

exe_serie = EXE(
    pyz_serie,
    a_serie.scripts,
    [],
    exclude_binaries=True,
    name="Escanear_Serie",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,    # herramienta CLI: consola visible
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe_gui,
    a_gui.binaries,
    a_gui.datas,
    exe_serie,
    a_serie.binaries,
    a_serie.datas,
    name="Programa_Maestro",
)

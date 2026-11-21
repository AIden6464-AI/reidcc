# PyInstaller spec: one shared _internal, two front doors.
#   Reidcc.exe   windowed  -> always the GUI (double-click, Start Menu)
#   reidcc.com   console   -> TUI / CLI (typed in a terminal); renamed from reidcc-cli.exe by build.ps1
# Build: python\build\build.ps1   (output: E:\reidcc\app\)
import os
SRC = os.path.abspath(os.path.join(SPECPATH, ".."))   # python\: reid.py, reid_gui.py
ROOT = os.path.dirname(SRC)                           # the Reidcc folder: icon, assets
ICON = os.path.join(ROOT, "reidcc.ico")

a = Analysis(
    [os.path.join(SRC, "reid.py")],
    pathex=[SRC],
    datas=[(ICON, "."), (os.path.join(ROOT, "assets"), "assets")],  # banner, gate + its frames (make_assets.py)
    hiddenimports=["reid_gui", "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.font"],
    excludes=["PyQt5", "PyQt6", "PySide6", "numpy", "matplotlib", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Reidcc",
          console=False, icon=ICON, upx=False)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="reidcc-cli",
          console=True, icon=ICON, upx=False)

COLLECT(gui, cli, a.binaries, a.datas, name="app", upx=False)

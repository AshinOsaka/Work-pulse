# PyInstaller spec for the WorkPulse desktop agent (Windows).
#   cd agent
#   .venv\Scripts\python -m PyInstaller packaging\workpulse-agent.spec --noconfirm
# Output: dist\WorkPulseAgent\WorkPulseAgent.exe (one-folder build: fast start, signable files).
# ruff: noqa

from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - provided by PyInstaller

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    datas=[],
    hiddenimports=[
        "pystray._win32",
        "PIL._tkinter_finder",
    ],
    excludes=["pytest", "mypy", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WorkPulseAgent",
    console=False,  # background/tray application: no console window
    icon=str(ROOT / "packaging" / "workpulse.ico"),
    version=str(ROOT / "packaging" / "version-info.txt"),
    disable_windowed_traceback=False,
    upx=False,  # UPX-packed binaries trigger antivirus false positives
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="WorkPulseAgent",
    upx=False,
)

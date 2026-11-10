"""Start with Windows: the installer build must start from its own folder, never from a lone copied exe."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.system import platform


def _frozen(monkeypatch: pytest.MonkeyPatch, exe: Path, bundle: Path, appdata: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))


@pytest.fixture
def onedir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The installer layout: Programs/WorkPulse/WorkPulseAgent.exe + _internal/."""
    app = tmp_path / "Programs" / "WorkPulse"
    (app / "_internal").mkdir(parents=True)
    exe = app / "WorkPulseAgent.exe"
    exe.write_bytes(b"launcher")
    _frozen(monkeypatch, exe, app / "_internal", tmp_path)
    return exe


def test_installer_build_is_detected(onedir: Path) -> None:
    assert platform.is_onedir_build() is True


def test_installer_build_starts_from_its_own_folder(onedir: Path) -> None:
    assert platform.autostart_command() == f'"{onedir}" --minimized'


@pytest.mark.skipif(sys.platform != "win32", reason="the copy step only runs on Windows")
def test_installer_build_is_not_copied_and_a_broken_copy_is_removed(onedir: Path, tmp_path: Path) -> None:
    # What 0.8.1/0.8.2 left behind: the launcher alone, which can't start.
    stale = platform.installed_exe_path()
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"launcher")
    assert platform.ensure_installed() == onedir
    assert not stale.exists()
    assert platform.autostart_command() == f'"{onedir}" --minimized'


def test_single_file_download_still_uses_the_stable_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    download = tmp_path / "Downloads" / "WorkPulseAgent-0.8.0.exe"
    download.parent.mkdir()
    download.write_bytes(b"onefile")
    _frozen(monkeypatch, download, tmp_path / "Temp" / "_MEI1234", tmp_path)
    assert platform.is_onedir_build() is False
    if sys.platform == "win32":
        copy = platform.ensure_installed()
        assert copy == platform.installed_exe_path() and copy.read_bytes() == b"onefile"
        assert platform.autostart_command() == f'"{copy}" --minimized'

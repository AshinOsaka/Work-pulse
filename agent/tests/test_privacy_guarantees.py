"""Phase 16: what the agent must never be able to collect, pinned down so a later change can't slip it in.

WorkPulse promises employees that it never records keystrokes, typed text, passwords, clipboard contents, or audio and
video. The agent therefore contains no code that could: no keyboard hooks or key-state reads, no clipboard access, no
microphone or camera capture, and no input-logging libraries. Idle detection uses only `GetLastInputInfo`, which
returns the *time* of the last input, never what it was.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

FORBIDDEN_CALLS = re.compile(
    r"SetWindowsHookEx|WH_KEYBOARD|WH_MOUSE_LL|GetAsyncKeyState|GetKeyState|GetKeyboardState|GetRawInputData|"
    r"RegisterRawInputDevices|MapVirtualKey|ToUnicode|OpenClipboard|GetClipboardData|win32clipboard|"
    r"waveInOpen|IAudioCaptureClient|MFCreateDeviceSource|capCreateCaptureWindow"
)
FORBIDDEN_MODULES = {"pynput", "keyboard", "mouse", "pyHook", "pyhooked", "pyperclip", "win32clipboard", "sounddevice",
                     "pyaudio", "cv2", "clipboard"}  # fmt: skip


def sources() -> list[Path]:
    files = sorted(APP.rglob("*.py"))
    assert len(files) > 20, "agent sources not found; the guarantee would be checked against nothing"
    return files


def _docstrings(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def test_no_input_capture_clipboard_or_media_apis() -> None:
    for path in sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name | ast.Attribute):
                name = node.id if isinstance(node, ast.Name) else node.attr
                assert not FORBIDDEN_CALLS.fullmatch(name), f"{path.name}: {name}"
            # Strings too (e.g. getattr(user32, "GetAsyncKeyState")), except docstrings, which may explain what is
            # never collected.
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                assert not FORBIDDEN_CALLS.search(node.value), f"{path.name}: {node.value[:60]}"


def test_no_input_logging_or_media_libraries_are_imported() -> None:
    for path in sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            assert not FORBIDDEN_MODULES.intersection(names), f"{path.name}: {names}"


def test_idle_detection_reads_only_the_time_of_last_input() -> None:
    idle = (APP / "activity" / "idle.py").read_text(encoding="utf-8")
    assert "GetLastInputInfo" in idle
    requirements = (APP.parent / "requirements.txt").read_text(encoding="utf-8").lower()
    assert not any(module.lower() in requirements for module in FORBIDDEN_MODULES - {"mouse", "keyboard", "clipboard"})

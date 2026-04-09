"""Cross-platform helpers for Windows/Unix runtime differences."""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_IS_WINDOWS = platform.system() == "Windows"

try:
    import fcntl as _fcntl
except Exception:
    _fcntl = None

try:
    import msvcrt as _msvcrt
except Exception:
    _msvcrt = None


def get_host_temp_dir(app_name: str = "hermes") -> Path:
    """Return a temp directory for host-side Hermes runtime files."""
    path = Path(tempfile.gettempdir()) / app_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_host_temp_path(name: str, app_name: str = "hermes") -> Path:
    """Return a stable file path under the host temp directory."""
    return get_host_temp_dir(app_name) / name


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Acquire an exclusive cross-platform file lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(path, "a+")
    try:
        if _fcntl is not None:
            _fcntl.flock(lock_file.fileno(), _fcntl.LOCK_EX)
        elif _msvcrt is not None:
            lock_file.seek(0)
            _msvcrt.locking(lock_file.fileno(), _msvcrt.LK_LOCK, 1)
        yield
    finally:
        try:
            if _fcntl is not None:
                _fcntl.flock(lock_file.fileno(), _fcntl.LOCK_UN)
            elif _msvcrt is not None:
                lock_file.seek(0)
                _msvcrt.locking(lock_file.fileno(), _msvcrt.LK_UNLCK, 1)
        finally:
            lock_file.close()


def get_detached_popen_kwargs() -> dict:
    """Return platform-appropriate kwargs for detached subprocess launch."""
    if _IS_WINDOWS:
        creationflags = 0
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": creationflags}
    return {"start_new_session": True}


def shell_join(parts: list[str]) -> str:
    """Quote argv parts for a shell command string."""
    if _IS_WINDOWS:
        return subprocess.list2cmdline(parts)
    import shlex
    return " ".join(shlex.quote(part) for part in parts)

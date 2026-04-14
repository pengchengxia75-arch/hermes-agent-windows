"""Lightweight local fallback for ``python-dotenv``.

This project prefers the real ``python-dotenv`` package when installed, but
Windows-native and bare test environments may not have it yet.  The Hermes
codebase only relies on a small subset of the package API, so we provide a
minimal compatible implementation here.
"""

from __future__ import annotations

import os
from pathlib import Path


def _parse_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].strip()
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def load_dotenv(
    dotenv_path=None,
    override: bool = False,
    encoding: str = "utf-8",
    *args,
    **kwargs,
):
    path = dotenv_path
    if path is None:
        path = Path.cwd() / ".env"
    path = Path(path)
    if not path.exists():
        return False

    with open(path, "r", encoding=encoding) as f:
        for raw_line in f:
            parsed = _parse_line(raw_line)
            if not parsed:
                continue
            key, value = parsed
            if override or key not in os.environ:
                os.environ[key] = value
    return True

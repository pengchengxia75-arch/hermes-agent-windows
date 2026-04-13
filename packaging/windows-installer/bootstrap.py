#!/usr/bin/env python3
"""
Hermes Windows installer bootstrapper.

This script is designed to be packaged as a Windows EXE with PyInstaller.
It delegates the heavy lifting to ``scripts/install.ps1`` so the EXE and the
PowerShell installer stay aligned.
"""

from __future__ import annotations

import argparse
import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import queue
import webbrowser
from pathlib import Path
from typing import Iterable

try:
    import tkinter as tk
    from tkinter import messagebox
    _TK_AVAILABLE = True
except Exception:
    tk = None
    messagebox = None
    _TK_AVAILABLE = False


APP_NAME = "Hermes Windows Installer"
DEFAULT_HERMES_HOME = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes")

DEPENDENCY_GUIDANCE = {
    "PowerShell": {
        "required": True,
        "auto": False,
        "description": "PowerShell 是运行 Hermes 安装脚本所必需的系统组件。",
        "recommended_version": "PowerShell 7 或系统自带 Windows PowerShell 5.1+",
        "download_url": "https://aka.ms/PSWindows",
        "download_label": "PowerShell 7（推荐）",
    },
    "uv": {
        "required": True,
        "auto": True,
        "description": "uv 用来安装 Python 和 Python 依赖。",
        "recommended_version": "最新版 uv（x64）",
        "download_url": "https://docs.astral.sh/uv/getting-started/installation/",
        "download_label": "uv 官方安装文档",
    },
    "Python": {
        "required": True,
        "auto": True,
        "description": "Hermes 运行需要 Python 3.11，安装器会优先尝试 3.11，其次接受 3.10+。",
        "recommended_version": "Python 3.11 x64（推荐），3.10+ 可兼容",
        "download_url": "https://www.python.org/downloads/windows/",
        "download_label": "Python for Windows（推荐 3.11 x64）",
    },
    "Git": {
        "required": True,
        "auto": True,
        "description": "Git 用于获取和更新 Hermes 源代码。",
        "recommended_version": "Git for Windows 最新稳定版（x64）",
        "download_url": "https://git-scm.com/download/win",
        "download_label": "Git for Windows",
    },
    "Git Bash": {
        "required": True,
        "auto": True,
        "description": "Windows 版 Hermes 的本地命令执行依赖 Git Bash 兼容层。",
        "recommended_version": "随 Git for Windows 一起安装的 bash.exe",
        "download_url": "https://git-scm.com/download/win",
        "download_label": "Git for Windows（包含 Git Bash）",
    },
    "Node.js": {
        "required": True,
        "auto": True,
        "description": "浏览器工具和部分桥接功能依赖 Node.js。",
        "recommended_version": "Node.js LTS x64",
        "download_url": "https://nodejs.org/en/download",
        "download_label": "Node.js LTS for Windows x64",
    },
    "winget": {
        "required": False,
        "auto": False,
        "description": "winget 不是必须项，但有它时可以更方便自动补齐依赖。",
        "recommended_version": "Windows App Installer 最新版",
        "download_url": "https://learn.microsoft.com/windows/package-manager/winget/",
        "download_label": "winget / App Installer 文档",
    },
    "ripgrep": {
        "required": False,
        "auto": True,
        "description": "ripgrep 用于更快的文件搜索，不影响基础聊天使用。",
        "recommended_version": "ripgrep x64 最新稳定版",
        "download_url": "https://github.com/BurntSushi/ripgrep/releases",
        "download_label": "ripgrep Releases",
    },
    "ffmpeg": {
        "required": False,
        "auto": True,
        "description": "ffmpeg 主要用于语音/TTS 功能，不影响核心 CLI。",
        "recommended_version": "FFmpeg Windows x64 Essentials / 最新稳定版",
        "download_url": "https://www.gyan.dev/ffmpeg/builds/",
        "download_label": "FFmpeg Windows Builds",
    },
}


def _resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[2]


def _install_script_path() -> Path:
    root = _resource_root()
    candidates = [
        root / "scripts" / "install.ps1",
        root / "install.ps1",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find scripts/install.ps1 in bundled resources.")


def _find_command(name: str) -> str | None:
    return shutil.which(name)


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".hermes-write-test"
        probe.write_text("ok", encoding="utf-8")
        try:
            probe.unlink()
        except Exception:
            return False
        return True
    except Exception:
        return False


def _command_version(command_name: str) -> str:
    probes = {
        "uv": ["uv", "--version"],
        "git": ["git", "--version"],
        "node": ["node", "--version"],
        "winget": ["winget", "--version"],
        "python": ["python", "--version"],
        "powershell.exe": ["powershell.exe", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
    }
    try:
        cmd = probes.get(command_name)
        if not cmd:
            return ""
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8)
        output = (result.stdout or result.stderr or "").strip()
        return output.splitlines()[0].strip() if output else ""
    except Exception:
        return ""


def _git_bash_path() -> str:
    candidates = [
        os.environ.get("HERMES_GIT_BASH_PATH", ""),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def _gather_preflight(args: argparse.Namespace) -> list[dict[str, str | bool]]:
    hermes_home = Path(args.hermes_home or DEFAULT_HERMES_HOME)
    install_dir = Path(args.install_dir or (hermes_home / "hermes-agent"))
    temp_root = Path(tempfile.gettempdir())
    checks: list[dict[str, str | bool]] = []

    def add(label: str, status: str, detail: str, *, key: str | None = None) -> None:
        guide = DEPENDENCY_GUIDANCE.get(key or label, {})
        checks.append(
            {
                "label": label,
                "status": status,
                "detail": detail,
                "required": bool(guide.get("required", False)),
                "auto": bool(guide.get("auto", False)),
                "description": str(guide.get("description", "")),
                "recommended_version": str(guide.get("recommended_version", "")),
                "download_url": str(guide.get("download_url", "")),
                "download_label": str(guide.get("download_label", "")),
            }
        )

    powershell_path = _find_command("powershell.exe")
    powershell_detail = powershell_path or "not on PATH"
    powershell_version = _command_version("powershell.exe")
    if powershell_version:
        powershell_detail = f"{powershell_detail} ({powershell_version})"
    add("PowerShell", "OK" if powershell_path else "MISSING", powershell_detail)

    try:
        install_script = _install_script_path()
        add("Install script", "OK" if install_script.exists() else "MISSING", str(install_script))
    except FileNotFoundError:
        add("Install script", "MISSING", "bundled install.ps1 not found")

    add("Temp directory writable", "OK" if _is_writable_dir(temp_root) else "FAIL", str(temp_root))
    add("Hermes home writable", "OK" if _is_writable_dir(hermes_home) else "FAIL", str(hermes_home))
    add("Install directory parent", "OK" if _is_writable_dir(install_dir.parent) else "FAIL", str(install_dir.parent))

    for command_name, label in (
        ("uv", "uv"),
        ("git", "Git"),
        ("node", "Node.js"),
        ("winget", "winget"),
        ("python", "Python"),
    ):
        resolved = _find_command(command_name)
        detail = resolved or "not on PATH"
        version = _command_version(command_name)
        if version:
            detail = f"{detail} ({version})"
        add(label, "FOUND" if resolved else "MISSING", detail, key=label)

    bash_path = _git_bash_path()
    add("Git Bash", "FOUND" if bash_path else "MISSING", bash_path or "bash.exe not found", key="Git Bash")

    return checks


def _manual_guidance_lines(checks: Iterable[dict[str, str | bool]]) -> list[str]:
    lines: list[str] = []
    for item in checks:
        status = str(item["status"])
        if status not in {"MISSING", "FAIL"}:
            continue
        label = str(item["label"])
        auto = "会尝试自动安装" if item.get("auto") else "不会自动安装"
        required = "必需" if item.get("required") else "可选"
        lines.append(f"  - {label}：{required}，{auto}")
        description = str(item.get("description") or "")
        if description:
            lines.append(f"    说明：{description}")
        recommended = str(item.get("recommended_version") or "")
        if recommended:
            lines.append(f"    推荐版本：{recommended}")
        url = str(item.get("download_url") or "")
        label_text = str(item.get("download_label") or "")
        if url:
            lines.append(f"    手动下载：{label_text or url} -> {url}")
    return lines


def _print_preflight(checks: Iterable[dict[str, str | bool]]) -> None:
    print(f"[INFO] {APP_NAME} 环境预检")
    for item in checks:
        label = str(item["label"])
        status = str(item["status"])
        detail = str(item["detail"])
        required = "必需" if item.get("required") else "可选"
        auto = "自动安装" if item.get("auto") else "手动处理"
        print(f"  - {label}: {status} ({required} / {auto})")
        print(f"    {detail}")
        description = str(item.get("description") or "")
        if description:
            print(f"    说明：{description}")
        recommended = str(item.get("recommended_version") or "")
        if recommended:
            print(f"    推荐版本：{recommended}")
    guidance = _manual_guidance_lines(checks)
    if guidance:
        print("")
        print("[INFO] 如果自动安装失败，可按下面的官方链接手动下载：")
        for line in guidance:
            print(line)
    print("")


def _build_install_command(args: argparse.Namespace) -> tuple[list[str], Path]:
    install_script = _install_script_path()
    temp_dir = Path(tempfile.mkdtemp(prefix="hermes-installer-"))
    atexit.register(shutil.rmtree, temp_dir, ignore_errors=True)
    temp_script = temp_dir / "install.ps1"
    shutil.copy2(install_script, temp_script)

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(temp_script),
    ]
    if args.branch:
        cmd.extend(["-Branch", args.branch])
    if args.hermes_home:
        cmd.extend(["-HermesHome", args.hermes_home])
    if args.install_dir:
        cmd.extend(["-InstallDir", args.install_dir])
    if args.no_venv:
        cmd.append("-NoVenv")
    if args.skip_setup:
        cmd.append("-SkipSetup")
    return cmd, temp_dir


def _hermes_exe_path(hermes_home: str | None) -> Path:
    base = Path(hermes_home or DEFAULT_HERMES_HOME)
    return base / "hermes-agent" / "venv" / "Scripts" / "hermes.exe"


def _launch_post_install_terminal(hermes_home: str | None) -> None:
    hermes_exe = _hermes_exe_path(hermes_home)
    if hermes_exe.exists():
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoExit",
                "-Command",
                f'& "{hermes_exe}" setup',
            ]
        )
        return

    subprocess.Popen(["powershell.exe", "-NoExit"])


def _launch_hermes_chat_terminal(hermes_home: str | None) -> None:
    hermes_exe = _hermes_exe_path(hermes_home)
    if hermes_exe.exists():
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoExit",
                "-Command",
                f'& "{hermes_exe}"',
            ]
        )
        return
    subprocess.Popen(["powershell.exe", "-NoExit"])


def _open_log_file() -> None:
    log_path = _log_file_path()
    if log_path.exists():
        os.startfile(str(log_path))


def _open_download_url(url: str) -> None:
    if url:
        webbrowser.open(url)


def _log_file_path() -> Path:
    return Path(tempfile.gettempdir()) / "hermes-installer.log"


def _cleanup_temp_install_dir(temp_dir: Path | None) -> None:
    if not temp_dir:
        return
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


def _stream_process(cmd: list[str], log_path: Path) -> int:
    with log_path.open("w", encoding="utf-8", newline="\n") as handle:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            handle.write(line)
        return process.wait()


def _stream_process_to_queue(cmd: list[str], log_path: Path, line_queue: "queue.Queue[tuple[str, str]]") -> int:
    with log_path.open("w", encoding="utf-8", newline="\n") as handle:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            handle.write(line)
            line_queue.put(("line", line))
        return_code = process.wait()
    line_queue.put(("done", str(return_code)))
    return return_code


def run_installer(args: argparse.Namespace) -> int:
    print(f"[INFO] Starting {APP_NAME}...")
    checks = _gather_preflight(args)
    _print_preflight(checks)
    if args.check_only:
        print("[OK] Preflight complete. No changes were made.")
        return 0

    cmd, temp_dir = _build_install_command(args)
    log_path = _log_file_path()
    print("[INFO] Launching bundled PowerShell installer.")
    print(f"[INFO] Install log: {log_path}")
    try:
        return_code = _stream_process(cmd, log_path)
    except FileNotFoundError:
        print("[ERROR] powershell.exe was not found on this system.")
        _cleanup_temp_install_dir(temp_dir)
        return 1

    if return_code != 0:
        print(f"[ERROR] Installer exited with code {return_code}.")
        print(f"[INFO] Review log: {log_path}")
        _cleanup_temp_install_dir(temp_dir)
        return return_code

    print("[OK] Hermes installation finished.")
    print(f"[INFO] Log saved to: {log_path}")
    if args.launch_setup:
        print("[INFO] Opening a PowerShell window for `hermes setup`...")
        _launch_post_install_terminal(args.hermes_home)
    else:
        print("[INFO] Next step: open a new PowerShell and run `hermes setup`.")
    _cleanup_temp_install_dir(temp_dir)
    return 0


class InstallerGUI:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("860x620")
        self.root.minsize(760, 520)

        self.queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.install_thread: threading.Thread | None = None
        self.launch_setup_var = tk.BooleanVar(value=bool(args.launch_setup))
        self.status_var = tk.StringVar(value="准备就绪")

        self._build_ui()
        self._render_preflight()
        self.root.after(100, self._poll_queue)

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, padx=14, pady=14)
        outer.pack(fill="both", expand=True)

        title = tk.Label(
            outer,
            text="Hermes Windows Installer",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        )
        title.pack(fill="x")

        subtitle = tk.Label(
            outer,
            text="Hermes Windows 原生安装器：先检测环境，再补依赖，再安装 Hermes",
            font=("Segoe UI", 10),
            fg="#444444",
            anchor="w",
        )
        subtitle.pack(fill="x", pady=(0, 10))

        config_frame = tk.LabelFrame(outer, text="安装选项", padx=10, pady=8)
        config_frame.pack(fill="x", pady=(0, 10))

        tk.Label(config_frame, text="分支").grid(row=0, column=0, sticky="w")
        self.branch_entry = tk.Entry(config_frame)
        self.branch_entry.insert(0, self.args.branch)
        self.branch_entry.grid(row=0, column=1, sticky="ew", padx=(8, 14))

        tk.Label(config_frame, text="Hermes 主目录").grid(row=1, column=0, sticky="w")
        self.home_entry = tk.Entry(config_frame)
        self.home_entry.insert(0, self.args.hermes_home or DEFAULT_HERMES_HOME)
        self.home_entry.grid(row=1, column=1, sticky="ew", padx=(8, 14))

        tk.Label(config_frame, text="安装目录").grid(row=2, column=0, sticky="w")
        self.install_entry = tk.Entry(config_frame)
        default_install_dir = self.args.install_dir or os.path.join(self.home_entry.get(), "hermes-agent")
        self.install_entry.insert(0, default_install_dir)
        self.install_entry.grid(row=2, column=1, sticky="ew", padx=(8, 14))

        config_frame.columnconfigure(1, weight=1)

        options_row = tk.Frame(config_frame)
        options_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        tk.Checkbutton(options_row, text="安装完成后立即打开 `hermes setup`", variable=self.launch_setup_var).pack(side="left")

        action_row = tk.Frame(outer)
        action_row.pack(fill="x", pady=(0, 10))
        self.install_button = tk.Button(action_row, text="一键安装 Hermes", width=18, command=self._start_install)
        self.install_button.pack(side="left")
        self.check_button = tk.Button(action_row, text="仅检查环境", width=18, command=self._refresh_preflight)
        self.check_button.pack(side="left", padx=(8, 0))

        self.open_setup_button = tk.Button(action_row, text="立即配置", width=12, command=self._open_setup, state="disabled")
        self.open_setup_button.pack(side="left", padx=(8, 0))
        self.open_chat_button = tk.Button(action_row, text="立即打开", width=12, command=self._open_chat, state="disabled")
        self.open_chat_button.pack(side="left", padx=(8, 0))
        self.open_log_button = tk.Button(action_row, text="查看日志", width=12, command=_open_log_file)
        self.open_log_button.pack(side="left", padx=(8, 0))

        self.status_label = tk.Label(action_row, textvariable=self.status_var, anchor="e")
        self.status_label.pack(side="right")

        self.output = tk.Text(outer, wrap="word", font=("Consolas", 10))
        self.output.pack(fill="both", expand=True)

    def _append(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def _open_setup(self) -> None:
        _launch_post_install_terminal(self.home_entry.get().strip() or None)

    def _open_chat(self) -> None:
        _launch_hermes_chat_terminal(self.home_entry.get().strip() or None)

    def _build_runtime_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            branch=self.branch_entry.get().strip() or "main",
            hermes_home=self.home_entry.get().strip() or None,
            install_dir=self.install_entry.get().strip() or None,
            no_venv=self.args.no_venv,
            skip_setup=self.args.skip_setup,
            launch_setup=bool(self.launch_setup_var.get()),
            check_only=False,
            gui=True,
            console=False,
        )

    def _render_preflight(self) -> None:
        self.output.delete("1.0", "end")
        checks = _gather_preflight(self._build_runtime_args())
        self._append("[INFO] Hermes Windows Installer 环境预检\n")
        for item in checks:
            label = str(item["label"])
            status = str(item["status"])
            detail = str(item["detail"])
            required = "必需" if item.get("required") else "可选"
            auto = "自动安装" if item.get("auto") else "手动处理"
            self._append(f"  - {label}: {status} ({required} / {auto})\n")
            self._append(f"    {detail}\n")
            description = str(item.get("description") or "")
            if description:
                self._append(f"    说明：{description}\n")
            recommended = str(item.get("recommended_version") or "")
            if recommended:
                self._append(f"    推荐版本：{recommended}\n")
        guidance = _manual_guidance_lines(checks)
        if guidance:
            self._append("\n[INFO] 如果自动安装失败，可按下面的官方链接手动下载：\n")
            for line in guidance:
                self._append(f"{line}\n")
        self._append("\n")
        self.status_var.set("环境检查完成")

    def _refresh_preflight(self) -> None:
        self._render_preflight()

    def _start_install(self) -> None:
        if self.install_thread and self.install_thread.is_alive():
            return
        runtime_args = self._build_runtime_args()
        cmd, temp_dir = _build_install_command(runtime_args)
        log_path = _log_file_path()
        self.output.delete("1.0", "end")
        self._append(f"[INFO] 开始运行 {APP_NAME}...\n")
        self._append(f"[INFO] 安装日志：{log_path}\n\n")
        self.install_button.config(state="disabled")
        self.check_button.config(state="disabled")
        self.open_setup_button.config(state="disabled")
        self.open_chat_button.config(state="disabled")
        self.status_var.set("正在安装...")

        def _worker() -> None:
            try:
                _stream_process_to_queue(cmd, log_path, self.queue)
            except Exception as exc:
                self.queue.put(("line", f"[ERROR] Installer bootstrap failed: {exc}\n"))
                self.queue.put(("done", "1"))
            finally:
                _cleanup_temp_install_dir(temp_dir)

        self.install_thread = threading.Thread(target=_worker, daemon=True)
        self.install_thread.start()

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "line":
                    self._append(payload)
                elif kind == "done":
                    code = int(payload)
                    self.install_button.config(state="normal")
                    self.check_button.config(state="normal")
                    if code == 0:
                        self.status_var.set("安装完成")
                        self.open_setup_button.config(state="normal")
                        self.open_chat_button.config(state="normal")
                        self._append("\n[OK] Hermes 安装完成。\n")
                        self._append(f"[INFO] 日志已保存到：{_log_file_path()}\n")
                        if self.launch_setup_var.get():
                            _launch_post_install_terminal(self.home_entry.get().strip() or None)
                            self._append("[INFO] 已自动打开新的 PowerShell 窗口运行 `hermes setup`。\n")
                        else:
                            self._append("[INFO] 下一步：点击“立即配置”或手动在新 PowerShell 中运行 `hermes setup`。\n")
                        self._append("[INFO] 你也可以点击“立即打开”直接进入 Hermes 命令行。\n")
                        if messagebox is not None and not self.launch_setup_var.get():
                            if messagebox.askyesno(APP_NAME, "Hermes 已安装完成。现在要立即打开配置向导吗？"):
                                self._open_setup()
                    else:
                        self.status_var.set(f"安装失败 ({code})")
                        self._append(f"\n[ERROR] 安装器退出，错误码：{code}\n")
                        self._append(f"[INFO] 请查看日志：{_log_file_path()}\n")
                        if messagebox is not None:
                            messagebox.showerror(APP_NAME, f"安装失败，错误码：{code}\n请点击“查看日志”排查。")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def run(self) -> int:
        self.root.mainloop()
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes Windows 安装器引导程序")
    parser.add_argument("--branch", default="main", help="要安装的 Git 分支")
    parser.add_argument("--hermes-home", help="覆盖 HERMES_HOME 目录")
    parser.add_argument("--install-dir", help="覆盖代码安装目录")
    parser.add_argument("--no-venv", action="store_true", help="向 install.ps1 传递 -NoVenv")
    parser.add_argument("--skip-setup", action="store_true", help="向 install.ps1 传递 -SkipSetup")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="仅运行环境预检，不执行安装",
    )
    parser.add_argument("--gui", action="store_true", help="打开图形化安装器")
    parser.add_argument("--console", action="store_true", help="强制使用控制台模式")
    parser.add_argument(
        "--launch-setup",
        action="store_true",
        help="安装完成后自动打开新的 PowerShell 窗口运行 `hermes setup`",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    use_gui = _TK_AVAILABLE and not args.console and (args.gui or (getattr(sys, "frozen", False) and len(sys.argv) == 1))
    if use_gui:
        return InstallerGUI(args).run()
    return run_installer(args)


if __name__ == "__main__":
    raise SystemExit(main())

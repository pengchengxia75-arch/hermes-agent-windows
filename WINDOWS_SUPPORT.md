# Windows Support

This fork/package of Hermes Agent supports native Windows installation and usage without WSL for the core CLI workflow.

Repository:
[`pengchengxia75-arch/hermes-agent-windows`](https://github.com/pengchengxia75-arch/hermes-agent-windows)

## Supported

- One-line PowerShell install via `scripts/install.ps1`
- Native Windows install location under `%LOCALAPPDATA%\hermes`
- CLI startup with `hermes`
- Local command execution through Git Bash
- Core config files, skills sync, and standard Python-based features
- Automatic setup of:
  - `uv`
  - Git for Windows
  - Node.js
  - `ripgrep`
  - `ffmpeg`
  - `HERMES_HOME`
  - `HERMES_GIT_BASH_PATH`

## Runtime Model

Hermes starts from PowerShell or CMD, but local shell execution is routed through Git Bash for compatibility with the upstream Unix-oriented command model.

## Recommended Use Cases

- CLI chat
- Local coding workflows
- Skills that mainly use Python and local terminal commands
- Regular configuration and day-to-day agent usage

## Experimental

These may work, but are not yet guaranteed to match Linux/WSL behavior:

- Gateway/platform integrations
- Browser-heavy workflows
- Voice/STT/TTS edge cases
- Advanced terminal backends such as Docker, SSH, Modal, Daytona, and Singularity
- RL and `tinker-atropos` flows

## Install

```powershell
irm https://raw.githubusercontent.com/pengchengxia75-arch/hermes-agent-windows/main/scripts/install.ps1 | iex
```

## Installed Paths

- Hermes home: `%LOCALAPPDATA%\hermes`
- Code: `%LOCALAPPDATA%\hermes\hermes-agent`
- Config: `%LOCALAPPDATA%\hermes\config.yaml`
- Env file: `%LOCALAPPDATA%\hermes\.env`

## First Run

```powershell
hermes version
hermes setup
hermes
```

## Notes

- After install, open a new terminal window so PATH changes are picked up.
- If `hermes` is not found, verify that `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts` is on your user PATH.
- This fork is based on the upstream `NousResearch/hermes-agent` source code and keeps the MIT license.

# Hermes Agent Windows

Windows-native fork of
[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent).

This version is adapted for native Windows use and does not require WSL2 for
normal CLI installation and usage.

## Install

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/pengchengxia75-arch/hermes-agent-windows/main/scripts/install.ps1 | iex
```

## Use

After installation, open a new PowerShell window and run:

```powershell
hermes version
hermes setup
hermes
```

## What This Fork Focuses On

- native Windows installation
- no WSL2 requirement
- Git Bash compatibility for command execution
- simpler Windows setup for Hermes CLI

## Upstream

Original project:
[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent)

This repository is a Windows adaptation built on top of the upstream source
code, not a separate project from scratch.

## License

This repository keeps the upstream MIT license.

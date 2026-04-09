# Hermes Agent Windows

This repository is based on the original [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) source code.

I adapted it so Hermes Agent can be installed and used on native Windows without requiring WSL2.

## What Changed

- Native Windows installation flow
- One-line PowerShell installer
- Git Bash based shell compatibility for local command execution
- Windows environment setup for Hermes runtime

## Install on Windows

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/pengchengxia75-arch/hermes-agent-windows/main/scripts/install.ps1 | iex
```

## After Install

Open a new PowerShell window, then run:

```powershell
hermes version
hermes setup
hermes
```

## Notes

- This repo is a Windows adaptation of the upstream Hermes Agent project.
- The upstream project is here:
  [https://github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
- This version is focused on making the core CLI workflow usable on Windows without WSL2.

## License

This project keeps the upstream MIT license.

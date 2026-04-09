# GitHub Publish Guide

This repository is already published here:

[`pengchengxia75-arch/hermes-agent-windows`](https://github.com/pengchengxia75-arch/hermes-agent-windows)

Use this guide when you want to push later updates from your local folder to GitHub.

## 1. Open PowerShell in this folder

Folder:

`C:\Users\xpc\Desktop\hermes\hermes-agent-main`

## 2. Check what changed

```powershell
git status --short
```

## 3. Add and commit your updates

```powershell
git add .
git commit -m "Describe your update here"
```

Example:

```powershell
git commit -m "Update Windows fork docs"
```

## 4. Push to GitHub

```powershell
git push
```

## 5. Current public install command

Share this with Windows users:

```powershell
$u = "https://raw.githubusercontent.com/pengchengxia75-arch/hermes-agent-windows/main/scripts/install.ps1"; $p = "$env:TEMP\hermes-install.ps1"; Invoke-WebRequest -Uri $u -OutFile $p; powershell -ExecutionPolicy Bypass -File $p
```

## 6. Recommended GitHub About text

Repository description:

`Windows-native fork of Hermes Agent. No WSL2 required.`

## 7. Optional release tag

If you want a version tag:

```powershell
git tag v0.8.0-windows-beta1
git push origin v0.8.0-windows-beta1
```

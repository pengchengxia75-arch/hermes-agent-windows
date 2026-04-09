# GitHub Publish Guide

This guide assumes you want to publish this Windows-capable Hermes package to your own GitHub repository.

## 1. Create a new repo on GitHub

Create an empty repository on GitHub, for example:

- Repository name: `hermes-agent-windows`
- Visibility: Public or Private

Do not initialize it with a README if you want the cleanest push.

## 2. Open PowerShell in this folder

Folder:

`C:\Users\xpc\Desktop\hermes\hermes-agent-main`

## 3. Initialize git locally

```powershell
git init
git branch -M main
```

## 4. Review files before first commit

You should keep at least:

- `scripts/install.ps1`
- `README.md`
- `WINDOWS_SUPPORT.md`
- `GITHUB_PUBLISH_GUIDE.md`
- source code folders

## 5. Add and commit

```powershell
git add .
git commit -m "Add Windows native install support for Hermes"
```

## 6. Connect your GitHub repo

Replace the URL below with your own:

```powershell
git remote add origin https://github.com/<your-name>/<your-repo>.git
```

## 7. Push

```powershell
git push -u origin main
```

## 8. Public install command

After pushing, your one-line install command becomes:

```powershell
irm https://raw.githubusercontent.com/<your-name>/<your-repo>/main/scripts/install.ps1 | iex
```

## 9. Suggested README note

Mention clearly that:

- Windows native install is supported for core CLI workflows
- shell execution uses Git Bash under the hood
- some advanced features remain experimental

## 10. Optional next step

After the first push, you can create a release tag:

```powershell
git tag v0.8.0-windows-beta1
git push origin v0.8.0-windows-beta1
```

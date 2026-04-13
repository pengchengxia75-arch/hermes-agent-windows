# Hermes Windows Installer

这个目录存放的是 Hermes Windows 原生适配版的 EXE 安装器。它的目标不是把 Hermes 做成桌面客户端，而是让普通 Windows 用户也能更稳地完成安装。

## 当前能力

- 用 `PyInstaller` 打包轻量 EXE 安装器
- 内置并调用仓库里的 `scripts/install.ps1`
- 安装前先做环境预检
- 缺依赖时显示中文说明、推荐版本和官方下载链接
- 安装日志写入 `%TEMP%\\hermes-installer.log`
- 安装完成后可直接打开 `hermes setup` 或 `hermes`

## 构建

在仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows-installer\build.ps1
```

构建后会生成两个 EXE：

```text
packaging\windows-installer\dist\HermesInstaller.exe
packaging\windows-installer\dist\HermesInstallerConsole.exe
```

- `HermesInstaller.exe`
  - GUI 图形安装器
  - 适合普通用户双击安装
- `HermesInstallerConsole.exe`
  - 控制台安装器
  - 适合排障、看日志、远程协助

## 运行

```powershell
.\packaging\windows-installer\dist\HermesInstaller.exe
```

可选参数：

- `--branch main`
- `--hermes-home C:\Users\<you>\AppData\Local\hermes`
- `--install-dir C:\Users\<you>\AppData\Local\hermes\hermes-agent`
- `--skip-setup`
- `--no-venv`
- `--check-only`
- `--gui`
- `--console`

## 当前定位

这是一个“薄封装安装器”。底层仍然复用现有的 `install.ps1`，这样 EXE 和 PowerShell 安装命令可以始终保持一致，不会出现两套安装逻辑分叉。

也就是说：

- 依赖安装主逻辑仍然在 `install.ps1`
- fallback 行为仍然在 `install.ps1`
- EXE 这一层主要负责用户体验、环境预检和错误提示

## 当前体验增强

- 安装前显示中文环境预检
- 标明哪些依赖是必需，哪些是可选
- 自动安装失败时给出官方下载链接和推荐版本
- 支持 `--check-only` 只检查环境
- GUI 版面向普通用户
- Console 版面向排障和支持

## 已知说明

- 当前 EXE 还没有做代码签名，Windows SmartScreen 可能会提示来源未知。这不影响功能，但首次分发时需要在发布说明里提前告知用户。

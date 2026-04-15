# Hermes Agent Windows v0.9.0 升级说明

## 本次更新内容

### 🖥 全新 Web UI 管理面板

新增 `hermes web` 命令，启动基于 React + TypeScript 的现代化管理面板，包含以下功能页面：

| 页面 | 功能 |
|------|------|
| **对话** | 与 Hermes Agent 实时聊天，支持流式输出和快捷操作 |
| **状态** | 查看 Gateway 运行状态、活跃会话、平台连接情况 |
| **会话** | 浏览历史对话记录，支持全文搜索 |
| **分析** | 查看 Token 用量统计和费用估算 |
| **日志** | 实时查看运行日志，支持级别过滤 |
| **定时任务** | 管理和触发 Cron 定时任务 |
| **技能** | 启用/禁用已安装技能 |
| **配置** | 可视化编辑 config.yaml 所有配置项 |
| **密钥** | 管理 .env 中的 API Key 等环境变量 |

界面支持中文/英文切换，适配手机和桌面端。

### 🐛 Windows 兼容性修复

- 修复 `hermes gateway run` 在部分 Windows 系统上报 `[WinError 11]` 导致无法启动的问题

---

## 升级方法

### 方法一：命令行一键升级（推荐）

在 PowerShell 中执行：

```powershell
hermes update
```

升级完成后，安装 Web UI 所需依赖（只需执行一次）：

```powershell
cd $env:LOCALAPPDATA\hermes\hermes-agent
uv pip install fastapi
```

### 方法二：手动升级

```powershell
cd $env:LOCALAPPDATA\hermes\hermes-agent
git pull
uv pip install fastapi
```

---

## 如何使用 Web UI

**第一步：** 启动 Hermes Gateway（保持窗口开着）

```powershell
hermes gateway run
```

**第二步：** 另开一个 PowerShell 窗口，启动 Web UI

```powershell
hermes web
```

浏览器会自动打开 `http://127.0.0.1:9119`，点击顶部导航的 **对话** 即可开始聊天。

> 如需指定端口：`hermes web --port 8080`

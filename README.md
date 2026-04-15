# Hermes Agent Windows

[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent) 的 Windows 原生适配版本。

无需 WSL2，直接在 Windows 上安装和运行。

> 当前版本：**v0.9.0** · [查看更新说明](RELEASE_v0.9.0.md)

---

## 安装

打开 PowerShell，执行一行命令：

```powershell
$u = "https://raw.githubusercontent.com/pengchengxia75-arch/hermes-agent-windows/main/scripts/install.ps1"; $p = "$env:TEMP\hermes-install.ps1"; Invoke-WebRequest -Uri $u -OutFile $p; powershell -ExecutionPolicy Bypass -File $p
```

安装完成后，额外安装 Web UI 依赖（只需一次）：

```powershell
uv pip install fastapi uvicorn --python "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe"
```

---

## 基本使用

```powershell
hermes setup      # 初始化配置（首次运行）
hermes            # 启动命令行对话
```

---

## Web UI 管理面板

v0.9.0 新增图形化管理界面，在浏览器中使用 Hermes。

**第一步：** 启动 Gateway（保持窗口开着）

```powershell
hermes gateway run
```

**第二步：** 另开一个 PowerShell，启动 Web UI

```powershell
hermes web
```

浏览器自动打开 `http://127.0.0.1:9119`

| 页面 | 功能 |
|------|------|
| 对话 | 与 Agent 实时聊天，流式输出 |
| 状态 | Gateway 运行状态、平台连接情况 |
| 会话 | 历史对话记录，支持全文搜索 |
| 分析 | Token 用量统计和费用估算 |
| 日志 | 实时运行日志，支持级别过滤 |
| 定时任务 | 管理和触发 Cron 任务 |
| 技能 | 启用/禁用已安装技能 |
| 配置 | 可视化编辑全部配置项 |
| 密钥 | 管理 API Key 等环境变量 |

> 如需指定端口：`hermes web --port 8080`

---

## 升级

```powershell
hermes update
```

---

## 与上游的关系

上游项目：[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent)

本项目在上游基础上做了以下适配：

- Windows 原生安装，无需 WSL2
- Git Bash 兼容性
- 修复 Windows 下 `os.kill` WinError 11 问题
- 新增 `hermes web` 命令
- 新增对话页面（ChatPage）
- 中文界面支持

---

## License

遵循上游 MIT 协议。

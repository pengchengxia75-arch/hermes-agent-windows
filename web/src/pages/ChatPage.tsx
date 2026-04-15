import { useEffect, useRef, useState, useCallback } from "react";
import { Bot, Send, Plus, Zap, RotateCcw, MessageSquare, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { SessionInfo, SessionMessage } from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────────────

interface Message {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

// ── Constants ──────────────────────────────────────────────────────────────

const QUICK_ACTIONS = [
  { icon: "📊", text: "帮我分析数据并生成可视化报告" },
  { icon: "🔍", text: "搜索今日最新 AI 资讯并总结要点" },
  { icon: "⚡", text: "列出所有已安装的技能及功能简介" },
  { icon: "🌐", text: "打开浏览器搜索 GitHub Trending 今日热门项目" },
  { icon: "🧠", text: "查看我的对话记忆，总结了哪些重要信息" },
  { icon: "✅", text: "检查当前运行的进程和配置的定时任务" },
];

const STORAGE_KEY = "hermes_chat_messages";
const HISTORY_KEY  = "hermes_chat_history";
const SIDEBAR_KEY  = "hermes_sidebar_open";

// ── Helpers ────────────────────────────────────────────────────────────────

function loadSaved() {
  try {
    return {
      messages: JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]") as Message[],
      history:  JSON.parse(sessionStorage.getItem(HISTORY_KEY)  || "[]") as { role: string; content: string }[],
    };
  } catch { return { messages: [], history: [] }; }
}

function relTime(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60)    return "刚刚";
  if (diff < 3600)  return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 86400 * 2) return "昨天";
  return new Date(ts * 1000).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

function sessionTitle(s: SessionInfo): string {
  if (s.title) return s.title;
  if (s.preview) return s.preview.slice(0, 40);
  return `对话 ${new Date(s.started_at * 1000).toLocaleDateString("zh-CN")}`;
}

function groupSessions(sessions: SessionInfo[]) {
  const now = Date.now() / 1000;
  const today:     SessionInfo[] = [];
  const yesterday: SessionInfo[] = [];
  const week:      SessionInfo[] = [];
  const older:     SessionInfo[] = [];
  for (const s of sessions) {
    const diff = now - s.last_active;
    if      (diff < 86400)     today.push(s);
    else if (diff < 86400 * 2) yesterday.push(s);
    else if (diff < 86400 * 7) week.push(s);
    else                        older.push(s);
  }
  return [
    { label: "今天",   items: today },
    { label: "昨天",   items: yesterday },
    { label: "本周",   items: week },
    { label: "更早",   items: older },
  ].filter(g => g.items.length > 0);
}

// ── Component ──────────────────────────────────────────────────────────────

export default function ChatPage() {
  const saved = loadSaved();

  // chat state
  const [messages,  setMessages]  = useState<Message[]>(saved.messages);
  const [input,     setInput]     = useState("");
  const [streaming, setStreaming] = useState(false);
  const [agentInfo, setAgentInfo] = useState("");
  const historyRef  = useRef<{ role: string; content: string }[]>(saved.history);
  const bottomRef   = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef    = useRef<AbortController | null>(null);

  // sidebar state
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(() => {
    try { return localStorage.getItem(SIDEBAR_KEY) !== "false"; } catch { return true; }
  });
  const [sessions,     setSessions]     = useState<SessionInfo[]>([]);
  const [activeId,     setActiveId]     = useState<string | null>(null);
  const [loadingHist,  setLoadingHist]  = useState(false);

  // ── Persist sidebar pref ──
  useEffect(() => {
    try { localStorage.setItem(SIDEBAR_KEY, String(sidebarOpen)); } catch {}
  }, [sidebarOpen]);

  // ── Persist messages ──
  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.map(m => ({ ...m, streaming: false }))));
      sessionStorage.setItem(HISTORY_KEY,  JSON.stringify(historyRef.current));
    } catch {}
  }, [messages]);

  // ── Load sessions ──
  const refreshSessions = useCallback(async () => {
    try {
      const resp = await api.getSessions(50);
      setSessions(resp.sessions);
    } catch {}
  }, []);

  useEffect(() => { refreshSessions(); }, [refreshSessions]);

  // ── Agent status ──
  useEffect(() => {
    fetch("/api/status").then(r => r.json()).then(d => {
      if (d.gateway_running) {
        const m = d.active_model || "", p = d.active_provider || "";
        setAgentInfo(m || p ? `${m}${p ? " · " + p : ""} · 已连接` : "Agent 已连接");
      } else {
        setAgentInfo("⚠ Gateway 未运行");
      }
    }).catch(() => setAgentInfo("⚠ 无法连接 API"));
  }, []);

  // ── Auto-scroll ──
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // ── Textarea resize ──
  const autoResize = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, []);

  // ── New chat ──
  const newChat = useCallback(() => {
    if (streaming) abortRef.current?.abort();
    setMessages([]);
    historyRef.current = [];
    setActiveId(null);
    sessionStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(HISTORY_KEY);
    setInput("");
    setTimeout(() => textareaRef.current?.focus(), 50);
  }, [streaming]);

  // ── Load historical session ──
  const loadSession = useCallback(async (id: string) => {
    if (streaming) return;
    setLoadingHist(true);
    try {
      const resp = await api.getSessionMessages(id);
      const msgs: Message[] = resp.messages
        .filter((m: SessionMessage) => m.role === "user" || m.role === "assistant")
        .filter((m: SessionMessage) => m.content)
        .map((m: SessionMessage) => ({ role: m.role as "user" | "assistant", content: m.content ?? "" }));

      setMessages(msgs);
      historyRef.current = msgs.map(m => ({ role: m.role, content: m.content }));
      setActiveId(id);
      sessionStorage.removeItem(STORAGE_KEY);
      sessionStorage.removeItem(HISTORY_KEY);
    } catch {
      // ignore
    } finally {
      setLoadingHist(false);
    }
  }, [streaming]);

  // ── Send message ──
  const sendMessage = useCallback(async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || streaming) return;

    setInput("");
    autoResize();

    const userMsg: Message = { role: "user", content };
    setMessages(prev => [...prev, userMsg]);
    historyRef.current = [...historyRef.current, { role: "user", content }];

    setMessages(prev => [...prev, { role: "assistant", content: "", streaming: true }]);
    setStreaming(true);

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const resp = await fetch("/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: "hermes-agent", messages: historyRef.current, stream: true }),
        signal: abort.signal,
      });

      if (!resp.ok) {
        const t = await resp.text().catch(() => `HTTP ${resp.status}`);
        let errMsg = `⚠️ HTTP ${resp.status}`;
        try { errMsg = `⚠️ ${JSON.parse(t).error?.message ?? t}`; } catch {}
        setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? { ...m, content: errMsg, streaming: false } : m));
        return;
      }

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "", fullText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop()!;
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]") break;
          try {
            const chunk = JSON.parse(raw);
            if (chunk.error) {
              fullText = `⚠️ ${chunk.error.message}`;
              setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? { ...m, content: fullText, streaming: false } : m));
              return;
            }
            const delta = chunk.choices?.[0]?.delta?.content ?? "";
            if (delta) {
              fullText += delta;
              setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? { ...m, content: fullText } : m));
            }
          } catch {}
        }
      }

      if (!fullText) fullText = "⚠️ Agent 未返回内容，请检查 API Key 和模型配置。";
      setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? { ...m, content: fullText, streaming: false } : m));

      if (!fullText.startsWith("⚠️")) {
        historyRef.current = [...historyRef.current, { role: "assistant", content: fullText }];
        // Refresh session list so new session appears in sidebar
        setTimeout(refreshSessions, 1500);
      }
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") return;
      const msg = `⚠️ 无法连接 Agent API\n${(e as Error).message}`;
      setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? { ...m, content: msg, streaming: false } : m));
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [input, streaming, autoResize, refreshSessions]);

  const onKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  }, [sendMessage]);

  const hasMessages = messages.length > 0;
  const groups = groupSessions(sessions);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-[calc(100vh-3rem)] -mt-4 sm:-mt-6 -mx-3 sm:-mx-6 overflow-hidden">

      {/* ── Sidebar ── */}
      <aside className={`
        flex flex-col shrink-0 border-r border-border bg-background transition-all duration-200 overflow-hidden
        ${sidebarOpen ? "w-56" : "w-0"}
      `}>
        {/* Sidebar header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
          <span className="font-display text-[0.65rem] tracking-[0.15em] uppercase text-muted-foreground">历史对话</span>
          <Button variant="ghost" size="sm" onClick={newChat} className="h-6 w-6 p-0" title="新对话">
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto py-1">
          {groups.length === 0 && (
            <div className="px-3 py-4 text-center text-muted-foreground/50 text-xs">暂无历史对话</div>
          )}
          {groups.map(group => (
            <div key={group.label}>
              <div className="px-3 pt-3 pb-1 font-display text-[0.6rem] tracking-widest uppercase text-muted-foreground/40">
                {group.label}
              </div>
              {group.items.map(s => (
                <button
                  key={s.id}
                  onClick={() => loadSession(s.id)}
                  className={`
                    w-full text-left px-3 py-2 text-xs leading-snug transition-colors rounded-none
                    hover:bg-muted/50
                    ${activeId === s.id ? "bg-muted text-foreground" : "text-muted-foreground"}
                  `}
                >
                  <div className="flex items-start gap-1.5">
                    <MessageSquare className="h-3 w-3 mt-0.5 shrink-0 opacity-50" />
                    <div className="flex-1 min-w-0">
                      <div className="truncate font-medium">{sessionTitle(s)}</div>
                      <div className="text-[0.6rem] opacity-50 mt-0.5">{relTime(s.last_active)}</div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ))}
        </div>
      </aside>

      {/* ── Main chat area ── */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Top bar */}
        <div className="flex items-center gap-2 border-b border-border px-3 py-2 bg-background/80 backdrop-blur-sm shrink-0">
          <Button
            variant="ghost" size="sm"
            onClick={() => setSidebarOpen(o => !o)}
            className="h-7 w-7 p-0 text-muted-foreground"
            title={sidebarOpen ? "收起历史" : "展开历史"}
          >
            {sidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </Button>

          <Bot className="h-4 w-4 text-muted-foreground shrink-0" />
          <span className="font-display text-[0.7rem] tracking-[0.12em] uppercase text-muted-foreground truncate flex-1">
            {activeId ? sessionTitle(sessions.find(s => s.id === activeId) ?? {} as SessionInfo) : "新对话"}
          </span>

          <Button variant="ghost" size="sm" onClick={newChat} className="h-7 gap-1 text-xs shrink-0">
            <Plus className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">新对话</span>
          </Button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {loadingHist ? (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm gap-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
              加载中...
            </div>
          ) : !hasMessages ? (
            /* Welcome */
            <div className="flex flex-col items-center justify-center h-full gap-5 max-w-lg mx-auto text-center">
              <div className="p-3 border border-border rounded-lg bg-background">
                <Bot className="h-7 w-7 text-muted-foreground" />
              </div>
              <div>
                <h2 className="font-display text-base font-bold tracking-wide uppercase mb-1">Hermes Agent</h2>
                <p className="text-sm text-muted-foreground">有什么我可以帮你做的？</p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full">
                {QUICK_ACTIONS.map(a => (
                  <button
                    key={a.text}
                    onClick={() => sendMessage(a.text)}
                    className="flex items-start gap-2.5 p-3 text-left border border-border rounded-lg bg-background hover:bg-muted/40 transition-colors text-sm"
                  >
                    <span className="text-base leading-none mt-0.5 shrink-0">{a.icon}</span>
                    <span className="text-muted-foreground leading-snug text-xs">{a.text}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Message list */
            <div className="max-w-3xl mx-auto space-y-4">
              {messages.map((msg, idx) => (
                <div key={idx} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  {msg.role === "assistant" && (
                    <div className="shrink-0 mt-1 h-7 w-7 rounded border border-border bg-background flex items-center justify-center">
                      <Bot className="h-4 w-4 text-muted-foreground" />
                    </div>
                  )}
                  <div className={`
                    max-w-[80%] rounded-lg px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap
                    ${msg.role === "user"
                      ? "bg-foreground text-background"
                      : "bg-muted/50 border border-border text-foreground"}
                  `}>
                    {msg.content || (
                      <span className="flex items-center gap-1.5 text-muted-foreground">
                        <span className="animate-pulse">●</span>
                        <span className="animate-pulse" style={{ animationDelay: "0.2s" }}>●</span>
                        <span className="animate-pulse" style={{ animationDelay: "0.4s" }}>●</span>
                      </span>
                    )}
                    {msg.streaming && msg.content && (
                      <span className="inline-block w-0.5 h-3.5 bg-current ml-0.5 animate-pulse align-middle" />
                    )}
                  </div>
                  {msg.role === "user" && (
                    <div className="shrink-0 mt-1 h-7 w-7 rounded border border-border bg-background flex items-center justify-center text-xs font-bold">
                      我
                    </div>
                  )}
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="shrink-0 border-t border-border px-4 py-3 bg-background/80 backdrop-blur-sm">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-end gap-2 border border-border rounded-lg bg-background p-2">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => { setInput(e.target.value); autoResize(); }}
                onKeyDown={onKeyDown}
                placeholder="输入消息，Shift+Enter 换行..."
                rows={1}
                disabled={streaming || loadingHist}
                className="flex-1 resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground min-h-[1.5rem] max-h-40 py-1 px-1"
              />
              {streaming ? (
                <Button variant="ghost" size="sm" onClick={() => abortRef.current?.abort()}
                  className="shrink-0 h-8 w-8 p-0 text-muted-foreground hover:text-destructive" title="停止">
                  <RotateCcw className="h-4 w-4" />
                </Button>
              ) : (
                <Button size="sm" onClick={() => sendMessage()} disabled={!input.trim() || loadingHist}
                  className="shrink-0 h-8 w-8 p-0" title="发送 (Enter)">
                  <Send className="h-4 w-4" />
                </Button>
              )}
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-muted-foreground/40">
              <Zap className="h-3 w-3" />
              <span className="font-display text-[0.6rem] tracking-widest uppercase">{agentInfo}</span>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

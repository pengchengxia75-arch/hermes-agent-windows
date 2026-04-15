import { useEffect, useRef, useState, useCallback } from "react";
import { Bot, Send, Plus, Zap, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/i18n";

// ── Types ──────────────────────────────────────────────────────────────────

interface Message {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

// ── Quick actions ──────────────────────────────────────────────────────────

const QUICK_ACTIONS = [
  { icon: "📊", text: "帮我分析数据并生成可视化报告" },
  { icon: "🔍", text: "搜索今日最新 AI 资讯并总结要点" },
  { icon: "⚡", text: "列出所有已安装的技能及功能简介" },
  { icon: "🌐", text: "打开浏览器搜索 GitHub Trending 今日热门项目" },
  { icon: "🧠", text: "查看我的对话记忆，总结了哪些重要信息" },
  { icon: "✅", text: "检查当前运行的进程和配置的定时任务" },
];

// ── Component ──────────────────────────────────────────────────────────────

const STORAGE_KEY = "hermes_chat_messages";
const HISTORY_KEY = "hermes_chat_history";

function loadSaved(): { messages: Message[]; history: { role: string; content: string }[] } {
  try {
    const msgs = sessionStorage.getItem(STORAGE_KEY);
    const hist = sessionStorage.getItem(HISTORY_KEY);
    return {
      messages: msgs ? JSON.parse(msgs) : [],
      history: hist ? JSON.parse(hist) : [],
    };
  } catch {
    return { messages: [], history: [] };
  }
}

export default function ChatPage() {
  const { t } = useI18n();
  const saved = loadSaved();
  const [messages, setMessages] = useState<Message[]>(saved.messages);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [agentInfo, setAgentInfo] = useState<string>("");
  const historyRef = useRef<{ role: string; content: string }[]>(saved.history);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ── Persist messages to sessionStorage on every change ──
  useEffect(() => {
    try {
      // Don't save mid-stream placeholders
      const toSave = messages.map(m => ({ ...m, streaming: false }));
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
      sessionStorage.setItem(HISTORY_KEY, JSON.stringify(historyRef.current));
    } catch { /* storage full or unavailable */ }
  }, [messages]);

  // ── Fetch model info for status hint ──
  useEffect(() => {
    fetch("/api/status")
      .then((r) => r.json())
      .then((d) => {
        if (d.gateway_running) {
          const model = d.active_model || "";
          const provider = d.active_provider || "";
          setAgentInfo(
            model || provider
              ? `${model}${provider ? " · " + provider : ""} · Agent 已连接`
              : "Agent 已连接"
          );
        } else {
          setAgentInfo("⚠ Agent 未运行 — 请先执行 hermes gateway run");
        }
      })
      .catch(() => setAgentInfo("⚠ 无法连接 Agent API"));
  }, []);

  // ── Auto-scroll ──
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Auto-resize textarea ──
  const autoResize = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, []);

  // ── New chat ──
  const newChat = useCallback(() => {
    if (streaming && abortRef.current) abortRef.current.abort();
    setMessages([]);
    historyRef.current = [];
    sessionStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(HISTORY_KEY);
    setInput("");
    setTimeout(() => textareaRef.current?.focus(), 50);
  }, [streaming]);

  // ── Send message ──
  const sendMessage = useCallback(
    async (text?: string) => {
      const content = (text ?? input).trim();
      if (!content || streaming) return;

      setInput("");
      autoResize();

      const userMsg: Message = { role: "user", content };
      setMessages((prev) => [...prev, userMsg]);
      historyRef.current = [...historyRef.current, { role: "user", content }];

      // Placeholder for assistant
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "", streaming: true },
      ]);
      setStreaming(true);

      const abort = new AbortController();
      abortRef.current = abort;

      try {
        const resp = await fetch("/v1/chat/completions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: "hermes-agent",
            messages: historyRef.current,
            stream: true,
          }),
          signal: abort.signal,
        });

        // Non-200: read as text and show error
        if (!resp.ok) {
          const errText = await resp.text().catch(() => `HTTP ${resp.status}`);
          let errMsg = `⚠️ HTTP ${resp.status}`;
          try {
            const j = JSON.parse(errText);
            errMsg = `⚠️ ${j.error?.message ?? errText}`;
          } catch {
            errMsg = `⚠️ ${errText}`;
          }
          setMessages((prev) =>
            prev.map((m, i) =>
              i === prev.length - 1 ? { ...m, content: errMsg, streaming: false } : m
            )
          );
          return;
        }

        // SSE streaming
        const reader = resp.body!.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        let fullText = "";

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
                setMessages((prev) =>
                  prev.map((m, i) =>
                    i === prev.length - 1
                      ? { ...m, content: fullText, streaming: false }
                      : m
                  )
                );
                return;
              }
              const delta = chunk.choices?.[0]?.delta?.content ?? "";
              if (delta) {
                fullText += delta;
                setMessages((prev) =>
                  prev.map((m, i) =>
                    i === prev.length - 1
                      ? { ...m, content: fullText }
                      : m
                  )
                );
              }
            } catch {
              // ignore parse error
            }
          }
        }

        if (!fullText) fullText = "⚠️ Agent 未返回内容，请检查 API Key 和模型配置。";

        setMessages((prev) =>
          prev.map((m, i) =>
            i === prev.length - 1 ? { ...m, content: fullText, streaming: false } : m
          )
        );

        if (!fullText.startsWith("⚠️")) {
          historyRef.current = [
            ...historyRef.current,
            { role: "assistant", content: fullText },
          ];
        }
      } catch (e: unknown) {
        if ((e as Error).name === "AbortError") return;
        const msg = `⚠️ 无法连接 Agent API\n${(e as Error).message}`;
        setMessages((prev) =>
          prev.map((m, i) =>
            i === prev.length - 1 ? { ...m, content: msg, streaming: false } : m
          )
        );
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [input, streaming, autoResize]
  );

  // ── Keyboard handler ──
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    },
    [sendMessage]
  );

  const hasMessages = messages.length > 0;

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -mt-4 sm:-mt-6 -mx-3 sm:-mx-6">
      {/* Top bar */}
      <div className="flex items-center justify-between border-b border-border px-4 sm:px-6 py-2 bg-background/80 backdrop-blur-sm shrink-0">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-muted-foreground" />
          <span className="font-display text-[0.75rem] tracking-[0.12em] uppercase text-muted-foreground">
            {t.app.nav.chat}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden sm:inline font-display text-[0.65rem] tracking-wider uppercase text-muted-foreground/60">
            {agentInfo}
          </span>
          <Button variant="ghost" size="sm" onClick={newChat} className="gap-1.5 text-xs">
            <Plus className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">新对话</span>
          </Button>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4">
        {!hasMessages ? (
          /* Welcome screen */
          <div className="flex flex-col items-center justify-center h-full gap-6 max-w-xl mx-auto text-center">
            <div className="p-3 border border-border rounded-lg bg-background">
              <Bot className="h-8 w-8 text-muted-foreground" />
            </div>
            <div>
              <h2 className="font-display text-lg font-bold tracking-wide uppercase mb-1">
                Hermes Agent
              </h2>
              <p className="text-sm text-muted-foreground">
                有什么我可以帮你做的？
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full">
              {QUICK_ACTIONS.map((a) => (
                <button
                  key={a.text}
                  onClick={() => sendMessage(a.text)}
                  className="flex items-start gap-3 p-3 text-left border border-border rounded-lg bg-background hover:bg-muted/40 transition-colors text-sm"
                >
                  <span className="text-lg leading-none mt-0.5 shrink-0">{a.icon}</span>
                  <span className="text-muted-foreground leading-snug">{a.text}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* Message list */
          <div className="max-w-3xl mx-auto space-y-4">
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.role === "assistant" && (
                  <div className="shrink-0 mt-1 h-7 w-7 rounded border border-border bg-background flex items-center justify-center">
                    <Bot className="h-4 w-4 text-muted-foreground" />
                  </div>
                )}
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-2.5 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-foreground text-background"
                      : "bg-muted/50 border border-border text-foreground"
                  }`}
                >
                  {msg.content || (
                    <span className="flex items-center gap-1.5 text-muted-foreground">
                      <span className="animate-pulse">●</span>
                      <span className="animate-pulse delay-100">●</span>
                      <span className="animate-pulse delay-200">●</span>
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

      {/* Input area */}
      <div className="shrink-0 border-t border-border px-4 sm:px-6 py-3 bg-background/80 backdrop-blur-sm">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-end gap-2 border border-border rounded-lg bg-background p-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => { setInput(e.target.value); autoResize(); }}
              onKeyDown={onKeyDown}
              placeholder="输入消息，Shift+Enter 换行..."
              rows={1}
              className="flex-1 resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground min-h-[1.5rem] max-h-40 py-1 px-1"
              disabled={streaming}
            />
            {streaming ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => abortRef.current?.abort()}
                className="shrink-0 h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                title="停止生成"
              >
                <RotateCcw className="h-4 w-4" />
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={() => sendMessage()}
                disabled={!input.trim()}
                className="shrink-0 h-8 w-8 p-0"
                title="发送 (Enter)"
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 text-muted-foreground/50">
            <Zap className="h-3 w-3" />
            <span className="font-display text-[0.6rem] tracking-widest uppercase">
              {agentInfo}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

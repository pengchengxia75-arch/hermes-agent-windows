// ===== State =====
let currentPage = 'chat';
let chatStarted = false;
let configSection = 'model';

// ===== API =====
const API = window.location.port === '19800'
  ? ''          // same origin when served by dashboard_api.py
  : 'http://localhost:19800';  // dev fallback

async function apiFetch(path, opts = {}) {
  try {
    const r = await fetch(API + path, opts);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } catch (e) {
    console.warn('API error', path, e.message);
    return null;
  }
}

// ===== Status bar =====
async function refreshStatus() {
  const data = await apiFetch('/api/status');
  if (!data) return;
  const hint = document.getElementById('chat-input-hint');
  if (hint) {
    const running = data.agent_running;
    hint.textContent = running
      ? `由 ${data.model} (${data.provider}) 提供支持 · Agent API 已连接`
      : `Agent API 未连接 (${API || 'localhost:19800'}) · 对话功能不可用`;
    hint.style.color = running ? '' : 'var(--warning)';
  }
  // Update overview status dots
  const dot = document.querySelector('#page-overview .status-dot');
  if (dot) dot.className = 'status-dot ' + (data.agent_running ? 'green' : 'red');
}

// Poll status every 15s
setInterval(refreshStatus, 15000);

// ===== Navigation =====
function navigate(page) {
  currentPage = page;
  document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });
  document.querySelectorAll('.page').forEach(el => {
    el.classList.toggle('active', el.id === 'page-' + page);
  });
  const historyPanel = document.getElementById('history-panel');
  if (historyPanel) historyPanel.style.display = (page === 'chat') ? 'flex' : 'none';
}

// ===== Sidebar collapse =====
function toggleSidebar() {
  const sb = document.querySelector('.sidebar');
  sb.classList.toggle('collapsed');
  const icon = document.getElementById('collapse-icon');
  if (icon) icon.textContent = sb.classList.contains('collapsed') ? '▶' : '◀';
}

// ===== Chat =====
const QUICK_ACTIONS = [
  { icon: '📊', text: '帮我分析这份数据并生成可视化图表和报告' },
  { icon: '📝', text: '把以下内容生成一份专业的 PPT 演示文稿' },
  { icon: '🔄', text: '帮我将文件转换为 Markdown 格式' },
  { icon: '🔍', text: '搜索今日最新 AI 资讯并总结要点' },
  { icon: '⚡', text: '列出所有已安装的技能及功能简介' },
  { icon: '🌐', text: '打开浏览器搜索 GitHub Trending 今日热门项目' },
  { icon: '🧠', text: '查看我的对话记忆，总结了哪些重要信息' },
  { icon: '✅', text: '检查当前运行的进程和配置的定时任务' },
];

function renderQuickActions() {
  const container = document.getElementById('quick-actions');
  if (!container) return;
  container.innerHTML = QUICK_ACTIONS.map(a => `
    <div class="quick-action" onclick="fillInput('${a.text.replace(/'/g, "\\'")}')">
      <span class="quick-action-icon">${a.icon}</span>
      <span class="quick-action-text">${a.text}</span>
    </div>
  `).join('');
}

function fillInput(text) {
  const ta = document.getElementById('chat-input');
  if (ta) { ta.value = text; ta.focus(); autoResize(ta); }
}

function autoResize(ta) {
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
}

// Chat history for current session (sent to API)
let _chatHistory = [];

async function sendMessage() {
  const ta = document.getElementById('chat-input');
  const text = ta.value.trim();
  if (!text) return;

  if (!chatStarted) {
    document.getElementById('chat-welcome').style.display = 'none';
    document.getElementById('chat-messages').style.display = 'flex';
    chatStarted = true;
  }

  appendMessage('user', text);
  _chatHistory.push({ role: 'user', content: text });
  ta.value = '';
  autoResize(ta);

  const typing = showTyping();

  try {
    const resp = await fetch(API + '/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'hermes-agent',
        messages: _chatHistory,
        stream: true,
      }),
    });

    removeTyping(typing);

    if (!resp.ok || !resp.body) {
      const err = await resp.text().catch(() => 'unknown error');
      appendMessage('assistant', `⚠️ 连接失败 (HTTP ${resp.status})\n\n请确认 Hermes Agent 已启动（hermes api-server）。`);
      return;
    }

    // Stream SSE
    const msgEl = appendMessage('assistant', '');
    let fullText = '';
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (raw === '[DONE]') break;
        try {
          const chunk = JSON.parse(raw);
          if (chunk.error) {
            fullText = `⚠️ ${chunk.error.message}`;
            const content = msgEl.querySelector('.message-content');
            if (content) content.textContent = fullText;
            break;
          }
          const delta = chunk.choices?.[0]?.delta?.content || '';
          if (delta) {
            fullText += delta;
            const content = msgEl.querySelector('.message-content');
            if (content) content.textContent = fullText;
            const msgs = document.getElementById('chat-messages');
            msgs.scrollTop = msgs.scrollHeight;
          }
        } catch (_) {}
      }
    }
    // If nothing came back at all, show a generic error
    if (!fullText) {
      const content = msgEl.querySelector('.message-content');
      if (content) content.textContent = '⚠️ Agent 未返回内容，请检查 API Key 和模型配置。';
    }
    if (fullText && !fullText.startsWith('⚠️')) {
      _chatHistory.push({ role: 'assistant', content: fullText });
    }

  } catch (e) {
    removeTyping(typing);
    appendMessage('assistant', `⚠️ 无法连接 Agent API (${API || 'localhost:19800'})\n\n${e.message}`);
  }
}

function appendMessage(role, text) {
  const messages = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'message ' + role;
  div.innerHTML = `
    <div class="message-avatar">${role === 'assistant' ? '⚕' : '我'}</div>
    <div class="message-body">
      <div class="message-name">${role === 'assistant' ? 'Hermes Agent' : '你'}</div>
      <div class="message-content"></div>
    </div>
  `;
  div.querySelector('.message-content').textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function showTyping() {
  const messages = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'message assistant typing-indicator';
  div.innerHTML = `
    <div class="message-avatar">⚕</div>
    <div class="message-body">
      <div class="message-name">Hermes Agent</div>
      <div class="message-content"><span class="typing-dots"><span>.</span><span>.</span><span>.</span></span></div>
    </div>
  `;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function removeTyping(el) {
  if (el && el.parentNode) el.parentNode.removeChild(el);
}

function newChat() {
  chatStarted = false;
  _chatHistory = [];
  document.getElementById('chat-welcome').style.display = 'flex';
  document.getElementById('chat-messages').style.display = 'none';
  document.getElementById('chat-messages').innerHTML = '';
  document.getElementById('chat-input').value = '';
}

// ===== History (left panel in chat) =====
async function renderHistory() {
  const list = document.getElementById('history-list');
  if (!list) return;
  const data = await apiFetch('/api/sessions?limit=30');
  const sessions = data?.sessions || [];
  if (!sessions.length) {
    list.innerHTML = '<div style="color:var(--text-muted);padding:16px 12px;font-size:12px">暂无历史对话</div>';
    return;
  }

  // Group by date
  const groups = {};
  for (const s of sessions) {
    const d = new Date((s.last_active || s.started_at) * 1000);
    const today = new Date(); today.setHours(0,0,0,0);
    const yesterday = new Date(today); yesterday.setDate(today.getDate()-1);
    let label;
    if (d >= today) label = '今天';
    else if (d >= yesterday) label = '昨天';
    else label = `${d.getMonth()+1}/${d.getDate()}`;
    if (!groups[label]) groups[label] = [];
    groups[label].push(s);
  }

  list.innerHTML = Object.entries(groups).map(([date, items]) => `
    <div class="history-date-label">${date}</div>
    ${items.map(s => `
      <div class="history-item" onclick="loadSession('${s.id}', this)">
        <div class="history-item-title">${escHtml(s.title || s.preview || '(无标题)').slice(0,40)}</div>
        <div class="history-item-meta">${s.message_count||0} 条消息 · ${_relTime(s.last_active||s.started_at)}</div>
      </div>
    `).join('')}
  `).join('');
}

async function loadSession(id, el) {
  document.querySelectorAll('.history-item').forEach(i => i.classList.remove('active'));
  el.classList.add('active');
  const data = await apiFetch(`/api/sessions/${id}/messages`);
  if (!data) return;
  const msgs = data.messages || [];

  _chatHistory = msgs
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .map(m => ({ role: m.role, content: String(m.content || '') }));

  document.getElementById('chat-welcome').style.display = 'none';
  const container = document.getElementById('chat-messages');
  container.style.display = 'flex';
  container.innerHTML = '';
  chatStarted = true;
  _chatHistory.forEach(m => appendMessage(m.role, m.content));
}

// ===== Overview =====
async function renderOverview() {
  const data = await apiFetch('/api/stats');
  const stats = data ? [
    { label: '总对话次数', value: data.total_sessions.toLocaleString(), sub: '全部来源', icon: '💬' },
    { label: '已使用 Token', value: data.total_tokens_fmt, sub: '累计消耗', icon: '⚡' },
    { label: '活跃技能',    value: String(data.active_skills), sub: '已安装',  icon: '🧩' },
    { label: '计划任务',    value: String(data.active_tasks),  sub: '已配置',  icon: '⏰' },
  ] : [
    { label: '总对话次数', value: '--', sub: '', icon: '💬' },
    { label: '已使用 Token', value: '--', sub: '', icon: '⚡' },
    { label: '活跃技能',    value: '--', sub: '', icon: '🧩' },
    { label: '计划任务',    value: '--', sub: '', icon: '⏰' },
  ];
  const grid = document.getElementById('stats-grid');
  if (grid) {
    grid.innerHTML = stats.map(s => `
      <div class="stat-card">
        <div class="stat-icon">${s.icon}</div>
        <div class="stat-label">${s.label}</div>
        <div class="stat-value">${s.value}</div>
        <div class="stat-sub">${s.sub}</div>
      </div>
    `).join('');
  }
}

// ===== Memory =====
let _memoryData = { memory: [], user: [] };
let memoryFilter = '全部';

async function renderMemory() {
  const container = document.getElementById('memory-list');
  if (!container) return;
  const data = await apiFetch('/api/memory');
  if (data) _memoryData = data;

  const allItems = [
    ..._memoryData.memory.map(t => ({ text: t, type: '记忆', icon: '🧠' })),
    ..._memoryData.user.map(t =>   ({ text: t, type: '用户', icon: '👤' })),
  ];
  const filtered = memoryFilter === '全部' ? allItems : allItems.filter(m => m.type === memoryFilter);

  if (!filtered.length) {
    container.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:40px">' +
      (data ? '暂无记忆' : 'API 未连接，无法加载记忆') + '</div>';
    return;
  }
  container.innerHTML = filtered.map((m, i) => `
    <div class="memory-item">
      <span class="memory-icon">${m.icon}</span>
      <div class="memory-body">
        <div class="memory-text">${escHtml(m.text)}</div>
        <div class="memory-meta"><span class="tag blue" style="padding:1px 6px;font-size:10px">${m.type}</span></div>
      </div>
      <div class="memory-actions">
        <button class="btn btn-danger btn-icon" title="删除"
          onclick="deleteMemory('${m.type === '用户' ? 'user' : 'memory'}', ${i})">🗑️</button>
      </div>
    </div>
  `).join('');
}

async function deleteMemory(target, index) {
  const list = target === 'user' ? _memoryData.user : _memoryData.memory;
  const text = list[index];
  if (!text || !confirm('确认删除这条记忆？')) return;
  await apiFetch('/api/memory', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target, text }),
  });
  renderMemory();
}

function filterMemory(type, el) {
  memoryFilter = type;
  document.querySelectorAll('#memory-filters .btn, #page-memory .btn').forEach(b => {
    if (b.dataset.filter !== undefined)
      b.className = 'btn ' + (b.dataset.filter === type ? 'btn-primary' : 'btn-ghost');
  });
  renderMemory();
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ===== Tasks =====
async function renderTasks() {
  const container = document.getElementById('tasks-list');
  if (!container) return;
  const data = await apiFetch('/api/cron');
  const jobs = data?.jobs || [];

  if (!jobs.length) {
    container.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:40px">' +
      (data ? '暂无计划任务' : 'API 未连接') + '</div>';
    return;
  }

  container.innerHTML = jobs.map(j => {
    const paused = j.paused || j.status === 'paused';
    const errored = j.last_exit_code && j.last_exit_code !== 0;
    const dot = errored ? 'red' : paused ? 'yellow' : 'green';
    const label = errored ? '错误' : paused ? '暂停' : '运行中';
    const schedule = j.schedule?.cron || j.cron || '--';
    const next = j.next_run_at ? new Date(j.next_run_at * 1000).toLocaleString('zh-CN') : '--';
    return `
      <div class="task-item">
        <div class="status-dot ${dot}"></div>
        <div class="task-info">
          <div class="task-name">${escHtml(j.name || j.id)}
            <span class="tag ${dot}" style="margin-left:8px">${label}</span>
          </div>
          <div class="task-cron">cron: ${schedule} · 下次执行: ${next}</div>
          <div class="task-desc">${escHtml(j.task || j.description || '')}</div>
        </div>
        <div class="task-actions">
          <button class="btn btn-ghost btn-icon" title="立即运行"
            onclick="runJob('${j.id}')">▶️</button>
          <button class="btn btn-danger btn-icon" title="删除">🗑️</button>
        </div>
      </div>`;
  }).join('');
}

async function runJob(id) {
  await apiFetch(`/api/cron/run/${id}`, { method: 'POST' });
  renderTasks();
}

// ===== Skills =====
const SKILLS = [
  { icon: '📊', name: 'data-viz',      desc: '数据可视化分析，生成图表和报告',    tag: '内置', enabled: true },
  { icon: '📝', name: 'pptx',          desc: '生成专业 PPT 演示文稿',           tag: '内置', enabled: true },
  { icon: '🌐', name: 'web-search',    desc: '浏览器搜索，获取最新网络资讯',     tag: '内置', enabled: true },
  { icon: '💻', name: 'code-runner',   desc: '执行代码，支持 Python/JS/Shell', tag: '内置', enabled: true },
  { icon: '📂', name: 'file-manager',  desc: '文件读写、格式转换、批量处理',     tag: '内置', enabled: true },
  { icon: '🧠', name: 'memory-flush',  desc: '对话记忆整理与压缩',             tag: '内置', enabled: true },
  { icon: '📅', name: 'scheduler',     desc: '创建和管理定时任务',             tag: '内置', enabled: true },
  { icon: '🔌', name: 'mcp-connector', desc: '连接 MCP 服务器，扩展工具能力',  tag: '实验性', enabled: false },
  { icon: '🎨', name: 'image-gen',     desc: 'AI 图像生成（FAL/ComfyUI）',   tag: '需配置', enabled: false },
  { icon: '🎙️', name: 'voice',        desc: '语音输入/输出，多种 TTS 引擎',  tag: '需配置', enabled: false },
  { icon: '📧', name: 'email',         desc: '邮件收发与自动化处理',           tag: '需配置', enabled: false },
  { icon: '🔔', name: 'notification',  desc: '多渠道通知（Telegram/飞书等）', tag: '需配置', enabled: false },
];

function renderSkills() {
  const container = document.getElementById('skills-grid');
  if (!container) return;
  container.innerHTML = SKILLS.map(s => `
    <div class="skill-card">
      <div class="skill-header">
        <span class="skill-icon">${s.icon}</span>
        <div>
          <div class="skill-name">${s.name}</div>
          <span class="tag ${s.tag === '内置' ? 'green' : s.tag === '实验性' ? 'yellow' : 'gray'}">${s.tag}</span>
        </div>
      </div>
      <div class="skill-desc">${s.desc}</div>
      <div class="skill-footer">
        <label class="toggle" title="${s.enabled ? '已启用' : '已禁用'}">
          <input type="checkbox" ${s.enabled ? 'checked' : ''}>
          <span class="toggle-slider"></span>
        </label>
        <button class="btn btn-ghost" style="padding:4px 10px;font-size:11px">详情</button>
      </div>
    </div>
  `).join('');
}

// ===== Sessions =====
function _relTime(ts) {
  if (!ts) return '--';
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff/60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff/3600)} 小时前`;
  return `${Math.floor(diff/86400)} 天前`;
}

function _fmtTokens(n) {
  if (!n) return '--';
  if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n/1000).toFixed(1) + 'K';
  return String(n);
}

async function renderSessions() {
  const tbody = document.getElementById('sessions-tbody');
  if (!tbody) return;
  const data = await apiFetch('/api/sessions?limit=30');
  const sessions = data?.sessions || [];

  if (!sessions.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:32px">
      ${data ? '暂无会话记录' : 'API 未连接'}</td></tr>`;
    return;
  }
  tbody.innerHTML = sessions.map(s => {
    const title = escHtml(s.title || s.preview || s.id.slice(0, 16));
    const tokens = _fmtTokens((s.input_tokens || 0) + (s.output_tokens || 0));
    const active = !s.ended_at;
    return `
      <tr>
        <td><span class="status-dot ${active ? 'green' : 'gray'}"></span>${title}</td>
        <td><span class="tag blue">${escHtml(s.model || '--')}</span></td>
        <td>${s.message_count || 0} 轮</td>
        <td>${tokens}</td>
        <td>${_relTime(s.last_active || s.started_at)}</td>
        <td>
          <button class="btn btn-ghost" style="padding:4px 10px;font-size:11px"
            onclick="viewSession('${s.id}')">查看</button>
          <button class="btn btn-danger" style="padding:4px 10px;font-size:11px">删除</button>
        </td>
      </tr>`;
  }).join('');
}

async function viewSession(id) {
  const data = await apiFetch(`/api/sessions/${id}/messages`);
  if (!data) return;
  const msgs = data.messages || [];
  alert(`会话 ${id}\n共 ${msgs.length} 条消息\n\n` +
    msgs.slice(0,3).map(m => `[${m.role}] ${String(m.content||'').slice(0,80)}`).join('\n'));
}

// ===== Model config =====
// provider → { label, baseUrl, apiKeyEnv }
const PROVIDER_META = {
  'kimi-coding':  { label: 'Kimi / Moonshot', baseUrl: 'https://api.moonshot.cn/v1',       apiKeyEnv: 'KIMI_API_KEY' },
  'moonshot':     { label: 'Moonshot',         baseUrl: 'https://api.moonshot.cn/v1',       apiKeyEnv: 'KIMI_API_KEY' },
  'minimax-cn':   { label: 'MiniMax (国内)',    baseUrl: 'https://api.minimaxi.com/v1',      apiKeyEnv: 'MINIMAX_API_KEY' },
  'minimax':      { label: 'MiniMax (国际)',    baseUrl: 'https://api.minimax.io/v1',        apiKeyEnv: 'MINIMAX_API_KEY' },
  'openrouter':   { label: 'OpenRouter',       baseUrl: 'https://openrouter.ai/api/v1',     apiKeyEnv: 'OPENROUTER_API_KEY' },
  'anthropic':    { label: 'Anthropic',        baseUrl: 'https://api.anthropic.com/v1',     apiKeyEnv: 'ANTHROPIC_API_KEY' },
  'deepseek':     { label: 'DeepSeek',         baseUrl: 'https://api.deepseek.com/v1',      apiKeyEnv: 'DEEPSEEK_API_KEY' },
  'custom':       { label: '自定义端点',        baseUrl: '',                                  apiKeyEnv: 'CUSTOM_API_KEY' },
};

let _providerModels = {};  // loaded from API
let _cfgEnvData = {};       // loaded from /api/config

async function loadModelConfig() {
  // Load provider→models mapping
  const pm = await apiFetch('/api/provider-models');
  if (pm) _providerModels = pm;

  // Load current config
  const cfg = await apiFetch('/api/config');
  if (!cfg) return;
  _cfgEnvData = cfg.env || {};
  const yaml = cfg.yaml || {};

  const provider = yaml.model?.provider || yaml.provider || 'kimi-coding';
  const model    = yaml.model?.default  || '';
  const baseUrl  = yaml.model?.base_url || PROVIDER_META[provider]?.baseUrl || '';

  // Set provider select
  const sel = document.getElementById('cfg-provider');
  if (sel) {
    // ensure option exists
    const exists = [...sel.options].some(o => o.value === provider);
    if (!exists) {
      const opt = document.createElement('option');
      opt.value = opt.textContent = provider;
      sel.appendChild(opt);
    }
    sel.value = provider;
  }

  // Populate model list
  _populateModelList(provider, model);

  // Base URL
  const urlEl = document.getElementById('cfg-baseurl');
  if (urlEl) urlEl.value = baseUrl;

  // API Key from env (already redacted server-side)
  const meta = PROVIDER_META[provider] || {};
  const keyEnv = meta.apiKeyEnv || '';
  const keyEl = document.getElementById('cfg-apikey');
  if (keyEl) {
    const val = _cfgEnvData[keyEnv] || '';
    keyEl.value = val;
    keyEl.placeholder = keyEnv ? `${keyEnv} (当前已设置)` : '输入 API Key';
  }

  // Update hint label
  const hint = document.querySelector('#cfg-apikey')?.closest('.form-group')?.querySelector('.form-hint');
  if (hint && keyEnv) hint.textContent = `变量名：${keyEnv} · 仅保存在本地 ~/.hermes/.env`;

  // Max tokens & temperature
  const maxTokens = yaml.model?.max_tokens || '';
  const temperature = yaml.model?.temperature || '';
  const mtEl = document.getElementById('cfg-maxtokens');
  if (mtEl && maxTokens) mtEl.value = maxTokens;
  const tempEl = document.getElementById('cfg-temperature');
  if (tempEl && temperature !== '') tempEl.value = temperature;
}

function _populateModelList(provider, selectedModel) {
  const wrapper = document.getElementById('cfg-model-wrapper');
  if (!wrapper) return;
  const models = _providerModels[provider] || [];
  const isCustom = provider === 'custom' || !models.length;

  if (isCustom) {
    // Replace with text input
    wrapper.innerHTML = `<input class="form-input" id="cfg-model" type="text"
      value="${selectedModel || ''}" placeholder="输入模型 ID，如 gpt-4o">`;
  } else {
    // Replace with select
    wrapper.innerHTML = `<select class="form-select" id="cfg-model">
      ${models.map(m => `<option value="${m}" ${m === selectedModel ? 'selected' : ''}>${m}</option>`).join('')}
    </select>`;
  }
}

function onProviderChange() {
  const provider = document.getElementById('cfg-provider')?.value;
  if (!provider) return;
  _populateModelList(provider, '');

  // Auto-fill base URL
  const meta = PROVIDER_META[provider] || {};
  const urlEl = document.getElementById('cfg-baseurl');
  if (urlEl && meta.baseUrl) urlEl.value = meta.baseUrl;

  // Update API key placeholder
  const keyEl = document.getElementById('cfg-apikey');
  if (keyEl) {
    const envKey = meta.apiKeyEnv || 'API_KEY';
    keyEl.value = _cfgEnvData[envKey] || '';
    keyEl.placeholder = `${envKey}`;
  }
  const hint = keyEl?.closest('.form-group')?.querySelector('.form-hint');
  if (hint && meta.apiKeyEnv) hint.textContent = `变量名：${meta.apiKeyEnv} · 仅保存在本地 ~/.hermes/.env`;
}

async function saveModelConfig() {
  const provider   = document.getElementById('cfg-provider')?.value   || '';
  const model      = document.getElementById('cfg-model')?.value      || '';
  const baseUrl    = document.getElementById('cfg-baseurl')?.value    || '';
  const apiKey     = document.getElementById('cfg-apikey')?.value     || '';
  const maxTokens  = document.getElementById('cfg-maxtokens')?.value  || '';
  const temperature= document.getElementById('cfg-temperature')?.value|| '';

  const meta = PROVIDER_META[provider] || {};
  const keyEnv = meta.apiKeyEnv || 'API_KEY';

  const saves = [
    apiFetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ type: 'yaml', key: 'model.default',  value: model }) }),
    apiFetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ type: 'yaml', key: 'model.provider', value: provider }) }),
    apiFetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ type: 'yaml', key: 'model.base_url', value: baseUrl }) }),
  ];
  if (maxTokens) saves.push(apiFetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ type: 'yaml', key: 'model.max_tokens', value: parseInt(maxTokens) }) }));
  if (temperature) saves.push(apiFetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ type: 'yaml', key: 'model.temperature', value: parseFloat(temperature) }) }));
  // Only save API key if user typed something new (not the masked placeholder)
  if (apiKey && !apiKey.includes('••••')) {
    saves.push(apiFetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ type: 'env', key: keyEnv, value: apiKey }) }));
  }

  await Promise.all(saves);

  const msg = document.getElementById('cfg-save-msg');
  if (msg) { msg.style.display = 'block'; setTimeout(() => msg.style.display = 'none', 2500); }
}

function toggleApiKeyVis() {
  const el = document.getElementById('cfg-apikey');
  if (el) el.type = el.type === 'password' ? 'text' : 'password';
}

// ===== Config sections =====
function switchConfigSection(section, el) {
  configSection = section;
  document.querySelectorAll('.config-nav .nav-item').forEach(i => i.classList.remove('active'));
  el.classList.add('active');
  document.querySelectorAll('.config-section').forEach(s => {
    s.classList.toggle('active', s.dataset.section === section);
  });
}

// ===== Logs =====
const LOGS = [
  { time: '14:12:33', level: 'INFO',    msg: 'run_agent: Loaded environment variables from C:\\Users\\xpc\\AppData\\Local\\hermes\\.env' },
  { time: '14:12:34', level: 'INFO',    msg: 'agent.auxiliary_client: Vision auto-detect: using active provider kimi-coding (kimi-k2.5)' },
  { time: '14:12:35', level: 'INFO',    msg: 'agent: Initialized with model kimi-k2.5, provider kimi-coding, endpoint api.moonshot.cn' },
  { time: '14:12:40', level: 'INFO',    msg: 'agent: Turn 1 started — user message: "你好"' },
  { time: '14:12:42', level: 'INFO',    msg: 'agent: Streaming response — 127 tokens' },
  { time: '14:12:45', level: 'INFO',    msg: 'agent: Turn 1 completed — 1,247 tokens total (prompt: 980, completion: 267)' },
  { time: '14:13:00', level: 'INFO',    msg: 'cron.scheduler: Next scheduled job: daily-news at 08:00 tomorrow' },
  { time: '14:15:22', level: 'INFO',    msg: 'agent: Turn 2 started — user message: "检查当前系统状态"' },
  { time: '14:15:24', level: 'INFO',    msg: 'agent: Tool call: exec — Get-Process | Select Name, CPU, WorkingSet' },
  { time: '14:15:26', level: 'INFO',    msg: 'agent: Tool result returned (423 chars)' },
  { time: '14:15:30', level: 'WARNING', msg: 'cli: Session context at 42% capacity — consider starting a new session' },
  { time: '14:15:35', level: 'INFO',    msg: 'agent: Turn 2 completed — 3,891 tokens total' },
  { time: '14:20:12', level: 'ERROR',   msg: 'gateway.feishu: Connection timeout after 30s — retrying (attempt 2/3)' },
  { time: '14:20:42', level: 'WARNING', msg: 'agent.credential_pool: KIMI_API_KEY rate limited (429) — backing off 5s' },
  { time: '14:20:48', level: 'INFO',    msg: 'agent.credential_pool: Retry succeeded after backoff' },
  { time: '14:25:00', level: 'INFO',    msg: 'memory: Flushing 6 memories to disk — total stored: 24' },
];

let logFilter = '全部级别';

async function renderLogs() {
  const container = document.getElementById('logs-container');
  if (!container) return;
  const level = logFilter === '全部级别' ? '' : logFilter;
  const data = await apiFetch(`/api/logs?limit=200${level ? '&level='+level : ''}`);
  const logs = data?.logs || [];
  if (!logs.length) {
    container.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">' +
      (data ? '暂无日志' : 'API 未连接') + '</div>';
    return;
  }
  container.innerHTML = logs.map(l => `
    <div class="log-line">
      <span class="log-time">${escHtml(l.time)}</span>
      <span class="log-level ${l.level}">${l.level}</span>
      <span class="log-msg">${escHtml(l.msg)}</span>
    </div>
  `).join('');
}

function setLogFilter(level) {
  logFilter = level;
  renderLogs();
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
  navigate('chat');
  renderQuickActions();
  renderHistory();
  refreshStatus();

  // Lazy-load other pages on first visit
  const _loaded = {};
  const _lazyRender = { overview: renderOverview, memory: renderMemory,
    tasks: renderTasks, skills: renderSkills, sessions: renderSessions, logs: renderLogs,
    config: loadModelConfig };
  const _origNavigate = window.navigate;
  window.navigate = function(page) {
    _origNavigate(page);
    if (_lazyRender[page] && !_loaded[page]) {
      _loaded[page] = true;
      _lazyRender[page]();
    }
  };

  // Chat input
  const ta = document.getElementById('chat-input');
  if (ta) {
    ta.addEventListener('input', () => autoResize(ta));
    ta.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
  }

  // History search
  const hs = document.getElementById('history-search-input');
  if (hs) {
    hs.addEventListener('input', () => {
      const q = hs.value.toLowerCase();
      document.querySelectorAll('.history-item').forEach(el => {
        el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }
});

// ===== Platform cards =====
function togglePlatform(id) {
  const card = document.getElementById('pc-' + id);
  if (card) card.classList.toggle('open');
}

function onPlatformToggle(id, checkbox) {
  const card = document.getElementById('pc-' + id);
  if (!card) return;
  if (checkbox.checked && !card.classList.contains('open')) {
    card.classList.add('open');
  }
  // Update status tag
  const label = card.querySelector('.toggle-label');
  const tag = label.querySelector('.tag');
  if (tag) {
    tag.className = 'tag ' + (checkbox.checked ? 'green' : 'gray');
    tag.style.fontSize = '10px'; tag.style.marginLeft = '6px';
    tag.textContent = checkbox.checked ? '已启用' : '';
    tag.style.display = checkbox.checked ? '' : 'none';
  }
}

function copyWebhook(platform) {
  const map = { feishu: 'feishu', wecom: 'wecom', telegram: 'telegram' };
  const path = map[platform] || platform;
  const text = `http://你的IP:8680/${path}/webhook`;
  navigator.clipboard.writeText(text).catch(() => {});
}

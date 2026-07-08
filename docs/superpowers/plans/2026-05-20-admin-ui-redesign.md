# Admin UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild all 3 frontend pages with custom CSS (no Pico CSS), dark sidebar + top bar + light content area, filter bar, professional admin panel look.

**Architecture:** Pure HTML/CSS/JS static pages served by FastAPI. No build step, no framework. Chart.js CDN for charts. All styles inlined. Three pages: login, dashboard, session-detail.

**Tech Stack:** HTML5, CSS3, Vanilla JS, Chart.js 4.4.7

---

### Task 1: Login Page Redesign

**Files:**
- Modify: `static/login.html`

- [ ] **Step 1: Rewrite login.html with custom CSS**

Replace entire file. Centered card on gray background (#f1f5f9), blue logo mark, rounded inputs, full-width submit button.

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>学生状态监测系统 - 登录</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; }
    .login-card { width: 380px; background: #fff; border-radius: 12px; padding: 36px 32px; box-shadow: 0 4px 24px rgba(0,0,0,0.06); }
    .logo { width: 44px; height: 44px; background: #3b82f6; color: #fff; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: 700; margin: 0 auto 12px; }
    .title { text-align: center; font-size: 16px; font-weight: 600; color: #1e293b; margin-bottom: 4px; }
    .subtitle { text-align: center; font-size: 12px; color: #94a3b8; margin-bottom: 28px; }
    .field { margin-bottom: 16px; }
    .field label { display: block; font-size: 12px; font-weight: 500; color: #475569; margin-bottom: 4px; }
    .field input { width: 100%; padding: 9px 12px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px; outline: none; transition: border .15s; }
    .field input:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
    .btn { width: 100%; padding: 10px; background: #3b82f6; color: #fff; border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; transition: background .15s; }
    .btn:hover { background: #2563eb; }
    .error { text-align: center; font-size: 12px; color: #dc2626; margin-top: 12px; display: none; }
    .version { text-align: center; font-size: 11px; color: #94a3b8; margin-top: 20px; }
  </style>
</head>
<body>
  <div>
    <div class="login-card">
      <div class="logo">S</div>
      <div class="title">学生状态监测系统</div>
      <div class="subtitle">管理员登录</div>
      <form id="loginForm">
        <div class="field">
          <label>用户名</label>
          <input type="text" id="username" required autofocus placeholder="admin">
        </div>
        <div class="field">
          <label>密码</label>
          <input type="password" id="password" required placeholder="········">
        </div>
        <button type="submit" class="btn">登 录</button>
        <div class="error" id="error">用户名或密码错误</div>
      </form>
    </div>
    <div class="version">Student Monitor v1.0</div>
  </div>
  <script>
    if (localStorage.getItem('token')) { window.location.href = '/static/dashboard.html'; }
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const errEl = document.getElementById('error');
      errEl.style.display = 'none';
      const resp = await fetch('/api/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ username: document.getElementById('username').value, password: document.getElementById('password').value })
      });
      if (resp.ok) {
        const data = await resp.json();
        localStorage.setItem('token', data.access_token);
        window.location.href = '/static/dashboard.html';
      } else {
        errEl.style.display = 'block';
      }
    });
  </script>
</body>
</html>
```

- [ ] **Step 2: Verify login still works**

Start backend (`python main.py`), open browser, verify login flow.

---

### Task 2: Dashboard Page Redesign

**Files:**
- Modify: `static/dashboard.html`

This is the largest change. Key sections:
1. Global CSS (no Pico CSS)
2. Layout: sidebar + top bar + main content
3. Filter bar
4. Stats row
5. Device cards grid
6. Detail panel (expandable)
7. Bind dialog (modal)
8. JS logic

- [ ] **Step 1: Write the full dashboard HTML**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>仪表盘 - 学生状态监测</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #f8fafc; color: #1e293b; }
    .app { display: flex; height: 100vh; }
    /* Sidebar */
    .sidebar { width: 220px; min-width: 220px; background: #0f172a; color: #fff; display: flex; flex-direction: column; }
    .sidebar-brand { padding: 16px; font-size: 14px; font-weight: 600; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; align-items: center; gap: 8px; }
    .sidebar-brand .dot { width: 8px; height: 8px; background: #3b82f6; border-radius: 50%; }
    .sidebar-nav { flex: 1; padding: 8px; }
    .sidebar-nav .item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 6px; font-size: 12px; color: rgba(255,255,255,0.6); cursor: pointer; margin-bottom: 2px; transition: all .15s; }
    .sidebar-nav .item:hover { color: #fff; background: rgba(255,255,255,0.06); }
    .sidebar-nav .item.active { color: #fff; background: #3b82f6; }
    .sidebar-devices { padding: 8px; border-top: 1px solid rgba(255,255,255,0.08); flex: 1; overflow-y: auto; }
    .sidebar-devices .label { font-size: 10px; text-transform: uppercase; color: rgba(255,255,255,0.35); padding: 8px 10px 4px; letter-spacing: 0.5px; }
    .sidebar-devices .dev-item { display: flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 4px; font-size: 11px; cursor: pointer; color: rgba(255,255,255,0.7); transition: all .15s; }
    .sidebar-devices .dev-item:hover { background: rgba(255,255,255,0.06); color: #fff; }
    .sidebar-devices .dev-item.active { background: rgba(59,130,246,0.2); color: #fff; }
    .dev-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
    .dev-dot.online { background: #10b981; }
    .dev-dot.offline { background: #64748b; }
    .sidebar-actions { padding: 8px; border-top: 1px solid rgba(255,255,255,0.08); }
    .sidebar-actions button { width: 100%; padding: 6px 10px; border-radius: 6px; border: none; font-size: 11px; cursor: pointer; margin-bottom: 4px; }
    .btn-bind { background: #3b82f6; color: #fff; }
    .btn-bind:hover { background: #2563eb; }
    .btn-logout { background: transparent; color: rgba(255,255,255,0.5); border: 1px solid rgba(255,255,255,0.1) !important; }
    .btn-logout:hover { color: #fff; background: rgba(255,255,255,0.05); }
    /* Top bar */
    .topbar { height: 44px; background: #fff; border-bottom: 1px solid #e2e8f0; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; font-size: 12px; color: #64748b; }
    .topbar .user { display: flex; align-items: center; gap: 6px; }
    .topbar .avatar { width: 24px; height: 24px; background: #3b82f6; color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600; }
    /* Main */
    .main-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
    .main-content { flex: 1; overflow-y: auto; padding: 20px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .page-header h2 { font-size: 18px; font-weight: 600; }
    .page-header .update-time { font-size: 11px; color: #94a3b8; }
    /* Stats */
    .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
    .stat-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; }
    .stat-card .stat-label { font-size: 11px; color: #64748b; margin-bottom: 4px; }
    .stat-card .stat-value { font-size: 22px; font-weight: 700; }
    .stat-card .stat-sub { font-size: 10px; color: #94a3b8; }
    /* Filter */
    .filter-bar { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .filter-bar .fl-label { font-size: 11px; font-weight: 600; color: #475569; }
    .filter-bar select { padding: 5px 8px; border: 1px solid #e2e8f0; border-radius: 4px; font-size: 11px; color: #334155; background: #fff; outline: none; }
    .filter-bar select:focus { border-color: #3b82f6; }
    .btn-sm { padding: 5px 12px; border-radius: 4px; border: none; font-size: 11px; cursor: pointer; }
    .btn-primary { background: #3b82f6; color: #fff; }
    .btn-primary:hover { background: #2563eb; }
    .btn-ghost { background: transparent; color: #3b82f6; }
    .btn-ghost:hover { background: #eff6ff; }
    .filter-spacer { flex: 1; }
    /* Cards grid */
    .cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; margin-bottom: 16px; }
    .device-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; cursor: pointer; transition: all .15s; border-left: 3px solid #e2e8f0; }
    .device-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
    .device-card.online { border-left-color: #10b981; }
    .device-card.offline { opacity: 0.5; border-left-color: #94a3b8; }
    .device-card.selected { border-color: #3b82f6; box-shadow: 0 0 0 1px #3b82f6; }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .card-header .name { font-size: 13px; font-weight: 600; }
    .card-metrics { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
    .card-metric .val { font-size: 16px; font-weight: 700; }
    .card-metric .lbl { font-size: 10px; color: #94a3b8; }
    .card-metric .val.alert-danger { color: #dc2626; }
    .card-metric .val.alert-warn { color: #d97706; }
    .card-footer { margin-top: 8px; font-size: 10px; color: #94a3b8; }
    /* Detail panel */
    .detail-panel { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 16px; display: none; }
    .detail-panel.visible { display: block; }
    .detail-panel h4 { font-size: 12px; color: #64748b; margin-bottom: 10px; }
    .detail-chart-wrap { height: 150px; margin-bottom: 10px; }
    .detail-link { text-align: right; font-size: 11px; }
    .detail-link a { color: #3b82f6; text-decoration: none; }
    .detail-link a:hover { text-decoration: underline; }
    /* Modal */
    .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100; align-items: center; justify-content: center; }
    .modal-overlay.open { display: flex; }
    .modal { background: #fff; border-radius: 12px; padding: 24px; width: 400px; box-shadow: 0 8px 32px rgba(0,0,0,0.12); }
    .modal h3 { font-size: 15px; margin-bottom: 16px; }
    .modal .field { margin-bottom: 12px; }
    .modal .field label { display: block; font-size: 11px; color: #475569; margin-bottom: 3px; }
    .modal .field input { width: 100%; padding: 7px 10px; border: 1px solid #e2e8f0; border-radius: 4px; font-size: 12px; outline: none; }
    .modal .field input:focus { border-color: #3b82f6; }
    .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
    .btn-cancel { padding: 6px 14px; border-radius: 4px; border: 1px solid #e2e8f0; background: #fff; font-size: 12px; cursor: pointer; color: #475569; }
    .btn-cancel:hover { background: #f8fafc; }
  </style>
</head>
<body>
<div class="app">
  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-brand"><span class="dot"></span> 学生状态监测</div>
    <div class="sidebar-nav">
      <div class="item active">📊 仪表盘</div>
    </div>
    <div class="sidebar-devices">
      <div class="label">设备列表</div>
      <div id="deviceList"></div>
    </div>
    <div class="sidebar-actions">
      <button class="btn-bind" id="bindBtn">+ 绑定设备</button>
      <button class="btn-logout" id="logoutBtn">退出登录</button>
    </div>
  </div>

  <!-- Main -->
  <div class="main-wrap">
    <div class="topbar">
      <span>仪表盘</span>
      <span class="user"><span class="avatar">A</span> admin</span>
    </div>
    <div class="main-content" id="mainContent">
      <!-- Stats -->
      <div class="stats-row" id="statsRow">
        <div class="stat-card"><div class="stat-label">在线设备</div><div class="stat-value" id="statOnline">0</div><div class="stat-sub" id="statTotal">/ 0</div></div>
        <div class="stat-card"><div class="stat-label">活跃告警</div><div class="stat-value" id="statAlerts" style="color:#dc2626;">0</div></div>
        <div class="stat-card"><div class="stat-label">进行中时段</div><div class="stat-value" id="statSessions">0</div></div>
        <div class="stat-card"><div class="stat-label">最近更新</div><div class="stat-value" id="statUpdate" style="font-size:14px;">--</div></div>
      </div>

      <!-- Filter -->
      <div class="filter-bar">
        <span class="fl-label">筛选</span>
        <select id="flDevice"><option value="">全部设备</option></select>
        <select id="flStatus"><option value="">全部状态</option><option value="online">在线</option><option value="offline">离线</option></select>
        <select id="flFatigue"><option value="">疲劳度: 全部</option><option value="0.5">&gt; 0.5</option><option value="0.7">&gt; 0.7</option></select>
        <select id="flDistraction"><option value="">分心度: 全部</option><option value="0.5">&gt; 0.5</option><option value="0.7">&gt; 0.7</option></select>
        <button class="btn-sm btn-primary" id="filterBtn">查询</button>
        <span class="filter-spacer"></span>
        <button class="btn-sm btn-ghost" id="resetBtn">重置</button>
      </div>

      <!-- Cards -->
      <div class="cards-grid" id="cardsGrid"></div>

      <!-- Detail -->
      <div class="detail-panel" id="detailPanel">
        <h4 id="detailTitle">设备详情</h4>
        <div class="detail-chart-wrap"><canvas id="detailChart"></canvas></div>
        <div class="detail-link"><a href="#" id="detailSessionLink">查看完整时段 →</a></div>
      </div>
    </div>
  </div>
</div>

<!-- Bind Modal -->
<div class="modal-overlay" id="bindModal">
  <div class="modal">
    <h3>绑定新设备</h3>
    <div class="field"><label>设备ID</label><input type="text" id="bindDeviceId" placeholder="设备唯一标识（UUID）"></div>
    <div class="field"><label>设备名称</label><input type="text" id="bindDeviceName" placeholder="给设备起个名字"></div>
    <div class="field"><label>绑定码（留空自动生成）</label><input type="text" id="bindCode" placeholder="4位绑定码"></div>
    <div class="modal-actions">
      <button class="btn-cancel" id="bindCancel">取消</button>
      <button class="btn-sm btn-primary" id="bindSubmit">绑定</button>
    </div>
  </div>
</div>

<script>
const token = localStorage.getItem('token');
if (!token) { window.location.href = '/static/login.html'; }

let allDevices = [], statuses = {}, currentDevice = null, chart = null, pollTimer = null;

async function api(url, opts = {}) {
  const res = await fetch(url, { ...opts, headers: { ...opts.headers, 'Authorization': `Bearer ${token}` } });
  if (res.status === 401) { localStorage.removeItem('token'); window.location.href = '/static/login.html'; }
  return res.json();
}

// Load devices
async function loadDevices() {
  allDevices = await api('/api/devices');
  renderSidebar();
  renderFilterOptions();
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollAll, 5000);
  pollAll();
}

function renderSidebar() {
  const el = document.getElementById('deviceList');
  el.innerHTML = allDevices.map(d => {
    const s = statuses[d.device_id];
    const online = s?.online;
    return `<div class="dev-item${currentDevice === d.device_id ? ' active' : ''}" data-did="${d.device_id}" onclick="selectDevice('${d.device_id}')">
      <span class="dev-dot ${online ? 'online' : 'offline'}"></span>${d.name || d.device_id}
    </div>`;
  }).join('') || '<div style="font-size:10px;color:rgba(255,255,255,0.3);padding:8px;">暂无设备</div>';
}

function renderFilterOptions() {
  const sel = document.getElementById('flDevice');
  sel.innerHTML = '<option value="">全部设备</option>' + allDevices.map(d => `<option value="${d.device_id}">${d.name || d.device_id}</option>`).join('');
}

async function pollAll() {
  if (!allDevices.length) return;
  const results = await Promise.all(allDevices.map(d => api(`/api/realtime/${d.device_id}`).catch(() => ({online:false,summary:{}}))));
  allDevices.forEach((d, i) => { statuses[d.device_id] = results[i]; });
  renderSidebar();
  renderCards();
  if (currentDevice) updateDetail();
}

// Filters
function getFilters() {
  return {
    device: document.getElementById('flDevice').value,
    status: document.getElementById('flStatus').value,
    fatigue: parseFloat(document.getElementById('flFatigue').value) || 0,
    distraction: parseFloat(document.getElementById('flDistraction').value) || 0,
  };
}

function applyFilters() {
  const f = getFilters();
  return allDevices.filter(d => {
    if (f.device && d.device_id !== f.device) return false;
    const s = statuses[d.device_id];
    if (!s) return !f.status; // no data, show if no status filter
    if (f.status === 'online' && !s.online) return false;
    if (f.status === 'offline' && s.online) return false;
    if (s.summary && Object.keys(s.summary).length) {
      if (f.fatigue && s.summary.avg_fatigue < f.fatigue) return false;
      if (f.distraction && s.summary.avg_distraction < f.distraction) return false;
    }
    return true;
  });
}

// Render cards
function renderCards() {
  const filtered = applyFilters();
  const grid = document.getElementById('cardsGrid');
  
  let onlineCount = 0, alertCount = 0, activeSessions = 0;
  allDevices.forEach(d => {
    const s = statuses[d.device_id];
    if (s?.online) onlineCount++;
    if (s?.summary && Object.keys(s.summary).length) {
      activeSessions++;
      if (s.summary.avg_fatigue > 0.5 || s.summary.avg_distraction > 0.5) alertCount++;
    }
  });
  document.getElementById('statOnline').textContent = onlineCount;
  document.getElementById('statTotal').textContent = `/ ${allDevices.length}`;
  document.getElementById('statAlerts').textContent = alertCount;
  document.getElementById('statSessions').textContent = activeSessions;
  document.getElementById('statUpdate').textContent = new Date().toLocaleTimeString();

  grid.innerHTML = filtered.map(d => {
    const s = statuses[d.device_id];
    const online = s?.online;
    const sm = (s?.summary && Object.keys(s.summary).length) ? s.summary : null;
    const fat = sm ? sm.avg_fatigue : null;
    const dis = sm ? sm.avg_distraction : null;
    const dif = sm ? sm.avg_difficulty : null;
    const fatClass = fat !== null && fat > 0.5 ? 'alert-danger' : '';
    const disClass = dis !== null && dis > 0.5 ? 'alert-warn' : '';
    return `<div class="device-card ${online ? 'online' : 'offline'}${currentDevice===d.device_id?' selected':''}" onclick="selectDevice('${d.device_id}')">
      <div class="card-header">
        <span class="name">${d.name || d.device_id}</span>
        <span class="dev-dot ${online ? 'online' : 'offline'}"></span>
      </div>
      <div class="card-metrics">
        <div class="card-metric"><div class="val ${fatClass}">${fat!==null?fat.toFixed(2):'--'}</div><div class="lbl">疲劳度</div></div>
        <div class="card-metric"><div class="val ${disClass}">${dis!==null?dis.toFixed(2):'--'}</div><div class="lbl">分心度</div></div>
        <div class="card-metric"><div class="val">${dif!==null?dif.toFixed(2):'--'}</div><div class="lbl">困难度</div></div>
      </div>
      <div class="card-footer">${sm ? `动作: ${sm.current_action} · 注视: ${sm.current_gaze}` : (online ? '等待数据...' : '离线')}</div>
    </div>`;
  }).join('') || '<div style="grid-column:1/-1;text-align:center;color:#94a3b8;padding:40px;">无匹配设备</div>';
}

// Device selection
function selectDevice(did) {
  currentDevice = currentDevice === did ? null : did;
  renderSidebar();
  renderCards();
  if (currentDevice) updateDetail();
  else document.getElementById('detailPanel').classList.remove('visible');
}

function updateDetail() {
  if (!currentDevice) return;
  const s = statuses[currentDevice];
  if (!s || !s.summary || !Object.keys(s.summary).length) {
    document.getElementById('detailPanel').classList.remove('visible');
    return;
  }
  const panel = document.getElementById('detailPanel');
  panel.classList.add('visible');
  document.getElementById('detailTitle').textContent = `${currentDevice} · 实时趋势`;
  const link = document.getElementById('detailSessionLink');
  link.href = s.session_id ? `/static/session.html?id=${s.session_id}` : '#';
  link.style.display = s.session_id ? '' : 'none';

  const canvas = document.getElementById('detailChart');
  if (!canvas) return;
  if (chart) chart.destroy();
  const sm = s.summary;
  chart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: [new Date().toLocaleTimeString()],
      datasets: [
        { label: '疲劳', data: [sm.avg_fatigue], borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.05)', tension: 0.3, fill: true },
        { label: '分心', data: [sm.avg_distraction], borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.05)', tension: 0.3, fill: true },
        { label: '困难', data: [sm.avg_difficulty], borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,0.05)', tension: 0.3, fill: true },
      ]
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: 0, max: 1 } }, plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } } }
  });
}

// Filter events
document.getElementById('filterBtn').onclick = renderCards;
document.getElementById('resetBtn').onclick = () => {
  document.getElementById('flDevice').value = '';
  document.getElementById('flStatus').value = '';
  document.getElementById('flFatigue').value = '';
  document.getElementById('flDistraction').value = '';
  renderCards();
};

// Bind modal
document.getElementById('bindBtn').onclick = () => document.getElementById('bindModal').classList.add('open');
document.getElementById('bindCancel').onclick = () => document.getElementById('bindModal').classList.remove('open');
document.getElementById('bindSubmit').onclick = async () => {
  const deviceId = document.getElementById('bindDeviceId').value.trim();
  const name = document.getElementById('bindDeviceName').value.trim();
  const code = document.getElementById('bindCode').value.trim();
  if (!deviceId) return alert('请输入设备ID');
  const res = await api('/api/devices/bind', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({device_id:deviceId,name,bind_code:code}) });
  if (res.bind_code) alert(`绑定成功！绑定码: ${res.bind_code}`);
  else if (res.status === 'ok') alert('绑定成功');
  document.getElementById('bindModal').classList.remove('open');
  loadDevices();
};
document.getElementById('logoutBtn').onclick = () => { localStorage.removeItem('token'); window.location.href = '/static/login.html'; };

// Start
loadDevices();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify dashboard works**

Open browser, log in, verify: sidebar shows devices, cards render, filters work, clicking a device shows detail panel.

---

### Task 3: Session Detail Page Redesign

**Files:**
- Modify: `static/session.html`

- [ ] **Step 1: Write the full session detail HTML**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>时段详情 - 学生状态监测</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #f8fafc; color: #1e293b; }
    .topbar { height: 44px; background: #fff; border-bottom: 1px solid #e2e8f0; display: flex; align-items: center; padding: 0 20px; font-size: 12px; }
    .topbar a { color: #3b82f6; text-decoration: none; }
    .topbar a:hover { text-decoration: underline; }
    .container { max-width: 1100px; margin: 0 auto; padding: 24px 20px; }
    .page-header { margin-bottom: 20px; }
    .page-header h1 { font-size: 18px; font-weight: 600; }
    .page-header .meta { font-size: 11px; color: #64748b; margin-top: 4px; }
    .summary-cards { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 20px; }
    .s-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; text-align: center; }
    .s-card .val { font-size: 22px; font-weight: 700; }
    .s-card .lbl { font-size: 10px; color: #64748b; margin-top: 2px; }
    .chart-box { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
    .chart-box h3 { font-size: 13px; font-weight: 600; margin-bottom: 12px; }
    .chart-wrap { height: 250px; }
    .timeline-box { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }
    .timeline-box h3 { font-size: 13px; font-weight: 600; margin-bottom: 12px; }
    .tl-track { position: relative; padding-left: 20px; border-left: 2px solid #e2e8f0; margin-left: 8px; }
    .tl-item { position: relative; margin-bottom: 12px; }
    .tl-dot { position: absolute; left: -27px; top: 3px; width: 10px; height: 10px; border-radius: 50%; border: 2px solid #fff; }
    .tl-dot.fatigue { background: #dc2626; }
    .tl-dot.distraction { background: #d97706; }
    .tl-dot.difficulty { background: #3b82f6; }
    .tl-dot.action { background: #94a3b8; }
    .tl-time { font-size: 10px; color: #94a3b8; }
    .tl-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; margin-left: 4px; }
    .tl-tag.fatigue { background: #fee2e2; color: #dc2626; }
    .tl-tag.distraction { background: #fef3c7; color: #d97706; }
    .tl-tag.difficulty { background: #dbeafe; color: #1e40af; }
    .tl-tag.action { background: #f1f5f9; color: #64748b; }
    .tl-detail { font-size: 10px; color: #94a3b8; margin-left: 4px; }
    .load-more { text-align: center; margin-top: 12px; font-size: 11px; color: #3b82f6; cursor: pointer; }
    .load-more:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="topbar"><a href="/static/dashboard.html">← 返回仪表盘</a></div>
  <div class="container">
    <div class="page-header">
      <h1 id="title">时段详情</h1>
      <div class="meta" id="meta"></div>
    </div>
    <div class="summary-cards" id="summaryCards"></div>
    <div class="chart-box">
      <h3>指标趋势</h3>
      <div class="chart-wrap"><canvas id="trendChart"></canvas></div>
    </div>
    <div class="timeline-box">
      <h3>事件时间线</h3>
      <div class="tl-track" id="timeline"></div>
      <div class="load-more" id="loadMore" style="display:none;">加载更多...</div>
    </div>
  </div>

<script>
const token = localStorage.getItem('token');
if (!token) { window.location.href = '/static/login.html'; }

const params = new URLSearchParams(window.location.search);
const sessionId = params.get('id');
let allEvents = [], shownCount = 0, pageSize = 50;

async function load() {
  const resp = await fetch(`/api/sessions/${sessionId}`, { headers: {'Authorization': `Bearer ${token}`} });
  if (!resp.ok) { document.getElementById('title').textContent = '加载失败'; return; }
  const data = await resp.json();
  if (!data.timeline || !data.timeline.length) { document.getElementById('title').textContent = '暂无数据'; return; }

  document.getElementById('title').textContent = `设备 ${data.device_id}`;
  document.getElementById('meta').textContent = `${new Date(data.start_time).toLocaleString()} · 状态: ${data.status === 'active' ? '进行中' : '已结束'}${data.end_time ? ' · 结束: ' + new Date(data.end_time).toLocaleString() : ''}`;

  const tl = data.timeline;
  const avgF = (tl.reduce((s,r) => s+r.fatigue_level, 0) / tl.length).toFixed(2);
  const avgD = (tl.reduce((s,r) => s+r.distraction_level, 0) / tl.length).toFixed(2);
  const avgDiff = (tl.reduce((s,r) => s+r.difficulty_indicator, 0) / tl.length).toFixed(2);
  const maxDiff = Math.max(...tl.map(r => r.difficulty_indicator)).toFixed(2);

  document.getElementById('summaryCards').innerHTML = `
    <div class="s-card"><div class="val">${tl.length}</div><div class="lbl">分析帧数</div></div>
    <div class="s-card"><div class="val">${avgF}</div><div class="lbl">平均疲劳度</div></div>
    <div class="s-card"><div class="val">${avgD}</div><div class="lbl">平均分心度</div></div>
    <div class="s-card"><div class="val" style="color:#d97706;">${maxDiff}</div><div class="lbl">最高困难度</div></div>
    <div class="s-card"><div class="val" style="color:#dc2626;" id="alertCount">--</div><div class="lbl">异常事件</div></div>
  `;

  // Build events
  allEvents = [];
  tl.forEach(r => {
    const t = r.timestamp;
    if (r.fatigue_level > 0.5) allEvents.push({t, type:'fatigue', label:'疲劳告警', detail:`疲劳度 ${r.fatigue_level.toFixed(2)}`});
    if (r.distraction_level > 0.5) allEvents.push({t, type:'distraction', label:'分心告警', detail:`分心度 ${r.distraction_level.toFixed(2)}`});
    if (r.difficulty_indicator > 0.5) allEvents.push({t, type:'difficulty', label:'困难度升高', detail:`困难度 ${r.difficulty_indicator.toFixed(2)}`});
  });
  document.getElementById('alertCount').textContent = allEvents.length;

  // Chart
  new Chart(document.getElementById('trendChart'), {
    type: 'line',
    data: {
      labels: tl.map(r => new Date(r.timestamp).toLocaleTimeString()),
      datasets: [
        { label: '疲劳度', data: tl.map(r => r.fatigue_level), borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.04)', tension: 0.2, fill: true },
        { label: '分心度', data: tl.map(r => r.distraction_level), borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.04)', tension: 0.2, fill: true },
        { label: '困难度', data: tl.map(r => r.difficulty_indicator), borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,0.04)', tension: 0.2, fill: true },
      ]
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: 0, max: 1 } }, plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } } }
  });

  renderTimeline();
}

function renderTimeline() {
  shownCount = Math.min(shownCount + pageSize, allEvents.length);
  const html = allEvents.slice(0, shownCount).map(e => `
    <div class="tl-item">
      <div class="tl-dot ${e.type}"></div>
      <span class="tl-time">${new Date(e.t).toLocaleTimeString()}</span>
      <span class="tl-tag ${e.type}">${e.label}</span>
      <span class="tl-detail">${e.detail}</span>
    </div>
  `).join('') || '<div style="font-size:11px;color:#94a3b8;">无异常事件</div>';
  document.getElementById('timeline').innerHTML = html;
  document.getElementById('loadMore').style.display = shownCount < allEvents.length ? '' : 'none';
}

document.getElementById('loadMore').onclick = renderTimeline;
load();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify**

Open dashboard, click "查看时段详情" on any device card, confirm timeline and chart render correctly.

---

### Task 4: Final Verification

- [ ] **Step 1: Run full flow**

```bash
# Terminal 1
python main.py

# Terminal 2
python simulate_devices.py 3 3

# Browser: open http://localhost:8000
# 1. Login (admin / admin123)
# 2. See 3 device cards with live data
# 3. Apply filters (fatigue > 0.5)
# 4. Click a device card -> see detail panel expand
# 5. Click "查看完整时段" -> see session detail page with chart + timeline
```

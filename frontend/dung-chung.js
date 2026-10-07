/* ========== SafeVoice AI — COMMON JS ========== */

const API_BASE = (window.location.protocol === 'file:' || window.location.port === '5500') 
    ? 'http://localhost:5085' 
    : window.location.origin;
const WS_BASE = API_BASE.replace('http', 'ws');

/* ========== JWT HELPERS ========== */
function getToken() {
  return localStorage.getItem('sg_access_token');
}

function getRefreshToken() {
  return localStorage.getItem('sg_refresh_token');
}

function setTokens(access, refresh) {
  localStorage.setItem('sg_access_token', access);
  if (refresh) localStorage.setItem('sg_refresh_token', refresh);
}

function removeTokens() {
  localStorage.removeItem('sg_access_token');
  localStorage.removeItem('sg_refresh_token');
}

function decodeJwt(token) {
  try {
    const base64 = token.split('.')[1];
    const decoded = atob(base64.replace(/-/g, '+').replace(/_/g, '/'));
    const json = decodeURIComponent(escape(decoded));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function getCurrentUser() {
  const token = getToken();
  if (!token) return null;
  const payload = decodeJwt(token);
  if (!payload) return null;
  // Check expiry
  if (payload.exp && payload.exp * 1000 < Date.now()) {
    return null;
  }
  return payload;
}

function checkAuth() {
  const user = getCurrentUser();
  if (!user) {
    // Token expired — try refresh in background, redirect if no refresh token
    const rt = getRefreshToken();
    if (rt) {
      // Kick off refresh and reload (async, page will reload)
      refreshToken(rt);
      return null;
    }
    window.location.href = '/dang-nhap.html';
    return null;
  }
  return user;
}

async function refreshToken(rt) {
  try {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rt }),
    });
    if (res.ok) {
      const data = await res.json();
      setTokens(data.access_token, null);
      window.location.reload();
    } else {
      removeTokens();
      window.location.href = '/dang-nhap.html';
    }
  } catch {
    removeTokens();
    window.location.href = '/dang-nhap.html';
  }
}

/* ========== API HELPER ========== */
async function api(method, url, body = null) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const opts = { method, headers };
  if (body && method !== 'GET') {
    opts.body = JSON.stringify(body);
  }

  const res = await fetch(`${API_BASE}${url}`, opts);

  if (res.status === 401) {
    const rt = getRefreshToken();
    if (rt) {
      await refreshToken(rt);
      return;
    }
    removeTokens();
    window.location.href = '/dang-nhap.html';
    return;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: 'Lỗi không xác định' }));
    throw new Error(err.message || `HTTP ${res.status}`);
  }

  return res.json();
}

/* ========== WEBSOCKET ========== */
let socket = null;
let wsCallbacks = [];

function setupWebSocket() {
  if (typeof signalR === 'undefined') {
    const script = document.createElement('script');
    script.src = '/vendor/signalr.min.js';
    script.onload = () => connectWebSocket();
    document.head.appendChild(script);
  } else {
    connectWebSocket();
  }
}

async function connectWebSocket() {
  try {
    const token = getToken();
    if (!token) return;

    socket = new signalR.HubConnectionBuilder()
      .withUrl(`${API_BASE}/ws/alerts`, {
         accessTokenFactory: () => token
      })
      .withAutomaticReconnect()
      .build();

    socket.on('new-alert', (alert) => {
      console.log('🚨 New alert:', alert);
      showAlertToast(alert);
      playAlertSound();
      updateNotificationBadge();
      wsCallbacks.forEach(cb => {
        if (cb.event === 'new-alert') cb.fn(alert);
      });
    });

    socket.on('alert-updated', (alert) => {
      console.log('✅ Alert updated:', alert);
      wsCallbacks.forEach(cb => {
        if (cb.event === 'alert-updated') cb.fn(alert);
      });
    });

    await socket.start();
    console.log('🔌 WebSocket (SignalR) connected');
  } catch (err) {
    console.error('WebSocket connection failed:', err);
    setTimeout(connectWebSocket, 5000);
  }
}

function onWsEvent(event, fn) {
  wsCallbacks.push({ event, fn });
}

/* ========== TOAST NOTIFICATIONS ========== */
function showToast(title, message, severity = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const icons = { danger: '<i class="bi bi-exclamation-triangle"></i>', warning: '<i class="bi bi-exclamation-circle"></i>', success: '<i class="bi bi-check-circle"></i>', info: '<i class="bi bi-info-circle"></i>' };

  const toast = document.createElement('div');
  toast.className = `toast ${severity}`;
  toast.innerHTML = `
    <div class="toast-icon">${icons[severity] || 'ℹ️'}</div>
    <div class="toast-content">
      <div class="toast-title">${title}</div>
      <div class="toast-message">${message}</div>
    </div>
    <button class="toast-close" onclick="this.parentElement.remove()">✕</button>
  `;

  container.appendChild(toast);
  setTimeout(() => toast.remove(), 6000);
  toast.addEventListener('click', () => toast.remove());
}

function showAlertToast(alert) {
  const typeLabels = {
    dap_pha: '<i class="bi bi-hammer" style="color:var(--danger)"></i> Đập phá / Đánh đập',
    scream: '<i class="bi bi-volume-up" style="color:var(--danger)"></i> Gào thét / La hét',
    help: '<i class="bi bi-person-arms-up" style="color:var(--warning)"></i> Kêu cứu / Van xin',
    threat: '<i class="bi bi-shield-exclamation" style="color:var(--caution)"></i> Đe dọa',
    argument: '<i class="bi bi-chat-right-text" style="color:var(--info)"></i> Cãi vã',
  };

  const severity = alert.risk_level === 'high' ? 'danger' : alert.risk_level === 'review' ? 'warning' : 'info';
  const area = alert.device?.area?.name || alert.device?.area || 'Không xác định';
  const label = typeLabels[alert.sound_type] || alert.sound_type;

  showToast(
    `${label}`,
    `Khu vực: ${area} — Nguy cơ: ${riskLabel(alert)}<br/><br/>
    <small style="font-style:italic;color:#666;">${alert.notes ? alert.notes : ''}</small>`,
    severity
  );
}

/* ========== NOTIFICATION SOUND ========== */
let audioCtx = null;
function playAlertSound() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(880, audioCtx.currentTime);
    oscillator.frequency.setValueAtTime(660, audioCtx.currentTime + 0.1);
    oscillator.frequency.setValueAtTime(880, audioCtx.currentTime + 0.2);
    gainNode.gain.setValueAtTime(0.3, audioCtx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.5);
    oscillator.start(audioCtx.currentTime);
    oscillator.stop(audioCtx.currentTime + 0.5);
  } catch (e) {
    console.log('Could not play alert sound:', e);
  }
}

/* ========== NOTIFICATION BADGE ========== */
let pendingCount = 0;
async function updateNotificationBadge() {
  try {
    const data = await api('GET', '/api/statistics/summary');
    pendingCount = data.pending_urgent || 0;
    const badge = document.getElementById('notification-badge');
    if (badge) {
      badge.textContent = pendingCount;
      badge.style.display = pendingCount > 0 ? 'flex' : 'none';
    }
  } catch {}
}

/* ========== DARK MODE ========== */
function initTheme() {
  const saved = localStorage.getItem('sg_theme') || 'light';
  document.documentElement.setAttribute('data-theme', saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('sg_theme', next);
}

/* ========== RENDER APP SHELL ========== */
function renderAppShell(activePageId) {
  const user = getCurrentUser();
  if (!user) return;

  const roleLabels = {
    admin: 'Quản trị viên',
    ban_giam_hieu: 'Ban giám hiệu',
    giam_thi: 'Giám thị',
    bao_ve: 'Bảo vệ',
  };

  const initials = (user.name || 'U').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

  const navItems = [
    { id: 'dashboard', icon: '<i class="bi bi-grid-1x2"></i>', label: 'Tổng quan', href: '/tong-quan.html' },
    { id: 'alerts', icon: '<i class="bi bi-exclamation-triangle"></i>', label: 'Cảnh báo trực tiếp', href: '/canh-bao.html', badge: true },
    { id: 'history', icon: '<i class="bi bi-clock-history"></i>', label: 'Lịch sử cảnh báo', href: '/lich-su.html' },
    { id: 'statistics', icon: '<i class="bi bi-bar-chart-line"></i>', label: 'Thống kê', href: '/thong-ke.html' }
  ];

  if (user.role !== 'phu_huynh') {
    navItems.push({ id: 'devices', icon: '<i class="bi bi-mic"></i>', label: 'Thiết bị', href: '/thiet-bi.html' });
  }

  if (user.role === 'admin') {
    navItems.push({ id: 'users', icon: '<i class="bi bi-people"></i>', label: 'Người dùng', href: '/nguoi-dung.html' });
    navItems.push({ id: 'areas', icon: '<i class="bi bi-map"></i>', label: 'Khu vực', href: '/khu-vuc.html' });
  }

  navItems.push({ id: 'settings', icon: '<i class="bi bi-gear"></i>', label: 'Cài đặt', href: '/cai-dat.html' });

  const pageTitles = {
    dashboard: 'Tổng quan',
    alerts: 'Cảnh báo trực tiếp',
    analyze: 'Cắt âm thanh AI',
    history: 'Lịch sử cảnh báo',
    statistics: 'Thống kê',
    devices: 'Quản lý thiết bị',
    users: 'Quản lý người dùng',
    areas: 'Quản lý khu vực',
    settings: 'Cài đặt hệ thống',
  };

  const shell = document.getElementById('app-shell');
  if (!shell) return;

  shell.innerHTML = `
    <!-- Sidebar -->
    <aside class="sidebar" id="sidebar">
      <div class="sidebar-brand">
        <div class="brand-icon"><img src="/logo.png" alt="Logo"></div>
        <div>
          <h1>SafeVoice</h1>
          <span class="brand-sub">AI Monitoring System</span>
        </div>
      </div>
      <nav class="sidebar-nav">
        <div class="nav-section">
          <div class="nav-section-title">Giám sát</div>
          ${navItems.slice(0, 4).map(item => `
            <a href="${item.href}" class="nav-item ${activePageId === item.id ? 'active' : ''}">
              <span class="nav-icon">${item.icon}</span>
              <span>${item.label}</span>
              ${item.badge ? `<span class="nav-badge" id="sidebar-alert-badge" style="display:none">0</span>` : ''}
            </a>
          `).join('')}
        </div>
        <div class="nav-section">
          <div class="nav-section-title">Quản lý</div>
          ${navItems.slice(5).map(item => `
            <a href="${item.href}" class="nav-item ${activePageId === item.id ? 'active' : ''}">
              <span class="nav-icon">${item.icon}</span>
              <span>${item.label}</span>
            </a>
          `).join('')}
        </div>
      </nav>
    </aside>

    <!-- Sidebar Overlay for Mobile -->
    <div class="sidebar-overlay" id="sidebar-overlay" onclick="toggleSidebar()"></div>

    <!-- Topbar -->
    <header class="topbar">
      <div class="topbar-left">
        <button class="mobile-menu-btn" onclick="toggleSidebar()">☰</button>
        <h2>${pageTitles[activePageId] || 'SafeVoice AI'}</h2>
      </div>
      <div class="topbar-right">
        <button class="topbar-btn" onclick="toggleTheme()" title="Chuyển đổi giao diện">
          <i class="bi bi-moon"></i>
        </button>
        <button class="topbar-btn" onclick="window.location.href='/canh-bao.html'" title="Cảnh báo">
          <i class="bi bi-bell"></i>
          <span class="badge" id="notification-badge" style="display:none">0</span>
        </button>
        <div class="user-info">
          <div class="user-avatar">${initials}</div>
          <div class="user-meta">
            <span class="user-name">${user.name || 'User'}</span>
            <span class="user-role">${roleLabels[user.role] || user.role}</span>
          </div>
        </div>
        <button class="btn btn-outline btn-sm" onclick="logout()">Đăng xuất</button>
      </div>
    </header>

    <!-- Toast container -->
    <div class="toast-container" id="toast-container"></div>
  `;

  // Set up mobile sidebar toggle
  window.toggleSidebar = () => {
    document.getElementById('sidebar').classList.toggle('sidebar-open');
    const overlay = document.getElementById('sidebar-overlay');
    if(overlay) overlay.classList.toggle('active');
  };

  // Close sidebar on link click (mobile)
  document.querySelectorAll('.sidebar .nav-item').forEach(item => {
    item.addEventListener('click', () => {
      document.getElementById('sidebar')?.classList.remove('sidebar-open');
      document.getElementById('sidebar-overlay')?.classList.remove('active');
    });
  });
}

function logout() {
  removeTokens();
  window.location.href = '/dang-nhap.html';
}

/* ========== DATE/TIME HELPERS ========== */
function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function formatTime(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatDateTime(dateStr) {
  return `${formatDate(dateStr)} ${formatTime(dateStr)}`;
}

function formatRelative(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Vừa xong';
  if (mins < 60) return `${mins} phút trước`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  return `${days} ngày trước`;
}

/* ========== STRING HELPERS (SECURITY) ========== */
function escapeHTML(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/* ========== LABEL HELPERS ========== */
const SOUND_TYPE_LABELS = {
  dap_pha: { label: 'Đập phá / Đánh đập', icon: '<i class="bi bi-hammer" style="color:var(--danger)"></i>', color: 'danger' },
  scream: { label: 'Gào thét / La hét', icon: '<i class="bi bi-volume-up" style="color:var(--danger)"></i>', color: 'danger' },
  help: { label: 'Kêu cứu / Van xin', icon: '<i class="bi bi-person-arms-up" style="color:var(--warning)"></i>', color: 'warning' },
  threat: { label: 'Đe dọa', icon: '<i class="bi bi-shield-exclamation" style="color:var(--caution)"></i>', color: 'caution' },
  argument: { label: 'Cãi vã', icon: '<i class="bi bi-chat-right-text" style="color:var(--info)"></i>', color: 'info' },
};

const STATUS_LABELS = {
  pending: { label: 'Chờ xử lý', class: 'badge-warning' },
  confirmed: { label: 'Đã xác nhận', class: 'badge-danger' },
  false_alarm: { label: 'Báo động giả', class: 'badge-muted' },
  resolved: { label: 'Đã xử lý', class: 'badge-success' },
};

/* ========== PAGINATION ========== */
window.renderPagination = function(totalItems, itemsPerPage, currentPage, containerId, onPageChange) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const totalPages = Math.ceil(totalItems / itemsPerPage);
  if (totalPages <= 1) {
    container.innerHTML = '';
    return;
  }

  let html = '<div class="pagination" style="display:flex; justify-content:center; gap:8px; margin-top:20px;">';
  
  // Prev button
  html += `<button class="btn btn-sm ${currentPage === 1 ? 'disabled' : 'btn-outline'}" ${currentPage === 1 ? 'disabled' : ''} data-page="${currentPage - 1}">Trước</button>`;

  // Page numbers
  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= currentPage - 1 && i <= currentPage + 1)) {
      html += `<button class="btn btn-sm ${i === currentPage ? 'btn-primary' : 'btn-outline'}" data-page="${i}">${i}</button>`;
    } else if (i === currentPage - 2 || i === currentPage + 2) {
      html += `<span style="padding: 4px 8px; color: var(--text-muted);">...</span>`;
    }
  }

  // Next button
  html += `<button class="btn btn-sm ${currentPage === totalPages ? 'disabled' : 'btn-outline'}" ${currentPage === totalPages ? 'disabled' : ''} data-page="${currentPage + 1}">Sau</button>`;
  
  html += '</div>';
  container.innerHTML = html;

  container.querySelectorAll('button[data-page]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const page = parseInt(e.target.dataset.page);
      if (!isNaN(page) && page !== currentPage) {
        onPageChange(page);
      }
    });
  });
};

/* ========== PAGE INIT ========== */
function initPage(pageId) {
  initTheme();
  const user = checkAuth();
  if (!user) return null;
  renderAppShell(pageId);
  setupWebSocket();
  updateNotificationBadge();
  return user;
}


function riskLabel(value) {
  const risk = typeof value === 'string' ? value : value?.risk_level || value?.analysis?.risk_level || value?.dialog_data?.analysis?.risk_level;
  return ({low:'THẤP',review:'CẦN XEM LẠI',high:'CAO'})[risk] || 'Chưa đánh giá ngữ cảnh';
}

function analysisTime(seconds) {
  const ticks = Math.round(Math.max(0, Number(seconds) || 0)*10);
  return String(Math.floor(ticks/600)).padStart(2,'0') + ':' + ((ticks%600)/10).toFixed(1).padStart(4,'0');
}

function renderAnalysisReport(result) {
  if (!result?.asr || !result?.analysis) {
    return '<p>Bản ghi cũ chưa có phân tích ngữ cảnh/timeline. Cần phân tích lại audio gốc.</p>';
  }
  const asr=result.asr, analysis=result.analysis;
  const uncertain=asr.quality==='review' || asr.status!=='success';
  const segments=asr.segments || [];
  const events=(result.timeline || []).filter(e => e.type !== 'speech');
  const names={scream:'Tiếng hét',crying:'Tiếng khóc',baby_cry:'Tiếng trẻ nhỏ khóc',impact:'Va đập',loud_speech:'Tiếng nói lớn',speech:'Lời nói',speech_activity:'Có tiếng nói (YAMNet)',music:'Nhạc',applause:'Vỗ tay/cổ vũ',door:'Đóng cửa',unusual:'Âm thanh chưa phân loại trong nhóm theo dõi'};
  const category={possible_physical_violence:'Có thể có xung đột thể chất',possible_verbal_abuse:'Có thể có bạo lực bằng lời nói',profanity:'Chửi tục',threat_or_distress:'Đe dọa hoặc kêu cứu',verbal_conflict:'Tranh cãi',ambiguous_audio:'Âm thanh cần xác minh',insufficient_evidence:'Chưa đủ bằng chứng'};
  const url=result.audio?.original_audio_url || result.original_audio_url;
  const safeUrl=typeof url==='string' && /^\/(uploads|tai-lieu)\//.test(url) && !url.includes('..') ? url : null;
  const signalNames={insult:'Lời xúc phạm',profanity:'Chửi tục',threat:'Đe dọa',help:'Kêu cứu',victim:'Yêu cầu dừng hành vi'};
  const evidence=analysis.evidence_items || [];
  const messages=segments.map((s,i)=>({ ...s,type:'speech',index:i+1 }));
  const acoustic=events.filter(e=>['scream','crying','impact','loud_speech'].includes(e.type));
  const conversation=[...messages,...acoustic].sort((a,b)=>a.start-b.start);
  const timeButton=(start,end)=>`<button type="button" class="ai-chat-time" data-ai-seek="${Math.max(0,Number(start)||0)}" ${safeUrl ? '' : 'disabled'} title="Nghe từ thời điểm này"><i class="bi bi-play-circle" aria-hidden="true"></i> ${analysisTime(start)}${end!=null ? '–'+analysisTime(end) : ''}</button>`;
  const chunkNames={profanity:'Chửi tục',verbal_abuse:'Xúc phạm',threat:'Đe dọa',help:'Kêu cứu',possible_physical_violence:'Nghi xung đột thể chất',scream:'Tiếng hét',crying:'Tiếng khóc',impact:'Va đập',loud_speech:'Nói lớn'};
  const chunkCards=(result.chunks||[]).map(c=>{
    const chunkUrl=typeof c.audio_url==='string' && /^\/uploads\/processed\/chunks\//.test(c.audio_url) && !c.audio_url.includes('..') ? c.audio_url : null;
    const rank={low:0,review:1,high:2};
    const boundaryHigher=(rank[c.boundary_context?.risk_level]??-1)>(rank[c.analysis?.risk_level]??-1);
    const risk=boundaryHigher ? c.boundary_context.risk_level : c.analysis?.risk_level;
    return `<article class="ai-chunk-card"><div class="ai-chat-meta"><strong>Đoạn cắt ${Number(c.index)}</strong>${timeButton(c.start,c.end)}<strong class="ai-chat-risk ai-chat-risk-${['low','review','high'].includes(risk)?risk:'review'}">${riskLabel(risk)}</strong></div>
      <div class="ai-chat-tags">${(c.labels||[]).map(l=>`<span>${escapeHTML(chunkNames[l]||l)}</span>`).join('') || `<span>${boundaryHigher ? 'Dấu hiệu từ ngữ cảnh liền kề' : 'Chưa có nhãn đáng ngờ'}</span>`}</div>
      <p>${escapeHTML(c.analysis?.summary||'')}</p>
      ${boundaryHigher ? `<p class="ai-chat-notice">Có bằng chứng liên quan ở sát ranh giới đoạn: ${escapeHTML(c.boundary_context.summary)}</p>` : ''}
      ${chunkUrl ? `<audio controls preload="none" src="${escapeHTML(chunkUrl)}" aria-label="Nghe đoạn cắt ${Number(c.index)}"></audio><a href="${escapeHTML(chunkUrl)}" download>Tải WAV đoạn này</a>` : ''}</article>`;
  });
  const rows=conversation.map(s=>{
    if(s.type!=='speech') return `<div class="ai-chat-event">${timeButton(s.start)}<span><i class="bi bi-soundwave" aria-hidden="true"></i> ${escapeHTML(names[s.type]||s.type)}${s.strength==='tentative' ? ' · tín hiệu yếu' : ''}</span></div>`;
    const flags=s.accepted===false ? [] : [...new Set(evidence.filter(e=>e.kind==='speech' && s.text.includes(e.text || '\u0000') && e.start<=s.end && e.end>=s.start).map(e=>signalNames[e.signal]).filter(Boolean))];
    return `<article class="ai-chat-message${s.accepted===false ? ' ai-chat-unverified' : ''}">
      <div class="ai-chat-index" aria-hidden="true">${String(s.index).padStart(2,'0')}</div>
      <div class="ai-chat-bubble"><div class="ai-chat-meta"><strong>Đoạn ${s.index}</strong>${timeButton(s.start,s.end)}</div>
      <p class="ai-chat-text">${escapeHTML(s.text)}</p>
      ${flags.length || s.accepted===false ? `<div class="ai-chat-tags">${flags.map(f=>`<span>${escapeHTML(f)}</span>`).join('')}${s.accepted===false ? '<span>Chưa xác minh lời nói</span>' : ''}</div>` : ''}</div>
    </article>`;
  }).join('');
  return `<section class="ai-analysis-report">
    <div class="ai-chat-verdict"><div class="ai-chat-verdict-top"><span><i class="bi bi-stars" aria-hidden="true"></i> AI nhận xét</span><strong class="ai-chat-risk ai-chat-risk-${['low','review','high'].includes(analysis.risk_level) ? analysis.risk_level : 'review'}">${riskLabel(analysis)}</strong></div>
    <h4>${escapeHTML(category[analysis.category]||analysis.category)}</h4><p>${escapeHTML(analysis.summary)}</p>
    ${typeof analysis.has_profanity==='boolean' ? `<div class="ai-chat-findings"><span>Chửi tục: <strong>${analysis.has_profanity ? 'Có' : uncertain ? 'Chưa xác định' : 'Chưa nhận diện'}</strong></span><span>Xúc phạm: <strong>${analysis.has_insults ? 'Có' : uncertain ? 'Chưa xác định' : 'Chưa nhận diện'}</strong></span></div>` : ''}</div>
    ${analysis.analysis_version!=='rules-3.0' ? '<p class="ai-chat-notice">Bản phân tích cũ, chưa được cập nhật bằng bản AI mới.</p>' : ''}
    ${safeUrl ? `<div class="ai-chat-player"><span><i class="bi bi-headphones" aria-hidden="true"></i> Nghe bản ghi gốc</span><audio controls preload="metadata" src="${escapeHTML(safeUrl)}"></audio></div>` : ''}
    ${chunkCards.length ? `<div class="ai-chat-heading"><h4>Đánh giá từng đoạn 10 giây</h4><span>${chunkCards.length} đoạn cắt</span></div><div class="ai-chunk-list">${chunkCards.slice(0,6).join('')}</div>${chunkCards.length>6 ? `<details class="ai-chat-technical"><summary>Xem ${chunkCards.length-6} đoạn còn lại</summary>${chunkCards.slice(6).join('')}</details>` : ''}` : ''}
    <div class="ai-chat-heading"><h4>Nội dung hội thoại</h4><span>${segments.length} đoạn lời nói</span></div>
    <p class="ai-chat-hint">${safeUrl ? 'Bấm thời gian để nghe lại. ' : ''}Các đoạn được sắp theo thời gian; chưa phân biệt người nói.</p>
    ${uncertain ? '<p class="ai-chat-notice">Lời nói chưa được nhận dạng đầy đủ hoặc cần xác minh.</p>' : ''}
    <div class="ai-chat-thread">${rows || '<p class="ai-chat-empty">Chưa nhận dạng được lời nói hoặc sự kiện âm thanh.</p>'}</div>
    <details class="ai-chat-technical"><summary>Xem bằng chứng và thông tin kỹ thuật</summary>
    <ul>${(analysis.evidence||[]).map(e=>`<li>${escapeHTML(e)}</li>`).join('')}</ul>
    <p style="white-space:pre-wrap">Transcript gốc: ${escapeHTML(asr.raw_transcript || '')}</p>
    ${events.length ? events.map(e=>`<p><strong>${analysisTime(e.start)}–${analysisTime(e.end)}</strong> ${escapeHTML(names[e.type]||e.type)}${e.class_name ? ': '+escapeHTML(e.class_name):''} <small>(điểm YAMNet: ${Number(e.score).toFixed(3)}${e.strength==='tentative' ? '; tín hiệu yếu, cần xác minh':''})</small></p>`).join('') : '<p>Không có sự kiện vượt ngưỡng theo dõi.</p>'}
    <ul>${(analysis.limitations||[]).map(e=>`<li>${escapeHTML(e)}</li>`).join('')}</ul></details>
  </section>`;
}

document.addEventListener('click',event=>{
  const button=event.target.closest?.('[data-ai-seek]');
  if(!button || button.disabled) return;
  const audio=button.closest('.ai-analysis-report')?.querySelector('audio');
  if(!audio) return;
  const seek=()=>{audio.currentTime=Math.max(0,Number(button.dataset.aiSeek)||0);audio.play().catch(()=>{});};
  if(audio.readyState>=1) seek();
  else {audio.addEventListener('loadedmetadata',seek,{once:true});audio.load();}
});

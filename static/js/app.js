// Shared dashboard chrome: fetch helper, toasts, tabs, theme, ADB status/install.

async function apiFetch(url, opts = {}) {
  const method = (opts.method || 'GET').toUpperCase();
  const headers = Object.assign({}, opts.headers);
  if (opts.body && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    if (typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
  }
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    headers['X-CSRF-Token'] = window.CSRF_TOKEN || '';
  }
  const res = await fetch(url, Object.assign({}, opts, { headers, credentials: 'same-origin' }));
  if (res.status === 401) {
    window.location.href = '/';
    throw new Error('unauthenticated');
  }
  return res;
}

function toast(message, type = 'info', timeoutMs = 4000) {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), timeoutMs);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function formatBytes(bytes) {
  if (bytes == null || isNaN(bytes)) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let n = Number(bytes);
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

// --- Tabs -------------------------------------------------------------
const TAB_CHANGE_LISTENERS = [];
function onTabChange(fn) { TAB_CHANGE_LISTENERS.push(fn); }

function initTabs() {
  const items = document.querySelectorAll('.nav-tabs li');
  items.forEach((li) => {
    li.addEventListener('click', () => {
      const tab = li.dataset.tab;
      items.forEach((x) => x.classList.toggle('active', x === li));
      document.querySelectorAll('.tab-pane').forEach((pane) => {
        pane.classList.toggle('active', pane.id === `tab-${tab}`);
      });
      localStorage.setItem('adbpanel.tab', tab);
      TAB_CHANGE_LISTENERS.forEach((fn) => fn(tab));
    });
  });
  const saved = localStorage.getItem('adbpanel.tab');
  if (saved) {
    const li = document.querySelector(`.nav-tabs li[data-tab="${saved}"]`);
    if (li) li.click();
  } else if (items.length) {
    TAB_CHANGE_LISTENERS.forEach((fn) => fn(items[0].dataset.tab));
  }
}

function currentTab() {
  const active = document.querySelector('.nav-tabs li.active');
  return active ? active.dataset.tab : null;
}

// --- Theme --------------------------------------------------------------
function initTheme() {
  const toggle = document.getElementById('theme-toggle');
  if (!toggle) return;
  toggle.addEventListener('click', async () => {
    const html = document.documentElement;
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    try { await apiFetch('/api/settings', { method: 'POST', body: { theme: next } }); } catch (e) { /* ignore */ }
  });
}

// --- Logout ---------------------------------------------------------------
function initLogout() {
  const btn = document.getElementById('logout-btn');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    try { await apiFetch('/api/auth/logout', { method: 'POST' }); } catch (e) { /* ignore */ }
    window.location.href = '/';
  });
}

// --- ADB status/install ---------------------------------------------------
async function refreshAdbStatus() {
  const card = document.getElementById('adb-status-card');
  if (!card) return null;
  try {
    const res = await fetch('/api/adb/status');
    const status = await res.json();
    renderAdbStatus(status);
    return status;
  } catch (err) {
    card.innerHTML = `<span class="badge red">Error</span> Could not reach server`;
    return null;
  }
}

function renderAdbStatus(status) {
  const card = document.getElementById('adb-status-card');
  if (status.installed) {
    card.innerHTML = `<span class="badge green">ADB installed</span> v${escapeHtml(status.version)} (${escapeHtml(status.source)})`;
  } else {
    card.innerHTML = `<span class="badge red">ADB not installed</span> <button id="install-adb-btn">Install ADB</button>`;
    document.getElementById('install-adb-btn').addEventListener('click', installAdb);
  }
}

async function installAdb() {
  const card = document.getElementById('adb-status-card');
  card.innerHTML = `<span class="badge yellow">Installing…</span> downloading platform-tools`;
  try {
    const res = await apiFetch('/api/adb/install', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      toast('ADB installed successfully', 'success');
      renderAdbStatus(data.status);
      if (window.refreshDevices) window.refreshDevices();
    } else {
      toast(`Install failed: ${data.error}`, 'error');
      refreshAdbStatus();
    }
  } catch (err) {
    toast(`Install failed: ${err}`, 'error');
    refreshAdbStatus();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initTheme();
  initLogout();
  refreshAdbStatus();
});

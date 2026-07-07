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

function statTileHtml(title, value, sub) {
  return `<div class="card"><div class="muted">${escapeHtml(title)}</div><h2>${value}</h2>${sub ? `<div class="muted">${sub}</div>` : ''}</div>`;
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
  const items = document.querySelectorAll('.nav-tabs li[data-tab]');
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

// --- Nested sub-nav (progressive disclosure inside a tab pane) -------------
// views: [{ key, label, render(bodyEl) }]. Persists the last-active view per
// storageKey the same way initTabs persists the active top-level tab, and
// re-renders only the swapped-in view's body -- any "must stay visible"
// surface (e.g. a live screenshot canvas or streaming console) belongs in a
// sibling element the caller renders itself, outside rootEl.
function createSubNav(rootEl, storageKey, views, opts = {}) {
  if (!rootEl || !views || !views.length) return null;
  const defaultKey = opts.defaultKey || views[0].key;
  const saved = localStorage.getItem(storageKey);
  const initialKey = views.some((v) => v.key === saved) ? saved : defaultKey;
  rootEl.innerHTML = `<div class="subnav-pills" role="tablist"></div><div class="subnav-body"></div>`;
  const pillsEl = rootEl.querySelector('.subnav-pills');
  const bodyEl = rootEl.querySelector('.subnav-body');
  pillsEl.innerHTML = views.map((v) =>
    `<button type="button" class="subnav-pill" data-subnav-key="${escapeHtml(v.key)}">${escapeHtml(v.label)}</button>`).join('');
  function activate(key) {
    const view = views.find((v) => v.key === key) || views[0];
    pillsEl.querySelectorAll('.subnav-pill').forEach((btn) =>
      btn.classList.toggle('active', btn.dataset.subnavKey === view.key));
    localStorage.setItem(storageKey, view.key);
    bodyEl.innerHTML = '';
    view.render(bodyEl);
  }
  pillsEl.querySelectorAll('.subnav-pill').forEach((btn) =>
    btn.addEventListener('click', () => activate(btn.dataset.subnavKey)));
  activate(initialKey);
  return { activate, pillsEl, bodyEl };
}

// Nav items marked data-requires-device only make sense against a connected,
// authorized device -- hide them otherwise instead of leaving a click target
// whose pane will just say "select a device". Group labels above a
// now-empty group are hidden along with it so the sidebar never shows an
// orphaned heading with nothing underneath.
function updateNavDeviceGating(_serial, device) {
  const hasDevice = !!(device && device.state === 'device');
  document.querySelectorAll('.nav-tabs li[data-requires-device]').forEach((li) => {
    li.style.display = hasDevice ? 'list-item' : 'none';
  });
  document.querySelectorAll('.nav-group-label').forEach((label) => {
    const group = label.dataset.group;
    const anyVisible = Array.from(document.querySelectorAll(`.nav-tabs li[data-tab][data-group="${group}"]`))
      .some((li) => !li.hasAttribute('data-requires-device') || hasDevice);
    label.style.display = anyVisible ? '' : 'none';
  });
  if (!hasDevice) {
    const active = document.querySelector('.nav-tabs li.active');
    if (active && active.hasAttribute('data-requires-device')) {
      const dashboardTab = document.querySelector('.nav-tabs li[data-tab="dashboard"]');
      if (dashboardTab) dashboardTab.click();
    }
  }
}

// --- Theme --------------------------------------------------------------
// Cycle dark -> light -> system. window.getThemeMode/setThemeMode come from the
// inline bootstrap in base.html, which owns localStorage + prefers-color-scheme
// resolution; here we only cycle the mode and mirror it to server settings.
const THEME_MODES = ['dark', 'light', 'system'];
const THEME_LABELS = { dark: 'Dark', light: 'Light', system: 'System' };
function themeButtonLabel(mode) { return `Theme: ${THEME_LABELS[mode] || 'System'}`; }

function initTheme() {
  const toggle = document.getElementById('theme-toggle');
  if (!toggle || !window.getThemeMode) return;
  const sync = () => { toggle.textContent = themeButtonLabel(window.getThemeMode()); };
  sync();
  toggle.addEventListener('click', async () => {
    const cur = window.getThemeMode();
    const next = THEME_MODES[(THEME_MODES.indexOf(cur) + 1) % THEME_MODES.length];
    window.setThemeMode(next);
    sync();
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

// --- Tool status/install ---------------------------------------------------
// Each tool has 2 possible DOM targets: the topbar (data-tool-status-scope="topbar",
// hidden once the tool reaches a "terminal green" state) and the Settings > Tooling
// section (data-tool-status-scope="settings", always shown). Install buttons are
// class-based, not id-based, since the same markup renders into both targets at once.
function toolStatusEls(tool) { return document.querySelectorAll(`[data-tool-status="${tool}"]`); }
function setToolStatusHTML(tool, html, { hideWhenGreen = false } = {}) {
  toolStatusEls(tool).forEach((el) => {
    el.innerHTML = html;
    if (el.dataset.toolStatusScope === 'topbar') el.style.display = hideWhenGreen ? 'none' : '';
  });
}

async function refreshAdbStatus() {
  if (!toolStatusEls('adb').length) return null;
  try {
    const res = await fetch('/api/adb/status');
    const status = await res.json();
    renderAdbStatus(status);
    return status;
  } catch (err) {
    setToolStatusHTML('adb', `<span class="badge red">Error</span> Could not reach server`);
    return null;
  }
}

async function refreshApktoolStatus() {
  if (!toolStatusEls('apktool').length) return null;
  try {
    const res = await apiFetch('/api/apktool/status');
    const status = await res.json();
    renderApktoolStatus(status);
    return status;
  } catch (err) {
    setToolStatusHTML('apktool', `<span class="badge red">APKTool error</span>`);
    return null;
  }
}

function renderApktoolStatus(status) {
  const javaOk = status.java && status.java.installed;
  const apktoolOk = status.apktool && status.apktool.installed;
  let html; let terminalGreen = false;
  if (!javaOk) {
    html = `<span class="badge red">Java missing</span> <a href="https://adoptium.net/" target="_blank" rel="noopener">Install Java</a>`;
  } else if (apktoolOk) {
    html = `<span class="badge green">APKTool installed</span> v${escapeHtml(status.apktool.version || status.apktool.pinned_version || '')}`;
    terminalGreen = true;
  } else {
    html = `<span class="badge red">APKTool missing</span> <button type="button" class="install-apktool-btn">Install APKTool</button>`;
  }
  setToolStatusHTML('apktool', html, { hideWhenGreen: terminalGreen });
  document.querySelectorAll('.install-apktool-btn').forEach((btn) => btn.addEventListener('click', installApktool));
}

async function installApktool() {
  setToolStatusHTML('apktool', `<span class="badge yellow">Installing...</span> downloading apktool.jar`);
  try {
    const res = await apiFetch('/api/apktool/install', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      toast('APKTool installed successfully', 'success');
      renderApktoolStatus(data.status);
    } else {
      toast(`APKTool install failed: ${data.error}`, 'error');
      refreshApktoolStatus();
    }
  } catch (err) {
    toast(`APKTool install failed: ${err}`, 'error');
    refreshApktoolStatus();
  }
}

async function refreshJadxToolStatus() {
  if (!toolStatusEls('jadx').length) return null;
  try {
    const res = await apiFetch('/api/jadx/status');
    const status = await res.json();
    renderJadxToolStatus(status);
    return status;
  } catch (err) {
    setToolStatusHTML('jadx', `<span class="badge red">JADX error</span>`);
    return null;
  }
}

function renderJadxToolStatus(status) {
  const javaOk = status.java && status.java.installed;
  const jadxOk = status.jadx && status.jadx.installed;
  let html; let terminalGreen = false;
  if (!javaOk) {
    html = `<span class="badge red">Java missing</span> <a href="https://adoptium.net/" target="_blank" rel="noopener">Install Java</a>`;
  } else if (jadxOk) {
    html = `<span class="badge green">JADX installed</span> v${escapeHtml(status.jadx.version || status.jadx.pinned_version || '')}`;
    terminalGreen = true;
  } else {
    html = `<span class="badge red">JADX missing</span> <button type="button" class="install-jadx-btn">Install JADX</button>`;
  }
  setToolStatusHTML('jadx', html, { hideWhenGreen: terminalGreen });
  document.querySelectorAll('.install-jadx-btn').forEach((btn) => btn.addEventListener('click', () => {
    if (typeof installJadx === 'function') installJadx();
  }));
}

async function refreshFridaToolStatus() {
  if (!toolStatusEls('frida').length) return null;
  try {
    const res = await apiFetch('/api/frida/status');
    const status = await res.json();
    renderFridaToolStatus(status);
    return status;
  } catch (err) {
    setToolStatusHTML('frida', `<span class="badge red">Frida error</span>`);
    return null;
  }
}

function renderFridaToolStatus(status) {
  const serial = typeof getSelectedSerial === 'function' ? getSelectedSerial() : '';
  const ds = serial && status.devices ? status.devices.find((d) => d.serial === serial) : null;
  let html; let terminalGreen = false;
  if (!status.python_installed) {
    html = `<span class="badge red">Frida missing</span> Install requirements.txt`;
  } else if (!ds) {
    html = `<span class="badge green">Frida package</span> v${escapeHtml(status.python_version || '')}`;
    terminalGreen = true;
  } else if (ds.error) {
    html = `<span class="badge red">Frida device error</span> ${escapeHtml(ds.error)}`;
  } else if (!ds.root_available) {
    html = `<span class="badge yellow">Frida needs root</span> v${escapeHtml(status.python_version || '')}`;
  } else if (ds.server_pushed) {
    html = `<span class="badge green">Frida server ready</span> ${ds.server_running ? 'running' : 'pushed'}`;
    terminalGreen = true;
  } else {
    html = `<span class="badge yellow">Frida server missing</span> <button type="button" class="install-frida-server-btn">Install Frida</button>`;
  }
  setToolStatusHTML('frida', html, { hideWhenGreen: terminalGreen });
  document.querySelectorAll('.install-frida-server-btn').forEach((btn) => btn.addEventListener('click', installFridaServer));
}

async function installFridaServer() {
  const serial = typeof getSelectedSerial === 'function' ? getSelectedSerial() : '';
  if (!serial) { toast('Select a rooted device first', 'error'); return; }
  setToolStatusHTML('frida', `<span class="badge yellow">Installing...</span> pushing frida-server`);
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/server/push`, { method: 'POST' });
    const data = await res.json();
    toast(data.ok ? 'Frida server installed on device' : `Frida install failed: ${data.error}`, data.ok ? 'success' : 'error');
  } catch (err) {
    toast(`Frida install failed: ${err}`, 'error');
  }
  refreshFridaToolStatus();
}

function renderAdbStatus(status) {
  let html; let terminalGreen = false;
  if (status.installed) {
    html = `<span class="badge green">ADB installed</span> v${escapeHtml(status.version)} (${escapeHtml(status.source)})`;
    terminalGreen = true;
  } else {
    html = `<span class="badge red">ADB not installed</span> <button type="button" class="install-adb-btn">Install ADB</button>`;
  }
  setToolStatusHTML('adb', html, { hideWhenGreen: terminalGreen });
  document.querySelectorAll('.install-adb-btn').forEach((btn) => btn.addEventListener('click', installAdb));
}

async function installAdb() {
  setToolStatusHTML('adb', `<span class="badge yellow">Installing…</span> downloading platform-tools`);
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

// --- Keyboard shortcuts -----------------------------------------------------
function initKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    if (e.key >= '1' && e.key <= '9') {
      const items = document.querySelectorAll('.nav-tabs li[data-tab]');
      const idx = parseInt(e.key, 10) - 1;
      if (items[idx]) items[idx].click();
      return;
    }
    if (e.key === 'r' || e.key === 'R') {
      if (window.refreshDevices) window.refreshDevices();
      toast('Refreshing devices…', 'info', 1500);
      return;
    }
    if (e.key === 'Escape') {
      if (typeof closeModal === 'function') closeModal();
      return;
    }
    if (e.key === '?') {
      toast('Shortcuts: 1-9 switch tabs · r refresh devices · Esc close preview', 'info', 6000);
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initTheme();
  initLogout();
  initKeyboardShortcuts();
  refreshAdbStatus();
  refreshApktoolStatus();
  refreshJadxToolStatus();
  refreshFridaToolStatus();
  if (typeof onDeviceChange === 'function') {
    onDeviceChange(updateNavDeviceGating);
    onDeviceChange(() => refreshFridaToolStatus());
  }
});

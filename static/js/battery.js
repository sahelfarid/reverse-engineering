// Battery/HW tab, Permissions tab, Clipboard tab (all backed by routes/battery.py).

function renderBatteryTab() {
  const pane = document.getElementById('tab-battery');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device.</div>`;
    return;
  }
  pane.innerHTML = `<div id="hardware-body">Loading…</div><button id="hardware-refresh-btn">Refresh</button>`;
  document.getElementById('hardware-refresh-btn').addEventListener('click', () => loadHardware(serial));
  loadHardware(serial);
}

async function loadHardware(serial) {
  const body = document.getElementById('hardware-body');
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/hardware`);
  const data = await res.json();
  if (!data.ok) { body.innerHTML = `<div class="alert error">${escapeHtml(data.error)}</div>`; return; }
  const h = data.hardware;
  const b = h.battery;
  const disk = h.disk.map((d) => `<tr><td>${escapeHtml(d.mounted_on)}</td><td>${escapeHtml(d.used)}/${escapeHtml(d.size)}</td><td>${escapeHtml(d.use_pct)}</td></tr>`).join('');
  body.innerHTML = `
    <div class="card-grid">
      <div class="card"><h4>Battery</h4>
        <div>${b.level != null ? b.level + '%' : '—'} ${b.charging ? '(charging)' : ''}</div>
        <div class="muted">Health: ${escapeHtml(b.health || '—')} · Status: ${escapeHtml(b.status || '—')}</div>
        <div class="muted">Voltage: ${escapeHtml(b.voltage_mv || '—')} mV · Temp: ${b.temperature_c != null ? b.temperature_c + '°C' : '—'}</div>
        <div class="muted">Technology: ${escapeHtml(b.technology || '—')} · Cycle count: ${escapeHtml(b.cycle_count || '—')}</div>
      </div>
      <div class="card"><h4>CPU</h4>
        <div>${h.cpu.cores != null ? h.cpu.cores + ' cores' : '—'}</div>
        <div class="muted">${escapeHtml(h.cpu.hardware || h.cpu.model || '—')}</div>
      </div>
      <div class="card"><h4>GPU</h4>
        <div class="muted">EGL: ${escapeHtml(h.gpu.egl || '—')}</div>
        <div class="muted">${escapeHtml(h.gpu.renderer || '—')}</div>
      </div>
      <div class="card"><h4>Sensors (${h.sensors.length})</h4>
        <div class="muted">${h.sensors.slice(0, 20).map(escapeHtml).join('<br>') || '—'}</div>
      </div>
      <div class="card" style="grid-column: span 2;"><h4>Disk usage</h4>
        <table><thead><tr><th>Mount</th><th>Used/Size</th><th>%</th></tr></thead><tbody>${disk}</tbody></table>
      </div>
    </div>
  `;
}

// --- Permissions tab -------------------------------------------------------

function renderPermissionsTab() {
  const pane = document.getElementById('tab-permissions');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="card">
      <div style="display:flex; gap:8px; margin-bottom:10px;">
        <select id="permissions-package-select" style="flex:1;"><option>Loading packages…</option></select>
        <button id="permissions-load-btn">Load</button>
      </div>
      <div id="permissions-body"></div>
    </div>
  `;
  loadPermissionsPackageList(serial);
  document.getElementById('permissions-load-btn').addEventListener('click', () => loadPermissions(serial));
}

async function loadPermissionsPackageList(serial) {
  const select = document.getElementById('permissions-package-select');
  try {
    let list = PACKAGES_CACHE && PACKAGES_CACHE.length ? PACKAGES_CACHE : null;
    if (!list) {
      const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages`);
      const data = await res.json();
      list = data.ok ? data.packages : [];
    }
    select.innerHTML = list.map((p) => `<option value="${escapeHtml(p.package)}">${escapeHtml(p.package)}</option>`).join('');
  } catch (e) { select.innerHTML = '<option value="">Failed to load</option>'; }
}

async function loadPermissions(serial) {
  const pkg = document.getElementById('permissions-package-select').value;
  const body = document.getElementById('permissions-body');
  if (!pkg) return;
  body.innerHTML = 'Loading…';
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/permissions`);
  const data = await res.json();
  if (!data.ok) { body.innerHTML = `<div class="alert error">${escapeHtml(data.error)}</div>`; return; }
  const p = data.permissions;
  const rows = (name) => `<span class="badge ${p.granted.includes(name) ? 'green' : 'red'}">${p.granted.includes(name) ? 'granted' : 'denied'}</span>
    <button data-perm="${escapeHtml(name)}" data-act="grant">Grant</button>
    <button data-perm="${escapeHtml(name)}" data-act="revoke">Revoke</button>`;
  body.innerHTML = `
    <div class="card"><h4>Dangerous permissions</h4>
      <table><tbody>${p.dangerous_requested.map((n) => `<tr><td>${escapeHtml(n)}</td><td>${rows(n)}</td></tr>`).join('') || '<tr><td class="muted">None requested</td></tr>'}</tbody></table>
    </div>
    <div class="card"><h4>Normal permissions</h4>
      <div class="muted">${p.normal_requested.map(escapeHtml).join('<br>') || 'None'}</div>
    </div>
  `;
  body.querySelectorAll('button[data-act]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const endpoint = btn.dataset.act;
      const res2 = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/permissions/${endpoint}`, {
        method: 'POST', body: { permission: btn.dataset.perm },
      });
      const data2 = await res2.json();
      toast(data2.ok ? `${endpoint} ok` : `${endpoint} failed: ${data2.error}`, data2.ok ? 'success' : 'error');
      loadPermissions(serial);
    });
  });
}

// --- Clipboard tab -----------------------------------------------------------

function renderClipboardTab() {
  const pane = document.getElementById('tab-clipboard');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="alert warn">Android restricts programmatic clipboard access (especially since Android 10, reads are limited to the focused app). Read may fail depending on OS version/OEM; write requires a helper app such as "Clipper" to be installed on the device.</div>
    <div class="card-grid">
      <div class="card">
        <h4>Read clipboard</h4>
        <button id="clipboard-read-btn">Read</button>
        <pre id="clipboard-read-output" class="shell-output" style="height:100px; margin-top:8px;"></pre>
      </div>
      <div class="card">
        <h4>Write clipboard</h4>
        <textarea id="clipboard-write-input" rows="3" style="width:100%;"></textarea>
        <button id="clipboard-write-btn">Write</button>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h4>History (this session)</h4>
        <div id="clipboard-history"></div>
      </div>
    </div>
  `;
  document.getElementById('clipboard-read-btn').addEventListener('click', () => readClipboard(serial));
  document.getElementById('clipboard-write-btn').addEventListener('click', () => writeClipboard(serial));
  loadClipboardHistory(serial);
}

async function readClipboard(serial) {
  const out = document.getElementById('clipboard-read-output');
  out.textContent = 'Reading…';
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/clipboard`);
  const data = await res.json();
  out.textContent = data.ok ? data.text : `${data.error}${data.detail ? ': ' + data.detail : ''}`;
  loadClipboardHistory(serial);
}

async function writeClipboard(serial) {
  const text = document.getElementById('clipboard-write-input').value;
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/clipboard`, { method: 'POST', body: { text } });
  const data = await res.json();
  toast(data.ok ? (data.note || 'Sent') : `${data.error}: ${data.detail || ''}`, data.ok ? 'success' : 'error');
}

async function loadClipboardHistory(serial) {
  const container = document.getElementById('clipboard-history');
  if (!container) return;
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/clipboard/history`);
  const data = await res.json();
  container.innerHTML = (data.history || []).slice().reverse().map((t) => `<div>${escapeHtml(t)}</div>`).join('') || '<div class="muted">No reads yet this session</div>';
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => {
    if (tab === 'battery') renderBatteryTab();
    if (tab === 'permissions') renderPermissionsTab();
    if (tab === 'clipboard') renderClipboardTab();
  });
  onDeviceChange(() => {
    if (currentTab() === 'battery') renderBatteryTab();
    if (currentTab() === 'permissions') renderPermissionsTab();
    if (currentTab() === 'clipboard') renderClipboardTab();
  });
});

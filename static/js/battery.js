// Battery/HW tab, Permissions tab, Clipboard tab (all backed by routes/battery.py).

Object.assign(TIP_REGISTRY, {
  'clipboard.restrictions': {
    title: 'Clipboard restrictions',
    body: '<p>Android restricts programmatic clipboard access -- especially since Android 10, reads are limited to the focused app.</p><p>Read may fail depending on OS version/OEM; write requires a helper app such as "Clipper" to be installed on the device.</p>',
  },
});

function renderBatteryTab() {
  const pane = document.getElementById('tab-battery');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="panel-page">
      <div class="panel-header">
        <h2>Battery / HW</h2>
        <p class="muted">Hardware telemetry and root/tamper detection.</p>
      </div>
      <div id="battery-subnav"></div>
    </div>
  `;
  createSubNav(document.getElementById('battery-subnav'), 'adbpanel.subnav.battery', [
    { key: 'hardware', label: 'Hardware', render: (body) => renderHardwareView(body, serial) },
    { key: 'integrity', label: 'Integrity', render: (body) => renderIntegrityView(body, serial) },
  ]);
}

function renderHardwareView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <div class="section-head">
        <div><h3>Hardware</h3></div>
        <button id="hardware-refresh-btn" class="ghost-btn small">Refresh</button>
      </div>
      <div id="hardware-body">Loading…</div>
    </section>`;
  document.getElementById('hardware-refresh-btn').addEventListener('click', () => loadHardware(serial));
  loadHardware(serial);
}

function renderIntegrityView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <div class="section-head">
        <div><h3>Device integrity / root detection</h3></div>
        <button id="integrity-refresh-btn" class="ghost-btn small">Re-check</button>
      </div>
      <div id="integrity-body">Loading…</div>
    </section>`;
  document.getElementById('integrity-refresh-btn').addEventListener('click', () => loadIntegrity(serial));
  loadIntegrity(serial);
}

const INTEGRITY_VERDICT_CLASS = {
  'rooted': 'red', 'likely rooted': 'red', 'possibly modified': 'yellow', 'not detected': 'green',
};

async function loadIntegrity(serial) {
  const body = document.getElementById('integrity-body');
  if (!body) return;
  body.innerHTML = 'Checking…';
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/integrity`);
    const data = await res.json();
    if (!data.ok) { body.innerHTML = `<div class="alert error">${escapeHtml(data.error)}</div>`; return; }
    const r = data.report;
    const badgeClass = INTEGRITY_VERDICT_CLASS[r.verdict] || 'yellow';
    const b = r.indicators.build_integrity;
    const checkRow = (label, present, evidence) =>
      `<tr><td>${escapeHtml(label)}</td><td>${present ? '<span class="badge red">✓ detected</span>' : '<span class="badge green">✗ clear</span>'}</td><td class="muted">${escapeHtml(evidence || '—')}</td></tr>`;
    body.innerHTML = `
      <div style="font-size:1.1em; margin-bottom:8px;">Verdict: <span class="badge ${badgeClass}">${escapeHtml(r.verdict)}</span></div>
      <div class="table-wrap auto-height">
        <table>
          <thead><tr><th>Indicator</th><th>State</th><th>Evidence</th></tr></thead>
          <tbody>
            ${checkRow('Working root shell', r.indicators.working_root_shell, r.indicators.working_root_shell ? 'su -c id returned uid=0' : '')}
            ${checkRow('su binaries on disk', r.indicators.su_paths.length > 0, r.indicators.su_paths.join(', '))}
            ${checkRow('Magisk app installed', r.indicators.magisk.app_installed, r.indicators.magisk.app_installed ? 'com.topjohnwu.magisk' : '')}
            ${checkRow('Magisk artifacts', r.indicators.magisk.artifacts.length > 0, r.indicators.magisk.artifacts.join(', '))}
            ${checkRow('busybox present', !!r.indicators.busybox, r.indicators.busybox)}
            ${checkRow('Build signed with test-keys', !!(b.build_tags && b.build_tags.includes('test-keys')), b.build_tags)}
            ${checkRow('Debuggable build', b.debuggable === '1', 'ro.debuggable=' + escapeHtml(b.debuggable || '?'))}
            ${checkRow('Insecure build', b.secure === '0', 'ro.secure=' + escapeHtml(b.secure || '?'))}
            ${checkRow('SELinux not enforcing', !!(b.selinux && b.selinux.toLowerCase() !== 'enforcing'), 'getenforce=' + escapeHtml(b.selinux || '?'))}
            ${checkRow('Bootloader unlocked', b.bootloader_locked === '0', 'ro.boot.flash.locked=' + escapeHtml(b.bootloader_locked || '?'))}
          </tbody>
        </table>
      </div>
      <div class="alert info" style="margin-top:10px;">${escapeHtml(r.disclaimer)}</div>
    `;
  } catch (err) {
    body.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
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
    <div class="panel-page">
      <div class="panel-header">
        <h2>Permissions</h2>
        <p class="muted">Inspect and grant/revoke a package's runtime permissions.</p>
      </div>
      <section class="panel-section">
        <div class="toolbar-row">
          <select id="permissions-package-select" style="flex:1;"><option>Loading packages…</option></select>
          <button id="permissions-load-btn">Load</button>
        </div>
        <div id="permissions-body"></div>
      </section>
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
    <div class="panel-page">
      <div class="panel-header">
        <h2>Clipboard</h2>
        <p class="muted">
          Read/write the device clipboard.
          <button type="button" class="tip-btn" data-tip-key="clipboard.restrictions" aria-label="Help">?</button>
        </p>
      </div>
      <div id="clipboard-subnav"></div>
    </div>
  `;
  createSubNav(document.getElementById('clipboard-subnav'), 'adbpanel.subnav.clipboard', [
    { key: 'read', label: 'Read', render: (body) => renderClipboardReadView(body, serial) },
    { key: 'write', label: 'Write', render: (body) => renderClipboardWriteView(body, serial) },
    { key: 'history', label: 'History', render: (body) => renderClipboardHistoryView(body, serial) },
  ]);
}

function renderClipboardReadView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <button id="clipboard-read-btn">Read</button>
      <pre id="clipboard-read-output" class="shell-output" style="height:160px; margin-top:8px;"></pre>
    </section>`;
  document.getElementById('clipboard-read-btn').addEventListener('click', () => readClipboard(serial));
}

function renderClipboardWriteView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <textarea id="clipboard-write-input" rows="4" style="width:100%;"></textarea>
      <div class="section-actions justify-start">
        <button id="clipboard-write-btn" class="primary-btn">Write</button>
      </div>
    </section>`;
  document.getElementById('clipboard-write-btn').addEventListener('click', () => writeClipboard(serial));
}

function renderClipboardHistoryView(body, serial) {
  body.innerHTML = `<section class="panel-section"><div id="clipboard-history"></div></section>`;
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

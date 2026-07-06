// Processes tab: running process list, kill, foreground app.

function renderProcessesTab() {
  const pane = document.getElementById('tab-processes');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="card">
      <div style="display:flex; gap:8px; margin-bottom:8px;">
        <input type="text" id="processes-filter" placeholder="Filter by name or pid…" style="flex:1;">
        <button id="processes-refresh-btn">Refresh</button>
      </div>
      <div id="processes-foreground" class="muted" style="margin-bottom:8px;"></div>
      <div id="processes-alert"></div>
      <table>
        <thead><tr><th>PID</th><th>PPID</th><th>User</th><th>RSS (KB)</th><th>Name</th><th>Actions</th></tr></thead>
        <tbody id="processes-table-body"><tr><td colspan="6">Loading…</td></tr></tbody>
      </table>
    </div>
  `;
  document.getElementById('processes-refresh-btn').addEventListener('click', () => { loadProcesses(serial); loadForegroundApp(serial); });
  document.getElementById('processes-filter').addEventListener('input', renderProcessesTable);
  loadProcesses(serial);
  loadForegroundApp(serial);
}

let PROCESSES_CACHE = [];

async function loadForegroundApp(serial) {
  const el = document.getElementById('processes-foreground');
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/foreground-app`);
  const data = await res.json();
  if (el) el.textContent = data.ok && data.package ? `Foreground: ${data.package}${data.activity ? '/' + data.activity : ''}` : 'Foreground: —';
}

async function loadProcesses(serial) {
  const body = document.getElementById('processes-table-body');
  const alertEl = document.getElementById('processes-alert');
  body.innerHTML = `<tr><td colspan="6">Loading…</td></tr>`;
  alertEl.innerHTML = '';
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/processes`);
    const data = await res.json();
    if (!data.ok) { body.innerHTML = `<tr><td colspan="6">${escapeHtml(data.error)}</td></tr>`; return; }
    if (!data.parseable) alertEl.innerHTML = `<div class="alert warn">Process list format was not fully recognized on this device; showing best-effort results.</div>`;
    PROCESSES_CACHE = data.processes;
    renderProcessesTable();
  } catch (err) {
    body.innerHTML = `<tr><td colspan="6">${escapeHtml(String(err))}</td></tr>`;
  }
}

function renderProcessesTable() {
  const body = document.getElementById('processes-table-body');
  const filter = (document.getElementById('processes-filter').value || '').toLowerCase();
  const serial = getSelectedSerial();
  const rows = PROCESSES_CACHE.filter((p) => !filter || String(p.pid).includes(filter) || (p.name || '').toLowerCase().includes(filter)).slice(0, 500);
  if (!rows.length) { body.innerHTML = `<tr><td colspan="6" class="muted">No matching processes</td></tr>`; return; }
  body.innerHTML = rows.map((p) => `
    <tr>
      <td>${p.pid ?? '—'}</td><td>${escapeHtml(p.ppid || '—')}</td><td>${escapeHtml(p.user || '—')}</td>
      <td>${escapeHtml(p.rss_kb || '—')}</td><td>${escapeHtml(p.name || '—')}</td>
      <td><button data-pid="${p.pid}" data-sig="TERM">Term</button><button data-pid="${p.pid}" data-sig="KILL">Kill -9</button></td>
    </tr>`).join('');
  body.querySelectorAll('button[data-pid]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const pid = btn.dataset.pid;
      if (!pid || pid === 'null') return;
      if (!confirm(`Send ${btn.dataset.sig} to pid ${pid}?`)) return;
      const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/processes/${pid}/kill`, { method: 'POST', body: { signal: btn.dataset.sig } });
      const data = await res.json();
      toast(data.ok ? 'Signal sent' : `Failed: ${data.error}`, data.ok ? 'success' : 'error');
      loadProcesses(serial);
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'processes') renderProcessesTab(); });
  onDeviceChange(() => { if (currentTab() === 'processes') renderProcessesTab(); });
});

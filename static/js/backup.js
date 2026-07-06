// Backup tab: one-click exports for common media folders, logcat, APKs, app data/databases.

function renderBackupTab() {
  const pane = document.getElementById('tab-backup');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to export backups.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="card-grid">
      <div class="card">
        <h4>Common folders</h4>
        <div id="backup-targets" style="display:flex; gap:6px; flex-wrap:wrap;">Loading…</div>
      </div>
      <div class="card">
        <h4>Logs</h4>
        <button id="backup-logcat-btn">Export logcat</button>
      </div>
      <div class="card">
        <h4>APK export</h4>
        <div style="display:flex; gap:8px;">
          <input type="text" id="backup-apk-package" placeholder="com.example.app" style="flex:1;">
          <button id="backup-apk-btn">Export APK</button>
        </div>
      </div>
      <div class="card">
        <h4>App data / database (needs debuggable app or root)</h4>
        <div style="display:flex; gap:8px; margin-bottom:6px;">
          <input type="text" id="backup-data-package" placeholder="Package" style="flex:1;">
          <button id="backup-appdata-btn">Export app data (.tar.gz)</button>
          <button id="backup-appdata-async-btn" title="Run as a cancellable background job (Settings tab)">…as background job</button>
        </div>
        <div style="display:flex; gap:8px;">
          <input type="text" id="backup-db-name" placeholder="Database file name" style="flex:1;">
          <button id="backup-db-btn">Export database</button>
        </div>
        <div id="backup-limitation" class="alert info" style="margin-top:8px;">
          Requires the target app to be debuggable (uses run-as) or the device to be rooted; otherwise this will fail with a clear error.
        </div>
      </div>
    </div>
  `;
  loadBackupTargets(serial);
  document.getElementById('backup-logcat-btn').addEventListener('click', () => {
    window.location.href = `/api/devices/${encodeURIComponent(serial)}/backup/logcat`;
  });
  document.getElementById('backup-apk-btn').addEventListener('click', () => {
    const pkg = document.getElementById('backup-apk-package').value.trim();
    if (!pkg) return;
    window.location.href = `/api/devices/${encodeURIComponent(serial)}/backup/apk/${encodeURIComponent(pkg)}`;
  });
  document.getElementById('backup-appdata-btn').addEventListener('click', async () => {
    const pkg = document.getElementById('backup-data-package').value.trim();
    if (!pkg) return;
    await downloadOrError(`/api/devices/${encodeURIComponent(serial)}/backup/app-data?package=${encodeURIComponent(pkg)}`);
  });
  document.getElementById('backup-appdata-async-btn').addEventListener('click', async () => {
    const pkg = document.getElementById('backup-data-package').value.trim();
    if (!pkg) return;
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/backup/app-data/async?package=${encodeURIComponent(pkg)}`);
    const data = await res.json();
    toast(data.ok ? 'Export job started — see Settings → Background jobs' : `Failed: ${data.error}`, data.ok ? 'success' : 'error');
  });
  document.getElementById('backup-db-btn').addEventListener('click', async () => {
    const pkg = document.getElementById('backup-data-package').value.trim();
    const db = document.getElementById('backup-db-name').value.trim();
    if (!pkg || !db) return;
    await downloadOrError(`/api/devices/${encodeURIComponent(serial)}/backup/database?package=${encodeURIComponent(pkg)}&db=${encodeURIComponent(db)}`);
  });
}

async function downloadOrError(url) {
  try {
    const res = await apiFetch(url);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      toast(`Export failed: ${data.error || res.statusText}`, 'error');
      return;
    }
    const blob = await res.blob();
    const disposition = res.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = match ? match[1] : 'export';
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (err) {
    toast(`Export failed: ${err}`, 'error');
  }
}

async function loadBackupTargets(serial) {
  const container = document.getElementById('backup-targets');
  const res = await apiFetch('/api/backup/targets');
  const data = await res.json();
  const entries = Object.entries(data.targets || {});
  container.innerHTML = entries.map(([key, path]) => `<button data-key="${escapeHtml(key)}" title="${escapeHtml(path)}">${escapeHtml(key)}</button>`).join('');
  container.querySelectorAll('button[data-key]').forEach((btn) => {
    btn.addEventListener('click', () => {
      window.location.href = `/api/devices/${encodeURIComponent(serial)}/backup/export/${encodeURIComponent(btn.dataset.key)}`;
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'backup') renderBackupTab(); });
  onDeviceChange(() => { if (currentTab() === 'backup') renderBackupTab(); });
});

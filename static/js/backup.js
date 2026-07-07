// Backup tab: one-click exports for common media folders, logcat, APKs, app data/databases.

Object.assign(TIP_REGISTRY, {
  'backup.appdata': {
    title: 'App data / database export',
    body: '<p>Requires the target app to be debuggable (uses <code>run-as</code>) or the device to be rooted; otherwise this fails with a clear error.</p><p>"…as background job" runs the same export as a cancellable job you can track from Settings → Background jobs, useful for large app data.</p>',
  },
});

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
    <div class="panel-page">
      <div class="panel-header">
        <h2>Backup</h2>
        <p class="muted">One-click exports for common media folders, logs, APKs, and app data/databases.</p>
      </div>
      <div id="backup-subnav"></div>
    </div>
  `;
  createSubNav(document.getElementById('backup-subnav'), 'adbpanel.subnav.backup', [
    { key: 'folders', label: 'Folders', render: (body) => renderBackupFoldersView(body, serial) },
    { key: 'logs', label: 'Logs', render: (body) => renderBackupLogsView(body, serial) },
    { key: 'apk', label: 'APK export', render: (body) => renderBackupApkView(body, serial) },
    { key: 'appdata', label: 'App data', render: (body) => renderBackupAppDataView(body, serial) },
  ]);
}

function renderBackupFoldersView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <div class="section-head"><div><h3>Common folders</h3><p class="section-desc">One click zips and downloads the whole folder.</p></div></div>
      <div id="backup-targets" class="toolbar-row">Loading…</div>
    </section>`;
  loadBackupTargets(serial);
}

function renderBackupLogsView(body, serial) {
  body.innerHTML = `<section class="panel-section"><button id="backup-logcat-btn">Export logcat</button></section>`;
  document.getElementById('backup-logcat-btn').addEventListener('click', () => {
    window.location.href = `/api/devices/${encodeURIComponent(serial)}/backup/logcat`;
  });
}

function renderBackupApkView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <div class="toolbar-row">
        <input type="text" id="backup-apk-package" placeholder="com.example.app" style="flex:1;">
        <button id="backup-apk-btn">Export APK</button>
      </div>
    </section>`;
  document.getElementById('backup-apk-btn').addEventListener('click', () => {
    const pkg = document.getElementById('backup-apk-package').value.trim();
    if (!pkg) return;
    window.location.href = `/api/devices/${encodeURIComponent(serial)}/backup/apk/${encodeURIComponent(pkg)}`;
  });
}

function renderBackupAppDataView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <div class="section-head">
        <div><h3>App data / database</h3></div>
        <button type="button" class="tip-btn" data-tip-key="backup.appdata" aria-label="Help">?</button>
      </div>
      <div class="toolbar-row">
        <input type="text" id="backup-data-package" placeholder="Package" style="flex:1;">
        <button id="backup-appdata-btn">Export app data (.tar.gz)</button>
        <button id="backup-appdata-async-btn" title="Run as a cancellable background job (Settings tab)">…as background job</button>
      </div>
      <div class="toolbar-row">
        <input type="text" id="backup-db-name" placeholder="Database file name" style="flex:1;">
        <button id="backup-db-btn">Export database</button>
      </div>
    </section>`;
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

// Packages tab: list/search installed apps, install/uninstall/enable/disable/etc.

let PACKAGES_CACHE = [];

function renderPackagesTab() {
  const pane = document.getElementById('tab-packages');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to manage packages.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="card">
      <div style="display:flex; gap:8px; margin-bottom:10px; flex-wrap:wrap;">
        <input type="text" id="packages-filter" placeholder="Filter by package name…" style="flex:1; min-width:200px;">
        <label><input type="checkbox" id="packages-system-toggle"> Show system apps</label>
        <button id="packages-refresh-btn">Refresh</button>
        <label class="ghost-btn" style="display:inline-block;">Install APK(s)<input type="file" id="packages-install-input" accept=".apk" multiple style="display:none;"></label>
      </div>
      <div id="packages-alert"></div>
      <table>
        <thead><tr><th>Package</th><th>Version</th><th>Type</th><th>Actions</th></tr></thead>
        <tbody id="packages-table-body"><tr><td colspan="4">Loading…</td></tr></tbody>
      </table>
    </div>
  `;
  wirePackagesToolbar(serial);
  loadPackages(serial);
}

function wirePackagesToolbar(serial) {
  document.getElementById('packages-refresh-btn').addEventListener('click', () => loadPackages(serial));
  document.getElementById('packages-filter').addEventListener('input', () => renderPackagesTable(serial));
  document.getElementById('packages-system-toggle').addEventListener('change', () => renderPackagesTable(serial));
  document.getElementById('packages-install-input').addEventListener('change', async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    const form = new FormData();
    files.forEach((f) => form.append('apk', f));
    toast(`Installing ${files.map((f) => f.name).join(', ')}…`, 'info');
    try {
      const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/install`, { method: 'POST', body: form });
      const data = await res.json();
      if (data.ok) { toast('Install succeeded', 'success'); loadPackages(serial); }
      else toast(`Install failed: ${data.output || data.error}`, 'error');
    } catch (err) { toast(`Install failed: ${err}`, 'error'); }
    e.target.value = '';
  });
}

async function loadPackages(serial) {
  const body = document.getElementById('packages-table-body');
  body.innerHTML = `<tr><td colspan="4">Loading…</td></tr>`;
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages`);
    const data = await res.json();
    if (!data.ok) { body.innerHTML = `<tr><td colspan="4">Failed: ${escapeHtml(data.error)}</td></tr>`; return; }
    PACKAGES_CACHE = data.packages;
    renderPackagesTable(serial);
  } catch (err) {
    body.innerHTML = `<tr><td colspan="4">${escapeHtml(String(err))}</td></tr>`;
  }
}

function renderPackagesTable(serial) {
  const body = document.getElementById('packages-table-body');
  const filter = document.getElementById('packages-filter').value.toLowerCase();
  const showSystem = document.getElementById('packages-system-toggle').checked;
  const rows = PACKAGES_CACHE
    .filter((p) => (showSystem || !p.is_system) && p.package.toLowerCase().includes(filter))
    .slice(0, 500);
  if (!rows.length) { body.innerHTML = `<tr><td colspan="4" class="muted">No matching packages</td></tr>`; return; }
  body.innerHTML = rows.map((p) => `
    <tr data-pkg="${escapeHtml(p.package)}">
      <td>${escapeHtml(p.package)}</td>
      <td>${escapeHtml(p.version_name || '—')} ${p.version_code ? '(' + escapeHtml(p.version_code) + ')' : ''}</td>
      <td>${p.is_system ? '<span class="badge yellow">system</span>' : '<span class="badge green">user</span>'}</td>
      <td class="file-actions">
        <button data-act="launch">Launch</button>
        <button data-act="force-stop">Stop</button>
        <button data-act="disable">Disable</button>
        <button data-act="enable">Enable</button>
        <button data-act="clear-data">Clear</button>
        <button data-act="pull">Pull APK</button>
        <button data-act="uninstall">Uninstall</button>
      </td>
    </tr>`).join('');
  body.querySelectorAll('tr[data-pkg]').forEach((row) => {
    const pkg = row.dataset.pkg;
    row.querySelectorAll('button[data-act]').forEach((btn) => {
      btn.addEventListener('click', () => handlePackageAction(serial, pkg, btn.dataset.act));
    });
  });
}

async function handlePackageAction(serial, pkg, action) {
  if (action === 'pull') {
    window.location.href = `/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/pull`;
    return;
  }
  if (action === 'uninstall' && !confirm(`Uninstall ${pkg}?`)) return;
  const endpointMap = {
    launch: 'launch', 'force-stop': 'force-stop', disable: 'disable', enable: 'enable',
    'clear-data': 'clear-data', uninstall: 'uninstall',
  };
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/${endpointMap[action]}`, { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      toast(`${action} succeeded`, 'success');
      if (action === 'uninstall') loadPackages(serial);
    } else {
      toast(`${action} failed: ${data.output || data.error}`, 'error');
    }
  } catch (err) {
    toast(`${action} failed: ${err}`, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'packages') renderPackagesTab(); });
  onDeviceChange(() => { if (currentTab() === 'packages') renderPackagesTab(); });
});

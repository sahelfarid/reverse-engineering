// App Inspector tab: pick a package, view permissions/components/data dirs.

function renderInspectorTab() {
  const pane = document.getElementById('tab-inspector');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to inspect apps.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="panel-page">
      <div class="panel-header">
        <h2>App Inspector</h2>
        <p class="muted">Pick a package to view its permissions, components, and app data.</p>
      </div>
      <section class="panel-section">
        <div class="toolbar-row">
          <select id="inspector-package-select" style="flex:1;"><option>Loading packages…</option></select>
          <button id="inspector-inspect-btn">Inspect</button>
          <button id="inspector-open-btn">Open</button>
          <button id="inspector-kill-btn">Kill</button>
          <button id="inspector-restart-btn">Restart</button>
        </div>
        <div id="inspector-body" class="muted">Select a package and click Inspect.</div>
      </section>
    </div>
  `;
  loadInspectorPackages(serial);
  document.getElementById('inspector-inspect-btn').addEventListener('click', () => inspectSelected(serial));
  document.getElementById('inspector-open-btn').addEventListener('click', () => quickPackageAction(serial, 'launch'));
  document.getElementById('inspector-kill-btn').addEventListener('click', () => quickPackageAction(serial, 'force-stop'));
  document.getElementById('inspector-restart-btn').addEventListener('click', () => quickPackageAction(serial, 'restart'));
}

async function loadInspectorPackages(serial) {
  const select = document.getElementById('inspector-package-select');
  try {
    let list = PACKAGES_CACHE && PACKAGES_CACHE.length ? PACKAGES_CACHE : null;
    if (!list) {
      const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages`);
      const data = await res.json();
      list = data.ok ? data.packages : [];
    }
    select.innerHTML = list.map((p) => `<option value="${escapeHtml(p.package)}">${escapeHtml(p.package)}</option>`).join('');
  } catch (err) {
    select.innerHTML = `<option value="">Failed to load packages</option>`;
  }
}

function inspectorListOrDash(arr) {
  return arr.length ? arr.map(escapeHtml).join('<br>') : '<span class="muted">none</span>';
}

async function inspectSelected(serial) {
  const pkg = document.getElementById('inspector-package-select').value;
  const body = document.getElementById('inspector-body');
  if (!pkg) return;
  body.innerHTML = 'Loading…';
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/inspect`);
    const data = await res.json();
    if (!data.ok) { body.innerHTML = `<div class="alert error">${escapeHtml(data.error)}</div>`; return; }
    const d = data.detail;
    // Mounted lazily (post-action) rather than at tab-render time -- same
    // createSubNav helper other tabs use pre-action, invoked here once we
    // actually have data to show behind the pills.
    createSubNav(body, 'adbpanel.subnav.inspector', [
      { key: 'permissions', label: 'Permissions', render: (v) => renderInspectorPermissionsView(v, d) },
      { key: 'components', label: 'Components', render: (v) => renderInspectorComponentsView(v, d) },
      { key: 'data', label: 'App data', render: (v) => renderInspectorDataView(v, d) },
    ]);
  } catch (err) {
    body.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

function renderInspectorPermissionsView(body, d) {
  body.innerHTML = `
    <div class="card-grid">
      <div class="card"><h4>Requested permissions</h4>${inspectorListOrDash(d.permissions.requested)}</div>
      <div class="card"><h4>Granted</h4>${inspectorListOrDash(d.permissions.granted)}</div>
      <div class="card"><h4>Denied</h4>${inspectorListOrDash(d.permissions.denied)}</div>
      <div class="card"><h4>Native ABI</h4>${escapeHtml(d.permissions.primary_abi || '—')} / ${escapeHtml(d.permissions.secondary_abi || '—')}</div>
    </div>`;
}

function renderInspectorComponentsView(body, d) {
  body.innerHTML = `
    <div class="card-grid">
      <div class="card"><h4>Activities</h4>${inspectorListOrDash(d.components.activities)}</div>
      <div class="card"><h4>Services</h4>${inspectorListOrDash(d.components.services)}</div>
      <div class="card"><h4>Receivers</h4>${inspectorListOrDash(d.components.receivers)}</div>
      <div class="card"><h4>Providers</h4>${inspectorListOrDash(d.components.providers)}</div>
    </div>`;
}

function renderInspectorDataView(body, d) {
  body.innerHTML = `
    <div class="card">
      <h4>App data</h4>
      ${d.data.accessible ? `
        <div>Size: ${escapeHtml(d.data.size || '—')}</div>
        <div>Databases: ${inspectorListOrDash(d.data.databases)}</div>
        <div>Shared prefs: ${inspectorListOrDash(d.data.shared_prefs)}</div>
      ` : `<div class="alert info">${escapeHtml(d.data.limitation)}</div>`}
    </div>`;
}

async function quickPackageAction(serial, action) {
  const pkg = document.getElementById('inspector-package-select').value;
  if (!pkg) return;
  const endpoint = action === 'restart' ? 'restart' : action;
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/${endpoint}`, { method: 'POST' });
    const data = await res.json();
    toast(data.ok ? `${action} ok` : `${action} failed: ${data.output || data.error}`, data.ok ? 'success' : 'error');
  } catch (err) {
    toast(`${action} failed: ${err}`, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'inspector') renderInspectorTab(); });
  onDeviceChange(() => { if (currentTab() === 'inspector') renderInspectorTab(); });
});

// APKTool tab: decompile, browse/edit local projects, rebuild, and reinstall.

let APKTOOL_PACKAGES = [];
let APKTOOL_PROJECT = null;
let APKTOOL_PATH = '';

function renderApktoolTab() {
  const pane = document.getElementById('tab-apktool');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to decompile APKs.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="alert warn">Authorized testing only. Decompile, edit, rebuild, and reinstall APKs you own or are explicitly allowed to test.</div>
    <div class="card-grid">
      <div class="card" style="grid-column: span 2;">
        <h3>Tooling</h3>
        <div id="apktool-tab-status" class="muted">Checking...</div>
        <div style="display:flex; gap:8px; margin-top:10px; flex-wrap:wrap;">
          <button id="apktool-refresh-status-btn">Refresh status</button>
          <button id="apktool-install-btn">Install APKTool</button>
        </div>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Decompile package</h3>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <input type="text" id="apktool-package-filter" placeholder="Filter packages..." style="flex:1; min-width:180px;">
          <select id="apktool-package-select" style="flex:2; min-width:260px;"></select>
          <button id="apktool-load-packages-btn">Refresh packages</button>
          <button id="apktool-decompile-btn">Decompile</button>
        </div>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Projects</h3>
        <div style="display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap;">
          <button id="apktool-refresh-projects-btn">Refresh projects</button>
          <button id="apktool-rebuild-btn" disabled>Rebuild</button>
          <button id="apktool-reinstall-btn" disabled>Reinstall signed APK</button>
          <button id="apktool-delete-project-btn" disabled>Delete project</button>
        </div>
        <div id="apktool-projects-body" class="muted">Loading...</div>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Project browser</h3>
        <div class="breadcrumbs" id="apktool-breadcrumbs"></div>
        <table>
          <thead><tr><th>Name</th><th>Size</th><th>Modified</th><th>Action</th></tr></thead>
          <tbody id="apktool-browser-body"><tr><td colspan="4" class="muted">Open a project.</td></tr></tbody>
        </table>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Editor</h3>
        <div class="muted" id="apktool-editor-path">No file open</div>
        <textarea id="apktool-editor" spellcheck="false" style="width:100%; min-height:360px; font-family:Consolas, monospace;"></textarea>
        <div style="display:flex; gap:8px; margin-top:8px;">
          <button id="apktool-save-file-btn" disabled>Save file</button>
        </div>
      </div>
    </div>
  `;
  wireApktoolControls(serial);
  loadApktoolStatus();
  loadApktoolPackages(serial);
  loadApktoolProjects();
}

function wireApktoolControls(serial) {
  document.getElementById('apktool-refresh-status-btn').addEventListener('click', loadApktoolStatus);
  document.getElementById('apktool-install-btn').addEventListener('click', installApktool);
  document.getElementById('apktool-load-packages-btn').addEventListener('click', () => loadApktoolPackages(serial));
  document.getElementById('apktool-package-filter').addEventListener('input', renderApktoolPackageSelect);
  document.getElementById('apktool-decompile-btn').addEventListener('click', () => startApktoolDecompile(serial));
  document.getElementById('apktool-refresh-projects-btn').addEventListener('click', loadApktoolProjects);
  document.getElementById('apktool-rebuild-btn').addEventListener('click', startApktoolRebuild);
  document.getElementById('apktool-reinstall-btn').addEventListener('click', () => reinstallApktoolProject(serial));
  document.getElementById('apktool-delete-project-btn').addEventListener('click', deleteApktoolProject);
  document.getElementById('apktool-save-file-btn').addEventListener('click', saveApktoolFile);
}

async function loadApktoolStatus() {
  const el = document.getElementById('apktool-tab-status');
  if (!el) return;
  const res = await apiFetch('/api/apktool/status');
  const status = await res.json();
  const java = status.java || {};
  const tool = status.apktool || {};
  const signing = status.signing || {};
  el.innerHTML = `
    Java: ${java.installed ? `<span class="badge green">${escapeHtml(java.version || 'installed')}</span>` : '<span class="badge red">missing</span>'}
    APKTool: ${tool.installed ? `<span class="badge green">${escapeHtml(tool.version || tool.pinned_version)}</span>` : '<span class="badge red">missing</span>'}
    Signing: ${signing.available ? `<span class="badge green">${escapeHtml(signing.preferred)}</span>` : '<span class="badge red">missing</span>'}
    Zipalign: ${signing.zipalign ? 'yes' : 'optional'}
  `;
  if (typeof renderApktoolStatus === 'function') renderApktoolStatus(status);
}

async function loadApktoolPackages(serial) {
  const select = document.getElementById('apktool-package-select');
  if (select) select.innerHTML = '<option>Loading...</option>';
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages`);
  const data = await res.json();
  APKTOOL_PACKAGES = data.packages || [];
  renderApktoolPackageSelect();
}

function renderApktoolPackageSelect() {
  const select = document.getElementById('apktool-package-select');
  if (!select) return;
  const filter = (document.getElementById('apktool-package-filter').value || '').toLowerCase();
  const rows = APKTOOL_PACKAGES.filter((p) => (p.package || '').toLowerCase().includes(filter)).slice(0, 500);
  select.innerHTML = rows.map((p) => `<option value="${escapeHtml(p.package)}">${escapeHtml(p.package)}${p.is_system ? ' (system)' : ''}</option>`).join('');
  if (!rows.length) select.innerHTML = '<option value="">No matching packages</option>';
}

async function startApktoolDecompile(serial) {
  const pkg = document.getElementById('apktool-package-select').value;
  if (!pkg) { toast('Select a package first', 'error'); return; }
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/apktool/decompile/${encodeURIComponent(pkg)}`, { method: 'POST' });
  const data = await res.json();
  toast(data.ok ? 'Decompile job started - see Settings > Background jobs' : `Decompile failed: ${data.error}`, data.ok ? 'success' : 'error');
}

async function loadApktoolProjects() {
  const body = document.getElementById('apktool-projects-body');
  if (body) body.innerHTML = 'Loading...';
  const res = await apiFetch('/api/apktool/projects');
  const data = await res.json();
  const projects = data.projects || [];
  if (!projects.length) { body.innerHTML = '<div class="muted">No decompiled projects yet.</div>'; return; }
  body.innerHTML = `
    <table>
      <thead><tr><th>Project</th><th>Decompiled</th><th>Size</th><th>Action</th></tr></thead>
      <tbody>
        ${projects.map((p) => `<tr>
          <td>${escapeHtml(p.package || p.project)}</td>
          <td>${new Date((p.decompiled_at || 0) * 1000).toLocaleString()}</td>
          <td>${formatBytes(p.size)}</td>
          <td><button data-project="${escapeHtml(p.project)}">Open</button></td>
        </tr>`).join('')}
      </tbody>
    </table>
  `;
  body.querySelectorAll('button[data-project]').forEach((btn) => {
    btn.addEventListener('click', () => openApktoolProject(btn.dataset.project, ''));
  });
}

async function openApktoolProject(project, path) {
  APKTOOL_PROJECT = project;
  APKTOOL_PATH = path || '';
  document.getElementById('apktool-rebuild-btn').disabled = false;
  document.getElementById('apktool-reinstall-btn').disabled = false;
  document.getElementById('apktool-delete-project-btn').disabled = false;
  await browseApktoolProject();
}

async function browseApktoolProject() {
  const body = document.getElementById('apktool-browser-body');
  body.innerHTML = `<tr><td colspan="4">Loading...</td></tr>`;
  const res = await apiFetch(`/api/apktool/projects/${encodeURIComponent(APKTOOL_PROJECT)}/browse?path=${encodeURIComponent(APKTOOL_PATH)}`);
  const data = await res.json();
  if (!data.ok) { body.innerHTML = `<tr><td colspan="4">${escapeHtml(data.error)}</td></tr>`; return; }
  renderApktoolBreadcrumbs(data.breadcrumbs || []);
  if (!data.entries.length) { body.innerHTML = `<tr><td colspan="4" class="muted">Empty folder</td></tr>`; return; }
  body.innerHTML = data.entries.map((e) => {
    const fullPath = APKTOOL_PATH ? `${APKTOOL_PATH}/${e.name}` : e.name;
    return `<tr data-path="${escapeHtml(fullPath)}" data-type="${escapeHtml(e.type)}">
      <td>${escapeHtml(e.name)}</td>
      <td>${e.size != null ? formatBytes(e.size) : '-'}</td>
      <td>${new Date((e.modified || 0) * 1000).toLocaleString()}</td>
      <td><button data-act="${e.type === 'dir' ? 'open' : 'edit'}">${e.type === 'dir' ? 'Open' : 'Edit'}</button></td>
    </tr>`;
  }).join('');
  body.querySelectorAll('button[data-act]').forEach((btn) => {
    const row = btn.closest('tr');
    btn.addEventListener('click', () => {
      if (btn.dataset.act === 'open') openApktoolProject(APKTOOL_PROJECT, row.dataset.path);
      else openApktoolFile(row.dataset.path);
    });
  });
}

function renderApktoolBreadcrumbs(breadcrumbs) {
  const el = document.getElementById('apktool-breadcrumbs');
  el.innerHTML = breadcrumbs.map((b) => `<span data-path="${escapeHtml(b.path)}">${escapeHtml(b.name)}</span>`).join('<span class="muted"> / </span>');
  el.querySelectorAll('span[data-path]').forEach((s) => s.addEventListener('click', () => openApktoolProject(APKTOOL_PROJECT, s.dataset.path)));
}

async function openApktoolFile(path) {
  const res = await apiFetch(`/api/apktool/projects/${encodeURIComponent(APKTOOL_PROJECT)}/file?path=${encodeURIComponent(path)}`);
  const data = await res.json();
  if (!data.ok) { toast(`Open failed: ${data.error}`, 'error'); return; }
  document.getElementById('apktool-editor-path').textContent = path;
  document.getElementById('apktool-editor-path').dataset.path = path;
  document.getElementById('apktool-editor').value = data.content || '';
  document.getElementById('apktool-save-file-btn').disabled = false;
}

async function saveApktoolFile() {
  const pathEl = document.getElementById('apktool-editor-path');
  const path = pathEl.dataset.path;
  if (!APKTOOL_PROJECT || !path) return;
  const res = await apiFetch(`/api/apktool/projects/${encodeURIComponent(APKTOOL_PROJECT)}/file?path=${encodeURIComponent(path)}`, {
    method: 'POST',
    body: { content: document.getElementById('apktool-editor').value },
  });
  const data = await res.json();
  toast(data.ok ? 'File saved' : `Save failed: ${data.error}`, data.ok ? 'success' : 'error');
}

async function startApktoolRebuild() {
  if (!APKTOOL_PROJECT) return;
  const res = await apiFetch(`/api/apktool/projects/${encodeURIComponent(APKTOOL_PROJECT)}/rebuild`, { method: 'POST' });
  const data = await res.json();
  toast(data.ok ? 'Rebuild job started - see Settings > Background jobs' : `Rebuild failed: ${data.error}`, data.ok ? 'success' : 'error');
}

async function reinstallApktoolProject(serial) {
  if (!APKTOOL_PROJECT) return;
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/apktool/projects/${encodeURIComponent(APKTOOL_PROJECT)}/reinstall`, { method: 'POST' });
  const data = await res.json();
  toast(data.ok ? 'Reinstall succeeded' : `Reinstall failed: ${data.output || data.error}`, data.ok ? 'success' : 'error');
}

async function deleteApktoolProject() {
  if (!APKTOOL_PROJECT || !confirm(`Delete local project ${APKTOOL_PROJECT}?`)) return;
  const project = APKTOOL_PROJECT;
  const res = await apiFetch(`/api/apktool/projects/${encodeURIComponent(project)}`, { method: 'DELETE' });
  const data = await res.json();
  toast(data.ok ? 'Project deleted' : `Delete failed: ${data.error}`, data.ok ? 'success' : 'error');
  if (data.ok) {
    APKTOOL_PROJECT = null;
    APKTOOL_PATH = '';
    renderApktoolTab();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'apktool') renderApktoolTab(); });
  onDeviceChange(() => { if (currentTab() === 'apktool') renderApktoolTab(); });
});

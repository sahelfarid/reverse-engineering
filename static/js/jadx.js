// JADX tab: decompile (device pull or local upload) to readable Java, browse,
// search, view manifest/static findings, and export a report. Read-only --
// there is no save/rebuild/reinstall here (that's the APKTool tab's job).

let JADX_PACKAGES = [];
let JADX_PROJECT = null;
let JADX_PATH = '';

function renderJadxTab() {
  const pane = document.getElementById('tab-jadx');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  const hasDevice = !!(serial && device && device.state === 'device');
  pane.innerHTML = `
    <div class="alert warn">Authorized analysis only. Decompile and inspect APKs you own or are explicitly allowed to test.</div>
    <div class="card-grid">
      <div class="card" style="grid-column: span 2;">
        <h3>Tooling</h3>
        <div id="jadx-tab-status" class="muted">Checking...</div>
        <div style="display:flex; gap:8px; margin-top:10px; flex-wrap:wrap;">
          <button id="jadx-refresh-status-btn">Refresh status</button>
          <button id="jadx-install-btn">Install jadx</button>
        </div>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Decompile from device</h3>
        ${hasDevice ? `
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <input type="text" id="jadx-package-filter" placeholder="Filter packages..." style="flex:1; min-width:180px;">
          <select id="jadx-package-select" style="flex:2; min-width:260px;"></select>
          <button id="jadx-load-packages-btn">Refresh packages</button>
        </div>
        <div style="display:flex; gap:14px; align-items:center; margin-top:8px; flex-wrap:wrap;">
          <label class="muted"><input type="checkbox" id="jadx-opt-no-res"> Skip resources (--no-res, faster)</label>
          <label class="muted"><input type="checkbox" id="jadx-opt-deobf"> Deobfuscate names (--deobf)</label>
          <button id="jadx-decompile-btn">Decompile</button>
        </div>` : `<div class="muted">Select an authorized, online device to decompile from a package.</div>`}
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Import a local file</h3>
        <div class="muted" style="margin-bottom:8px;">Analyze an APK/DEX/JAR already on this machine instead of pulling one from a device.</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
          <input type="file" id="jadx-import-file" accept=".apk,.dex,.jar">
          <input type="text" id="jadx-import-name" placeholder="Project name (optional)" style="flex:1; min-width:160px;">
          <button id="jadx-import-btn">Import &amp; decompile</button>
        </div>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Projects</h3>
        <div style="display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap;">
          <button id="jadx-refresh-projects-btn">Refresh projects</button>
          <button id="jadx-delete-project-btn" disabled>Delete project</button>
        </div>
        <div id="jadx-projects-body" class="muted">Loading...</div>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Project browser</h3>
        <div class="breadcrumbs" id="jadx-breadcrumbs"></div>
        <table>
          <thead><tr><th>Name</th><th>Size</th><th>Modified</th><th>Action</th></tr></thead>
          <tbody id="jadx-browser-body"><tr><td colspan="4" class="muted">Open a project.</td></tr></tbody>
        </table>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Search</h3>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <input type="text" id="jadx-search-query" placeholder="Search decompiled sources..." style="flex:1; min-width:220px;">
          <label class="muted"><input type="checkbox" id="jadx-search-regex"> Regex</label>
          <button id="jadx-search-btn">Search</button>
        </div>
        <div id="jadx-search-results" class="muted" style="margin-top:8px;">No search yet.</div>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Viewer (read-only)</h3>
        <div class="muted" id="jadx-editor-path">No file open</div>
        <textarea id="jadx-editor" readonly spellcheck="false" style="width:100%; min-height:320px; font-family:Consolas, monospace;"></textarea>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Manifest</h3>
        <div style="margin-bottom:8px;"><button id="jadx-load-manifest-btn" disabled>Load manifest</button></div>
        <div id="jadx-manifest-body" class="muted">Open a project first.</div>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Static findings</h3>
        <div style="display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap;">
          <button id="jadx-run-findings-btn" disabled>Run static checks</button>
          <button id="jadx-load-findings-btn" disabled>Load last findings</button>
        </div>
        <div id="jadx-findings-body" class="muted">Open a project first.</div>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h3>Report export</h3>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <button id="jadx-export-json-btn" disabled>Export JSON</button>
          <button id="jadx-export-md-btn" disabled>Export Markdown</button>
        </div>
      </div>
    </div>
  `;
  wireJadxControls(serial);
  loadJadxStatus();
  if (hasDevice) loadJadxPackages(serial);
  loadJadxProjects();
}

function wireJadxControls(serial) {
  document.getElementById('jadx-refresh-status-btn').addEventListener('click', loadJadxStatus);
  document.getElementById('jadx-install-btn').addEventListener('click', installJadx);
  const loadPkgsBtn = document.getElementById('jadx-load-packages-btn');
  if (loadPkgsBtn) loadPkgsBtn.addEventListener('click', () => loadJadxPackages(serial));
  const filterEl = document.getElementById('jadx-package-filter');
  if (filterEl) filterEl.addEventListener('input', renderJadxPackageSelect);
  const decompileBtn = document.getElementById('jadx-decompile-btn');
  if (decompileBtn) decompileBtn.addEventListener('click', () => startJadxDecompile(serial));
  document.getElementById('jadx-import-btn').addEventListener('click', startJadxImport);
  document.getElementById('jadx-refresh-projects-btn').addEventListener('click', loadJadxProjects);
  document.getElementById('jadx-delete-project-btn').addEventListener('click', deleteJadxProject);
  document.getElementById('jadx-search-btn').addEventListener('click', searchJadxProject);
  document.getElementById('jadx-load-manifest-btn').addEventListener('click', loadJadxManifest);
  document.getElementById('jadx-run-findings-btn').addEventListener('click', runJadxFindings);
  document.getElementById('jadx-load-findings-btn').addEventListener('click', loadJadxFindings);
  document.getElementById('jadx-export-json-btn').addEventListener('click', () => exportJadxReport('json'));
  document.getElementById('jadx-export-md-btn').addEventListener('click', () => exportJadxReport('md'));
}

async function loadJadxStatus() {
  const el = document.getElementById('jadx-tab-status');
  if (!el) return;
  const res = await apiFetch('/api/jadx/status');
  const status = await res.json();
  const java = status.java || {};
  const tool = status.jadx || {};
  el.innerHTML = `
    Java: ${java.installed ? `<span class="badge green">${escapeHtml(java.version || 'installed')}</span>` : '<span class="badge red">missing</span>'}
    jadx: ${tool.installed ? `<span class="badge green">${escapeHtml(tool.version || tool.pinned_version)} (${escapeHtml(tool.source || '')})</span>` : '<span class="badge red">missing</span>'}
  `;
  if (typeof renderJadxToolStatus === 'function') renderJadxToolStatus(status);
}

async function installJadx() {
  const btn = document.getElementById('jadx-install-btn');
  if (btn) btn.disabled = true;
  try {
    const res = await apiFetch('/api/jadx/install', { method: 'POST' });
    const data = await res.json();
    toast(data.ok ? 'jadx installed successfully' : `jadx install failed: ${data.error}`, data.ok ? 'success' : 'error');
  } catch (err) {
    toast(`jadx install failed: ${err}`, 'error');
  }
  if (btn) btn.disabled = false;
  loadJadxStatus();
}

async function loadJadxPackages(serial) {
  const select = document.getElementById('jadx-package-select');
  if (select) select.innerHTML = '<option>Loading...</option>';
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages`);
  const data = await res.json();
  JADX_PACKAGES = data.packages || [];
  renderJadxPackageSelect();
}

function renderJadxPackageSelect() {
  const select = document.getElementById('jadx-package-select');
  if (!select) return;
  const filterEl = document.getElementById('jadx-package-filter');
  const filter = (filterEl ? filterEl.value : '').toLowerCase();
  const rows = JADX_PACKAGES.filter((p) => (p.package || '').toLowerCase().includes(filter)).slice(0, 500);
  select.innerHTML = rows.map((p) => `<option value="${escapeHtml(p.package)}">${escapeHtml(p.package)}${p.is_system ? ' (system)' : ''}</option>`).join('');
  if (!rows.length) select.innerHTML = '<option value="">No matching packages</option>';
}

async function startJadxDecompile(serial) {
  const select = document.getElementById('jadx-package-select');
  const pkg = select ? select.value : '';
  if (!pkg) { toast('Select a package first', 'error'); return; }
  const body = {
    no_res: document.getElementById('jadx-opt-no-res').checked,
    deobf: document.getElementById('jadx-opt-deobf').checked,
  };
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/jadx/decompile/${encodeURIComponent(pkg)}`, { method: 'POST', body });
  const data = await res.json();
  toast(data.ok ? 'Decompile job started - see Settings > Background jobs' : `Decompile failed: ${data.error}`, data.ok ? 'success' : 'error');
}

async function startJadxImport() {
  const fileInput = document.getElementById('jadx-import-file');
  const file = fileInput.files[0];
  if (!file) { toast('Choose a file to import first', 'error'); return; }
  const form = new FormData();
  form.append('file', file);
  const name = document.getElementById('jadx-import-name').value.trim();
  if (name) form.append('project', name);
  const res = await apiFetch('/api/jadx/import', { method: 'POST', body: form });
  const data = await res.json();
  toast(data.ok ? 'Import job started - see Settings > Background jobs' : `Import failed: ${data.error}`, data.ok ? 'success' : 'error');
  if (data.ok) {
    fileInput.value = '';
    document.getElementById('jadx-import-name').value = '';
  }
}

async function loadJadxProjects() {
  const body = document.getElementById('jadx-projects-body');
  if (body) body.innerHTML = 'Loading...';
  const res = await apiFetch('/api/jadx/projects');
  const data = await res.json();
  const projects = data.projects || [];
  if (!projects.length) { body.innerHTML = '<div class="muted">No decompiled projects yet.</div>'; return; }
  body.innerHTML = `
    <table>
      <thead><tr><th>Project</th><th>Source</th><th>Decompiled</th><th>Size</th><th>SHA-256</th><th>Action</th></tr></thead>
      <tbody>
        ${projects.map((p) => `<tr>
          <td>${escapeHtml(p.package || p.project)}</td>
          <td>${escapeHtml(p.source || 'device')}</td>
          <td>${new Date((p.decompiled_at || 0) * 1000).toLocaleString()}</td>
          <td>${formatBytes(p.size)}</td>
          <td class="mono-input" title="${escapeHtml(p.sha256 || '')}">${escapeHtml((p.sha256 || '').slice(0, 10))}</td>
          <td><button data-project="${escapeHtml(p.project)}">Open</button></td>
        </tr>`).join('')}
      </tbody>
    </table>
  `;
  body.querySelectorAll('button[data-project]').forEach((btn) => {
    btn.addEventListener('click', () => openJadxProject(btn.dataset.project, ''));
  });
}

function openJadxProject(project, path) {
  JADX_PROJECT = project;
  JADX_PATH = path || '';
  document.getElementById('jadx-delete-project-btn').disabled = false;
  document.getElementById('jadx-load-manifest-btn').disabled = false;
  document.getElementById('jadx-run-findings-btn').disabled = false;
  document.getElementById('jadx-load-findings-btn').disabled = false;
  document.getElementById('jadx-export-json-btn').disabled = false;
  document.getElementById('jadx-export-md-btn').disabled = false;
  document.getElementById('jadx-manifest-body').innerHTML = '<span class="muted">Not loaded yet.</span>';
  document.getElementById('jadx-findings-body').innerHTML = '<span class="muted">Not loaded yet.</span>';
  return browseJadxProject();
}

async function browseJadxProject() {
  const body = document.getElementById('jadx-browser-body');
  body.innerHTML = `<tr><td colspan="4">Loading...</td></tr>`;
  const res = await apiFetch(`/api/jadx/projects/${encodeURIComponent(JADX_PROJECT)}/browse?path=${encodeURIComponent(JADX_PATH)}`);
  const data = await res.json();
  if (!data.ok) { body.innerHTML = `<tr><td colspan="4">${escapeHtml(data.error)}</td></tr>`; return; }
  renderJadxBreadcrumbs(data.breadcrumbs || []);
  if (!data.entries.length) { body.innerHTML = `<tr><td colspan="4" class="muted">Empty folder</td></tr>`; return; }
  body.innerHTML = data.entries.map((e) => {
    const fullPath = JADX_PATH ? `${JADX_PATH}/${e.name}` : e.name;
    return `<tr data-path="${escapeHtml(fullPath)}" data-type="${escapeHtml(e.type)}">
      <td>${escapeHtml(e.name)}</td>
      <td>${e.size != null ? formatBytes(e.size) : '-'}</td>
      <td>${new Date((e.modified || 0) * 1000).toLocaleString()}</td>
      <td><button data-act="${e.type === 'dir' ? 'open' : 'view'}">${e.type === 'dir' ? 'Open' : 'View'}</button></td>
    </tr>`;
  }).join('');
  body.querySelectorAll('button[data-act]').forEach((btn) => {
    const row = btn.closest('tr');
    btn.addEventListener('click', () => {
      if (btn.dataset.act === 'open') openJadxProject(JADX_PROJECT, row.dataset.path);
      else openJadxFile(row.dataset.path);
    });
  });
}

function renderJadxBreadcrumbs(breadcrumbs) {
  const el = document.getElementById('jadx-breadcrumbs');
  el.innerHTML = breadcrumbs.map((b) => `<span data-path="${escapeHtml(b.path)}">${escapeHtml(b.name)}</span>`).join('<span class="muted"> / </span>');
  el.querySelectorAll('span[data-path]').forEach((s) => s.addEventListener('click', () => openJadxProject(JADX_PROJECT, s.dataset.path)));
}

async function openJadxFile(path) {
  const res = await apiFetch(`/api/jadx/projects/${encodeURIComponent(JADX_PROJECT)}/file?path=${encodeURIComponent(path)}`);
  const data = await res.json();
  if (!data.ok) { toast(`Open failed: ${data.error}`, 'error'); return; }
  document.getElementById('jadx-editor-path').textContent = path;
  document.getElementById('jadx-editor').value = data.content || '';
}

async function searchJadxProject() {
  if (!JADX_PROJECT) { toast('Open a project first', 'error'); return; }
  const query = document.getElementById('jadx-search-query').value.trim();
  const resultsEl = document.getElementById('jadx-search-results');
  if (!query) { toast('Enter a search query', 'error'); return; }
  const regex = document.getElementById('jadx-search-regex').checked;
  resultsEl.innerHTML = 'Searching...';
  const res = await apiFetch(`/api/jadx/projects/${encodeURIComponent(JADX_PROJECT)}/search?q=${encodeURIComponent(query)}&regex=${regex ? '1' : '0'}`);
  const data = await res.json();
  if (!data.ok) { resultsEl.innerHTML = `<span class="badge red">${escapeHtml(data.error)}</span>`; return; }
  const hits = data.results || [];
  if (!hits.length) { resultsEl.innerHTML = '<div class="muted">No matches.</div>'; return; }
  resultsEl.innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th>File</th><th>Line</th><th>Snippet</th></tr></thead>
    <tbody>${hits.map((h) => `<tr data-path="${escapeHtml(h.path)}"><td>${escapeHtml(h.path)}</td><td>${h.line}</td><td class="mono-input">${escapeHtml(h.snippet)}</td></tr>`).join('')}</tbody>
  </table></div>`;
  resultsEl.querySelectorAll('tr[data-path]').forEach((row) => {
    row.addEventListener('click', () => openJadxFile(row.dataset.path));
    row.style.cursor = 'pointer';
  });
}

function manifestComponentRows(list) {
  if (!list || !list.length) return '<div class="muted">None</div>';
  return `<div class="table-wrap"><table>
    <thead><tr><th>Name</th><th>Exported</th><th>Permission</th><th>Intents</th></tr></thead>
    <tbody>${list.map((c) => `<tr>
      <td>${escapeHtml(c.name || '')}</td>
      <td>${c.exported === 'true' ? '<span class="badge yellow">yes</span>' : 'no'}</td>
      <td>${escapeHtml(c.permission || '-')}</td>
      <td>${escapeHtml((c.intent_actions || []).join(', '))}</td>
    </tr>`).join('')}</tbody>
  </table></div>`;
}

async function loadJadxManifest() {
  if (!JADX_PROJECT) return;
  const body = document.getElementById('jadx-manifest-body');
  body.innerHTML = 'Loading...';
  const res = await apiFetch(`/api/jadx/projects/${encodeURIComponent(JADX_PROJECT)}/manifest`);
  const data = await res.json();
  if (!data.ok) { body.innerHTML = `<span class="badge red">${escapeHtml(data.error)}</span>`; return; }
  body.innerHTML = `
    <div><strong>${escapeHtml(data.package || '')}</strong> v${escapeHtml(data.version_name || '?')} (${escapeHtml(String(data.version_code || '?'))})</div>
    <div class="muted">SDK: min ${escapeHtml(String(data.min_sdk || '?'))} / target ${escapeHtml(String(data.target_sdk || '?'))}</div>
    <div style="margin:6px 0;">
      Debuggable: ${data.debuggable === 'true' ? '<span class="badge red">true</span>' : 'false'}
      &nbsp; Allow backup: ${data.allow_backup === 'true' ? '<span class="badge yellow">true</span>' : 'false'}
    </div>
    <div class="muted" style="margin-bottom:4px;">Permissions (${(data.permissions || []).length})</div>
    <div style="margin-bottom:10px;">${(data.permissions || []).map((p) => escapeHtml(p)).join('<br>') || '<span class="muted">None</span>'}</div>
    <div class="muted" style="margin-bottom:4px;">Activities</div>
    ${manifestComponentRows(data.activities)}
    <div class="muted" style="margin:8px 0 4px;">Services</div>
    ${manifestComponentRows(data.services)}
    <div class="muted" style="margin:8px 0 4px;">Receivers</div>
    ${manifestComponentRows(data.receivers)}
    <div class="muted" style="margin:8px 0 4px;">Providers</div>
    ${manifestComponentRows(data.providers)}
  `;
}

function findingsBadgeClass(severity) {
  if (severity === 'high') return 'red';
  if (severity === 'medium') return 'yellow';
  return 'gray';
}

function renderJadxFindings(findings) {
  const body = document.getElementById('jadx-findings-body');
  if (!findings || !findings.length) { body.innerHTML = '<div class="muted">No findings.</div>'; return; }
  body.innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th>Severity</th><th>Title</th><th>File</th><th>Snippet</th></tr></thead>
    <tbody>${findings.map((f) => `<tr>
      <td><span class="badge ${findingsBadgeClass(f.severity)}">${escapeHtml(f.severity)}</span></td>
      <td title="${escapeHtml(f.note || '')}">${escapeHtml(f.title)}</td>
      <td>${escapeHtml(f.file || '')}${f.line ? ':' + f.line : ''}</td>
      <td class="mono-input">${escapeHtml((f.snippet || '').slice(0, 120))}</td>
    </tr>`).join('')}</tbody>
  </table></div>`;
}

async function runJadxFindings() {
  if (!JADX_PROJECT) return;
  const body = document.getElementById('jadx-findings-body');
  body.innerHTML = 'Running static checks...';
  const res = await apiFetch(`/api/jadx/projects/${encodeURIComponent(JADX_PROJECT)}/findings`, { method: 'POST' });
  const data = await res.json();
  if (!data.ok) { body.innerHTML = `<span class="badge red">${escapeHtml(data.error)}</span>`; return; }
  renderJadxFindings(data.findings);
}

async function loadJadxFindings() {
  if (!JADX_PROJECT) return;
  const body = document.getElementById('jadx-findings-body');
  body.innerHTML = 'Loading...';
  const res = await apiFetch(`/api/jadx/projects/${encodeURIComponent(JADX_PROJECT)}/findings`);
  if (res.status === 404) { body.innerHTML = '<div class="muted">No static checks have been run for this project yet.</div>'; return; }
  const data = await res.json();
  if (!data.ok) { body.innerHTML = `<span class="badge red">${escapeHtml(data.error)}</span>`; return; }
  renderJadxFindings(data.findings);
}

function exportJadxReport(fmt) {
  if (!JADX_PROJECT) return;
  window.location.href = `/api/jadx/projects/${encodeURIComponent(JADX_PROJECT)}/report?format=${fmt}`;
}

async function deleteJadxProject() {
  if (!JADX_PROJECT || !confirm(`Delete local project ${JADX_PROJECT}?`)) return;
  const project = JADX_PROJECT;
  const res = await apiFetch(`/api/jadx/projects/${encodeURIComponent(project)}`, { method: 'DELETE' });
  const data = await res.json();
  toast(data.ok ? 'Project deleted' : `Delete failed: ${data.error}`, data.ok ? 'success' : 'error');
  if (data.ok) {
    JADX_PROJECT = null;
    JADX_PATH = '';
    renderJadxTab();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'jadx') renderJadxTab(); });
  onDeviceChange(() => { if (currentTab() === 'jadx') renderJadxTab(); });
});

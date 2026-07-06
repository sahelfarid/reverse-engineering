// File manager tab: browse/search/preview + mkdir/rename/move/copy/delete/upload/download.

function filesPathKey(serial) { return `adbpanel.filesPath.${serial}`; }
function getFilesPath(serial) { return localStorage.getItem(filesPathKey(serial)) || '/sdcard'; }
function setFilesPath(serial, path) { localStorage.setItem(filesPathKey(serial), path); }

const FILE_TYPE_ICON = { dir: '📁', file: '📄', symlink: '🔗', block: '⛭', char: '⛭', socket: '⚡', fifo: '⛭', unknown: '❓' };

function renderFilesTab() {
  const pane = document.getElementById('tab-files');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to browse files.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="card">
      <div class="breadcrumbs" id="files-breadcrumbs"></div>
      <div style="display:flex; gap:8px; margin-bottom:10px; flex-wrap:wrap;">
        <input type="text" id="files-path-input" style="flex:1; min-width:220px;">
        <button id="files-go-btn">Go</button>
        <button id="files-up-btn">Up</button>
        <button id="files-refresh-btn">Refresh</button>
        <button id="files-mkdir-btn">New folder</button>
        <label class="ghost-btn" style="display:inline-block;">Upload<input type="file" id="files-upload-input" style="display:none;"></label>
        <input type="text" id="files-search-input" placeholder="Search filename…" style="width:160px;">
        <button id="files-search-btn">Search</button>
      </div>
      <div id="files-alert"></div>
      <div id="files-search-results"></div>
      <table>
        <thead><tr><th></th><th>Name</th><th>Size</th><th>Modified</th><th>Perms</th><th>Actions</th></tr></thead>
        <tbody id="files-table-body"></tbody>
      </table>
    </div>
    <div id="preview-modal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,.6); z-index:50; align-items:center; justify-content:center;">
      <div class="card" style="max-width:80vw; max-height:80vh; overflow:auto;">
        <button id="preview-close-btn">Close</button>
        <div id="preview-body"></div>
      </div>
    </div>
  `;
  wireFilesToolbar(serial);
  loadDirectory(serial, getFilesPath(serial));
}

function wireFilesToolbar(serial) {
  document.getElementById('files-go-btn').addEventListener('click', () => {
    loadDirectory(serial, document.getElementById('files-path-input').value || '/');
  });
  document.getElementById('files-path-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') loadDirectory(serial, e.target.value || '/');
  });
  document.getElementById('files-up-btn').addEventListener('click', () => {
    const cur = getFilesPath(serial);
    const parent = cur.split('/').filter(Boolean).slice(0, -1).join('/');
    loadDirectory(serial, '/' + parent);
  });
  document.getElementById('files-refresh-btn').addEventListener('click', () => loadDirectory(serial, getFilesPath(serial)));
  document.getElementById('files-mkdir-btn').addEventListener('click', async () => {
    const name = prompt('New folder name:');
    if (!name) return;
    const path = getFilesPath(serial).replace(/\/$/, '') + '/' + name;
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/files/mkdir`, { method: 'POST', body: { path } });
    const data = await res.json();
    if (data.ok) { toast('Folder created', 'success'); loadDirectory(serial, getFilesPath(serial)); }
    else toast(`mkdir failed: ${data.error}`, 'error');
  });
  document.getElementById('files-upload-input').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    form.append('remote_dir', getFilesPath(serial));
    toast(`Uploading ${file.name}…`, 'info');
    try {
      const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/files/upload`, { method: 'POST', body: form });
      const data = await res.json();
      if (data.ok) { toast('Upload complete', 'success'); loadDirectory(serial, getFilesPath(serial)); }
      else toast(`Upload failed: ${data.error}`, 'error');
    } catch (err) { toast(`Upload failed: ${err}`, 'error'); }
    e.target.value = '';
  });
  document.getElementById('files-search-btn').addEventListener('click', () => runSearch(serial));
  document.getElementById('files-search-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') runSearch(serial); });
  document.getElementById('preview-close-btn').addEventListener('click', () => {
    document.getElementById('preview-modal').style.display = 'none';
  });
}

async function runSearch(serial) {
  const query = document.getElementById('files-search-input').value.trim();
  const container = document.getElementById('files-search-results');
  if (!query) { container.innerHTML = ''; return; }
  container.innerHTML = '<div class="muted">Searching…</div>';
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/files/search?path=${encodeURIComponent(getFilesPath(serial))}&query=${encodeURIComponent(query)}`);
  const data = await res.json();
  if (!data.ok) { container.innerHTML = `<div class="alert error">Search failed</div>`; return; }
  if (!data.results.length) { container.innerHTML = `<div class="alert info">No matches under this folder.</div>`; return; }
  container.innerHTML = `<div class="card">${data.results.map((p) => `<div class="dir-row" data-path="${escapeHtml(p)}" style="cursor:pointer; padding:4px 0;">${escapeHtml(p)}</div>`).join('')}${data.truncated ? '<div class="muted">Results truncated…</div>' : ''}</div>`;
  container.querySelectorAll('.dir-row').forEach((el) => {
    el.addEventListener('click', () => {
      const p = el.dataset.path;
      const parent = p.split('/').slice(0, -1).join('/') || '/';
      loadDirectory(serial, parent);
      container.innerHTML = '';
    });
  });
}

async function loadDirectory(serial, path) {
  const alertEl = document.getElementById('files-alert');
  const body = document.getElementById('files-table-body');
  alertEl.innerHTML = '';
  body.innerHTML = `<tr><td colspan="6">Loading…</td></tr>`;
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/files/browse?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    if (!data.ok) {
      const messages = {
        permission_denied: 'Permission denied listing this folder.',
        not_found: 'That path does not exist on the device.',
      };
      alertEl.innerHTML = `<div class="alert error">${escapeHtml(messages[data.error] || data.error || 'Failed to list directory')}</div>`;
      body.innerHTML = '';
      return;
    }
    setFilesPath(serial, data.path);
    document.getElementById('files-path-input').value = data.path;
    renderBreadcrumbs(serial, data.breadcrumbs);
    if (!data.parseable) {
      alertEl.innerHTML = `<div class="alert warn">Some entries could not be fully parsed (best effort shown).</div>`;
    }
    renderFilesTable(serial, data.path, data.entries);
  } catch (err) {
    alertEl.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

function renderBreadcrumbs(serial, breadcrumbs) {
  const el = document.getElementById('files-breadcrumbs');
  el.innerHTML = breadcrumbs.map((b) => `<span data-path="${escapeHtml(b.path)}">${escapeHtml(b.name)}</span>`).join('<span class="muted"> / </span>');
  el.querySelectorAll('span[data-path]').forEach((s) => s.addEventListener('click', () => loadDirectory(serial, s.dataset.path)));
}

function renderFilesTable(serial, currentPath, entries) {
  const body = document.getElementById('files-table-body');
  if (!entries.length) { body.innerHTML = `<tr><td colspan="6" class="muted">Empty folder</td></tr>`; return; }
  body.innerHTML = entries.map((e) => {
    const fullPath = currentPath.replace(/\/$/, '') + '/' + e.name;
    const icon = FILE_TYPE_ICON[e.type] || '❓';
    const isDir = e.type === 'dir';
    return `
      <tr class="${isDir ? 'dir-row' : ''}" data-path="${escapeHtml(fullPath)}" data-type="${e.type}">
        <td>${icon}</td>
        <td>${escapeHtml(e.name)}${e.symlink_target ? ' → ' + escapeHtml(e.symlink_target) : ''}</td>
        <td>${e.size != null ? formatBytes(e.size) : '—'}</td>
        <td>${escapeHtml(e.mtime || '—')}</td>
        <td>${escapeHtml(e.perms || '—')}</td>
        <td class="file-actions">
          ${isDir ? `<button data-act="zip">ZIP</button><button data-act="zip-async" title="Run as a cancellable background job (Settings tab)">ZIP (job)</button>` : `<a href="/api/devices/${encodeURIComponent(serial)}/files/download?path=${encodeURIComponent(fullPath)}"><button type="button">DL</button></a>`}
          ${!isDir ? `<button data-act="preview">View</button>` : ''}
          <button data-act="rename">Ren</button>
          <button data-act="move">Mv</button>
          <button data-act="copy">Cp</button>
          <button data-act="delete">Del</button>
        </td>
      </tr>`;
  }).join('');

  body.querySelectorAll('tr').forEach((row) => {
    const path = row.dataset.path;
    const isDir = row.dataset.type === 'dir';
    if (isDir) {
      row.addEventListener('click', (e) => {
        if (e.target.closest('.file-actions')) return;
        loadDirectory(serial, path);
      });
    }
    row.querySelectorAll('button[data-act]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleFileAction(serial, path, isDir, btn.dataset.act, currentPath);
      });
    });
  });
}

async function handleFileAction(serial, path, isDir, action, currentPath) {
  if (action === 'zip') {
    window.location.href = `/api/devices/${encodeURIComponent(serial)}/files/download-folder?path=${encodeURIComponent(path)}`;
    return;
  }
  if (action === 'zip-async') {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/files/download-folder/async?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    toast(data.ok ? 'Folder ZIP job started — see Settings → Background jobs' : `Failed: ${data.error}`, data.ok ? 'success' : 'error');
    return;
  }
  if (action === 'preview') return openPreview(serial, path);
  if (action === 'delete') {
    if (!confirm(`Delete ${path}${isDir ? ' (recursively)' : ''}?`)) return;
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/files/delete`, { method: 'POST', body: { path, recursive: isDir } });
    const data = await res.json();
    if (data.ok) { toast('Deleted', 'success'); loadDirectory(serial, currentPath); }
    else toast(`Delete failed: ${data.error}`, 'error');
    return;
  }
  if (action === 'rename') {
    const newName = prompt('New name:', path.split('/').pop());
    if (!newName) return;
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/files/rename`, { method: 'POST', body: { path, new_name: newName } });
    const data = await res.json();
    if (data.ok) { toast('Renamed', 'success'); loadDirectory(serial, currentPath); }
    else toast(`Rename failed: ${data.error}`, 'error');
    return;
  }
  if (action === 'move' || action === 'copy') {
    const dest = prompt(`Destination absolute path to ${action} to:`, currentPath);
    if (!dest) return;
    const endpoint = action === 'move' ? 'move' : 'copy';
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/files/${endpoint}`, { method: 'POST', body: { src: path, dest } });
    const data = await res.json();
    if (data.ok) { toast(action === 'move' ? 'Moved' : 'Copied', 'success'); loadDirectory(serial, currentPath); }
    else toast(`${action} failed: ${data.error}`, 'error');
  }
}

async function openPreview(serial, path) {
  const modal = document.getElementById('preview-modal');
  const body = document.getElementById('preview-body');
  body.innerHTML = 'Loading preview…';
  modal.style.display = 'flex';
  const url = `/api/devices/${encodeURIComponent(serial)}/files/preview?path=${encodeURIComponent(path)}`;
  try {
    const res = await fetch(url, { credentials: 'same-origin' });
    const contentType = res.headers.get('Content-Type') || '';
    if (contentType.startsWith('image/')) {
      body.innerHTML = `<img src="${url}" style="max-width:100%; max-height:70vh;">`;
      return;
    }
    const data = await res.json();
    if (!data.ok) { body.innerHTML = `<div class="alert error">${escapeHtml(data.error || 'Preview not supported for this file type')}</div>`; return; }
    body.innerHTML = `<pre class="shell-output">${escapeHtml(data.content)}</pre>${data.truncated ? '<div class="muted">Truncated preview…</div>' : ''}`;
  } catch (err) {
    body.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'files') renderFilesTab(); });
  onDeviceChange(() => { if (currentTab() === 'files') renderFilesTab(); });
});

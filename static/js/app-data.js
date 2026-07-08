// App Data Explorer tab: browse an app's private/public data dirs, preview
// files (text/JSON/shared_prefs/binary), query SQLite DBs, edit, and delete.

const APPDATA_STATE = { scope: 'private', path: '', pkg: null };

function renderAppDataTab() {
  const pane = document.getElementById('tab-app-data');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to browse app data.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="panel-page">
      <div class="panel-header">
        <h2>App Data Explorer</h2>
        <p class="muted">Browse an app's private (/data/data) and public (/sdcard/Android/data) storage. Private data needs a debuggable app (run-as) or a rooted device.</p>
      </div>
      <section class="panel-section">
        <div class="toolbar-row">
          <select id="appdata-package-select" style="flex:1;"><option>Loading packages…</option></select>
          <button id="appdata-browse-btn">Browse</button>
        </div>
        <div id="appdata-body" class="muted">Select a package and click Browse.</div>
      </section>
    </div>
  `;
  loadAppDataPackages(serial);
  document.getElementById('appdata-browse-btn').addEventListener('click', () => {
    const pkg = document.getElementById('appdata-package-select').value;
    if (!pkg) return;
    APPDATA_STATE.pkg = pkg;
    APPDATA_STATE.scope = 'private';
    APPDATA_STATE.path = '';
    renderAppDataOverview(serial, pkg);
  });
}

async function loadAppDataPackages(serial) {
  const select = document.getElementById('appdata-package-select');
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

async function renderAppDataOverview(serial, pkg) {
  const body = document.getElementById('appdata-body');
  body.innerHTML = 'Loading…';
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/data`);
    const data = await res.json();
    if (!data.ok) { body.innerHTML = `<div class="alert error">${escapeHtml(data.error)}</div>`; return; }
    body.innerHTML = `
      <div class="card-grid">
        <div class="card">
          <h4>Private (/data/data/${escapeHtml(pkg)})</h4>
          ${data.private.accessible
            ? `<button type="button" data-scope="private">Browse private data</button>`
            : `<div class="alert info">${escapeHtml(data.private.limitation || 'Not accessible')}</div>`}
        </div>
        <div class="card">
          <h4>Public (/sdcard/Android/data/${escapeHtml(pkg)})</h4>
          ${data.public.accessible
            ? `<button type="button" data-scope="public">Browse public data</button>`
            : `<div class="alert info">Not accessible or does not exist.</div>`}
        </div>
      </div>
      <div id="appdata-browser"></div>
    `;
    body.querySelectorAll('button[data-scope]').forEach((btn) => {
      btn.addEventListener('click', () => {
        APPDATA_STATE.scope = btn.dataset.scope;
        APPDATA_STATE.path = '';
        browseAppData(serial, pkg);
      });
    });
  } catch (err) {
    body.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

async function browseAppData(serial, pkg) {
  const browser = document.getElementById('appdata-browser');
  if (!browser) return;
  browser.innerHTML = 'Loading…';
  try {
    const qs = new URLSearchParams({ scope: APPDATA_STATE.scope, path: APPDATA_STATE.path });
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/data?${qs}`);
    const data = await res.json();
    if (!data.ok) { browser.innerHTML = `<div class="alert error">${escapeHtml(data.error || 'not accessible')}</div>`; return; }
    const crumbPath = data.path || '';
    const parts = crumbPath ? crumbPath.split('/') : [];
    const crumbs = [`<a href="#" data-path="">${escapeHtml(APPDATA_STATE.scope)}</a>`];
    let acc = '';
    parts.forEach((part) => { acc = acc ? `${acc}/${part}` : part; crumbs.push(`<a href="#" data-path="${escapeHtml(acc)}">${escapeHtml(part)}</a>`); });

    const rows = data.entries.map((e) => {
      const isDir = e.type === 'dir';
      const entryPath = crumbPath ? `${crumbPath}/${e.name}` : e.name;
      return `<tr>
        <td>${isDir ? '📁' : '📄'} ${isDir ? `<a href="#" data-open-dir="${escapeHtml(entryPath)}">${escapeHtml(e.name)}</a>` : escapeHtml(e.name)}</td>
        <td>${e.size == null ? '—' : formatBytes(e.size)}</td>
        <td>${escapeHtml(e.mtime || '—')}</td>
        <td>${isDir ? '' : `<button type="button" data-open-file="${escapeHtml(entryPath)}">Open</button>`}
            <button type="button" class="ghost-btn" data-delete-path="${escapeHtml(entryPath)}">Delete</button></td>
      </tr>`;
    }).join('') || `<tr><td colspan="4" class="muted">Empty directory</td></tr>`;

    browser.innerHTML = `
      <div class="breadcrumbs">${crumbs.join(' / ')}</div>
      <div class="table-wrap"><table><thead><tr><th>Name</th><th>Size</th><th>Modified</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      <div id="appdata-detail"></div>
    `;
    browser.querySelectorAll('a[data-path]').forEach((a) => a.addEventListener('click', (e) => {
      e.preventDefault(); APPDATA_STATE.path = a.dataset.path; browseAppData(serial, pkg);
    }));
    browser.querySelectorAll('a[data-open-dir]').forEach((a) => a.addEventListener('click', (e) => {
      e.preventDefault(); APPDATA_STATE.path = a.dataset.openDir; browseAppData(serial, pkg);
    }));
    browser.querySelectorAll('button[data-open-file]').forEach((btn) => btn.addEventListener('click', () => openAppDataFile(serial, pkg, btn.dataset.openFile)));
    browser.querySelectorAll('button[data-delete-path]').forEach((btn) => btn.addEventListener('click', () => deleteAppDataPath(serial, pkg, btn.dataset.deletePath)));
  } catch (err) {
    browser.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

async function deleteAppDataPath(serial, pkg, path) {
  if (!window.confirm(`Delete ${path}? This cannot be undone.`)) return;
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/data/delete`, {
      method: 'POST', body: { paths: [path], scope: APPDATA_STATE.scope },
    });
    const data = await res.json();
    toast(data.ok ? 'Deleted' : 'Delete failed', data.ok ? 'success' : 'error');
    browseAppData(serial, pkg);
  } catch (err) {
    toast(`Delete failed: ${err}`, 'error');
  }
}

async function openAppDataFile(serial, pkg, path) {
  const detail = document.getElementById('appdata-detail');
  if (!detail) return;
  detail.innerHTML = 'Loading…';
  const isDb = /\.(db|sqlite|sqlite3)$/i.test(path);
  if (isDb) {
    return renderAppDataDatabase(serial, pkg, path.split('/').pop());
  }
  try {
    const qs = new URLSearchParams({ path, scope: APPDATA_STATE.scope });
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/data/file?${qs}`);
    const data = await res.json();
    if (!data.ok) { detail.innerHTML = `<div class="alert error">${escapeHtml(data.error)}</div>`; return; }
    if (data.kind === 'binary') {
      detail.innerHTML = `<div class="card"><h4>${escapeHtml(path)}</h4><div class="muted">Binary file (${formatBytes(data.size)}), preview not supported.</div></div>`;
      return;
    }
    if (data.kind === 'shared_prefs' && data.parsed) {
      const rows = data.parsed.map((e) => `<tr>
        <td>${escapeHtml(e.key)}</td><td>${escapeHtml(e.type)}</td>
        <td><input type="text" data-key="${escapeHtml(e.key)}" data-type="${escapeHtml(e.type)}" value="${escapeHtml(Array.isArray(e.value) ? JSON.stringify(e.value) : String(e.value))}" ${e.type === 'set' ? 'disabled' : ''}></td>
        <td>${e.type === 'set' ? '' : `<button type="button" data-save-key="${escapeHtml(e.key)}">Save</button>`}</td>
      </tr>`).join('');
      detail.innerHTML = `
        <div class="card">
          <h4>${escapeHtml(path)} (SharedPreferences)</h4>
          <div class="table-wrap"><table><thead><tr><th>Key</th><th>Type</th><th>Value</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
        </div>`;
      detail.querySelectorAll('button[data-save-key]').forEach((btn) => btn.addEventListener('click', async () => {
        const key = btn.dataset.saveKey;
        const input = detail.querySelector(`input[data-key="${CSS.escape(key)}"]`);
        try {
          const res2 = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/data/edit`, {
            method: 'POST', body: { path, scope: APPDATA_STATE.scope, key, value: input.value, value_type: input.dataset.type },
          });
          const d2 = await res2.json();
          toast(d2.ok ? 'Saved' : `Save failed: ${d2.error}`, d2.ok ? 'success' : 'error');
        } catch (err) {
          toast(`Save failed: ${err}`, 'error');
        }
      }));
      return;
    }
    detail.innerHTML = `
      <div class="card">
        <h4>${escapeHtml(path)}</h4>
        <textarea id="appdata-edit-textarea" rows="16" style="width:100%;font-family:monospace;">${escapeHtml(data.content)}</textarea>
        <div class="toolbar-row"><button id="appdata-save-file-btn">Save</button></div>
      </div>`;
    document.getElementById('appdata-save-file-btn').addEventListener('click', async () => {
      const content = document.getElementById('appdata-edit-textarea').value;
      try {
        const res2 = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/data/edit`, {
          method: 'POST', body: { path, scope: APPDATA_STATE.scope, content },
        });
        const d2 = await res2.json();
        toast(d2.ok ? 'Saved' : `Save failed: ${d2.error}`, d2.ok ? 'success' : 'error');
      } catch (err) {
        toast(`Save failed: ${err}`, 'error');
      }
    });
  } catch (err) {
    detail.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

async function renderAppDataDatabase(serial, pkg, dbName) {
  const detail = document.getElementById('appdata-detail');
  detail.innerHTML = 'Loading database…';
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/data/databases?db=${encodeURIComponent(dbName)}`);
    const data = await res.json();
    if (!data.ok) { detail.innerHTML = `<div class="alert error">${escapeHtml(data.error)}</div>`; return; }
    detail.innerHTML = `
      <div class="card">
        <h4>${escapeHtml(dbName)}</h4>
        <div class="muted">Tables: ${data.tables.map(escapeHtml).join(', ') || 'none'}</div>
        <div class="toolbar-row">
          <input type="text" id="appdata-sql-input" placeholder="SELECT * FROM table_name" style="flex:1;font-family:monospace;">
          <button id="appdata-sql-run-btn">Run query</button>
        </div>
        <div id="appdata-sql-result"></div>
      </div>`;
    document.getElementById('appdata-sql-run-btn').addEventListener('click', async () => {
      const query = document.getElementById('appdata-sql-input').value;
      const resultEl = document.getElementById('appdata-sql-result');
      resultEl.innerHTML = 'Running…';
      try {
        const qs = new URLSearchParams({ db: dbName, query });
        const res2 = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/data/databases?${qs}`);
        const d2 = await res2.json();
        if (!d2.ok) { resultEl.innerHTML = `<div class="alert error">${escapeHtml(d2.error)}</div>`; return; }
        const head = d2.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join('');
        const rows = d2.rows.map((row) => `<tr>${d2.columns.map((c) => `<td>${escapeHtml(String(row[c]))}</td>`).join('')}</tr>`).join('')
          || `<tr><td colspan="${d2.columns.length || 1}" class="muted">No rows</td></tr>`;
        resultEl.innerHTML = `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
      } catch (err) {
        resultEl.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
      }
    });
  } catch (err) {
    detail.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'app-data') renderAppDataTab(); });
  onDeviceChange(() => { if (currentTab() === 'app-data') renderAppDataTab(); });
});

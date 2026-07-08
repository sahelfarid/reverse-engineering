// Frida tab: provision frida-server, attach/spawn targets, and stream script output.

Object.assign(TIP_REGISTRY, {
  'frida.warning': {
    title: 'Authorized testing only',
    body: '<p>Run Frida only against your own devices and apps, or those you have explicit permission to test.</p>',
  },
});

let FRIDA_STATUS = null;
let FRIDA_PROCESSES = [];
let FRIDA_SELECTED_PID = null;
let FRIDA_SPAWN_PACKAGE = '';
let fridaSource = null;
let fridaSessionId = null;

function selectedFridaDeviceStatus(serial) {
  return FRIDA_STATUS && (FRIDA_STATUS.devices || []).find((d) => d.serial === serial);
}

function renderFridaTab() {
  const pane = document.getElementById('tab-frida');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device for Frida instrumentation.</div>`;
    return;
  }
  FRIDA_SELECTED_PID = null;
  pane.innerHTML = `
    <div class="panel-page">
      <div class="panel-header">
        <h2>Frida</h2>
        <p class="muted">
          Provision frida-server, attach or spawn a target, and run a script against it.
          <button type="button" class="tip-btn" data-tip-key="frida.warning" aria-label="Help">?</button>
        </p>
      </div>
      <section class="panel-section subnav-pinned">
        <div class="section-head">
          <div><h3>Live console</h3></div>
          <button id="frida-detach-btn" disabled>Detach</button>
        </div>
        <pre id="frida-console" class="shell-output"></pre>
        <div class="toolbar-row" style="margin-top:8px;">
          <button id="frida-rpc-refresh-btn" disabled title="List the attached script's rpc.exports">Load exports</button>
          <select id="frida-rpc-select" disabled></select>
          <input type="text" id="frida-rpc-args" placeholder='args JSON, e.g. [1, "x"]' disabled style="flex:1; min-width:160px;">
          <button id="frida-rpc-call-btn" disabled>Call</button>
        </div>
        <div class="toolbar-row" style="margin-top:6px;">
          <input type="text" id="frida-post-input" placeholder='send to script (JSON or text), delivered to recv()' disabled style="flex:1; min-width:200px;">
          <button id="frida-post-btn" disabled>Send</button>
        </div>
      </section>
      <div id="frida-subnav"></div>
    </div>
  `;
  document.getElementById('frida-detach-btn').addEventListener('click', detachFrida);
  document.getElementById('frida-rpc-refresh-btn').addEventListener('click', loadFridaExports);
  document.getElementById('frida-rpc-call-btn').addEventListener('click', callFridaExport);
  document.getElementById('frida-post-btn').addEventListener('click', postFridaMessage);
  createSubNav(document.getElementById('frida-subnav'), 'adbpanel.subnav.frida', [
    { key: 'status', label: 'Status', render: (body) => renderFridaStatusView(body, serial) },
    { key: 'target', label: 'Target', render: (body) => renderFridaTargetView(body, serial) },
    { key: 'script', label: 'Script', render: (body) => renderFridaScriptView(body, serial) },
  ]);
}

function renderFridaStatusView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <div id="frida-status-card" class="muted">Checking Frida status...</div>
      <div class="toolbar-row" style="margin-top:10px;">
        <button id="frida-refresh-btn">Refresh</button>
        <button id="frida-push-btn">Push server</button>
        <button id="frida-start-btn">Start server</button>
        <button id="frida-stop-btn">Stop server</button>
      </div>
    </section>`;
  document.getElementById('frida-refresh-btn').addEventListener('click', () => refreshFridaStatus(serial));
  document.getElementById('frida-push-btn').addEventListener('click', () => fridaServerAction(serial, 'push'));
  document.getElementById('frida-start-btn').addEventListener('click', () => fridaServerAction(serial, 'start'));
  document.getElementById('frida-stop-btn').addEventListener('click', () => fridaServerAction(serial, 'stop'));
  refreshFridaStatus(serial);
}

let FRIDA_TARGET_MODE = 'processes';
let FRIDA_APPLICATIONS = [];

function renderFridaTargetView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <div class="toolbar-row">
        <div class="btn-group" role="tablist">
          <button id="frida-mode-processes" class="${FRIDA_TARGET_MODE === 'processes' ? 'active' : ''}">Processes</button>
          <button id="frida-mode-apps" class="${FRIDA_TARGET_MODE === 'apps' ? 'active' : ''}">Applications</button>
        </div>
        <input type="text" id="frida-process-filter" placeholder="Filter..." style="flex:1; min-width:160px;">
        <button id="frida-process-refresh-btn">Refresh</button>
        <button id="frida-frontmost-btn" title="Select the app currently in the foreground">Frontmost</button>
      </div>
      <div class="table-wrap auto-height">
        <table>
          <thead id="frida-target-head"></thead>
          <tbody id="frida-process-body"><tr><td colspan="4">Loading...</td></tr></tbody>
        </table>
      </div>
      <div class="section-head" style="margin-top:14px;">
        <div><h3>Spawn gating</h3><p class="section-desc">Suspend every newly launched process so you can attach before it runs.</p></div>
      </div>
      <div class="toolbar-row">
        <button id="frida-gating-enable-btn">Enable gating</button>
        <button id="frida-gating-disable-btn">Disable gating</button>
        <button id="frida-pending-refresh-btn">Refresh pending</button>
      </div>
      <div class="table-wrap auto-height">
        <table>
          <thead><tr><th>PID</th><th>Identifier</th><th>Action</th></tr></thead>
          <tbody id="frida-pending-body"><tr><td colspan="3" class="muted">Enable gating, then launch the target app.</td></tr></tbody>
        </table>
      </div>
    </section>`;
  document.getElementById('frida-mode-processes').addEventListener('click', () => setFridaTargetMode(serial, 'processes'));
  document.getElementById('frida-mode-apps').addEventListener('click', () => setFridaTargetMode(serial, 'apps'));
  document.getElementById('frida-process-refresh-btn').addEventListener('click', () => reloadFridaTarget(serial));
  document.getElementById('frida-frontmost-btn').addEventListener('click', () => selectFridaFrontmost(serial));
  document.getElementById('frida-process-filter').addEventListener('input', renderFridaTargetTable);
  document.getElementById('frida-gating-enable-btn').addEventListener('click', () => setFridaSpawnGating(serial, true));
  document.getElementById('frida-gating-disable-btn').addEventListener('click', () => setFridaSpawnGating(serial, false));
  document.getElementById('frida-pending-refresh-btn').addEventListener('click', () => loadFridaPendingSpawn(serial));
  reloadFridaTarget(serial);
}

async function setFridaSpawnGating(serial, enable) {
  const action = enable ? 'enable' : 'disable';
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/spawn-gating/${action}`, { method: 'POST' });
  const data = await res.json();
  toast(data.ok ? `Spawn gating ${action}d` : `Gating ${action} failed: ${data.error}`, data.ok ? 'success' : 'error');
  if (data.ok && enable) loadFridaPendingSpawn(serial);
}

async function loadFridaPendingSpawn(serial) {
  const body = document.getElementById('frida-pending-body');
  if (body) body.innerHTML = `<tr><td colspan="3">Loading...</td></tr>`;
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/pending-spawn`);
    const data = await res.json();
    if (!data.ok) { if (body) body.innerHTML = `<tr><td colspan="3" class="muted">${escapeHtml(data.error || 'failed')}</td></tr>`; return; }
    const rows = data.pending || [];
    if (!rows.length) { body.innerHTML = `<tr><td colspan="3" class="muted">No pending spawns</td></tr>`; return; }
    body.innerHTML = rows.map((s) => `
      <tr>
        <td>${s.pid}</td>
        <td>${escapeHtml(s.identifier || '-')}</td>
        <td>
          <button data-frida-resume="${s.pid}" title="Resume so it runs normally">Resume</button>
          <button data-frida-kill="${s.pid}" title="Kill the suspended process">Kill</button>
        </td>
      </tr>`).join('');
    body.querySelectorAll('button[data-frida-resume]').forEach((btn) => {
      btn.addEventListener('click', () => fridaPidAction(serial, 'resume', btn.dataset.fridaResume));
    });
    body.querySelectorAll('button[data-frida-kill]').forEach((btn) => {
      btn.addEventListener('click', () => fridaPidAction(serial, 'kill', btn.dataset.fridaKill));
    });
  } catch (err) {
    if (body) body.innerHTML = `<tr><td colspan="3">${escapeHtml(String(err))}</td></tr>`;
  }
}

async function fridaPidAction(serial, action, pid) {
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/${action}/${encodeURIComponent(pid)}`, { method: 'POST' });
  const data = await res.json();
  toast(data.ok ? `${action} pid ${pid} ok` : `${action} failed: ${data.error}`, data.ok ? 'success' : 'error');
  loadFridaPendingSpawn(serial);
  if (FRIDA_TARGET_MODE === 'processes') loadFridaProcesses(serial);
}

function setFridaTargetMode(serial, mode) {
  if (FRIDA_TARGET_MODE === mode) return;
  FRIDA_TARGET_MODE = mode;
  document.getElementById('frida-mode-processes').classList.toggle('active', mode === 'processes');
  document.getElementById('frida-mode-apps').classList.toggle('active', mode === 'apps');
  reloadFridaTarget(serial);
}

function reloadFridaTarget(serial) {
  if (FRIDA_TARGET_MODE === 'apps') loadFridaApplications(serial);
  else loadFridaProcesses(serial);
}

function renderFridaTargetTable() {
  if (FRIDA_TARGET_MODE === 'apps') renderFridaAppTable();
  else renderFridaProcessTable();
}

function renderFridaScriptView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <div class="toolbar-row">
        <select id="frida-script-select"></select>
        <input type="text" id="frida-script-name" placeholder="Script name" style="width:180px;">
        <button id="frida-load-script-btn">Load</button>
        <button id="frida-save-script-btn">Save</button>
        <button id="frida-delete-script-btn">Delete</button>
      </div>
      <textarea id="frida-script-editor" spellcheck="false" style="width:100%; min-height:280px; font-family:Consolas, monospace;"></textarea>
      <div class="section-head" style="margin-top:14px;">
        <div><h3>Attach</h3><p class="section-desc">Attach to the process selected on the Target tab, or spawn a fresh package.</p></div>
      </div>
      <div class="toolbar-row">
        <button id="frida-attach-selected-btn">Attach selected (${escapeHtml(String(FRIDA_SELECTED_PID || '—'))})</button>
        <input type="text" id="frida-spawn-package" placeholder="Spawn by package name" value="${escapeHtml(FRIDA_SPAWN_PACKAGE)}" style="flex:1; min-width:200px;">
        <button id="frida-spawn-btn">Spawn + attach</button>
      </div>
    </section>`;
  document.getElementById('frida-load-script-btn').addEventListener('click', loadSelectedFridaScript);
  document.getElementById('frida-save-script-btn').addEventListener('click', saveFridaScript);
  document.getElementById('frida-delete-script-btn').addEventListener('click', deleteFridaScript);
  document.getElementById('frida-attach-selected-btn').addEventListener('click', () => attachFrida(serial));
  document.getElementById('frida-spawn-btn').addEventListener('click', () => attachFrida(serial, true));
  loadFridaScripts();
}

function setFridaConsole(text, append = false, type = 'info') {
  const out = document.getElementById('frida-console');
  if (!out) return;
  if (!append) out.innerHTML = '';
  const line = document.createElement('div');
  const colors = {
    send: '#35c46a', error: '#e0563d', info: '#d8dee9', message: '#4f8cff',
    log: '#d8dee9', warning: '#e0b341', warn: '#e0b341', debug: '#8b949e',
  };
  line.style.color = colors[type] || colors.info;
  line.textContent = text;
  out.appendChild(line);
  out.scrollTop = out.scrollHeight;
}

async function refreshFridaStatus(serial) {
  const card = document.getElementById('frida-status-card');
  try {
    const res = await apiFetch('/api/frida/status');
    FRIDA_STATUS = await res.json();
    const ds = selectedFridaDeviceStatus(serial);
    if (!FRIDA_STATUS.python_installed) {
      card.innerHTML = `<span class="badge red">Python package missing</span> Install dependencies with requirements.txt.`;
    } else if (!ds) {
      card.innerHTML = `<span class="badge yellow">No device detail</span> Frida ${escapeHtml(FRIDA_STATUS.python_version || '')}`;
    } else if (ds.error) {
      card.innerHTML = `<span class="badge red">Error</span> ${escapeHtml(ds.error)}`;
    } else {
      const versionBadge = ds.server_pushed && ds.version_match === false
        ? `<span class="badge red" title="frida-server ${escapeHtml(ds.server_version || '?')} is incompatible with the installed Python frida ${escapeHtml(FRIDA_STATUS.python_version || '')}. Push server to fix.">version mismatch: server ${escapeHtml(ds.server_version || '?')}</span>`
        : (ds.server_version ? `<span class="badge green">server ${escapeHtml(ds.server_version)}</span>` : '');
      card.innerHTML = `
        <span class="badge green">Frida ${escapeHtml(FRIDA_STATUS.python_version || '')}</span>
        ${versionBadge}
        ABI ${escapeHtml(ds.abi || '-')} | root ${ds.root_available ? 'yes' : 'no'} | cached ${ds.server_cached ? 'yes' : 'no'} | pushed ${ds.server_pushed ? 'yes' : 'no'} | running ${ds.server_running ? 'yes' : 'no'}
      `;
    }
    const rootOk = Boolean(ds && ds.root_available && FRIDA_STATUS.python_installed);
    ['frida-push-btn', 'frida-start-btn', 'frida-stop-btn'].forEach((id) => {
      const btn = document.getElementById(id);
      if (btn) {
        btn.disabled = !rootOk;
        btn.title = rootOk ? '' : 'Classic frida-server requires a rooted device and the Python frida package.';
      }
    });
  } catch (err) {
    if (card) card.innerHTML = `<span class="badge red">Error</span> ${escapeHtml(String(err))}`;
  }
}

async function fridaServerAction(serial, action) {
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/server/${action}`, { method: 'POST' });
  const data = await res.json();
  toast(data.ok ? `Frida server ${action} complete` : `Frida ${action} failed: ${data.error}`, data.ok ? 'success' : 'error');
  refreshFridaStatus(serial);
}

async function loadFridaProcesses(serial) {
  const body = document.getElementById('frida-process-body');
  if (body) body.innerHTML = `<tr><td colspan="3">Loading...</td></tr>`;
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/processes`);
    const data = await res.json();
    FRIDA_PROCESSES = data.processes || [];
    renderFridaProcessTable();
  } catch (err) {
    if (body) body.innerHTML = `<tr><td colspan="3">${escapeHtml(String(err))}</td></tr>`;
  }
}

function renderFridaProcessTable() {
  const head = document.getElementById('frida-target-head');
  if (head) head.innerHTML = `<tr><th>PID</th><th>Name</th><th>Action</th></tr>`;
  const body = document.getElementById('frida-process-body');
  if (!body) return;
  const filter = (document.getElementById('frida-process-filter').value || '').toLowerCase();
  const rows = FRIDA_PROCESSES.filter((p) => !filter || String(p.pid).includes(filter) || (p.name || '').toLowerCase().includes(filter)).slice(0, 300);
  if (!rows.length) { body.innerHTML = `<tr><td colspan="3" class="muted">No matching processes</td></tr>`; return; }
  body.innerHTML = rows.map((p) => `
    <tr>
      <td>${p.pid ?? '-'}</td>
      <td>${escapeHtml(p.name || '-')}</td>
      <td>
        <button data-frida-pid="${p.pid}">Select</button>
        <button data-frida-killproc="${p.pid}" title="Kill this process">Kill</button>
      </td>
    </tr>
  `).join('');
  body.querySelectorAll('button[data-frida-pid]').forEach((btn) => {
    btn.addEventListener('click', () => selectFridaPid(btn.dataset.fridaPid, btn));
  });
  body.querySelectorAll('button[data-frida-killproc]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const serial = getSelectedSerial();
      if (serial && confirm(`Kill PID ${btn.dataset.fridaKillproc}?`)) fridaPidAction(serial, 'kill', btn.dataset.fridaKillproc);
    });
  });
}

function selectFridaPid(pid, btn) {
  document.querySelectorAll('button[data-frida-pid], button[data-frida-app-pid]').forEach((b) => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  FRIDA_SELECTED_PID = pid;
  toast(`Selected PID ${pid} — switch to the Script tab to attach`, 'info', 2500);
}

async function loadFridaApplications(serial) {
  const body = document.getElementById('frida-process-body');
  if (body) body.innerHTML = `<tr><td colspan="4">Loading applications...</td></tr>`;
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/applications`);
    const data = await res.json();
    if (!data.ok) { if (body) body.innerHTML = `<tr><td colspan="4" class="muted">${escapeHtml(data.error || 'failed')}</td></tr>`; return; }
    FRIDA_APPLICATIONS = data.applications || [];
    renderFridaAppTable();
  } catch (err) {
    if (body) body.innerHTML = `<tr><td colspan="4">${escapeHtml(String(err))}</td></tr>`;
  }
}

function renderFridaAppTable() {
  const head = document.getElementById('frida-target-head');
  if (head) head.innerHTML = `<tr><th>Identifier</th><th>Name</th><th>State</th><th>Action</th></tr>`;
  const body = document.getElementById('frida-process-body');
  if (!body) return;
  const filter = (document.getElementById('frida-process-filter').value || '').toLowerCase();
  const rows = FRIDA_APPLICATIONS.filter((a) => !filter
    || (a.identifier || '').toLowerCase().includes(filter)
    || (a.name || '').toLowerCase().includes(filter)).slice(0, 500);
  if (!rows.length) { body.innerHTML = `<tr><td colspan="4" class="muted">No matching applications</td></tr>`; return; }
  body.innerHTML = rows.map((a) => `
    <tr>
      <td>${escapeHtml(a.identifier || '-')}</td>
      <td>${escapeHtml(a.name || '-')}</td>
      <td>${a.running ? `<span class="badge green">running ${a.pid}</span>` : '<span class="muted">stopped</span>'}</td>
      <td>${a.running
        ? `<button data-frida-app-pid="${a.pid}">Attach</button>`
        : `<button data-frida-spawn="${escapeHtml(a.identifier || '')}">Spawn</button>`}</td>
    </tr>
  `).join('');
  body.querySelectorAll('button[data-frida-app-pid]').forEach((btn) => {
    btn.addEventListener('click', () => selectFridaPid(btn.dataset.fridaAppPid, btn));
  });
  body.querySelectorAll('button[data-frida-spawn]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const pkg = btn.dataset.fridaSpawn;
      FRIDA_SPAWN_PACKAGE = pkg;
      toast(`Spawn target set to ${pkg} — switch to the Script tab and press Spawn + attach`, 'info', 3000);
    });
  });
}

async function selectFridaFrontmost(serial) {
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/frontmost`);
    const data = await res.json();
    if (!data.ok) { toast(`Frontmost failed: ${data.error}`, 'error'); return; }
    const app = data.application;
    if (!app) { toast('No app is currently in the foreground', 'info'); return; }
    if (app.running && app.pid) {
      FRIDA_SELECTED_PID = String(app.pid);
      toast(`Foreground app ${app.identifier} (PID ${app.pid}) selected — switch to the Script tab`, 'success', 3000);
    } else {
      FRIDA_SPAWN_PACKAGE = app.identifier;
      toast(`Foreground app ${app.identifier} set as spawn target`, 'success', 3000);
    }
  } catch (err) {
    toast(String(err), 'error');
  }
}

async function loadFridaScripts() {
  const select = document.getElementById('frida-script-select');
  const res = await apiFetch('/api/frida/scripts');
  const data = await res.json();
  window.FRIDA_SCRIPTS = data.scripts || {};
  const names = Object.keys(window.FRIDA_SCRIPTS);
  select.innerHTML = names.map((name) => {
    const s = window.FRIDA_SCRIPTS[name];
    return `<option value="${escapeHtml(name)}">${escapeHtml(name)}${s.readonly ? ' (template)' : ''}</option>`;
  }).join('');
  if (names.length) loadSelectedFridaScript();
}

function loadSelectedFridaScript() {
  const name = document.getElementById('frida-script-select').value;
  const script = window.FRIDA_SCRIPTS && window.FRIDA_SCRIPTS[name];
  if (!script) return;
  document.getElementById('frida-script-name').value = script.readonly ? '' : name;
  document.getElementById('frida-script-editor').value = script.source || '';
}

async function saveFridaScript() {
  const name = document.getElementById('frida-script-name').value.trim();
  const source = document.getElementById('frida-script-editor').value;
  if (!name || !source) return;
  const res = await apiFetch('/api/frida/scripts', { method: 'POST', body: { name, source } });
  const data = await res.json();
  toast(data.ok ? 'Script saved' : `Save failed: ${data.error}`, data.ok ? 'success' : 'error');
  if (data.ok) loadFridaScripts();
}

async function deleteFridaScript() {
  const name = document.getElementById('frida-script-select').value;
  if (!name || !confirm(`Delete script ${name}?`)) return;
  const res = await apiFetch(`/api/frida/scripts/${encodeURIComponent(name)}`, { method: 'DELETE' });
  const data = await res.json();
  toast(data.ok ? 'Script deleted' : `Delete failed: ${data.error}`, data.ok ? 'success' : 'error');
  if (data.ok) loadFridaScripts();
}

async function attachFrida(serial, spawn = false) {
  const source = document.getElementById('frida-script-editor').value;
  const body = { script_source: source };
  if (spawn) {
    const pkg = document.getElementById('frida-spawn-package').value.trim();
    if (!pkg) { toast('Enter a package name to spawn', 'error'); return; }
    body.spawn = pkg;
  } else {
    if (!FRIDA_SELECTED_PID) { toast('Select a running process on the Target tab first', 'error'); return; }
    body.target = FRIDA_SELECTED_PID;
  }
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/attach`, { method: 'POST', body });
  const data = await res.json();
  if (!data.ok) { toast(`Attach failed: ${data.error}`, 'error'); return; }
  fridaSessionId = data.session_id;
  document.getElementById('frida-detach-btn').disabled = false;
  ['frida-rpc-refresh-btn', 'frida-post-input', 'frida-post-btn'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = false;
  });
  setFridaConsole(`Attached session ${fridaSessionId}`);
  startFridaStream(fridaSessionId);
}

function setFridaRpcDisabled(disabled) {
  ['frida-rpc-refresh-btn', 'frida-rpc-select', 'frida-rpc-args', 'frida-rpc-call-btn',
   'frida-post-input', 'frida-post-btn'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = disabled;
  });
}

async function postFridaMessage() {
  if (!fridaSessionId) return;
  const input = document.getElementById('frida-post-input');
  const raw = input.value.trim();
  if (!raw) return;
  let message;
  try { message = JSON.parse(raw); } catch (e) { message = raw; }  // fall back to plain string
  setFridaConsole(`post: ${raw}`, true, 'send');
  try {
    const res = await apiFetch(`/api/frida/sessions/${encodeURIComponent(fridaSessionId)}/post`,
      { method: 'POST', body: { message } });
    const data = await res.json();
    if (!data.ok) { setFridaConsole(`post error: ${data.error}`, true, 'error'); return; }
    input.value = '';
  } catch (err) {
    setFridaConsole(`post error: ${String(err)}`, true, 'error');
  }
}

async function loadFridaExports() {
  if (!fridaSessionId) return;
  const select = document.getElementById('frida-rpc-select');
  try {
    const res = await apiFetch(`/api/frida/sessions/${encodeURIComponent(fridaSessionId)}/exports`);
    const data = await res.json();
    if (!data.ok) { toast(`Load exports failed: ${data.error}`, 'error'); return; }
    const names = data.exports || [];
    if (!names.length) { setFridaConsole('No rpc.exports defined in this script', true, 'info'); return; }
    select.innerHTML = names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join('');
    select.disabled = false;
    document.getElementById('frida-rpc-args').disabled = false;
    document.getElementById('frida-rpc-call-btn').disabled = false;
    setFridaConsole(`Loaded ${names.length} export(s): ${names.join(', ')}`, true, 'info');
  } catch (err) {
    toast(String(err), 'error');
  }
}

async function callFridaExport() {
  if (!fridaSessionId) return;
  const name = document.getElementById('frida-rpc-select').value;
  const argsText = document.getElementById('frida-rpc-args').value.trim();
  let args = [];
  if (argsText) {
    try {
      args = JSON.parse(argsText);
      if (!Array.isArray(args)) { toast('Args must be a JSON array', 'error'); return; }
    } catch (e) { toast('Args must be valid JSON array', 'error'); return; }
  }
  setFridaConsole(`rpc: ${name}(${argsText || ''})`, true, 'send');
  try {
    const res = await apiFetch(`/api/frida/sessions/${encodeURIComponent(fridaSessionId)}/exports/${encodeURIComponent(name)}`,
      { method: 'POST', body: { args } });
    const data = await res.json();
    if (!data.ok) { setFridaConsole(`rpc error: ${data.error}`, true, 'error'); return; }
    setFridaConsole(`rpc => ${JSON.stringify(data.result)}`, true, 'message');
  } catch (err) {
    setFridaConsole(`rpc error: ${String(err)}`, true, 'error');
  }
}

function startFridaStream(sessionId) {
  if (fridaSource) fridaSource.close();
  fridaSource = new EventSource(`/api/frida/sessions/${encodeURIComponent(sessionId)}/stream`);
  fridaSource.onmessage = (event) => {
    const entry = JSON.parse(event.data);
    const msg = entry.message || {};
    if (msg.type === 'heartbeat') return;
    if (msg.type === 'detached') {
      const crash = msg.crash ? ` (crash: ${escapeHtml(msg.crash.summary || msg.crash.process_name || '')})` : '';
      setFridaConsole(`session detached: ${msg.reason || 'unknown reason'}${crash}`, true, 'error');
      if (fridaSource) { fridaSource.close(); fridaSource = null; }
      fridaSessionId = null;
      const btn = document.getElementById('frida-detach-btn');
      if (btn) btn.disabled = true;
      setFridaRpcDisabled(true);
      return;
    }
    if (msg.type === 'log') {
      const level = (msg.level || 'info').toLowerCase();
      const label = level === 'warning' ? 'warn' : level;
      setFridaConsole(`${label}: ${msg.payload ?? ''}`, true, label === 'error' ? 'error' : label);
    } else if (msg.type === 'send') setFridaConsole(`send: ${JSON.stringify(msg.payload)}`, true, 'send');
    else if (msg.type === 'error') setFridaConsole(`error: ${msg.description || JSON.stringify(msg)}`, true, 'error');
    else setFridaConsole(`${msg.type || 'message'}: ${JSON.stringify(msg)}`, true, 'message');
  };
}

async function detachFrida() {
  if (!fridaSessionId) return;
  const id = fridaSessionId;
  if (fridaSource) { fridaSource.close(); fridaSource = null; }
  fridaSessionId = null;
  document.getElementById('frida-detach-btn').disabled = true;
  setFridaRpcDisabled(true);
  const res = await apiFetch(`/api/frida/sessions/${encodeURIComponent(id)}/detach`, { method: 'POST' });
  const data = await res.json();
  toast(data.ok ? 'Detached' : `Detach failed: ${data.error}`, data.ok ? 'success' : 'error');
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => {
    if (tab === 'frida') renderFridaTab();
    else if (fridaSource) { fridaSource.close(); fridaSource = null; }
  });
  onDeviceChange(() => { if (currentTab() === 'frida') renderFridaTab(); });
});

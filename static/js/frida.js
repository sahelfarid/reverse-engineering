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
let FRIDA_TARGET_MODE = 'processes';
let FRIDA_APPLICATIONS = [];
let FRIDA_SESSIONS = [];
let FRIDA_EVENT_LOG = []; // client-side ring of device events for the Events panel
let FRIDA_BINARIES = []; // { id, hex, label, ts } binary side-channel payloads
let fridaSource = null;
let fridaSessionId = null;
let fridaSessionPollTimer = null;
let fridaDeviceEventTimer = null;
let fridaDeviceEventAfter = 0;
let fridaDeviceEventSerial = null;
let fridaBinarySeq = 0;

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
          <label class="muted" for="frida-session-select" title="Switch among concurrent sessions">Session</label>
          <select id="frida-session-select" title="Active session" style="min-width:160px;"></select>
          <button id="frida-sessions-refresh-btn" title="Refresh session list">Sessions</button>
          <button id="frida-export-txt-btn" title="Download console log as text">Export .txt</button>
          <button id="frida-export-json-btn" title="Download console log as JSON">Export .json</button>
          <button id="frida-export-bin-btn" title="Download binary data payloads from this session">Export binaries</button>
          <button id="frida-interrupt-btn" disabled title="Interrupt the script's current execution (it can continue)">Interrupt</button>
          <button id="frida-terminate-btn" disabled title="Force-terminate a runaway script and drop the session">Terminate</button>
          <button id="frida-eternalize-btn" disabled title="Leave the script running after disconnect (fire-and-forget)">Eternalize</button>
          <button id="frida-detach-btn" disabled>Detach</button>
        </div>
        <div id="frida-session-meta" class="muted" style="margin:4px 0 6px;"></div>
        <pre id="frida-console" class="shell-output"></pre>
        <div id="frida-binary-list" class="muted" style="margin-top:6px; font-size:0.9em;"></div>
        <div class="toolbar-row" style="margin-top:8px;">
          <button id="frida-rpc-refresh-btn" disabled title="List the attached script's rpc.exports">Load exports</button>
          <select id="frida-rpc-select" disabled></select>
          <input type="text" id="frida-rpc-args" placeholder='args JSON, e.g. [1, "x"]' disabled style="flex:1; min-width:160px;">
          <button id="frida-rpc-call-btn" disabled>Call</button>
        </div>
        <div class="toolbar-row" style="margin-top:6px;">
          <input type="text" id="frida-post-input" placeholder='message to script (JSON or text) → recv()' disabled style="flex:1; min-width:160px;">
          <input type="text" id="frida-post-data" placeholder="optional binary data (hex)" disabled style="flex:1; min-width:140px;" title="Hex side-channel delivered as the binary data of script.post()">
          <button id="frida-post-btn" disabled>Send</button>
        </div>
        <div class="toolbar-row" style="margin-top:6px;">
          <button id="frida-childgate-on-btn" disabled title="Follow fork()/exec() children (suspends them for inspection)">Child gating on</button>
          <button id="frida-childgate-off-btn" disabled title="Stop following children">Child gating off</button>
        </div>
      </section>
      <div id="frida-subnav"></div>
    </div>
  `;
  document.getElementById('frida-detach-btn').addEventListener('click', detachFrida);
  document.getElementById('frida-eternalize-btn').addEventListener('click', eternalizeFrida);
  document.getElementById('frida-rpc-refresh-btn').addEventListener('click', loadFridaExports);
  document.getElementById('frida-rpc-call-btn').addEventListener('click', callFridaExport);
  document.getElementById('frida-post-btn').addEventListener('click', postFridaMessage);
  document.getElementById('frida-childgate-on-btn').addEventListener('click', () => setFridaChildGating(true));
  document.getElementById('frida-childgate-off-btn').addEventListener('click', () => setFridaChildGating(false));
  document.getElementById('frida-interrupt-btn').addEventListener('click', interruptFridaScript);
  document.getElementById('frida-terminate-btn').addEventListener('click', terminateFridaScript);
  document.getElementById('frida-export-txt-btn').addEventListener('click', () => exportFridaConsole('text'));
  document.getElementById('frida-export-json-btn').addEventListener('click', () => exportFridaConsole('json'));
  document.getElementById('frida-export-bin-btn').addEventListener('click', exportFridaBinaries);
  document.getElementById('frida-sessions-refresh-btn').addEventListener('click', () => refreshFridaSessionsList(true));
  document.getElementById('frida-session-select').addEventListener('change', onFridaSessionSelect);
  createSubNav(document.getElementById('frida-subnav'), 'adbpanel.subnav.frida', [
    { key: 'status', label: 'Status', render: (body) => renderFridaStatusView(body, serial) },
    { key: 'target', label: 'Target', render: (body) => renderFridaTargetView(body, serial) },
    { key: 'script', label: 'Script', render: (body) => renderFridaScriptView(body, serial) },
  ]);
  startFridaDeviceEventPoll(serial);
  refreshFridaSessionsList(false);
  if (fridaSessionId) enableFridaSessionControls(true);
  renderFridaBinaryList();
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
        <button id="frida-sysinfo-btn" title="Device details Frida reports (os, arch, access)">Device info</button>
      </div>
      <div id="frida-sysinfo" style="display:none; margin-top:10px;"></div>
    </section>`;
  document.getElementById('frida-refresh-btn').addEventListener('click', () => refreshFridaStatus(serial));
  document.getElementById('frida-push-btn').addEventListener('click', () => fridaServerAction(serial, 'push'));
  document.getElementById('frida-start-btn').addEventListener('click', () => fridaServerAction(serial, 'start'));
  document.getElementById('frida-stop-btn').addEventListener('click', () => fridaServerAction(serial, 'stop'));
  document.getElementById('frida-sysinfo-btn').addEventListener('click', () => loadFridaSystemInfo(serial));
  refreshFridaStatus(serial);
}

function renderKeyValueTable(obj, preferKeys) {
  if (!obj || typeof obj !== 'object') return '<p class="muted">No data</p>';
  const rows = [];
  const seen = new Set();
  const add = (k, v) => {
    seen.add(k);
    let display;
    if (v === null || v === undefined) display = '—';
    else if (typeof v === 'object') display = `<pre class="shell-output" style="margin:0; max-height:120px;">${escapeHtml(JSON.stringify(v, null, 2))}</pre>`;
    else display = escapeHtml(String(v));
    rows.push(`<tr><th style="text-align:left; white-space:nowrap; padding-right:12px;">${escapeHtml(k)}</th><td>${display}</td></tr>`);
  };
  (preferKeys || []).forEach((k) => {
    if (Object.prototype.hasOwnProperty.call(obj, k)) add(k, obj[k]);
  });
  Object.keys(obj).sort().forEach((k) => {
    if (!seen.has(k)) add(k, obj[k]);
  });
  return `<div class="table-wrap auto-height"><table class="kv-table"><tbody>${rows.join('')}</tbody></table></div>`;
}

async function loadFridaSystemInfo(serial) {
  const out = document.getElementById('frida-sysinfo');
  if (!out) return;
  out.style.display = 'block';
  out.innerHTML = '<p class="muted">Querying device...</p>';
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/system`);
    const data = await res.json();
    if (!data.ok) { out.innerHTML = `<p class="muted">Error: ${escapeHtml(data.error || 'failed')}</p>`; return; }
    const sys = data.system || {};
    const prefer = ['arch', 'os', 'platform', 'access', 'name', 'api-level', 'api_level', 'version'];
    out.innerHTML = `
      <div class="section-head"><div><h3>System parameters</h3><p class="section-desc">From <code>device.query_system_parameters()</code></p></div></div>
      ${renderKeyValueTable(sys, prefer)}
      <details style="margin-top:8px;"><summary class="muted">Raw JSON</summary>
        <pre class="shell-output" style="max-height:200px;">${escapeHtml(JSON.stringify(sys, null, 2))}</pre>
      </details>`;
  } catch (err) {
    out.innerHTML = `<p class="muted">${escapeHtml(String(err))}</p>`;
  }
}

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
      <div class="toolbar-row" style="margin-top:6px;">
        <input type="text" id="frida-kill-target" placeholder="Kill by PID or process name" style="flex:1; min-width:180px;" title="device.kill(pid|name)">
        <button id="frida-kill-btn" title="Kill process by PID or name">Kill</button>
      </div>
      <div class="table-wrap auto-height">
        <table>
          <thead id="frida-target-head"></thead>
          <tbody id="frida-process-body"><tr><td colspan="4">Loading...</td></tr></tbody>
        </table>
      </div>
      <div id="frida-target-detail" style="display:none; margin-top:10px;"></div>
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
      <div class="section-head" style="margin-top:14px;">
        <div><h3>Pending children</h3><p class="section-desc">Children suspended by child gating (enable from Live console after attaching).</p></div>
        <button id="frida-pending-children-refresh-btn">Refresh children</button>
      </div>
      <div class="table-wrap auto-height">
        <table>
          <thead><tr><th>PID</th><th>Parent</th><th>Identifier / path</th><th>Action</th></tr></thead>
          <tbody id="frida-pending-children-body"><tr><td colspan="4" class="muted">No pending children.</td></tr></tbody>
        </table>
      </div>
      <div class="section-head" style="margin-top:14px;">
        <div><h3>Device event stream</h3><p class="section-desc">Live <code>spawn-*</code>, <code>child-*</code>, <code>process-crashed</code>, and <code>output</code> signals.</p></div>
        <button id="frida-events-clear-btn">Clear</button>
      </div>
      <div class="table-wrap auto-height">
        <table>
          <thead><tr><th>Time</th><th>Type</th><th>Detail</th></tr></thead>
          <tbody id="frida-events-body"><tr><td colspan="3" class="muted">Waiting for events…</td></tr></tbody>
        </table>
      </div>
      <div id="frida-crash-detail" style="display:none; margin-top:10px;"></div>
      <div class="section-head" style="margin-top:14px;">
        <div><h3>Stdin input</h3><p class="section-desc">Send bytes to a spawned process with <code>stdio=pipe</code> (device.input).</p></div>
      </div>
      <div class="toolbar-row">
        <input type="text" id="frida-stdin-pid" placeholder="PID" style="width:100px;" title="Process PID (defaults to selected)">
        <input type="text" id="frida-stdin-data" placeholder="Text to send (or hex if encoding=hex)" style="flex:1; min-width:180px;">
        <select id="frida-stdin-encoding" title="Encoding">
          <option value="utf8">utf8</option>
          <option value="hex">hex</option>
        </select>
        <button id="frida-stdin-send-btn">Send stdin</button>
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
  document.getElementById('frida-pending-children-refresh-btn').addEventListener('click', () => loadFridaPendingChildren(serial));
  document.getElementById('frida-stdin-send-btn').addEventListener('click', () => sendFridaStdin(serial));
  document.getElementById('frida-kill-btn').addEventListener('click', () => killFridaTarget(serial));
  document.getElementById('frida-events-clear-btn').addEventListener('click', () => {
    FRIDA_EVENT_LOG = [];
    renderFridaEventsPanel();
  });
  if (FRIDA_SELECTED_PID) {
    const pidEl = document.getElementById('frida-stdin-pid');
    if (pidEl && !pidEl.value) pidEl.value = String(FRIDA_SELECTED_PID);
  }
  renderFridaEventsPanel();
  reloadFridaTarget(serial);
}

function formatFridaEventDetail(ev) {
  if (!ev) return '—';
  if (ev.type === 'process-crashed') {
    return `pid=${ev.pid ?? '?'} ${ev.process_name || ''} — ${ev.summary || 'crashed'}`.trim();
  }
  if (ev.type === 'output') return `pid=${ev.pid} fd=${ev.fd}: ${(ev.data || '').slice(0, 120)}`;
  const id = ev.identifier || ev.path || '';
  const parent = ev.parent_pid != null ? ` parent=${ev.parent_pid}` : '';
  return `pid=${ev.pid ?? '?'}${parent} ${id}`.trim();
}

function renderFridaEventsPanel() {
  const body = document.getElementById('frida-events-body');
  if (!body) return;
  const rows = FRIDA_EVENT_LOG.slice(-100).reverse();
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="3" class="muted">Waiting for events…</td></tr>`;
    return;
  }
  body.innerHTML = rows.map((ev, idx) => {
    const t = ev.ts ? new Date(ev.ts * 1000).toLocaleTimeString() : '—';
    const type = escapeHtml(ev.type || '?');
    const detail = escapeHtml(formatFridaEventDetail(ev));
    const crashBtn = ev.type === 'process-crashed'
      ? ` <button type="button" data-frida-crash-idx="${FRIDA_EVENT_LOG.length - 1 - idx}" class="linkish">report</button>`
      : '';
    return `<tr>
      <td class="muted">${escapeHtml(t)}</td>
      <td><code>${type}</code></td>
      <td>${detail}${crashBtn}</td>
    </tr>`;
  }).join('');
  body.querySelectorAll('button[data-frida-crash-idx]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const i = Number(btn.dataset.fridaCrashIdx);
      showFridaCrashDetail(FRIDA_EVENT_LOG[i]);
    });
  });
}

function showFridaCrashDetail(ev) {
  const box = document.getElementById('frida-crash-detail');
  if (!box || !ev) return;
  box.style.display = 'block';
  const prefer = ['pid', 'process_name', 'summary', 'report'];
  box.innerHTML = `
    <div class="section-head"><div><h3>Crash report</h3>
      <p class="section-desc">From <code>device.on('process-crashed')</code></p></div></div>
    ${renderKeyValueTable(ev, prefer)}
    ${ev.report ? `<pre class="shell-output" style="max-height:280px; margin-top:8px;">${escapeHtml(String(ev.report))}</pre>` : '<p class="muted">No native report attached.</p>'}
  `;
}

function pushFridaEvent(ev) {
  if (!ev || !ev.type) return;
  FRIDA_EVENT_LOG.push(ev);
  if (FRIDA_EVENT_LOG.length > 200) FRIDA_EVENT_LOG.splice(0, FRIDA_EVENT_LOG.length - 200);
  renderFridaEventsPanel();
  if (ev.type === 'process-crashed' && ev.report) {
    // Keep last crash detail ready without forcing open every time.
  }
}

async function loadFridaPendingChildren(serial) {
  const body = document.getElementById('frida-pending-children-body');
  if (body) body.innerHTML = `<tr><td colspan="4">Loading...</td></tr>`;
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/pending-children`);
    const data = await res.json();
    if (!data.ok) { if (body) body.innerHTML = `<tr><td colspan="4" class="muted">${escapeHtml(data.error || 'failed')}</td></tr>`; return; }
    const rows = data.pending || [];
    if (!rows.length) { body.innerHTML = `<tr><td colspan="4" class="muted">No pending children</td></tr>`; return; }
    body.innerHTML = rows.map((c) => `
      <tr>
        <td>${c.pid}</td>
        <td>${c.parent_pid ?? '-'}</td>
        <td>${escapeHtml(c.identifier || c.path || '-')}</td>
        <td>
          <button data-frida-resume="${c.pid}" title="Resume so it runs normally">Resume</button>
          <button data-frida-kill="${c.pid}" title="Kill the suspended child">Kill</button>
        </td>
      </tr>`).join('');
    body.querySelectorAll('button[data-frida-resume]').forEach((btn) => {
      btn.addEventListener('click', () => fridaPidAction(serial, 'resume', btn.dataset.fridaResume));
    });
    body.querySelectorAll('button[data-frida-kill]').forEach((btn) => {
      btn.addEventListener('click', () => fridaPidAction(serial, 'kill', btn.dataset.fridaKill));
    });
  } catch (err) {
    if (body) body.innerHTML = `<tr><td colspan="4">${escapeHtml(String(err))}</td></tr>`;
  }
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
  loadFridaPendingChildren(serial);
  if (FRIDA_TARGET_MODE === 'processes') loadFridaProcesses(serial);
}

async function killFridaTarget(serial, targetOverride) {
  const input = document.getElementById('frida-kill-target');
  const target = (targetOverride != null ? String(targetOverride) : (input?.value || '')).trim();
  if (!target) { toast('Enter a PID or process name to kill', 'error'); return; }
  if (!confirm(`Kill ${target}?`)) return;
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/kill`, {
      method: 'POST',
      body: { target },
    });
    const data = await res.json();
    toast(data.ok ? `Killed ${target}` : `Kill failed: ${data.error}`, data.ok ? 'success' : 'error');
    if (data.ok) {
      if (input) input.value = '';
      if (FRIDA_TARGET_MODE === 'processes') loadFridaProcesses(serial);
      else loadFridaApplications(serial);
    }
  } catch (err) {
    toast(String(err), 'error');
  }
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
      <p id="frida-script-desc" class="section-desc muted" style="margin:6px 0 8px;"></p>
      <textarea id="frida-script-editor" spellcheck="false" style="width:100%; min-height:280px; font-family:Consolas, monospace;"></textarea>
      <div class="section-head" style="margin-top:14px;">
        <div><h3>Attach</h3><p class="section-desc">Attach to the process selected on the Target tab, or spawn a fresh package.</p></div>
      </div>
      <div class="toolbar-row">
        <label class="muted" for="frida-runtime-select" title="JS runtime for create_script">Runtime</label>
        <select id="frida-runtime-select" title="QJS is default; V8 for broader ES/compat">
          <option value="">default (QJS)</option>
          <option value="qjs">qjs</option>
          <option value="v8">v8</option>
        </select>
        <input type="text" id="frida-script-params" placeholder='PARAMS JSON, e.g. {"className":"com.example.App"}' style="flex:1; min-width:220px;" title="Injected as const PARAMS = {...} before the script">
        <button id="frida-attach-selected-btn">Attach selected (${escapeHtml(String(FRIDA_SELECTED_PID || '—'))})</button>
        <input type="text" id="frida-spawn-package" placeholder="Spawn by package name" value="${escapeHtml(FRIDA_SPAWN_PACKAGE)}" style="flex:1; min-width:200px;">
        <button id="frida-spawn-btn">Spawn + attach</button>
      </div>
      <div class="section-head" style="margin-top:10px;">
        <div><h3>Spawn options</h3><p class="section-desc">Optional argv / env / cwd / stdio for device.spawn (used with Spawn + attach).</p></div>
      </div>
      <div class="toolbar-row">
        <input type="text" id="frida-spawn-argv" placeholder='argv JSON, e.g. ["--flag"]' style="flex:1; min-width:160px;" title="Extra argv list (JSON array)">
        <input type="text" id="frida-spawn-env" placeholder='env JSON, e.g. {"DEBUG":"1"}' style="flex:1; min-width:160px;" title="Environment object (JSON)">
        <input type="text" id="frida-spawn-cwd" placeholder="cwd" style="width:140px;" title="Working directory">
        <select id="frida-spawn-stdio" title="stdio mode">
          <option value="">stdio default</option>
          <option value="inherit">inherit</option>
          <option value="pipe">pipe</option>
        </select>
      </div>
    </section>`;
  document.getElementById('frida-load-script-btn').addEventListener('click', loadSelectedFridaScript);
  document.getElementById('frida-save-script-btn').addEventListener('click', saveFridaScript);
  document.getElementById('frida-delete-script-btn').addEventListener('click', deleteFridaScript);
  document.getElementById('frida-attach-selected-btn').addEventListener('click', () => attachFrida(serial));
  document.getElementById('frida-spawn-btn').addEventListener('click', () => attachFrida(serial, true));
  document.getElementById('frida-script-select').addEventListener('change', loadSelectedFridaScript);
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

function setFridaConsoleHtml(html, append = false, type = 'info') {
  const out = document.getElementById('frida-console');
  if (!out) return;
  if (!append) out.innerHTML = '';
  const line = document.createElement('div');
  const colors = {
    send: '#35c46a', error: '#e0563d', info: '#d8dee9', message: '#4f8cff',
    log: '#d8dee9', warning: '#e0b341', warn: '#e0b341', debug: '#8b949e',
  };
  line.style.color = colors[type] || colors.info;
  line.innerHTML = html;
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
        <button data-frida-infoproc="${p.pid}" title="Show process metadata">Info</button>
        <button data-frida-killproc="${p.pid}" title="Kill by PID">Kill PID</button>
        <button data-frida-killname="${escapeHtml(p.name || '')}" title="Kill by process name">Kill name</button>
      </td>
    </tr>
  `).join('');
  body.querySelectorAll('button[data-frida-pid]').forEach((btn) => {
    btn.addEventListener('click', () => selectFridaPid(btn.dataset.fridaPid, btn));
  });
  body.querySelectorAll('button[data-frida-infoproc]').forEach((btn) => {
    btn.addEventListener('click', () => loadFridaProcessDetail(getSelectedSerial(), btn.dataset.fridaInfoproc));
  });
  body.querySelectorAll('button[data-frida-killproc]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const serial = getSelectedSerial();
      if (serial && confirm(`Kill PID ${btn.dataset.fridaKillproc}?`)) fridaPidAction(serial, 'kill', btn.dataset.fridaKillproc);
    });
  });
  body.querySelectorAll('button[data-frida-killname]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const serial = getSelectedSerial();
      const name = btn.dataset.fridaKillname;
      if (serial && name) killFridaTarget(serial, name);
    });
  });
}

async function loadFridaProcessDetail(serial, query) {
  const out = document.getElementById('frida-target-detail');
  if (!serial || !out) return;
  out.style.display = 'block';
  out.innerHTML = '<p class="muted">Loading process metadata...</p>';
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/process?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    if (!data.ok) { out.innerHTML = `<p class="muted">Error: ${escapeHtml(data.error || 'failed')}</p>`; return; }
    const proc = data.process || {};
    const flat = {
      pid: proc.pid,
      name: proc.name,
      ...(proc.parameters && typeof proc.parameters === 'object' ? proc.parameters : {}),
    };
    out.innerHTML = `
      <div class="section-head"><div><h3>Process metadata</h3>
        <p class="section-desc">From <code>device.get_process()</code> / enumerate scope=metadata</p></div></div>
      ${renderKeyValueTable(flat, ['pid', 'name', 'path', 'user', 'ppid', 'uid'])}
      <details style="margin-top:8px;"><summary class="muted">Raw JSON</summary>
        <pre class="shell-output" style="max-height:200px;">${escapeHtml(JSON.stringify(proc, null, 2))}</pre>
      </details>`;
  } catch (err) {
    out.innerHTML = `<p class="muted">${escapeHtml(String(err))}</p>`;
  }
}

function selectFridaPid(pid, btn) {
  document.querySelectorAll('button[data-frida-pid], button[data-frida-app-pid]').forEach((b) => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  FRIDA_SELECTED_PID = pid;
  const stdin = document.getElementById('frida-stdin-pid');
  if (stdin) stdin.value = String(pid);
  const kill = document.getElementById('frida-kill-target');
  if (kill && !kill.value) kill.value = String(pid);
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
        ? `<button data-frida-app-pid="${a.pid}">Attach</button>
           <button data-frida-killproc="${a.pid}" title="Kill by PID">Kill</button>`
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
  body.querySelectorAll('button[data-frida-killproc]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const serial = getSelectedSerial();
      if (serial && confirm(`Kill PID ${btn.dataset.fridaKillproc}?`)) fridaPidAction(serial, 'kill', btn.dataset.fridaKillproc);
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
  if (!select) return;
  const res = await apiFetch('/api/frida/scripts');
  const data = await res.json();
  window.FRIDA_SCRIPTS = data.scripts || {};
  const names = Object.keys(window.FRIDA_SCRIPTS);
  select.innerHTML = names.map((name) => {
    const s = window.FRIDA_SCRIPTS[name];
    const tag = s.readonly ? ' (template)' : '';
    return `<option value="${escapeHtml(name)}">${escapeHtml(name)}${tag}</option>`;
  }).join('');
  if (names.length) loadSelectedFridaScript();
}

function loadSelectedFridaScript() {
  const name = document.getElementById('frida-script-select')?.value;
  const script = window.FRIDA_SCRIPTS && window.FRIDA_SCRIPTS[name];
  if (!script) return;
  const nameEl = document.getElementById('frida-script-name');
  const editor = document.getElementById('frida-script-editor');
  const desc = document.getElementById('frida-script-desc');
  if (nameEl) nameEl.value = script.readonly ? '' : name;
  if (editor) editor.value = script.source || '';
  if (desc) {
    const scope = name === 'template-ssl-pinning-bypass'
      ? ' Coverage: OkHttp CertificatePinner, Conscrypt/TrustManagerImpl, custom TrustManager, WebViewClient (not Flutter/Cronet).'
      : name === 'template-root-detection-bypass'
        ? ' Coverage: File.exists, Runtime.exec, SystemProperties, Build.TAGS, PackageManager, RootBeer (not SafetyNet/Play Integrity).'
        : '';
    desc.textContent = (script.description || '') + scope;
  }
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

function enableFridaSessionControls(enabled) {
  ['frida-detach-btn', 'frida-eternalize-btn', 'frida-childgate-on-btn', 'frida-childgate-off-btn',
   'frida-interrupt-btn', 'frida-terminate-btn'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = !enabled;
  });
  ['frida-rpc-refresh-btn', 'frida-post-input', 'frida-post-data', 'frida-post-btn'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = !enabled;
  });
  if (!enabled) setFridaRpcDisabled(true);
}

async function attachFrida(serial, spawn = false) {
  const source = document.getElementById('frida-script-editor').value;
  const body = { script_source: source };
  const runtimeEl = document.getElementById('frida-runtime-select');
  const runtime = runtimeEl && runtimeEl.value ? runtimeEl.value : '';
  if (runtime) body.runtime = runtime;
  const paramsText = (document.getElementById('frida-script-params')?.value || '').trim();
  if (paramsText) {
    try {
      const params = JSON.parse(paramsText);
      if (!params || typeof params !== 'object' || Array.isArray(params)) {
        toast('PARAMS must be a JSON object', 'error');
        return;
      }
      body.params = params;
    } catch (e) {
      toast('PARAMS must be valid JSON', 'error');
      return;
    }
  }
  if (spawn) {
    const pkg = document.getElementById('frida-spawn-package').value.trim();
    if (!pkg) { toast('Enter a package name to spawn', 'error'); return; }
    body.spawn = pkg;
    const argvText = (document.getElementById('frida-spawn-argv')?.value || '').trim();
    if (argvText) {
      try {
        const argv = JSON.parse(argvText);
        if (!Array.isArray(argv)) { toast('argv must be a JSON array', 'error'); return; }
        body.argv = argv;
      } catch (e) { toast('argv must be valid JSON', 'error'); return; }
    }
    const envText = (document.getElementById('frida-spawn-env')?.value || '').trim();
    if (envText) {
      try {
        const env = JSON.parse(envText);
        if (!env || typeof env !== 'object' || Array.isArray(env)) {
          toast('env must be a JSON object', 'error'); return;
        }
        body.env = env;
      } catch (e) { toast('env must be valid JSON', 'error'); return; }
    }
    const cwd = (document.getElementById('frida-spawn-cwd')?.value || '').trim();
    if (cwd) body.cwd = cwd;
    const stdio = document.getElementById('frida-spawn-stdio')?.value || '';
    if (stdio) body.stdio = stdio;
  } else {
    if (!FRIDA_SELECTED_PID) { toast('Select a running process on the Target tab first', 'error'); return; }
    body.target = FRIDA_SELECTED_PID;
  }
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/attach`, { method: 'POST', body });
  const data = await res.json();
  if (!data.ok) { toast(`Attach failed: ${data.error}`, 'error'); return; }
  activateFridaSession(data.session_id, {
    runtime,
    params: Boolean(body.params),
    spawnOptions: Boolean(body.argv || body.env || body.cwd || body.stdio),
  });
  startFridaDeviceEventPoll(serial);
  refreshFridaSessionsList(false);
}

function activateFridaSession(sessionId, notes = {}) {
  fridaSessionId = sessionId;
  enableFridaSessionControls(true);
  const parts = [];
  if (notes.runtime) parts.push(`runtime=${notes.runtime}`);
  if (notes.params) parts.push('params');
  if (notes.spawnOptions) parts.push('spawn-options');
  const note = parts.length ? ` (${parts.join(', ')})` : '';
  setFridaConsole(`Active session ${sessionId}${note}`);
  updateFridaSessionMeta();
  startFridaStream(sessionId);
  startFridaSessionPoll(sessionId);
  renderFridaSessionSelect();
}

function clearFridaSessionUi({ keepSessionId = false } = {}) {
  if (!keepSessionId) fridaSessionId = null;
  if (fridaSource) { fridaSource.close(); fridaSource = null; }
  if (fridaSessionPollTimer) { clearInterval(fridaSessionPollTimer); fridaSessionPollTimer = null; }
  enableFridaSessionControls(false);
  updateFridaSessionMeta();
  renderFridaSessionSelect();
}

function updateFridaSessionMeta() {
  const el = document.getElementById('frida-session-meta');
  if (!el) return;
  if (!fridaSessionId) {
    el.textContent = 'No active session';
    return;
  }
  const s = FRIDA_SESSIONS.find((x) => x.id === fridaSessionId);
  if (!s) {
    el.textContent = `Session ${fridaSessionId}`;
    return;
  }
  const target = typeof s.target === 'object' ? JSON.stringify(s.target) : String(s.target ?? '—');
  const state = s.detached
    ? `detached (${s.detach_reason || 'unknown'})`
    : 'live';
  el.innerHTML = `Session <code>${escapeHtml(s.id)}</code> · target ${escapeHtml(target)} · ${escapeHtml(state)}${s.runtime ? ` · runtime ${escapeHtml(s.runtime)}` : ''}`;
}

async function refreshFridaSessionsList(announce) {
  try {
    const res = await apiFetch('/api/frida/sessions');
    const data = await res.json();
    if (!data.ok) return;
    FRIDA_SESSIONS = data.sessions || [];
    renderFridaSessionSelect();
    updateFridaSessionMeta();
    if (announce) toast(`${FRIDA_SESSIONS.length} session(s)`, 'info');
    // If active session disappeared, disable controls.
    if (fridaSessionId && !FRIDA_SESSIONS.some((s) => s.id === fridaSessionId)) {
      clearFridaSessionUi();
    }
  } catch (e) { /* ignore */ }
}

function renderFridaSessionSelect() {
  const sel = document.getElementById('frida-session-select');
  if (!sel) return;
  const live = FRIDA_SESSIONS.filter((s) => !s.detached);
  const detached = FRIDA_SESSIONS.filter((s) => s.detached);
  const options = [];
  if (!FRIDA_SESSIONS.length) {
    options.push(`<option value="">(no sessions)</option>`);
  } else {
    live.forEach((s) => {
      const t = typeof s.target === 'object' ? JSON.stringify(s.target) : s.target;
      options.push(`<option value="${escapeHtml(s.id)}">${escapeHtml(s.id)} · ${escapeHtml(String(t))} [live]</option>`);
    });
    detached.forEach((s) => {
      options.push(`<option value="${escapeHtml(s.id)}">${escapeHtml(s.id)} [detached: ${escapeHtml(s.detach_reason || '?')}]</option>`);
    });
  }
  sel.innerHTML = options.join('');
  if (fridaSessionId) sel.value = fridaSessionId;
  else if (live.length) { /* leave empty until user picks or attaches */ }
}

function onFridaSessionSelect() {
  const sel = document.getElementById('frida-session-select');
  if (!sel || !sel.value) return;
  const id = sel.value;
  const s = FRIDA_SESSIONS.find((x) => x.id === id);
  if (s && s.detached) {
    toast(`Session ${id} is detached: ${s.detach_reason || 'unknown'}`, 'error');
    enableFridaSessionControls(false);
    fridaSessionId = id;
    updateFridaSessionMeta();
    return;
  }
  if (id === fridaSessionId && fridaSource) {
    updateFridaSessionMeta();
    return;
  }
  activateFridaSession(id);
}

async function interruptFridaScript() {
  if (!fridaSessionId) return;
  try {
    const res = await apiFetch(`/api/frida/sessions/${encodeURIComponent(fridaSessionId)}/interrupt`, { method: 'POST' });
    const data = await res.json();
    setFridaConsole(data.ok ? 'script interrupted' : `interrupt failed: ${data.error}`, true, data.ok ? 'info' : 'error');
  } catch (err) {
    setFridaConsole(`interrupt error: ${String(err)}`, true, 'error');
  }
}

async function terminateFridaScript() {
  if (!fridaSessionId) return;
  if (!confirm('Force-terminate this script and drop the session?')) return;
  const id = fridaSessionId;
  try {
    const res = await apiFetch(`/api/frida/sessions/${encodeURIComponent(id)}/terminate`, { method: 'POST' });
    const data = await res.json();
    if (!data.ok) { setFridaConsole(`terminate failed: ${data.error}`, true, 'error'); return; }
    setFridaConsole('script terminated; session dropped', true, 'error');
    clearFridaSessionUi();
    refreshFridaSessionsList(false);
  } catch (err) {
    setFridaConsole(`terminate error: ${String(err)}`, true, 'error');
  }
}

async function setFridaChildGating(enable) {
  if (!fridaSessionId) return;
  const action = enable ? 'enable' : 'disable';
  try {
    const res = await apiFetch(`/api/frida/sessions/${encodeURIComponent(fridaSessionId)}/child-gating/${action}`, { method: 'POST' });
    const data = await res.json();
    if (!data.ok) { setFridaConsole(`child gating ${action} failed: ${data.error}`, true, 'error'); return; }
    setFridaConsole(`child gating ${action}d — watch the Target tab's Pending children table`, true, 'info');
  } catch (err) {
    setFridaConsole(`child gating error: ${String(err)}`, true, 'error');
  }
}

function startFridaSessionPoll(sessionId) {
  if (fridaSessionPollTimer) clearInterval(fridaSessionPollTimer);
  fridaSessionPollTimer = setInterval(async () => {
    try {
      // Refresh full list so multi-session state stays current.
      await refreshFridaSessionsList(false);
      if (!fridaSessionId || fridaSessionId !== sessionId) return;
      const res = await apiFetch(`/api/frida/sessions/${encodeURIComponent(sessionId)}`);
      const data = await res.json();
      if (!data.ok) return;
      const sess = data.session || {};
      if (sess.detached) {
        setFridaConsole(`session detached: ${sess.detach_reason || 'unknown reason'} (poll)`, true, 'error');
        if (sess.crash || (sess.detach_reason && String(sess.detach_reason).includes('crash'))) {
          // detach reason already printed
        }
        enableFridaSessionControls(false);
        if (fridaSource) { fridaSource.close(); fridaSource = null; }
        updateFridaSessionMeta();
      }
    } catch (e) { /* ignore transient poll errors */ }
  }, 4000);
}

function setFridaRpcDisabled(disabled) {
  ['frida-rpc-refresh-btn', 'frida-rpc-select', 'frida-rpc-args', 'frida-rpc-call-btn',
   'frida-post-input', 'frida-post-data', 'frida-post-btn'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = disabled;
  });
}

async function postFridaMessage() {
  if (!fridaSessionId) return;
  const input = document.getElementById('frida-post-input');
  const dataEl = document.getElementById('frida-post-data');
  const raw = (input?.value || '').trim();
  const hex = (dataEl?.value || '').trim();
  if (!raw && !hex) return;
  let message = raw;
  if (raw) {
    try { message = JSON.parse(raw); } catch (e) { message = raw; }
  } else {
    message = null;
  }
  if (hex && !/^[0-9a-fA-F]*$/.test(hex)) {
    toast('Binary data must be hex digits only', 'error');
    return;
  }
  setFridaConsole(`post: ${raw || '(null)'}${hex ? ` + ${hex.length / 2} bytes` : ''}`, true, 'send');
  try {
    const body = { message };
    if (hex) body.data = hex;
    const res = await apiFetch(`/api/frida/sessions/${encodeURIComponent(fridaSessionId)}/post`,
      { method: 'POST', body });
    const data = await res.json();
    if (!data.ok) { setFridaConsole(`post error: ${data.error}`, true, 'error'); return; }
    if (input) input.value = '';
    if (dataEl) dataEl.value = '';
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

function recordFridaBinary(hex, label) {
  if (!hex) return;
  fridaBinarySeq += 1;
  const id = `bin-${fridaBinarySeq}`;
  FRIDA_BINARIES.push({ id, hex, label: label || id, ts: Date.now() });
  if (FRIDA_BINARIES.length > 50) FRIDA_BINARIES.splice(0, FRIDA_BINARIES.length - 50);
  renderFridaBinaryList();
  setFridaConsoleHtml(
    `binary payload ${escapeHtml(label || id)} (${hex.length / 2} bytes) `
    + `<button type="button" data-frida-dl-bin="${escapeHtml(id)}">Download</button>`,
    true,
    'message',
  );
  document.querySelectorAll(`button[data-frida-dl-bin="${id}"]`).forEach((btn) => {
    btn.addEventListener('click', () => downloadFridaBinaryById(id));
  });
}

function renderFridaBinaryList() {
  const el = document.getElementById('frida-binary-list');
  if (!el) return;
  if (!FRIDA_BINARIES.length) {
    el.textContent = '';
    return;
  }
  el.innerHTML = `Binary payloads: ${FRIDA_BINARIES.map((b) =>
    `<button type="button" data-frida-dl-bin="${escapeHtml(b.id)}" title="${b.hex.length / 2} bytes">${escapeHtml(b.label)} (${b.hex.length / 2}B)</button>`
  ).join(' ')}`;
  el.querySelectorAll('button[data-frida-dl-bin]').forEach((btn) => {
    btn.addEventListener('click', () => downloadFridaBinaryById(btn.dataset.fridaDlBin));
  });
}

function downloadFridaBinaryById(id) {
  const b = FRIDA_BINARIES.find((x) => x.id === id);
  if (!b) { toast('Binary not found', 'error'); return; }
  try {
    const bytes = new Uint8Array(b.hex.match(/.{1,2}/g).map((h) => parseInt(h, 16)));
    downloadFridaBlob(bytes, `${b.label || id}.bin`, 'application/octet-stream');
    toast(`Downloaded ${bytes.length} bytes`, 'success');
  } catch (e) {
    toast(`Download failed: ${e}`, 'error');
  }
}

function handleFridaStreamEntry(entry) {
  const msg = entry.message || {};
  if (msg.type === 'heartbeat') return;
  if (entry.data_hex) recordFridaBinary(entry.data_hex, `msg-${fridaBinarySeq + 1}`);

  if (msg.type === 'detached') {
    const crash = msg.crash;
    let crashTxt = '';
    if (crash) {
      crashTxt = ` (crash: ${crash.summary || crash.process_name || ''})`;
      pushFridaEvent({ type: 'process-crashed', ...crash, ts: Date.now() / 1000 });
      if (crash.report) {
        setFridaConsole(`crash report:\n${String(crash.report).slice(0, 2000)}`, true, 'error');
      }
    }
    setFridaConsole(`session detached: ${msg.reason || 'unknown reason'}${crashTxt}`, true, 'error');
    enableFridaSessionControls(false);
    if (fridaSource) { fridaSource.close(); fridaSource = null; }
    updateFridaSessionMeta();
    refreshFridaSessionsList(false);
    return;
  }
  if (msg.type === 'process-crashed') {
    pushFridaEvent(msg);
    setFridaConsole(
      `crash: pid=${msg.pid ?? '?'} ${msg.process_name || ''} — ${msg.summary || 'process crashed'}`.trim(),
      true,
      'error',
    );
    if (msg.report) {
      setFridaConsole(`crash report:\n${String(msg.report).slice(0, 4000)}`, true, 'error');
      showFridaCrashDetail(msg);
    }
    return;
  }
  if (msg.type === 'output') {
    pushFridaEvent(msg);
    setFridaConsole(`stdio[${msg.fd}] pid=${msg.pid}: ${msg.data || ''}`, true, 'info');
    return;
  }
  if (msg.type === 'spawn-added' || msg.type === 'spawn-removed'
      || msg.type === 'child-added' || msg.type === 'child-removed') {
    pushFridaEvent(msg);
    setFridaConsole(
      `${msg.type}: pid=${msg.pid ?? '?'} ${msg.identifier || msg.path || ''}`.trim(),
      true,
      'message',
    );
    const serial = getSelectedSerial();
    if (serial) {
      if (msg.type.startsWith('spawn')) loadFridaPendingSpawn(serial);
      if (msg.type.startsWith('child')) loadFridaPendingChildren(serial);
    }
    return;
  }
  if (msg.type === 'log') {
    const level = (msg.level || 'info').toLowerCase();
    const label = level === 'warning' ? 'warn' : level;
    setFridaConsole(`${label}: ${msg.payload ?? ''}`, true, label === 'error' ? 'error' : label);
  } else if (msg.type === 'send') {
    setFridaConsole(`send: ${JSON.stringify(msg.payload)}`, true, 'send');
    if (entry.data) setFridaConsole(`  data: ${entry.data}`, true, 'debug');
  } else if (msg.type === 'error') {
    setFridaConsole(`error: ${msg.description || JSON.stringify(msg)}`, true, 'error');
  } else {
    setFridaConsole(`${msg.type || 'message'}: ${JSON.stringify(msg)}`, true, 'message');
  }
}

function startFridaStream(sessionId) {
  if (fridaSource) fridaSource.close();
  fridaSource = new EventSource(`/api/frida/sessions/${encodeURIComponent(sessionId)}/stream`);
  fridaSource.onmessage = (event) => {
    try {
      handleFridaStreamEntry(JSON.parse(event.data));
    } catch (e) { /* ignore parse errors */ }
  };
}

function startFridaDeviceEventPoll(serial) {
  if (!serial) return;
  if (fridaDeviceEventTimer && fridaDeviceEventSerial === serial) return;
  if (fridaDeviceEventTimer) clearInterval(fridaDeviceEventTimer);
  fridaDeviceEventSerial = serial;
  fridaDeviceEventAfter = 0;
  apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/events/wire`, { method: 'POST' }).catch(() => {});
  fridaDeviceEventTimer = setInterval(() => pollFridaDeviceEvents(serial), 2500);
  pollFridaDeviceEvents(serial);
}

async function pollFridaDeviceEvents(serial) {
  if (!serial || fridaDeviceEventSerial !== serial) return;
  try {
    const res = await apiFetch(
      `/api/devices/${encodeURIComponent(serial)}/frida/events?after=${encodeURIComponent(fridaDeviceEventAfter)}&limit=50`,
    );
    const data = await res.json();
    if (!data.ok) return;
    const events = data.events || [];
    let sawSpawn = false;
    let sawChild = false;
    for (const ev of events) {
      if (ev.ts && ev.ts > fridaDeviceEventAfter) fridaDeviceEventAfter = ev.ts;
      if (ev.type && String(ev.type).startsWith('spawn')) sawSpawn = true;
      if (ev.type && String(ev.type).startsWith('child')) sawChild = true;
      pushFridaEvent(ev);
      // Avoid double console spam when session SSE already fans these out.
      if (fridaSessionId) continue;
      if (ev.type === 'process-crashed') {
        setFridaConsole(
          `crash: pid=${ev.pid ?? '?'} ${ev.process_name || ''} — ${ev.summary || 'process crashed'}`.trim(),
          true,
          'error',
        );
        if (ev.report) setFridaConsole(`crash report:\n${String(ev.report).slice(0, 2000)}`, true, 'error');
      } else if (ev.type === 'output') {
        setFridaConsole(`stdio[${ev.fd}] pid=${ev.pid}: ${ev.data || ''}`, true, 'info');
      } else if (ev.type) {
        setFridaConsole(
          `${ev.type}: pid=${ev.pid ?? '?'} ${ev.identifier || ev.path || ''}`.trim(),
          true,
          'message',
        );
      }
    }
    if (sawSpawn) loadFridaPendingSpawn(serial);
    if (sawChild) loadFridaPendingChildren(serial);
  } catch (e) { /* ignore poll errors */ }
}

async function sendFridaStdin(serial) {
  const pidEl = document.getElementById('frida-stdin-pid');
  const dataEl = document.getElementById('frida-stdin-data');
  const encEl = document.getElementById('frida-stdin-encoding');
  const pid = (pidEl?.value || FRIDA_SELECTED_PID || '').toString().trim();
  const data = (dataEl?.value || '');
  const encoding = encEl?.value || 'utf8';
  if (!pid) { toast('Enter a PID for stdin input', 'error'); return; }
  if (!data) { toast('Enter data to send', 'error'); return; }
  try {
    const res = await apiFetch(
      `/api/devices/${encodeURIComponent(serial)}/frida/input/${encodeURIComponent(pid)}`,
      { method: 'POST', body: { data, encoding } },
    );
    const result = await res.json();
    toast(result.ok ? `Sent ${result.bytes} byte(s) to pid ${pid}` : `stdin failed: ${result.error}`,
      result.ok ? 'success' : 'error');
    if (result.ok && dataEl) dataEl.value = '';
  } catch (err) {
    toast(String(err), 'error');
  }
}

async function exportFridaConsole(format) {
  if (fridaSessionId) {
    try {
      const res = await apiFetch(
        `/api/frida/sessions/${encodeURIComponent(fridaSessionId)}/export?format=${encodeURIComponent(format)}`,
      );
      if (format === 'text') {
        const text = await res.text();
        if (res.ok) {
          downloadFridaBlob(text, `frida-session-${fridaSessionId}.txt`, 'text/plain');
          toast('Exported console as text', 'success');
          return;
        }
      } else {
        const data = await res.json();
        if (data.ok) {
          // Harvest any data_hex into the binary list for one-click download.
          (data.messages || []).forEach((item, i) => {
            if (item.data_hex) recordFridaBinary(item.data_hex, `export-${i + 1}`);
          });
          downloadFridaBlob(JSON.stringify(data, null, 2), `frida-session-${fridaSessionId}.json`, 'application/json');
          toast('Exported console as JSON', 'success');
          return;
        }
        toast(`Export failed: ${data.error || res.status}`, 'error');
        return;
      }
    } catch (err) {
      toast(`Export error: ${String(err)}`, 'error');
      return;
    }
  }
  const out = document.getElementById('frida-console');
  const text = out ? out.innerText || out.textContent || '' : '';
  if (!text.trim()) { toast('Console is empty', 'info'); return; }
  if (format === 'json') {
    const lines = text.split('\n').filter(Boolean).map((line) => ({ line }));
    downloadFridaBlob(JSON.stringify({ messages: lines }, null, 2), 'frida-console.json', 'application/json');
  } else {
    downloadFridaBlob(text, 'frida-console.txt', 'text/plain');
  }
  toast('Exported console from UI', 'success');
}

async function exportFridaBinaries() {
  // Prefer session export harvest; fall back to in-memory list.
  if (fridaSessionId) {
    try {
      const res = await apiFetch(
        `/api/frida/sessions/${encodeURIComponent(fridaSessionId)}/export?format=json`,
      );
      const data = await res.json();
      if (data.ok) {
        const bins = [];
        (data.messages || []).forEach((item, i) => {
          if (item.data_hex) bins.push({ hex: item.data_hex, label: `payload-${i + 1}` });
        });
        if (!bins.length && !FRIDA_BINARIES.length) {
          toast('No binary payloads in this session', 'info');
          return;
        }
        const all = bins.length ? bins : FRIDA_BINARIES;
        if (all.length === 1) {
          downloadFridaBinaryHex(all[0].hex, all[0].label || 'payload');
          return;
        }
        // Zip-less multi-download: JSON manifest + individual .bin for each.
        downloadFridaBlob(
          JSON.stringify(all.map((b) => ({ label: b.label, bytes: b.hex.length / 2, hex: b.hex })), null, 2),
          `frida-binaries-${fridaSessionId}.json`,
          'application/json',
        );
        all.forEach((b, i) => {
          setTimeout(() => downloadFridaBinaryHex(b.hex, b.label || `payload-${i + 1}`), 100 * (i + 1));
        });
        toast(`Exported ${all.length} binary payload(s)`, 'success');
        return;
      }
    } catch (e) { /* fall through */ }
  }
  if (!FRIDA_BINARIES.length) { toast('No binary payloads captured', 'info'); return; }
  FRIDA_BINARIES.forEach((b, i) => {
    setTimeout(() => downloadFridaBinaryHex(b.hex, b.label || `payload-${i + 1}`), 100 * (i + 1));
  });
  toast(`Exported ${FRIDA_BINARIES.length} binary payload(s)`, 'success');
}

function downloadFridaBinaryHex(hex, label) {
  try {
    const bytes = new Uint8Array(hex.match(/.{1,2}/g).map((h) => parseInt(h, 16)));
    downloadFridaBlob(bytes, `${label || 'payload'}.bin`, 'application/octet-stream');
  } catch (e) {
    toast(`Binary export failed: ${e}`, 'error');
  }
}

function downloadFridaBlob(content, filename, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function eternalizeFrida() {
  if (!fridaSessionId) return;
  if (!confirm('Eternalize this script? It will keep running after you disconnect.')) return;
  const id = fridaSessionId;
  const res = await apiFetch(`/api/frida/sessions/${encodeURIComponent(id)}/eternalize`, { method: 'POST' });
  const data = await res.json();
  if (!data.ok) { toast(`Eternalize failed: ${data.error}`, 'error'); return; }
  clearFridaSessionUi();
  setFridaConsole(`Session ${id} eternalized — script remains on target`, true, 'info');
  toast('Script eternalized', 'success');
  refreshFridaSessionsList(false);
}

async function detachFrida() {
  if (!fridaSessionId) return;
  const id = fridaSessionId;
  clearFridaSessionUi();
  const res = await apiFetch(`/api/frida/sessions/${encodeURIComponent(id)}/detach`, { method: 'POST' });
  const data = await res.json();
  toast(data.ok ? 'Detached' : `Detach failed: ${data.error}`, data.ok ? 'success' : 'error');
  refreshFridaSessionsList(false);
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => {
    if (tab === 'frida') renderFridaTab();
    else if (fridaSource) { fridaSource.close(); fridaSource = null; }
  });
  onDeviceChange(() => { if (currentTab() === 'frida') renderFridaTab(); });
});

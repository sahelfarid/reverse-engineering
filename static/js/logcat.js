// Logcat tab: live streaming via SSE with tag/pid/package/level/regex filters.

let logcatSource = null;
let logcatLines = [];
let logcatPaused = false;

const LOGCAT_LEVEL_COLOR = { V: '#9aa1ab', D: '#4f8cff', I: '#35c46a', W: '#e0b13d', E: '#e0563d', F: '#e0563d' };

Object.assign(TIP_REGISTRY, {
  'logcat.filters': {
    title: 'Logcat filters',
    body: '<p>Tag, PID, and Package filter the stream server-side. If you give a Package with no PID, the server resolves its current PID for you; giving both skips that lookup.</p><p>The search box applies a regex against each line client-side.</p>',
  },
});

function renderLogcatTab() {
  const pane = document.getElementById('tab-logcat');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to view logcat.</div>`;
    return;
  }
  if (pane.dataset.boundSerial === serial) return;
  pane.dataset.boundSerial = serial;
  stopLogcatStream();
  logcatLines = [];

  pane.innerHTML = `
    <div class="panel-page">
      <div class="panel-header">
        <h2>Logcat</h2>
        <p class="muted">Stream the device log live, filtered by tag, PID, package, level, or a regex query.</p>
      </div>
      <section class="panel-section">
        <div class="toolbar-row">
          <input type="text" id="logcat-tag" placeholder="Tag">
          <input type="text" id="logcat-pid" placeholder="PID">
          <input type="text" id="logcat-package" placeholder="Package">
          <select id="logcat-level">
            <option value="V">Verbose+</option><option value="D">Debug+</option>
            <option value="I" selected>Info+</option><option value="W">Warn+</option>
            <option value="E">Error+</option><option value="F">Fatal</option>
          </select>
          <input type="text" id="logcat-query" placeholder="Regex search…" style="flex:1; min-width:150px;">
          <button type="button" class="tip-btn" data-tip-key="logcat.filters" aria-label="Help">?</button>
        </div>
        <div class="toolbar-row">
          <button id="logcat-start-btn">Start</button>
          <button id="logcat-pause-btn">Pause</button>
          <button id="logcat-clear-btn">Clear device log</button>
          <button id="logcat-clear-view-btn">Clear view</button>
          <button id="logcat-export-btn">Export</button>
        </div>
        <pre id="logcat-output" class="shell-output"></pre>
      </section>
    </div>
  `;
  wireLogcatControls(serial);
}

function wireLogcatControls(serial) {
  document.getElementById('logcat-start-btn').addEventListener('click', () => startLogcatStream(serial));
  document.getElementById('logcat-pause-btn').addEventListener('click', () => stopLogcatStream());
  document.getElementById('logcat-clear-view-btn').addEventListener('click', () => {
    document.getElementById('logcat-output').innerHTML = '';
    logcatLines = [];
  });
  document.getElementById('logcat-clear-btn').addEventListener('click', async () => {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/logcat/clear`, { method: 'POST' });
    const data = await res.json();
    toast(data.ok ? 'Device log cleared' : 'Failed to clear device log', data.ok ? 'success' : 'error');
  });
  document.getElementById('logcat-export-btn').addEventListener('click', () => {
    const text = logcatLines.map((e) => e.raw).join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `logcat-${serial}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  });
}

function startLogcatStream(serial) {
  stopLogcatStream();
  const tag = document.getElementById('logcat-tag').value.trim();
  const pid = document.getElementById('logcat-pid').value.trim();
  const pkg = document.getElementById('logcat-package').value.trim();
  const level = document.getElementById('logcat-level').value;
  const query = document.getElementById('logcat-query').value.trim();
  const params = new URLSearchParams();
  if (tag) params.set('tag', tag);
  if (pid) params.set('pid', pid);
  if (pkg) params.set('package', pkg);
  if (level) params.set('min_level', level);
  if (query) params.set('query', query);

  logcatSource = new EventSource(`/api/devices/${encodeURIComponent(serial)}/logcat/stream?${params.toString()}`);
  logcatPaused = false;
  logcatSource.onmessage = (event) => {
    const entry = JSON.parse(event.data);
    appendLogcatLine(serial, entry);
  };
  logcatSource.onerror = () => { /* browser auto-retries; leave as-is */ };
}

function stopLogcatStream() {
  if (logcatSource) { logcatSource.close(); logcatSource = null; }
  logcatPaused = true;
}

function appendLogcatLine(serial, entry) {
  const out = document.getElementById('logcat-output');
  if (!out) return;
  const maxLines = (window.APP_SETTINGS && window.APP_SETTINGS.max_log_lines) || 5000;
  logcatLines.push(entry);
  if (logcatLines.length > maxLines) logcatLines.splice(0, logcatLines.length - maxLines);

  const color = LOGCAT_LEVEL_COLOR[entry.level] || '#d8dee9';
  const line = document.createElement('div');
  line.style.color = color;
  line.textContent = entry.raw;
  out.appendChild(line);
  while (out.childElementCount > maxLines) out.removeChild(out.firstChild);
  out.scrollTop = out.scrollHeight;
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'logcat') renderLogcatTab(); else stopLogcatStream(); });
  onDeviceChange(() => {
    stopLogcatStream();
    const pane = document.getElementById('tab-logcat');
    if (pane) delete pane.dataset.boundSerial;
    if (currentTab() === 'logcat') renderLogcatTab();
  });
});

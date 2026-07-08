// SSL Pinning tab: static+dynamic detection report per package, plus a
// bypass-script store and an explicit-confirmation attach flow.

function renderSslPinningTab() {
  const pane = document.getElementById('tab-sslpinning');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to check SSL pinning.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="panel-page">
      <div class="panel-header">
        <h2>SSL Pinning Detection & Bypass</h2>
        <p class="muted">Authorized testing only. Bypass actively changes the app's TLS trust behavior -- only use it against apps you own or are explicitly authorized to test.</p>
      </div>
      <section class="panel-section">
        <div class="toolbar-row">
          <select id="sslpin-package-select" style="flex:1;"><option>Loading packages…</option></select>
          <button id="sslpin-detect-btn">Run detection</button>
        </div>
        <div id="sslpin-detect-result" class="muted">Pick a package and run detection.</div>
      </section>
      <section class="panel-section">
        <h3>Bypass</h3>
        <div id="sslpin-bypass-body" class="muted">Loading scripts…</div>
      </section>
    </div>
  `;
  loadSslPinPackages(serial);
  loadSslPinScripts(serial);
  document.getElementById('sslpin-detect-btn').addEventListener('click', () => runSslPinDetect(serial));
}

async function loadSslPinPackages(serial) {
  const select = document.getElementById('sslpin-package-select');
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

async function runSslPinDetect(serial) {
  const pkg = document.getElementById('sslpin-package-select').value;
  const resultEl = document.getElementById('sslpin-detect-result');
  if (!pkg) return;
  resultEl.innerHTML = 'Scanning sources and spawning the app to observe TLS checks…';
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/packages/${encodeURIComponent(pkg)}/sslpinning/detect`, {
      method: 'POST', body: { duration_sec: 4 },
    });
    const data = await res.json();
    if (!data.ok) { resultEl.innerHTML = `<div class="alert error">${escapeHtml(data.error)}</div>`; return; }
    const report = data.report;
    const staticFindings = (report.static && report.static.findings) || [];
    const dynamicEvents = (report.dynamic && report.dynamic.events) || [];
    const staticRows = staticFindings.length
      ? staticFindings.map((f) => `<tr><td>${escapeHtml(f.severity)}</td><td>${escapeHtml(f.id)}</td><td>${escapeHtml(f.file)}${f.line ? ':' + f.line : ''}</td><td><code>${escapeHtml(f.snippet || '')}</code></td></tr>`).join('')
      : `<tr><td colspan="4" class="muted">${escapeHtml((report.static && report.static.reason) || 'No static findings')}</td></tr>`;
    const dynamicRows = dynamicEvents.length
      ? dynamicEvents.map((e) => `<tr><td>${escapeHtml(e.check)}</td><td><code>${escapeHtml(e.detail)}</code></td></tr>`).join('')
      : `<tr><td colspan="2" class="muted">${escapeHtml((report.dynamic && report.dynamic.reason) || 'No dynamic hits observed')}</td></tr>`;
    resultEl.innerHTML = `
      <div class="card">
        <h4>Verdict: ${escapeHtml(report.verdict)}</h4>
        <div class="muted">${escapeHtml(report.disclaimer || '')}</div>
      </div>
      <div class="card">
        <h4>Static evidence (JADX source/resource scan)</h4>
        <div class="table-wrap"><table><thead><tr><th>Severity</th><th>Pattern</th><th>Location</th><th>Snippet</th></tr></thead>
        <tbody>${staticRows}</tbody></table></div>
      </div>
      <div class="card">
        <h4>Dynamic evidence (Frida observation)</h4>
        <div class="table-wrap"><table><thead><tr><th>Check</th><th>Detail</th></tr></thead>
        <tbody>${dynamicRows}</tbody></table></div>
      </div>
    `;
  } catch (err) {
    resultEl.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

async function loadSslPinScripts(serial) {
  const body = document.getElementById('sslpin-bypass-body');
  try {
    const res = await apiFetch('/api/frida/sslpinning/scripts');
    const data = await res.json();
    const scripts = data.ok ? data.scripts : {};
    const options = Object.keys(scripts).map((name) =>
      `<option value="${escapeHtml(name)}">${escapeHtml(name)}${scripts[name].readonly ? ' (built-in)' : ''}</option>`).join('');
    body.innerHTML = `
      <div class="toolbar-row">
        <select id="sslpin-script-select" style="flex:1;">${options}</select>
        <input type="text" id="sslpin-spawn-pkg" placeholder="package to spawn (defaults to detection package)" style="flex:1;">
        <button id="sslpin-bypass-btn">Attach bypass</button>
      </div>
      <label class="muted"><input type="checkbox" id="sslpin-confirm-checkbox"> I am authorized to test this app's traffic.</label>
      <div id="sslpin-bypass-result" class="muted"></div>
    `;
    document.getElementById('sslpin-bypass-btn').addEventListener('click', () => runSslPinBypass(serial));
  } catch (err) {
    body.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

async function runSslPinBypass(serial) {
  const resultEl = document.getElementById('sslpin-bypass-result');
  const scriptName = document.getElementById('sslpin-script-select').value;
  const confirmed = document.getElementById('sslpin-confirm-checkbox').checked;
  const spawnInput = document.getElementById('sslpin-spawn-pkg').value.trim();
  const spawnPkg = spawnInput || document.getElementById('sslpin-package-select').value;
  if (!confirmed) { toast('Check the authorization box first', 'error'); return; }
  if (!spawnPkg) { toast('Pick a package to spawn', 'error'); return; }
  resultEl.innerHTML = 'Attaching…';
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/frida/sslpinning/bypass`, {
      method: 'POST', body: { confirm: true, spawn: spawnPkg, script_name: scriptName },
    });
    const data = await res.json();
    if (!data.ok) { resultEl.innerHTML = `<div class="alert error">${escapeHtml(data.error || data.message)}</div>`; return; }
    resultEl.innerHTML = `<div class="alert info">Attached: session ${escapeHtml(data.session_id)}. Manage it from the Frida tab (sessions/stream/detach).</div>`;
    toast('SSL-pinning bypass attached', 'success');
  } catch (err) {
    resultEl.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'sslpinning') renderSslPinningTab(); });
  onDeviceChange(() => { if (currentTab() === 'sslpinning') renderSslPinningTab(); });
});

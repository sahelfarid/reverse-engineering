// Network tab (info/ping/port-forwarding) + Wireless tab (tcpip/connect/known devices).

function renderNetworkTab() {
  const pane = document.getElementById('tab-network');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to view network info.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="card-grid">
      <div class="card"><h4>Network info</h4><div id="network-info-body">Loading…</div></div>
      <div class="card">
        <h4>Ping (from device)</h4>
        <div style="display:flex; gap:8px;"><input type="text" id="network-ping-host" placeholder="host or IP"><button id="network-ping-btn">Ping</button></div>
        <pre id="network-ping-output" class="shell-output" style="height:120px; margin-top:8px;"></pre>
      </div>
    </div>
    <div class="card-grid">
      <div class="card">
        <h4>Port forwarding (local → device)</h4>
        <div style="display:flex; gap:6px; margin-bottom:8px;"><input type="text" id="fwd-local" placeholder="tcp:8080" style="width:100px;"> → <input type="text" id="fwd-remote" placeholder="tcp:8080" style="width:100px;"><button id="fwd-add-btn">Add</button></div>
        <div id="fwd-list"></div>
      </div>
      <div class="card">
        <h4>Reverse forwarding (device → local)</h4>
        <div style="display:flex; gap:6px; margin-bottom:8px;"><input type="text" id="rev-remote" placeholder="tcp:8080" style="width:100px;"> ← <input type="text" id="rev-local" placeholder="tcp:8080" style="width:100px;"><button id="rev-add-btn">Add</button></div>
        <div id="rev-list"></div>
      </div>
    </div>
  `;
  loadNetworkInfo(serial);
  loadForwards(serial);
  loadReverses(serial);
  document.getElementById('network-ping-btn').addEventListener('click', () => runPing(serial));
  document.getElementById('fwd-add-btn').addEventListener('click', () => addForward(serial));
  document.getElementById('rev-add-btn').addEventListener('click', () => addReverse(serial));
}

async function loadNetworkInfo(serial) {
  const body = document.getElementById('network-info-body');
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/network`);
  const data = await res.json();
  if (!data.ok) { body.innerHTML = `<div class="alert error">${escapeHtml(data.error)}</div>`; return; }
  const n = data.network;
  body.innerHTML = `
    <div>Wi-Fi IP: ${escapeHtml(n.wifi_ip || '—')}${n.wifi_prefix ? '/' + n.wifi_prefix : ''}</div>
    <div>Gateway: ${escapeHtml(n.gateway || '—')}</div>
    <div>DNS: ${escapeHtml(n.dns1 || '—')} ${n.dns2 ? ', ' + escapeHtml(n.dns2) : ''}</div>
    <div>Mobile network: ${escapeHtml(n.mobile_network_type || '—')}</div>
  `;
}

async function runPing(serial) {
  const host = document.getElementById('network-ping-host').value.trim();
  const out = document.getElementById('network-ping-output');
  if (!host) return;
  out.textContent = 'Pinging…';
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/network/ping`, { method: 'POST', body: { host, count: 4 } });
  const data = await res.json();
  out.textContent = data.output || data.error || '';
}

async function loadForwards(serial) {
  const list = document.getElementById('fwd-list');
  const res = await apiFetch('/api/forwards');
  const data = await res.json();
  const rows = (data.forwards || []).filter((f) => f.serial === serial);
  list.innerHTML = rows.length ? rows.map((f) => `
    <div style="display:flex; gap:8px; align-items:center;">${escapeHtml(f.local)} → ${escapeHtml(f.remote)}
      <button data-local="${escapeHtml(f.local)}" class="fwd-remove-btn">Remove</button></div>`).join('')
    : '<div class="muted">No forwards</div>';
  list.querySelectorAll('.fwd-remove-btn').forEach((btn) => btn.addEventListener('click', async () => {
    await apiFetch('/api/forward/remove', { method: 'POST', body: { local: btn.dataset.local } });
    loadForwards(serial);
  }));
}

async function addForward(serial) {
  const local = document.getElementById('fwd-local').value.trim();
  const remote = document.getElementById('fwd-remote').value.trim();
  if (!local || !remote) return;
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/forward`, { method: 'POST', body: { local, remote } });
  const data = await res.json();
  toast(data.ok ? 'Forward added' : `Failed: ${data.error}`, data.ok ? 'success' : 'error');
  loadForwards(serial);
}

async function loadReverses(serial) {
  const list = document.getElementById('rev-list');
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/reverse`);
  const data = await res.json();
  const rows = data.reverses || [];
  list.innerHTML = rows.length ? rows.map((r) => `
    <div style="display:flex; gap:8px; align-items:center;">${escapeHtml(r.remote)} ← ${escapeHtml(r.local)}
      <button data-remote="${escapeHtml(r.remote)}" class="rev-remove-btn">Remove</button></div>`).join('')
    : '<div class="muted">No reverses</div>';
  list.querySelectorAll('.rev-remove-btn').forEach((btn) => btn.addEventListener('click', async () => {
    await apiFetch(`/api/devices/${encodeURIComponent(serial)}/reverse/remove`, { method: 'POST', body: { remote: btn.dataset.remote } });
    loadReverses(serial);
  }));
}

async function addReverse(serial) {
  const remote = document.getElementById('rev-remote').value.trim();
  const local = document.getElementById('rev-local').value.trim();
  if (!remote || !local) return;
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/reverse`, { method: 'POST', body: { remote, local } });
  const data = await res.json();
  toast(data.ok ? 'Reverse added' : `Failed: ${data.error}`, data.ok ? 'success' : 'error');
  loadReverses(serial);
}

// --- Wireless tab ---------------------------------------------------------

function renderWirelessTab() {
  const pane = document.getElementById('tab-wireless');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  pane.innerHTML = `
    <div class="card-grid">
      <div class="card">
        <h4>Enable wireless debugging (USB device)</h4>
        <div style="display:flex; gap:8px; margin-bottom:8px;">
          <input type="number" id="wireless-port" value="5555" style="width:80px;">
          <button id="wireless-enable-btn" ${!device || device.state !== 'device' ? 'disabled' : ''}>Enable tcpip</button>
        </div>
        <div id="wireless-address-info" class="muted"></div>
      </div>
      <div class="card">
        <h4>Connect / disconnect</h4>
        <div style="display:flex; gap:8px; margin-bottom:8px;">
          <input type="text" id="wireless-address" placeholder="192.168.1.50:5555" style="flex:1;">
          <button id="wireless-connect-btn">Connect</button>
          <button id="wireless-disconnect-btn">Disconnect</button>
        </div>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h4>Known devices</h4>
        <div style="display:flex; gap:8px; margin-bottom:8px;">
          <input type="text" id="wireless-known-name" placeholder="Name" style="width:140px;">
          <input type="text" id="wireless-known-address" placeholder="192.168.1.50:5555" style="flex:1;">
          <button id="wireless-known-save-btn">Save</button>
          <button id="wireless-reconnect-all-btn">Reconnect all</button>
        </div>
        <div id="wireless-known-list"></div>
      </div>
    </div>
  `;
  wireWirelessControls(serial);
  loadKnownDevices();
  if (serial && device && device.state === 'device') loadWirelessAddress(serial);
}

function wireWirelessControls(serial) {
  const enableBtn = document.getElementById('wireless-enable-btn');
  if (enableBtn) enableBtn.addEventListener('click', async () => {
    const port = parseInt(document.getElementById('wireless-port').value, 10) || 5555;
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/wireless/enable-tcpip`, { method: 'POST', body: { port } });
    const data = await res.json();
    toast(data.ok ? 'tcpip mode enabled' : 'Failed to enable tcpip', data.ok ? 'success' : 'error');
    if (data.ok) loadWirelessAddress(serial, port);
  });
  document.getElementById('wireless-connect-btn').addEventListener('click', async () => {
    const address = document.getElementById('wireless-address').value.trim();
    if (!address) return;
    const res = await apiFetch('/api/wireless/connect', { method: 'POST', body: { address } });
    const data = await res.json();
    toast(data.ok ? 'Connected' : `Connect failed: ${data.output || data.error}`, data.ok ? 'success' : 'error');
    if (data.ok) refreshDevices();
  });
  document.getElementById('wireless-disconnect-btn').addEventListener('click', async () => {
    const address = document.getElementById('wireless-address').value.trim();
    if (!address) return;
    const res = await apiFetch('/api/wireless/disconnect', { method: 'POST', body: { address } });
    const data = await res.json();
    toast(data.ok ? 'Disconnected' : 'Disconnect failed', data.ok ? 'success' : 'error');
    if (data.ok) refreshDevices();
  });
  document.getElementById('wireless-known-save-btn').addEventListener('click', async () => {
    const name = document.getElementById('wireless-known-name').value.trim();
    const address = document.getElementById('wireless-known-address').value.trim();
    if (!name || !address) return;
    await apiFetch('/api/wireless/known', { method: 'POST', body: { name, address } });
    loadKnownDevices();
  });
  document.getElementById('wireless-reconnect-all-btn').addEventListener('click', async () => {
    const res = await apiFetch('/api/wireless/reconnect-all', { method: 'POST' });
    const data = await res.json();
    toast(`Reconnect attempted for ${data.results.length} device(s)`, 'info');
    refreshDevices();
  });
}

async function loadWirelessAddress(serial, port) {
  const el = document.getElementById('wireless-address-info');
  if (!el) return;
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/wireless/address?port=${port || 5555}`);
  const data = await res.json();
  el.textContent = data.address ? `Device address: ${data.address}` : 'Could not determine Wi-Fi IP (is Wi-Fi connected?)';
}

async function loadKnownDevices() {
  const list = document.getElementById('wireless-known-list');
  if (!list) return;
  const res = await apiFetch('/api/wireless/known');
  const data = await res.json();
  const entries = Object.entries(data.devices || {});
  list.innerHTML = entries.length ? entries.map(([name, addr]) => `
    <div style="display:flex; gap:8px; align-items:center;">
      <div style="flex:1;">${escapeHtml(name)} — ${escapeHtml(addr)}</div>
      <button data-name="${escapeHtml(name)}" class="known-delete-btn">Delete</button>
    </div>`).join('') : '<div class="muted">No known devices saved</div>';
  list.querySelectorAll('.known-delete-btn').forEach((btn) => btn.addEventListener('click', async () => {
    await apiFetch(`/api/wireless/known/${encodeURIComponent(btn.dataset.name)}`, { method: 'DELETE' });
    loadKnownDevices();
  }));
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => {
    if (tab === 'network') renderNetworkTab();
    if (tab === 'wireless') renderWirelessTab();
  });
  onDeviceChange(() => {
    if (currentTab() === 'network') renderNetworkTab();
    if (currentTab() === 'wireless') renderWirelessTab();
  });
});

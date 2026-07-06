// Device discovery/selection: populates the top device picker and the Devices tab.

let ADB_DEVICES = [];
const DEVICE_CHANGE_LISTENERS = [];
function onDeviceChange(fn) { DEVICE_CHANGE_LISTENERS.push(fn); }

function getSelectedSerial() {
  const sel = document.getElementById('device-select');
  return sel && sel.value ? sel.value : null;
}

function getSelectedDevice() {
  const serial = getSelectedSerial();
  return ADB_DEVICES.find((d) => d.serial === serial) || null;
}

function stateBadgeClass(state) {
  if (state === 'device') return 'green';
  if (state === 'unauthorized' || state === 'recovery') return 'yellow';
  return 'red';
}

async function refreshDevices() {
  const sel = document.getElementById('device-select');
  if (!sel) return;
  const previous = sel.value;
  try {
    const res = await apiFetch('/api/devices');
    if (res.status === 503) {
      sel.innerHTML = '<option value="">ADB not installed</option>';
      ADB_DEVICES = [];
      renderDevicesTab();
      DEVICE_CHANGE_LISTENERS.forEach((fn) => fn(null, null));
      return;
    }
    const data = await res.json();
    ADB_DEVICES = data.devices || [];
    if (!ADB_DEVICES.length) {
      sel.innerHTML = '<option value="">No devices connected</option>';
    } else {
      sel.innerHTML = ADB_DEVICES.map((d) => {
        const label = `${d.serial} — ${d.state}${d.model ? ' (' + d.model + ')' : ''}`;
        return `<option value="${escapeHtml(d.serial)}">${escapeHtml(label)}</option>`;
      }).join('');
      if (ADB_DEVICES.some((d) => d.serial === previous)) {
        sel.value = previous;
      } else {
        const firstOnline = ADB_DEVICES.find((d) => d.state === 'device');
        sel.value = (firstOnline || ADB_DEVICES[0]).serial;
      }
    }
    renderDevicesTab();
    DEVICE_CHANGE_LISTENERS.forEach((fn) => fn(getSelectedSerial(), getSelectedDevice()));
  } catch (err) {
    toast(`Failed to list devices: ${err}`, 'error');
  }
}

function renderDevicesTab() {
  const pane = document.getElementById('tab-devices');
  if (!pane) return;
  if (!ADB_DEVICES.length) {
    pane.innerHTML = `<div class="alert info">No devices detected — enable USB debugging on the device and reconnect the cable (or accept the RSA prompt if one appeared).</div>`;
    return;
  }
  const rows = ADB_DEVICES.map((d) => `
    <tr>
      <td>${escapeHtml(d.serial)}</td>
      <td><span class="badge ${stateBadgeClass(d.state)}">${escapeHtml(d.state)}</span></td>
      <td>${escapeHtml(d.model || '—')}</td>
      <td>${escapeHtml(d.product || '—')}</td>
      <td>${escapeHtml(d.transport_id || '—')}</td>
      <td>${d.is_wireless ? 'Wi-Fi' : 'USB'}</td>
    </tr>`).join('');
  pane.innerHTML = `
    <div class="panel-page">
      <section class="panel-section">
        <div class="section-head">
          <div>
            <h3>Connected devices</h3>
            <p class="section-desc">USB and Wi-Fi debugging targets currently visible to adb.</p>
          </div>
        </div>
        <div class="table-wrap auto-height">
          <table>
            <thead><tr><th>Serial</th><th>State</th><th>Model</th><th>Product</th><th>Transport</th><th>Link</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>
      <section id="device-detail-card" class="panel-section">Loading device details…</section>
    </div>
  `;
  loadDeviceDetail();
}

async function loadDeviceDetail() {
  const card = document.getElementById('device-detail-card');
  const serial = getSelectedSerial();
  if (!card || !serial) return;
  const device = getSelectedDevice();
  if (!device || device.state !== 'device') {
    card.innerHTML = `<div class="alert warn">Device is "${device ? device.state : 'unknown'}" — ${
      device && device.state === 'unauthorized'
        ? 'accept the RSA key prompt on the device screen to authorize this computer.'
        : 'reconnect or restart the device to bring it online.'
    }</div>`;
    return;
  }
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}`);
    const data = await res.json();
    if (!data.ok) { card.innerHTML = `<div class="alert error">${escapeHtml(data.error)}</div>`; return; }
    const p = data.device.properties;
    const b = data.device.battery;
    const volumes = data.device.storage.volumes.map((v) => `
      <tr><td>${escapeHtml(v.mounted_on)}</td><td>${escapeHtml(v.use_pct)}</td><td>${escapeHtml(v.available_kb)} KB free</td></tr>
    `).join('');
    card.innerHTML = `
      <div class="section-head">
        <div>
          <h3>${escapeHtml(p.model || serial)}</h3>
          <p class="section-desc">${escapeHtml(serial)}${data.device.is_wireless ? ' · Wi-Fi' : ' · USB'}</p>
        </div>
      </div>
      <div class="card-grid">
        ${statTileHtml('Manufacturer', escapeHtml(p.manufacturer || '—'))}
        ${statTileHtml('Android version', `${escapeHtml(p.android_version || '—')}`, `SDK ${escapeHtml(p.sdk_version || '—')}`)}
        ${statTileHtml('ABI', escapeHtml(p.abi || '—'))}
        ${statTileHtml('Battery', b.level != null ? b.level + '%' : '—', b.charging ? 'Charging' : '')}
        ${statTileHtml('Root', data.device.root_available ? '<span class="badge green">available</span>' : '<span class="badge red">unavailable</span>')}
      </div>
      <div class="table-wrap auto-height">
        <table><thead><tr><th>Mount</th><th>Used</th><th>Free</th></tr></thead><tbody>${volumes}</tbody></table>
      </div>
    `;
  } catch (err) {
    card.innerHTML = `<div class="alert error">Failed to load device details: ${escapeHtml(String(err))}</div>`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  refreshDevices();
  setInterval(refreshDevices, 5000);
  document.getElementById('refresh-devices-btn').addEventListener('click', refreshDevices);
  document.getElementById('device-select').addEventListener('change', () => {
    renderDevicesTab();
    DEVICE_CHANGE_LISTENERS.forEach((fn) => fn(getSelectedSerial(), getSelectedDevice()));
  });
  onTabChange((tab) => { if (tab === 'devices') renderDevicesTab(); });
});

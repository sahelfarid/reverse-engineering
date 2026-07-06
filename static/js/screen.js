// Screen tab: screenshot (+ continuous polling), recording, rotation, wake/sleep, brightness.

let screenPollTimer = null;

function renderScreenTab() {
  const pane = document.getElementById('tab-screen');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to use screen tools.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="card-grid">
      <div class="card" style="grid-column: span 2;">
        <div style="display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap;">
          <button id="screen-refresh-btn">Screenshot</button>
          <label><input type="checkbox" id="screen-continuous-toggle"> Continuous (2s)</label>
          <a id="screen-download-link" download="screenshot.png"><button type="button">Download PNG</button></a>
        </div>
        <img id="screen-preview" style="max-width:100%; max-height:60vh; border:1px solid var(--border); border-radius:8px;">
      </div>
      <div class="card">
        <h4>Recording</h4>
        <div style="display:flex; gap:8px; margin-bottom:8px;">
          <input type="number" id="screen-record-limit" value="60" min="1" max="180" style="width:70px;"> sec
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <button id="screen-record-start-btn">Start</button>
          <button id="screen-record-stop-btn">Stop</button>
          <button id="screen-record-pull-btn">Pull recording</button>
        </div>
        <div id="screen-record-status" class="muted" style="margin-top:8px;"></div>
      </div>
      <div class="card">
        <h4>Rotation</h4>
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
          <button data-deg="0">0°</button><button data-deg="90">90°</button>
          <button data-deg="180">180°</button><button data-deg="270">270°</button>
          <button id="screen-auto-rotate-btn">Auto</button>
        </div>
      </div>
      <div class="card">
        <h4>Power</h4>
        <div style="display:flex; gap:8px;">
          <button id="screen-wake-btn">Wake</button>
          <button id="screen-sleep-btn">Sleep</button>
        </div>
      </div>
      <div class="card">
        <h4>Brightness</h4>
        <input type="range" id="screen-brightness" min="0" max="255" value="128" style="width:100%;">
      </div>
    </div>
  `;
  wireScreenControls(serial);
  refreshScreenshot(serial);
}

function wireScreenControls(serial) {
  document.getElementById('screen-refresh-btn').addEventListener('click', () => refreshScreenshot(serial));
  document.getElementById('screen-continuous-toggle').addEventListener('change', (e) => {
    if (screenPollTimer) { clearInterval(screenPollTimer); screenPollTimer = null; }
    if (e.target.checked) screenPollTimer = setInterval(() => refreshScreenshot(serial), 2000);
  });
  document.getElementById('screen-record-start-btn').addEventListener('click', async () => {
    const limit = parseInt(document.getElementById('screen-record-limit').value, 10) || 60;
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/screen/record/start`, { method: 'POST', body: { time_limit_sec: limit } });
    const data = await res.json();
    document.getElementById('screen-record-status').textContent = data.ok ? `Recording (pid ${data.pid})…` : `Failed: ${data.error}`;
  });
  document.getElementById('screen-record-stop-btn').addEventListener('click', async () => {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/screen/record/stop`, { method: 'POST' });
    const data = await res.json();
    document.getElementById('screen-record-status').textContent = data.ok ? 'Stopped. Use "Pull recording" to download.' : `Failed: ${data.error}`;
  });
  document.getElementById('screen-record-pull-btn').addEventListener('click', () => {
    window.location.href = `/api/devices/${encodeURIComponent(serial)}/screen/record/pull`;
  });
  document.querySelectorAll('[data-deg]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/screen/rotate`, { method: 'POST', body: { degrees: parseInt(btn.dataset.deg, 10) } });
      const data = await res.json();
      toast(data.ok ? 'Rotated' : 'Rotate failed', data.ok ? 'success' : 'error');
    });
  });
  document.getElementById('screen-auto-rotate-btn').addEventListener('click', async () => {
    await apiFetch(`/api/devices/${encodeURIComponent(serial)}/screen/auto-rotate`, { method: 'POST' });
    toast('Auto-rotate enabled', 'success');
  });
  document.getElementById('screen-wake-btn').addEventListener('click', () => apiFetch(`/api/devices/${encodeURIComponent(serial)}/screen/wake`, { method: 'POST' }));
  document.getElementById('screen-sleep-btn').addEventListener('click', () => apiFetch(`/api/devices/${encodeURIComponent(serial)}/screen/sleep`, { method: 'POST' }));
  let brightnessDebounce = null;
  document.getElementById('screen-brightness').addEventListener('input', (e) => {
    clearTimeout(brightnessDebounce);
    const level = e.target.value;
    brightnessDebounce = setTimeout(() => {
      apiFetch(`/api/devices/${encodeURIComponent(serial)}/screen/brightness`, { method: 'POST', body: { level: parseInt(level, 10) } });
    }, 250);
  });
}

async function refreshScreenshot(serial) {
  const img = document.getElementById('screen-preview');
  const link = document.getElementById('screen-download-link');
  if (!img) return;
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/screen/screenshot`);
    if (!res.ok) { toast('Screenshot failed', 'error'); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    img.src = url;
    link.href = url;
  } catch (err) {
    toast(`Screenshot failed: ${err}`, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => {
    if (screenPollTimer) { clearInterval(screenPollTimer); screenPollTimer = null; }
    if (tab === 'screen') renderScreenTab();
  });
  onDeviceChange(() => { if (currentTab() === 'screen') renderScreenTab(); });
});

// Automation tab: click/drag a live screenshot to tap/swipe, send text/keyevents,
// record a step list, and save/play/import/export macros.

let automationRecording = false;
let automationSteps = [];
let automationScreenSize = { width: null, height: null };
let AUTOMATION_SUBNAV = null;

const COMMON_KEYEVENTS = [
  ['HOME', 'KEYCODE_HOME'], ['BACK', 'KEYCODE_BACK'], ['APP SWITCH', 'KEYCODE_APP_SWITCH'],
  ['POWER', 'KEYCODE_POWER'], ['VOL+', 'KEYCODE_VOLUME_UP'], ['VOL-', 'KEYCODE_VOLUME_DOWN'],
  ['ENTER', 'KEYCODE_ENTER'], ['DEL', 'KEYCODE_DEL'], ['MENU', 'KEYCODE_MENU'],
];

function renderAutomationTab() {
  const pane = document.getElementById('tab-automation');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device for input automation.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="panel-page">
      <div class="panel-header">
        <h2>Automation</h2>
        <p class="muted">Click/drag the live screenshot to tap/swipe, send text or keys, and record/replay macros.</p>
      </div>
      <section class="panel-section subnav-pinned">
        <div class="toolbar-row">
          <button id="automation-refresh-btn">Refresh preview</button>
          <label><input type="checkbox" id="automation-record-toggle"> Record actions into steps</label>
        </div>
        <div style="position:relative; display:inline-block;">
          <img id="automation-preview" style="max-width:100%; max-height:60vh; border:1px solid var(--border); border-radius:8px; cursor:crosshair;">
        </div>
        <div class="muted">Click = tap · Click-drag = swipe</div>
      </section>
      <div id="automation-subnav"></div>
    </div>
  `;
  wireAutomationCanvas(serial);
  AUTOMATION_SUBNAV = createSubNav(document.getElementById('automation-subnav'), 'adbpanel.subnav.automation', [
    { key: 'input', label: 'Input', render: (body) => renderAutomationInputView(body, serial) },
    { key: 'recorder', label: 'Recorder', render: (body) => renderAutomationRecorderView(body, serial) },
    { key: 'macros', label: 'Macros', render: (body) => renderAutomationMacrosView(body, serial) },
  ]);
  loadScreenSize(serial);
  refreshAutomationPreview(serial);
}

function renderAutomationInputView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <div class="toolbar-row">
        <input type="text" id="automation-text-input" placeholder="Text to type…" style="flex:1;">
        <button id="automation-text-btn">Send</button>
      </div>
      <div class="toolbar-row">
        ${COMMON_KEYEVENTS.map(([label, code]) => `<button data-code="${code}">${label}</button>`).join('')}
      </div>
    </section>`;
  document.getElementById('automation-text-btn').addEventListener('click', async () => {
    const text = document.getElementById('automation-text-input').value;
    if (!text) return;
    await apiFetch(`/api/devices/${encodeURIComponent(serial)}/input/text`, { method: 'POST', body: { text } });
    if (automationRecording) { automationSteps.push({ type: 'text', text }); renderStepsList(); }
  });
  body.querySelectorAll('button[data-code]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await apiFetch(`/api/devices/${encodeURIComponent(serial)}/input/keyevent`, { method: 'POST', body: { code: btn.dataset.code } });
      if (automationRecording) { automationSteps.push({ type: 'keyevent', code: btn.dataset.code }); renderStepsList(); }
    });
  });
}

function renderAutomationRecorderView(body, serial) {
  body.innerHTML = `
    <section class="panel-section">
      <div class="toolbar-row">
        <button id="automation-add-wait-btn">Add wait (500ms)</button>
        <button id="automation-play-btn">Play steps</button>
        <button id="automation-clear-steps-btn">Clear</button>
        <input type="text" id="automation-macro-name" placeholder="Macro name" style="width:140px;">
        <button id="automation-save-macro-btn">Save as macro</button>
        <button id="automation-export-btn">Export JSON</button>
        <label class="ghost-btn upload-label">Import JSON<input type="file" id="automation-import-input" accept="application/json" style="display:none;"></label>
      </div>
      <ol id="automation-steps-list" class="muted"></ol>
    </section>`;
  document.getElementById('automation-add-wait-btn').addEventListener('click', () => {
    automationSteps.push({ type: 'wait', wait_ms: 500 });
    renderStepsList();
  });
  document.getElementById('automation-clear-steps-btn').addEventListener('click', () => { automationSteps = []; renderStepsList(); });
  document.getElementById('automation-play-btn').addEventListener('click', () => playStepsDirect(serial));
  document.getElementById('automation-save-macro-btn').addEventListener('click', async () => {
    const name = document.getElementById('automation-macro-name').value.trim();
    if (!name || !automationSteps.length) return;
    const res = await apiFetch('/api/macros', { method: 'POST', body: { name, steps: automationSteps } });
    const data = await res.json();
    toast(data.ok ? 'Macro saved' : `Save failed: ${data.error}`, data.ok ? 'success' : 'error');
    if (AUTOMATION_SUBNAV) AUTOMATION_SUBNAV.activate('macros');
  });
  document.getElementById('automation-export-btn').addEventListener('click', () => {
    const blob = new Blob([JSON.stringify(automationSteps, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'macro-steps.json';
    a.click();
    URL.revokeObjectURL(a.href);
  });
  document.getElementById('automation-import-input').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      automationSteps = JSON.parse(await file.text());
      renderStepsList();
    } catch (err) { toast(`Invalid macro file: ${err}`, 'error'); }
    e.target.value = '';
  });
  renderStepsList();
}

function renderAutomationMacrosView(body, serial) {
  body.innerHTML = `<section class="panel-section"><div id="automation-macros-list">Loading…</div></section>`;
  loadMacrosList(serial);
}

async function loadScreenSize(serial) {
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/screen-size`);
    const data = await res.json();
    automationScreenSize = { width: data.width, height: data.height };
  } catch (e) { /* ignore */ }
}

async function refreshAutomationPreview(serial) {
  const img = document.getElementById('automation-preview');
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/screen/screenshot`);
    if (!res.ok) return;
    const blob = await res.blob();
    img.src = URL.createObjectURL(blob);
  } catch (e) { /* ignore */ }
}

function mapClientToDevice(img, clientX, clientY) {
  const rect = img.getBoundingClientRect();
  const scaleX = (automationScreenSize.width || img.naturalWidth) / rect.width;
  const scaleY = (automationScreenSize.height || img.naturalHeight) / rect.height;
  return { x: Math.round((clientX - rect.left) * scaleX), y: Math.round((clientY - rect.top) * scaleY) };
}

function wireAutomationCanvas(serial) {
  const img = document.getElementById('automation-preview');
  let dragStart = null;

  img.addEventListener('mousedown', (e) => { dragStart = mapClientToDevice(img, e.clientX, e.clientY); });
  img.addEventListener('mouseup', async (e) => {
    if (!dragStart) return;
    const end = mapClientToDevice(img, e.clientX, e.clientY);
    const dist = Math.hypot(end.x - dragStart.x, end.y - dragStart.y);
    if (dist < 10) {
      await apiFetch(`/api/devices/${encodeURIComponent(serial)}/input/tap`, { method: 'POST', body: dragStart });
      if (automationRecording) automationSteps.push({ type: 'tap', ...dragStart });
    } else {
      const body = { x1: dragStart.x, y1: dragStart.y, x2: end.x, y2: end.y, duration_ms: 300 };
      await apiFetch(`/api/devices/${encodeURIComponent(serial)}/input/swipe`, { method: 'POST', body });
      if (automationRecording) automationSteps.push({ type: 'swipe', ...body });
    }
    dragStart = null;
    renderStepsList();
    setTimeout(() => refreshAutomationPreview(serial), 400);
  });

  document.getElementById('automation-refresh-btn').addEventListener('click', () => refreshAutomationPreview(serial));
  document.getElementById('automation-record-toggle').addEventListener('change', (e) => { automationRecording = e.target.checked; });
}

async function playStepsDirect(serial) {
  if (!automationSteps.length) return;
  const tempName = '__adhoc_playback__';
  await apiFetch('/api/macros', { method: 'POST', body: { name: tempName, steps: automationSteps } });
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/macros/${encodeURIComponent(tempName)}/play`, { method: 'POST' });
  const data = await res.json();
  toast(data.ok ? 'Playback complete' : 'Playback had failures', data.ok ? 'success' : 'error');
  await apiFetch(`/api/macros/${encodeURIComponent(tempName)}`, { method: 'DELETE' });
}

function renderStepsList() {
  const list = document.getElementById('automation-steps-list');
  if (!list) return;
  list.innerHTML = automationSteps.map((s, i) => `<li>${escapeHtml(JSON.stringify(s))} <button data-idx="${i}" class="remove-step-btn">x</button></li>`).join('');
  list.querySelectorAll('.remove-step-btn').forEach((btn) => {
    btn.addEventListener('click', () => { automationSteps.splice(parseInt(btn.dataset.idx, 10), 1); renderStepsList(); });
  });
}

async function loadMacrosList(serial) {
  const container = document.getElementById('automation-macros-list');
  if (!container) return;
  const res = await apiFetch('/api/macros');
  const data = await res.json();
  const names = Object.keys(data.macros || {});
  if (!names.length) { container.innerHTML = `<div class="muted">No saved macros</div>`; return; }
  container.innerHTML = names.map((n) => `
    <div style="display:flex; gap:8px; align-items:center; margin-bottom:4px;">
      <div style="flex:1;">${escapeHtml(n)} <span class="muted">(${data.macros[n].length} steps)</span></div>
      <button data-name="${escapeHtml(n)}" data-act="play">Play</button>
      <button data-name="${escapeHtml(n)}" data-act="delete">Delete</button>
    </div>`).join('');
  container.querySelectorAll('button[data-act]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.name;
      if (btn.dataset.act === 'delete') {
        await apiFetch(`/api/macros/${encodeURIComponent(name)}`, { method: 'DELETE' });
      } else {
        const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/macros/${encodeURIComponent(name)}/play`, { method: 'POST' });
        const data2 = await res.json();
        toast(data2.ok ? `${name} played` : `${name} failed`, data2.ok ? 'success' : 'error');
      }
      loadMacrosList(serial);
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'automation') renderAutomationTab(); });
  onDeviceChange(() => { if (currentTab() === 'automation') renderAutomationTab(); });
});

// Properties tab: categorized getprop viewer with a search box.

let PROPERTIES_CACHE = null;

function renderPropertiesTab() {
  const pane = document.getElementById('tab-properties');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to view properties.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="card">
      <div style="display:flex; gap:8px; margin-bottom:10px;">
        <input type="text" id="properties-search" placeholder="Search key or value…" style="flex:1;">
        <button id="properties-refresh-btn">Refresh</button>
      </div>
      <div id="properties-body">Loading…</div>
    </div>
  `;
  document.getElementById('properties-refresh-btn').addEventListener('click', () => loadProperties(serial));
  document.getElementById('properties-search').addEventListener('input', renderPropertiesBody);
  loadProperties(serial);
}

async function loadProperties(serial) {
  const body = document.getElementById('properties-body');
  body.innerHTML = 'Loading…';
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/properties`);
    const data = await res.json();
    if (!data.ok) { body.innerHTML = `<div class="alert error">${escapeHtml(data.error)}</div>`; return; }
    PROPERTIES_CACHE = data.categories;
    renderPropertiesBody();
  } catch (err) {
    body.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

function renderPropertiesBody() {
  const body = document.getElementById('properties-body');
  if (!PROPERTIES_CACHE || !body) return;
  const query = (document.getElementById('properties-search').value || '').toLowerCase();
  const categoryOrder = Object.keys(PROPERTIES_CACHE).sort();
  const sections = categoryOrder.map((cat) => {
    const rows = PROPERTIES_CACHE[cat].filter((p) => !query || p.key.toLowerCase().includes(query) || p.value.toLowerCase().includes(query));
    if (!rows.length) return '';
    return `
      <div class="card">
        <h4>${escapeHtml(cat)} <span class="muted">(${rows.length})</span></h4>
        <table><tbody>${rows.map((p) => `<tr><td>${escapeHtml(p.key)}</td><td>${escapeHtml(p.value)}</td></tr>`).join('')}</tbody></table>
      </div>`;
  }).join('');
  body.innerHTML = sections || `<div class="alert info">No properties match "${escapeHtml(query)}"</div>`;
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'properties') renderPropertiesTab(); });
  onDeviceChange(() => { if (currentTab() === 'properties') renderPropertiesTab(); });
});

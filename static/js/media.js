// Media tab: thumbnail gallery for on-device Photos/Videos/Audio/Downloads/
// Documents. Reuses the existing files/browse + files/preview + files/download
// endpoints (via /api/backup/targets for canonical folder paths) -- no new
// backend routes.

const MEDIA_CATEGORY_TARGET_KEY = {
  photos: 'photos',
  videos: 'movies',
  audio: 'music',
  downloads: 'downloads',
  documents: 'documents',
};
const MEDIA_CATEGORY_LABEL = {
  photos: 'Photos',
  videos: 'Videos',
  audio: 'Audio',
  downloads: 'Downloads',
  documents: 'Documents',
};

let MEDIA_TARGETS = null;
const MEDIA_SELECTED = new Set();

async function getMediaTargets() {
  if (MEDIA_TARGETS) return MEDIA_TARGETS;
  const res = await apiFetch('/api/backup/targets');
  const data = await res.json();
  MEDIA_TARGETS = data.targets || {};
  return MEDIA_TARGETS;
}

function renderMediaTab() {
  const pane = document.getElementById('tab-media');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to browse media.</div>`;
    return;
  }
  pane.innerHTML = `
    <div class="panel-page">
      <div class="panel-header">
        <h2>Media</h2>
        <p class="muted">Browse photos, videos, audio, downloads, and documents on the device.</p>
      </div>
      <div id="media-subnav"></div>
    </div>
  `;
  createSubNav(document.getElementById('media-subnav'), 'adbpanel.subnav.media', Object.keys(MEDIA_CATEGORY_LABEL).map((key) => ({
    key, label: MEDIA_CATEGORY_LABEL[key], render: (body) => renderMediaCategory(body, serial, key),
  })));
}

async function renderMediaCategory(body, serial, category) {
  body.innerHTML = `<div class="panel-section"><div class="muted">Loading…</div></div>`;
  MEDIA_SELECTED.clear();
  const targets = await getMediaTargets();
  const path = targets[MEDIA_CATEGORY_TARGET_KEY[category]];
  if (!path) { body.innerHTML = `<div class="alert error">No known folder for ${escapeHtml(MEDIA_CATEGORY_LABEL[category])}.</div>`; return; }
  const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/files/browse?path=${encodeURIComponent(path)}`);
  const data = await res.json();
  if (!data.ok) {
    const messages = { permission_denied: 'Permission denied listing this folder.', not_found: 'That folder does not exist on this device.' };
    body.innerHTML = `<section class="panel-section"><div class="alert error">${escapeHtml(messages[data.error] || data.error || 'Failed to list folder')}</div></section>`;
    return;
  }
  const files = (data.entries || []).filter((e) => e.type !== 'dir');
  body.innerHTML = `
    <section class="panel-section">
      <div class="section-head">
        <div>
          <h3>${escapeHtml(MEDIA_CATEGORY_LABEL[category])}</h3>
          <p class="section-desc">${escapeHtml(path)}</p>
        </div>
        <div id="media-selection-bar"></div>
      </div>
      ${files.length ? `<div class="media-grid" id="media-grid"></div>` : `<div class="muted">No files found in this folder.</div>`}
    </section>
  `;
  if (!files.length) return;
  const grid = document.getElementById('media-grid');
  grid.innerHTML = files.map((e) => {
    const fullPath = path.replace(/\/$/, '') + '/' + e.name;
    const isImage = /\.(png|jpe?g|gif|webp|bmp)$/i.test(e.name);
    const previewUrl = `/api/devices/${encodeURIComponent(serial)}/files/preview?path=${encodeURIComponent(fullPath)}`;
    const ext = (e.name.split('.').pop() || '?').slice(0, 4).toUpperCase();
    return `
      <div class="media-tile" data-path="${escapeHtml(fullPath)}">
        <label class="media-tile-select"><input type="checkbox" class="media-select-cb" data-path="${escapeHtml(fullPath)}"></label>
        <div class="media-tile-thumb">
          ${isImage ? `<img src="${previewUrl}" loading="lazy" alt="${escapeHtml(e.name)}">` : `<div class="media-tile-icon">${escapeHtml(ext)}</div>`}
        </div>
        <div class="media-tile-name" title="${escapeHtml(e.name)}">${escapeHtml(e.name)}</div>
        <div class="media-tile-size muted">${e.size != null ? formatBytes(e.size) : ''}</div>
      </div>`;
  }).join('');
  grid.querySelectorAll('.media-tile-thumb').forEach((thumb) => {
    thumb.addEventListener('click', () => openMediaPreview(serial, thumb.closest('.media-tile').dataset.path));
  });
  grid.querySelectorAll('.media-select-cb').forEach((cb) => {
    cb.addEventListener('click', (e) => e.stopPropagation());
    cb.addEventListener('change', () => {
      if (cb.checked) MEDIA_SELECTED.add(cb.dataset.path); else MEDIA_SELECTED.delete(cb.dataset.path);
      updateMediaSelectionBar(serial);
    });
  });
  updateMediaSelectionBar(serial);
}

function updateMediaSelectionBar(serial) {
  const bar = document.getElementById('media-selection-bar');
  if (!bar) return;
  const n = MEDIA_SELECTED.size;
  bar.innerHTML = n
    ? `<span class="muted">${n} selected</span> <button type="button" id="media-download-selected-btn" class="primary-btn">Download selected</button>`
    : '';
  const btn = document.getElementById('media-download-selected-btn');
  if (btn) btn.addEventListener('click', () => downloadSelectedMedia(serial));
}

function downloadSelectedMedia(serial) {
  // No batch-zip endpoint exists for an arbitrary cross-folder file selection --
  // fire one download per selected file via the existing single-file endpoint,
  // staggered slightly so each navigation has a moment to start. Browsers may
  // still prompt for permission to allow multiple simultaneous downloads.
  const paths = Array.from(MEDIA_SELECTED);
  paths.forEach((path, i) => {
    setTimeout(() => {
      window.location.href = `/api/devices/${encodeURIComponent(serial)}/files/download?path=${encodeURIComponent(path)}`;
    }, i * 300);
  });
  toast(`Downloading ${paths.length} file(s) — your browser may ask to allow multiple downloads`, 'info');
}

async function openMediaPreview(serial, path) {
  const modalEl = openModal(path.split('/').pop(), 'Loading preview…');
  const body = modalEl.querySelector('.modal-body');
  const url = `/api/devices/${encodeURIComponent(serial)}/files/preview?path=${encodeURIComponent(path)}`;
  try {
    const res = await fetch(url, { credentials: 'same-origin' });
    const contentType = res.headers.get('Content-Type') || '';
    if (contentType.startsWith('image/')) {
      body.innerHTML = `<img src="${url}" style="max-width:100%; max-height:70vh;">`;
      return;
    }
    const data = await res.json();
    if (!data.ok) {
      const downloadUrl = url.replace('/files/preview', '/files/download');
      body.innerHTML = `<div class="alert info">Preview not available for this file type.</div><a href="${downloadUrl}"><button type="button" class="primary-btn">Download</button></a>`;
      return;
    }
    body.innerHTML = `<pre class="shell-output">${escapeHtml(data.content)}</pre>${data.truncated ? '<div class="muted">Truncated preview…</div>' : ''}`;
  } catch (err) {
    body.innerHTML = `<div class="alert error">${escapeHtml(String(err))}</div>`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'media') renderMediaTab(); });
  onDeviceChange(() => { if (currentTab() === 'media') renderMediaTab(); });
});

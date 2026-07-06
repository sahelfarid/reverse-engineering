// Settings tab: app config form, change password, audit log viewer.

function renderSettingsTab() {
  const pane = document.getElementById('tab-settings');
  if (!pane) return;
  pane.innerHTML = `
    <div class="card-grid">
      <div class="card">
        <h4>General</h4>
        <div id="settings-form">Loading…</div>
        <button id="settings-save-btn" style="margin-top:8px;">Save</button>
      </div>
      <div class="card">
        <h4>Change password</h4>
        <input type="password" id="settings-current-password" placeholder="Current password (blank if none set yet)" style="width:100%; margin-bottom:6px;">
        <input type="password" id="settings-new-password" placeholder="New password (min 6 chars)" style="width:100%; margin-bottom:6px;">
        <button id="settings-change-password-btn">Change password</button>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h4>Background jobs</h4>
        <div class="muted">APK installs, folder downloads, and app-data exports triggered "as a background job" show up here with progress and a Cancel/Download action.</div>
        <button id="settings-jobs-refresh-btn" style="margin-top:6px;">Refresh</button>
        <div id="settings-jobs-body" style="margin-top:8px;"></div>
      </div>
      <div class="card" style="grid-column: span 2;">
        <h4>Audit log (privileged actions)</h4>
        <button id="settings-audit-refresh-btn">Refresh</button>
        <div id="settings-audit-body" style="margin-top:8px; max-height:300px; overflow-y:auto;"></div>
      </div>
    </div>
  `;
  loadSettingsForm();
  loadAuditLog();
  loadJobsPanel();
  document.getElementById('settings-save-btn').addEventListener('click', saveSettingsForm);
  document.getElementById('settings-change-password-btn').addEventListener('click', changePassword);
  document.getElementById('settings-audit-refresh-btn').addEventListener('click', loadAuditLog);
  document.getElementById('settings-jobs-refresh-btn').addEventListener('click', loadJobsPanel);
}

let jobsPollTimer = null;

async function loadJobsPanel() {
  const body = document.getElementById('settings-jobs-body');
  if (!body) return;
  const res = await apiFetch('/api/jobs');
  const data = await res.json();
  const jobsList = data.jobs || [];
  if (!jobsList.length) { body.innerHTML = '<div class="muted">No jobs yet</div>'; }
  else {
    body.innerHTML = jobsList.map((j) => `
      <div style="display:flex; gap:8px; align-items:center; margin-bottom:6px;">
        <div style="width:140px;">${escapeHtml(j.type)}</div>
        <div style="flex:1;">${escapeHtml(j.label || '')} <span class="badge ${j.status === 'done' ? 'green' : j.status === 'error' ? 'red' : 'yellow'}">${escapeHtml(j.status)}</span> ${j.progress != null ? j.progress + '%' : ''}</div>
        ${j.status === 'running' || j.status === 'pending' ? `<button data-job="${j.id}" data-act="cancel">Cancel</button>` : ''}
        ${j.status === 'done' && j.result && j.result.file_path ? `<button data-job="${j.id}" data-act="download">Download</button>` : ''}
        ${j.status === 'error' ? `<span class="muted">${escapeHtml(j.error || '')}</span>` : ''}
      </div>`).join('');
    body.querySelectorAll('button[data-act]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        if (btn.dataset.act === 'cancel') {
          await apiFetch(`/api/jobs/${btn.dataset.job}/cancel`, { method: 'POST' });
          loadJobsPanel();
        } else {
          window.location.href = `/api/jobs/${btn.dataset.job}/download`;
        }
      });
    });
  }
  const hasActive = jobsList.some((j) => j.status === 'running' || j.status === 'pending');
  if (hasActive && !jobsPollTimer) {
    jobsPollTimer = setInterval(loadJobsPanel, 2000);
  } else if (!hasActive && jobsPollTimer) {
    clearInterval(jobsPollTimer);
    jobsPollTimer = null;
  }
}

async function loadSettingsForm() {
  const container = document.getElementById('settings-form');
  const res = await apiFetch('/api/settings');
  const data = await res.json();
  const s = data.settings;
  container.innerHTML = `
    <label>ADB path override<br><input type="text" id="set-adb-path" value="${escapeHtml(s.adb_path_override || '')}" placeholder="(auto-detect)" style="width:100%;"></label><br><br>
    <label>Android SDK path override<br><input type="text" id="set-android-sdk-path" value="${escapeHtml(s.android_sdk_path_override || '')}" placeholder="(ANDROID_HOME / ANDROID_SDK_ROOT)" style="width:100%;"></label><br><br>
    <label>Refresh interval (ms)<br><input type="number" id="set-refresh-interval" value="${s.refresh_interval_ms}" style="width:100%;"></label><br><br>
    <label>Shell timeout (sec)<br><input type="number" id="set-shell-timeout" value="${s.shell_timeout_sec}" style="width:100%;"></label><br><br>
    <label>Max log lines<br><input type="number" id="set-max-log" value="${s.max_log_lines}" style="width:100%;"></label><br><br>
    <label>Max upload size (MB)<br><input type="number" id="set-max-upload" value="${s.max_upload_mb}" style="width:100%;"></label><br><br>
    <label>Download directory<br><input type="text" id="set-download-dir" value="${escapeHtml(s.download_dir)}" style="width:100%;"></label><br><br>
    <label>Theme<br>
      <select id="set-theme" style="width:100%;">
        <option value="dark" ${s.theme === 'dark' ? 'selected' : ''}>Dark</option>
        <option value="light" ${s.theme === 'light' ? 'selected' : ''}>Light</option>
      </select>
    </label>
  `;
  window.APP_SETTINGS = s;
}

async function saveSettingsForm() {
  const body = {
    adb_path_override: document.getElementById('set-adb-path').value.trim() || null,
    android_sdk_path_override: document.getElementById('set-android-sdk-path').value.trim() || null,
    refresh_interval_ms: parseInt(document.getElementById('set-refresh-interval').value, 10) || 4000,
    shell_timeout_sec: parseInt(document.getElementById('set-shell-timeout').value, 10) || 20,
    max_log_lines: parseInt(document.getElementById('set-max-log').value, 10) || 5000,
    max_upload_mb: parseInt(document.getElementById('set-max-upload').value, 10) || 200,
    download_dir: document.getElementById('set-download-dir').value.trim(),
    theme: document.getElementById('set-theme').value,
  };
  const res = await apiFetch('/api/settings', { method: 'POST', body });
  const data = await res.json();
  if (data.ok) {
    toast('Settings saved', 'success');
    window.APP_SETTINGS = data.settings;
    document.documentElement.setAttribute('data-theme', data.settings.theme);
  } else {
    toast(`Save failed: ${data.error}`, 'error');
  }
}

async function changePassword() {
  const current_password = document.getElementById('settings-current-password').value;
  const new_password = document.getElementById('settings-new-password').value;
  if (!new_password) return; // current_password may legitimately be blank if none is set yet
  const res = await apiFetch('/api/auth/change-password', { method: 'POST', body: { current_password, new_password } });
  const data = await res.json();
  toast(data.ok ? 'Password changed' : `Failed: ${data.error}`, data.ok ? 'success' : 'error');
  if (data.ok) {
    document.getElementById('settings-current-password').value = '';
    document.getElementById('settings-new-password').value = '';
  }
}

async function loadAuditLog() {
  const body = document.getElementById('settings-audit-body');
  const res = await apiFetch('/api/audit');
  const data = await res.json();
  const entries = (data.entries || []).slice().reverse();
  body.innerHTML = entries.length ? `<table><thead><tr><th>Time</th><th>Action</th><th>Details</th></tr></thead><tbody>${entries.map((e) => `
    <tr><td>${escapeHtml(e.ts)}</td><td>${escapeHtml(e.action)}</td><td>${escapeHtml(JSON.stringify(e.details))}</td></tr>`).join('')}</tbody></table>` : '<div class="muted">No audit entries yet</div>';
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => {
    if (tab === 'settings') { renderSettingsTab(); }
    else if (jobsPollTimer) { clearInterval(jobsPollTimer); jobsPollTimer = null; }
  });
});

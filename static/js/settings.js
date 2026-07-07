// Settings tab: app config form, change password, audit log viewer.

function renderSettingsTab() {
  const pane = document.getElementById('tab-settings');
  if (!pane) return;
  pane.innerHTML = `
    <div class="panel-page">
      <div class="panel-header">
        <h2>Settings</h2>
        <p class="muted">Configure paths and limits, rotate credentials, and review privileged activity on this panel.</p>
      </div>
      <div class="panel-grid settings-grid">
        <section class="panel-section settings-tooling">
          <div class="section-head">
            <div>
              <h3>Tooling</h3>
              <p class="section-desc">External tool status. Installed tools stay here only; anything needing attention also stays in the topbar.</p>
            </div>
          </div>
          <div class="card-grid">
            <div id="adb-status-card-settings" class="status-card" data-tool-status="adb" data-tool-status-scope="settings">Checking…</div>
            <div id="apktool-status-card-settings" class="status-card" data-tool-status="apktool" data-tool-status-scope="settings">Checking…</div>
            <div id="jadx-status-card-settings" class="status-card" data-tool-status="jadx" data-tool-status-scope="settings">Checking…</div>
            <div id="frida-tool-status-card-settings" class="status-card" data-tool-status="frida" data-tool-status-scope="settings">Checking…</div>
          </div>
        </section>

        <section class="panel-section settings-general">
          <div class="section-head">
            <div>
              <h3>General</h3>
              <p class="section-desc">Paths, timeouts, and limits used across the panel.</p>
            </div>
          </div>
          <div id="settings-form" class="field-grid">Loading…</div>
          <div class="section-actions">
            <span id="settings-dirty-indicator" class="dirty-indicator" hidden>Unsaved changes</span>
            <button id="settings-save-btn" class="primary-btn">Save changes</button>
          </div>
        </section>

        <section class="panel-section settings-security">
          <div class="section-head">
            <div>
              <h3>Change password</h3>
              <p class="section-desc">Update the credential used to access this panel.</p>
            </div>
          </div>
          <div class="field-grid single-col">
            <div class="field">
              <label for="settings-current-password">Current password</label>
              <div class="input-wrap has-toggle">
                <input type="password" id="settings-current-password" placeholder="Blank if none set yet" autocomplete="current-password">
                <button type="button" class="toggle-visibility" data-target="settings-current-password">Show</button>
              </div>
            </div>
            <div class="field">
              <label for="settings-new-password">New password</label>
              <div class="input-wrap has-toggle">
                <input type="password" id="settings-new-password" placeholder="Min 6 characters" autocomplete="new-password">
                <button type="button" class="toggle-visibility" data-target="settings-new-password">Show</button>
              </div>
              <span class="field-hint">Minimum 6 characters.</span>
            </div>
            <div class="field">
              <label for="settings-confirm-password">Confirm new password</label>
              <div class="input-wrap has-toggle">
                <input type="password" id="settings-confirm-password" placeholder="Repeat new password" autocomplete="new-password">
                <button type="button" class="toggle-visibility" data-target="settings-confirm-password">Show</button>
              </div>
              <span id="settings-password-error" class="field-error" hidden></span>
            </div>
          </div>
          <div class="section-actions">
            <button id="settings-change-password-btn" class="primary-btn">Change password</button>
          </div>
        </section>

        <section class="panel-section settings-jobs">
          <div class="section-head">
            <div>
              <h3>Background jobs</h3>
              <p class="section-desc">APK installs, folder downloads, and app-data exports triggered as a background job show up here with progress and a Cancel/Download action.</p>
            </div>
            <button id="settings-jobs-refresh-btn" class="ghost-btn small">Refresh</button>
          </div>
          <div id="settings-jobs-body"></div>
        </section>

        <section class="panel-section settings-audit">
          <div class="section-head">
            <div>
              <h3>Audit log</h3>
              <p class="section-desc">Privileged actions performed on this panel: authentication, settings changes, and destructive operations.</p>
            </div>
            <button id="settings-audit-refresh-btn" class="ghost-btn small">Refresh</button>
          </div>
          <div id="settings-audit-body"></div>
        </section>
      </div>
    </div>
  `;
  loadSettingsForm();
  loadAuditLog();
  loadJobsPanel();
  refreshAdbStatus();
  refreshApktoolStatus();
  refreshJadxToolStatus();
  refreshFridaToolStatus();
  document.getElementById('settings-save-btn').addEventListener('click', saveSettingsForm);
  document.getElementById('settings-change-password-btn').addEventListener('click', changePassword);
  document.getElementById('settings-audit-refresh-btn').addEventListener('click', loadAuditLog);
  document.getElementById('settings-jobs-refresh-btn').addEventListener('click', loadJobsPanel);
  pane.querySelectorAll('.toggle-visibility').forEach((btn) => {
    btn.addEventListener('click', () => {
      const input = document.getElementById(btn.dataset.target);
      const showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      btn.textContent = showing ? 'Show' : 'Hide';
    });
  });
}

let jobsPollTimer = null;

function jobProgressHTML(j) {
  if (j.status !== 'running' && j.status !== 'pending') return '';
  const pct = j.progress != null ? j.progress : 0;
  return `<div class="job-progress-track"><div class="job-progress-fill" style="width:${pct}%;"></div></div>`;
}

async function loadJobsPanel() {
  const body = document.getElementById('settings-jobs-body');
  if (!body) return;
  const res = await apiFetch('/api/jobs');
  const data = await res.json();
  const jobsList = data.jobs || [];
  if (!jobsList.length) { body.innerHTML = '<div class="muted">No jobs yet</div>'; }
  else {
    body.innerHTML = jobsList.map((j) => `
      <div class="job-row">
        <div class="job-type">${escapeHtml(j.type)}</div>
        <div class="job-info">
          <div class="job-info-top">
            <span class="job-label">${escapeHtml(j.label || '')}</span>
            <span class="badge ${j.status === 'done' ? 'green' : j.status === 'error' ? 'red' : 'yellow'}">${escapeHtml(j.status)}</span>
            ${j.progress != null && (j.status === 'running' || j.status === 'pending') ? `<span class="muted">${j.progress}%</span>` : ''}
            ${j.status === 'error' ? `<span class="muted">${escapeHtml(j.error || '')}</span>` : ''}
          </div>
          ${jobProgressHTML(j)}
        </div>
        <div class="job-actions">
          ${j.status === 'running' || j.status === 'pending' ? `<button data-job="${j.id}" data-act="cancel">Cancel</button>` : ''}
          ${j.status === 'done' && j.result && j.result.file_path ? `<button data-job="${j.id}" data-act="download">Download</button>` : ''}
        </div>
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

const SETTINGS_FIELDS = [
  { id: 'set-adb-path', key: 'adb_path_override', label: 'ADB path override', type: 'text', mono: true,
    hint: 'Leave blank to auto-detect from PATH.' },
  { id: 'set-android-sdk-path', key: 'android_sdk_path_override', label: 'Android SDK path override', type: 'text', mono: true,
    hint: 'Overrides ANDROID_HOME / ANDROID_SDK_ROOT.' },
  { id: 'set-jadx-path', key: 'jadx_path_override', label: 'jadx path override', type: 'text', mono: true,
    hint: 'Leave blank to auto-detect from PATH, then the managed vendor/jadx install.' },
  { id: 'set-refresh-interval', key: 'refresh_interval_ms', label: 'Refresh interval', type: 'number', unit: 'ms',
    hint: 'How often device and tool status is polled.' },
  { id: 'set-shell-timeout', key: 'shell_timeout_sec', label: 'Shell timeout', type: 'number', unit: 'sec',
    hint: 'Max time a shell command may run before being killed.' },
  { id: 'set-max-log', key: 'max_log_lines', label: 'Max log lines', type: 'number',
    hint: 'Logcat buffer cap before older lines are trimmed.' },
  { id: 'set-max-upload', key: 'max_upload_mb', label: 'Max upload size', type: 'number', unit: 'MB',
    hint: 'Largest file accepted for APK install / push.' },
  { id: 'set-download-dir', key: 'download_dir', label: 'Download directory', type: 'text', mono: true, wide: true,
    hint: 'Where exported files are saved on this machine.' },
];

function fieldHTML(f, value) {
  return `
    <div class="field${f.wide ? ' field-wide' : ''}">
      <label for="${f.id}">${escapeHtml(f.label)}</label>
      <div class="input-wrap${f.unit ? ' has-unit' : ''}">
        <input type="${f.type}" id="${f.id}" value="${escapeHtml(String(value ?? ''))}"
          class="${f.mono ? 'mono-input' : ''}" placeholder="${f.type === 'text' ? '(auto-detect)' : ''}">
        ${f.unit ? `<span class="unit">${f.unit}</span>` : ''}
      </div>
      ${f.hint ? `<span class="field-hint">${escapeHtml(f.hint)}</span>` : ''}
    </div>`;
}

function collectSettingsFormValues() {
  const values = {};
  SETTINGS_FIELDS.forEach((f) => {
    const el = document.getElementById(f.id);
    if (!el) return;
    values[f.key] = f.type === 'number' ? (parseInt(el.value, 10) || 0) : el.value.trim();
  });
  const themeEl = document.getElementById('set-theme');
  if (themeEl) values.theme = themeEl.value;
  return values;
}

let settingsInitialSnapshot = '';

function refreshDirtyIndicator() {
  const indicator = document.getElementById('settings-dirty-indicator');
  if (!indicator) return;
  const isDirty = JSON.stringify(collectSettingsFormValues()) !== settingsInitialSnapshot;
  indicator.hidden = !isDirty;
}

async function loadSettingsForm() {
  const container = document.getElementById('settings-form');
  const res = await apiFetch('/api/settings');
  const data = await res.json();
  const s = data.settings;
  container.innerHTML = `
    ${SETTINGS_FIELDS.map((f) => fieldHTML(f, s[f.key])).join('')}
    <div class="field">
      <label for="set-theme">Theme</label>
      <select id="set-theme">
        <option value="dark" ${s.theme === 'dark' ? 'selected' : ''}>Dark</option>
        <option value="light" ${s.theme === 'light' ? 'selected' : ''}>Light</option>
        <option value="system" ${s.theme === 'system' ? 'selected' : ''}>System (follow OS)</option>
      </select>
      <span class="field-hint">"System" follows your OS light/dark setting.</span>
    </div>
  `;
  window.APP_SETTINGS = s;
  settingsInitialSnapshot = JSON.stringify(collectSettingsFormValues());
  refreshDirtyIndicator();
  container.querySelectorAll('input, select').forEach((el) => {
    el.addEventListener('input', refreshDirtyIndicator);
    el.addEventListener('change', refreshDirtyIndicator);
  });
}

async function saveSettingsForm() {
  const values = collectSettingsFormValues();
  const body = {
    adb_path_override: values.adb_path_override || null,
    android_sdk_path_override: values.android_sdk_path_override || null,
    jadx_path_override: values.jadx_path_override || null,
    refresh_interval_ms: values.refresh_interval_ms || 4000,
    shell_timeout_sec: values.shell_timeout_sec || 20,
    max_log_lines: values.max_log_lines || 5000,
    max_upload_mb: values.max_upload_mb || 200,
    download_dir: values.download_dir,
    theme: values.theme,
  };
  const res = await apiFetch('/api/settings', { method: 'POST', body });
  const data = await res.json();
  if (data.ok) {
    toast('Settings saved', 'success');
    window.APP_SETTINGS = data.settings;
    settingsInitialSnapshot = JSON.stringify(collectSettingsFormValues());
    refreshDirtyIndicator();
    if (window.setThemeMode) window.setThemeMode(data.settings.theme);
    else document.documentElement.setAttribute('data-theme', data.settings.theme);
  } else {
    toast(`Save failed: ${data.error}`, 'error');
  }
}

async function changePassword() {
  const current_password = document.getElementById('settings-current-password').value;
  const new_password = document.getElementById('settings-new-password').value;
  const confirm_password = document.getElementById('settings-confirm-password').value;
  const errorEl = document.getElementById('settings-password-error');
  if (!new_password) return; // current_password may legitimately be blank if none is set yet
  if (new_password !== confirm_password) {
    errorEl.textContent = 'Passwords do not match.';
    errorEl.hidden = false;
    return;
  }
  errorEl.hidden = true;
  const res = await apiFetch('/api/auth/change-password', { method: 'POST', body: { current_password, new_password } });
  const data = await res.json();
  toast(data.ok ? 'Password changed' : `Failed: ${data.error}`, data.ok ? 'success' : 'error');
  if (data.ok) {
    document.getElementById('settings-current-password').value = '';
    document.getElementById('settings-new-password').value = '';
    document.getElementById('settings-confirm-password').value = '';
  }
}

function auditActionBadgeClass(action) {
  if (action.includes('password') || action.includes('delete') || action.includes('remove')) return 'red';
  if (action.includes('auth')) return 'green';
  if (action.includes('settings') || action.includes('update')) return 'blue';
  return 'gray';
}

async function loadAuditLog() {
  const body = document.getElementById('settings-audit-body');
  const res = await apiFetch('/api/audit');
  const data = await res.json();
  const entries = (data.entries || []).slice().reverse();
  if (!entries.length) { body.innerHTML = '<div class="muted">No audit entries yet</div>'; return; }
  body.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Time</th><th>Action</th><th>Details</th></tr></thead><tbody>${entries.map((e) => {
    const [date, time] = String(e.ts).split('T');
    return `<tr>
      <td class="audit-time"><span class="audit-date">${escapeHtml(date || e.ts)}</span>${time ? ` ${escapeHtml(time.replace(/\.\d+/, ''))}` : ''}</td>
      <td><span class="badge ${auditActionBadgeClass(e.action)}">${escapeHtml(e.action)}</span></td>
      <td class="audit-details">${escapeHtml(JSON.stringify(e.details))}</td>
    </tr>`;
  }).join('')}</tbody></table></div>`;
  body.querySelectorAll('td.audit-details').forEach((cell) => {
    cell.addEventListener('click', () => cell.classList.toggle('expanded'));
  });
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => {
    if (tab === 'settings') { renderSettingsTab(); }
    else if (jobsPollTimer) { clearInterval(jobsPollTimer); jobsPollTimer = null; }
  });
});

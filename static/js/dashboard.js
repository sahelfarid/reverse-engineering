// Dashboard tab: live overview cards for the selected device.

let dashboardTimer = null;

function dashboardCardHtml(title, value, sub) {
  return `<div class="card"><div class="muted">${escapeHtml(title)}</div><h2>${value}</h2>${sub ? `<div class="muted">${sub}</div>` : ''}</div>`;
}

async function renderDashboardTab() {
  const pane = document.getElementById('tab-dashboard');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();

  if (!serial || !device) {
    pane.innerHTML = `<div class="alert info">No devices detected — enable USB debugging and reconnect.</div>`;
    return;
  }
  if (device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Selected device is "${escapeHtml(device.state)}" — connect an authorized device to see live stats.</div>`;
    return;
  }

  try {
    const [detailRes, overviewRes] = await Promise.all([
      apiFetch(`/api/devices/${encodeURIComponent(serial)}`),
      apiFetch(`/api/devices/${encodeURIComponent(serial)}/overview`),
    ]);
    const detail = await detailRes.json();
    const overview = await overviewRes.json();
    if (!detail.ok || !overview.ok) {
      pane.innerHTML = `<div class="alert error">${escapeHtml(detail.error || overview.error || 'failed to load')}</div>`;
      return;
    }
    const b = detail.device.battery;
    const vol = detail.device.storage.volumes.find((v) => v.mounted_on === '/data') || detail.device.storage.volumes[0];
    const cm = overview.overview.cpu_mem;
    const apps = overview.overview.apps;
    const screen = overview.overview.screen;
    const fg = overview.overview.foreground;
    const wifi = overview.overview.wifi;
    const memPct = cm.mem_total_kb && cm.mem_available_kb
      ? Math.round(100 * (1 - cm.mem_available_kb / cm.mem_total_kb)) : null;

    pane.innerHTML = `
      <div class="card-grid">
        ${dashboardCardHtml('Connected devices', ADB_DEVICES.filter((d) => d.state === 'device').length, `${ADB_DEVICES.length} total`)}
        ${dashboardCardHtml('Battery', b.level != null ? b.level + '%' : '—', b.charging ? 'Charging' : (b.status || ''))}
        ${dashboardCardHtml('Storage', vol ? vol.use_pct : '—', vol ? `${escapeHtml(vol.mounted_on)} · ${formatBytes(Number(vol.available_kb) * 1024)} free` : '')}
        ${dashboardCardHtml('Memory', memPct != null ? memPct + '%' : '—', cm.mem_available_kb ? `${formatBytes(cm.mem_available_kb * 1024)} available` : '')}
        ${dashboardCardHtml('CPU load', cm.load_1m || '—', cm.load_5m ? `5m: ${cm.load_5m}, 15m: ${cm.load_15m}` : '')}
        ${dashboardCardHtml('Running apps', apps.user_apps != null ? apps.user_apps : '—', apps.total_apps != null ? `${apps.total_apps} incl. system` : '')}
        ${dashboardCardHtml('Link', device.is_wireless ? 'Wi-Fi' : 'USB', wifi.enabled == null ? '' : `Wi-Fi radio ${wifi.enabled ? 'on' : 'off'}`)}
        ${dashboardCardHtml('Screen', screen.screen_on == null ? '—' : (screen.screen_on ? 'On' : 'Off'), '')}
        ${dashboardCardHtml('Root', detail.device.root_available ? 'Available' : 'Unavailable', '')}
        ${dashboardCardHtml('Foreground app', fg.package || '—', fg.activity || '')}
      </div>
    `;
  } catch (err) {
    pane.innerHTML = `<div class="alert error">Failed to load dashboard: ${escapeHtml(String(err))}</div>`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => {
    if (dashboardTimer) { clearInterval(dashboardTimer); dashboardTimer = null; }
    if (tab === 'dashboard') {
      renderDashboardTab();
      dashboardTimer = setInterval(renderDashboardTab, 4000);
    }
  });
  onDeviceChange(() => { if (currentTab() === 'dashboard') renderDashboardTab(); });
});

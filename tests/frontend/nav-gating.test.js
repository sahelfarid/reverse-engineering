// Smoke tests for app.js's updateNavDeviceGating(): sidebar tabs marked
// data-requires-device should hide when no authorized device is selected,
// and bounce back to the Dashboard tab if the currently active tab was one
// of the ones that just got hidden.
import { describe, it, expect } from 'vitest';
import { buildDom } from './dom.js';

function setUp() {
  const dom = buildDom(
    `<ul class="nav-tabs">
      <li data-tab="dashboard" class="active">Dashboard</li>
      <li data-tab="devices">Devices</li>
      <li data-tab="files" data-requires-device="true">Files</li>
      <li data-tab="wireless">Wireless</li>
    </ul>
    <div id="tab-dashboard" class="tab-pane active"></div>
    <div id="tab-devices" class="tab-pane"></div>
    <div id="tab-files" class="tab-pane"></div>
    <div id="tab-wireless" class="tab-pane"></div>`,
    ['app.js'],
  );
  const { window } = dom;
  window.initTabs();
  return { window, document: window.document };
}

describe('updateNavDeviceGating', () => {
  it('hides data-requires-device tabs when no device is connected', () => {
    const { window, document } = setUp();
    window.updateNavDeviceGating(null, null);
    expect(document.querySelector('li[data-tab="files"]').style.display).toBe('none');
    expect(document.querySelector('li[data-tab="devices"]').style.display).not.toBe('none');
    expect(document.querySelector('li[data-tab="wireless"]').style.display).not.toBe('none');
  });

  it('shows data-requires-device tabs once an authorized device is selected', () => {
    const { window, document } = setUp();
    window.updateNavDeviceGating(null, null);
    window.updateNavDeviceGating('s1', { serial: 's1', state: 'device' });
    expect(document.querySelector('li[data-tab="files"]').style.display).toBe('list-item');
  });

  it('keeps requires-device tabs hidden for an unauthorized/offline device', () => {
    const { window, document } = setUp();
    window.updateNavDeviceGating('s1', { serial: 's1', state: 'unauthorized' });
    expect(document.querySelector('li[data-tab="files"]').style.display).toBe('none');
  });

  it('falls back to the Dashboard tab if the active tab just got hidden', () => {
    const { window, document } = setUp();
    document.querySelector('li[data-tab="files"]').click(); // simulate the user being on Files
    expect(document.querySelector('li[data-tab="files"]').classList.contains('active')).toBe(true);

    window.updateNavDeviceGating(null, null); // device disconnects

    expect(document.querySelector('li[data-tab="files"]').classList.contains('active')).toBe(false);
    expect(document.querySelector('li[data-tab="dashboard"]').classList.contains('active')).toBe(true);
    expect(document.getElementById('tab-dashboard').classList.contains('active')).toBe(true);
    expect(document.getElementById('tab-files').classList.contains('active')).toBe(false);
  });

  it('leaves the active tab alone if it does not require a device', () => {
    const { window, document } = setUp();
    document.querySelector('li[data-tab="devices"]').click();
    window.updateNavDeviceGating(null, null);
    expect(document.querySelector('li[data-tab="devices"]').classList.contains('active')).toBe(true);
  });
});

// Smoke tests for static/js/shell.js: terminal output rendering and
// command-failure display. This is the frontend follow-up flagged (but left
// out of scope) in docs/module-audits/shell.md -- the Python test suite can't
// reach DOM rendering, so this exercises the real script via jsdom instead.
import { describe, it, expect, vi } from 'vitest';
import { buildDom } from './dom.js';

// getSelectedSerial/getSelectedDevice/onDeviceChange normally live in
// devices.js, which pulls in its own DOM (#device-select, #refresh-devices-btn)
// and fetch calls unrelated to what this test covers. Stubbed here so the
// test isolates shell.js's own rendering/interaction logic.
const DEVICE_STUB = {
  code: `
    function getSelectedSerial() { return 's1'; }
    function getSelectedDevice() { return { serial: 's1', state: 'device' }; }
    function onDeviceChange(_fn) {}
  `,
};

function setUp() {
  const dom = buildDom(
    '<div id="tab-shell"></div><div id="toast-container"></div>',
    ['app.js', DEVICE_STUB, 'shell.js'],
  );
  const { window } = dom;
  return { dom, window, document: window.document };
}

function typeAndSubmit(window, document, command) {
  const input = document.getElementById('shell-input');
  input.value = command;
  const evt = new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
  input.dispatchEvent(evt);
}

describe('shell.js terminal rendering', () => {
  it('renders stdout and a green exit badge for a successful command', async () => {
    const { window, document } = setUp();
    window.fetch = vi.fn((url) => {
      if (String(url).includes('su-available')) {
        return Promise.resolve({ status: 200, json: async () => ({ ok: true, available: false }) });
      }
      return Promise.resolve({
        status: 200,
        json: async () => ({ ok: true, result: { stdout: 'hello world\n', stderr: '', returncode: 0 } }),
      });
    });

    window.renderShellTab();
    typeAndSubmit(window, document, 'echo hello world');

    await vi.waitFor(() => {
      expect(document.getElementById('shell-output').textContent).toContain('hello world');
    });

    const output = document.getElementById('shell-output');
    expect(output.textContent).toContain('$ echo hello world');
    expect(output.textContent).toContain('exit 0');
    expect(output.querySelector('.badge.green')).not.toBeNull();
    expect(output.querySelector('.badge.red')).toBeNull();

    // The input is cleared and the command is stashed in local history.
    expect(document.getElementById('shell-input').value).toBe('');
  });

  it('renders stderr and a red exit badge for a failing command', async () => {
    const { window, document } = setUp();
    window.fetch = vi.fn((url) => {
      if (String(url).includes('su-available')) {
        return Promise.resolve({ status: 200, json: async () => ({ ok: true, available: false }) });
      }
      return Promise.resolve({
        status: 200,
        json: async () => ({ ok: true, result: { stdout: '', stderr: 'no such file', returncode: 1 } }),
      });
    });

    window.renderShellTab();
    typeAndSubmit(window, document, 'cat /nope');

    await vi.waitFor(() => {
      expect(document.getElementById('shell-output').textContent).toContain('no such file');
    });

    const output = document.getElementById('shell-output');
    expect(output.textContent).toContain('exit 1');
    expect(output.querySelector('.badge.red')).not.toBeNull();
  });

  it('shows an error toast and leaves the transcript empty when the API call itself fails', async () => {
    const { window, document } = setUp();
    window.fetch = vi.fn((url) => {
      if (String(url).includes('su-available')) {
        return Promise.resolve({ status: 200, json: async () => ({ ok: true, available: false }) });
      }
      return Promise.resolve({ status: 200, json: async () => ({ ok: false, error: 'invalid_command' }) });
    });

    window.renderShellTab();
    typeAndSubmit(window, document, 'this-is-not-a-real-flag --bogus');

    await vi.waitFor(() => {
      expect(document.getElementById('toast-container').children.length).toBeGreaterThan(0);
    });

    const toastEl = document.getElementById('toast-container').firstElementChild;
    expect(toastEl.className).toContain('error');
    expect(toastEl.textContent).toContain('invalid_command');
    // The failed submission never reaches appendShellEntry(), so no transcript block was rendered.
    expect(document.getElementById('shell-output').children.length).toBe(0);
  });

  it('escapes HTML in the command and output instead of rendering it', async () => {
    const { window, document } = setUp();
    window.fetch = vi.fn((url) => {
      if (String(url).includes('su-available')) {
        return Promise.resolve({ status: 200, json: async () => ({ ok: true, available: false }) });
      }
      return Promise.resolve({
        status: 200,
        json: async () => ({ ok: true, result: { stdout: '<img src=x onerror=alert(1)>', stderr: '', returncode: 0 } }),
      });
    });

    window.renderShellTab();
    typeAndSubmit(window, document, '<b>echo</b>');

    await vi.waitFor(() => {
      expect(document.getElementById('shell-output').children.length).toBeGreaterThan(0);
    });

    const output = document.getElementById('shell-output');
    expect(output.querySelector('img')).toBeNull();
    expect(output.querySelector('b')).toBeNull();
    expect(output.textContent).toContain('<b>echo</b>');
    expect(output.textContent).toContain('<img src=x onerror=alert(1)>');
  });
});

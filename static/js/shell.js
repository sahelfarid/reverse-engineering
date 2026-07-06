// Shell terminal tab: request/response command execution against `adb shell`
// (not a live PTY — each submitted command is one round trip), with local
// history/autocomplete/export and optional su.

const SHELL_COMMON_COMMANDS = [
  'ls -la', 'cd', 'pwd', 'cat', 'pm list packages', 'dumpsys battery', 'dumpsys activity activities',
  'getprop', 'ps -A', 'top -n 1', 'df', 'du -sh', 'settings get global', 'settings put global',
  'input keyevent', 'input tap', 'input swipe', 'input text', 'screencap -p', 'logcat -d',
  'rm', 'mv', 'cp', 'mkdir', 'chmod', 'su', 'exit', 'clear', 'wm size', 'wm density',
];

let shellTranscript = [];

function shellHistoryKey(serial) { return `adbpanel.shellHistory.${serial}`; }

function loadShellHistory(serial) {
  try { return JSON.parse(localStorage.getItem(shellHistoryKey(serial)) || '[]'); }
  catch (e) { return []; }
}

function saveShellHistory(serial, history) {
  localStorage.setItem(shellHistoryKey(serial), JSON.stringify(history.slice(-200)));
}

function renderShellTab() {
  const pane = document.getElementById('tab-shell');
  if (!pane) return;
  const serial = getSelectedSerial();
  const device = getSelectedDevice();
  if (!serial || !device || device.state !== 'device') {
    pane.innerHTML = `<div class="alert warn">Select an authorized, online device to use the shell.</div>`;
    return;
  }
  if (pane.dataset.boundSerial === serial) return; // already wired up for this device
  pane.dataset.boundSerial = serial;
  shellTranscript = [];

  pane.innerHTML = `
    <div class="card">
      <div style="display:flex; gap:10px; align-items:center; margin-bottom:8px; flex-wrap:wrap;">
        <label><input type="checkbox" id="shell-su-toggle" disabled> Use su</label>
        <button id="shell-clear-btn">Clear</button>
        <button id="shell-export-btn">Export history</button>
        <span class="muted">Enter runs the command · Shift+Enter for a new line · ↑/↓ recall history</span>
      </div>
      <pre id="shell-output" class="shell-output"></pre>
      <div style="display:flex; gap:8px; margin-top:8px; position:relative;">
        <textarea id="shell-input" rows="1" style="flex:1; font-family:Consolas,monospace;" placeholder="e.g. ls -la /sdcard"></textarea>
        <button id="shell-run-btn">Run</button>
        <div id="shell-autocomplete" class="card" style="position:absolute; bottom:100%; left:0; right:80px; display:none; max-height:160px; overflow-y:auto; z-index:5;"></div>
      </div>
    </div>
  `;

  checkSuAvailability(serial);
  wireShellInput(serial);
}

async function checkSuAvailability(serial) {
  const toggle = document.getElementById('shell-su-toggle');
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/shell/su-available`);
    const data = await res.json();
    if (data.ok && data.available) toggle.disabled = false;
  } catch (e) { /* leave disabled */ }
}

function appendShellEntry(command, result) {
  const out = document.getElementById('shell-output');
  const rcClass = result.returncode === 0 ? 'green' : 'red';
  const block = document.createElement('div');
  block.innerHTML = `<div>$ ${escapeHtml(command)}</div>` +
    (result.stdout ? `<div>${escapeHtml(result.stdout)}</div>` : '') +
    (result.stderr ? `<div style="color:#e0563d">${escapeHtml(result.stderr)}</div>` : '') +
    `<div class="muted">exit ${result.returncode} <span class="badge ${rcClass}"></span></div>`;
  out.appendChild(block);
  out.scrollTop = out.scrollHeight;
  shellTranscript.push({ command, ...result });
}

function wireShellInput(serial) {
  const input = document.getElementById('shell-input');
  const runBtn = document.getElementById('shell-run-btn');
  const clearBtn = document.getElementById('shell-clear-btn');
  const exportBtn = document.getElementById('shell-export-btn');
  const autocomplete = document.getElementById('shell-autocomplete');
  let historyIdx = null;

  async function submit() {
    const command = input.value;
    if (!command.trim()) return;
    input.value = '';
    autocomplete.style.display = 'none';
    const history = loadShellHistory(serial);
    history.push(command);
    saveShellHistory(serial, history);
    historyIdx = null;
    const useSu = document.getElementById('shell-su-toggle').checked;
    try {
      const res = await apiFetch(`/api/devices/${encodeURIComponent(serial)}/shell/exec`, {
        method: 'POST', body: { command, use_su: useSu },
      });
      const data = await res.json();
      if (!data.ok) { toast(`Shell error: ${data.error}`, 'error'); return; }
      appendShellEntry(command, data.result);
    } catch (err) {
      toast(`Shell request failed: ${err}`, 'error');
    }
  }

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
      return;
    }
    if (e.key === 'ArrowUp' && !input.value.includes('\n')) {
      const history = loadShellHistory(serial);
      if (!history.length) return;
      historyIdx = historyIdx == null ? history.length - 1 : Math.max(0, historyIdx - 1);
      input.value = history[historyIdx];
      e.preventDefault();
    }
    if (e.key === 'ArrowDown' && !input.value.includes('\n')) {
      const history = loadShellHistory(serial);
      if (historyIdx == null) return;
      historyIdx = Math.min(history.length - 1, historyIdx + 1);
      input.value = history[historyIdx];
      e.preventDefault();
    }
  });

  input.addEventListener('input', () => {
    const value = input.value.trim();
    if (!value) { autocomplete.style.display = 'none'; return; }
    const matches = SHELL_COMMON_COMMANDS.filter((c) => c.startsWith(value)).slice(0, 8);
    if (!matches.length) { autocomplete.style.display = 'none'; return; }
    autocomplete.innerHTML = matches.map((m) => `<div class="ac-item" style="padding:4px 8px; cursor:pointer;">${escapeHtml(m)}</div>`).join('');
    autocomplete.style.display = 'block';
    autocomplete.querySelectorAll('.ac-item').forEach((el, i) => {
      el.addEventListener('click', () => { input.value = matches[i]; autocomplete.style.display = 'none'; input.focus(); });
    });
  });

  runBtn.addEventListener('click', submit);
  clearBtn.addEventListener('click', () => {
    document.getElementById('shell-output').innerHTML = '';
    shellTranscript = [];
  });
  exportBtn.addEventListener('click', () => {
    const text = shellTranscript.map((e) => `$ ${e.command}\n${e.stdout}${e.stderr ? '\n[stderr] ' + e.stderr : ''}\n(exit ${e.returncode})\n`).join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `adb-shell-${serial}-session.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  onTabChange((tab) => { if (tab === 'shell') renderShellTab(); });
  onDeviceChange(() => { if (currentTab() === 'shell') renderShellTab(); });
});

// Generic single-instance modal, shared by file preview and help-tip buttons.

window.TIP_REGISTRY = window.TIP_REGISTRY || {};
let CURRENT_MODAL = null;

function openModal(title, bodyHtml) {
  closeModal();
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <div class="modal-header">
        <h3>${escapeHtml(title || '')}</h3>
        <button type="button" class="ghost-btn small" data-modal-close>Close</button>
      </div>
      <div class="modal-body">${bodyHtml}</div>
    </div>`;
  backdrop.addEventListener('click', (e) => { if (e.target === backdrop) closeModal(); });
  backdrop.querySelector('[data-modal-close]').addEventListener('click', closeModal);
  document.body.appendChild(backdrop);
  CURRENT_MODAL = backdrop;
  return backdrop;
}

function closeModal() {
  if (CURRENT_MODAL) { CURRENT_MODAL.remove(); CURRENT_MODAL = null; }
}

// Delegated so any tab can drop in `<button class="tip-btn" data-tip-key="...">?</button>`
// with zero per-tab wiring; tip content is populated into TIP_REGISTRY by each
// tab file at load time (see settings.js/etc: `Object.assign(TIP_REGISTRY, {...})`).
function initTipButtons() {
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.tip-btn');
    if (!btn) return;
    const tip = TIP_REGISTRY[btn.dataset.tipKey];
    openModal(tip ? tip.title : 'Help', tip ? tip.body : '<p class="muted">No help content found for this item.</p>');
  });
}

document.addEventListener('DOMContentLoaded', initTipButtons);

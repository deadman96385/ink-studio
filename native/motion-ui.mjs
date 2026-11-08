// Interface motion: content that newly appears eases in instead of cutting,
// and <details> sections open and close smoothly. See MOTION_PLAN.md.
//
// Panels here re-render with innerHTML on every change, so "new" is decided
// by comparing what was added with what it replaced: a re-render that keeps
// the same controls (only values changed) stays still, while a different tab,
// new options after a dropdown change, or fresh results animate.
import {prefersReducedMotion} from './motion.mjs';

const ENTER = 'cubic-bezier(.05,.7,.1,1)';
const STANDARD = 'cubic-bezier(.2,0,0,1)';
const REVEAL_MS = 180, MAX_PER_BATCH = 60;
const SKIP = 'svg,select,datalist,canvas,dialog:not([open]),.toast,[data-no-motion]';

// Pure: identity of a node for "is this the same thing re-rendered?".
// Numbers are ignored so a changed value doesn't count as new content.
export function signature(n) {
  if (n.nodeType !== 1) return null;
  const text = (n.textContent || '').replace(/[\d.,−-]+/g, '').replace(/\s+/g, ' ').trim().slice(0, 48);
  return `${n.tagName}#${n.id || ''}.${n.getAttribute?.('class') || ''}|${text}`;
}

// Pure: which added nodes are genuinely new compared with the removed ones.
export function freshNodes(added, removed) {
  const old = new Map();
  for (const n of removed) { const s = signature(n); if (s) old.set(s, (old.get(s) || 0) + 1); }
  const out = [];
  for (const n of added) {
    const s = signature(n);
    if (!s) continue;
    const left = old.get(s) || 0;
    if (left) old.set(s, left - 1); else out.push(n);
  }
  return out;
}

const animating = new Set();
export function reveal(el, {delay = 0} = {}) {
  if (!el?.animate || !el.isConnected || !el.getClientRects().length) return;
  for (const a of animating) if (a !== el && a.contains(el)) return; // parent already easing in
  const reduced = prefersReducedMotion();
  const anim = el.animate(reduced
    ? [{opacity: 0}, {opacity: 1}]
    : [{opacity: 0, translate: '0 4px'}, {opacity: 1, translate: '0 0'}],
  {duration: reduced ? 120 : REVEAL_MS, easing: ENTER, delay, fill: 'backwards'});
  animating.add(el);
  const done = () => animating.delete(el);
  anim.onfinish = done; anim.oncancel = done;
}

function skipped(target) {
  return !(target instanceof HTMLElement) || !!target.closest(SKIP);
}

export function installInterfaceMotion(root = document.body) {
  const observer = new MutationObserver(records => {
    // Panels are rebuilt in several steps (base HTML, then modules mount their
    // controls), so compare everything added in this batch with everything
    // removed in it, not record by record.
    const added = [], removed = [], shown = [];
    for (const r of records) {
      if (skipped(r.target)) continue;
      if (r.type === 'attributes') { if (r.oldValue !== null && !r.target.hidden) shown.push(r.target); continue; }
      for (const n of r.addedNodes) if (n.isConnected) added.push(n);
      removed.push(...r.removedNodes);
    }
    let fresh = freshNodes(added, removed).filter(n => !skipped(n));
    // Keep only the outermost new nodes.
    fresh = fresh.filter(n => !fresh.some(o => o !== n && o.contains(n)));
    if (fresh.length > MAX_PER_BATCH) {
      const parents = [...new Set(fresh.map(n => n.parentElement).filter(Boolean))];
      fresh = parents.length <= MAX_PER_BATCH ? parents : [];
    }
    fresh.forEach((n, i) => reveal(n, {delay: Math.min(i * 12, 120)}));
    for (const el of shown.slice(0, MAX_PER_BATCH)) reveal(el);
  });
  observer.observe(root, {subtree: true, childList: true, attributes: true, attributeFilter: ['hidden'], attributeOldValue: true});

  installDialogExit();

  // <details>: animate height instead of snapping open/closed.
  const running = new WeakMap();
  root.addEventListener('click', e => {
    const summary = e.target.closest?.('summary');
    const d = summary?.parentElement;
    if (!d || d.tagName !== 'DETAILS' || e.defaultPrevented) return;
    const control = e.target.closest('button,a,input,select,textarea');
    if (control && summary.contains(control)) return; // a control inside the summary
    if (prefersReducedMotion() || d.closest('[data-no-motion]')) return;
    e.preventDefault();
    toggleDetails(d, running);
  });
  return observer;
}

// Dialogs close instantly as before (code reads .open right after close()),
// and a visual copy fades out on top so closing doesn't read as a cut.
function installDialogExit() {
  const snapshots = new WeakMap();
  const snap = d => {
    if (!d.open || prefersReducedMotion() || d.hasAttribute('data-no-motion')) return;
    const r = d.getBoundingClientRect();
    if (r.width && r.height) snapshots.set(d, {rect: r, modal: d.matches(':modal'), scroll: d.scrollTop});
  };
  const close = HTMLDialogElement.prototype.close;
  HTMLDialogElement.prototype.close = function (...args) { snap(this); return close.apply(this, args); };
  document.addEventListener('cancel', e => snap(e.target), true);   // Escape
  document.addEventListener('submit', e => { const d = e.target.closest?.('dialog'); if (d && e.target.method === 'dialog') snap(d); }, true);
  document.addEventListener('close', e => {
    const d = e.target, s = snapshots.get(d);
    snapshots.delete(d);
    if (s && d instanceof HTMLDialogElement && !d.open) ghostOut(d, s);
  }, true);
}

function ghostOut(d, {rect, modal, scroll}) {
  const ghost = d.cloneNode(true);
  ghost.removeAttribute('open'); ghost.removeAttribute('id');
  for (const n of ghost.querySelectorAll('[id]')) n.removeAttribute('id');
  // cloneNode keeps attributes, not live values or canvas pixels.
  const live = d.querySelectorAll('input,select,textarea,canvas'), copy = ghost.querySelectorAll('input,select,textarea,canvas');
  live.forEach((el, i) => {
    const c = copy[i]; if (!c) return;
    if (el.tagName === 'CANVAS') {
      try {
        const img = new Image();
        img.src = el.toDataURL(); img.className = el.className;
        img.style.cssText = `display:block;width:${el.clientWidth}px;height:${el.clientHeight}px`;
        c.replaceWith(img);
      } catch {}
    } else if (el.type === 'checkbox' || el.type === 'radio') c.checked = el.checked;
    else c.value = el.value;
  });
  const div = document.createElement('div');
  div.setAttribute('data-no-motion', ''); div.setAttribute('aria-hidden', 'true'); div.inert = true;
  div.style.cssText = 'position:fixed;inset:0;z-index:2147483000;pointer-events:none';
  if (modal) { const b = document.createElement('div'); b.style.cssText = 'position:absolute;inset:0;background:#142c2466;backdrop-filter:blur(3px)'; div.append(b); }
  ghost.style.cssText += `;display:block;position:fixed;margin:0;left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px;max-height:none;max-width:none;overflow:hidden;animation:none`;
  div.append(ghost);
  document.body.append(div);
  ghost.scrollTop = scroll;
  const opts = {duration: 160, easing: 'cubic-bezier(.3,0,.8,.15)', fill: 'forwards'};
  ghost.animate([{opacity: 1, translate: '0 0', scale: '1'}, {opacity: 0, translate: '0 6px', scale: '.98'}], opts);
  const fade = div.firstElementChild !== ghost ? div.firstElementChild.animate([{opacity: 1}, {opacity: 0}], opts) : null;
  const done = () => div.remove();
  (fade || ghost.getAnimations()[0])?.finished.then(done, done);
  setTimeout(done, 400);
}

function toggleDetails(d, running) {
  const current = running.get(d);
  const opening = current ? !current.opening : !d.open;
  const from = d.getBoundingClientRect().height;
  current?.anim.cancel();
  d.style.height = '';
  // Measure the end height in the end state.
  d.open = false; const closedH = d.getBoundingClientRect().height;
  d.open = true; const openH = d.getBoundingClientRect().height;
  const to = opening ? openH : closedH;
  const duration = Math.round(Math.min(320, 160 + Math.abs(to - from) * .25));
  d.style.overflow = 'hidden';
  const anim = d.animate({height: [`${from}px`, `${to}px`]}, {duration, easing: STANDARD});
  if (opening) for (const child of d.children) if (child.tagName !== 'SUMMARY') reveal(child);
  const state = {opening, anim};
  running.set(d, state);
  anim.onfinish = () => {
    if (!opening) d.open = false;
    d.style.overflow = '';
    running.delete(d);
  };
}

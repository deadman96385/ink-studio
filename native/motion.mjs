// Canvas motion: newly placed layers grow out of their placement point and
// removed layers shrink away. The canvas rebuilds its SVG on every render, so
// entries are tracked by layer id and resumed with a negative animation-delay
// instead of restarting. Timings mirror the tokens in motion.css.
import {groupBounds} from './geometry.mjs';

export const TIMING = {place: 380, swap: 240, exit: 160, stagger: 25, staggerCap: 240, maxAnimated: 200};

// Pure: decide which layers enter, how, from where and when.
// prev: Set of ids from the last render (null on first render).
export function planEntries(prev, layers, now, {baseline = false} = {}) {
  const ids = new Set(layers.map(l => l.id));
  if (baseline || !prev) return {ids, entries: [], removed: []};
  const added = layers.filter(l => !prev.has(l.id));
  const removed = [...prev].filter(id => !ids.has(id));
  if (!added.length || added.length > TIMING.maxAnimated) return {ids, entries: [], removed};
  // Pure placement grows from the group's centre; a replacement (an operation
  // swapping shapes for new ones) only settles in, so it doesn't look like new art.
  const kind = removed.length ? 'swap' : 'place';
  const b = groupBounds(added);
  const origin = {x: b.x + b.w / 2, y: b.y + b.h / 2};
  const step = added.length > 1 ? Math.min(TIMING.stagger, TIMING.staggerCap / (added.length - 1)) : 0;
  const duration = TIMING[kind];
  // start stays null until the browser actually begins the animation, so work
  // that blocks the first paint (re-rendering panels) doesn't eat the motion.
  const entries = added.map((l, i) => ({id: l.id, kind, origin, created: now, start: null, delay: kind === 'place' ? Math.round(i * step) : 0, duration}));
  return {ids, entries, removed};
}

// Pure: CSS animation-delay that resumes an entry at its current progress.
export const resumeDelay = (entry, now) => entry.start == null ? entry.delay : entry.delay - (now - entry.start);
export const finished = (entry, now) => entry.start == null
  ? now - entry.created > 2000 // never painted (e.g. hidden tab); give up
  : now - entry.start > entry.delay + entry.duration;

export function prefersReducedMotion() {
  try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return false; }
}

export function createCanvasMotion({node, now = () => performance.now()}) {
  let known = null, projectId = null, quietNext = false;
  const entering = new Map();
  let ghosts = [];
  return {
    // The next render shows a restored state (undo, redo, load) or a stroke
    // the user just drew, so nothing should appear to be newly placed.
    quiet() { quietNext = true; },
    // Call before the artwork group is cleared, while old layer nodes still exist.
    before(project, art) {
      const t = now(), baseline = quietNext || project.id !== projectId;
      quietNext = false; projectId = project.id;
      const plan = planEntries(known, project.layers, t, {baseline});
      for (const [id, e] of entering) if (finished(e, t) || !plan.ids.has(id)) entering.delete(id);
      known = plan.ids;
      if (baseline) entering.clear();
      for (const e of plan.entries) entering.set(e.id, e);
      ghosts = [];
      if (!baseline && plan.removed.length && plan.removed.length <= TIMING.maxAnimated) {
        for (const id of plan.removed) {
          const old = art.querySelector(`:scope > [data-layer="${CSS.escape(id)}"], :scope > .art-enter > [data-layer="${CSS.escape(id)}"]`);
          if (!old) continue;
          const clone = old.cloneNode(true);
          clone.removeAttribute('data-layer');
          for (const n of clone.querySelectorAll('[data-layer]')) n.removeAttribute('data-layer');
          ghosts.push(clone);
        }
      }
    },
    // Wraps a layer's group when it is still entering.
    wrap(id, g) {
      const e = entering.get(id);
      if (!e) return g;
      const w = node('g', {class: `art-enter art-${e.kind}`});
      w.style.setProperty('--ox', `${e.origin.x}px`);
      w.style.setProperty('--oy', `${e.origin.y}px`);
      w.style.animationDuration = `${e.duration}ms`;
      w.style.animationDelay = `${resumeDelay(e, now())}ms`;
      // animationstart fires once the delay has elapsed.
      w.addEventListener('animationstart', () => { if (e.start == null) e.start = now() - e.delay; }, {once: true});
      w.addEventListener('animationend', () => entering.delete(id), {once: true});
      w.append(g);
      return w;
    },
    // Call after the new artwork is drawn: removed layers shrink away above it.
    after(host) {
      host.replaceChildren();
      if (!ghosts.length) return;
      for (const clone of ghosts) {
        const w = node('g', {class: 'art-exit'});
        w.append(clone);
        host.append(w);
        // Shrink toward the ghost's own centre.
        try { const box = w.getBBox(); w.style.setProperty('--ox', `${box.x + box.width / 2}px`); w.style.setProperty('--oy', `${box.y + box.height / 2}px`); } catch {}
        w.style.animationDuration = `${TIMING.exit}ms`;
        const done = () => w.remove();
        w.addEventListener('animationend', done, {once: true});
        setTimeout(done, TIMING.exit + 100); // also covers animation: none
      }
      ghosts = [];
    },
    isEntering: id => entering.has(id),
  };
}

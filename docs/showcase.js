// The tour is static. This player only replays stitches from a prepared PES export.
'use strict';

const viewer = document.getElementById('image-dialog');
const enlarged = document.getElementById('enlarged-image');
let previousFocus;
document.querySelectorAll('[data-enlarge]').forEach(link => {
  link.addEventListener('click', event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || typeof viewer.showModal !== 'function') return;
    event.preventDefault();
    previousFocus = link;
    enlarged.src = link.href;
    enlarged.alt = link.querySelector('img').alt;
    document.getElementById('image-caption').textContent = link.dataset.caption;
    viewer.showModal();
  });
});
viewer.addEventListener('close', () => previousFocus?.focus());
viewer.addEventListener('click', event => { if (event.target === viewer) {
  const box = viewer.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) viewer.close();
}});

async function initPlayer() {
  const canvas = document.getElementById('stitch-canvas');
  const context = canvas.getContext('2d');
  if (!context) return;
  const response = await fetch('assets/field-notes-stitches.json');
  if (!response.ok) throw new Error('Sample unavailable');
  const sample = await response.json();
  const slider = document.getElementById('stitch-position');
  const play = document.getElementById('play');
  const counter = document.getElementById('stitch-count');
  const total = sample.segments.length;
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let position = total, playing = false, frame = 0, lastTime = 0;
  slider.max = total;
  slider.value = total;

  function render() {
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.round(rect.width * dpr), height = Math.round(rect.height * dpr);
    if (!width || !height) return;
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, width, height);
    const scale = Math.min(width / (sample.width + 20), height / (sample.height + 20));
    context.translate(width / 2, height / 2);
    context.scale(scale, scale);
    context.translate(-(sample.bounds[0] + sample.width / 2), -(sample.bounds[1] + sample.height / 2));
    context.lineCap = 'round';
    // Paint each real segment; the light pass adds thread texture, not geometry.
    for (let i = 0; i < position; i++) {
      const [x1, y1, x2, y2, thread] = sample.segments[i];
      context.beginPath(); context.moveTo(x1, y1); context.lineTo(x2, y2);
      context.strokeStyle = sample.threads[thread].color; context.lineWidth = .26; context.stroke();
      context.strokeStyle = '#fff9e344'; context.lineWidth = .055; context.stroke();
    }
    slider.value = position;
    counter.value = `${position.toLocaleString()} / ${total.toLocaleString()}`;
    slider.setAttribute('aria-valuetext', `${position.toLocaleString()} of ${total.toLocaleString()} stitches`);
  }
  function pause() {
    playing = false; cancelAnimationFrame(frame); play.textContent = position === total ? 'Replay stitches' : 'Play stitches';
  }
  function tick(time) {
    if (!playing) return;
    position = Math.min(total, position + Math.max(1, Math.round((time - lastTime) * .4)));
    lastTime = time; render();
    if (position === total) pause(); else frame = requestAnimationFrame(tick);
  }
  play.addEventListener('click', () => {
    if (playing) return pause();
    if (position === total) position = 0;
    playing = true; play.textContent = 'Pause'; lastTime = performance.now(); frame = requestAnimationFrame(tick);
  });
  slider.addEventListener('input', () => { position = Number(slider.value); pause(); render(); });
  document.getElementById('restart').addEventListener('click', () => { position = 0; pause(); render(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
  // No automatic playback, including for visitors who prefer reduced motion.
  reducedMotion.addEventListener('change', () => { if (reducedMotion.matches) pause(); });
  canvas.hidden = false;
  document.getElementById('sample-fallback').hidden = true;
  document.getElementById('player-controls').hidden = false;
  new ResizeObserver(render).observe(canvas);
  render();
}
initPlayer().catch(() => {
  document.getElementById('player-note').textContent = 'Static preview shown. Serve this folder over HTTP to enable replay.';
});

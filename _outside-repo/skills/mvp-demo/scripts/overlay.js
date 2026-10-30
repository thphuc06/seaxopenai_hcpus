// Demo overlay kit, injected into every page of a recording (page.add_init_script).
// Gives the page: a callout chip at the top, a visible cursor that follows the mouse, subtitles that move out of the way
// of content, and a "camera" that zooms smoothly onto one element. All elements have ids starting with "demo-" and never
// take clicks (pointer-events: none), except the chip, which is hidden while the mouse is near it.
//   window.demoChip(text)               show a short callout ("" hides it)
//   window.demoSubs(epochMs, chunks)    subtitles: [{t, e, text}] in ms from epochMs (Date.now() clock)
//   window.demoCamera(selector, scale)  zoom onto an element; demoCamera(null) zooms back out
// Mark backgrounds that subtitles may cover with data-bg, and elements they must never cover with data-ink.
(() => {
  const R = () => document.documentElement;
  const css = (e, t) => { e.style.cssText = t; return e; };
  const mk = (id, t) => { let e = document.getElementById(id); if (!e) { e = document.createElement('div'); e.id = id; R().appendChild(css(e, t)); } return e; };
  const store = { get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
                  set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) {} } };
  let ACCENT = '#b4442a';   // set --demo-accent on the page's :root to change it
  const ensure = () => {
    if (!R()) return;
    if (!document.getElementById('demo-chip')) ACCENT = getComputedStyle(R()).getPropertyValue('--demo-accent').trim() || ACCENT;
    mk('demo-chip', `position:fixed;left:50%;top:7px;transform:translateX(-50%);background:${ACCENT};color:#fff;font:700 20px system-ui,Segoe UI,sans-serif;padding:6px 20px;border-radius:999px;z-index:2147483647;display:none;white-space:nowrap;pointer-events:none;max-width:94vw;overflow:hidden;text-overflow:ellipsis`);
    mk('demo-cur', `position:fixed;width:26px;height:26px;margin:-13px 0 0 -13px;border-radius:50%;border:3px solid ${ACCENT};background:rgba(180,68,42,.25);z-index:2147483647;pointer-events:none;display:none;transition:transform .12s`);
    mk('demo-sub', 'position:fixed;left:50%;transform:translateX(-50%);max-width:1040px;background:rgba(0,0,0,.76);color:#fff;font:600 30px/1.25 system-ui,Segoe UI,sans-serif;padding:10px 24px;border-radius:12px;text-align:center;z-index:2147483647;display:none;pointer-events:none;bottom:22px');
    const c = store.get('demo-chip') || ''; const chip = document.getElementById('demo-chip'); chip.textContent = c; chip.style.display = c ? 'block' : 'none';
    const p = JSON.parse(store.get('demo-pos') || 'null');
    if (p) { const k = document.getElementById('demo-cur'); k.style.left = p.x + 'px'; k.style.top = p.y + 'px'; k.style.display = 'block'; }
  };
  window.addEventListener('DOMContentLoaded', ensure);
  // A tiny, almost invisible pixel that changes every 100 ms: the recorder writes frames only when the page repaints,
  // so without it a still slide leaves a hole in the video and the timeline drifts.
  setInterval(() => { if (!R()) return; const t = mk('demo-tick', 'position:fixed;right:0;bottom:0;width:2px;height:2px;z-index:2147483647;pointer-events:none');
    t.style.background = t.style.background === 'rgba(0, 0, 0, 0.02)' ? 'rgba(0, 0, 0, 0.03)' : 'rgba(0, 0, 0, 0.02)'; }, 100);
  window.addEventListener('mousemove', (e) => {
    ensure(); const k = document.getElementById('demo-cur'); k.style.left = e.clientX + 'px'; k.style.top = e.clientY + 'px'; k.style.display = 'block';
    store.set('demo-pos', JSON.stringify({x: e.clientX, y: e.clientY}));
  }, true);
  window.addEventListener('mousedown', () => { const k = document.getElementById('demo-cur'); if (k) k.style.transform = 'scale(.6)'; }, true);
  window.addEventListener('mouseup', () => { const k = document.getElementById('demo-cur'); if (k) k.style.transform = 'none'; }, true);
  window.demoChip = (t) => { store.set('demo-chip', t || ''); ensure(); };
  window.demoCamera = (sel, s) => {
    ensure(); const body = document.body, k = document.getElementById('demo-cur');
    body.style.transition = 'transform 1s ease-in-out';
    if (!sel || s === 1) { body.style.transform = 'none'; if (k) k.style.opacity = 1; R().style.overflow = ''; return; }
    const r = document.querySelector(sel).getBoundingClientRect();
    s = Math.min(s || 1.5, (innerHeight - 150) / r.height, (innerWidth - 40) / r.width);  // never taller than the room above the subtitles
    const ecx = r.left + window.scrollX + r.width / 2, ecy = r.top + window.scrollY + r.height / 2;
    const dx = innerWidth / 2 - (r.left + r.width / 2), dy = (innerHeight - 100) / 2 + 22 - (r.top + r.height / 2);
    R().style.overflow = 'hidden'; if (k) k.style.opacity = 0;
    body.style.transformOrigin = ecx + 'px ' + ecy + 'px';
    body.style.transform = 'translate(' + dx + 'px,' + dy + 'px) scale(' + s + ')';
  };

  // ---- subtitles: pick the first of four spots where nothing readable sits under them
  const isOverlay = (e) => e.id && e.id.startsWith('demo-');
  const inkAt = (e, x, y) => {
    if (e === document.documentElement || e === document.body || isOverlay(e) || e.closest('[data-bg]')) return false;
    let o = 1; for (let n = e; n && n.nodeType === 1; n = n.parentElement) o *= parseFloat(getComputedStyle(n).opacity);
    if (o < 0.3) return false;                      // still fading in: not content yet
    if (e.closest('[data-ink]')) return true;
    if (['IMG', 'CANVAS', 'VIDEO', 'INPUT', 'BUTTON', 'SELECT', 'TEXTAREA'].includes(e.tagName) || e instanceof SVGElement) return true;
    const cs = getComputedStyle(e);
    const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/.exec(cs.backgroundColor);
    if ((m && (m[4] === undefined || parseFloat(m[4]) > 0.04)) || cs.backgroundImage !== 'none') return true;
    if (parseFloat(cs.borderTopWidth) > 0 && cs.borderTopStyle !== 'none') return true;
    for (const n of e.childNodes) if (n.nodeType === 3 && n.textContent.trim()) {
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const r of rg.getClientRects()) if (x >= r.left - 4 && x <= r.right + 4 && y >= r.top - 3 && y <= r.bottom + 3) return true;
    }
    return false;
  };
  const hits = (r) => {
    let n = 0;
    for (let i = 0; i <= 12; i++) for (const f of [0.1, 0.5, 0.9]) {
      const x = r.left + (r.width * i) / 12, y = r.top + r.height * f;
      if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) continue;
      if (document.elementsFromPoint(x, y).some((e) => inkAt(e, x, y))) n++;
    }
    return n;
  };
  const SPOTS = [{bottom: 22}, {top: 64}, {bottom: 128}, {top: 132}];
  let lastSpot = 0, lastChunk = -1;
  const put = (sub, i) => { sub.style.top = sub.style.bottom = 'auto'; for (const [k, v] of Object.entries(SPOTS[i])) sub.style[k] = v + 'px'; };
  const place = (sub, force) => {
    const order = force ? SPOTS.map((_, i) => i) : [lastSpot, ...SPOTS.map((_, i) => i).filter((i) => i !== lastSpot)];
    let best = null;
    for (const i of order) {
      put(sub, i);
      const n = hits(sub.getBoundingClientRect());
      if (n === 0) { best = {i, n}; break; }
      if (best === null || n < best.n) best = {i, n};
    }
    put(sub, best.i); lastSpot = best.i;
  };
  window.demoSubs = (t0, chunks) => { window.__subs = {t0, chunks}; store.set('demo-subs', JSON.stringify(window.__subs)); lastChunk = -1; };
  setInterval(() => {
    if (!window.__subs) { const s = store.get('demo-subs'); if (s) window.__subs = JSON.parse(s); }
    if (!R()) return; ensure();
    const sub = document.getElementById('demo-sub'); if (!sub) return;
    const S = window.__subs; if (!S) { sub.style.display = 'none'; return; }
    const t = Date.now() - S.t0; const i = S.chunks.findIndex((c) => t >= c.t && t < c.e);
    if (i < 0) { sub.style.display = 'none'; lastChunk = -1; return; }
    if (i !== lastChunk) { sub.textContent = S.chunks[i].text; sub.style.display = 'block'; place(sub, false); lastChunk = i; }
    else if (hits(sub.getBoundingClientRect()) > 0) { place(sub, true); }   // the page moved under it: look again
  }, 90);
})();

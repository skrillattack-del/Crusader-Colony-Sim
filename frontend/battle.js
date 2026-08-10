/* Battle viewer — animated humanoid battles for Crusader Colony Sim.
 *
 * Renders the LiveBattle snapshot stream (poll ~10 Hz) at 60 fps with
 * client-side interpolation: procedural mini-skeleton soldiers, fully
 * articulated general figures driven by the server's action state machine,
 * geometry-typed technique effects from the combat grammar, and a duel
 * cinema inset that draws the fighters' G3 conduit graphs live — flow,
 * saturation, seals, ruptures, gates and µ, in the documentation's
 * "painterly body overlaid with blueprint math" style.
 */
(() => {
  'use strict';

  const bc = document.getElementById('bcanvas');
  const bctx = bc.getContext('2d');

  // ------------------------------------------------------------ state
  let watchId = null, pollTimer = null, rafId = null;
  let snapA = null, snapB = null;      // {d, time} previous / latest
  let prevUnits = new Map();           // uid -> [x, y]
  let prevGens = [];                   // [{x, y, at}]
  let unitAnim = new Map();            // uid -> {anim, since}
  let floaters = [];                   // {x, y, text, color, born, world}
  let fxSeen = new Map();              // fx key -> expiry
  let shake = 0;
  let lastPhase = '', phaseAt = -1e9, phaseLabel = '';
  // animation pass: particles, weapon trails, death/fall tracking, UI tweens
  let particles = [];                  // {x,y,vx,vy,life,max,col,size,grav,world,spin,rot}
  let trails = new Map();              // id -> [{x,y,born}] recent blade-tip screen pts
  let falling = new Map();             // id -> {x,y,face,h,col,dead,born} mid-fall figures
  let lastUnit = new Map();            // uid -> {side,type,hp,face} last known (for fall fig)
  let prevUids = new Set();            // detect vanished units (deaths)
  let prevGenDown = [];                // detect generals going down
  let prevMorale = [null, null];       // morale-change flash
  let moraleFlash = [0, 0];            // timestamp of last morale change
  let resultAt = -1e9;                 // result-overlay appear time
  let lastNow = 0;                     // dt for particle physics
  const POLL_MS = 100;

  // ------------------------------------------------------------ palette
  const SIDE = ['#ff6b6b', '#74b9ff'];
  const SIDE_GLOW = ['rgba(255,107,107,', 'rgba(116,185,255,'];
  const TR_COLOR = { kinetic: '#e8eef2', thermal: '#ff9040',
    gravitational: '#b06cff', spatial: '#4dd8ff', spiritual: '#ffd34d' };
  const EV_COLOR = { log: '#8b9bab', kill: '#ff8f8f', duel: '#ffd34d',
    tech: '#4dd8ff', wound: '#ff6b6b', rout: '#ffb26b', result: '#f1c40f',
    gate: '#ffd34d', rupture: '#ff5b5b', seal: '#c9a6ff' };
  // unit type shading: levy, spear, archer, lcav, knight, pike, siege
  const TYPE_TINT = [0.78, 0.92, 0.85, 0.95, 1.15, 0.9, 0.7];
  const PHASE_LABEL = { deploy: 'DEPLOYMENT', clash: 'THE CLASH',
    rout: 'ROUT!', done: 'THE FIELD FALLS SILENT' };
  // body.py orders (must match backend)
  const PARTS = ['head', 'eyes', 'torso', 'heart', 'lungs', 'spine',
    'arm_r', 'forearm_r', 'hand_r', 'arm_l', 'forearm_l', 'hand_l',
    'thigh_r', 'shin_r', 'thigh_l', 'shin_l'];
  const GATE_MAX = 8;

  // ------------------------------------------------------------ helpers
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const easeOut = t => 1 - Math.pow(1 - t, 3);
  const easeIn = t => t * t * t;
  const easeOutCubic = easeOut;
  const easeOutQuint = t => 1 - Math.pow(1 - t, 5);
  const easeInOutCubic = t => t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2;
  const easeOutBack = t => {
    const c1 = 1.70158, c3 = c1 + 1;
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
  };

  // ----- particle system: blood, dust, sparks, debris -----
  function spawnParticles(wx, wy, n, opt) {
    const o = opt || {};
    const col = o.col || '#b03030';
    for (let i = 0; i < n; i++) {
      const a = o.dir !== undefined
        ? o.dir + (Math.random() - 0.5) * (o.spread || 1.2)
        : Math.random() * 6.283;
      const sp = (o.spd || 1) * (0.4 + Math.random() * 0.9);
      particles.push({
        x: wx, y: wy,
        vx: Math.cos(a) * sp + (o.vx || 0),
        vy: Math.sin(a) * sp + (o.vy || 0),
        life: o.life || 0.7, max: o.life || 0.7,
        col, size: o.size || (0.8 + Math.random() * 1.2),
        grav: o.grav !== undefined ? o.grav : 14,
        world: o.world !== false,         // true = coords in world space (px/py)
        spin: (Math.random() - 0.5) * 8, rot: Math.random() * 6.283,
        drag: o.drag !== undefined ? o.drag : 1.6,
        glow: o.glow || false,
      });
    }
    if (particles.length > 520) particles.splice(0, particles.length - 520);
  }

  function updateParticles(dt, px, py, sc, now, ctx) {
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.life -= dt;
      if (p.life <= 0) { particles.splice(i, 1); continue; }
      p.vy += p.grav * dt;
      p.vx -= p.vx * p.drag * dt;
      p.vy -= p.vy * p.drag * 0.4 * dt;
      p.x += p.vx * dt * 18;
      p.y += p.vy * dt * 18;
      p.rot += p.spin * dt;
    }
    // draw
    for (const p of particles) {
      const sx = p.world ? px(p.x) : p.x;
      const sy = p.world ? py(p.y) : p.y;
      const t = p.life / p.max;
      ctx.globalAlpha = clamp(t, 0, 1);
      const r = p.size * sc * (0.6 + t * 0.6);
      if (p.glow) {
        ctx.fillStyle = p.col;
        ctx.beginPath(); ctx.arc(sx, sy, r * 1.6, 0, 6.283);
        ctx.globalAlpha = clamp(t, 0, 1) * 0.4; ctx.fill();
        ctx.globalAlpha = clamp(t, 0, 1);
      }
      ctx.fillStyle = p.col;
      ctx.beginPath(); ctx.arc(sx, sy, r, 0, 6.283); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ----- weapon trails: ribbon of recent blade-tip screen positions -----
  const TRAIL_LIFE = 160;              // ms
  function pushTrail(id, sx, sy, now) {
    let arr = trails.get(id);
    if (!arr) { arr = []; trails.set(id, arr); }
    arr.push({ x: sx, y: sy, born: now });
    if (arr.length > 14) arr.shift();
  }
  function drawTrails(ctx, now, sc, pred) {
    for (const [id, arr] of trails) {
      if (pred && !pred(id)) continue;
      if (arr.length < 2) continue;
      for (let i = 1; i < arr.length; i++) {
        const a = arr[i - 1], b = arr[i];
        const age = now - b.born;
        if (age > TRAIL_LIFE) continue;
        const t = 1 - age / TRAIL_LIFE;
        ctx.strokeStyle = `rgba(240,248,255,${0.55 * t * t})`;
        ctx.lineWidth = (1 + t * 2.4) * sc;
        ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
      while (arr.length && now - arr[0].born > TRAIL_LIFE) arr.shift();
    }
  }

  // ----- falling figures: bridge standing -> down/corpse over ~0.5s -----
  function drawFalling(ctx, fx, fy, h, face, col, born, now) {
    const t = clamp((now - born) / 500, 0, 1);
    if (t >= 1) return false;            // done -> caller shows persistent corpse
    const e = easeOutCubic(t);
    const cx = fx, cy = fy;
    const standHipY = cy - h * 0.42, standChestY = cy - h * 0.72;
    // collapse: hip & chest drop toward ground, torso rotates to horizontal
    const hipY = lerp(standHipY, cy - h * 0.06, e);
    const chestY = lerp(standChestY, cy - h * 0.10, e);
    const lean = e * 1.3 * face;          // topple forward
    const chestX = cx + Math.sin(lean) * h * 0.30;
    ctx.save();
    ctx.globalAlpha = 1 - e * 0.25;
    ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineCap = 'round';
    const lw = Math.max(1, h * 0.1);
    // legs buckle
    ctx.lineWidth = lw;
    ctx.beginPath(); ctx.moveTo(cx, hipY); ctx.lineTo(cx - h * 0.18 * face, cy - h * 0.02); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, hipY); ctx.lineTo(cx + h * 0.14 * face, cy - h * 0.02); ctx.stroke();
    // torso
    ctx.lineWidth = lw * 1.3;
    ctx.beginPath(); ctx.moveTo(cx, hipY); ctx.lineTo(chestX, chestY); ctx.stroke();
    // arms flail
    ctx.lineWidth = lw * 0.85;
    ctx.beginPath(); ctx.moveTo(chestX, chestY);
    ctx.lineTo(chestX + h * 0.20 * face, chestY + h * 0.12); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(chestX, chestY);
    ctx.lineTo(chestX - h * 0.16 * face, chestY + h * 0.10); ctx.stroke();
    // head
    ctx.beginPath(); ctx.arc(chestX + Math.sin(lean) * h * 0.18,
      chestY - Math.cos(lean) * h * 0.12, h * 0.12, 0, 6.283); ctx.fill();
    ctx.restore();
    return true;
  }

  function tint(hex, f) {
    const r = clamp(Math.round(parseInt(hex.slice(1, 3), 16) * f), 0, 255);
    const g = clamp(Math.round(parseInt(hex.slice(3, 5), 16) * f), 0, 255);
    const b = clamp(Math.round(parseInt(hex.slice(5, 7), 16) * f), 0, 255);
    return `rgb(${r},${g},${b})`;
  }

  function satColor(s) {   // conduit saturation: gold -> red
    const t = clamp(s, 0, 1);
    const r = Math.round(lerp(255, 255, t));
    const g = Math.round(lerp(211, 70, t));
    const b = Math.round(lerp(77, 50, t));
    return `rgb(${r},${g},${b})`;
  }

  // ------------------------------------------------------------ open/close
  async function openBattle(id) {
    watchId = id;
    if (window.setMapAnimPaused) setMapAnimPaused(true);
    document.getElementById('battlewrap').style.display = 'flex';
    snapA = snapB = null;
    prevUnits.clear(); unitAnim.clear(); floaters = []; fxSeen.clear();
    particles = []; trails.clear(); falling.clear(); prevUids.clear();
    lastUnit.clear();
    prevGenDown = []; prevMorale = [null, null]; moraleFlash = [0, 0];
    resultAt = -1e9;
    lastPhase = ''; shake = 0;
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(poll, POLL_MS);
    await poll();
    if (rafId) cancelAnimationFrame(rafId);
    const loop = (ts) => { render(ts); rafId = requestAnimationFrame(loop); };
    rafId = requestAnimationFrame(loop);
  }
  function closeBattle() {
    watchId = null;
    if (window.setMapAnimPaused) setMapAnimPaused(false);
    document.getElementById('battlewrap').style.display = 'none';
    if (pollTimer) clearInterval(pollTimer);
    if (rafId) cancelAnimationFrame(rafId);
    pollTimer = rafId = null;
  }
  window.openBattle = openBattle;
  window.closeBattle = closeBattle;

  // ------------------------------------------------------------ polling
  async function poll() {
    if (watchId === null) return;
    let b;
    try {
      const r = await fetch('/api/battle?id=' + watchId);
      b = await r.json();
    } catch (e) { return; }
    if (!b || b.error) { closeBattle(); return; }
    // shift interpolation buffer
    if (snapB) {
      snapA = snapB;
      prevUnits.clear();
      for (const u of snapA.d.units) {
        prevUnits.set(u[0], [u[3], u[4]]);
        lastUnit.set(u[0], { side: u[1], type: u[2], hp: u[5], face: u[6] });
      }
      prevGens = snapA.d.generals.map(g => ({ x: g.x, y: g.y, at: g.at }));
    }
    snapB = { d: b, time: performance.now() };
    // unit anim transitions + hurt/death detection
    const liveUids = new Set();
    for (const u of b.units) {
      liveUids.add(u[0]);
      const st = unitAnim.get(u[0]);
      const wasHurt = st && st.anim === 3;
      if (!st || st.anim !== u[7]) unitAnim.set(u[0], { anim: u[7], since: performance.now() });
      lastUnit.set(u[0], { side: u[1], type: u[2], hp: u[5], face: u[6] });
      // transition into hurt (anim 3) -> blood burst
      if (!wasHurt && u[7] === 3) {
        spawnParticles(u[3], u[4], 9, { col: '#a82828', spd: 2.8, life: 0.55,
          grav: 18, size: 1.2 });
      }
    }
    // vanished units = deaths: spawn a fall figure + blood at last known pos
    for (const id of prevUids) {
      if (liveUids.has(id) || falling.has(id)) continue;
      const p = prevUnits.get(id);
      const info = lastUnit.get(id);
      if (p) {
        spawnParticles(p[0], p[1], 16, { col: '#9e2222', spd: 3.4, life: 0.75,
          grav: 16, size: 1.4 });
        const face = info ? info.face : (id % 2 === 0 ? 1 : -1);
        falling.set(id, { x: p[0], y: p[1], born: performance.now(), face,
          side: info ? info.side : 0, type: info ? info.type : 0 });
      }
    }
    prevUids = liveUids;
    if (unitAnim.size > 1600) {
      for (const k of unitAnim.keys()) if (!liveUids.has(k)) unitAnim.delete(k);
    }
    // HUD
    document.getElementById('s0name').textContent = b.sides[0].name;
    document.getElementById('s1name').textContent = b.sides[1].name;
    // morale bars (DOM tween via CSS) + flash on change
    for (let s = 0; s < 2; s++) {
      const bar = document.getElementById('s' + s + 'morale');
      bar.style.width = (b.sides[s].morale * 100) + '%';
      if (prevMorale[s] !== null && Math.abs(b.sides[s].morale - prevMorale[s]) > 0.004) {
        moraleFlash[s] = performance.now();
        bar.classList.remove('mflash');
        void bar.offsetWidth;            // restart CSS animation
        bar.classList.add('mflash');
      }
      prevMorale[s] = b.sides[s].morale;
    }
    document.getElementById('s0count').textContent =
      `${b.sides[0].count}/${b.sides[0].initial} ⚔${b.sides[0].kills || 0}`;
    document.getElementById('s1count').textContent =
      `${b.sides[1].count}/${b.sides[1].initial} ⚔${b.sides[1].kills || 0}`;
    // kill feed (typed colors)
    const feed = document.getElementById('killfeed');
    feed.innerHTML = b.events.slice().reverse().map(e => {
      const kind = Array.isArray(e) ? e[0] : 'log';
      const text = Array.isArray(e) ? e[1] : e;
      return `<div style="color:${EV_COLOR[kind] || '#b2bec3'}">${text}</div>`;
    }).join('');
    document.getElementById('bresult').textContent = b.result
      ? `⚑ ${b.result.winner} holds the field — ` +
        `${b.result.kills[0] + b.result.kills[1]} casualties`
      : `${b.phase}  ·  ${b.t}s`;
    if (b.result && resultAt < 0) resultAt = performance.now();
    if (!b.result) resultAt = -1e9;
    // phase banner
    if (b.phase !== lastPhase) {
      lastPhase = b.phase;
      phaseLabel = PHASE_LABEL[b.phase] || b.phase;
      phaseAt = performance.now();
    }
    // fx-driven floaters & shake
    for (const f of b.fx) {
      if (f.age > 0.22) continue;
      const key = `${f.k}:${Math.round(f.x)}:${Math.round(f.y)}:${f.side}`;
      const now = performance.now();
      if (fxSeen.has(key) && fxSeen.get(key) > now) continue;
      fxSeen.set(key, now + 900);
      if (f.k === 'gate') {
        shake = Math.min(14, shake + 3 + (f.lvl || 1));
        spawnFloat(f.x, f.y, `GATE ${f.lvl}  µ↑`, '#ffd34d');
        spawnParticles(f.x, f.y, 10, { col: '#ffd34d', spd: 4, life: 0.7,
          grav: 6, size: 1.2, glow: true });
      } else if (f.k === 'rupture') {
        shake = Math.min(14, shake + 2);
        spawnFloat(f.x, f.y, 'τ≫C RUPTURE', '#ff5b5b');
        spawnParticles(f.x, f.y, 16, { col: '#ff5b5b', spd: 5, life: 0.6,
          grav: 8, size: 1.4, glow: true });
      } else if (f.k === 'seal') {
        spawnFloat(f.x, f.y, 'MERIDIAN SEALED', '#c9a6ff');
        spawnParticles(f.x, f.y, 8, { col: '#c9a6ff', spd: 2.5, life: 0.7,
          grav: -2, size: 1.0, glow: true });
      } else if (f.k === 'slain') {
        shake = Math.min(16, shake + 6);
        spawnParticles(f.x, f.y, 18, { col: '#9e2222', spd: 3.4, life: 0.8,
          grav: 16, size: 1.4 });
        spawnParticles(f.x, f.y, 6, { col: '#d94444', spd: 2, life: 0.5,
          grav: 10, size: 1.0 });
      } else if (f.k === 'tech') {
        shake = Math.min(12, shake + 1.5 + (f.pw || 0) * 0.2);
        const tc = TR_COLOR[f.tr] || '#fff';
        spawnParticles(f.x, f.y, 12, { col: tc, spd: 4.5, life: 0.6,
          grav: 4, size: 1.2, glow: true });
      } else if (f.k === 'clash') {
        const pw = f.pw || 2;
        spawnParticles(f.x, f.y, 5 + Math.min(8, pw), { col: '#b9a06a',
          spd: 2 + pw * 0.2, life: 0.45, grav: 14, size: 0.9 });
        if (pw > 6) { shake = Math.min(10, shake + 1);
          spawnParticles(f.x, f.y, 5, { col: '#ffe9a8', spd: 3, life: 0.3,
            grav: 2, size: 1.0, glow: true }); }
      }
    }
    for (const [k, exp] of fxSeen) if (exp < performance.now()) fxSeen.delete(k);
    // generals going down/dead -> blood burst + tracked fall
    b.generals.forEach((g, i) => {
      const wasDown = prevGenDown[i] || false;
      const isDown = !g.alive || g.down;
      if (!wasDown && isDown) {
        spawnParticles(g.x, g.y, 22, { col: '#9e2222', spd: 3.6, life: 0.9,
          grav: 16, size: 1.5 });
        falling.set('g' + i, { x: g.x, y: g.y, born: performance.now(),
          face: g.face, side: g.side, gen: true, col: tint(SIDE[g.side], g.alive ? 1 : 0.75) });
      }
      prevGenDown[i] = isDown;
    });
  }

  function spawnFloat(wx, wy, text, color) {
    floaters.push({ x: wx, y: wy, text, color, born: performance.now() });
    if (floaters.length > 24) floaters.shift();
  }

  // ------------------------------------------------------------ pose math
  // Angle convention: 0 = straight down; positive swings toward facing.
  function runCycle(ph) {
    const s = Math.sin(ph);
    return { hipF: s * 0.62, kneeF: Math.max(0, -s) * 0.95,
             hipB: -s * 0.62, kneeB: Math.max(0, s) * 0.95,
             shF: -s * 0.45, elF: 0.35, shB: s * 0.45, elB: 0.35,
             lean: 0.12, crouch: 0.05 };
  }

  function fighterPose(g, at, now) {
    const t = clamp(at, 0, 1);
    switch (g.action) {
      case 'advance': case 'disengage':
        return runCycle(now / 130);
      case 'windup': {
        const e = easeIn(t);
        return { shF: lerp(0.3, -2.45, e), elF: lerp(0.2, -0.7, e),
                 shB: 0.5, elB: 0.4, hipF: 0.3, kneeF: -0.1,
                 hipB: -0.25, kneeB: 0.4, lean: lerp(0, -0.16, e), crouch: 0.08 };
      }
      case 'strike': {
        const e = easeOut(t);
        return { shF: lerp(-2.45, 1.45, e), elF: lerp(-0.7, 0.15, e),
                 shB: lerp(0.5, -0.4, e), elB: 0.3,
                 hipF: lerp(0.3, 0.55, e), kneeF: -0.15,
                 hipB: lerp(-0.25, -0.5, e), kneeB: lerp(0.4, 0.7, e),
                 lean: lerp(-0.16, 0.22, e), crouch: 0.1 };
      }
      case 'guard':
        return { shF: 0.95, elF: 1.85, shB: 0.65, elB: 1.5,
                 hipF: 0.22, kneeF: -0.08, hipB: -0.2, kneeB: 0.3,
                 lean: -0.05, crouch: 0.14 + Math.sin(now / 300) * 0.01 };
      case 'channel': {
        const pulse = Math.sin(now / 90) * 0.05;
        return { shF: 1.35 + pulse, elF: 0.15, shB: 1.15 + pulse, elB: 0.2,
                 hipF: 0.18, kneeF: -0.05, hipB: -0.18, kneeB: 0.25,
                 lean: 0.1, crouch: 0.16 };
      }
      case 'gate': {
        const tr = Math.sin(now / 26) * 0.05;
        return { shF: -0.55 + tr, elF: -0.95, shB: -0.55 - tr, elB: -0.95,
                 hipF: 0.42, kneeF: -0.5, hipB: -0.42, kneeB: 0.6,
                 lean: -0.12, crouch: 0.34 };
      }
      case 'stagger': {
        const e = easeOut(t);
        return { shF: lerp(0.4, 1.9, e), elF: 0.5, shB: lerp(0.2, 1.4, e),
                 elB: 0.6, hipF: 0.15, kneeF: 0.1, hipB: -0.4,
                 kneeB: 0.55, lean: lerp(0, -0.5, e), crouch: 0.1 };
      }
      default: {   // idle micro-sway
        const s = Math.sin(now / 420);
        return { shF: 0.28 + s * 0.03, elF: 0.35, shB: -0.15, elB: 0.3,
                 hipF: 0.14, kneeF: -0.05, hipB: -0.14, kneeB: 0.12,
                 lean: 0.02, crouch: 0.02 + s * 0.01 };
      }
    }
  }

  // Draws an articulated figure; returns joint positions for overlays.
  function drawFighter(ctx, cx, cy, h, face, pose, opt) {
    const col = opt.color, lw = Math.max(1.5, h * 0.075);
    const crouch = pose.crouch * h * 0.22;
    const hipY = cy - h * 0.46 + crouch;
    const torso = h * 0.30, up = h * 0.17, fo = h * 0.16;
    const th = h * 0.24, sh = h * 0.22;
    const lean = pose.lean * face;
    const chestX = cx + Math.sin(lean) * torso, chestY = hipY - Math.cos(lean) * torso;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    const seg = (x0, y0, a, len, w) => {
      const x1 = x0 + Math.sin(a) * face * len, y1 = y0 + Math.cos(a) * len;
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1);
      ctx.lineWidth = w; ctx.stroke();
      return [x1, y1];
    };
    ctx.strokeStyle = opt.limbColor || col;
    // legs (draw back first)
    const kneeB = seg(cx, hipY, pose.hipB, th, lw);
    const footB = seg(kneeB[0], kneeB[1], pose.hipB + pose.kneeB, sh, lw * 0.9);
    const kneeF = seg(cx, hipY, pose.hipF, th, lw);
    const footF = seg(kneeF[0], kneeF[1], pose.hipF + pose.kneeF, sh, lw * 0.9);
    // torso
    ctx.strokeStyle = col;
    ctx.beginPath(); ctx.moveTo(cx, hipY); ctx.lineTo(chestX, chestY);
    ctx.lineWidth = lw * 1.35; ctx.stroke();
    // back arm
    ctx.strokeStyle = opt.limbColor || col;
    const elB = seg(chestX, chestY, pose.shB, up, lw * 0.85);
    const handB = seg(elB[0], elB[1], pose.shB + pose.elB, fo, lw * 0.75);
    // front arm (weapon arm)
    const elF = seg(chestX, chestY, pose.shF, up, lw * 0.95);
    const handF = seg(elF[0], elF[1], pose.shF + pose.elF, fo, lw * 0.85);
    // head
    const headR = h * 0.095;
    const headX = chestX + Math.sin(lean) * headR * 2.2;
    const headY = chestY - Math.cos(lean) * headR * 1.6;
    ctx.fillStyle = col;
    ctx.beginPath(); ctx.arc(headX, headY, headR, 0, 6.283); ctx.fill();
    // weapon: blade continues the forearm direction past the hand
    if (opt.weapon !== false) {
      const af = pose.shF + pose.elF;
      const bx = handF[0] + Math.sin(af) * face * h * 0.45;
      const by = handF[1] + Math.cos(af) * h * 0.45;
      ctx.strokeStyle = opt.weaponColor || '#d9e2ea';
      ctx.lineWidth = Math.max(1, lw * 0.55);
      ctx.beginPath(); ctx.moveTo(handF[0], handF[1]); ctx.lineTo(bx, by); ctx.stroke();
      if (opt.strikeTrail) {
        ctx.strokeStyle = 'rgba(255,255,255,0.5)';
        ctx.lineWidth = lw * 0.4;
        ctx.beginPath();
        ctx.arc(chestX, chestY, h * 0.55, -1.9 * face, 0.9 * face, face < 0);
        ctx.stroke();
      }
      if (opt.trailId) pushTrail(opt.trailId, bx, by, opt._now || performance.now());
    }
    return { hip: [cx, hipY], chest: [chestX, chestY], head: [headX, headY],
             elF, handF, elB, handB, kneeF, footF, kneeB, footB };
  }

  function drawDownFigure(ctx, cx, cy, h, face, col, dead) {
    ctx.save();
    ctx.globalAlpha = dead ? 0.8 : 1;
    // blood pool
    ctx.fillStyle = 'rgba(120,20,25,0.5)';
    ctx.beginPath(); ctx.ellipse(cx, cy, h * 0.42, h * 0.12, 0, 0, 6.283); ctx.fill();
    ctx.strokeStyle = col; ctx.lineWidth = Math.max(1.5, h * 0.07);
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(cx - h * 0.3 * face, cy - h * 0.05);
    ctx.lineTo(cx + h * 0.25 * face, cy - h * 0.08);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + h * 0.05 * face, cy - h * 0.07);
    ctx.lineTo(cx + h * 0.3 * face, cy + h * 0.02);
    ctx.stroke();
    ctx.fillStyle = col;
    ctx.beginPath();
    ctx.arc(cx - h * 0.38 * face, cy - h * 0.06, h * 0.09, 0, 6.283);
    ctx.fill();
    ctx.restore();
  }

  // ------------------------------------------------------------ soldiers
  function drawSoldier(ctx, x, y, side, type, hp, face, anim, uid, s, now) {
    const h = s * 2.2;
    const col = tint(SIDE[side], TYPE_TINT[type] * (0.62 + 0.38 * hp));
    const st = unitAnim.get(uid);
    const since = st ? (now - st.since) : 999;
    const lw = Math.max(1, h * 0.1);
    ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineCap = 'round';
    // hit reaction (anim 3): knockback shove + backward lean
    let kbx = 0, lean = 0;
    if (anim === 3) {
      const k = clamp(since / 300, 0, 1);
      const env = Math.sin(k * Math.PI);
      kbx = env * h * 0.20 * -face;
      lean = env * 0.4 * -face;
    }
    // strike lunge (anim 2)
    let lunge = 0;
    if (anim === 2) lunge = Math.sin(clamp(since / 350, 0, 1) * Math.PI) * h * 0.22 * face;
    const cx = x + lunge + kbx, cy = y;
    // cavalry: horse under the rider
    if (type === 3 || type === 4) {
      const bob = anim === 1 ? Math.sin(now / 95 + uid) * h * 0.03 : 0;
      ctx.save();
      ctx.strokeStyle = tint('#8a6b4a', side === 0 ? 1.05 : 0.95);
      ctx.lineWidth = h * 0.3;
      ctx.beginPath();
      ctx.moveTo(cx - h * 0.42 * face, cy - h * 0.3 + bob);
      ctx.lineTo(cx + h * 0.42 * face, cy - h * 0.3 + bob);
      ctx.stroke();
      ctx.lineWidth = lw * 0.9;
      const g = anim === 1 ? Math.sin(now / 90 + uid) * 0.5 : 0.15;
      for (const o of [-0.3, 0.3]) {
        ctx.beginPath();
        ctx.moveTo(cx + o * h * face, cy - h * 0.3 + bob);
        ctx.lineTo(cx + (o + g * 0.25) * h * face, cy); ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(cx + o * h * face, cy - h * 0.3 + bob);
        ctx.lineTo(cx + (o - g * 0.25) * h * face, cy); ctx.stroke();
      }
      // horse head
      ctx.beginPath();
      ctx.moveTo(cx + h * 0.42 * face, cy - h * 0.32 + bob);
      ctx.lineTo(cx + h * 0.58 * face, cy - h * 0.5 + bob);
      ctx.lineWidth = h * 0.14; ctx.stroke();
      ctx.restore();
      // rider
      const chestY = cy - h * 0.72 + bob;
      ctx.beginPath(); ctx.moveTo(cx, cy - h * 0.34 + bob); ctx.lineTo(cx, chestY);
      ctx.lineWidth = lw * 1.2; ctx.stroke();
      ctx.beginPath(); ctx.arc(cx, chestY - h * 0.1, h * 0.11, 0, 6.283); ctx.fill();
      const tip = drawWeapon(ctx, cx, chestY, h, face, type, anim, since, lw);
      if (tip && (anim === 2)) pushTrail(uid, tip[0], tip[1], now);
      if (anim === 3 && since < 280) hurtFlash(ctx, cx, cy - h * 0.4, h);
      return;
    }
    // gait: stride phase, vertical bob, knee bend
    const walking = anim === 1;
    const cad = walking ? 120 : 1;
    const ph = walking ? Math.sin(now / cad + uid * 1.7) : 0;
    const bob = walking ? Math.abs(Math.cos(now / cad + uid * 1.7)) * h * 0.05
                        : Math.sin(now / 600 + uid) * h * 0.01;   // idle breathing
    const hipY = cy - h * 0.42 - bob;
    const chestY = cy - h * 0.72 - bob;
    const chestX = cx + Math.sin(lean) * h * 0.06;
    // 2-segment legs with knees (back leg first)
    const th = h * 0.24, sh = h * 0.22;
    const drawLeg = (swing) => {
      const hipA = swing * 0.55;
      const kneeBend = Math.max(0, -swing) * 0.8 + (walking ? 0.14 : 0.06);
      const kx = cx + Math.sin(hipA) * face * th;
      const ky = hipY + Math.cos(hipA) * th;
      const fa = hipA + kneeBend;
      const fxp = kx + Math.sin(fa) * face * sh;
      const fyp = ky + Math.cos(fa) * sh;
      ctx.lineWidth = lw;
      ctx.beginPath(); ctx.moveTo(cx, hipY); ctx.lineTo(kx, ky); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(kx, ky); ctx.lineTo(fxp, fyp); ctx.stroke();
    };
    drawLeg(ph); drawLeg(-ph);
    // torso (with lean)
    ctx.lineWidth = lw * 1.3;
    ctx.beginPath(); ctx.moveTo(cx, hipY); ctx.lineTo(chestX, chestY); ctx.stroke();
    // back arm counter-swing
    ctx.lineWidth = lw * 0.85;
    const armSwing = walking ? -ph * 0.6 : Math.sin(now / 500 + uid) * 0.12;
    ctx.beginPath(); ctx.moveTo(chestX, chestY);
    ctx.lineTo(chestX + Math.sin(armSwing) * face * h * 0.16,
               chestY + Math.cos(armSwing) * h * 0.16); ctx.stroke();
    // head
    ctx.fillStyle = col;
    const headX = chestX + Math.sin(lean) * h * 0.05;
    ctx.beginPath(); ctx.arc(headX, chestY - h * 0.12, h * 0.12, 0, 6.283); ctx.fill();
    // helmet hint for knights/spearmen
    if (type === 4 || type === 1) {
      ctx.fillStyle = tint(col, 1.3);
      ctx.fillRect(headX - h * 0.12, chestY - h * 0.26, h * 0.24, h * 0.07);
      ctx.fillStyle = col;
    }
    const tip = drawWeapon(ctx, chestX, chestY, h, face, type, anim, since, lw);
    if (tip && (anim === 2 || type === 5 || type === 1)) pushTrail(uid, tip[0], tip[1], now);
    if (anim === 3 && since < 280) hurtFlash(ctx, cx, cy - h * 0.4, h);
  }

  function drawWeapon(ctx, cx, chestY, h, face, type, anim, since, lw) {
    ctx.save();
    ctx.lineWidth = Math.max(0.8, lw * 0.7);
    const striking = anim === 2 && since < 350;
    const sp = striking ? easeOutCubic(clamp(since / 350, 0, 1)) : 0;
    // sp follows a 0->1 ease then holds; the swing envelope adds the return
    const swing = striking ? Math.sin(clamp(since / 350, 0, 1) * Math.PI) : 0;
    let tip = null;
    if (type === 2) {                    // archer: bow arc + arrow
      ctx.strokeStyle = '#c9a06a';
      ctx.beginPath();
      ctx.arc(cx + h * 0.28 * face, chestY, h * 0.3, -1.25, 1.25);
      ctx.stroke();
      if (striking) {
        const ax = cx + (h * 0.3 + sp * h * 0.9) * face;
        const ay = chestY - sp * h * 0.15;
        ctx.strokeStyle = '#eee';
        ctx.beginPath();
        ctx.moveTo(cx + h * 0.3 * face, chestY); ctx.lineTo(ax, ay); ctx.stroke();
        tip = [ax, ay];
      }
    } else if (type === 5 || type === 1) { // pike/spear
      const len = type === 5 ? h * 1.15 : h * 0.85;
      ctx.strokeStyle = '#c9b08a';
      const dip = striking ? sp * 0.25 : 0;
      const tx = cx + len * face, ty = chestY + h * 0.1 - len * (0.12 - dip);
      ctx.beginPath();
      ctx.moveTo(cx - h * 0.1 * face, chestY + h * 0.1); ctx.lineTo(tx, ty);
      ctx.stroke();
      tip = [tx, ty];
    } else if (type === 6) {              // siege crew: hammer
      ctx.strokeStyle = '#b0a090';
      const tx = cx + h * 0.4 * face, ty = chestY - h * 0.25 + sp * h * 0.4;
      ctx.beginPath(); ctx.moveTo(cx, chestY); ctx.lineTo(tx, ty); ctx.stroke();
      tip = [tx, ty];
    } else {                              // sword
      ctx.strokeStyle = '#d9e2ea';
      const a = striking ? lerp(-1.1, 0.9, sp) : -0.7;
      const hx = cx + h * 0.14 * face, hy = chestY + h * 0.05;
      const tx = cx + (h * 0.14 + Math.cos(a) * h * 0.55) * face;
      const ty = chestY + h * 0.05 - Math.sin(a + 1.2) * h * 0.5;
      ctx.beginPath(); ctx.moveTo(hx, hy); ctx.lineTo(tx, ty); ctx.stroke();
      tip = [tx, ty];
      if (striking && swing > 0.5) {
        ctx.strokeStyle = `rgba(255,255,255,${0.45 * swing})`;
        ctx.lineWidth = lw * 0.5;
        ctx.beginPath();
        ctx.arc(cx, chestY, h * 0.5, -1.3 * face, 0.5 * face, face < 0);
        ctx.stroke();
      }
    }
    ctx.restore();
    return tip;
  }

  function hurtFlash(ctx, x, y, h) {
    ctx.fillStyle = 'rgba(255,60,60,0.45)';
    ctx.beginPath(); ctx.arc(x, y, h * 0.5, 0, 6.283); ctx.fill();
  }

  // ------------------------------------------------------------ fx
  function drawFx(ctx, f, px, py, sc, now) {
    const life = { tech: 1.6, clash: 0.5, gate: 1.4, seal: 0.9,
                   rupture: 0.9, slain: 2.0 }[f.k] || 1.2;
    const p = clamp(f.age / life, 0, 1);
    const a = 1 - p;
    if (f.k === 'clash') {
      const x = px(f.x), y = py(f.y) - sc * 1.2;
      ctx.strokeStyle = `rgba(255,255,235,${0.85 * a})`;
      ctx.lineWidth = 1.4;
      const r = sc * (0.4 + p * 1.6) * (0.6 + (f.pw || 2) * 0.06);
      for (let i = 0; i < 6; i++) {
        const an = i * 1.047 + (f.x * 7 % 1);
        ctx.beginPath();
        ctx.moveTo(x + Math.cos(an) * r * 0.3, y + Math.sin(an) * r * 0.3);
        ctx.lineTo(x + Math.cos(an) * r, y + Math.sin(an) * r);
        ctx.stroke();
      }
      return;
    }
    if (f.k === 'gate') {
      const x = px(f.x), y = py(f.y) - sc * 1.2;
      const lvl = f.lvl || 1;
      const col = lvl >= 6 ? '255,70,60' : '255,211,77';
      ctx.strokeStyle = `rgba(${col},${0.9 * a})`;
      ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.arc(x, y, sc * (1 + p * 6), 0, 6.283); ctx.stroke();
      ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(x, y, sc * (0.5 + p * 9), 0, 6.283); ctx.stroke();
      // rising pillar
      ctx.fillStyle = `rgba(${col},${0.25 * a})`;
      ctx.fillRect(x - sc * 0.8, y - sc * (6 + p * 6), sc * 1.6, sc * (6 + p * 6));
      return;
    }
    if (f.k === 'rupture') {
      const x = px(f.x), y = py(f.y) - sc * 1.6;
      ctx.strokeStyle = `rgba(255,70,70,${0.9 * a})`;
      ctx.lineWidth = 1.6;
      for (let i = 0; i < 7; i++) {
        const an = i * 0.9 + f.age * 3;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + Math.cos(an) * sc * (0.5 + p * 1.8),
                   y + Math.sin(an) * sc * (0.5 + p * 1.8));
        ctx.stroke();
      }
      return;
    }
    if (f.k === 'seal') {
      const x = px(f.x), y = py(f.y) - sc * 1.4;
      ctx.strokeStyle = `rgba(201,166,255,${0.9 * a})`;
      ctx.lineWidth = 1.4;
      for (let i = 0; i < 5; i++) {
        const an = p * 8 + i * 1.257;
        const r = sc * (0.4 + i * 0.28);
        ctx.beginPath();
        ctx.arc(x + Math.cos(an) * r * 0.4, y + Math.sin(an) * r * 0.4,
                sc * 0.16, 0, 6.283);
        ctx.stroke();
      }
      return;
    }
    if (f.k === 'slain') {
      const x = px(f.x), y = py(f.y);
      ctx.strokeStyle = `rgba(20,8,10,${0.5 * a})`;
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(x, y, sc * (1 + p * 7), 0, 6.283); ctx.stroke();
      ctx.fillStyle = `rgba(160,30,35,${0.35 * a})`;
      ctx.beginPath(); ctx.arc(x, y, sc * (0.6 + p * 2.5), 0, 6.283); ctx.fill();
      return;
    }
    // geometry-typed technique footprints
    const col = TR_COLOR[f.tr] || '#fff';
    const rgb = col.length === 7
      ? `${parseInt(col.slice(1, 3), 16)},${parseInt(col.slice(3, 5), 16)},${parseInt(col.slice(5, 7), 16)}`
      : '255,255,255';
    const ox = px(f.x), oy = py(f.y);
    const txp = px(f.tx !== undefined ? f.tx : f.x);
    const typ = py(f.ty !== undefined ? f.ty : f.y);
    const dirx = txp - ox, diry = typ - oy;
    const dd = Math.hypot(dirx, diry) || 1;
    const ux = dirx / dd, uy = diry / dd;
    const R = (f.r || 5) * sc;
    ctx.save();
    if (f.geo === 'radial') {
      ctx.strokeStyle = `rgba(${rgb},${0.9 * a})`;
      ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.arc(txp, typ, R * (0.25 + easeOut(p)), 0, 6.283); ctx.stroke();
      ctx.fillStyle = `rgba(${rgb},${0.16 * a})`;
      ctx.beginPath(); ctx.arc(txp, typ, R * (0.25 + easeOut(p)), 0, 6.283); ctx.fill();
    } else if (f.geo === 'cone') {
      const len = R * 1.9 * (0.3 + easeOut(p) * 0.7);
      const spread = 0.55;
      ctx.fillStyle = `rgba(${rgb},${0.3 * a})`;
      ctx.beginPath();
      ctx.moveTo(ox, oy);
      ctx.lineTo(ox + (ux - uy * spread) * len, oy + (uy + ux * spread) * len);
      ctx.lineTo(ox + (ux + uy * spread) * len, oy + (uy - ux * spread) * len);
      ctx.closePath(); ctx.fill();
      ctx.strokeStyle = `rgba(${rgb},${0.7 * a})`;
      ctx.lineWidth = 1.5; ctx.stroke();
    } else if (f.geo === 'line') {
      const len = R * 2.6;
      ctx.strokeStyle = `rgba(${rgb},${0.85 * a})`;
      ctx.lineWidth = 4 * (1 - p * 0.6);
      ctx.beginPath(); ctx.moveTo(ox, oy);
      ctx.lineTo(ox + ux * len, oy + uy * len); ctx.stroke();
      ctx.strokeStyle = `rgba(255,255,255,${0.5 * a})`;
      ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(ox, oy);
      ctx.lineTo(ox + ux * len, oy + uy * len); ctx.stroke();
    } else if (f.geo === 'cleave') {
      const len = R * 1.6 * (0.4 + easeOut(p) * 0.6);
      ctx.fillStyle = `rgba(${rgb},${0.35 * a})`;
      ctx.beginPath();
      ctx.moveTo(ox - uy * 3, oy + ux * 3);
      ctx.lineTo(ox + ux * len - uy * 5, oy + uy * len + ux * 5);
      ctx.lineTo(ox + ux * len + uy * 5, oy + uy * len - ux * 5);
      ctx.lineTo(ox + uy * 3, oy - ux * 3);
      ctx.closePath(); ctx.fill();
    } else if (f.geo === 'arc') {
      const base = Math.atan2(uy, ux);
      ctx.strokeStyle = `rgba(${rgb},${0.85 * a})`;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(ox, oy, sc * 5 * (0.5 + p * 0.5), base - 1.7, base + 1.7);
      ctx.stroke();
    } else {   // point
      ctx.fillStyle = `rgba(255,255,255,${0.9 * a})`;
      ctx.beginPath(); ctx.arc(txp, typ, sc * 0.8 * (1 - p), 0, 6.283); ctx.fill();
      ctx.strokeStyle = `rgba(${rgb},${0.9 * a})`;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(txp, typ, sc * (0.5 + p * 2.2), 0, 6.283); ctx.stroke();
    }
    ctx.restore();
  }

  // ------------------------------------------------------------ duel inset
  function drawDuelInset(ctx, b, gens, W, H, now) {
    const d = b.duel;
    if (!d) return;
    const ga = gens[d.a], gb = gens[d.b];
    if (!ga || !gb) return;
    const pw = Math.min(W * 0.5, 560), ph = Math.min(H * 0.46, 300);
    const x0 = (W - pw) / 2, y0 = 10;
    ctx.save();
    // panel
    ctx.fillStyle = 'rgba(7,11,17,0.86)';
    ctx.strokeStyle = '#31465f';
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x0, y0, pw, ph, 8);
    else ctx.rect(x0, y0, pw, ph);
    ctx.fill(); ctx.stroke();
    // blueprint grid
    ctx.strokeStyle = 'rgba(80,110,150,0.08)';
    ctx.lineWidth = 1;
    for (let gx = x0 + 20; gx < x0 + pw; gx += 26) {
      ctx.beginPath(); ctx.moveTo(gx, y0 + 4); ctx.lineTo(gx, y0 + ph - 4); ctx.stroke();
    }
    for (let gy = y0 + 20; gy < y0 + ph; gy += 26) {
      ctx.beginPath(); ctx.moveTo(x0 + 4, gy); ctx.lineTo(x0 + pw - 4, gy); ctx.stroke();
    }
    // registration corner marks (the docs' aesthetic)
    ctx.strokeStyle = 'rgba(160,190,220,0.35)';
    for (const [mx, my] of [[x0 + 10, y0 + 10], [x0 + pw - 10, y0 + 10],
                            [x0 + 10, y0 + ph - 10], [x0 + pw - 10, y0 + ph - 10]]) {
      ctx.beginPath(); ctx.arc(mx, my, 4, 0, 6.283); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(mx - 6, my); ctx.lineTo(mx + 6, my); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(mx, my - 6); ctx.lineTo(mx, my + 6); ctx.stroke();
    }
    ctx.font = '9px Consolas, monospace';
    ctx.fillStyle = 'rgba(160,190,220,0.5)';
    ctx.textAlign = 'left';
    ctx.fillText('G₃ FLOW — STATE TRANSFORMATION', x0 + 22, y0 + 14);
    ctx.textAlign = 'right';
    ctx.fillText('A:(Pa,Pd,W,t)→Δ', x0 + pw - 22, y0 + 14);

    const baseY = y0 + ph * 0.80;
    const fh = ph * 0.52;
    const positions = [[x0 + pw * 0.30, 1], [x0 + pw * 0.70, -1]];
    [ga, gb].forEach((g, i) => {
      const [fx, face] = positions[i];
      const col = SIDE[g.side];
      drawDuelFighter(ctx, g, fx, baseY, fh, face, col, now, i === 0 ? x0 + 12 : x0 + pw - 12, i === 0 ? 'left' : 'right', y0, ph, 'duel' + i);
    });
    // VS mark & floating annotations drawn by caller
    ctx.restore();
  }

  function drawDuelFighter(ctx, g, fx, baseY, fh, face, col, now, barX, align, y0, ph, trailId) {
    // aura by µ / gate
    const mu = g.mu || 1;
    if (mu > 1.05 || g.action === 'gate' || g.action === 'channel') {
      const rad = fh * (0.45 + (mu - 1) * 0.12);
      const gate = g.gate || 0;
      const gcol = gate >= 6 ? '255,60,50' : gate >= 1 ? '255,211,77' : '120,200,255';
      const grd = ctx.createRadialGradient(fx, baseY - fh * 0.4, fh * 0.1,
                                           fx, baseY - fh * 0.4, rad);
      grd.addColorStop(0, `rgba(${gcol},${0.22 + 0.06 * Math.sin(now / 80)})`);
      grd.addColorStop(1, `rgba(${gcol},0)`);
      ctx.fillStyle = grd;
      ctx.beginPath(); ctx.arc(fx, baseY - fh * 0.4, rad, 0, 6.283); ctx.fill();
    }
    let joints = null;
    if (g.action === 'down' || !g.alive) {
      drawDownFigure(ctx, fx, baseY, fh, face, col, !g.alive);
    } else {
      const at = extrapolateAt(g);
      const pose = fighterPose(g, at, now);
      joints = drawFighter(ctx, fx, baseY, fh, face, pose,
        { color: col, weaponColor: '#e8eef2',
          strikeTrail: g.action === 'strike', trailId, _now: now });
    }
    // conduit overlay on the body (G3 graph made visible)
    if (joints && g.edges) drawConduits(ctx, joints, g, now);
    // name + condition
    ctx.font = 'bold 11px "Segoe UI", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillStyle = col;
    ctx.fillText(g.name, fx, baseY - fh - 16);
    const bw = 74;
    barRow(ctx, fx - bw / 2, baseY - fh - 12, bw, 4, g.cond, col);
    barRow(ctx, fx - bw / 2, baseY - fh - 6, bw, 3, g.blood, '#c0392b');
    barRow(ctx, fx - bw / 2, baseY - fh - 2, bw, 3, g.res, '#3fd0c9');
    // µ / routing annotations
    ctx.font = '10px Consolas, monospace';
    ctx.fillStyle = '#dfe6e9';
    ctx.fillText(`µ ×${(g.mu || 1).toFixed(2)}`, fx, baseY + 14);
    if (g.routing || g.tech) {
      ctx.fillStyle = '#9fd8ff';
      ctx.fillText(g.tech ? g.tech : g.routing, fx, baseY + 26);
    }
    // gate padlock row
    const gx0 = fx - (GATE_MAX * 8) / 2;
    for (let i = 0; i < GATE_MAX; i++) {
      ctx.fillStyle = i < (g.gate || 0)
        ? (i >= 5 ? '#ff5b4d' : '#ffd34d') : 'rgba(120,140,160,0.25)';
      ctx.fillRect(gx0 + i * 8, baseY + 30, 6, 6);
    }
    // per-part integrity readout (aggregated)
    if (g.parts) {
      const agg = [
        ['head', g.parts[0]], ['eyes', g.parts[1]], ['torso', g.parts[2]],
        ['vitals', Math.min(g.parts[3], g.parts[4])], ['spine', g.parts[5]],
        ['sword arm', Math.min(g.parts[6], g.parts[7], g.parts[8])],
        ['off arm', Math.min(g.parts[9], g.parts[10], g.parts[11])],
        ['legs', Math.min(g.parts[12], g.parts[13], g.parts[14], g.parts[15])],
      ];
      ctx.font = '8px Consolas, monospace';
      ctx.textAlign = align;
      let yy = y0 + 30;
      for (const [label, v] of agg) {
        const vv = clamp(v, 0, 1);
        ctx.fillStyle = vv > 0.66 ? 'rgba(180,220,180,0.8)'
          : vv > 0.34 ? '#f0c674' : '#ff6b6b';
        ctx.fillText(label, barX, yy);
        const bx = align === 'left' ? barX : barX - 34;
        ctx.fillStyle = 'rgba(30,42,56,0.9)';
        ctx.fillRect(bx, yy + 2, 34, 3);
        ctx.fillStyle = vv > 0.66 ? '#7dbb7d' : vv > 0.34 ? '#f0c674' : '#ff6b6b';
        ctx.fillRect(bx, yy + 2, 34 * vv, 3);
        yy += 15;
      }
    }
  }

  function barRow(ctx, x, y, w, h, v, col) {
    ctx.fillStyle = 'rgba(16,24,32,0.9)';
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = col;
    ctx.fillRect(x, y, w * clamp(v || 0, 0, 1), h);
  }

  // EDGE_ORDER: core-heart, heart-spine, spine-arm_r, arm_r-hand_r,
  //             spine-arm_l, arm_l-hand_l, spine-eyes, spine-legs
  function drawConduits(ctx, j, g, now) {
    const E = g.edges;
    if (!E || E.length < 8) return;
    const belly = [j.hip[0], j.hip[1] - (j.hip[1] - j.chest[1]) * 0.35];
    const segs = [
      [j.hip, belly, E[0]],
      [belly, j.chest, E[1]],
      [j.chest, j.elF, E[2]], [j.elF, j.handF, E[3]],
      [j.chest, j.elB, E[4]], [j.elB, j.handB, E[5]],
      [j.chest, j.head, E[6]],
      [j.hip, j.kneeF, E[7]],
    ];
    ctx.save();
    ctx.lineCap = 'round';
    const flowing = g.action === 'channel' || g.action === 'strike'
      || g.action === 'windup' || (g.gate || 0) > 0;
    for (const [a, b, e] of segs) {
      const [sat, sealed, integ] = e;
      if (sealed) {
        ctx.strokeStyle = 'rgba(150,150,165,0.65)';
        ctx.setLineDash([3, 3]);
        ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
        ctx.setLineDash([]);
        const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
        ctx.strokeStyle = '#c9a6ff';
        ctx.beginPath(); ctx.moveTo(mx - 3, my - 3); ctx.lineTo(mx + 3, my + 3); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(mx + 3, my - 3); ctx.lineTo(mx - 3, my + 3); ctx.stroke();
        continue;
      }
      const base = 0.25 + sat * 0.6 + (flowing ? 0.18 + 0.1 * Math.sin(now / 70) : 0);
      ctx.strokeStyle = satColor(sat);
      ctx.globalAlpha = clamp(base, 0, 1) * clamp(integ, 0.2, 1);
      ctx.lineWidth = 1.2 + sat * 2.2;
      ctx.shadowColor = satColor(sat);
      ctx.shadowBlur = 4 + sat * 8;
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
      // integrity damage: broken channel notch
      if (integ < 0.8) {
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = '#ff5b5b';
        const mx = lerp(a[0], b[0], 0.5), my = lerp(a[1], b[1], 0.5);
        ctx.beginPath(); ctx.arc(mx, my, 2 + (1 - integ) * 2, 0, 6.283); ctx.fill();
      }
    }
    ctx.restore();
  }

  function extrapolateAt(g) {
    // advance the server-side action progress between polls
    if (!snapB) return g.at || 0;
    const dt = (performance.now() - snapB.time) / 1000;
    const rate = 2.2;   // typical 1/duration; clamped anyway
    return clamp((g.at || 0) + dt * rate * 0.5, 0, 1);
  }

  // ------------------------------------------------------------ render
  function render(now) {
    if (!snapB || watchId === null) return;
    const dt = lastNow ? Math.min(0.05, (now - lastNow) / 1000) : 0;
    lastNow = now;
    const b = snapB.d;
    // resize to CSS box
    const cssW = bc.clientWidth || 960, cssH = bc.clientHeight || 560;
    const dpr = window.devicePixelRatio || 1;
    if (bc.width !== Math.round(cssW * dpr) || bc.height !== Math.round(cssH * dpr)) {
      bc.width = Math.round(cssW * dpr);
      bc.height = Math.round(cssH * dpr);
    }
    const ctx = bctx;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const W = cssW, H = cssH;
    // field mapping with letterbox
    const sc = Math.min(W / 124, H / 74);
    const ox = (W - sc * 120) / 2, oy = (H - sc * 70) / 2;
    const px = x => ox + (x + 60) * sc;
    const py = y => oy + (y + 35) * sc;
    // screen shake
    let sx = 0, sy = 0;
    if (shake > 0.3) {
      sx = (Math.random() - 0.5) * shake;
      sy = (Math.random() - 0.5) * shake;
      shake *= 0.90;
    }
    ctx.save();
    ctx.translate(sx, sy);
    // ---- ground
    const grd = ctx.createLinearGradient(0, 0, 0, H);
    grd.addColorStop(0, '#1e2d20');
    grd.addColorStop(0.5, '#233527');
    grd.addColorStop(1, '#1a271d');
    ctx.fillStyle = grd;
    ctx.fillRect(-20, -20, W + 40, H + 40);
    // mottled turf
    ctx.fillStyle = 'rgba(58,82,56,0.10)';
    for (let i = 0; i < 46; i++) {
      const rx = ((i * 733) % 977) / 977, ry = ((i * 397) % 811) / 811;
      ctx.beginPath();
      ctx.ellipse(ox + rx * sc * 120, oy + ry * sc * 70,
                  sc * (1.2 + (i % 4) * 0.8), sc * (0.8 + (i % 3) * 0.5),
                  (i % 6) * 0.5, 0, 6.283);
      ctx.fill();
    }
    // interpolation factor
    let alpha = 1;
    if (snapA) {
      const span = Math.max(30, snapB.time - snapA.time);
      alpha = clamp((now - snapB.time) / span, 0, 1);
    }
    // ---- falling figures (dying transition before corpse appears)
    const doneFalling = [];
    for (const [id, fall] of falling) {
      const h = fall.gen ? sc * 3.1 : sc * 2.2;
      const col = fall.col || tint(SIDE[fall.side], (fall.gen ? 1 : TYPE_TINT[fall.type] * 0.62));
      const cont = drawFalling(ctx, px(fall.x), py(fall.y), h, fall.face, col, fall.born, now);
      if (!cont) doneFalling.push(id);
    }
    for (const id of doneFalling) falling.delete(id);
    // ---- corpses (persist under the living)
    for (const c of (b.corpses || [])) {
      const col = tint(SIDE[c[2]], 0.45);
      drawCorpse(ctx, px(c[0]), py(c[1]), sc * 1.9, c[2] === 0 ? 1 : -1, col);
    }
    // ---- soldier weapon trails (under soldiers)
    drawTrails(ctx, now, sc, id => id[0] !== 'g' && !id.startsWith('duel'));
    // ---- soldiers
    for (const u of b.units) {
      const prev = prevUnits.get(u[0]);
      const x = prev ? lerp(prev[0], u[3], alpha) : u[3];
      const y = prev ? lerp(prev[1], u[4], alpha) : u[4];
      drawSoldier(ctx, px(x), py(y), u[1], u[2], u[5], u[6], u[7], u[0], sc, now);
    }
    // ---- field fx
    for (const f of b.fx) drawFx(ctx, f, px, py, sc, now);
    // ---- particles (blood / dust / sparks)
    updateParticles(dt, px, py, sc, now, ctx);
    // ---- general weapon trails
    drawTrails(ctx, now, sc, id => id[0] === 'g' || id.startsWith('duel'));
    // ---- generals
    b.generals.forEach((g, i) => {
      const prev = prevGens[i];
      const gx = prev ? lerp(prev.x, g.x, alpha) : g.x;
      const gy = prev ? lerp(prev.y, g.y, alpha) : g.y;
      const X = px(gx), Y = py(gy);
      const h = sc * 3.1;
      if (!g.alive || g.down) {
        drawDownFigure(ctx, X, Y, h, g.face, tint(SIDE[g.side], g.alive ? 1 : 0.6), !g.alive);
      } else {
        // aura under the figure
        const mu = g.mu || 1;
        if (mu > 1.05) {
          const gate = g.gate || 0;
          const gcol = gate >= 6 ? '255,60,50' : '255,211,77';
          const rad = h * (0.6 + (mu - 1) * 0.25);
          const ag = ctx.createRadialGradient(X, Y - h * 0.4, h * 0.1, X, Y - h * 0.4, rad);
          ag.addColorStop(0, `rgba(${gcol},0.3)`);
          ag.addColorStop(1, `rgba(${gcol},0)`);
          ctx.fillStyle = ag;
          ctx.beginPath(); ctx.arc(X, Y - h * 0.4, rad, 0, 6.283); ctx.fill();
        }
        const pose = fighterPose(g, extrapolateAt(g), now);
        drawFighter(ctx, X, Y, h, g.face, pose,
          { color: SIDE[g.side], weaponColor: '#f1e6c8',
            strikeTrail: g.action === 'strike', trailId: 'g' + i, _now: now });
        // banner crest
        ctx.fillStyle = '#f1c40f';
        ctx.beginPath();
        ctx.moveTo(X, Y - h - 8); ctx.lineTo(X + 4, Y - h - 3);
        ctx.lineTo(X, Y - h + 2); ctx.lineTo(X - 4, Y - h - 3);
        ctx.fill();
      }
      // name + condition bar
      ctx.font = 'bold 10px "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = '#fff';
      ctx.strokeStyle = 'rgba(10,16,22,0.8)';
      ctx.lineWidth = 2.5;
      ctx.strokeText(g.name, X, Y - h * 1.15 - 10);
      ctx.fillText(g.name, X, Y - h * 1.15 - 10);
      barRow(ctx, X - 20, Y - h * 1.15 - 7, 40, 4, g.cond, SIDE[g.side]);
      if (g.dueling) {
        ctx.strokeStyle = 'rgba(255,255,255,0.6)';
        ctx.lineWidth = 1.2;
        ctx.setLineDash([4, 3]);
        ctx.beginPath(); ctx.arc(X, Y - h * 0.4, h * 0.9, 0, 6.283); ctx.stroke();
        ctx.setLineDash([]);
      }
    });
    // ---- floaters (eased rise)
    floaters = floaters.filter(f => now - f.born < 1300);
    ctx.font = 'bold 10px Consolas, monospace';
    ctx.textAlign = 'center';
    for (const f of floaters) {
      const p = (now - f.born) / 1300;
      const e = easeOutCubic(p);
      ctx.globalAlpha = 1 - e;
      ctx.fillStyle = f.color;
      const y = py(f.y) - sc * 2.5 - e * 34;
      const scf = 0.85 + (1 - e) * 0.22;
      ctx.save();
      ctx.translate(px(f.x), y);
      ctx.scale(scf, scf);
      ctx.fillText(f.text, 0, 0);
      ctx.restore();
    }
    ctx.globalAlpha = 1;
    // ---- duel cinema inset
    drawDuelInset(ctx, b, b.generals, W, H, now);
    // ---- phase banner (slide+scale tween)
    const ps = (now - phaseAt) / 1000;
    if (ps < 2.4 && phaseLabel) {
      const p = ps / 2.4;
      const e = p < 0.18 ? easeOutBack(p / 0.18)
              : p > 0.78 ? easeOutCubic((1 - p) / 0.22) : 1;
      const alpha = clamp(p < 0.15 ? p / 0.15
                        : p > 0.78 ? (1 - p) / 0.22 : 1, 0, 1);
      ctx.save();
      ctx.globalAlpha = alpha;
      const y = H * 0.55 - (1 - e) * H * 0.08;
      const s = 0.92 + (1 - e) * 0.18;
      ctx.translate(W / 2, y);
      ctx.scale(s, s);
      ctx.font = 'bold 30px "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = lastPhase === 'rout' ? '#ffb26b' : '#e8d9a0';
      ctx.strokeStyle = 'rgba(8,12,18,0.85)';
      ctx.lineWidth = 5;
      ctx.strokeText(phaseLabel, 0, 0);
      ctx.fillText(phaseLabel, 0, 0);
      ctx.restore();
    }
    // ---- result overlay (fade/scale in)
    if (b.result) {
      const t = clamp((now - resultAt) / 900, 0, 1);
      const e = easeOutCubic(t);
      ctx.fillStyle = `rgba(6,10,14,${0.35 * e})`;
      ctx.fillRect(0, 0, W, H);
      ctx.save();
      ctx.globalAlpha = e;
      const s = 0.9 + e * 0.1;
      ctx.translate(W / 2, H * 0.5);
      ctx.scale(s, s);
      ctx.font = 'bold 26px "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = '#f1c40f';
      ctx.strokeStyle = 'rgba(8,12,18,0.9)';
      ctx.lineWidth = 5;
      const txt = `⚑ ${b.result.winner} HOLDS THE FIELD`;
      ctx.strokeText(txt, 0, 0);
      ctx.fillText(txt, 0, 0);
      ctx.restore();
    }
    ctx.restore();
  }

  function drawCorpse(ctx, x, y, h, face, col) {
    ctx.save();
    ctx.globalAlpha = 0.6;
    ctx.fillStyle = 'rgba(105,18,22,0.4)';
    ctx.beginPath(); ctx.ellipse(x, y, h * 0.4, h * 0.13, 0, 0, 6.283); ctx.fill();
    ctx.strokeStyle = col;
    ctx.lineWidth = Math.max(1, h * 0.09);
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(x - h * 0.28 * face, y); ctx.lineTo(x + h * 0.22 * face, y - h * 0.04);
    ctx.stroke();
    ctx.fillStyle = col;
    ctx.beginPath(); ctx.arc(x - h * 0.36 * face, y - h * 0.02, h * 0.08, 0, 6.283);
    ctx.fill();
    ctx.restore();
  }

  // ------------------------------------------------------------ buttons
  document.getElementById('bclose').onclick = closeBattle;
  document.getElementById('watch').onclick = async () => {
    const r = await fetch('/api/battles');
    const d = await r.json();
    if (d.battles.length) openBattle(d.battles[d.battles.length - 1].id);
    else {
      const box = document.getElementById('chron');
      const el = document.createElement('div');
      el.textContent = '—— no live battles right now; wait for armies to clash, or stage one ——';
      box.appendChild(el);
      box.scrollTop = box.scrollHeight;
    }
  };
  const stageBtn = document.getElementById('stage');
  if (stageBtn) stageBtn.onclick = async () => {
    const r = await fetch('/api/debug_battle', { method: 'POST' });
    const d = await r.json();
    if (d && d.id !== undefined) openBattle(d.id);
  };
})();

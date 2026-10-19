// LAB, live — "what the rig changed", drawn from the Pi's `lab` block.
//
// *** THIS FILE DRAWS. IT DOES NOT MEASURE. ***
//
// Every number on this screen arrives finished in `f.lab` (pi/web/lab.py) or in
// the Teensy-authored `f.authority` / `f.tone`. There is no logarithm, no sum,
// no fit and no FFT here — even the log-frequency axis arrives as 0..1
// positions. What this file decides is ADR-005 §7's list and nothing else:
// geometry, colour, layout, typography, and keeping a short history of frames
// it has already been given so they can be drawn as a trail.
//
// *** ABSENCE IS DRAWN AS ABSENCE. ***
//
// A null from the Pi is a worded gap (ui.js `gap`), a missing bar, or a hatched
// cell — never a zero, never a line drawn through it. A clipped frame is shown
// live with its flag and is excluded from every running statistic on the Pi.

import { esc, gap } from "./ui.js";

// ---- drawing constants (choices, not measurements) --------------------------

const SPEC_TOP_DB = 0;          // reference magnitude 1.0
const SPEC_BOT_DB = -90;        // display floor of the overlay. Not a noise floor.
const EQ_RANGE_DB = 15;         // EQ / spectrogram colour range, ± this
const TF_RANGE_DB = 24;         // the firmware's TF rail
const DYN_LO_DBFS = -60;        // dynamics plot extent
const HISTORY_ROWS = 216;       // spectrogram rows kept (~10 s of frames)
const TRAIL = 240;              // descriptor trail length
const PAD = { l: 52, r: 14, t: 12, b: 30 };

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

// Diverging scale for "return minus input": violet cut, neutral, green boost.
function hexRgb(h) {
  const v = parseInt(h.replace("#", ""), 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}
function mix(a, b, t) {
  return a.map((x, i) => Math.round(x + (b[i] - x) * t));
}
let LUT = null;
function lut() {
  if (LUT) return LUT;
  const cut = hexRgb(css("--cut")), mid = hexRgb(css("--diverge-mid")), boost = hexRgb(css("--boost"));
  LUT = [];
  for (let k = 0; k <= 60; k += 1) {
    const t = k / 30 - 1;          // -1 .. 1
    const c = t < 0 ? mix(mid, cut, Math.pow(-t, 0.75)) : mix(mid, boost, Math.pow(t, 0.75));
    LUT.push(`rgb(${c[0]},${c[1]},${c[2]})`);
  }
  return LUT;
}
function divColor(db) {
  const t = Math.max(-1, Math.min(1, db / EQ_RANGE_DB));
  return lut()[Math.round((t + 1) * 30)];
}

// ---- formatting (presentation of finished numbers) ---------------------------

function signed(v, digits = 1) {
  const s = v.toFixed(digits);
  return v > 0 ? `+${s}` : s.replace("-", "−");
}
function hz(v) {
  return v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 1 : 2)} kHz` : `${v.toFixed(0)} Hz`;
}
const fin = (v) => typeof v === "number" && Number.isFinite(v);

// ---- canvas plumbing ----------------------------------------------------------

function makeCanvas(host) {
  const c = document.createElement("canvas");
  host.appendChild(c);
  const ctx = c.getContext("2d");
  const s = { c, ctx, w: 0, h: 0 };
  // TODO-80's rule: size is read every draw, because a hidden or freshly
  // resized kiosk surface measures differently from the one at construction.
  s.fit = () => {
    const dpr = window.devicePixelRatio || 1;
    const w = host.clientWidth, h = host.clientHeight;
    if (w <= 0 || h <= 0) return false;
    if (w !== s.w || h !== s.h) {
      s.w = w; s.h = h;
      c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
      c.style.width = `${w}px`; c.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      s.resized = true;
    }
    return true;
  };
  return s;
}

function plotBox(s) {
  return { x: PAD.l, y: PAD.t, w: s.w - PAD.l - PAD.r, h: s.h - PAD.t - PAD.b };
}

function freqGrid(ctx, box, axis, { labels = true } = {}) {
  ctx.strokeStyle = css("--grid");
  ctx.lineWidth = 1;
  ctx.fillStyle = css("--ink-2");
  ctx.font = "600 14px \"DejaVu Sans\", system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  for (const t of axis.ticks) {
    const x = box.x + t.x * box.w;
    ctx.beginPath(); ctx.moveTo(x + 0.5, box.y); ctx.lineTo(x + 0.5, box.y + box.h); ctx.stroke();
    if (labels) ctx.fillText(t.label, x, box.y + box.h + 8);
  }
}

function dbGrid(ctx, box, ticks, toY, unit) {
  ctx.font = "600 14px \"DejaVu Sans\", system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (const v of ticks) {
    const y = toY(v);
    ctx.strokeStyle = v === 0 ? css("--grid-strong") : css("--grid");
    ctx.beginPath(); ctx.moveTo(box.x, y + 0.5); ctx.lineTo(box.x + box.w, y + 0.5); ctx.stroke();
    ctx.fillStyle = css("--ink-2");
    ctx.fillText(`${v > 0 ? "+" : ""}${v}`, box.x - 8, y);
  }
  if (unit) {
    ctx.save();
    ctx.translate(14, box.y + box.h / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center";
    ctx.fillStyle = css("--ink-3");
    ctx.font = "600 12px \"DejaVu Sans\", system-ui, sans-serif";
    ctx.fillText(unit, 0, 0);
    ctx.restore();
  }
}

function cursorLine(ctx, box, axis, sel) {
  if (sel === null) return;
  const b = axis.bins[sel];
  if (!b) return;
  const x0 = box.x + b.x0 * box.w, x1 = box.x + b.x1 * box.w;
  ctx.fillStyle = "rgba(255,255,255,0.08)";
  ctx.fillRect(x0, box.y, Math.max(2, x1 - x0), box.h);
  ctx.strokeStyle = "rgba(255,255,255,0.65)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo((x0 + x1) / 2, box.y); ctx.lineTo((x0 + x1) / 2, box.y + box.h); ctx.stroke();
  ctx.setLineDash([]);
}

// ---- the charts -------------------------------------------------------------

function drawOverlay(s, L, sel) {
  const { ctx } = s;
  const box = plotBox(s);
  const ax = L.axis;
  const fr = L.frame;
  ctx.clearRect(0, 0, s.w, s.h);
  const toY = (db) => box.y + (SPEC_TOP_DB - Math.max(SPEC_BOT_DB, Math.min(SPEC_TOP_DB, db)))
    / (SPEC_TOP_DB - SPEC_BOT_DB) * box.h;
  dbGrid(ctx, box, [0, -20, -40, -60, -80], toY, "dB rel. 1.0 (not dBFS)");
  freqGrid(ctx, box, ax);

  // The firmware's energised gate, named on the plot so a quiet bin is read as
  // quiet rather than as missing.
  const fy = toY(L.floor_db);
  ctx.strokeStyle = css("--ink-3");
  ctx.setLineDash([2, 5]);
  ctx.beginPath(); ctx.moveTo(box.x, fy); ctx.lineTo(box.x + box.w, fy); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = css("--ink-3");
  ctx.textAlign = "right"; ctx.textBaseline = "bottom";
  ctx.font = "600 12px \"DejaVu Sans\", system-ui, sans-serif";
  ctx.fillText("energised gate", box.x + box.w - 4, fy - 3);

  // Difference fill: one column per bin where both channels clear the gate.
  for (let k = 0; k < ax.bins.length; k += 1) {
    const b = ax.bins[k];
    const x0 = box.x + b.x0 * box.w, x1 = box.x + b.x1 * box.w;
    const c = fr.cells[k];
    const si = fr.src_db[k], ro = fr.ret_matched_db[k];
    if (c === "B" && fin(si) && fin(ro)) {
      ctx.fillStyle = divColor(fr.delta_db[k]);
      ctx.globalAlpha = 0.55;
      const ya = toY(si), yb = toY(ro);
      ctx.fillRect(x0, Math.min(ya, yb), Math.max(1, x1 - x0), Math.max(1.5, Math.abs(yb - ya)));
      ctx.globalAlpha = 1;
    } else if (c === "R" && fin(ro)) {
      ctx.fillStyle = css("--added");
      ctx.globalAlpha = 0.28;
      ctx.fillRect(x0, toY(ro), Math.max(1, x1 - x0), box.y + box.h - toY(ro));
      ctx.globalAlpha = 1;
    }
  }

  // The two traces. A null breaks the line: absence is not interpolated.
  function trace(vals, color, width) {
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineJoin = "round";
    ctx.beginPath();
    let pen = false;
    for (let k = 0; k < ax.bins.length; k += 1) {
      const v = vals[k];
      if (!fin(v)) { pen = false; continue; }
      const b = ax.bins[k];
      const x = box.x + ((b.x0 + b.x1) / 2) * box.w, y = toY(v);
      if (pen) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      pen = true;
    }
    ctx.stroke();
  }
  ctx.shadowBlur = 10;
  ctx.shadowColor = css("--warm");
  trace(fr.src_db, css("--warm"), 2.5);
  ctx.shadowColor = css("--cold");
  trace(fr.ret_matched_db, css("--cold"), 2.5);
  ctx.shadowBlur = 0;
  cursorLine(ctx, box, ax, sel);
}

function drawEq(s, L, sel) {
  const { ctx } = s;
  const box = plotBox(s);
  const ax = L.axis;
  const eq = L.eq;
  ctx.clearRect(0, 0, s.w, s.h);
  const toY = (db) => box.y + box.h / 2 - Math.max(-EQ_RANGE_DB, Math.min(EQ_RANGE_DB, db))
    / EQ_RANGE_DB * (box.h / 2);
  dbGrid(ctx, box, [12, 6, 0, -6, -12], toY, "dB, level-matched");
  freqGrid(ctx, box, ax);

  const y0 = toY(0);
  for (let k = 0; k < ax.bins.length; k += 1) {
    const v = eq.db[k];
    if (!fin(v)) continue;
    const b = ax.bins[k];
    const x0 = box.x + b.x0 * box.w + 1, x1 = box.x + b.x1 * box.w - 1;
    const w = Math.max(1.5, x1 - x0);
    const y = toY(v);
    // Spread band: how much this bin moved frame to frame.
    const sd = eq.sd[k];
    if (fin(sd)) {
      ctx.fillStyle = "rgba(255,255,255,0.10)";
      ctx.fillRect(x0, toY(v + sd), w, toY(v - sd) - toY(v + sd));
    }
    ctx.fillStyle = divColor(v);
    ctx.fillRect(x0, Math.min(y, y0), w, Math.max(2, Math.abs(y - y0)));
  }
  cursorLine(ctx, box, ax, sel);
}

function drawTf(s, L, sel) {
  const { ctx } = s;
  const box = plotBox(s);
  const ax = L.axis;
  const tf = L.tf;
  ctx.clearRect(0, 0, s.w, s.h);
  const toY = (db) => box.y + box.h / 2 - Math.max(-TF_RANGE_DB, Math.min(TF_RANGE_DB, db))
    / TF_RANGE_DB * (box.h / 2);
  dbGrid(ctx, box, [24, 12, 0, -12, -24], toY, "Teensy TF dB");
  freqGrid(ctx, box, ax);
  for (let k = 0; k < ax.bins.length; k += 1) {
    const b = ax.bins[k];
    const x = box.x + ((b.x0 + b.x1) / 2) * box.w;
    const c = tf.cls[k];
    const v = tf.db[k];
    if (c === "U" || !fin(v)) {
      // Pen-lift: a short tick on the axis, so a gap reads as a gap.
      ctx.fillStyle = css("--ink-3");
      ctx.fillRect(x - 0.5, box.y + box.h - 6, 1, 6);
      continue;
    }
    const y = toY(v);
    if (c === "C") {
      ctx.fillStyle = css("--amber");
      ctx.beginPath();
      const up = v > 0;
      ctx.moveTo(x, y + (up ? -6 : 6)); ctx.lineTo(x - 5, y + (up ? 3 : -3)); ctx.lineTo(x + 5, y + (up ? 3 : -3));
      ctx.fill();
    } else {
      ctx.fillStyle = css("--tf");
      ctx.beginPath(); ctx.arc(x, y, 3.2, 0, Math.PI * 2); ctx.fill();
    }
  }
  cursorLine(ctx, box, ax, sel);
}

function drawDiffGram(s, hist, ax) {
  const { ctx } = s;
  const box = { x: PAD.l, y: 8, w: s.w - PAD.l - PAD.r, h: s.h - 8 - PAD.b };
  ctx.clearRect(0, 0, s.w, s.h);
  ctx.fillStyle = css("--diverge-mid");
  ctx.fillRect(box.x, box.y, box.w, box.h);
  const rh = box.h / HISTORY_ROWS;
  const quiet = css("--panel-3");
  const hatch = css("--ink-4");
  const added = css("--added");
  const cut = css("--cut-deep");
  for (let r = 0; r < hist.length; r += 1) {
    const row = hist[hist.length - 1 - r];          // newest at the top
    const y = box.y + r * rh;
    if (row.gap) {
      ctx.fillStyle = css("--ink-3");
      ctx.fillRect(box.x, y, box.w, Math.max(1, rh));
      continue;
    }
    for (let k = 0; k < ax.bins.length; k += 1) {
      const c = row.cells[k];
      const b = ax.bins[k];
      const x0 = box.x + b.x0 * box.w, x1 = box.x + b.x1 * box.w;
      let col;
      if (c === "B") col = divColor(row.delta[k]);
      else if (c === "R") col = added;
      else if (c === "I") col = cut;
      else if (c === "u") col = hatch;
      else col = quiet;
      ctx.fillStyle = col;
      ctx.fillRect(x0, y, Math.max(1, x1 - x0) + 0.5, rh + 0.5);
    }
  }
  freqGrid(ctx, box, ax);
  ctx.fillStyle = css("--ink-2");
  ctx.textAlign = "right"; ctx.textBaseline = "top";
  ctx.font = "700 13px \"DejaVu Sans\", system-ui, sans-serif";
  ctx.fillText("now", box.x - 8, box.y);
  ctx.textBaseline = "bottom";
  ctx.fillText(`−${HISTORY_ROWS}`, box.x - 8, box.y + box.h);
  ctx.fillText("frames", box.x - 8, box.y + box.h - 16);
}

function drawDynamics(s, L, auth) {
  const { ctx } = s;
  const d = L.dynamics;
  const pad = { l: 46, r: 12, t: 12, b: 34 };
  const side = Math.min(s.w - pad.l - pad.r, s.h - pad.t - pad.b);
  const box = { x: pad.l, y: pad.t, w: side, h: side };
  ctx.clearRect(0, 0, s.w, s.h);
  const toX = (v) => box.x + (Math.max(DYN_LO_DBFS, Math.min(0, v)) - DYN_LO_DBFS) / -DYN_LO_DBFS * box.w;
  const toY = (v) => box.y + box.h - (Math.max(DYN_LO_DBFS, Math.min(0, v)) - DYN_LO_DBFS) / -DYN_LO_DBFS * box.h;

  ctx.font = "600 13px \"DejaVu Sans\", system-ui, sans-serif";
  for (let v = DYN_LO_DBFS; v <= 0; v += 20) {
    ctx.strokeStyle = css("--grid");
    ctx.beginPath(); ctx.moveTo(toX(v) + 0.5, box.y); ctx.lineTo(toX(v) + 0.5, box.y + box.h); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(box.x, toY(v) + 0.5); ctx.lineTo(box.x + box.w, toY(v) + 0.5); ctx.stroke();
    ctx.fillStyle = css("--ink-2");
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    ctx.fillText(String(v), toX(v), box.y + box.h + 6);
    ctx.textAlign = "right"; ctx.textBaseline = "middle";
    ctx.fillText(String(v), box.x - 6, toY(v));
  }
  ctx.fillStyle = css("--ink-3");
  ctx.textAlign = "center"; ctx.textBaseline = "bottom";
  ctx.fillText("input peak dBFS →", box.x + box.w / 2, s.h - 1);

  // Unity: what a wire would draw.
  ctx.strokeStyle = css("--ink-3");
  ctx.setLineDash([5, 5]);
  ctx.beginPath(); ctx.moveTo(toX(DYN_LO_DBFS), toY(DYN_LO_DBFS)); ctx.lineTo(toX(0), toY(0)); ctx.stroke();
  ctx.setLineDash([]);

  if (fin(d.slope) && fin(d.intercept)) {
    const xs = d.points.map((p) => p[0]);
    const lo = Math.min(...xs), hi = Math.max(...xs);
    ctx.strokeStyle = css("--boost");
    ctx.lineWidth = 3;
    ctx.shadowBlur = 8; ctx.shadowColor = css("--boost");
    ctx.beginPath();
    ctx.moveTo(toX(lo), toY(d.intercept + d.slope * lo));
    ctx.lineTo(toX(hi), toY(d.intercept + d.slope * hi));
    ctx.stroke();
    ctx.shadowBlur = 0; ctx.lineWidth = 1;
  }
  const n = d.points.length;
  for (let k = 0; k < n; k += 1) {
    const [a, b] = d.points[k];
    ctx.globalAlpha = 0.2 + 0.8 * ((k + 1) / n);
    ctx.fillStyle = css("--cold");
    ctx.beginPath(); ctx.arc(toX(a), toY(b), 3, 0, Math.PI * 2); ctx.fill();
  }
  ctx.globalAlpha = 1;

  // The current frame, ringed.
  const pin = auth.peak_source_dbfs, pout = auth.peak_return_dbfs;
  if (fin(pin) && fin(pout)) {
    ctx.strokeStyle = auth.source_clip || auth.return_clip ? css("--coral") : css("--ink-1");
    ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.arc(toX(pin), toY(pout), 8, 0, Math.PI * 2); ctx.stroke();
    ctx.lineWidth = 1;
  }
}

function drawBalance(s, L) {
  const { ctx } = s;
  const edges = L.octave_edges;
  const sin = L.frame.input?.octave_share, sout = L.frame.return?.octave_share;
  ctx.clearRect(0, 0, s.w, s.h);
  const rows = edges.length - 1;
  const top = 6, left = 92, right = 12;
  const rowH = (s.h - top - 8) / rows;
  const bw = s.w - left - right;
  ctx.font = "600 13px \"DejaVu Sans\", system-ui, sans-serif";
  for (let k = 0; k < rows; k += 1) {
    const y = top + k * rowH;
    const lo = edges[k], hi = edges[k + 1];
    const label = `${lo >= 1000 ? `${lo / 1000}k` : lo}–${hi >= 1000 ? `${Math.round(hi / 100) / 10}k` : hi}`;
    ctx.fillStyle = css("--ink-2");
    ctx.textAlign = "right"; ctx.textBaseline = "middle";
    ctx.fillText(label, left - 8, y + rowH / 2);
    ctx.fillStyle = css("--panel-3");
    ctx.fillRect(left, y + 3, bw, rowH - 6);
    const bh = (rowH - 10) / 2;
    if (sin && fin(sin[k])) {
      ctx.fillStyle = css("--warm");
      ctx.fillRect(left, y + 4, Math.max(1, sin[k] * bw), bh);
    }
    if (sout && fin(sout[k])) {
      ctx.fillStyle = css("--cold");
      ctx.fillRect(left, y + 6 + bh, Math.max(1, sout[k] * bw), bh);
    }
  }
}

function drawTrail(s, trail, series, { lo, hi, fmt }) {
  const { ctx } = s;
  const box = { x: 46, y: 8, w: s.w - 46 - 10, h: s.h - 8 - 10 };
  ctx.clearRect(0, 0, s.w, s.h);
  const toY = (v) => box.y + box.h - (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo) * box.h;
  ctx.font = "600 12px \"DejaVu Sans\", system-ui, sans-serif";
  for (const v of [lo, (lo + hi) / 2, hi]) {
    ctx.strokeStyle = css("--grid");
    ctx.beginPath(); ctx.moveTo(box.x, toY(v) + 0.5); ctx.lineTo(box.x + box.w, toY(v) + 0.5); ctx.stroke();
    ctx.fillStyle = css("--ink-2");
    ctx.textAlign = "right"; ctx.textBaseline = "middle";
    ctx.fillText(fmt(v), box.x - 6, toY(v));
  }
  function line(key, color) {
    ctx.strokeStyle = color; ctx.lineWidth = 2.2;
    ctx.beginPath();
    let pen = false;
    for (let k = 0; k < trail.length; k += 1) {
      const v = trail[k][key];
      if (!fin(v)) { pen = false; continue; }
      const x = box.x + (k + TRAIL - trail.length) / (TRAIL - 1) * box.w;
      if (pen) ctx.lineTo(x, toY(v)); else ctx.moveTo(x, toY(v));
      pen = true;
    }
    ctx.stroke();
    ctx.lineWidth = 1;
  }
  for (const [key, color] of series) line(key, css(color));
}

// ---- HTML ---------------------------------------------------------------------

const TEMPLATE = `
<div class="lab-dash">
  <header class="ld-hero">
    <div>
      <div class="ld-kicker">LAB · live</div>
      <h1 class="ld-title">What the rig changed</h1>
    </div>
    <div class="ld-chips" data-slot="chips"></div>
  </header>

  <section class="ld-kpis" data-slot="kpis"></section>

  <section class="ld-card">
    <div class="ld-card-head">
      <h2>Input vs return, this frame</h2>
      <div class="ld-legend">
        <span><i class="sw sw-in"></i>input</span>
        <span><i class="sw sw-out"></i>return, level-matched</span>
        <span><i class="sw sw-boost"></i>rig louder</span>
        <span><i class="sw sw-cut"></i>rig quieter</span>
        <span><i class="sw sw-added"></i>rig-only</span>
      </div>
    </div>
    <div class="ld-plot ld-plot-overlay" data-plot="overlay"></div>
    <div class="ld-readout" data-slot="readout"></div>
  </section>

  <section class="ld-card">
    <div class="ld-card-head">
      <h2>The rig's EQ signature</h2>
      <div class="ld-sub" data-slot="eq-sub"></div>
    </div>
    <div class="ld-plot ld-plot-eq" data-plot="eq"></div>
    <p class="ld-note">Each bar: the return's level over the input's in that band, power-averaged
      over recent played frames, after removing the overall level change. The pale band is how much
      it moved frame to frame. Bands where both signals weren't above the gate get no bar.</p>
  </section>

  <section class="ld-card">
    <div class="ld-card-head">
      <h2>Difference spectrogram</h2>
      <div class="ld-legend">
        <span><i class="sw sw-ramp"></i>−${EQ_RANGE_DB} … +${EQ_RANGE_DB} dB</span>
        <span><i class="sw sw-added"></i>rig-only</span>
        <span><i class="sw sw-cutdeep"></i>rig removed it</span>
      </div>
    </div>
    <div class="ld-plot ld-plot-gram" data-plot="gram"></div>
  </section>

  <div class="ld-pair">
    <section class="ld-card">
      <div class="ld-card-head"><h2>Dynamics: peak in → out</h2></div>
      <div class="ld-plot ld-plot-dyn" data-plot="dyn"></div>
      <div class="ld-sub" data-slot="dyn-sub"></div>
    </section>
    <section class="ld-card">
      <div class="ld-card-head">
        <h2>Tonal balance</h2>
        <div class="ld-legend"><span><i class="sw sw-in"></i>in</span><span><i class="sw sw-out"></i>out</span></div>
      </div>
      <div class="ld-plot ld-plot-bal" data-plot="bal"></div>
      <div class="ld-sub">share of energy per octave, this frame</div>
    </section>
  </div>

  <div class="ld-pair">
    <section class="ld-card">
      <div class="ld-card-head"><h2>Brightness over time</h2></div>
      <div class="ld-plot ld-plot-trail" data-plot="trail-c"></div>
      <div class="ld-sub">spectral centroid · <b class="t-in">input</b> · <b class="t-out">return</b></div>
    </section>
    <section class="ld-card">
      <div class="ld-card-head"><h2>Tilt change over time</h2></div>
      <div class="ld-plot ld-plot-trail" data-plot="trail-t"></div>
      <div class="ld-sub">return minus input, dB per octave</div>
    </section>
  </div>

  <section class="ld-card">
    <div class="ld-card-head">
      <h2>Teensy transfer function <span class="ld-auth">instrument-authored</span></h2>
      <div class="ld-legend">
        <span><i class="sw sw-tf"></i>measured</span>
        <span><i class="sw sw-clamp"></i>on the ±24 dB rail</span>
        <span><i class="sw sw-gap"></i>pen-lift</span>
      </div>
    </div>
    <div class="ld-plot ld-plot-tf" data-plot="tf"></div>
    <div class="ld-integrity" data-slot="integrity"></div>
  </section>

  <section class="ld-card ld-limits">
    <h2>What this screen cannot see</h2>
    <ul>
      <li><b>Bands are ~172 Hz wide.</b> Individual guitar harmonics below ~1 kHz share a band, so
        nothing here resolves pitch or a single harmonic.</li>
      <li><b>Magnitude only.</b> The live frame carries no phase or coherence, so a band's change can't be
        split into "EQ" versus "distortion landing in the same band". Rig-only energy is the part
        that lands where the input had none.</li>
      <li><b>Uncalibrated.</b> Levels are dB relative to FFT magnitude 1.0, not dBFS. Differences between
        input and return are meaningful; absolute levels are not.</li>
      <li><b>Clipped frames don't count.</b> They are drawn live and flagged, but excluded from every
        running statistic.</li>
      <li>Every number is computed on the Pi from the Teensy's spectra and peaks
        (<code>pi/web/lab.py</code>). The Teensy's own grades and insights appear when it sends a RESULT.</li>
    </ul>
  </section>
</div>`;

function tile(cls, label, valueHtml, sub, extra = "") {
  return `<article class="ld-kpi ${cls}">
    <div class="ld-kpi-label">${esc(label)}</div>
    <div class="ld-kpi-value">${valueHtml}</div>
    <div class="ld-kpi-sub">${sub}</div>${extra}
  </article>`;
}

function big(v, unit) {
  return `<span class="ld-num">${esc(v)}</span>${unit ? `<span class="ld-unit">${esc(unit)}</span>` : ""}`;
}

function kpis(f, L) {
  const tone = f.tone || {};
  const sm = L.smooth || {};
  const held = L.smooth_held ? `<span class="ld-held">held</span>` : "";
  const out = [];

  // LEVEL — TONE's matched gain, same number, same states.
  if (fin(tone.gain_db)) {
    out.push(tile("k-level", "Level change", big(signed(tone.gain_db), "dB"),
      `return vs input · ${tone.gain_bins} bands${tone.gain_state === "held" ? " · <span class=\"ld-held\">held</span>" : ""}`));
  } else if (fin(tone.gain_bound_db)) {
    out.push(tile("k-level", "Level change", big(`< ${signed(tone.gain_bound_db)}`, "dB"),
      "return below the gate everywhere the input is above it"));
  } else {
    out.push(tile("k-level", "Level change", gap("not established yet: play"), "needs input above the gate"));
  }

  // BRIGHTNESS — centroid shift.
  if (fin(sm.centroid_cents)) {
    const oct = sm.centroid_cents / 1200;
    out.push(tile("k-bright", "Brightness shift", big(signed(sm.centroid_cents, 0), "¢"),
      `${fin(sm.centroid_in) ? hz(sm.centroid_in) : "?"} → ${fin(sm.centroid_out) ? hz(sm.centroid_out) : "?"} · ${signed(oct, 2)} oct ${held}`,
      `<div class="ld-kpi-bar"><span style="left:50%;width:${Math.min(50, Math.abs(oct) * 50)}%;${oct < 0 ? "transform:translateX(-100%)" : ""}"></span></div>`));
  } else {
    out.push(tile("k-bright", "Brightness shift", gap("not established yet"), "spectral centroid, return vs input"));
  }

  // TILT
  out.push(fin(sm.tilt_db_oct)
    ? tile("k-tilt", "Tilt change", big(signed(sm.tilt_db_oct), "dB/oct"),
      `return minus input · slope of level vs octave ${held}`)
    : tile("k-tilt", "Tilt change", gap("not established yet"), "slope of level vs octave"));

  // ADDED
  out.push(fin(sm.added_pct)
    ? tile("k-added", "Added content", big(sm.added_pct.toFixed(1), "%"),
      `of return energy where the input had none ${held}`)
    : tile("k-added", "Added content", gap("not established yet"), "energy only the rig produced"));

  // DYNAMICS
  const d = L.dynamics;
  out.push(fin(d.slope)
    ? tile("k-dyn", "Dynamics slope", big(d.slope.toFixed(2), ""),
      `1.00 = linear · ${d.slope > 0 ? `≈ ${(1 / d.slope).toFixed(1)} : 1` : ""} · r² ${fin(d.r2) ? d.r2.toFixed(2) : "?"} · n ${d.n}`)
    : tile("k-dyn", "Dynamics slope", gap(d.why || "not established yet"), "output peak vs input peak"));

  // SELF-NOISE
  const idle = L.idle;
  out.push(fin(idle.excess_db)
    ? tile("k-noise", "Rig self-noise", big(signed(idle.excess_db), "dB"),
      `return over input, strings silent · ${idle.frames} frames`)
    : tile("k-noise", "Rig self-noise", gap(idle.why || "not established yet"), "return over input with nothing played"));

  return out.join("");
}

function chips(f, L) {
  const a = f.authority || {};
  const tone = f.tone || {};
  const c = [];
  const playing = tone.gain_state === "live";
  c.push(`<span class="ld-chip ${playing ? "on" : ""}"><i></i>${playing ? "SIGNAL" : "NO SIGNAL"}</span>`);
  if (a.source_clip) c.push(`<span class="ld-chip bad">▲ INPUT CLIP</span>`);
  if (a.return_clip) c.push(`<span class="ld-chip bad">▲ RETURN CLIP</span>`);
  c.push(`<span class="ld-chip">${esc(String(L.eq.frames))} played frames</span>`);
  if (L.frames_clipped) c.push(`<span class="ld-chip warn">${esc(String(L.frames_clipped))} clipped, excluded</span>`);
  return c.join("");
}

function integrity(f, L) {
  const a = f.authority || {};
  const item = (k, v) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`;
  const n = (v, d = 2) => (fin(v) ? `<span class="num">${esc(v.toFixed(d))}</span>` : gap("not reported"));
  return `<dl>
    ${item("TF confidence", n(a.tf_confidence))}
    ${item("TF clamped bins", fin(a.tf_clamped_count) ? esc(String(a.tf_clamped_count)) : gap("not reported"))}
    ${item("TF persistence", a.tf_persistence_active === undefined ? gap("not reported")
      : a.tf_persistence_active ? `<span class="warn">holding last value</span>` : "fresh")}
    ${item("state", esc(a.measurement_state ?? "not reported"))}
    ${item("input peak", fin(a.peak_source_dbfs) ? `${esc(a.peak_source_dbfs.toFixed(1))} dBFS` : gap("not reported"))}
    ${item("return peak", fin(a.peak_return_dbfs) ? `${esc(a.peak_return_dbfs.toFixed(1))} dBFS` : gap("not reported"))}
    ${item("block", esc(String(a.output_block_number ?? "?")))}
    ${item("frames seen", esc(String(L.frames_seen)))}
  </dl>`;
}

function readout(L, sel) {
  if (sel === null) {
    return `<span class="ld-hint">Touch any spectrum chart to inspect a band</span>`;
  }
  const b = L.axis.bins[sel];
  const fr = L.frame;
  const v = (x, u = "dB") => (fin(x) ? `<b>${esc(signed(x))}</b> ${u}` : `<span class="gap">—none—</span>`);
  const cellWord = { B: "both above gate", R: "rig-only", I: "rig took it below the gate", q: "quiet", u: "unmeasured" }[fr.cells[sel]] || "?";
  return `<span class="ld-rb">${esc(hz(b.hz))}</span>
    <span>in ${v(fr.src_db[sel])}</span>
    <span>out ${v(fr.ret_matched_db[sel])}</span>
    <span>Δ ${v(fr.delta_db[sel])}</span>
    <span>EQ ${v(L.eq.db[sel])}${fin(L.eq.sd[sel]) ? ` ±${esc(L.eq.sd[sel].toFixed(1))}` : ""}</span>
    <span>Teensy TF ${v(L.tf.db[sel])} <small>unmatched</small></span>
    <span class="ld-rc">${esc(cellWord)}</span>`;
}

// ---- the view -------------------------------------------------------------------

export function createLabDashboard(root) {
  root.innerHTML = TEMPLATE;
  const slot = (n) => root.querySelector(`[data-slot="${n}"]`);
  const plots = {};
  for (const el of root.querySelectorAll("[data-plot]")) plots[el.dataset.plot] = makeCanvas(el);

  const hist = [];
  const trail = [];
  let lastBlock = null;
  let last = null;
  let sel = null;

  // A linked cursor: touching any frequency chart selects that band in all of
  // them. Presentation only — it picks an index into arrays already received.
  for (const name of ["overlay", "eq", "tf", "gram"]) {
    const p = plots[name];
    const pick = (ev) => {
      if (!last) return;
      const r = p.c.getBoundingClientRect();
      const t = (ev.clientX - r.left - PAD.l) / (r.width - PAD.l - PAD.r);
      const bins = last.lab.axis.bins;
      let best = null;
      for (let k = 0; k < bins.length; k += 1) {
        if (t >= bins[k].x0 && t <= bins[k].x1) { best = k; break; }
      }
      sel = best;
      draw(last, true);
    };
    p.c.addEventListener("pointerdown", pick);
    p.c.addEventListener("pointermove", (ev) => { if (ev.buttons || ev.pointerType === "mouse") pick(ev); });
  }

  function draw(f, cursorOnly = false) {
    const L = f.lab;
    for (const p of Object.values(plots)) p.fit();
    drawOverlay(plots.overlay, L, sel);
    drawEq(plots.eq, L, sel);
    drawTf(plots.tf, L, sel);
    slot("readout").innerHTML = readout(L, sel);
    if (cursorOnly) return;
    drawDiffGram(plots.gram, hist, L.axis);
    drawDynamics(plots.dyn, L, f.authority || {});
    drawBalance(plots.bal, L);
    drawTrail(plots["trail-c"], trail, [["cin", "--warm"], ["cout", "--cold"]], {
      lo: 0, hi: 4000, fmt: (v) => (v >= 1000 ? `${v / 1000}k` : `${v}`) });
    drawTrail(plots["trail-t"], trail, [["tilt", "--tf"]], {
      lo: -6, hi: 6, fmt: (v) => (v > 0 ? `+${v}` : `${v}`) });
  }

  return {
    update(f) {
      const L = f.lab;
      if (!L) return;
      last = f;
      // One history row per instrument frame, keyed on the block counter so a
      // repeated poll of the same frame is not drawn twice.
      if (L.block !== lastBlock) {
        if (lastBlock !== null && fin(L.block) && Math.abs(L.block - lastBlock) > 30) {
          hist.push({ gap: true });       // LAB was not watching: say so
        }
        lastBlock = L.block;
        hist.push({ cells: L.frame.cells, delta: L.frame.delta_db });
        if (hist.length > HISTORY_ROWS) hist.shift();
        const sm = L.smooth || {};
        trail.push({ cin: sm.centroid_in, cout: sm.centroid_out, tilt: L.smooth_held ? null : sm.tilt_db_oct });
        if (trail.length > TRAIL) trail.shift();

        slot("chips").innerHTML = chips(f, L);
        slot("kpis").innerHTML = kpis(f, L);
        slot("integrity").innerHTML = integrity(f, L);
        slot("eq-sub").innerHTML = fin(L.eq.gain_db)
          ? `${esc(String(L.eq.frames))} of ${esc(String(L.windows.eq))} frames · overall ${esc(signed(L.eq.gain_db))} dB removed`
          : gap("no played frames yet");
        const d = L.dynamics;
        slot("dyn-sub").innerHTML = fin(d.slope)
          ? `fit <b>${esc(d.slope.toFixed(2))}</b> · dashed = unity (a wire) · ring = now`
          : `${gap(d.why || "not established yet")} · dashed = unity`;
        draw(f);
      }
    },
  };
}

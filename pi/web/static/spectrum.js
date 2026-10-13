// SOURCE / RETURN magnitude spectrum, Canvas2D, on a log-frequency axis.
//
// *** THE UNIT IS NOT dBFS. ***
//
// These are Hann-windowed FFT magnitudes whose nominal full scale is 1.0, and
// that 1.0 has never been calibrated against a full-scale input on this
// instrument (payload.py, SPECTRUM_REFERENCE_NOTE). A Hann window has 0.5
// coherent gain, so a full-scale sine does not read 1.0 in its bin. The axis
// therefore says "dB rel. magnitude 1.0", never dBFS, and these values never
// share an axis with peak_source_dbfs -- a time-domain peak is a different
// quantity.
//
// *** THE DISPLAY FLOOR IS A DRAWING CHOICE, NOT A NOISE FLOOR. ***
//
// log10(0) is undefined and the real capture contains exact zeros -- three of
// them in the 2026-09-26 idle frame. A bin at exactly 0.0 is a genuine
// measurement of silence, so it is NOT discarded and NOT called unmeasured. It
// is drawn at FLOOR_DB because a line has to go somewhere, and every bin that
// was clipped to get there is marked, counted and reported. The instrument never
// said "-100 dB"; this renderer said "at or below the bottom of my axis".
//
// *** NO SECOND RESAMPLE. ***
// Every point is one transmitted bin at its own centre frequency. The firmware
// already decimated 512 -> 128 by MAXIMUM to preserve narrow peaks; reducing
// again here would flatten exactly what it preserved.

const FLOOR_DB = -100;      // display floor. A drawing choice. Not a measurement.
const TOP_DB = 0;           // reference magnitude 1.0
const AXIS_LO_HZ = 20;      // musical low end, so the uncovered region is VISIBLE
const PAD = { l: 46, r: 10, t: 10, b: 26 };

const HZ_TICKS = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
const DB_TICKS = [0, -20, -40, -60, -80, -100];

const css = (n) => getComputedStyle(document.documentElement)
  .getPropertyValue(n).trim();

function fmtHz(hz) {
  return hz >= 1000 ? `${hz / 1000}k` : `${hz}`;
}

export { FLOOR_DB, TOP_DB, AXIS_LO_HZ };

export function createSpectrum(container) {
  const canvas = document.createElement("canvas");
  canvas.className = "spectrum-canvas";
  container.appendChild(canvas);
  const ctx = canvas.getContext("2d");

  let spectra = null;
  let w = 0;
  let h = 0;

  // TODO-80's rule, restated for Canvas2D: a kiosk surface is resized after
  // first paint, and a hidden container measures 0. Size is a function.
  function resize() {
    const cw = container.clientWidth;
    const ch = container.clientHeight;
    if (cw <= 0 || ch <= 0) return false;
    if (cw === w && ch === h) return false;
    w = cw; h = ch;
    canvas.width = w;
    canvas.height = h;
    draw();
    return true;
  }
  if (typeof ResizeObserver === "function") {
    new ResizeObserver(() => resize()).observe(container);
  }

  const plot = () => ({
    x0: PAD.l, y0: PAD.t,
    x1: w - PAD.r, y1: h - PAD.b,
    get wi() { return this.x1 - this.x0; },
    get hi() { return this.y1 - this.y0; },
  });

  function draw() {
    if (!w || !h) return;
    const p = plot();
    const hiHz = spectra ? spectra.nyquist_hz : 22050;
    const lgLo = Math.log10(AXIS_LO_HZ);
    const lgHi = Math.log10(hiHz);
    const xOf = (hz) => p.x0 + ((Math.log10(hz) - lgLo) / (lgHi - lgLo)) * p.wi;
    const yOf = (db) => p.y1 - ((db - FLOOR_DB) / (TOP_DB - FLOOR_DB)) * p.hi;

    ctx.clearRect(0, 0, w, h);

    // --- grid ---------------------------------------------------------------
    ctx.strokeStyle = css("--hairline");
    ctx.fillStyle = css("--faint");
    ctx.lineWidth = 1;
    ctx.font = '10px "DejaVu Sans Mono", monospace';

    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const db of DB_TICKS) {
      const y = Math.round(yOf(db)) + 0.5;
      ctx.beginPath(); ctx.moveTo(p.x0, y); ctx.lineTo(p.x1, y); ctx.stroke();
      ctx.fillText(`${db}`, p.x0 - 6, y);
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (const hz of HZ_TICKS) {
      if (hz < AXIS_LO_HZ || hz > hiHz) continue;
      const x = Math.round(xOf(hz)) + 0.5;
      ctx.beginPath(); ctx.moveTo(x, p.y0); ctx.lineTo(x, p.y1); ctx.stroke();
      ctx.fillText(fmtHz(hz), x, p.y1 + 5);
    }

    if (!spectra) {
      ctx.fillStyle = css("--faint");
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = '12px "DejaVu Sans", sans-serif';
      ctx.fillText("no live frame", (p.x0 + p.x1) / 2, (p.y0 + p.y1) / 2);
      return;
    }

    const geo = spectra.geometry;

    // --- the region the instrument does not transmit -------------------------
    // Drawn rather than cropped. The lowest transmitted bin spans DC, so the
    // first usable bin starts above 150 Hz -- which is ABOVE the low E string's
    // 82 Hz fundamental. Cropping the axis to the data would hide that.
    const firstUsable = geo.find((g) => !g.dc);
    if (firstUsable && firstUsable.lo_hz > AXIS_LO_HZ) {
      const xEnd = xOf(firstUsable.lo_hz);
      ctx.save();
      ctx.beginPath();
      ctx.rect(p.x0, p.y0, xEnd - p.x0, p.hi);
      ctx.clip();
      ctx.fillStyle = "rgba(210,153,34,0.07)";
      ctx.fillRect(p.x0, p.y0, xEnd - p.x0, p.hi);
      ctx.strokeStyle = "rgba(210,153,34,0.30)";
      ctx.lineWidth = 1;
      for (let x = p.x0 - p.hi; x < xEnd; x += 7) {
        ctx.beginPath(); ctx.moveTo(x, p.y1); ctx.lineTo(x + p.hi, p.y0); ctx.stroke();
      }
      ctx.restore();
      ctx.save();
      ctx.translate(p.x0 + (xEnd - p.x0) / 2, p.y0 + p.hi / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.fillStyle = css("--unknown");
      ctx.font = '10px "DejaVu Sans", sans-serif';
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("not transmitted", 0, 0);
      ctx.restore();
    }

    // --- traces --------------------------------------------------------------
    const clipped = { src: 0, ret: 0 };

    function trace(points, key, colour, fill) {
      ctx.beginPath();
      let open = false;
      let lastX = 0;
      for (let i = 0; i < points.length; i++) {
        const g = geo[i];
        // DC bin excluded: its span starts at 0 Hz and decimateMax does not say
        // which source bin won, so it cannot be placed on a log axis.
        if (!g || g.dc) continue;
        const pt = points[i];
        // Pen-lift. An UNMEASURED bin breaks the line; it is never bridged.
        if (pt.cls !== "MEASURED" || pt.value === null) { open = false; continue; }
        const db = pt.value > 0 ? 20 * Math.log10(pt.value) : -Infinity;
        const atFloor = !(db > FLOOR_DB);
        if (atFloor) clipped[key]++;
        const x = xOf(g.hz);
        const y = yOf(atFloor ? FLOOR_DB : Math.min(db, TOP_DB));
        if (!open) { ctx.moveTo(x, y); open = true; } else { ctx.lineTo(x, y); }
        lastX = x;
      }
      ctx.strokeStyle = colour;
      ctx.lineWidth = fill ? 1.5 : 1.8;
      ctx.lineJoin = "round";
      ctx.stroke();
      if (fill && open) {
        ctx.lineTo(lastX, p.y1);
        ctx.lineTo(xOf(firstUsable ? firstUsable.hz : AXIS_LO_HZ), p.y1);
        ctx.closePath();
        const grad = ctx.createLinearGradient(0, p.y0, 0, p.y1);
        grad.addColorStop(0, colour + "66");
        grad.addColorStop(1, colour + "08");
        ctx.fillStyle = grad;
        ctx.fill();
      }
      return clipped[key];
    }

    trace(spectra.src, "src", css("--source"), true);
    trace(spectra.ret, "ret", css("--return"), false);

    // --- bins clipped to the floor, marked on the baseline -------------------
    // So graphical clipping is never mistaken for a measured level.
    if (clipped.src || clipped.ret) {
      ctx.fillStyle = css("--unknown");
      for (let i = 0; i < spectra.src.length; i++) {
        const g = geo[i];
        if (!g || g.dc) continue;
        const a = spectra.src[i], b = spectra.ret[i];
        const low = (v) => v && v.cls === "MEASURED" && v.value !== null
          && !(v.value > 0 && 20 * Math.log10(v.value) > FLOOR_DB);
        if (low(a) || low(b)) ctx.fillRect(Math.round(xOf(g.hz)) - 1, p.y1 - 3, 2, 3);
      }
    }

    // --- frame ---------------------------------------------------------------
    ctx.strokeStyle = css("--hairline");
    ctx.lineWidth = 1;
    ctx.strokeRect(p.x0 + 0.5, p.y0 + 0.5, p.wi - 1, p.hi - 1);

    draw.clipped = clipped;
  }

  return {
    update(next) { spectra = next || null; resize(); draw(); },
    resize,
    clippedCount() { return draw.clipped || { src: 0, ret: 0 }; },
  };
}

import { useState, useRef, useEffect, useCallback } from "react";

const W = 800;
const H = 480;

const COLORS = {
  bg: "#060a10",
  panelBg: "#0a0e16",
  cardBg: "#0c1018",
  gridLine: "rgba(40, 60, 90, 0.25)",
  gridMajor: "rgba(50, 80, 120, 0.35)",
  label: "#4a6578",
  labelBright: "#8ab0c8",
  separator: "rgba(30, 50, 80, 0.5)",
  white: "#d8e4f0",
  dim: "#2a3a4a",
};

const THEME = {
  source: {
    line: "#3498db",
    glow: "#2088d0",
    gradTop: "rgba(52, 152, 219, 0.55)",
    gradMid: "rgba(32, 100, 180, 0.25)",
    gradBot: "rgba(10, 30, 60, 0.02)",
  },
  ret: {
    line: "#2ecc71",
    glow: "#28b060",
    gradTop: "rgba(46, 204, 113, 0.45)",
    gradMid: "rgba(30, 140, 70, 0.18)",
    gradBot: "rgba(10, 40, 20, 0.02)",
  },
  tf: {
    line: "#f0a030",
    glow: "#e89020",
    gradPos: "rgba(240, 160, 48, 0.30)",
    gradNeg: "rgba(200, 120, 30, 0.15)",
    gradZero: "rgba(240, 160, 48, 0.02)",
  },
  meter: {
    green: "#2ecc71",
    yellow: "#f1c40f",
    red: "#e74c3c",
    bg: "#0e1520",
    peak: "#ffffff",
  },
  quality: { excellent: "#2ecc71", good: "#27ae60", marginal: "#f39c12", poor: "#e74c3c" },
  insight: { meas: "#f0a030", adv: "#5ba8a0", alert: "#e74c3c", detail: "#5a7888" },
};

// Attempt catmull-rom for smooth curves
function catmullRomSpline(points, segments = 4) {
  if (points.length < 2) return points;
  const result = [];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(i - 1, 0)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(i + 2, points.length - 1)];
    for (let t = 0; t < segments; t++) {
      const u = t / segments;
      const u2 = u * u;
      const u3 = u2 * u;
      const x = 0.5 * ((2 * p1.x) + (-p0.x + p2.x) * u + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * u2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * u3);
      const y = 0.5 * ((2 * p1.y) + (-p0.y + p2.y) * u + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * u2 + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * u3);
      result.push({ x, y });
    }
  }
  result.push(points[points.length - 1]);
  return result;
}

function generateSpectrum(seed, character) {
  const bins = 256;
  const data = [];
  for (let i = 0; i < bins; i++) {
    const freq = 20 * Math.pow(22050 / 20, i / bins);
    let db = -70;
    if (freq > 60 && freq < 16000) {
      db = -18 - character.rolloff * Math.max(0, Math.log10(freq / 200));
      for (const p of character.peaks) {
        const d = Math.abs(Math.log2(freq / p.f));
        if (d < 0.4) db = Math.max(db, p.db - d * 50);
      }
    }
    db += Math.sin(i * 5.7 + seed) * 1.8 + Math.sin(i * 2.3 + seed * 3) * 1.2;
    db += Math.sin(i * 0.8 + seed * 0.5) * 3;
    data.push(Math.max(-75, Math.min(-3, db)));
  }
  return data;
}

function generateTF(seed) {
  const bins = 256;
  const data = [];
  for (let i = 0; i < bins; i++) {
    const freq = 20 * Math.pow(22050 / 20, i / bins);
    if (freq < 35 || freq > 17000) { data.push(null); continue; }
    let db = 0;
    const bD = Math.abs(Math.log2(freq / 140));
    if (bD < 1.2) db += 5 * Math.pow(1 - bD / 1.2, 1.5);
    const mD = Math.abs(Math.log2(freq / 700));
    if (mD < 1) db -= 6 * Math.pow(1 - mD, 1.3);
    const pD = Math.abs(Math.log2(freq / 3200));
    if (pD < 0.6) db += 3.5 * Math.pow(1 - pD / 0.6, 1.2);
    if (freq > 7000) db -= 10 * Math.pow(Math.log10(freq / 7000), 1.5);
    db += Math.sin(i * 3.1 + seed) * 0.6 + Math.sin(i * 7.7 + seed * 2) * 0.3;
    data.push(db);
  }
  return data;
}

function freqToX(freq, x0, w) {
  const t = (Math.log10(Math.max(freq, 20)) - Math.log10(20)) / (Math.log10(20000) - Math.log10(20));
  return x0 + t * w;
}
function dbToY(db, minDb, maxDb, y0, h) {
  return y0 + ((db - maxDb) / (minDb - maxDb)) * h;
}

function drawRoundedRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function drawSmoothFilledCurve(ctx, data, x0, w, y0, h, minDb, maxDb, theme, baseY) {
  const pts = [];
  const step = Math.max(1, Math.floor(data.length / (w / 3)));
  for (let i = 0; i < data.length; i += step) {
    const t = i / data.length;
    const x = x0 + t * w;
    const y = dbToY(data[i], minDb, maxDb, y0, h);
    pts.push({ x, y: Math.max(y0, Math.min(baseY, y)) });
  }
  pts.push({ x: x0 + w, y: dbToY(data[data.length - 1], minDb, maxDb, y0, h) });

  const smooth = catmullRomSpline(pts, 6);

  // Gradient fill
  const grad = ctx.createLinearGradient(0, y0, 0, baseY);
  grad.addColorStop(0, theme.gradTop);
  grad.addColorStop(0.5, theme.gradMid);
  grad.addColorStop(1, theme.gradBot);

  ctx.beginPath();
  ctx.moveTo(smooth[0].x, baseY);
  for (const p of smooth) ctx.lineTo(p.x, p.y);
  ctx.lineTo(smooth[smooth.length - 1].x, baseY);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Glow line (thicker, slightly transparent)
  ctx.strokeStyle = theme.glow;
  ctx.lineWidth = 4;
  ctx.globalAlpha = 0.3;
  ctx.beginPath();
  for (let i = 0; i < smooth.length; i++) {
    if (i === 0) ctx.moveTo(smooth[i].x, smooth[i].y);
    else ctx.lineTo(smooth[i].x, smooth[i].y);
  }
  ctx.stroke();
  ctx.globalAlpha = 1.0;

  // Main line
  ctx.strokeStyle = theme.line;
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (let i = 0; i < smooth.length; i++) {
    if (i === 0) ctx.moveTo(smooth[i].x, smooth[i].y);
    else ctx.lineTo(smooth[i].x, smooth[i].y);
  }
  ctx.stroke();
}

function drawTFCurve(ctx, data, x0, w, y0, h, minDb, maxDb, theme) {
  const zeroY = dbToY(0, minDb, maxDb, y0, h);
  const pts = [];
  const step = Math.max(1, Math.floor(data.length / (w / 3)));
  for (let i = 0; i < data.length; i += step) {
    if (data[i] === null) continue;
    const t = i / data.length;
    const x = x0 + t * w;
    const y = dbToY(data[i], minDb, maxDb, y0, h);
    pts.push({ x, y: Math.max(y0, Math.min(y0 + h, y)) });
  }
  if (pts.length < 2) return;

  const smooth = catmullRomSpline(pts, 6);

  // Positive fill (above 0dB)
  const gradPos = ctx.createLinearGradient(0, y0, 0, zeroY);
  gradPos.addColorStop(0, theme.gradPos);
  gradPos.addColorStop(1, theme.gradZero);

  const gradNeg = ctx.createLinearGradient(0, zeroY, 0, y0 + h);
  gradNeg.addColorStop(0, theme.gradZero);
  gradNeg.addColorStop(1, theme.gradNeg);

  // Fill above zero
  ctx.save();
  ctx.beginPath();
  ctx.rect(x0, y0, w, zeroY - y0);
  ctx.clip();
  ctx.beginPath();
  ctx.moveTo(smooth[0].x, zeroY);
  for (const p of smooth) ctx.lineTo(p.x, p.y);
  ctx.lineTo(smooth[smooth.length - 1].x, zeroY);
  ctx.closePath();
  ctx.fillStyle = gradPos;
  ctx.fill();
  ctx.restore();

  // Fill below zero
  ctx.save();
  ctx.beginPath();
  ctx.rect(x0, zeroY, w, y0 + h - zeroY);
  ctx.clip();
  ctx.beginPath();
  ctx.moveTo(smooth[0].x, zeroY);
  for (const p of smooth) ctx.lineTo(p.x, p.y);
  ctx.lineTo(smooth[smooth.length - 1].x, zeroY);
  ctx.closePath();
  ctx.fillStyle = gradNeg;
  ctx.fill();
  ctx.restore();

  // Glow
  ctx.strokeStyle = theme.glow;
  ctx.lineWidth = 5;
  ctx.globalAlpha = 0.2;
  ctx.beginPath();
  for (let i = 0; i < smooth.length; i++) {
    if (i === 0) ctx.moveTo(smooth[i].x, smooth[i].y);
    else ctx.lineTo(smooth[i].x, smooth[i].y);
  }
  ctx.stroke();
  ctx.globalAlpha = 1.0;

  // Main line
  ctx.strokeStyle = theme.line;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  for (let i = 0; i < smooth.length; i++) {
    if (i === 0) ctx.moveTo(smooth[i].x, smooth[i].y);
    else ctx.lineTo(smooth[i].x, smooth[i].y);
  }
  ctx.stroke();
}

function drawMeter(ctx, x, y, barW, barH, peakDb, label, accentColor) {
  // Label
  ctx.fillStyle = accentColor;
  ctx.font = "bold 10px 'Inter', sans-serif";
  ctx.fillText(label, x, y - 5);

  // Bar bg with subtle rounded rect
  drawRoundedRect(ctx, x, y, barW, barH, 3);
  ctx.fillStyle = THEME.meter.bg;
  ctx.fill();

  // Gradient fill
  const t = Math.max(0, Math.min(1, (peakDb + 60) / 60));
  const filledW = Math.max(0, t * barW);
  if (filledW > 1) {
    ctx.save();
    drawRoundedRect(ctx, x, y, barW, barH, 3);
    ctx.clip();
    const grad = ctx.createLinearGradient(x, 0, x + barW, 0);
    grad.addColorStop(0, THEME.meter.green);
    grad.addColorStop(0.65, THEME.meter.yellow);
    grad.addColorStop(0.9, THEME.meter.red);
    ctx.fillStyle = grad;
    ctx.fillRect(x, y, filledW, barH);
    ctx.restore();
  }

  // Peak hold
  if (t > 0.02) {
    const peakX = x + t * barW;
    ctx.fillStyle = THEME.meter.peak;
    ctx.globalAlpha = 0.9;
    ctx.fillRect(peakX - 1, y, 2, barH);
    ctx.globalAlpha = 1.0;
  }

  // Readout
  ctx.fillStyle = peakDb > -3 ? THEME.meter.red : COLORS.white;
  ctx.font = "11px 'JetBrains Mono', monospace";
  const dbStr = peakDb <= -59 ? " --- " : `${peakDb.toFixed(1)}`;
  ctx.fillText(dbStr, x + barW + 8, y + barH - 2);
}

function drawGrid(ctx, x0, w, y0, h, dbValues, minDb, maxDb, freqs) {
  ctx.strokeStyle = COLORS.gridLine;
  ctx.lineWidth = 0.7;
  for (const db of dbValues) {
    const y = dbToY(db, minDb, maxDb, y0, h);
    ctx.beginPath();
    ctx.moveTo(x0, y);
    ctx.lineTo(x0 + w, y);
    ctx.stroke();
  }
  for (const freq of freqs) {
    const x = freqToX(freq, x0, w);
    ctx.beginPath();
    ctx.moveTo(x, y0);
    ctx.lineTo(x, y0 + h);
    ctx.stroke();
  }
}

function drawFreqLabels(ctx, x0, w, y, freqs) {
  ctx.textAlign = "center";
  ctx.font = "9px 'JetBrains Mono', monospace";
  const musical = { 50: "low", 100: "", 200: "bass", 500: "", 1000: "mids", 2000: "", 5000: "upper", 10000: "treble" };
  for (const f of freqs) {
    const x = freqToX(f, x0, w);
    ctx.fillStyle = COLORS.labelBright;
    const label = f >= 1000 ? `${f / 1000}k` : `${f}`;
    ctx.fillText(label, x, y);
    if (musical[f]) {
      ctx.fillStyle = COLORS.dim;
      ctx.font = "8px 'Inter', sans-serif";
      ctx.fillText(musical[f], x, y + 11);
      ctx.font = "9px 'JetBrains Mono', monospace";
    }
  }
  ctx.textAlign = "left";
}

function drawDbLabels(ctx, x, y0, h, dbValues, minDb, maxDb, highlight) {
  ctx.font = "9px 'JetBrains Mono', monospace";
  for (const db of dbValues) {
    const y = dbToY(db, minDb, maxDb, y0, h);
    ctx.fillStyle = db === highlight ? COLORS.labelBright : COLORS.label;
    const s = db > 0 ? `+${db}` : `${db}`;
    ctx.fillText(s, x, y + 3);
  }
}

function renderLive(ctx) {
  const srcChar = {
    rolloff: 14,
    peaks: [
      { f: 82, db: -6 }, { f: 165, db: -10 }, { f: 247, db: -15 },
      { f: 330, db: -12 }, { f: 440, db: -18 }, { f: 660, db: -22 },
      { f: 880, db: -28 }, { f: 1320, db: -32 },
    ]
  };
  const retChar = {
    rolloff: 11,
    peaks: [
      { f: 82, db: -8 }, { f: 165, db: -7 }, { f: 247, db: -16 },
      { f: 330, db: -9 }, { f: 500, db: -14 }, { f: 660, db: -19 },
      { f: 1000, db: -22 }, { f: 2500, db: -24 }, { f: 4000, db: -30 },
    ]
  };
  const specSrc = generateSpectrum(1.4, srcChar);
  const specRet = generateSpectrum(2.8, retChar);
  const tfData = generateTF(3.5);

  const meterH = 46;
  const specY = meterH + 1;
  const specH = 198;
  const tfY = specY + specH + 1;
  const tfH = H - tfY;
  const gml = 46;
  const gmr = 8;
  const gmt = 16;
  const gmb = 24;
  const gw = W - gml - gmr;

  // Background
  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(0, 0, W, H);

  // === METER BAR ===
  ctx.fillStyle = "#080c14";
  ctx.fillRect(0, 0, W, meterH);

  // Jack status dots
  const jacks = [
    { l: "IN", ok: true }, { l: "SEND", ok: true },
    { l: "TS", ok: true }, { l: "XLR", ok: false },
  ];
  let jx = 8;
  ctx.font = "8px 'Inter', sans-serif";
  for (const j of jacks) {
    ctx.beginPath();
    ctx.arc(jx + 4, 9, 3.5, 0, Math.PI * 2);
    ctx.fillStyle = j.ok ? "#1a6a3a" : "#1a2030";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(jx + 4, 9, 2, 0, Math.PI * 2);
    ctx.fillStyle = j.ok ? THEME.quality.good : "#2a3040";
    ctx.fill();
    ctx.fillStyle = j.ok ? COLORS.labelBright : COLORS.dim;
    ctx.fillText(j.l, jx + 12, 12);
    jx += j.l.length * 6 + 22;
  }

  // Monitor badge
  ctx.fillStyle = COLORS.dim;
  ctx.font = "8px monospace";
  ctx.fillText("SRC ◂ MON ▸ RET", 200, 12);

  drawMeter(ctx, 50, 22, 200, 14, -11.8, "SOURCE", THEME.source.line);
  drawMeter(ctx, 450, 22, 200, 14, -14.2, "RETURN", THEME.ret.line);

  // Separator
  const sepGrad = ctx.createLinearGradient(0, 0, W, 0);
  sepGrad.addColorStop(0, "transparent");
  sepGrad.addColorStop(0.2, COLORS.separator);
  sepGrad.addColorStop(0.8, COLORS.separator);
  sepGrad.addColorStop(1, "transparent");
  ctx.fillStyle = sepGrad;
  ctx.fillRect(0, meterH, W, 1);

  // === SPECTRUM ===
  const sgY = specY + gmt;
  const sgH = specH - gmt - gmb;

  drawGrid(ctx, gml, gw, sgY, sgH, [-20, -40, -60], -75, 0, [100, 500, 1000, 5000, 10000]);

  drawSmoothFilledCurve(ctx, specRet, gml, gw, sgY, sgH, -75, 0, THEME.ret, sgY + sgH);
  drawSmoothFilledCurve(ctx, specSrc, gml, gw, sgY, sgH, -75, 0, THEME.source, sgY + sgH);

  drawDbLabels(ctx, 4, sgY, sgH, [0, -20, -40, -60], -75, 0, 0);
  drawFreqLabels(ctx, gml, gw, sgY + sgH + 13, [100, 500, 1000, 5000, 10000]);

  // Legend
  ctx.fillStyle = THEME.source.line;
  ctx.font = "bold 9px sans-serif";
  ctx.fillText("●", gml + 2, specY + 11);
  ctx.fillStyle = COLORS.labelBright;
  ctx.font = "9px 'Inter', sans-serif";
  ctx.fillText("SOURCE", gml + 12, specY + 11);
  ctx.fillStyle = THEME.ret.line;
  ctx.font = "bold 9px sans-serif";
  ctx.fillText("●", gml + 68, specY + 11);
  ctx.fillStyle = COLORS.labelBright;
  ctx.font = "9px 'Inter', sans-serif";
  ctx.fillText("RETURN", gml + 78, specY + 11);

  // Separator
  ctx.fillStyle = sepGrad;
  ctx.fillRect(0, tfY - 1, W, 1);

  // === TRANSFER FUNCTION ===
  const tgY = tfY + gmt;
  const tgH = tfH - gmt - gmb;

  drawGrid(ctx, gml, gw, tgY, tgH, [-12, -6, 6, 12], -18, 18, [100, 500, 1000, 5000, 10000]);

  // Zero line — brighter
  const zeroY = dbToY(0, -18, 18, tgY, tgH);
  ctx.strokeStyle = "rgba(80, 120, 160, 0.4)";
  ctx.lineWidth = 1.2;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(gml, zeroY);
  ctx.lineTo(gml + gw, zeroY);
  ctx.stroke();
  ctx.setLineDash([]);

  drawTFCurve(ctx, tfData, gml, gw, tgY, tgH, -18, 18, THEME.tf);

  drawDbLabels(ctx, 4, tgY, tgH, [-12, -6, 0, 6, 12], -18, 18, 0);
  drawFreqLabels(ctx, gml, gw, tgY + tgH + 13, [100, 500, 1000, 5000, 10000]);

  // Legend
  ctx.fillStyle = THEME.tf.line;
  ctx.font = "bold 9px sans-serif";
  ctx.fillText("●", gml + 2, tfY + 11);
  ctx.fillStyle = COLORS.labelBright;
  ctx.font = "9px 'Inter', sans-serif";
  ctx.fillText("RIG CHANGE", gml + 12, tfY + 11);

  ctx.fillStyle = COLORS.dim;
  ctx.font = "8px 'Inter', sans-serif";
  ctx.textAlign = "right";
  ctx.fillText("▲ louder", gml + gw, tfY + 11);
  ctx.fillText("▼ quieter", gml + gw, tgY + tgH + 13);
  ctx.textAlign = "left";
}

function renderResult(ctx) {
  const tfData = generateTF(5.5);
  const headerH = 48;
  const insightW = 272;
  const tfW = W - insightW;
  const gml = 46;
  const gmr = 8;
  const gmt = 16;
  const gmb = 24;
  const gw = tfW - gml - gmr;

  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(0, 0, W, H);

  // Header
  ctx.fillStyle = "#080c14";
  ctx.fillRect(0, 0, W, headerH);

  // Quality pill
  drawRoundedRect(ctx, 10, 8, 72, 26, 6);
  ctx.fillStyle = THEME.quality.good;
  ctx.fill();
  ctx.fillStyle = "#000";
  ctx.font = "bold 13px 'Inter', sans-serif";
  ctx.fillText("GOOD", 21, 26);

  // Stats
  ctx.fillStyle = COLORS.white;
  ctx.font = "12px 'JetBrains Mono', monospace";
  ctx.fillText("γ² 0.94", 96, 26);
  ctx.fillStyle = COLORS.label;
  ctx.fillText("87% valid", 185, 26);

  // Provenance
  ctx.fillStyle = COLORS.dim;
  ctx.font = "9px 'JetBrains Mono', monospace";
  ctx.fillText("32 avg  ·  H1  ·  external  ·  cal: bench loopback", 10, 44);

  // Separator
  const sepGrad = ctx.createLinearGradient(0, 0, W, 0);
  sepGrad.addColorStop(0, "transparent");
  sepGrad.addColorStop(0.15, COLORS.separator);
  sepGrad.addColorStop(0.85, COLORS.separator);
  sepGrad.addColorStop(1, "transparent");
  ctx.fillStyle = sepGrad;
  ctx.fillRect(0, headerH, W, 1);

  // === TF RESULT ===
  const tgY = headerH + gmt;
  const tgH = H - headerH - gmt - gmb;

  drawGrid(ctx, gml, gw, tgY, tgH, [-12, -6, 6, 12], -18, 18, [100, 500, 1000, 5000, 10000]);

  const zeroY = dbToY(0, -18, 18, tgY, tgH);
  ctx.strokeStyle = "rgba(80, 120, 160, 0.4)";
  ctx.lineWidth = 1.2;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(gml, zeroY);
  ctx.lineTo(gml + gw, zeroY);
  ctx.stroke();
  ctx.setLineDash([]);

  drawTFCurve(ctx, tfData, gml, gw, tgY, tgH, -18, 18, THEME.tf);
  drawDbLabels(ctx, 4, tgY, tgH, [-12, -6, 0, 6, 12], -18, 18, 0);
  drawFreqLabels(ctx, gml, gw, tgY + tgH + 13, [100, 500, 1000, 5000, 10000]);

  // === INSIGHT PANEL ===
  const ipX = tfW;
  ctx.fillStyle = "#080c12";
  ctx.fillRect(ipX, headerH + 1, insightW, H - headerH);

  // Vert separator
  const vGrad = ctx.createLinearGradient(0, headerH, 0, H);
  vGrad.addColorStop(0, "transparent");
  vGrad.addColorStop(0.15, COLORS.separator);
  vGrad.addColorStop(0.85, COLORS.separator);
  vGrad.addColorStop(1, "transparent");
  ctx.fillStyle = vGrad;
  ctx.fillRect(ipX, headerH, 1, H - headerH);

  // Insight header
  let iy = headerH + 20;
  ctx.fillStyle = COLORS.labelBright;
  ctx.font = "bold 11px 'Inter', sans-serif";
  ctx.fillText("INSIGHTS", ipX + 14, iy);
  iy += 24;

  const insights = [
    { m: "M", title: "Bass boost: +4.2 dB", detail: "Peak at 140 Hz", c: THEME.insight.meas },
    { m: "M", title: "Mid scoop: −4.8 dB", detail: "Centered at 700 Hz", c: THEME.insight.meas },
    { m: "M", title: "Presence: +3.1 dB", detail: "Peak at 3.2 kHz", c: THEME.insight.meas },
    { m: "M", title: "HF rolloff: −6 dB/oct", detail: "Above 7 kHz", c: THEME.insight.meas },
    { m: "A", title: "Overdrive voicing", detail: "Bass boost + mid scoop pattern", c: THEME.insight.adv },
    { m: "A", title: "Check cable length", detail: "HF rolloff steeper than expected", c: THEME.insight.alert },
  ];

  for (const ins of insights) {
    // Tag pill
    drawRoundedRect(ctx, ipX + 12, iy - 10, 16, 14, 3);
    ctx.fillStyle = ins.c;
    ctx.globalAlpha = 0.2;
    ctx.fill();
    ctx.globalAlpha = 1.0;
    ctx.fillStyle = ins.c;
    ctx.font = "bold 9px monospace";
    ctx.fillText(ins.m, ipX + 15, iy);

    // Title
    ctx.fillStyle = ins.c === THEME.insight.alert ? THEME.insight.alert : COLORS.white;
    ctx.font = "10px 'Inter', sans-serif";
    ctx.fillText(ins.title, ipX + 34, iy);
    iy += 15;

    // Detail
    if (ins.detail) {
      ctx.fillStyle = THEME.insight.detail;
      ctx.font = "9px 'Inter', sans-serif";
      ctx.fillText(ins.detail, ipX + 34, iy);
      iy += 15;
    }
    iy += 8;
  }

  // Footer
  ctx.fillStyle = COLORS.dim;
  ctx.font = "8px 'Inter', sans-serif";
  ctx.fillText("press x to return  ·  s to save  ·  b for CSV", ipX + 14, H - 12);
}

export default function App() {
  const canvasRef = useRef(null);
  const [view, setView] = useState("live");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, W, H);
    if (view === "live") renderLive(ctx);
    else renderResult(ctx);
  }, [view]);

  return (
    <div className="flex flex-col items-center bg-black min-h-screen p-4">
      <div className="flex items-center gap-3 mb-3">
        <h1 className="text-lg font-semibold text-gray-300 tracking-wide">
          Guitar Rig Analyzer
        </h1>
        <span className="text-xs text-gray-600">800×480 concept</span>
      </div>
      <div className="flex gap-2 mb-3">
        {["live", "result"].map(v => (
          <button key={v} onClick={() => setView(v)}
            className={`px-4 py-1.5 rounded-md text-xs font-semibold uppercase tracking-wider transition-all ${
              view === v
                ? v === "live" ? "bg-blue-600/80 text-white shadow-lg shadow-blue-900/40"
                  : "bg-amber-600/80 text-white shadow-lg shadow-amber-900/40"
                : "bg-gray-900 text-gray-500 hover:bg-gray-800 hover:text-gray-400"
            }`}>
            {v === "live" ? "⚡ Live" : "📊 Result"}
          </button>
        ))}
      </div>
      <div className="rounded-xl overflow-hidden shadow-2xl shadow-black/60 border border-gray-800/50">
        <canvas ref={canvasRef} width={W} height={H}
          style={{ display: "block", width: W, height: H }} />
      </div>
      <div className="mt-3 max-w-xl grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-gray-600">
        <p>● Catmull-Rom spline smoothing</p>
        <p>● Gradient fills with glow lines</p>
        <p>● Musical frequency labels</p>
        <p>● Gradient meters with peak hold</p>
        <p>● M/A insight pills with color coding</p>
        <p>● Fade separators and rounded badges</p>
      </div>
    </div>
  );
}

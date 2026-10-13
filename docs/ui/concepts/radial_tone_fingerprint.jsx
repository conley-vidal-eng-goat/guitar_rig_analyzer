import { useRef, useEffect, useState, useCallback } from "react";

const W = 800;
const H = 480;
const CX = W / 2;
const CY = H / 2;
const BASE_R = 88;
const MAX_OUT = 130;
const MAX_IN = 70;
const NUM_BANDS = 48;

function generateTFData(seed, time) {
  const data = [];
  for (let i = 0; i < NUM_BANDS; i++) {
    const t = i / (NUM_BANDS - 1);
    const freq = 20 * Math.pow(20000 / 20, t);
    let db = 0;

    // Bass boost ~140Hz
    const bD = Math.abs(Math.log2(freq / 140));
    if (bD < 1.2) db += 5.5 * Math.pow(1 - bD / 1.2, 1.5);

    // Mid scoop ~700Hz
    const mD = Math.abs(Math.log2(freq / 700));
    if (mD < 1) db -= 6.5 * Math.pow(1 - mD, 1.3);

    // Presence peak ~3kHz
    const pD = Math.abs(Math.log2(freq / 3200));
    if (pD < 0.6) db += 4 * Math.pow(1 - pD / 0.6, 1.2);

    // HF rolloff
    if (freq > 7000) db -= 9 * Math.pow(Math.log10(freq / 7000), 1.5);

    // Gentle animation
    db += Math.sin(i * 2.1 + time * 0.8 + seed) * 0.7;
    db += Math.sin(i * 0.7 + time * 0.5) * 0.5;

    // Absolute energy (for thickness) — simulate return level
    let energy = 0.3;
    if (freq > 60 && freq < 12000) {
      energy = 0.5 + 0.4 * Math.exp(-Math.pow(Math.log2(freq / 500), 2) / 3);
    }
    energy += Math.sin(i * 1.3 + time * 0.6) * 0.06;
    energy = Math.max(0.1, Math.min(1.0, energy));

    data.push({ db, energy, freq });
  }
  return data;
}

function bandToAngles(bandIndex) {
  // Band 0 = 6 o'clock (bottom), band N-1 = 12 o'clock (top)
  // Right side: clockwise from bottom to top
  // Left side: counter-clockwise from bottom to top (mirror)
  const t = bandIndex / (NUM_BANDS - 1);
  const halfArc = Math.PI; // 180 degrees each side
  const bottomAngle = Math.PI / 2; // 90° = 6 o'clock in screen coords

  const rightAngle = bottomAngle - t * halfArc; // goes from π/2 to -π/2
  const leftAngle = bottomAngle + t * halfArc;  // goes from π/2 to 3π/2

  return { right: rightAngle, left: leftAngle };
}

function dbToOutward(db) {
  // Positive db = outward, negative = inward
  if (db >= 0) return (db / 18) * MAX_OUT;
  else return (db / 18) * MAX_IN;
}

function getBoostColor(db, dist, maxDist) {
  // Outward: blue near circle → green far
  const t = Math.min(1, dist / maxDist);
  const r = Math.round(20 + t * 30);
  const g = Math.round(100 + t * 155);
  const b = Math.round(220 - t * 100);
  return { r, g, b };
}

function getCutColor(db, dist, maxDist) {
  // Inward: yellow near circle → orange → red deep
  const t = Math.min(1, dist / maxDist);
  const r = Math.round(220 + t * 35);
  const g = Math.round(180 - t * 140);
  const b = Math.round(30 - t * 20);
  return { r, g, b };
}

function render(ctx, time, data) {
  // Clear
  ctx.fillStyle = "#030508";
  ctx.fillRect(0, 0, W, H);

  // Subtle radial background gradient
  const bgGrad = ctx.createRadialGradient(CX, CY, 0, CX, CY, 320);
  bgGrad.addColorStop(0, "rgba(8, 14, 24, 1)");
  bgGrad.addColorStop(0.5, "rgba(4, 8, 16, 1)");
  bgGrad.addColorStop(1, "rgba(2, 4, 8, 1)");
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, W, H);

  // Very subtle guide rings (outward)
  for (const r of [BASE_R + 40, BASE_R + 80, BASE_R + 120]) {
    ctx.strokeStyle = "rgba(30, 50, 70, 0.12)";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.arc(CX, CY, r, 0, Math.PI * 2);
    ctx.stroke();
  }
  // Guide rings (inward)
  for (const r of [BASE_R - 18, BASE_R - 36, BASE_R - 54]) {
    if (r > 5) {
      ctx.strokeStyle = "rgba(80, 50, 30, 0.1)";
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.arc(CX, CY, r, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  // === CENTER CIRCLE — draw FIRST so inward segments render on top ===
  // Dark fill — slightly lighter than pure black so inward cuts are visible
  const innerGrad = ctx.createRadialGradient(CX, CY, 0, CX, CY, BASE_R);
  innerGrad.addColorStop(0, "rgba(12, 18, 28, 1)");
  innerGrad.addColorStop(0.6, "rgba(8, 12, 22, 1)");
  innerGrad.addColorStop(1, "rgba(4, 6, 14, 1)");
  ctx.fillStyle = innerGrad;
  ctx.beginPath();
  ctx.arc(CX, CY, BASE_R, 0, Math.PI * 2);
  ctx.fill();

  // Center label (under segments)
  const pulse = 0.4 + 0.3 * Math.sin(time * 1.2) + 0.15 * Math.sin(time * 2.7);
  ctx.fillStyle = `rgba(100, 130, 160, ${0.15 + pulse * 0.08})`;
  ctx.font = "9px 'Inter', sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("INPUT", CX, CY - 4);
  ctx.fillText("BASELINE", CX, CY + 8);
  ctx.textAlign = "left";

  // Angular spread per band
  const bandSpread = (Math.PI / NUM_BANDS) * 0.75;

  // Draw spectral segments
  for (let i = 0; i < NUM_BANDS; i++) {
    const { db, energy, freq } = data[i];
    const { right: rAngle, left: lAngle } = bandToAngles(i);
    const extension = dbToOutward(db);
    const isBoost = db >= 0;

    // Thickness from energy (min 1.5px, max 6px)
    const thickness = 1.5 + energy * 4.5;

    // For each side (right and left)
    for (const angle of [rAngle, lAngle]) {
      const cosA = Math.cos(angle);
      const sinA = -Math.sin(angle); // screen Y is inverted

      if (isBoost) {
        // Extend outward from circle
        const startR = BASE_R + 2;
        const endR = BASE_R + extension;
        const dist = extension;

        if (dist < 1) continue;

        // Draw multiple layers for glow
        for (let layer = 2; layer >= 0; layer--) {
          const spread = layer * 2.5;
          const alpha = layer === 0 ? 0.85 : layer === 1 ? 0.25 : 0.08;
          const w = thickness + spread * 2;

          // Gradient along the segment
          const sx = CX + cosA * startR;
          const sy = CY + sinA * startR;
          const ex = CX + cosA * endR;
          const ey = CY + sinA * endR;

          const grad = ctx.createLinearGradient(sx, sy, ex, ey);
          const cNear = getBoostColor(db, 0, MAX_OUT);
          const cFar = getBoostColor(db, dist, MAX_OUT);
          grad.addColorStop(0, `rgba(${cNear.r},${cNear.g},${cNear.b},${alpha * 0.6})`);
          grad.addColorStop(0.5, `rgba(${Math.round((cNear.r+cFar.r)/2)},${Math.round((cNear.g+cFar.g)/2)},${Math.round((cNear.b+cFar.b)/2)},${alpha})`);
          grad.addColorStop(1, `rgba(${cFar.r},${cFar.g},${cFar.b},${alpha * 0.4})`);

          ctx.strokeStyle = grad;
          ctx.lineWidth = w;
          ctx.lineCap = "round";
          ctx.beginPath();
          ctx.moveTo(sx, sy);
          ctx.lineTo(ex, ey);
          ctx.stroke();
        }
      } else {
        // Extend inward toward center
        const startR = BASE_R - 2;
        const endR = Math.max(8, BASE_R + extension); // extension is negative
        const dist = startR - endR;

        if (dist < 1) continue;

        for (let layer = 2; layer >= 0; layer--) {
          const spread = layer * 2.5;
          const alpha = layer === 0 ? 0.9 : layer === 1 ? 0.35 : 0.12;
          const w = thickness + spread * 2;

          const sx = CX + cosA * startR;
          const sy = CY + sinA * startR;
          const ex = CX + cosA * endR;
          const ey = CY + sinA * endR;

          const grad = ctx.createLinearGradient(sx, sy, ex, ey);
          const cNear = getCutColor(db, 0, MAX_IN);
          const cFar = getCutColor(db, dist, MAX_IN);
          grad.addColorStop(0, `rgba(${cNear.r},${cNear.g},${cNear.b},${alpha * 0.7})`);
          grad.addColorStop(0.4, `rgba(${Math.round((cNear.r+cFar.r)/2)},${Math.round((cNear.g+cFar.g)/2)},${Math.round((cNear.b+cFar.b)/2)},${alpha})`);
          grad.addColorStop(1, `rgba(${cFar.r},${cFar.g},${cFar.b},${alpha * 0.85})`);

          ctx.strokeStyle = grad;
          ctx.lineWidth = w;
          ctx.lineCap = "round";
          ctx.beginPath();
          ctx.moveTo(sx, sy);
          ctx.lineTo(ex, ey);
          ctx.stroke();
        }
      }
    }
  }

  // === PULSING BORDER — drawn on top of segments ===
  const pulse2 = 0.4 + 0.3 * Math.sin(time * 1.2) + 0.15 * Math.sin(time * 2.7);

  // Outer glow layers
  for (let g = 3; g >= 0; g--) {
    const r = BASE_R + g * 2.5;
    const alpha = pulse2 * (0.04 + (3 - g) * 0.06);
    ctx.strokeStyle = `rgba(180, 210, 240, ${alpha})`;
    ctx.lineWidth = 3 + g * 2;
    ctx.beginPath();
    ctx.arc(CX, CY, r, 0, Math.PI * 2);
    ctx.stroke();
  }

  // Main border line
  ctx.strokeStyle = `rgba(200, 220, 240, ${0.3 + pulse2 * 0.4})`;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(CX, CY, BASE_R, 0, Math.PI * 2);
  ctx.stroke();

  // Frequency labels around the outside
  const labelR = BASE_R + MAX_OUT + 18;
  const freqLabels = [
    { band: 0, label: "SUB", sub: "20 Hz" },
    { band: Math.round(NUM_BANDS * 0.18), label: "BASS", sub: "100" },
    { band: Math.round(NUM_BANDS * 0.38), label: "MID", sub: "500" },
    { band: Math.round(NUM_BANDS * 0.58), label: "UPPER", sub: "2k" },
    { band: Math.round(NUM_BANDS * 0.78), label: "PRES", sub: "5k" },
    { band: NUM_BANDS - 1, label: "AIR", sub: "20k" },
  ];

  ctx.font = "8px 'Inter', sans-serif";
  for (const fl of freqLabels) {
    const { right: rA, left: lA } = bandToAngles(fl.band);
    for (const a of [rA, lA]) {
      const cosA = Math.cos(a);
      const sinA = -Math.sin(a);
      const lx = CX + cosA * labelR;
      const ly = CY + sinA * labelR;

      ctx.fillStyle = "rgba(100, 140, 170, 0.5)";
      ctx.textAlign = "center";
      ctx.font = "bold 8px 'Inter', sans-serif";
      ctx.fillText(fl.label, lx, ly - 2);
      ctx.fillStyle = "rgba(70, 100, 130, 0.4)";
      ctx.font = "7px 'JetBrains Mono', monospace";
      ctx.fillText(fl.sub, lx, ly + 8);
    }
  }

  // Legend
  ctx.textAlign = "left";
  ctx.font = "9px 'Inter', sans-serif";

  // Boost legend (top-right area)
  const lgx = W - 140;
  let lgy = 20;
  ctx.fillStyle = "rgba(80, 180, 220, 0.6)";
  ctx.fillText("▸ outward = boost", lgx, lgy);
  lgy += 14;

  // Color swatch
  const swGrad = ctx.createLinearGradient(lgx, 0, lgx + 60, 0);
  swGrad.addColorStop(0, "rgba(40, 120, 220, 0.7)");
  swGrad.addColorStop(1, "rgba(60, 220, 140, 0.7)");
  ctx.fillStyle = swGrad;
  ctx.fillRect(lgx, lgy, 60, 4);
  lgy += 14;

  ctx.fillStyle = "rgba(220, 150, 50, 0.6)";
  ctx.fillText("◂ inward = cut", lgx, lgy);
  lgy += 14;

  const swGrad2 = ctx.createLinearGradient(lgx, 0, lgx + 60, 0);
  swGrad2.addColorStop(0, "rgba(220, 180, 40, 0.7)");
  swGrad2.addColorStop(1, "rgba(230, 60, 30, 0.7)");
  ctx.fillStyle = swGrad2;
  ctx.fillRect(lgx, lgy, 60, 4);

  // Bottom info
  ctx.fillStyle = "rgba(80, 110, 140, 0.35)";
  ctx.font = "8px 'Inter', sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("RADIAL TONE FINGERPRINT", CX, H - 18);
  ctx.fillText("line thickness = signal energy  ·  distance = spectral difference", CX, H - 8);
  ctx.textAlign = "left";
}

export default function App() {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const timeRef = useRef(0);
  const [preset, setPreset] = useState("overdrive");

  const presets = {
    overdrive: { seed: 3.5, label: "Overdrive Pedal", desc: "Bass boost, mid scoop, presence peak, HF rolloff" },
    clean: { seed: 7.2, label: "Clean Boost", desc: "Slight fullness across the range, gentle treble lift" },
    wah: { seed: 11.0, label: "Wah (mid position)", desc: "Strong mid peak, everything else attenuated" },
    cable: { seed: 5.8, label: "Long Cable", desc: "Progressive HF rolloff from cable capacitance" },
  };

  const generatePresetData = useCallback((key, time) => {
    const base = generateTFData(presets[key].seed, time);
    if (key === "clean") {
      return base.map((b, i) => {
        const t = i / NUM_BANDS;
        const freq = 20 * Math.pow(20000/20, t);
        let db = 1.5 + Math.sin(i*0.8+time*0.5)*0.4;
        if (freq > 5000) db += 2 * Math.log10(freq/5000);
        if (freq > 14000) db -= 3;
        return { ...b, db: db + Math.sin(i*2.1+time*0.8)*0.5 };
      });
    }
    if (key === "wah") {
      return base.map((b, i) => {
        const t = i / NUM_BANDS;
        const freq = 20 * Math.pow(20000/20, t);
        let db = -8;
        const wahF = 1200 + Math.sin(time * 0.3) * 200;
        const d = Math.abs(Math.log2(freq / wahF));
        if (d < 0.8) db = 10 * Math.pow(1 - d/0.8, 2);
        return { ...b, db: db + Math.sin(i*1.7+time*0.7)*0.4, energy: Math.max(0.15, b.energy * (db > -2 ? 1 : 0.4)) };
      });
    }
    if (key === "cable") {
      return base.map((b, i) => {
        const t = i / NUM_BANDS;
        const freq = 20 * Math.pow(20000/20, t);
        let db = 0;
        // Cable capacitance: progressive HF rolloff starting around 1kHz,
        // getting severe above 4kHz. A 20ft cable can lose 6-10dB at 10kHz.
        if (freq > 800) db = -16 * Math.pow(Math.log10(freq/800), 1.6);
        db = Math.max(-16, db);
        db += Math.sin(i*1.5+time*0.6)*0.3;
        // Keep energy/thickness substantial even for cut frequencies —
        // the cable is still passing signal, just attenuated.
        // Thickness represents that the frequency EXISTS but is reduced.
        const energy = Math.max(0.3, 0.7 - Math.max(0, (freq-2000)/20000) * 0.5);
        return { ...b, db, energy };
      });
    }
    return base;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const loop = () => {
      timeRef.current += 0.03;
      const data = generatePresetData(preset, timeRef.current);
      render(ctx, timeRef.current, data);
      animRef.current = requestAnimationFrame(loop);
    };
    animRef.current = requestAnimationFrame(loop);
    return () => { if (animRef.current) cancelAnimationFrame(animRef.current); };
  }, [preset, generatePresetData]);

  return (
    <div className="flex flex-col items-center bg-black min-h-screen p-4">
      <h1 className="text-lg font-semibold text-gray-300 tracking-wide mb-1">
        Radial Tone Fingerprint
      </h1>
      <p className="text-xs text-gray-600 mb-3">Interactive concept — 800×480</p>

      <div className="flex gap-2 mb-3 flex-wrap justify-center">
        {Object.entries(presets).map(([key, p]) => (
          <button key={key} onClick={() => setPreset(key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              preset === key
                ? "bg-gray-700 text-white shadow-lg"
                : "bg-gray-900 text-gray-500 hover:bg-gray-800 hover:text-gray-400"
            }`}>
            {p.label}
          </button>
        ))}
      </div>

      <div className="rounded-xl overflow-hidden shadow-2xl shadow-black/80 border border-gray-800/30">
        <canvas ref={canvasRef} width={W} height={H}
          style={{ display: "block", width: W, height: H }} />
      </div>

      <div className="mt-3 max-w-lg text-center">
        <p className="text-sm text-gray-400 font-medium">{presets[preset].label}</p>
        <p className="text-xs text-gray-600 mt-1">{presets[preset].desc}</p>
      </div>

      <div className="mt-4 max-w-xl text-xs text-gray-700 space-y-1 text-center">
        <p>Center circle = input baseline (zero reference) · Pulsing border = live signal</p>
        <p>Outward (blue→green) = boost · Inward (yellow→red) = cut · Thickness = energy</p>
        <p>Low freq at bottom · High freq at top · Mirrored left-right symmetry</p>
      </div>
    </div>
  );
}

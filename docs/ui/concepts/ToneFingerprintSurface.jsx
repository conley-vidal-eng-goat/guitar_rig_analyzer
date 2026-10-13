import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";

/**
 * ToneFingerprintSurface.jsx — V2
 *
 * Replaces the individual bar columns with a single continuous deforming
 * ring surface. The surface rises for boosts (right side, warm colors)
 * and drops for cuts (left side, cold colors).
 *
 * Visual style:
 *   - One continuous mesh (annular ring geometry)
 *   - Height displacement from TF data
 *   - Contour-banded color: stepped color transitions suggest topographic
 *     lines without needing actual line geometry
 *   - Subtle edge glow via emissive color, not post-processing
 *   - Depth fading on the inner edge for visual weight
 *
 * Pi 5 performance:
 *   - Single mesh, single material
 *   - MeshBasicMaterial with vertex colors (no lighting cost)
 *   - No per-frame normal recomputation
 *   - Ring buffer history not needed (this is instantaneous, not waterfall)
 *   - ~3,600 vertices for the ring mesh
 */

const W = 720;
const H = 1280;

const NUM_BANDS = 64;
const RING_INNER = 1.8;
const RING_OUTER = 3.4;
const RING_SEGMENTS = 6; // radial subdivisions for surface width
const MAX_DISPLACEMENT = 3.8;
const MAX_DB = 18;
const CAM_DIST = 10.5;
const DATA_HZ = 10.8;
const DATA_PERIOD = 1 / DATA_HZ;

// Split arcs
const LEFT_START = Math.PI * 0.6;
const LEFT_END = Math.PI * 1.4;
const RIGHT_START = -Math.PI * 0.4;
const RIGHT_END = Math.PI * 0.4;

// Contour band count — how many discrete color steps
const CONTOUR_STEPS = 8;

const BG = new THREE.Color(0x04070b);

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function lerp(a, b, t) { return a + (b - a) * t; }
function smoothstep(edge0, edge1, x) {
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

function logFreqAt(i, n) {
  const t = n <= 1 ? 0 : i / (n - 1);
  return 20 * Math.pow(20000 / 20, t);
}

function formatFreq(f) {
  if (f >= 10000) return (f / 1000).toFixed(1) + " kHz";
  if (f >= 1000) return (f / 1000).toFixed(2) + " kHz";
  return Math.round(f) + " Hz";
}

// Cold palette for missing/cut (below ring)
function coldContourColor(magnitude, out) {
  const t = clamp(magnitude / MAX_DB, 0, 1);
  // Quantize to contour bands
  const band = Math.floor(t * CONTOUR_STEPS) / CONTOUR_STEPS;
  // Deep blue → cyan → ice white
  if (band < 0.3) {
    out.setRGB(0.06 + band * 0.3, 0.12 + band * 0.8, 0.35 + band * 1.2);
  } else if (band < 0.65) {
    const s = (band - 0.3) / 0.35;
    out.setRGB(0.15 + s * 0.15, 0.36 + s * 0.45, 0.71 + s * 0.2);
  } else {
    const s = (band - 0.65) / 0.35;
    out.setRGB(0.3 + s * 0.5, 0.81 + s * 0.15, 0.91 + s * 0.09);
  }
  return out;
}

// Warm palette for augmented/boost (above ring)
function warmContourColor(magnitude, out) {
  const t = clamp(magnitude / MAX_DB, 0, 1);
  const band = Math.floor(t * CONTOUR_STEPS) / CONTOUR_STEPS;
  // Dark amber → orange → gold → bright yellow-white
  if (band < 0.3) {
    out.setRGB(0.35 + band * 1.2, 0.12 + band * 0.5, 0.02 + band * 0.1);
  } else if (band < 0.65) {
    const s = (band - 0.3) / 0.35;
    out.setRGB(0.71 + s * 0.2, 0.27 + s * 0.35, 0.05 + s * 0.08);
  } else {
    const s = (band - 0.65) / 0.35;
    out.setRGB(0.91 + s * 0.09, 0.62 + s * 0.3, 0.13 + s * 0.55);
  }
  return out;
}

// Baseline ring color (near zero displacement)
function baselineColor(out) {
  out.setRGB(0.08, 0.1, 0.16);
  return out;
}

function makeDemoFrame(t) {
  const frame = [];
  for (let i = 0; i < NUM_BANDS; i++) {
    const freq = logFreqAt(i, NUM_BANDS);
    let db = 0;
    const bD = Math.abs(Math.log2(freq / 140));
    if (bD < 1.1) db += 4.6 * Math.pow(1 - bD / 1.1, 1.5);
    const mD = Math.abs(Math.log2(freq / 900));
    if (mD < 0.9) db -= 5.8 * Math.pow(1 - mD / 0.9, 1.4);
    const uD = Math.abs(Math.log2(freq / 3200));
    if (uD < 0.55) db += 4.0 * Math.pow(1 - uD / 0.55, 1.3);
    if (freq > 7000) db -= 8 * Math.pow(Math.log10(freq / 7000), 1.5);
    db += Math.sin(i * 0.7 + t * 0.8) * 0.55;
    db += Math.sin(i * 1.9 + t * 0.45) * 0.35;
    let energy = 0.45 + 0.4 * Math.exp(-Math.pow(Math.log2(freq / 700), 2) / 4);
    energy += Math.sin(i * 1.37 + t * 0.65) * 0.05;
    frame.push({ freq, db: clamp(db, -MAX_DB, MAX_DB), energy: clamp(energy, 0.15, 1) });
  }
  return frame;
}

function normalizeFrame(frame) {
  const out = new Array(NUM_BANDS);
  for (let i = 0; i < NUM_BANDS; i++) {
    const item = frame?.[i];
    out[i] = {
      freq: item?.freq ?? logFreqAt(i, NUM_BANDS),
      db: clamp(item?.db ?? 0, -MAX_DB, MAX_DB),
      energy: clamp(item?.energy ?? 0.4, 0.15, 1),
    };
  }
  return out;
}

// Build the ring mesh geometry
// Vertices arranged in rings: for each angular position, RING_SEGMENTS+1 radial vertices
function buildRingGeometry(angularPositions) {
  const nAngular = angularPositions.length;
  const nRadial = RING_SEGMENTS + 1;
  const vertexCount = nAngular * nRadial;
  const positions = new Float32Array(vertexCount * 3);
  const colors = new Float32Array(vertexCount * 3);
  const indices = [];

  // Initialize flat ring
  for (let a = 0; a < nAngular; a++) {
    const angle = angularPositions[a];
    for (let r = 0; r < nRadial; r++) {
      const radius = RING_INNER + (r / RING_SEGMENTS) * (RING_OUTER - RING_INNER);
      const vi = a * nRadial + r;
      positions[vi * 3] = Math.cos(angle) * radius;
      positions[vi * 3 + 1] = 0;
      positions[vi * 3 + 2] = -Math.sin(angle) * radius;
      colors[vi * 3] = 0.08;
      colors[vi * 3 + 1] = 0.1;
      colors[vi * 3 + 2] = 0.16;
    }
  }

  // Build triangle indices
  for (let a = 0; a < nAngular - 1; a++) {
    for (let r = 0; r < RING_SEGMENTS; r++) {
      const tl = a * nRadial + r;
      const tr = a * nRadial + r + 1;
      const bl = (a + 1) * nRadial + r;
      const br = (a + 1) * nRadial + r + 1;
      indices.push(tl, bl, tr);
      indices.push(tr, bl, br);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geo.setIndex(indices);
  return geo;
}

export default function App() {
  const mountRef = useRef(null);
  const overlayRef = useRef(null);
  const rendRef = useRef(null);
  const animRef = useRef(null);
  const latestRef = useRef(normalizeFrame(makeDemoFrame(0)));
  const dispRef = useRef(normalizeFrame(makeDemoFrame(0)));
  const rotRef = useRef({ x: -0.5, y: 0, tx: -0.5, ty: 0 });
  const ptrRef = useRef({ dn: false, x: 0, y: 0 });
  const infoRef = useRef({ side: "boost", freq: "440 Hz", db: "+0.0 dB" });
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(false);
  useEffect(() => { pausedRef.current = paused; }, [paused]);

  useEffect(() => {
    const el = mountRef.current;
    const ov = overlayRef.current;
    if (!el || !ov) return;
    const ctx = ov.getContext("2d");

    const scene = new THREE.Scene();
    scene.background = BG;
    const cam = new THREE.PerspectiveCamera(38, W / H, 0.1, 100);
    const ren = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    ren.setPixelRatio(1);
    ren.setSize(W, H);
    el.appendChild(ren.domElement);
    rendRef.current = ren;

    // Minimal lighting — MeshBasicMaterial ignores it, but ambient helps
    // if we ever switch to Lambert for subtle shading
    scene.add(new THREE.AmbientLight(0xffffff, 0.5));

    // === PULSING BASELINE RING ===
    const ringGeo = new THREE.TorusGeometry(
      (RING_INNER + RING_OUTER) / 2, 0.02, 8, 160
    );
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x9fb3c8, transparent: true, opacity: 0.6,
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 2;
    scene.add(ring);

    const ringGlowGeo = new THREE.TorusGeometry(
      (RING_INNER + RING_OUTER) / 2, 0.06, 8, 128
    );
    const ringGlowMat = new THREE.MeshBasicMaterial({
      color: 0x38506b, transparent: true, opacity: 0.15, depthWrite: false,
    });
    const ringGlow = new THREE.Mesh(ringGlowGeo, ringGlowMat);
    ringGlow.rotation.x = Math.PI / 2;
    scene.add(ringGlow);

    // === DIVIDER ===
    const divGeo = new THREE.CylinderGeometry(0.012, 0.012, (RING_OUTER - RING_INNER) * 2.5, 6);
    const divMat = new THREE.MeshBasicMaterial({ color: 0x41556f, transparent: true, opacity: 0.3 });
    const divider = new THREE.Mesh(divGeo, divMat);
    divider.rotation.z = Math.PI / 2;
    divider.position.y = 0.01;
    scene.add(divider);

    // === BUILD ANGULAR POSITIONS ===
    // Left side: missing (goes from LEFT_START to LEFT_END)
    // Right side: augmented (goes from RIGHT_START to RIGHT_END)
    const leftAngles = [];
    const rightAngles = [];
    for (let i = 0; i < NUM_BANDS; i++) {
      const t = NUM_BANDS <= 1 ? 0 : i / (NUM_BANDS - 1);
      leftAngles.push(lerp(LEFT_START, LEFT_END, t));
      rightAngles.push(lerp(RIGHT_START, RIGHT_END, t));
    }

    // === SURFACE MESHES ===
    const leftGeo = buildRingGeometry(leftAngles);
    const rightGeo = buildRingGeometry(rightAngles);

    const surfaceMat = new THREE.MeshBasicMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
    });

    const leftMesh = new THREE.Mesh(leftGeo, surfaceMat);
    const rightMesh = new THREE.Mesh(rightGeo, surfaceMat.clone());
    scene.add(leftMesh);
    scene.add(rightMesh);

    // === CYAN REFERENCE ===
    const refGeo = new THREE.CylinderGeometry(0.03, 0.03, MAX_DISPLACEMENT * 0.15, 6);
    const refMat = new THREE.MeshBasicMaterial({ color: 0x00ddff, transparent: true, opacity: 0.75 });
    const refLine = new THREE.Mesh(refGeo, refMat);
    scene.add(refLine);
    const refDotGeo = new THREE.SphereGeometry(0.06, 10, 10);
    const refDotMat = new THREE.MeshBasicMaterial({ color: 0x00ffee });
    const refDot = new THREE.Mesh(refDotGeo, refDotMat);
    scene.add(refDot);

    const tc = new THREE.Color();
    const nRadial = RING_SEGMENTS + 1;

    function updateSurface(geo, angles, data, side) {
      const pos = geo.attributes.position;
      const col = geo.attributes.color;

      for (let a = 0; a < angles.length; a++) {
        const angle = angles[a];
        const item = data[a];
        const magnitude = Math.abs(item.db);
        const isActive = side === "missing" ? item.db < 0 : item.db > 0;
        const rawHeight = isActive ? (magnitude / MAX_DB) * MAX_DISPLACEMENT : 0;

        for (let r = 0; r < nRadial; r++) {
          const vi = a * nRadial + r;
          const radialT = r / RING_SEGMENTS; // 0=inner, 1=outer

          // Height profile: peaks at center of ring width, tapers at edges
          // This creates a rounded cross-section instead of a flat slab
          const crossProfile = Math.sin(radialT * Math.PI);
          const height = rawHeight * crossProfile * item.energy;

          // Direction: missing drops below, augmented rises above
          const y = side === "missing" ? -height : height;

          const radius = RING_INNER + radialT * (RING_OUTER - RING_INNER);
          pos.setXYZ(vi,
            Math.cos(angle) * radius,
            y,
            -Math.sin(angle) * radius
          );

          // Color: contour-banded based on magnitude
          if (!isActive || magnitude < 0.5) {
            baselineColor(tc);
            // Slight edge tint even when inactive
            if (side === "missing") { tc.r += 0.02; tc.g += 0.04; tc.b += 0.08; }
            else { tc.r += 0.08; tc.g += 0.04; tc.b += 0.01; }
          } else if (side === "missing") {
            coldContourColor(magnitude, tc);
            // Darken inner/outer edges for depth
            const edgeFade = 0.6 + 0.4 * crossProfile;
            tc.multiplyScalar(edgeFade);
          } else {
            warmContourColor(magnitude, tc);
            const edgeFade = 0.6 + 0.4 * crossProfile;
            tc.multiplyScalar(edgeFade);
          }

          col.setXYZ(vi, tc.r, tc.g, tc.b);
        }
      }

      pos.needsUpdate = true;
      col.needsUpdate = true;
    }

    function updateReference() {
      const cx = cam.position.x, cz = cam.position.z;
      const len = Math.sqrt(cx * cx + cz * cz);
      if (len < 0.01) return;
      const camAngle = Math.atan2(-cz, cx);

      // Determine which side
      const rightDist = Math.abs(THREE.MathUtils.euclideanModulo(camAngle - 0, Math.PI * 2));
      const isRight = rightDist < Math.PI / 2 || rightDist > Math.PI * 1.5;
      const side = isRight ? "boost" : "missing";
      const angles = isRight ? rightAngles : leftAngles;

      let bestIdx = 0, bestDelta = Infinity;
      for (let i = 0; i < angles.length; i++) {
        const d = Math.abs(Math.atan2(Math.sin(camAngle - angles[i]), Math.cos(camAngle - angles[i])));
        if (d < bestDelta) { bestDelta = d; bestIdx = i; }
      }

      const a = angles[bestIdx];
      const midR = (RING_INNER + RING_OUTER) / 2;
      const rx = Math.cos(a) * midR;
      const rz = -Math.sin(a) * midR;
      refLine.position.set(rx, 0, rz);
      refDot.position.set(rx, 0, rz);

      const band = dispRef.current[bestIdx];
      infoRef.current = {
        side,
        freq: formatFreq(band.freq),
        db: `${band.db >= 0 ? "+" : ""}${band.db.toFixed(1)} dB`,
      };
    }

    function drawOverlay() {
      ctx.clearRect(0, 0, W, H);
      ctx.save();

      ctx.fillStyle = "rgba(255,255,255,0.92)";
      ctx.font = "600 34px system-ui, sans-serif";
      ctx.fillText("Tone Fingerprint", 22, 44);

      ctx.fillStyle = "rgba(180,195,210,0.7)";
      ctx.font = "500 17px system-ui, sans-serif";
      ctx.fillText("Left \u25BC missing  \u00B7  Right \u25B2 augmented", 22, 70);

      // Cold legend
      ctx.fillStyle = "rgba(76,201,240,0.9)";
      ctx.fillRect(22, 92, 16, 16);
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      ctx.font = "500 16px system-ui, sans-serif";
      ctx.fillText("Missing \u25BC", 46, 106);

      // Warm legend
      ctx.fillStyle = "rgba(255,123,0,0.9)";
      ctx.fillRect(180, 92, 16, 16);
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      ctx.fillText("Augmented \u25B2", 204, 106);

      // Frequency readout
      const nfo = infoRef.current;
      ctx.shadowColor = "rgba(0,221,255,0.5)";
      ctx.shadowBlur = 12;
      ctx.fillStyle = "rgba(0,221,255,0.95)";
      ctx.font = "700 28px 'JetBrains Mono', monospace";
      ctx.fillText(nfo.freq, 22, H - 58);

      ctx.shadowBlur = 0;
      ctx.fillStyle = nfo.side === "boost" ? "rgba(255,123,0,0.95)" : "rgba(76,201,240,0.95)";
      ctx.font = "600 22px 'JetBrains Mono', monospace";
      ctx.fillText(nfo.db, 22, H - 32);

      ctx.fillStyle = "rgba(160,175,190,0.45)";
      ctx.font = "500 15px system-ui";
      ctx.fillText(nfo.side === "boost" ? "\u25B2 augmented" : "\u25BC missing", 22, H - 12);

      ctx.restore();
    }

    function syncFrame(dt) {
      const d = dispRef.current;
      const l = latestRef.current;
      const alpha = 1 - Math.exp(-dt * 8.0);
      for (let i = 0; i < NUM_BANDS; i++) {
        d[i].db = lerp(d[i].db, l[i].db, alpha);
        d[i].energy = lerp(d[i].energy, l[i].energy, alpha);
        d[i].freq = l[i].freq;
      }
    }

    let lastT = performance.now() * 0.001;

    function loop(nowMs) {
      animRef.current = requestAnimationFrame(loop);
      if (!rendRef.current) return;

      const nowS = nowMs * 0.001;
      const dt = clamp(nowS - lastT, 0, 0.1);
      lastT = nowS;

      syncFrame(dt);

      // Update surfaces
      updateSurface(leftGeo, leftAngles, dispRef.current, "missing");
      updateSurface(rightGeo, rightAngles, dispRef.current, "boost");

      // Camera orbit
      const r = rotRef.current;
      r.x = lerp(r.x, r.tx, 0.07);
      r.y = lerp(r.y, r.ty, 0.07);
      if (!ptrRef.current.dn && !pausedRef.current) r.ty -= 0.0016;

      cam.position.set(
        Math.sin(r.y) * Math.cos(r.x) * CAM_DIST,
        -Math.sin(r.x) * CAM_DIST,
        Math.cos(r.y) * Math.cos(r.x) * CAM_DIST,
      );
      cam.lookAt(0, 0, 0);

      // Pulse
      const pulse = 0.45 + Math.sin(nowMs * 0.0014) * 0.12;
      ringMat.opacity = pulse;
      ringGlowMat.opacity = pulse * 0.25;

      updateReference();
      ren.render(scene, cam);
      drawOverlay();
    }

    // Input
    const cv = ren.domElement;
    const pd = (x, y) => { ptrRef.current = { dn: true, x, y }; };
    const pu = () => { ptrRef.current.dn = false; };
    const pm = (x, y) => {
      if (!ptrRef.current.dn) return;
      rotRef.current.ty -= (x - ptrRef.current.x) * 0.006;
      rotRef.current.tx += (y - ptrRef.current.y) * 0.004;
      ptrRef.current.x = x; ptrRef.current.y = y;
    };
    cv.addEventListener("mousedown", e => pd(e.clientX, e.clientY));
    cv.addEventListener("mousemove", e => pm(e.clientX, e.clientY));
    cv.addEventListener("mouseup", pu); cv.addEventListener("mouseleave", pu);
    cv.addEventListener("touchstart", e => { const t2 = e.touches[0]; pd(t2.clientX, t2.clientY); }, { passive: true });
    cv.addEventListener("touchmove", e => { e.preventDefault(); const t2 = e.touches[0]; pm(t2.clientX, t2.clientY); }, { passive: false });
    cv.addEventListener("touchend", pu);

    // Data polling
    let cancelled = false;
    let demoT = 0;
    async function poll() {
      while (!cancelled) {
        const start = performance.now();
        demoT += DATA_PERIOD;
        latestRef.current = normalizeFrame(makeDemoFrame(demoT));
        const elapsed = performance.now() - start;
        await new Promise(r => setTimeout(r, Math.max(0, DATA_PERIOD * 1000 - elapsed)));
      }
    }
    poll();
    animRef.current = requestAnimationFrame(loop);

    return () => {
      cancelled = true;
      if (animRef.current) cancelAnimationFrame(animRef.current);
      ren.dispose();
      leftGeo.dispose(); rightGeo.dispose();
      surfaceMat.dispose();
      ringGeo.dispose(); ringMat.dispose();
      ringGlowGeo.dispose(); ringGlowMat.dispose();
      divGeo.dispose(); divMat.dispose();
      refGeo.dispose(); refMat.dispose();
      refDotGeo.dispose(); refDotMat.dispose();
      if (el.contains(ren.domElement)) el.removeChild(ren.domElement);
    };
  }, [W, H]);

  return (
    <div className="flex flex-col items-center bg-black min-h-screen p-3">
      <div style={{
        position: "relative", width: W, height: H, borderRadius: 18, overflow: "hidden",
        boxShadow: "0 16px 48px rgba(0,0,0,0.5)", border: "1px solid rgba(255,255,255,0.06)",
      }}>
        <div ref={mountRef} style={{ position: "absolute", inset: 0, cursor: "grab" }} />
        <canvas ref={overlayRef} width={W} height={H}
          style={{ position: "absolute", inset: 0, pointerEvents: "none" }} />
        <button onClick={() => setPaused(v => !v)}
          style={{
            position: "absolute", right: 16, top: 16, zIndex: 5,
            border: "1px solid rgba(255,255,255,0.15)", background: "rgba(17,24,39,0.7)",
            color: "#fff", borderRadius: 999, padding: "8px 14px", fontSize: 14,
            backdropFilter: "blur(8px)",
          }}>
          {paused ? "Resume" : "Pause"}
        </button>
      </div>
      <p className="text-xs text-gray-600 mt-3">
        Continuous surface · Left drops below (missing) · Right rises above (augmented)
      </p>
    </div>
  );
}

import { useState, useRef, useEffect } from "react";
import * as THREE from "three";

const W = 800;
const H = 480;
const NUM_BANDS = 48;
const DISC_RADIUS = 2.8;
const MAX_BAR_HEIGHT = 3.5;
const MAX_DB = 18;

function generateTFData(seed, time) {
  const data = [];
  for (let i = 0; i < NUM_BANDS; i++) {
    const t = i / (NUM_BANDS - 1);
    const freq = 20 * Math.pow(20000 / 20, t);
    let db = 0;
    const bD = Math.abs(Math.log2(freq / 140));
    if (bD < 1.2) db += 5.5 * Math.pow(1 - bD / 1.2, 1.5);
    const mD = Math.abs(Math.log2(freq / 700));
    if (mD < 1) db -= 6.5 * Math.pow(1 - mD, 1.3);
    const pD = Math.abs(Math.log2(freq / 3200));
    if (pD < 0.6) db += 4 * Math.pow(1 - pD / 0.6, 1.2);
    if (freq > 7000) db -= 9 * Math.pow(Math.log10(freq / 7000), 1.5);
    db += Math.sin(i * 2.1 + time * 0.8 + seed) * 0.7;
    db += Math.sin(i * 0.7 + time * 0.5) * 0.5;
    let energy = 0.3;
    if (freq > 60 && freq < 12000) energy = 0.5 + 0.4 * Math.exp(-Math.pow(Math.log2(freq / 500), 2) / 3);
    energy += Math.sin(i * 1.3 + time * 0.6) * 0.06;
    energy = Math.max(0.15, Math.min(1.0, energy));
    data.push({ db, energy, freq });
  }
  return data;
}

function generatePresetData(key, seed, time) {
  const base = generateTFData(seed, time);
  if (key === "clean") {
    return base.map((b, i) => {
      const freq = 20 * Math.pow(20000 / 20, i / NUM_BANDS);
      let db = 1.5 + Math.sin(i * 0.8 + time * 0.5) * 0.4;
      if (freq > 5000) db += 2 * Math.log10(freq / 5000);
      if (freq > 14000) db -= 3;
      return { ...b, db: db + Math.sin(i * 2.1 + time * 0.8) * 0.5 };
    });
  }
  if (key === "wah") {
    return base.map((b, i) => {
      const freq = 20 * Math.pow(20000 / 20, i / NUM_BANDS);
      let db = -8;
      const wahF = 1200 + Math.sin(time * 0.3) * 200;
      const d = Math.abs(Math.log2(freq / wahF));
      if (d < 0.8) db = 10 * Math.pow(1 - d / 0.8, 2);
      return { ...b, db: db + Math.sin(i * 1.7 + time * 0.7) * 0.4, energy: Math.max(0.15, b.energy * (db > -2 ? 1 : 0.4)) };
    });
  }
  if (key === "cable") {
    return base.map((b, i) => {
      const freq = 20 * Math.pow(20000 / 20, i / NUM_BANDS);
      let db = 0;
      if (freq > 800) db = -16 * Math.pow(Math.log10(freq / 800), 1.6);
      db = Math.max(-16, db) + Math.sin(i * 1.5 + time * 0.6) * 0.3;
      return { ...b, db, energy: Math.max(0.3, 0.7 - Math.max(0, (freq - 2000) / 20000) * 0.5) };
    });
  }
  return base;
}

// Per-bar proportional gradient: base color at disc, tip color at end
// The gradient spans the full bar regardless of height
function getBoostBaseColor() { return new THREE.Color(0.1, 0.3, 0.95); }
function getBoostTipColor(db) {
  const t = Math.min(1, db / 14);
  return new THREE.Color(0.1 + t * 0.15, 0.75 + t * 0.25, 0.35 - t * 0.15);
}
function getCutBaseColor() { return new THREE.Color(1.0, 0.9, 0.15); }
function getCutTipColor(db) {
  const t = Math.min(1, Math.abs(db) / 14);
  return new THREE.Color(1.0, 0.2 - t * 0.1, 0.05);
}

function createGradientCylinder(segments) {
  const geo = new THREE.CylinderGeometry(1, 1, 1, segments, 6, false);
  const count = geo.attributes.position.count;
  const colors = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    colors[i * 3] = 0.1; colors[i * 3 + 1] = 0.3; colors[i * 3 + 2] = 0.9;
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geo;
}

function updateCylinderColors(geo, baseColor, tipColor, isBoost) {
  const colors = geo.attributes.color.array;
  const count = geo.attributes.position.count;
  for (let i = 0; i < count; i++) {
    const y = geo.attributes.position.getY(i);
    // For boost: bottom(y=-0.5)=base, top(y=+0.5)=tip
    // For cut: top(y=+0.5)=base(near disc), bottom(y=-0.5)=tip(far)
    const mix = isBoost ? (y + 0.5) : (0.5 - y);
    colors[i * 3]     = baseColor.r + (tipColor.r - baseColor.r) * mix;
    colors[i * 3 + 1] = baseColor.g + (tipColor.g - baseColor.g) * mix;
    colors[i * 3 + 2] = baseColor.b + (tipColor.b - baseColor.b) * mix;
  }
  geo.attributes.color.needsUpdate = true;
}

function angleToBandFreq(refAngle) {
  // refAngle from atan2, in [-π, π]
  // Bottom of circle (band 0, lowest freq) is at angle π/2
  // Top of circle (band N-1, highest freq) is at angle -π/2
  // Left and right sides are mirrored (same frequency)
  let diff = refAngle - Math.PI / 2;
  // Normalize to [-π, π]
  while (diff > Math.PI) diff -= 2 * Math.PI;
  while (diff < -Math.PI) diff += 2 * Math.PI;
  // Absolute angular distance from bottom (mirrored)
  const dist = Math.abs(diff);
  // 0 at bottom → π at top
  const t = Math.min(1, Math.max(0, dist / Math.PI));
  return 20 * Math.pow(20000 / 20, t);
}

function formatFreq(freq) {
  if (freq >= 10000) return (freq / 1000).toFixed(1) + " kHz";
  if (freq >= 1000) return (freq / 1000).toFixed(2) + " kHz";
  return Math.round(freq) + " Hz";
}

export default function App() {
  const mountRef = useRef(null);
  const overlayRef = useRef(null);
  const barsRef = useRef([]);
  const refLineRef = useRef(null);
  const ringMatRef = useRef(null);
  const ringGlowMatRef = useRef(null);
  const animRef = useRef(null);
  const timeRef = useRef(0);
  const mouseRef = useRef({ isDown: false, lastX: 0, lastY: 0 });
  const rotRef = useRef({ x: -0.55, y: 0, targetX: -0.55, targetY: 0 });
  const [preset, setPreset] = useState("overdrive");
  const presetRef = useRef("overdrive");

  const presets = {
    overdrive: { seed: 3.5, label: "Overdrive Pedal" },
    clean: { seed: 7.2, label: "Clean Boost" },
    wah: { seed: 11.0, label: "Wah Pedal" },
    cable: { seed: 5.8, label: "Long Cable" },
  };

  useEffect(() => { presetRef.current = preset; }, [preset]);

  useEffect(() => {
    const container = mountRef.current;
    const overlay = overlayRef.current;
    if (!container || !overlay) return;
    const overlayCtx = overlay.getContext("2d");

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x030508);
    const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 100);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.sortObjects = true;
    container.appendChild(renderer.domElement);

    // Vivid lighting
    scene.add(new THREE.AmbientLight(0xffffff, 0.45));
    const topLight = new THREE.PointLight(0xeeeeff, 0.7, 30);
    topLight.position.set(0, 10, 3);
    scene.add(topLight);
    const underLight = new THREE.PointLight(0xff8844, 0.5, 25);
    underLight.position.set(0, -10, 0);
    scene.add(underLight);

    // === PULSING RING — thin white heartbeat, the only baseline ===
    const ringGeo = new THREE.TorusGeometry(DISC_RADIUS, 0.012, 8, 128);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0xddeeff, transparent: true, opacity: 0.7,
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 2;
    scene.add(ring);
    ringMatRef.current = ringMat;

    const ringGlowGeo = new THREE.TorusGeometry(DISC_RADIUS, 0.04, 8, 128);
    const ringGlowMat = new THREE.MeshBasicMaterial({
      color: 0x88bbee, transparent: true, opacity: 0.2, depthWrite: false,
    });
    const ringGlow = new THREE.Mesh(ringGlowGeo, ringGlowMat);
    ringGlow.rotation.x = Math.PI / 2;
    scene.add(ringGlow);
    ringGlowMatRef.current = ringGlowMat;

    // === REFERENCE LINE — anchored to RING, short cyan marker ===
    const refHeight = MAX_BAR_HEIGHT * 0.125;
    const refLineGeo = new THREE.CylinderGeometry(0.04, 0.04, refHeight * 2, 8);
    const refLineMat = new THREE.MeshBasicMaterial({
      color: 0x00ddff, transparent: true, opacity: 0.75,
    });
    const refLine = new THREE.Mesh(refLineGeo, refLineMat);
    scene.add(refLine);

    // Cyan dot on the ring
    const refDotGeo = new THREE.SphereGeometry(0.07, 12, 12);
    const refDotMat = new THREE.MeshBasicMaterial({ color: 0x00ffee });
    const refDot = new THREE.Mesh(refDotGeo, refDotMat);
    scene.add(refDot);

    refLineRef.current = { line: refLine, dot: refDot };

    // === BARS — cylinders with threshold-based vertex gradients ===
    const bars = [];
    for (let i = 0; i < NUM_BANDS; i++) {
      const t = i / (NUM_BANDS - 1);
      const rightAngle = Math.PI / 2 - t * Math.PI;
      const leftAngle = Math.PI / 2 + t * Math.PI;

      for (const angle of [rightAngle, leftAngle]) {
        const bx = Math.cos(angle) * (DISC_RADIUS * 0.88);
        const bz = -Math.sin(angle) * (DISC_RADIUS * 0.88);

        const geo = createGradientCylinder(8);
        const mat = new THREE.MeshBasicMaterial({
          vertexColors: true,
          transparent: true,
          opacity: 0.95,
        });
        const bar = new THREE.Mesh(geo, mat);
        bar.position.set(bx, 0, bz);
        bar.userData = { bandIndex: i, angle };
        scene.add(bar);
        bars.push(bar);
      }
    }
    barsRef.current = bars;

    // === INPUT — swipe right = rotate right ===
    const canvas = renderer.domElement;
    const onDown = (cx, cy) => { mouseRef.current = { isDown: true, lastX: cx, lastY: cy }; };
    const onUp = () => { mouseRef.current.isDown = false; };
    const onMove = (cx, cy) => {
      if (!mouseRef.current.isDown) return;
      const dx = cx - mouseRef.current.lastX;
      const dy = cy - mouseRef.current.lastY;
      rotRef.current.targetY -= dx * 0.008;
      rotRef.current.targetX += dy * 0.005;
      mouseRef.current.lastX = cx;
      mouseRef.current.lastY = cy;
    };
    canvas.addEventListener("mousedown", e => onDown(e.clientX, e.clientY));
    canvas.addEventListener("mouseup", onUp);
    canvas.addEventListener("mouseleave", onUp);
    canvas.addEventListener("mousemove", e => onMove(e.clientX, e.clientY));
    canvas.addEventListener("touchstart", e => { const t2 = e.touches[0]; onDown(t2.clientX, t2.clientY); });
    canvas.addEventListener("touchend", onUp);
    canvas.addEventListener("touchmove", e => { e.preventDefault(); const t2 = e.touches[0]; onMove(t2.clientX, t2.clientY); }, { passive: false });

    // === ANIMATION ===
    const animate = () => {
      timeRef.current += 0.025;
      const time = timeRef.current;
      const key = presetRef.current;
      const seedVal = presets[key]?.seed || 3.5;
      const data = generatePresetData(key, seedVal, time);

      rotRef.current.x += (rotRef.current.targetX - rotRef.current.x) * 0.08;
      rotRef.current.y += (rotRef.current.targetY - rotRef.current.y) * 0.08;
      if (!mouseRef.current.isDown) rotRef.current.targetY -= 0.0018;

      const camDist = 8.5;
      camera.position.set(
        Math.sin(rotRef.current.y) * Math.cos(rotRef.current.x) * camDist,
        -Math.sin(rotRef.current.x) * camDist,
        Math.cos(rotRef.current.y) * Math.cos(rotRef.current.x) * camDist,
      );
      camera.lookAt(0, 0, 0);

      // Pulse ring
      const pulse = 0.4 + 0.3 * Math.sin(time * 1.2) + 0.12 * Math.sin(time * 2.7);
      if (ringMatRef.current) ringMatRef.current.opacity = pulse;
      if (ringGlowMatRef.current) ringGlowMatRef.current.opacity = pulse * 0.3;

      // === REFERENCE LINE — anchored to ring, closest point to camera ===
      const camXZ = new THREE.Vector2(camera.position.x, camera.position.z);
      let currentFreqText = "";
      if (camXZ.length() > 0.01) {
        camXZ.normalize();
        // Place on the RING radius, not the bar radius
        const refX = camXZ.x * DISC_RADIUS;
        const refZ = camXZ.y * DISC_RADIUS;

        if (refLineRef.current) {
          refLineRef.current.line.position.set(refX, 0, refZ);
          refLineRef.current.dot.position.set(refX, 0, refZ);
        }

        const refAngle = Math.atan2(-refZ, refX);
        const freq = angleToBandFreq(refAngle);
        currentFreqText = formatFreq(freq);
      }

      // Update bars with per-bar proportional gradients
      for (let bi = 0; bi < barsRef.current.length; bi++) {
        const bar = barsRef.current[bi];
        const d = data[bar.userData.bandIndex];
        if (!d) continue;

        const absDb = Math.abs(d.db);
        const barHeight = Math.max(0.05, (absDb / MAX_DB) * MAX_BAR_HEIGHT);
        const isBoost = d.db >= 0;
        const barRadius = 0.03 + d.energy * 0.06;

        bar.scale.set(barRadius * 2, barHeight, barRadius * 2);
        bar.position.y = isBoost ? barHeight / 2 + 0.005 : -(barHeight / 2 + 0.005);

        if (isBoost) {
          updateCylinderColors(bar.geometry, getBoostBaseColor(), getBoostTipColor(d.db), true);
        } else {
          updateCylinderColors(bar.geometry, getCutBaseColor(), getCutTipColor(d.db), false);
        }
      }

      renderer.render(scene, camera);

      // === DRAW FREQUENCY TEXT ON 2D OVERLAY ===
      overlayCtx.clearRect(0, 0, W, H);
      if (currentFreqText) {
        // Glow
        overlayCtx.shadowColor = "rgba(0, 221, 255, 0.6)";
        overlayCtx.shadowBlur = 15;
        overlayCtx.fillStyle = "#00ddff";
        overlayCtx.font = "bold 22px 'JetBrains Mono', 'Courier New', monospace";
        overlayCtx.fillText(currentFreqText, 16, 32);

        // Subtitle
        overlayCtx.shadowBlur = 0;
        overlayCtx.fillStyle = "rgba(0, 221, 255, 0.35)";
        overlayCtx.font = "11px sans-serif";
        overlayCtx.fillText("▼ reference", 16, 48);
      }

      animRef.current = requestAnimationFrame(animate);
    };
    animRef.current = requestAnimationFrame(animate);

    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
      renderer.dispose();
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement);
    };
  }, []);

  return (
    <div className="flex flex-col items-center bg-black min-h-screen p-4">
      <h1 className="text-lg font-semibold text-gray-300 tracking-wide mb-1">
        3D Radial Tone Fingerprint
      </h1>
      <p className="text-xs text-gray-600 mb-3">Drag to orbit · Full 360° · Cyan line = frequency reference</p>
      <div className="flex gap-2 mb-3 flex-wrap justify-center">
        {Object.entries(presets).map(([key, p]) => (
          <button key={key} onClick={() => setPreset(key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              preset === key ? "bg-gray-700 text-white shadow-lg" : "bg-gray-900 text-gray-500 hover:bg-gray-800"
            }`}>
            {p.label}
          </button>
        ))}
      </div>
      <div style={{ position: "relative", width: W, height: H }}
        className="rounded-xl overflow-hidden shadow-2xl shadow-black/80 border border-gray-800/30">
        {/* 3D WebGL canvas container */}
        <div ref={mountRef} style={{ position: "absolute", top: 0, left: 0, width: W, height: H, cursor: "grab" }} />
        {/* 2D overlay canvas for frequency text */}
        <canvas ref={overlayRef} width={W} height={H}
          style={{ position: "absolute", top: 0, left: 0, width: W, height: H, pointerEvents: "none" }} />
      </div>
      <div className="mt-3 max-w-xl text-xs text-gray-600 space-y-1 text-center">
        <p>UP: blue → green = boost · DOWN: yellow → red = cut</p>
        <p>Gradient spans each bar · Cyan marker tracks nearest frequency</p>
      </div>
    </div>
  );
}

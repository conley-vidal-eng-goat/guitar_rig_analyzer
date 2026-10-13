import React, { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

/**
 * ToneFingerprintSplit.jsx
 *
 * Split radial tone fingerprint for Raspberry Pi 5 / CM5 + Touch Display 2 (7"):
 *   - Display resolution target: 720 x 1280 portrait.
 *   - Left side  = missing / attenuated frequencies (cold colors, bars DROP BELOW ring)
 *   - Right side = augmented / boosted frequencies (warm colors, bars RISE ABOVE ring)
 *   - Direction reinforces meaning: down = loss, up = gain.
 *   - Uses InstancedMesh for low draw-call overhead.
 *   - Interpolates between incoming frames (~10.8 Hz) for smooth 60 FPS rendering.
 *   - Full 360° orbit — user can view from any angle including underneath.
 *   - Cyan reference line tracks nearest frequency to camera.
 *
 * INPUT DATA CONTRACT
 * -------------------
 * Each band item:
 *   { freq: number, db: number, energy?: number }
 *   db > 0 = augmented (right side, rises up)
 *   db < 0 = missing (left side, drops down)
 *   energy 0..1 controls bar thickness
 */

const DISPLAY_WIDTH = 720;
const DISPLAY_HEIGHT = 1280;
const NUM_BANDS = 48;
const DISC_RADIUS = 3.15;
const MAX_BAR_HEIGHT = 4.2;
const MAX_DB = 18;
const DATA_HZ = 10.8;

const CAMERA_DISTANCE = 10.5;
const BAR_RADIUS_BASE = 0.035;
const BAR_RADIUS_GAIN = 0.05;

// Left side arc (missing/attenuated) — wraps the left half of the ring
const LEFT_START = Math.PI * 0.62;
const LEFT_END = Math.PI * 1.38;
// Right side arc (augmented/boosted) — wraps the right half of the ring
const RIGHT_START = -Math.PI * 0.38;
const RIGHT_END = Math.PI * 0.38;

// Cyan reference line
const REF_LINE_HEIGHT = MAX_BAR_HEIGHT * 0.18;
const REF_LINE_COLOR = 0x00ddff;

const COLD_COLOR = new THREE.Color("#4cc9f0");
const COLD_ALERT_COLOR = new THREE.Color("#90e0ef");
const WARM_COLOR = new THREE.Color("#ff7b00");
const WARM_ALERT_COLOR = new THREE.Color("#ffd166");
const RING_COLOR = new THREE.Color("#9fb3c8");
const BACKGROUND_COLOR = new THREE.Color(0x04070b);

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function logFreqAt(index, count) {
  const t = count <= 1 ? 0 : index / (count - 1);
  return 20 * Math.pow(20000 / 20, t);
}

function formatFreq(freq) {
  if (freq >= 10000) return `${(freq / 1000).toFixed(1)} kHz`;
  if (freq >= 1000) return `${(freq / 1000).toFixed(2)} kHz`;
  return `${Math.round(freq)} Hz`;
}

function makeDemoFrame(timeSec) {
  const frame = [];
  for (let i = 0; i < NUM_BANDS; i++) {
    const freq = logFreqAt(i, NUM_BANDS);
    let db = 0;
    const lowPresence = Math.abs(Math.log2(freq / 140));
    if (lowPresence < 1.1) db += 4.6 * Math.pow(1 - lowPresence / 1.1, 1.5);
    const midDip = Math.abs(Math.log2(freq / 900));
    if (midDip < 0.9) db -= 5.8 * Math.pow(1 - midDip / 0.9, 1.4);
    const upperPeak = Math.abs(Math.log2(freq / 3200));
    if (upperPeak < 0.55) db += 4.0 * Math.pow(1 - upperPeak / 0.55, 1.3);
    if (freq > 7000) db -= 8 * Math.pow(Math.log10(freq / 7000), 1.5);
    db += Math.sin(i * 0.7 + timeSec * 0.8) * 0.55;
    db += Math.sin(i * 1.9 + timeSec * 0.45) * 0.35;
    let energy = 0.45 + 0.4 * Math.exp(-Math.pow(Math.log2(freq / 700), 2) / 4);
    energy += Math.sin(i * 1.37 + timeSec * 0.65) * 0.05;
    energy = clamp(energy, 0.18, 1.0);
    frame.push({ freq, db, energy });
  }
  return frame;
}

function normalizeFrame(frame) {
  const normalized = new Array(NUM_BANDS);
  for (let i = 0; i < NUM_BANDS; i++) {
    const item = frame?.[i];
    normalized[i] = {
      freq: item?.freq ?? logFreqAt(i, NUM_BANDS),
      db: clamp(item?.db ?? 0, -MAX_DB, MAX_DB),
      energy: clamp(item?.energy ?? 0.4, 0.15, 1),
    };
  }
  return normalized;
}

function buildBandLayout(sideStart, sideEnd) {
  const angles = [];
  for (let i = 0; i < NUM_BANDS; i++) {
    const t = NUM_BANDS <= 1 ? 0 : i / (NUM_BANDS - 1);
    angles.push(lerp(sideStart, sideEnd, t));
  }
  return angles;
}

function colorForMagnitude(mag, side) {
  const t = clamp(mag / MAX_DB, 0, 1);
  if (side === "missing") {
    return COLD_COLOR.clone().lerp(COLD_ALERT_COLOR, t);
  }
  return WARM_COLOR.clone().lerp(WARM_ALERT_COLOR, t);
}

function makeBarGeometry() {
  return new THREE.CylinderGeometry(1, 1, 1, 10, 1, false);
}

export default function ToneFingerprintSplit({
  getLiveData,
  width = DISPLAY_WIDTH,
  height = DISPLAY_HEIGHT,
}) {
  const mountRef = useRef(null);
  const overlayRef = useRef(null);
  const rendererRef = useRef(null);
  const animationRef = useRef(null);
  const dataTimerRef = useRef(null);
  const latestFrameRef = useRef(normalizeFrame(makeDemoFrame(0)));
  const displayedFrameRef = useRef(normalizeFrame(makeDemoFrame(0)));
  const rotationRef = useRef({ x: -0.52, y: 0.0, targetX: -0.52, targetY: 0.0 });
  const pointerRef = useRef({ isDown: false, x: 0, y: 0 });
  const hoveredRef = useRef({ side: "boost", index: 0, freqText: "20 Hz", dbText: "+0.0 dB" });
  const [isPaused, setIsPaused] = useState(false);

  const leftAngles = useMemo(() => buildBandLayout(LEFT_START, LEFT_END), []);
  const rightAngles = useMemo(() => buildBandLayout(RIGHT_START, RIGHT_END), []);

  useEffect(() => {
    const container = mountRef.current;
    const overlayCanvas = overlayRef.current;
    if (!container || !overlayCanvas) return undefined;

    const overlayCtx = overlayCanvas.getContext("2d");
    const scene = new THREE.Scene();
    scene.background = BACKGROUND_COLOR;

    const camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 100);
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(1);
    renderer.setSize(width, height);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Lighting — bright enough to illuminate bars both above and below the ring
    scene.add(new THREE.AmbientLight(0xffffff, 0.7));

    const keyLight = new THREE.DirectionalLight(0xffffff, 1.25);
    keyLight.position.set(3, 7, 5);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x99bbff, 0.45);
    fillLight.position.set(-4, 2, -3);
    scene.add(fillLight);

    // Underlight — illuminates the missing/cut bars below the ring
    const underLight = new THREE.DirectionalLight(0xaaddff, 0.6);
    underLight.position.set(0, -6, 2);
    scene.add(underLight);

    // === PULSING RING — the baseline reference ===
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(DISC_RADIUS, 0.025, 10, 160),
      new THREE.MeshBasicMaterial({ color: RING_COLOR, transparent: true, opacity: 0.65 })
    );
    ring.rotation.x = Math.PI / 2;
    scene.add(ring);

    const ringGlow = new THREE.Mesh(
      new THREE.TorusGeometry(DISC_RADIUS, 0.075, 8, 128),
      new THREE.MeshBasicMaterial({ color: 0x38506b, transparent: true, opacity: 0.18, depthWrite: false })
    );
    ringGlow.rotation.x = Math.PI / 2;
    scene.add(ringGlow);

    // === DIVIDER LINE — separates missing (left) from augmented (right) ===
    const dividerGeo = new THREE.CylinderGeometry(0.015, 0.015, DISC_RADIUS * 2.25, 8);
    const dividerMat = new THREE.MeshBasicMaterial({ color: 0x41556f, transparent: true, opacity: 0.35 });
    const leftDivider = new THREE.Mesh(dividerGeo, dividerMat);
    leftDivider.rotation.z = Math.PI / 2;
    leftDivider.position.y = 0.01;
    scene.add(leftDivider);

    // === CYAN REFERENCE LINE — tracks nearest frequency to camera ===
    const refLineGeo = new THREE.CylinderGeometry(0.035, 0.035, REF_LINE_HEIGHT * 2, 8);
    const refLineMat = new THREE.MeshBasicMaterial({
      color: REF_LINE_COLOR, transparent: true, opacity: 0.75,
    });
    const refLine = new THREE.Mesh(refLineGeo, refLineMat);
    scene.add(refLine);

    // Cyan dot on the ring where the reference line sits
    const refDot = new THREE.Mesh(
      new THREE.SphereGeometry(0.07, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0x00ffee })
    );
    scene.add(refDot);

    // === BARS — InstancedMesh for performance ===
    const barGeometry = makeBarGeometry();
    const coldMaterial = new THREE.MeshStandardMaterial({
      color: COLD_COLOR,
      emissive: 0x0f2230,
      roughness: 0.45,
      metalness: 0.12,
    });
    const warmMaterial = new THREE.MeshStandardMaterial({
      color: WARM_COLOR,
      emissive: 0x331400,
      roughness: 0.45,
      metalness: 0.12,
    });

    const missingBars = new THREE.InstancedMesh(barGeometry, coldMaterial, NUM_BANDS);
    const boostBars = new THREE.InstancedMesh(barGeometry, warmMaterial, NUM_BANDS);
    missingBars.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    boostBars.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    missingBars.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(NUM_BANDS * 3), 3);
    boostBars.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(NUM_BANDS * 3), 3);
    scene.add(missingBars);
    scene.add(boostBars);

    const tmpMatrix = new THREE.Matrix4();
    const tmpPos = new THREE.Vector3();
    const tmpScale = new THREE.Vector3();
    const tmpQuat = new THREE.Quaternion();
    const yAxis = new THREE.Vector3(0, 1, 0);

    function updateBars() {
      const displayed = displayedFrameRef.current;

      for (let i = 0; i < NUM_BANDS; i++) {
        const item = displayed[i];
        const magnitude = Math.abs(item.db);
        const energy = item.energy;
        const heightScale = Math.max(0.03, (magnitude / MAX_DB) * MAX_BAR_HEIGHT);
        const radiusScale = BAR_RADIUS_BASE + energy * BAR_RADIUS_GAIN;

        // LEFT SIDE = missing / attenuated frequencies.
        // Bars DROP BELOW the ring when db is negative — direction = loss.
        const missingActive = item.db < 0;
        const missingHeight = missingActive ? heightScale : 0.02;
        const missingAngle = leftAngles[i];
        const missingY = missingActive
          ? -(missingHeight / 2 + 0.01)   // below the ring
          : 0.01;                          // flat stub at ring level
        tmpPos.set(
          Math.cos(missingAngle) * (DISC_RADIUS * 0.92),
          missingY,
          -Math.sin(missingAngle) * (DISC_RADIUS * 0.92)
        );
        tmpQuat.setFromAxisAngle(yAxis, 0);
        tmpScale.set(radiusScale, missingHeight, radiusScale);
        tmpMatrix.compose(tmpPos, tmpQuat, tmpScale);
        missingBars.setMatrixAt(i, tmpMatrix);
        const missingColor = colorForMagnitude(magnitude, "missing");
        if (!missingActive) missingColor.multiplyScalar(0.2);
        missingBars.setColorAt(i, missingColor);

        // RIGHT SIDE = augmented / boosted frequencies.
        // Bars RISE ABOVE the ring when db is positive — direction = gain.
        const boostActive = item.db > 0;
        const boostHeight = boostActive ? heightScale : 0.02;
        const boostAngle = rightAngles[i];
        const boostY = boostActive
          ? boostHeight / 2 + 0.01    // above the ring
          : 0.01;                      // flat stub at ring level
        tmpPos.set(
          Math.cos(boostAngle) * (DISC_RADIUS * 0.92),
          boostY,
          -Math.sin(boostAngle) * (DISC_RADIUS * 0.92)
        );
        tmpScale.set(radiusScale, boostHeight, radiusScale);
        tmpMatrix.compose(tmpPos, tmpQuat, tmpScale);
        boostBars.setMatrixAt(i, tmpMatrix);
        const boostColor = colorForMagnitude(magnitude, "boost");
        if (!boostActive) boostColor.multiplyScalar(0.2);
        boostBars.setColorAt(i, boostColor);
      }

      missingBars.instanceMatrix.needsUpdate = true;
      boostBars.instanceMatrix.needsUpdate = true;
      if (missingBars.instanceColor) missingBars.instanceColor.needsUpdate = true;
      if (boostBars.instanceColor) boostBars.instanceColor.needsUpdate = true;
    }

    function updateReference() {
      const camXZ = new THREE.Vector2(camera.position.x, camera.position.z);
      if (camXZ.lengthSq() < 1e-6) return;
      camXZ.normalize();
      const angle = Math.atan2(-camXZ.y, camXZ.x);

      // Determine which side the camera is facing
      const rightDistance = Math.abs(THREE.MathUtils.euclideanModulo(angle - 0, Math.PI * 2));
      const isRight = rightDistance < Math.PI / 2 || rightDistance > Math.PI * 1.5;
      const side = isRight ? "boost" : "missing";
      const angles = isRight ? rightAngles : leftAngles;

      // Find the nearest band to the camera angle
      let bestIndex = 0;
      let bestDelta = Number.POSITIVE_INFINITY;
      for (let i = 0; i < angles.length; i++) {
        const delta = Math.abs(Math.atan2(Math.sin(angle - angles[i]), Math.cos(angle - angles[i])));
        if (delta < bestDelta) {
          bestDelta = delta;
          bestIndex = i;
        }
      }

      // Position the cyan reference line and dot on the ring
      const a = angles[bestIndex];
      const refX = Math.cos(a) * DISC_RADIUS;
      const refZ = -Math.sin(a) * DISC_RADIUS;
      refLine.position.set(refX, 0, refZ);
      refDot.position.set(refX, 0, refZ);

      // Update the hover readout
      const band = displayedFrameRef.current[bestIndex];
      hoveredRef.current = {
        side,
        index: bestIndex,
        freqText: formatFreq(band.freq),
        dbText: `${band.db >= 0 ? "+" : ""}${band.db.toFixed(1)} dB`,
      };
    }

    function drawOverlay() {
      overlayCtx.clearRect(0, 0, width, height);
      overlayCtx.save();

      // Title
      overlayCtx.fillStyle = "rgba(255,255,255,0.92)";
      overlayCtx.font = "600 34px system-ui, sans-serif";
      overlayCtx.fillText("Tone Fingerprint", 22, 44);

      // Subtitle
      overlayCtx.fillStyle = "rgba(180,195,210,0.75)";
      overlayCtx.font = "500 18px system-ui, sans-serif";
      overlayCtx.fillText("Left ▼ missing  ·  Right ▲ augmented", 22, 72);

      // Legend — missing (cold)
      overlayCtx.fillStyle = "rgba(76,201,240,0.95)";
      overlayCtx.fillRect(22, 94, 18, 18);
      overlayCtx.fillStyle = "rgba(255,255,255,0.92)";
      overlayCtx.font = "500 18px system-ui, sans-serif";
      overlayCtx.fillText("Missing ▼ below ring", 50, 109);

      // Legend — augmented (warm)
      overlayCtx.fillStyle = "rgba(255,123,0,0.95)";
      overlayCtx.fillRect(260, 94, 18, 18);
      overlayCtx.fillStyle = "rgba(255,255,255,0.92)";
      overlayCtx.fillText("Augmented ▲ above ring", 288, 109);

      // Frequency readout — bottom left, cyan colored
      const hover = hoveredRef.current;
      overlayCtx.shadowColor = "rgba(0, 221, 255, 0.5)";
      overlayCtx.shadowBlur = 12;
      overlayCtx.fillStyle = "rgba(0, 221, 255, 0.95)";
      overlayCtx.font = "700 28px 'JetBrains Mono', 'Courier New', monospace";
      overlayCtx.fillText(`${hover.freqText}`, 22, height - 62);

      // dB readout — colored by side
      overlayCtx.shadowBlur = 0;
      overlayCtx.fillStyle = hover.side === "boost"
        ? "rgba(255,123,0,0.95)"
        : "rgba(76,201,240,0.95)";
      overlayCtx.font = "600 24px 'JetBrains Mono', 'Courier New', monospace";
      overlayCtx.fillText(hover.dbText, 22, height - 34);

      // Side label
      overlayCtx.fillStyle = "rgba(160,175,190,0.5)";
      overlayCtx.font = "500 16px system-ui, sans-serif";
      overlayCtx.fillText(
        hover.side === "boost" ? "▲ augmented" : "▼ missing",
        22, height - 12
      );

      overlayCtx.restore();
    }

    function syncDisplayedFrame() {
      const displayed = displayedFrameRef.current;
      const latest = latestFrameRef.current;
      for (let i = 0; i < NUM_BANDS; i++) {
        displayed[i].db = lerp(displayed[i].db, latest[i].db, 0.16);
        displayed[i].energy = lerp(displayed[i].energy, latest[i].energy, 0.14);
        displayed[i].freq = latest[i].freq;
      }
    }

    function animate() {
      animationRef.current = requestAnimationFrame(animate);
      if (!rendererRef.current) return;

      syncDisplayedFrame();

      const rot = rotationRef.current;
      rot.x = lerp(rot.x, rot.targetX, 0.08);
      rot.y = lerp(rot.y, rot.targetY, 0.08);
      if (!pointerRef.current.isDown && !isPaused) {
        rot.targetY -= 0.0016;
      }

      camera.position.set(
        Math.sin(rot.y) * Math.cos(rot.x) * CAMERA_DISTANCE,
        -Math.sin(rot.x) * CAMERA_DISTANCE,
        Math.cos(rot.y) * Math.cos(rot.x) * CAMERA_DISTANCE,
      );
      // Look at ring center — both up and down bars are equally visible
      camera.lookAt(0, 0, 0);

      // Pulsing ring
      const pulse = 0.45 + Math.sin(performance.now() * 0.0014) * 0.12;
      ring.material.opacity = pulse;
      ringGlow.material.opacity = pulse * 0.25;

      updateBars();
      updateReference();
      renderer.render(scene, camera);
      drawOverlay();
    }

    // === INPUT — full 360° orbit, no clamping ===
    function onPointerDown(clientX, clientY) {
      pointerRef.current.isDown = true;
      pointerRef.current.x = clientX;
      pointerRef.current.y = clientY;
    }

    function onPointerMove(clientX, clientY) {
      if (!pointerRef.current.isDown) return;
      const dx = clientX - pointerRef.current.x;
      const dy = clientY - pointerRef.current.y;
      pointerRef.current.x = clientX;
      pointerRef.current.y = clientY;
      // Swipe right = rotate right, no vertical clamping
      rotationRef.current.targetY -= dx * 0.006;
      rotationRef.current.targetX += dy * 0.0035;
    }

    function onPointerUp() {
      pointerRef.current.isDown = false;
    }

    const canvas = renderer.domElement;
    canvas.addEventListener("mousedown", (e) => onPointerDown(e.clientX, e.clientY));
    canvas.addEventListener("mousemove", (e) => onPointerMove(e.clientX, e.clientY));
    canvas.addEventListener("mouseup", onPointerUp);
    canvas.addEventListener("mouseleave", onPointerUp);
    canvas.addEventListener("touchstart", (e) => {
      const t = e.touches[0];
      onPointerDown(t.clientX, t.clientY);
    }, { passive: true });
    canvas.addEventListener("touchmove", (e) => {
      const t = e.touches[0];
      onPointerMove(t.clientX, t.clientY);
      e.preventDefault();
    }, { passive: false });
    canvas.addEventListener("touchend", onPointerUp);

    // Data update timer — matches firmware live block rate
    let demoTime = 0;
    dataTimerRef.current = window.setInterval(async () => {
      let nextFrame;
      try {
        nextFrame = typeof getLiveData === "function"
          ? await getLiveData()
          : makeDemoFrame((demoTime += 1 / DATA_HZ));
      } catch {
        nextFrame = makeDemoFrame((demoTime += 1 / DATA_HZ));
      }
      latestFrameRef.current = normalizeFrame(nextFrame);
    }, 1000 / DATA_HZ);

    animate();

    return () => {
      if (dataTimerRef.current) window.clearInterval(dataTimerRef.current);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
      renderer.dispose();
      barGeometry.dispose();
      coldMaterial.dispose();
      warmMaterial.dispose();
      ring.geometry.dispose();
      ring.material.dispose();
      ringGlow.geometry.dispose();
      ringGlow.material.dispose();
      dividerGeo.dispose();
      dividerMat.dispose();
      refLineGeo.dispose();
      refLineMat.dispose();
      refDot.geometry.dispose();
      refDot.material.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [getLiveData, height, isPaused, leftAngles, rightAngles, width]);

  return (
    <div
      style={{
        width,
        height,
        position: "relative",
        background: "#000",
        overflow: "hidden",
        borderRadius: 18,
        boxShadow: "0 16px 48px rgba(0,0,0,0.45)",
      }}
    >
      <div
        ref={mountRef}
        style={{ position: "absolute", inset: 0, cursor: "grab" }}
      />
      <canvas
        ref={overlayRef}
        width={width}
        height={height}
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
      />
      <button
        type="button"
        onClick={() => setIsPaused((v) => !v)}
        style={{
          position: "absolute",
          right: 20,
          top: 20,
          zIndex: 5,
          border: "1px solid rgba(255,255,255,0.18)",
          background: "rgba(17,24,39,0.72)",
          color: "#fff",
          borderRadius: 999,
          padding: "10px 16px",
          fontSize: 16,
          backdropFilter: "blur(8px)",
        }}
      >
        {isPaused ? "Resume orbit" : "Pause orbit"}
      </button>
    </div>
  );
}

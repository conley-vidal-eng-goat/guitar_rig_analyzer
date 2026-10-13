import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";

/**
 * WaterfallSpectrum3D.jsx
 *
 * Live 3D waterfall spectrum analyzer for Raspberry Pi 5 + Touch Display 2.
 *
 * Axes:
 *   X = frequency (log scale, 20 Hz → 20 kHz, left to right)
 *   Z = time (newest row at front, scrolling backward into depth)
 *   Y = amplitude (height + color)
 *
 * Color maps to amplitude:
 *   silence → deep blue/black
 *   low     → cool blue/cyan
 *   mid     → green/yellow
 *   hot     → orange/red/white
 *
 * The mesh is a single PlaneGeometry with (FREQ_BINS × TIME_SLICES) vertices.
 * Each frame, the newest spectrum row is written to the front edge and all
 * existing rows shift back by one position. Vertex heights and colors update
 * in place — no geometry allocation per frame.
 *
 * Optimized for Pi 5:
 *   - Single mesh, single draw call
 *   - Vertex buffer updates only (no new geometry)
 *   - Pixel ratio capped at 1
 *   - Data interpolation from ~11 Hz input to smooth 60 FPS rendering
 */

const DISPLAY_WIDTH = 720;
const DISPLAY_HEIGHT = 1280;

const FREQ_BINS = 96;
const TIME_SLICES = 80;

const PLANE_WIDTH = 8;
const PLANE_DEPTH = 10;
const MAX_HEIGHT = 3.0;

const CAMERA_DISTANCE = 12;
const DATA_HZ = 10.8;

const BACKGROUND = new THREE.Color(0x04070b);
const REF_LINE_COLOR = 0x00ddff;

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

// Amplitude color map: dark blue → cyan → green → yellow → red → white
function amplitudeToColor(amp, target) {
  const t = clamp(amp, 0, 1);
  if (t < 0.15) {
    // Near silence: deep blue/black
    const s = t / 0.15;
    target.setRGB(0.02 + s * 0.05, 0.02 + s * 0.08, 0.08 + s * 0.35);
  } else if (t < 0.35) {
    // Low: blue → cyan
    const s = (t - 0.15) / 0.2;
    target.setRGB(0.07, 0.1 + s * 0.55, 0.43 + s * 0.45);
  } else if (t < 0.55) {
    // Mid-low: cyan → green
    const s = (t - 0.35) / 0.2;
    target.setRGB(0.07 + s * 0.15, 0.65 + s * 0.2, 0.88 - s * 0.55);
  } else if (t < 0.72) {
    // Mid: green → yellow
    const s = (t - 0.55) / 0.17;
    target.setRGB(0.22 + s * 0.68, 0.85 + s * 0.1, 0.33 - s * 0.25);
  } else if (t < 0.88) {
    // Hot: yellow → red/orange
    const s = (t - 0.72) / 0.16;
    target.setRGB(0.9 + s * 0.1, 0.95 - s * 0.6, 0.08 - s * 0.04);
  } else {
    // Peak: red → white-hot
    const s = (t - 0.88) / 0.12;
    target.setRGB(1.0, 0.35 + s * 0.6, 0.04 + s * 0.7);
  }
  return target;
}

function generateDemoSpectrum(timeSec) {
  const bins = [];
  for (let i = 0; i < FREQ_BINS; i++) {
    const freq = logFreqAt(i, FREQ_BINS);
    let amp = 0;

    // Simulated guitar spectrum — fundamental + harmonics that shift over time
    const fundamental = 110 + Math.sin(timeSec * 0.3) * 28;
    for (let h = 1; h <= 8; h++) {
      const harmonic = fundamental * h;
      const dist = Math.abs(Math.log2(freq / harmonic));
      if (dist < 0.15) {
        const strength = (1.0 / h) * (0.7 + 0.3 * Math.sin(timeSec * 1.2 + h));
        amp += strength * (1 - dist / 0.15);
      }
    }

    // Some broadband noise floor
    amp += 0.03 + Math.sin(i * 7.3 + timeSec * 2.1) * 0.015;

    // Occasional mid-range resonance sweep
    const sweepFreq = 800 + Math.sin(timeSec * 0.18) * 600;
    const sweepDist = Math.abs(Math.log2(freq / sweepFreq));
    if (sweepDist < 0.3) {
      amp += 0.35 * (1 - sweepDist / 0.3) * (0.5 + 0.5 * Math.sin(timeSec * 0.7));
    }

    bins.push(clamp(amp, 0, 1));
  }
  return bins;
}

export default function WaterfallSpectrum3D({
  getLiveData,
  width = DISPLAY_WIDTH,
  height = DISPLAY_HEIGHT,
}) {
  const mountRef = useRef(null);
  const overlayRef = useRef(null);
  const rendererRef = useRef(null);
  const animRef = useRef(null);
  const dataTimerRef = useRef(null);
  const rotRef = useRef({ x: -0.45, y: -0.3, targetX: -0.45, targetY: -0.3 });
  const pointerRef = useRef({ isDown: false, x: 0, y: 0 });
  const [isPaused, setIsPaused] = useState(false);

  // Rolling buffer of time slices — each is FREQ_BINS floats (0..1 amplitude)
  const historyRef = useRef(null);
  const latestSliceRef = useRef(new Float32Array(FREQ_BINS));
  const displaySliceRef = useRef(new Float32Array(FREQ_BINS));
  const freqReadoutRef = useRef({ freqText: "440 Hz", ampText: "0.00", ampNorm: 0 });

  useEffect(() => {
    const container = mountRef.current;
    const overlayCanvas = overlayRef.current;
    if (!container || !overlayCanvas) return;
    const overlayCtx = overlayCanvas.getContext("2d");

    // Initialize rolling history buffer
    const history = new Float32Array(FREQ_BINS * TIME_SLICES);
    historyRef.current = history;

    const scene = new THREE.Scene();
    scene.background = BACKGROUND;

    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(1);
    renderer.setSize(width, height);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Lighting
    scene.add(new THREE.AmbientLight(0xffffff, 0.5));
    const topLight = new THREE.DirectionalLight(0xffffff, 0.8);
    topLight.position.set(2, 8, 4);
    scene.add(topLight);
    const sideLight = new THREE.DirectionalLight(0x6688aa, 0.3);
    sideLight.position.set(-5, 3, -2);
    scene.add(sideLight);

    // === WATERFALL MESH ===
    // PlaneGeometry with FREQ_BINS segments along X, TIME_SLICES along Z.
    // We'll manipulate vertex Y positions for height and vertex colors for amplitude.
    const planeGeo = new THREE.PlaneGeometry(
      PLANE_WIDTH, PLANE_DEPTH,
      FREQ_BINS - 1, TIME_SLICES - 1
    );
    // Rotate plane to lie flat (XZ plane) — default PlaneGeometry faces +Y
    planeGeo.rotateX(-Math.PI / 2);

    // Initialize vertex colors
    const vertexCount = planeGeo.attributes.position.count;
    const colors = new Float32Array(vertexCount * 3);
    for (let i = 0; i < vertexCount; i++) {
      colors[i * 3] = 0.02;
      colors[i * 3 + 1] = 0.02;
      colors[i * 3 + 2] = 0.08;
    }
    planeGeo.setAttribute("color", new THREE.BufferAttribute(colors, 3));

    const planeMat = new THREE.MeshStandardMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      roughness: 0.5,
      metalness: 0.1,
    });
    const waterfall = new THREE.Mesh(planeGeo, planeMat);
    // Center the mesh: front edge (newest) at z = PLANE_DEPTH/2
    waterfall.position.set(0, 0, 0);
    scene.add(waterfall);

    // === GRID LINES on the floor for spatial reference ===
    const gridGeo = new THREE.PlaneGeometry(PLANE_WIDTH + 1, PLANE_DEPTH + 1, 12, 10);
    gridGeo.rotateX(-Math.PI / 2);
    const gridMat = new THREE.MeshBasicMaterial({
      color: 0x1a2535,
      wireframe: true,
      transparent: true,
      opacity: 0.15,
    });
    const grid = new THREE.Mesh(gridGeo, gridMat);
    grid.position.y = -0.02;
    scene.add(grid);

    // === CYAN REFERENCE LINE — vertical line at a frequency position ===
    const refLineGeo = new THREE.CylinderGeometry(0.025, 0.025, MAX_HEIGHT * 1.2, 6);
    const refLineMat = new THREE.MeshBasicMaterial({
      color: REF_LINE_COLOR, transparent: true, opacity: 0.7,
    });
    const refLine = new THREE.Mesh(refLineGeo, refLineMat);
    scene.add(refLine);

    // Cyan dot at the base
    const refDot = new THREE.Mesh(
      new THREE.SphereGeometry(0.06, 10, 10),
      new THREE.MeshBasicMaterial({ color: 0x00ffee })
    );
    scene.add(refDot);

    // === FREQUENCY AXIS LABELS — positioned along the front edge ===
    // (rendered on the 2D overlay instead of 3D text for performance)

    const positions = planeGeo.attributes.position;
    const colorAttr = planeGeo.attributes.color;
    const tmpColor = new THREE.Color();

    function pushNewSlice() {
      // Shift all rows back by one: row[t] = row[t-1]
      // Row 0 = front (newest), row TIME_SLICES-1 = back (oldest)
      history.copyWithin(FREQ_BINS, 0, FREQ_BINS * (TIME_SLICES - 1));
      // Write newest slice to row 0
      history.set(displaySliceRef.current, 0);
    }

    function updateMeshFromHistory() {
      for (let t = 0; t < TIME_SLICES; t++) {
        for (let f = 0; f < FREQ_BINS; f++) {
          const vertIdx = t * FREQ_BINS + f;
          const amp = history[t * FREQ_BINS + f];
          const h = amp * MAX_HEIGHT;

          // Update Y position (height)
          positions.setY(vertIdx, h);

          // Update color
          amplitudeToColor(amp, tmpColor);
          colorAttr.setXYZ(vertIdx, tmpColor.r, tmpColor.g, tmpColor.b);
        }
      }
      positions.needsUpdate = true;
      colorAttr.needsUpdate = true;
      planeGeo.computeVertexNormals();
    }

    function updateReference() {
      // Reference line sits at the front edge of the waterfall,
      // at the X position closest to the camera's viewing angle
      const camXZ = new THREE.Vector2(camera.position.x, camera.position.z);
      if (camXZ.lengthSq() < 1e-6) return;

      // Project camera direction onto the frequency axis (X)
      // The front edge runs along X from -PLANE_WIDTH/2 to +PLANE_WIDTH/2
      // Map camera X position to the nearest frequency bin
      const halfW = PLANE_WIDTH / 2;
      const frontZ = PLANE_DEPTH / 2;

      // Use camera X to determine which frequency we're pointing at
      const camAngle = Math.atan2(camera.position.x, camera.position.z);
      const projX = Math.sin(camAngle) * halfW * 1.5;
      const clampedX = clamp(projX, -halfW, halfW);

      // Map X position to frequency bin
      const binT = (clampedX + halfW) / PLANE_WIDTH;
      const binIndex = clamp(Math.round(binT * (FREQ_BINS - 1)), 0, FREQ_BINS - 1);
      const freq = logFreqAt(binIndex, FREQ_BINS);

      // Position the reference line at the front edge
      const xPos = -halfW + (binIndex / (FREQ_BINS - 1)) * PLANE_WIDTH;
      const amp = displaySliceRef.current[binIndex];
      const lineY = MAX_HEIGHT * 0.6;
      refLine.position.set(xPos, lineY, frontZ);
      refDot.position.set(xPos, 0.01, frontZ);

      freqReadoutRef.current = {
        freqText: formatFreq(freq),
        ampText: (amp * 100).toFixed(0) + "%",
        ampNorm: amp,
      };
    }

    function drawOverlay() {
      overlayCtx.clearRect(0, 0, width, height);
      overlayCtx.save();

      // Title
      overlayCtx.fillStyle = "rgba(255,255,255,0.92)";
      overlayCtx.font = "600 34px system-ui, sans-serif";
      overlayCtx.fillText("Waterfall Spectrum", 22, 44);

      // Subtitle
      overlayCtx.fillStyle = "rgba(180,195,210,0.7)";
      overlayCtx.font = "500 17px system-ui, sans-serif";
      overlayCtx.fillText("Frequency × Time × Amplitude  ·  newest at front", 22, 70);

      // Color scale legend
      const legendX = 22;
      const legendY = 92;
      const legendW = 200;
      const legendH = 14;
      const grad = overlayCtx.createLinearGradient(legendX, 0, legendX + legendW, 0);
      grad.addColorStop(0.0, "#060818");
      grad.addColorStop(0.2, "#1466aa");
      grad.addColorStop(0.4, "#14aacc");
      grad.addColorStop(0.55, "#40cc50");
      grad.addColorStop(0.7, "#ddcc22");
      grad.addColorStop(0.85, "#ee5500");
      grad.addColorStop(1.0, "#ffccaa");
      overlayCtx.fillStyle = grad;
      overlayCtx.fillRect(legendX, legendY, legendW, legendH);

      overlayCtx.fillStyle = "rgba(160,175,190,0.6)";
      overlayCtx.font = "500 12px system-ui, sans-serif";
      overlayCtx.fillText("quiet", legendX, legendY + 26);
      overlayCtx.textAlign = "right";
      overlayCtx.fillText("loud", legendX + legendW, legendY + 26);
      overlayCtx.textAlign = "left";

      // Frequency readout — bottom left, cyan
      const info = freqReadoutRef.current;
      overlayCtx.shadowColor = "rgba(0, 221, 255, 0.5)";
      overlayCtx.shadowBlur = 12;
      overlayCtx.fillStyle = "rgba(0, 221, 255, 0.95)";
      overlayCtx.font = "700 28px 'JetBrains Mono', 'Courier New', monospace";
      overlayCtx.fillText(info.freqText, 22, height - 52);

      overlayCtx.shadowBlur = 0;
      amplitudeToColor(info.ampNorm, tmpColor);
      const ampColorStr = `rgb(${Math.round(tmpColor.r * 255)},${Math.round(tmpColor.g * 255)},${Math.round(tmpColor.b * 255)})`;
      overlayCtx.fillStyle = ampColorStr;
      overlayCtx.font = "600 22px 'JetBrains Mono', 'Courier New', monospace";
      overlayCtx.fillText(`amplitude: ${info.ampText}`, 22, height - 26);

      overlayCtx.restore();
    }

    // Smooth incoming data
    function syncDisplaySlice() {
      const displayed = displaySliceRef.current;
      const latest = latestSliceRef.current;
      for (let i = 0; i < FREQ_BINS; i++) {
        displayed[i] = lerp(displayed[i], latest[i], 0.22);
      }
    }

    let sliceAccum = 0;

    function animate() {
      animRef.current = requestAnimationFrame(animate);
      if (!rendererRef.current) return;

      syncDisplaySlice();

      // Push a new row at the data rate, not every render frame
      sliceAccum += 1 / 60;
      if (sliceAccum >= 1 / DATA_HZ) {
        sliceAccum -= 1 / DATA_HZ;
        pushNewSlice();
      }

      updateMeshFromHistory();

      // Camera orbit
      const rot = rotRef.current;
      rot.x = lerp(rot.x, rot.targetX, 0.07);
      rot.y = lerp(rot.y, rot.targetY, 0.07);
      if (!pointerRef.current.isDown && !isPaused) {
        rot.targetY -= 0.0008;
      }

      camera.position.set(
        Math.sin(rot.y) * Math.cos(rot.x) * CAMERA_DISTANCE,
        -Math.sin(rot.x) * CAMERA_DISTANCE,
        Math.cos(rot.y) * Math.cos(rot.x) * CAMERA_DISTANCE,
      );
      camera.lookAt(0, 0.5, 0);

      updateReference();
      renderer.render(scene, camera);
      drawOverlay();
    }

    // Input — full orbit
    function onPointerDown(cx, cy) {
      pointerRef.current = { isDown: true, x: cx, y: cy };
    }
    function onPointerMove(cx, cy) {
      if (!pointerRef.current.isDown) return;
      const dx = cx - pointerRef.current.x;
      const dy = cy - pointerRef.current.y;
      pointerRef.current.x = cx;
      pointerRef.current.y = cy;
      rotRef.current.targetY -= dx * 0.006;
      rotRef.current.targetX += dy * 0.004;
    }
    function onPointerUp() {
      pointerRef.current.isDown = false;
    }

    const canvas = renderer.domElement;
    canvas.addEventListener("mousedown", e => onPointerDown(e.clientX, e.clientY));
    canvas.addEventListener("mousemove", e => onPointerMove(e.clientX, e.clientY));
    canvas.addEventListener("mouseup", onPointerUp);
    canvas.addEventListener("mouseleave", onPointerUp);
    canvas.addEventListener("touchstart", e => {
      const t = e.touches[0]; onPointerDown(t.clientX, t.clientY);
    }, { passive: true });
    canvas.addEventListener("touchmove", e => {
      e.preventDefault();
      const t = e.touches[0]; onPointerMove(t.clientX, t.clientY);
    }, { passive: false });
    canvas.addEventListener("touchend", onPointerUp);

    // Data input timer
    let demoTime = 0;
    dataTimerRef.current = window.setInterval(async () => {
      let spectrum;
      try {
        spectrum = typeof getLiveData === "function"
          ? await getLiveData()
          : generateDemoSpectrum((demoTime += 1 / DATA_HZ));
      } catch {
        spectrum = generateDemoSpectrum((demoTime += 1 / DATA_HZ));
      }
      // Normalize to FREQ_BINS if needed
      const slice = latestSliceRef.current;
      const srcLen = spectrum.length;
      for (let i = 0; i < FREQ_BINS; i++) {
        const srcIdx = Math.round((i / (FREQ_BINS - 1)) * (srcLen - 1));
        slice[i] = clamp(spectrum[srcIdx] ?? 0, 0, 1);
      }
    }, 1000 / DATA_HZ);

    animate();

    return () => {
      if (dataTimerRef.current) window.clearInterval(dataTimerRef.current);
      if (animRef.current) cancelAnimationFrame(animRef.current);
      renderer.dispose();
      planeGeo.dispose();
      planeMat.dispose();
      gridGeo.dispose();
      gridMat.dispose();
      refLineGeo.dispose();
      refLineMat.dispose();
      refDot.geometry.dispose();
      refDot.material.dispose();
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement);
    };
  }, [getLiveData, width, height, isPaused]);

  return (
    <div style={{
      width, height, position: "relative", background: "#000",
      overflow: "hidden", borderRadius: 18,
      boxShadow: "0 16px 48px rgba(0,0,0,0.45)",
    }}>
      <div ref={mountRef} style={{ position: "absolute", inset: 0, cursor: "grab" }} />
      <canvas ref={overlayRef} width={width} height={height}
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }} />
      <button
        type="button"
        onClick={() => setIsPaused(v => !v)}
        style={{
          position: "absolute", right: 20, top: 20, zIndex: 5,
          border: "1px solid rgba(255,255,255,0.18)",
          background: "rgba(17,24,39,0.72)", color: "#fff",
          borderRadius: 999, padding: "10px 16px", fontSize: 16,
          backdropFilter: "blur(8px)",
        }}
      >
        {isPaused ? "Resume" : "Pause"}
      </button>
    </div>
  );
}

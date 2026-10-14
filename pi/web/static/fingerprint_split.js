// ToneFingerprintSplit — ported from the committed concept (visual_design_document
// §1c) to a plain ES module. Geometry, arcs, colours, InstancedMesh batching and
// camera behaviour follow the original; what changed is the DATA CONTRACT.
//
// *** WHAT THIS RENDERER IS NOT ALLOWED TO DO (ADR-005) ***
//
//   - It receives bands that are ALREADY CLASSIFIED. It has no coverage nibbles,
//     no NaNs and no raw arrays, so it cannot classify even by accident.
//   - It draws NOTHING for an UNMEASURED band. Not a stub, not a zero, not a
//     faint hint. The original drew a 0.02 stub for the inactive side; that was
//     fine for synthetic data where every band had a value, and is wrong here.
//   - Bars are discrete per band. There is no surface, no spline and no
//     neighbour blending, so nothing can bridge an absent band.
//   - Frame-to-frame easing applies only while a band stays MEASURED. A class
//     change snaps, so a band can never ease THROUGH a state it was never in.
//
// VISUAL MAPPING
//   MEASURED      solid bar. db<0 -> left arc, drops below ring, cold cyan.
//                 db>0 -> right arc, rises above ring, warm orange.
//                 Bar thickness tracks coverage: a band resting on 1 of 4
//                 sources is visibly thinner than one resting on 4 of 4.
//   CLAMPED       flat amber disc ON the ring. No height -- the rail is not a
//                 magnitude anyone may read.
//   INDETERMINATE hollow amber wireframe marker ON the ring, at BOTH arc
//                 positions. The band has no established direction, so it is
//                 not placed on the loss side or the gain side.
//   UNMEASURED    nothing.

import * as THREE from "./vendor/three.module.js";

const NUM_BANDS = 48;
const DISC_RADIUS = 3.15;
const MAX_BAR_HEIGHT = 4.2;
const MAX_DB = 18;
const BAR_RADIUS_BASE = 0.035;
const BAR_RADIUS_GAIN = 0.05;
const CAMERA_FOV = 52;
// The ring plus a margin must fit the NARROW axis. On 720x1280 portrait that is
// the horizontal one, so a distance tuned on a landscape mock crops the ring.
const FIT_RADIUS = DISC_RADIUS * 1.28;

const LEFT_START = Math.PI * 0.62;
const LEFT_END = Math.PI * 1.38;
const RIGHT_START = -Math.PI * 0.38;
const RIGHT_END = Math.PI * 0.38;

const RING_GLOW_COLOR = 0x38506b;      // §1c reference implementation
const COLD_EMISSIVE = 0x0f2230;        // §1c reference implementation
const WARM_EMISSIVE = 0x331400;        // §1c reference implementation
// Two easing channels, per §1c: height at 0.16 and bar thickness at 0.14. The
// second was not ported, so coverage changes snapped while height eased.
const EASE_HEIGHT = 0.16;
const EASE_COVERAGE = 0.14;

const COLD_COLOR = new THREE.Color("#4cc9f0");
const COLD_ALERT_COLOR = new THREE.Color("#90e0ef");
const WARM_COLOR = new THREE.Color("#ff7b00");
const WARM_ALERT_COLOR = new THREE.Color("#ffd166");
const RING_COLOR = new THREE.Color("#9fb3c8");
const UNKNOWN_COLOR = new THREE.Color("#d29922");   // amber: "not established"
const BACKGROUND_COLOR = new THREE.Color(0x04070b);

const lerp = (a, b, t) => a + (b - a) * t;

function bandAngles(start, end) {
  const out = [];
  for (let i = 0; i < NUM_BANDS; i++) {
    out.push(lerp(start, end, NUM_BANDS === 1 ? 0 : i / (NUM_BANDS - 1)));
  }
  return out;
}

function colorForMagnitude(magnitude, side) {
  const t = Math.min(1, magnitude / MAX_DB);
  return side === "missing"
    ? COLD_COLOR.clone().lerp(COLD_ALERT_COLOR, t)
    : WARM_COLOR.clone().lerp(WARM_ALERT_COLOR, t);
}

export function createFingerprint(container) {
  const scene = new THREE.Scene();
  scene.background = BACKGROUND_COLOR;

  const camera = new THREE.PerspectiveCamera(CAMERA_FOV, 1, 0.1, 200);
  const halfFov = (CAMERA_FOV * Math.PI) / 180 / 2;
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(1);               // embedded GPU, per the design doc
  container.appendChild(renderer.domElement);

  // *** TODO-80: THE VIEWPORT IS NOT KNOWN AT CONSTRUCTION TIME. ***
  //
  // This used to read container.clientWidth/clientHeight once, here, and derive
  // both the camera aspect and the orbit distance from them. On the Pi that is
  // wrong, and it was wrong invisibly: Chromium's Wayland surface is created at
  // a provisional size and resized when the compositor assigns the output.
  // Measured on the panel 2026-10-12 — at load 668x392, on resize 720x1280. So
  // the ring was fitted to a viewport that never existed and then displayed at
  // one it had never seen.
  //
  // A macOS window is sized before first paint, which is why months of desktop
  // work could not surface this. Size is therefore now a FUNCTION, called on
  // construction, on every container resize, and again whenever the view is
  // shown after being hidden (a display:none container measures 0 x 0).
  let cameraDistance = 1;
  let lastW = 0;
  let lastH = 0;

  function resize() {
    const w = container.clientWidth;
    const h = container.clientHeight;
    // A hidden or not-yet-laid-out container measures zero. Fitting to that
    // would divide by zero and bake a NaN into the camera matrix, so the only
    // safe action is to do nothing and wait to be called again.
    if (w <= 0 || h <= 0) return false;
    if (w === lastW && h === lastH) return false;
    lastW = w;
    lastH = h;

    const aspect = w / h;
    camera.aspect = aspect;
    camera.updateProjectionMatrix();
    // The ring plus a margin must fit the NARROW axis, whichever that is now.
    cameraDistance = FIT_RADIUS / (Math.tan(halfFov) * Math.min(aspect, 1));
    renderer.setSize(w, h, false);
    return true;
  }

  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const key = new THREE.PointLight(0xdfe9ff, 0.8, 60);
  key.position.set(0, 12, 6);
  scene.add(key);
  const under = new THREE.PointLight(0x5fa8d3, 0.5, 60);
  under.position.set(0, -12, 0);
  scene.add(under);

  // Baseline ring — the zero reference. It is NOT data and never varies with it.
  //
  // The design document calls for a "thin white PULSING torus (same heartbeat as
  // other versions)" (visual_design_document.md §1c) with a wider, dimmer glow
  // behind it. Both were specified and neither was ported; restored 2026-10-13
  // against concepts/ToneFingerprintSplit.jsx. The pulse is a property of the
  // REFERENCE, not of the data — it must never be driven by a measurement, or a
  // reader could mistake the instrument's heartbeat for the instrument's signal.
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(DISC_RADIUS, 0.025, 10, 160),
    new THREE.MeshBasicMaterial({ color: RING_COLOR, transparent: true, opacity: 0.75 })
  );
  ring.rotation.x = Math.PI / 2;
  scene.add(ring);

  const ringGlow = new THREE.Mesh(
    new THREE.TorusGeometry(DISC_RADIUS, 0.075, 8, 128),
    new THREE.MeshBasicMaterial({ color: RING_GLOW_COLOR, transparent: true,
                                 opacity: 0.18, depthWrite: false })
  );
  ringGlow.rotation.x = Math.PI / 2;
  scene.add(ringGlow);

  const divider = new THREE.Mesh(
    new THREE.CylinderGeometry(0.012, 0.012, DISC_RADIUS * 2.25, 8),
    new THREE.MeshBasicMaterial({ color: RING_COLOR, transparent: true, opacity: 0.3 })
  );
  divider.rotation.z = Math.PI / 2;
  scene.add(divider);

  const leftAngles = bandAngles(LEFT_START, LEFT_END);
  const rightAngles = bandAngles(RIGHT_START, RIGHT_END);

  const barGeo = new THREE.CylinderGeometry(1, 1, 1, 10, 1, false);
  // `emissive` is specified by the reference implementation and was not ported.
  // Without it the bars are lit only by the two scene lights and read flat when a
  // band faces away from the key light. It is a constant self-illumination, so it
  // cannot encode a value and cannot vary with one.
  const coldMat = new THREE.MeshLambertMaterial({ color: COLD_COLOR, emissive: COLD_EMISSIVE });
  const warmMat = new THREE.MeshLambertMaterial({ color: WARM_COLOR, emissive: WARM_EMISSIVE });
  const missingBars = new THREE.InstancedMesh(barGeo, coldMat, NUM_BANDS);
  const boostBars = new THREE.InstancedMesh(barGeo, warmMat, NUM_BANDS);
  for (const m of [missingBars, boostBars]) {
    m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    m.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(NUM_BANDS * 3), 3);
    scene.add(m);
  }

  // Unknown markers: one per band per side, hollow, sitting on the ring plane.
  const markerGeo = new THREE.TorusGeometry(0.17, 0.035, 8, 24);
  const markerMat = new THREE.MeshBasicMaterial({ color: UNKNOWN_COLOR });
  const markers = new THREE.InstancedMesh(markerGeo, markerMat, NUM_BANDS * 2);
  markers.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  scene.add(markers);

  const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);
  const mat4 = new THREE.Matrix4();
  const pos = new THREE.Vector3();
  const scl = new THREE.Vector3();
  const quat = new THREE.Quaternion();
  const flat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);

  // Eased bar heights, and the class each was eased under. A class change snaps.
  const eased = new Array(NUM_BANDS).fill(0);
  const easedCov = new Array(NUM_BANDS).fill(1);
  const easedCls = new Array(NUM_BANDS).fill("UNMEASURED");

  let segments = [];

  function placeBar(mesh, i, angle, height, radius, below, color) {
    const y = height === 0 ? 0 : (below ? -(height / 2 + 0.01) : height / 2 + 0.01);
    pos.set(Math.cos(angle) * (DISC_RADIUS * 0.92), y, -Math.sin(angle) * (DISC_RADIUS * 0.92));
    quat.identity();
    scl.set(radius, height, radius);
    mesh.setMatrixAt(i, mat4.compose(pos, quat, scl));
    mesh.setColorAt(i, color);
  }

  function update() {
    let marker = 0;
    for (let i = 0; i < NUM_BANDS; i++) {
      const seg = segments[i];
      const cls = seg ? seg.cls : "UNMEASURED";

      // --- UNMEASURED and CLAMPED produce no bar on either side -------------
      if (cls !== "MEASURED") {
        eased[i] = 0;
        easedCls[i] = cls;
        missingBars.setMatrixAt(i, HIDDEN);
        boostBars.setMatrixAt(i, HIDDEN);
      } else {
        const db = seg.value;
        const magnitude = Math.abs(db);
        const target = Math.max(0.03, (magnitude / MAX_DB) * MAX_BAR_HEIGHT);
        // Ease only while the class is unchanged; otherwise snap. A band must
        // never animate through a magnitude it never had.
        eased[i] = easedCls[i] === "MEASURED" ? lerp(eased[i], target, EASE_HEIGHT) : target;

        const cov = seg.coverage ?? 1;
        easedCov[i] = easedCls[i] === "MEASURED"
          ? lerp(easedCov[i], cov, EASE_COVERAGE) : cov;
        easedCls[i] = "MEASURED";

        const radius = BAR_RADIUS_BASE + easedCov[i] * BAR_RADIUS_GAIN;
        const below = db < 0;
        const color = colorForMagnitude(magnitude, below ? "missing" : "boost");
        if (below) {
          placeBar(missingBars, i, leftAngles[i], eased[i], radius, true, color);
          boostBars.setMatrixAt(i, HIDDEN);
        } else {
          placeBar(boostBars, i, rightAngles[i], eased[i], radius, false, color);
          missingBars.setMatrixAt(i, HIDDEN);
        }
      }

      // --- markers for values that exist but are not established ------------
      if (cls === "INDETERMINATE" || cls === "CLAMPED") {
        for (const a of [leftAngles[i], rightAngles[i]]) {
          pos.set(Math.cos(a) * (DISC_RADIUS * 0.92), 0.02, -Math.sin(a) * (DISC_RADIUS * 0.92));
          scl.set(1, 1, 1);
          markers.setMatrixAt(marker++, mat4.compose(pos, flat, scl));
        }
      }
    }
    for (let m = marker; m < NUM_BANDS * 2; m++) markers.setMatrixAt(m, HIDDEN);

    missingBars.instanceMatrix.needsUpdate = true;
    boostBars.instanceMatrix.needsUpdate = true;
    markers.instanceMatrix.needsUpdate = true;
    if (missingBars.instanceColor) missingBars.instanceColor.needsUpdate = true;
    if (boostBars.instanceColor) boostBars.instanceColor.needsUpdate = true;
  }

  let yaw = 0.0, pitch = -0.42, spin = true;
  let dragging = false, lastX = 0, lastY = 0;
  const el = renderer.domElement;
  const down = (x, y) => { dragging = true; spin = false; lastX = x; lastY = y; };
  const move = (x, y) => {
    if (!dragging) return;
    yaw -= (x - lastX) * 0.008;
    pitch += (y - lastY) * 0.005;
    lastX = x; lastY = y;
  };
  el.addEventListener("mousedown", e => down(e.clientX, e.clientY));
  window.addEventListener("mouseup", () => { dragging = false; });
  window.addEventListener("mousemove", e => move(e.clientX, e.clientY));
  el.addEventListener("touchstart", e => down(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
  window.addEventListener("touchend", () => { dragging = false; });
  el.addEventListener("touchmove", e => { e.preventDefault(); move(e.touches[0].clientX, e.touches[0].clientY); }, { passive: false });

  let rafId = 0;

  function draw() {
    // The reference's heartbeat: opacity 0.45 +/- 0.12 at ~0.22 Hz, with the glow
    // tracking it at a quarter depth. Driven by the wall clock, never by data.
    const pulse = 0.45 + Math.sin(performance.now() * 0.0014) * 0.12;
    ring.material.opacity = pulse;
    ringGlow.material.opacity = pulse * 0.25;

    camera.position.set(
      Math.sin(yaw) * Math.cos(pitch) * cameraDistance,
      -Math.sin(pitch) * cameraDistance,
      Math.cos(yaw) * Math.cos(pitch) * cameraDistance
    );
    camera.lookAt(0, 0, 0);
    update();
    renderer.render(scene, camera);
  }

  function frame() {
    if (spin) yaw -= 0.0016;
    draw();
    rafId = requestAnimationFrame(frame);
  }

  // The compositor can resize this surface at any time, not only at startup —
  // a rotated output or a different kiosk geometry is the same event. Observing
  // the container covers both, and costs nothing while the size is stable.
  if (typeof ResizeObserver === "function") {
    new ResizeObserver(() => { if (resize() && !rafId) draw(); }).observe(container);
  }
  window.addEventListener("resize", () => { if (resize() && !rafId) draw(); });

  resize();
  rafId = requestAnimationFrame(frame);

  return {
    setSegments(next) { segments = next || []; },
    renderOnce() { resize(); update(); renderer.render(scene, camera); },

    // Paused means no rAF at all, not a loop that returns early: an idle
    // callback 60 times a second is still the GPU being asked to wake up.
    pause() {
      if (!rafId) return;
      cancelAnimationFrame(rafId);
      rafId = 0;
    },
    resume() {
      if (rafId) return;
      rafId = requestAnimationFrame(frame);
    },
    resize,
  };
}

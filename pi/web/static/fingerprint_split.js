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

// *** THE RING SHOWS A WINDOW, NOT THE WHOLE SPECTRUM (2026-10-15) ***
//
// The 48 bands span 21.5 Hz - 18.6 kHz at 2.47 semitones each. A guitar's six
// open strings (E2 82.4 Hz -> E4 329.6 Hz) occupy 9 of them, so the instrument
// was drawing the player's entire fundamental range across 19% of the circle
// and the rest of the ring was permanently empty.
//
// So the ring is WINDOWED: VIEW_BANDS consecutive bands starting at
// VIEW_BAND_LO, spread over the full arcs. Bands outside the window are not
// drawn and not summarised -- the census line already states full coverage, and
// a window that silently folded outside energy into its edges would be
// inventing a measurement.
//
// 🛑 THE WINDOW IS FIXED, DELIBERATELY. An auto-zoom that followed the data
// would change the meaning of a position between two frames, so two moments
// could not be compared -- and comparing two moments is the entire point of
// this instrument. If the window changes it changes because a human changed it.
const VIEW_BAND_LO = 8;                // ~68 Hz
const VIEW_BANDS = 16;                 // ~68 Hz .. ~574 Hz, covering E2..D5

const DISC_RADIUS = 3.15;

// *** TODO-88 CLOSED HERE: THE TALLEST DRAWABLE BAR NOW FITS THE FRAME. ***
//
// This was 4.2, and `target` had no upper clamp, so the firmware's ±24 dB rail
// could ask for (24/18)·4.2 = 5.6 — a third beyond the constant that named
// itself the maximum. Bars ran off the bottom of the panel (observed
// 2026-10-13) and the camera fit contained only the ring.
//
// Two changes make it bounded: magnitude is clamped to MAX_DB before scaling,
// and this constant is sized so the bar TIP sits inside the orbit-invariant
// bounding sphere the camera actually contains. With DISC_RADIUS 3.15, FOV 52,
// 720x1280 and FIT_RADIUS = DISC_RADIUS·1.28, that sphere is 3.888 and the bar
// ring sits at 2.983, leaving 2.494 of height. 2.3 + the 0.16 cap = 2.46.
//
// 🔺 The ring was NOT shrunk to achieve this, which was the alternative and
// would have worked against the complaint that prompted the work.
const MAX_BAR_HEIGHT = 2.3;

// Full bar length. Was 18 dB, which made a 1 dB change 5.5% of the bar and
// therefore invisible on the panel -- the "blips" the operator reported. 12 dB
// keeps the mapping LINEAR (bar length is proportional to |dB|, which is what
// the legend promises) while making ordinary rig changes legible.
const MAX_DB = 12;

// Any MEASURED band is drawn at least this tall. "The instrument measured this
// band" is itself information, and a bar too short to see loses it. Above this
// floor, length is linear in dB.
//
// 🛑 THE FLOOR IS A VISIBILITY MINIMUM, NOT A MAGNITUDE. Nothing may read a
// bar at the floor as "about 0.9 dB" -- it means "measured, and small". The
// legend says so.
const MIN_BAR_HEIGHT = 0.32;

// A bar longer than the scale is drawn at full length and CAPPED with a marker,
// never silently truncated -- a clipped bar that looks like a maximum would be
// a magnitude the instrument never reported.
const OVER_RANGE_MARK = 0.16;

// --- decay trail -------------------------------------------------------------
//
// Bars persist after the note stops, darkening to black, so a decaying note
// leaves a visible history instead of vanishing between polls.
//
// 🛑 A HELD BAR IS NOT A CURRENT MEASUREMENT, and must never read as one. The
// trail darkens monotonically to black and is drawn THINNER than the live bar,
// so "now" is always the brightest and thickest thing at a given angle. The
// legend states it.
const TRAIL_MS = 7000;                 // operator's choice: 6-7 s
const TRAIL_SAMPLE_MS = 350;           // 20 slots over the lifetime
const TRAIL_SLOTS = Math.ceil(TRAIL_MS / TRAIL_SAMPLE_MS);
const TRAIL_RADIUS_SCALE = 0.62;       // thinner than live, so "now" reads first

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
  for (let i = 0; i < VIEW_BANDS; i++) {
    out.push(lerp(start, end, VIEW_BANDS === 1 ? 0 : i / (VIEW_BANDS - 1)));
  }
  return out;
}

// Short, unambiguous frequency text. "82" and "1.2k" rather than "82.4 Hz" --
// the unit is stated once in the legend and repeating it 32 times around a
// 720 px panel costs legibility for nothing.
function hzLabel(hz) {
  if (!(hz > 0)) return "";
  if (hz < 1000) return String(Math.round(hz));
  return (hz / 1000).toFixed(hz < 10000 ? 1 : 0) + "k";
}

// A sprite carrying canvas text. Sprites always face the camera, which is what
// keeps a label readable while the ring orbits -- DOM overlays cannot track a
// rotating 3D position without reprojecting every frame.
// The canvas is rendered at FONT px for sharpness and then scaled DOWN into
// world units. The two numbers are independent: FONT controls crispness,
// LABEL_SCALE controls size on screen. 0.0085 was the first attempt and put 32
// labels at ~0.65 world units each around a 3.15 ring — they collided into an
// unreadable wall (headless render, 2026-10-15).
const LABEL_SCALE = 0.0030;

function makeLabelSprite(text, { dim = false } = {}) {
  const PAD = 6, FONT = 42;
  const c = document.createElement("canvas");
  const g = c.getContext("2d");
  g.font = `600 ${FONT}px ui-monospace, Menlo, monospace`;
  const w = Math.ceil(g.measureText(text).width) + PAD * 2;
  c.width = w; c.height = FONT + PAD * 2;
  const g2 = c.getContext("2d");
  g2.font = `600 ${FONT}px ui-monospace, Menlo, monospace`;
  g2.textBaseline = "middle";
  g2.fillStyle = dim ? "#7d6a3a" : "#9db0c4";
  g2.fillText(text, PAD, c.height / 2);
  const tex = new THREE.CanvasTexture(c);
  tex.minFilter = THREE.LinearFilter;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, transparent: true, depthWrite: false, depthTest: false,
  }));
  sp.scale.set(c.width * LABEL_SCALE, c.height * LABEL_SCALE, 1);
  return sp;
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
  const missingBars = new THREE.InstancedMesh(barGeo, coldMat, VIEW_BANDS);
  const boostBars = new THREE.InstancedMesh(barGeo, warmMat, VIEW_BANDS);
  for (const m of [missingBars, boostBars]) {
    m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    m.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(VIEW_BANDS * 3), 3);
    scene.add(m);
  }

  // Trail meshes. Unlit (MeshBasic) on purpose: a decayed bar must darken toward
  // black predictably, and a Lambert surface would brighten again whenever the
  // orbit carried it past the key light -- history that flickers back to life.
  const TRAIL_N = VIEW_BANDS * TRAIL_SLOTS;
  const trailMat = () => new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.9 });
  const coldTrail = new THREE.InstancedMesh(barGeo, trailMat(), TRAIL_N);
  const warmTrail = new THREE.InstancedMesh(barGeo, trailMat(), TRAIL_N);
  for (const m of [coldTrail, warmTrail]) {
    m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    m.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(TRAIL_N * 3), 3);
    scene.add(m);
  }

  // Over-range caps: shown only when |dB| exceeds the scale, so a bar pinned at
  // full length can never be mistaken for a value of exactly MAX_DB.
  const capGeo = new THREE.ConeGeometry(0.085, OVER_RANGE_MARK, 8);
  const caps = new THREE.InstancedMesh(
    capGeo, new THREE.MeshBasicMaterial({ color: 0xffffff }), VIEW_BANDS);
  caps.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  scene.add(caps);

  // Unknown markers: one per band per side, hollow, sitting on the ring plane.
  const markerGeo = new THREE.TorusGeometry(0.17, 0.035, 8, 24);
  const markerMat = new THREE.MeshBasicMaterial({ color: UNKNOWN_COLOR });
  const markers = new THREE.InstancedMesh(markerGeo, markerMat, VIEW_BANDS * 2);
  markers.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  scene.add(markers);

  const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);
  const mat4 = new THREE.Matrix4();
  const pos = new THREE.Vector3();
  const scl = new THREE.Vector3();
  const quat = new THREE.Quaternion();
  const flat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);
  const tmpColor = new THREE.Color();

  // Eased bar heights, and the class each was eased under. A class change snaps.
  const eased = new Array(VIEW_BANDS).fill(0);
  const easedCov = new Array(VIEW_BANDS).fill(1);
  const easedCls = new Array(VIEW_BANDS).fill("UNMEASURED");

  // Trail ring buffers, one per displayed band. Flat arrays rather than objects
  // so a 60 Hz sweep over 320 slots allocates nothing.
  const trailH = new Float32Array(TRAIL_N);      // height, 0 = empty slot
  const trailT = new Float64Array(TRAIL_N);      // timestamp
  const trailBelow = new Uint8Array(TRAIL_N);
  const trailR = new Float32Array(TRAIL_N);      // bar radius at capture time
  const trailCol = new Float32Array(TRAIL_N * 3);
  const trailHead = new Uint16Array(VIEW_BANDS);
  let lastTrailSample = 0;

  let segments = [];
  let dcEdgeHz = 0;          // bands centred below this are DC-contaminated
  let labelsBuilt = false;
  const labelSprites = [];

  // Frequency labels, one per displayed band on EACH arc -- a band appears on
  // the left when attenuated and on the right when boosted, so both positions
  // need naming or half the labels would point at nothing.
  function buildLabels() {
    if (labelsBuilt) return;
    labelsBuilt = true;
    for (const sp of labelSprites) scene.remove(sp);
    labelSprites.length = 0;
    for (let d = 0; d < VIEW_BANDS; d++) {
      const seg = segments[VIEW_BAND_LO + d];
      const hz = seg && seg.hz;
      if (!hz) continue;
      const dc = dcEdgeHz > 0 && hz < dcEdgeHz;
      // A DC-contaminated band is labelled with a bullet and dimmed. TODO-92:
      // transmitted bin 0 spans 0-150.73 Hz and contains DC, and LIVE refuses
      // to plot it. The ring still shows it -- marked, not silently.
      const text = (dc ? "•" : "") + hzLabel(hz);
      // Both arcs are labelled -- a band sits on the left when attenuated and on
      // the right when boosted, so labelling one arc would leave half the
      // positions unnamed. Labels sit outside the ring so a full-height bar
      // never crosses one.
      for (const a of [leftAngles[d], rightAngles[d]]) {
        const sp = makeLabelSprite(text, { dim: dc });
        sp.position.set(Math.cos(a) * (DISC_RADIUS * 1.16), 0.06,
                        -Math.sin(a) * (DISC_RADIUS * 1.16));
        scene.add(sp);
        labelSprites.push(sp);
      }
    }
  }

  function placeBar(mesh, i, angle, height, radius, below, color) {
    const y = height === 0 ? 0 : (below ? -(height / 2 + 0.01) : height / 2 + 0.01);
    pos.set(Math.cos(angle) * (DISC_RADIUS * 0.92), y, -Math.sin(angle) * (DISC_RADIUS * 0.92));
    quat.identity();
    scl.set(radius, height, radius);
    mesh.setMatrixAt(i, mat4.compose(pos, quat, scl));
    mesh.setColorAt(i, color);
  }

  function update() {
    const now = performance.now();
    const sampling = now - lastTrailSample >= TRAIL_SAMPLE_MS;
    if (sampling) lastTrailSample = now;

    let marker = 0;
    let cap = 0;
    for (let d = 0; d < VIEW_BANDS; d++) {
      const seg = segments[VIEW_BAND_LO + d];
      const cls = seg ? seg.cls : "UNMEASURED";

      // --- UNMEASURED and CLAMPED produce no bar on either side -------------
      if (cls !== "MEASURED") {
        eased[d] = 0;
        easedCls[d] = cls;
        missingBars.setMatrixAt(d, HIDDEN);
        boostBars.setMatrixAt(d, HIDDEN);
      } else {
        const db = seg.value;
        const magnitude = Math.abs(db);
        // Linear in dB above a visibility floor, so the legend's promise --
        // "bar length is proportional to |dB|" -- stays true everywhere the
        // bar is longer than the floor.
        const over = magnitude > MAX_DB;
        const target = Math.max(
          MIN_BAR_HEIGHT,
          (Math.min(magnitude, MAX_DB) / MAX_DB) * MAX_BAR_HEIGHT);
        // Ease only while the class is unchanged; otherwise snap. A band must
        // never animate through a magnitude it never had.
        eased[d] = easedCls[d] === "MEASURED" ? lerp(eased[d], target, EASE_HEIGHT) : target;

        const cov = seg.coverage ?? 1;
        easedCov[d] = easedCls[d] === "MEASURED"
          ? lerp(easedCov[d], cov, EASE_COVERAGE) : cov;
        easedCls[d] = "MEASURED";

        const radius = BAR_RADIUS_BASE + easedCov[d] * BAR_RADIUS_GAIN;
        const below = db < 0;
        const angle = below ? leftAngles[d] : rightAngles[d];
        const color = colorForMagnitude(magnitude, below ? "missing" : "boost");
        if (below) {
          placeBar(missingBars, d, angle, eased[d], radius, true, color);
          boostBars.setMatrixAt(d, HIDDEN);
        } else {
          placeBar(boostBars, d, angle, eased[d], radius, false, color);
          missingBars.setMatrixAt(d, HIDDEN);
        }

        // Over-range cap at the free end of the bar.
        if (over) {
          const y = below ? -(eased[d] + OVER_RANGE_MARK) : eased[d] + OVER_RANGE_MARK;
          pos.set(Math.cos(angle) * (DISC_RADIUS * 0.92), y,
                  -Math.sin(angle) * (DISC_RADIUS * 0.92));
          quat.identity();
          if (below) quat.setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);
          scl.set(1, 1, 1);
          caps.setMatrixAt(cap++, mat4.compose(pos, quat, scl));
        }

        // --- capture one trail sample -------------------------------------
        if (sampling) {
          const h = trailHead[d];
          const s = d * TRAIL_SLOTS + h;
          trailH[s] = eased[d];
          trailT[s] = now;
          trailBelow[s] = below ? 1 : 0;
          trailR[s] = radius * TRAIL_RADIUS_SCALE;
          trailCol[s * 3] = color.r;
          trailCol[s * 3 + 1] = color.g;
          trailCol[s * 3 + 2] = color.b;
          trailHead[d] = (h + 1) % TRAIL_SLOTS;
        }
      }

      // --- markers for values that exist but are not established ------------
      if (cls === "INDETERMINATE" || cls === "CLAMPED") {
        for (const a of [leftAngles[d], rightAngles[d]]) {
          pos.set(Math.cos(a) * (DISC_RADIUS * 0.92), 0.02, -Math.sin(a) * (DISC_RADIUS * 0.92));
          scl.set(1, 1, 1);
          markers.setMatrixAt(marker++, mat4.compose(pos, flat, scl));
        }
      }
    }
    for (let m = marker; m < VIEW_BANDS * 2; m++) markers.setMatrixAt(m, HIDDEN);
    for (let c = cap; c < VIEW_BANDS; c++) caps.setMatrixAt(c, HIDDEN);

    // --- draw the trail ----------------------------------------------------
    //
    // Age maps to brightness ONLY -- never to height or position. A decayed bar
    // keeps the height it was measured at, so the trail is a record of past
    // magnitudes rather than an animation of a value that never existed.
    let coldN = 0, warmN = 0;
    for (let s = 0; s < TRAIL_N; s++) {
      const h = trailH[s];
      if (h <= 0) continue;
      const age = now - trailT[s];
      if (age >= TRAIL_MS) { trailH[s] = 0; continue; }
      const k = 1 - age / TRAIL_MS;            // 1 = just captured, 0 = black
      const d = (s / TRAIL_SLOTS) | 0;
      const below = trailBelow[s] === 1;
      const angle = below ? leftAngles[d] : rightAngles[d];
      const mesh = below ? coldTrail : warmTrail;
      const idx = below ? coldN++ : warmN++;
      const y = below ? -(h / 2 + 0.01) : h / 2 + 0.01;
      pos.set(Math.cos(angle) * (DISC_RADIUS * 0.92), y,
              -Math.sin(angle) * (DISC_RADIUS * 0.92));
      quat.identity();
      scl.set(trailR[s], h, trailR[s]);
      mesh.setMatrixAt(idx, mat4.compose(pos, quat, scl));
      tmpColor.setRGB(trailCol[s * 3] * k, trailCol[s * 3 + 1] * k, trailCol[s * 3 + 2] * k);
      mesh.setColorAt(idx, tmpColor);
    }
    for (let i = coldN; i < TRAIL_N; i++) coldTrail.setMatrixAt(i, HIDDEN);
    for (let i = warmN; i < TRAIL_N; i++) warmTrail.setMatrixAt(i, HIDDEN);

    missingBars.instanceMatrix.needsUpdate = true;
    boostBars.instanceMatrix.needsUpdate = true;
    coldTrail.instanceMatrix.needsUpdate = true;
    warmTrail.instanceMatrix.needsUpdate = true;
    markers.instanceMatrix.needsUpdate = true;
    caps.instanceMatrix.needsUpdate = true;
    if (missingBars.instanceColor) missingBars.instanceColor.needsUpdate = true;
    if (boostBars.instanceColor) boostBars.instanceColor.needsUpdate = true;
    if (coldTrail.instanceColor) coldTrail.instanceColor.needsUpdate = true;
    if (warmTrail.instanceColor) warmTrail.instanceColor.needsUpdate = true;
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
    setSegments(next) {
      segments = next || [];
      // Labels depend only on the window's centre frequencies, which are fixed
      // for a given geometry -- so they are built once, on the first frame that
      // actually carries them, not rebuilt 20 times a second.
      if (!labelsBuilt && segments.length > VIEW_BAND_LO) buildLabels();
    },

    // The DC edge comes from the frame's own spectrum geometry (the low edge of
    // the first non-DC transmitted bin). Passing it in rather than hardcoding it
    // means the mark follows the instrument if the geometry ever changes.
    setDcEdge(hz) {
      const v = (typeof hz === "number" && isFinite(hz) && hz > 0) ? hz : 0;
      if (v === dcEdgeHz) return;
      dcEdgeHz = v;
      labelsBuilt = false;                  // re-label with the new marking
      if (segments.length > VIEW_BAND_LO) buildLabels();
    },

    // What the legend must describe. Read, never assumed, so the two cannot drift.
    scale() {
      const lo = segments[VIEW_BAND_LO] && segments[VIEW_BAND_LO].hz;
      const hi = segments[VIEW_BAND_LO + VIEW_BANDS - 1]
        && segments[VIEW_BAND_LO + VIEW_BANDS - 1].hz;
      return { maxDb: MAX_DB, trailMs: TRAIL_MS, bands: VIEW_BANDS, loHz: lo, hiHz: hi };
    },

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

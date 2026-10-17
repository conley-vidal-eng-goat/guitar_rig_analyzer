// ToneFingerprintSplit — ported from the committed concept (visual_design_document
// §1c) to a plain ES module. The ring, its pulse and glow, the lights, the
// InstancedMesh batching and the camera behaviour follow the original. What it
// DRAWS was redesigned on 2026-10-16.
//
// *** WHAT THIS RING SHOWS NOW: THE INPUT ON TOP, THE RIG'S RETURN UNDERNEATH ***
//
// Operator's brief, 2026-10-16: "it should be clear what the input signal looks
// like and what the rig return signal looks like and we can compare them
// because they are on top of each other."
//
//   ANGLE       frequency. One section per TRANSMITTED BIN, 151 Hz – 2.9 kHz,
//               lowest at the top, ascending clockwise. Labels are in Hz/kHz
//               and come from the bin geometry the instrument sent.
//   ABOVE       the INPUT — what went into the rig. Warm.
//   BELOW       the RETURN — what came back, LEVEL-MATCHED by the rig gain the
//               view prints as a number. Cool.
//   LENGTH      level above the floor (TF_SOURCE_GATE, -60 dB), linear in dB.
//               It is the volume, so a loud bin is long and a quiet one short.
//   WHITE SEAT  rig-only: the matched return has energy where the input has
//               none — noise or content the rig introduced.
//
// If the rig were a wire, the bottom would be a mirror of the top. The gain
// number says how much level the rig lost or added; the difference between the
// two shapes is what it did to the tone.
//
// *** WHAT THIS RENDERER IS NOT ALLOWED TO DO (ADR-005) ***
//
//   - It receives sections that are ALREADY CLASSIFIED by payload.py
//     (`tone_block`): which channel is above the floor, and which sections are
//     rig-only. It computes geometry from those numbers and nothing else.
//   - A bin quieter than the floor is MEASURED AND QUIET, not absent
//     (`classify_spectrum`). It gets no bar because its length would be zero,
//     and the legend says a dark section is quiet, not unmeasured.
//   - An UNMEASURED channel draws nothing and does not ease — it snaps.
//   - Bars are discrete per bin. No surface, spline or neighbour blending.
//
// *** WHAT WAS REMOVED, AND WHY, SO IT IS NOT RESTORED AS AN IMPROVEMENT ***
//
//   - The chromatic note ring (53 semitones, C2–E6). A transmitted bin is
//     172 Hz wide, so note names asserted a precision the wire does not carry:
//     every guitar fundamental below 151 Hz arrived in ONE bin, and that bin
//     contains DC. Notes return when the firmware sends them (TODO-92, phase 2).
//   - The tf_db mapping. On 2026-10-16 every band read -15..-24 dB against a
//     12 dB scale, so every bar was full length and length meant nothing; the
//     TF also held its last value while the source was gated.
//   - The amber INDETERMINATE/CLAMPED markers and coverage-driven thickness.
//     Both are tf_db properties. A magnitude spectrum has no clamp and no
//     coverage nibble, so there is nothing for them to show.
//   - The divider through the ring. It separated the old loss/gain half-rings,
//     which have not existed since the circle stopped being mirrored.

import * as THREE from "./vendor/three.module.js";

// *** THE RANGE IS FIXED, DELIBERATELY. ***
//
// An auto-zoom that followed the data would change the meaning of a position
// between two frames, so two moments could not be compared -- and comparing two
// moments is the entire point of this instrument. Must equal TONE_FIRST_BIN /
// TONE_LAST_BIN in payload.py (pinned by test).
//
// Bin 0 is excluded: it spans 0-150.73 Hz and contains DC. On 2026-10-16 it
// read -53 dB with the strings muted, which is what kept C2/C#2 permanently lit.
const FIRST_BIN = 1;
// Ends at 2.91 kHz: the range a guitar plays in (see TONE_LAST_BIN in
// payload.py for the operator's call and the data behind it).
const LAST_BIN = 16;
const SECTIONS = LAST_BIN - FIRST_BIN + 1;
const SECTION_ARC = (Math.PI * 2) / SECTIONS;

// *** THE LEVEL SCALE. LINEAR IN dB, FIXED, NEVER FITTED TO THE DATA. ***
//
// FLOOR_DB is the firmware's own "energised" level, 20*log10(TF_SOURCE_GATE)
// (config.h). Must equal TONE_FLOOR_DB in payload.py (pinned by test).
//
// FULL_DB is where a bar reaches full length. Strummed bins measured
// 2026-10-16 peaked near -38 dB and harmonics sat at -44..-55, so -24 puts a
// strong strum at about 60% of the bar with headroom for a hotter pickup.
// Anything louder is drawn full length and CAPPED, never silently truncated.
//
// 🛑 dB relative to FFT magnitude 1.0 — NOT dBFS. The reference has never been
// calibrated against a full-scale input (payload.SPECTRUM_REFERENCE_NOTE).
const FLOOR_DB = -60;
const FULL_DB = -24;

const DISC_RADIUS = 3.15;

// *** TODO-88: THE TALLEST DRAWABLE BAR FITS THE FRAME, IN BOTH DIRECTIONS. ***
//
// With DISC_RADIUS 3.15, FOV 52, 720x1280 and FIT_RADIUS = DISC_RADIUS·1.28,
// the orbit-invariant bounding sphere the camera contains is 3.888 and the bar
// ring sits at 3.018, leaving 2.452 of height. 2.25 + the 0.16 cap = 2.41. The
// sphere is symmetric about the ring plane, so the same bound holds for the
// input above and the return below.
const MAX_BAR_HEIGHT = 2.25;

// A bar louder than FULL_DB is drawn at full length and CAPPED with a marker —
// a clipped bar that looks like a maximum would be a level never reported.
const OVER_RANGE_MARK = 0.16;

// *** NO DECAY TRAIL. LIVE ONLY. ***
//
// A 7 s fade was built on 2026-10-15 and REMOVED the same evening at the
// operator's request: "live notes only, as long as they sustain in the signal".
// Recorded so it is not re-proposed: the objection was CLUTTER, not honesty.

// *** BARS ARE BLOCKS: WIDE ALONG THE RING, SHALLOW ACROSS IT (2026-10-16) ***
//
// Each of the 16 sections owns 1.14 world units of arc at the bar ring. Round
// bars were capped near 0.15 radius, because a full-scale bar must stay inside
// the camera's bounding sphere (3.888, see MAX_BAR_HEIGHT) -- and the operator
// read them as "very skinny, too much empty space". A block spends that budget
// where it can be seen: 0.86 along the ring (75% of the section) and 0.20
// across it. Its outer corner sits at hypot(2.898 + 0.10, 0.43) = 3.029 from
// the axis, and hypot(3.029, 2.41) = 3.871 < 3.888, so it still fits.
const BAR_WIDTH = 0.86;
const BAR_DEPTH = 0.20;
const CAMERA_FOV = 52;
// The ring plus a margin must fit the NARROW axis. On 720x1280 portrait that is
// the horizontal one, so a distance tuned on a landscape mock crops the ring.
const FIT_RADIUS = DISC_RADIUS * 1.28;

const ANGLE_START = Math.PI / 2;       // lowest bin at the top, ascending clockwise
const sectionAngle = (i) => ANGLE_START - i * SECTION_ARC;

const RING_GLOW_COLOR = 0x38506b;      // §1c reference implementation
// Raised from the §1c values (0x0f2230 / 0x331400) on 2026-10-16. Once the
// material colour stopped being squared, the reference emissives left the bar
// sides that face away from the key light a muddy brown and slate; warm vs cool
// is now the whole legend, so it has to read at a glance.
const COLD_EMISSIVE = 0x16405a;
const WARM_EMISSIVE = 0x5a2800;
// Bar height easing, per §1c. Presentation only: it smooths the 20 Hz poll into
// the 60 Hz draw. An UNMEASURED channel never eases -- it snaps to nothing.
const EASE_HEIGHT = 0.16;

// *** WARM IS THE INPUT, COOL IS THE RETURN (operator, 2026-10-16). ***
// Each brightens toward its alert tint as the bin gets louder, so a loud bin is
// both long AND bright.
const INPUT_COLOR = new THREE.Color("#ff7b00");
const INPUT_LOUD_COLOR = new THREE.Color("#ffd166");
const RETURN_COLOR = new THREE.Color("#4cc9f0");
const RETURN_LOUD_COLOR = new THREE.Color("#90e0ef");
// Rig-only: return energy with no input under it. White, on the ring itself,
// because it is a property of the section rather than a level to compare.
const RIG_ONLY_COLOR = new THREE.Color("#f4f8fc");
const RING_COLOR = new THREE.Color("#9fb3c8");
const BACKGROUND_COLOR = new THREE.Color(0x04070b);

const lerp = (a, b, t) => a + (b - a) * t;

// Hz under 1 kHz, kHz above, as the operator asked. One decimal is enough to
// tell neighbouring labels apart: labels sit two bins (344 Hz) apart.
export function fmtHz(hz) {
  if (!(hz > 0)) return "";
  return hz < 1000 ? `${Math.round(hz)} Hz` : `${(hz / 1000).toFixed(1)} kHz`;
}

// Bar length for a level: 0 at the floor, MAX_BAR_HEIGHT at FULL_DB, linear in
// dB between. `over` says the level is beyond the scale and must be capped.
function barFor(db) {
  if (db === null || db === undefined || !(db > FLOOR_DB)) return { h: 0, t: 0, over: false };
  const t = Math.min(1, (db - FLOOR_DB) / (FULL_DB - FLOOR_DB));
  return { h: t * MAX_BAR_HEIGHT, t, over: db > FULL_DB };
}

// A sprite carrying canvas text. Sprites always face the camera, which is what
// keeps a label readable while the ring orbits -- DOM overlays cannot track a
// rotating 3D position without reprojecting every frame.
// The canvas is rendered at FONT px for sharpness and then scaled DOWN into
// world units. FONT controls crispness, LABEL_SCALE controls size on screen.
// 0.0030 with labels at 1.17·DISC_RADIUS fitted note names; "6.1 kHz" is
// twice as long and clipped at both screen edges (render, 2026-10-16), so the
// labels came in to 1.13 and down to 0.0027.
const LABEL_SCALE = 0.0027;
const LABEL_RADIUS = DISC_RADIUS * 1.13;

function makeLabelSprite(text) {
  const PAD = 6, FONT = 42;
  const c = document.createElement("canvas");
  const g = c.getContext("2d");
  g.font = `600 ${FONT}px ui-monospace, Menlo, monospace`;
  const w = Math.ceil(g.measureText(text).width) + PAD * 2;
  c.width = w; c.height = FONT + PAD * 2;
  const g2 = c.getContext("2d");
  g2.font = `600 ${FONT}px ui-monospace, Menlo, monospace`;
  g2.textBaseline = "middle";
  g2.fillStyle = "#aebecf";
  g2.fillText(text, PAD, c.height / 2);
  const tex = new THREE.CanvasTexture(c);
  tex.minFilter = THREE.LinearFilter;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, transparent: true, depthWrite: false, depthTest: false,
  }));
  sp.scale.set(c.width * LABEL_SCALE, c.height * LABEL_SCALE, 1);
  return sp;
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
  // Chromium's Wayland surface is created at a provisional size and resized
  // when the compositor assigns the output -- measured on the panel 2026-10-12
  // at load 668x392, on resize 720x1280. Size is therefore a FUNCTION, called
  // on construction, on every container resize, and whenever the view is shown
  // after being hidden (a display:none container measures 0 x 0).
  let cameraDistance = 1;
  let lastW = 0;
  let lastH = 0;

  function resize() {
    const w = container.clientWidth;
    const h = container.clientHeight;
    // A hidden or not-yet-laid-out container measures zero. Fitting to that
    // would divide by zero and bake a NaN into the camera matrix.
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
  // §1c: a "thin white PULSING torus (same heartbeat as other versions)" with a
  // wider, dimmer glow behind it. The pulse is a property of the REFERENCE, not
  // of the data — it must never be driven by a measurement, or a reader could
  // mistake the instrument's heartbeat for the instrument's signal.
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

  const sectionAngles = [];
  for (let i = 0; i < SECTIONS; i++) sectionAngles.push(sectionAngle(i));

  const barGeo = new THREE.BoxGeometry(1, 1, 1);
  // `emissive` is a constant self-illumination (§1c), so it cannot encode a
  // value. Without it a bar facing away from the key light reads flat.
  //
  // The material colour is WHITE on purpose. three.js MULTIPLIES material
  // colour by instance colour, so a cyan material under a cyan instance drew
  // cyan-squared -- the dark teal of every TONE capture before 2026-10-16, and
  // a brown "orange" in the first input-over-return render. White leaves the
  // instance colour as specified.
  const returnMat = new THREE.MeshLambertMaterial({ color: 0xffffff, emissive: COLD_EMISSIVE });
  const inputMat = new THREE.MeshLambertMaterial({ color: 0xffffff, emissive: WARM_EMISSIVE });
  const inputBars = new THREE.InstancedMesh(barGeo, inputMat, SECTIONS);
  const returnBars = new THREE.InstancedMesh(barGeo, returnMat, SECTIONS);
  for (const m of [inputBars, returnBars]) {
    m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    m.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(SECTIONS * 3), 3);
    scene.add(m);
  }

  // *** THE SECTION SEATS. ***
  //
  // One torus arc per bin, each spanning SECTION_ARC with a small gap so
  // neighbours stay distinguishable. All share one geometry and differ only by
  // rotation, which is what makes them instanceable. A seat is dark unless the
  // section is RIG-ONLY, when it turns white.
  const arcGeo = new THREE.TorusGeometry(
    DISC_RADIUS, 0.085, 8, 14, SECTION_ARC * 0.86);
  const arcs = new THREE.InstancedMesh(
    arcGeo, new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.95 }), SECTIONS);
  arcs.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  arcs.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(SECTIONS * 3), 3);
  scene.add(arcs);

  // Over-range caps at the free end of a bar, shown only when the level is
  // beyond FULL_DB. Up to one per channel per section.
  const capGeo = new THREE.ConeGeometry(0.085, OVER_RANGE_MARK, 8);
  const caps = new THREE.InstancedMesh(
    capGeo, new THREE.MeshBasicMaterial({ color: 0xffffff }), SECTIONS * 2);
  caps.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  scene.add(caps);

  const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);
  const mat4 = new THREE.Matrix4();
  const pos = new THREE.Vector3();
  const scl = new THREE.Vector3();
  const quat = new THREE.Quaternion();
  const tmpColor = new THREE.Color();
  const ORIGIN = new THREE.Vector3(0, 0, 0);
  const UNIT = new THREE.Vector3(1, 1, 1);
  const AXIS_X = new THREE.Vector3(1, 0, 0);
  const AXIS_Y = new THREE.Vector3(0, 1, 0);
  const AXIS_Z = new THREE.Vector3(0, 0, 1);
  // A TorusGeometry is authored in its own XY plane, sweeping about LOCAL Z.
  // So a section is positioned by rotating about Z *first* — while the torus is
  // still in its own plane — and only then tilted flat into the ring plane.
  // The other order scatters the sections onto a plane of their own (first
  // headless render, 2026-10-15: a ring of little hooks).
  //
  // 🔺 THE TILT IS −90°, NOT +90°. Bars and labels sit at (cos a, ·, −sin a).
  // A +90° tilt sends the torus's local +Y to world +Z, i.e. (cos a, ·, +sin a):
  // the seats ran ANTI-clockwise while the bars ran clockwise, so a lit seat
  // sat at the mirror of its own bar. Present since the chromatic ring; found
  // 2026-10-16 when a white rig-only seat rendered at 2.5 kHz beside a return
  // bar at 2.1 kHz.
  const FLAT_Q = new THREE.Quaternion().setFromAxisAngle(AXIS_X, -Math.PI / 2);
  // Every bin keeps its seat whether or not anything is in it: the circle is a
  // fixed ruler. A quiet section is the DARKNESS, never a gap in the ring.
  const ARC_DARK = new THREE.Color("#161e28");
  // An UNMEASURED channel (no number at all) is darker still. Not reachable on
  // the current firmware (`classify_spectrum`), but it must not look quiet.
  const ARC_ABSENT = new THREE.Color("#07090d");

  // Eased bar heights per channel.
  const easedIn = new Array(SECTIONS).fill(0);
  const easedRet = new Array(SECTIONS).fill(0);

  let byBin = new Map();     // bin index -> section entry from tone.bins
  let labelKey = "";
  const labelSprites = [];
  let geometry = null;       // {loHz, hiHz, binHz} once a frame has arrived

  // *** LABELS ARE A RULER, READ FROM THE BIN GEOMETRY THE INSTRUMENT SENT. ***
  //
  // Each label is a bin's CENTRE frequency, so it names the section it sits on.
  // With 16 sections every one is labelled. They depend only on the geometry
  // (fixed per session by HELLO), so they are rebuilt only if that changes.
  function buildLabels(bins) {
    const key = bins.map((b) => b.hz).join(",");
    if (key === labelKey) return;
    labelKey = key;
    for (const sp of labelSprites) scene.remove(sp);
    labelSprites.length = 0;
    for (const b of bins) {
      const i = b.i - FIRST_BIN;
      if (i < 0 || i >= SECTIONS) continue;
      const a = sectionAngles[i];
      const sp = makeLabelSprite(fmtHz(b.hz));
      sp.position.set(Math.cos(a) * LABEL_RADIUS, 0.06, -Math.sin(a) * LABEL_RADIUS);
      scene.add(sp);
      labelSprites.push(sp);
    }
    const first = bins.find((b) => b.i === FIRST_BIN);
    const last = bins.find((b) => b.i === LAST_BIN);
    geometry = first && last
      ? { loHz: first.lo_hz, hiHz: last.hi_hz, binHz: first.hi_hz - first.lo_hz }
      : null;
  }

  function placeBar(mesh, i, angle, height, below, color) {
    if (height < 0.005) { mesh.setMatrixAt(i, HIDDEN); return; }
    const y = below ? -(height / 2 + 0.01) : height / 2 + 0.01;
    pos.set(Math.cos(angle) * (DISC_RADIUS * 0.92), y, -Math.sin(angle) * (DISC_RADIUS * 0.92));
    // Turning by `angle` about Y sends the box's local X to the radial
    // direction (cos a, 0, −sin a) and local Z to the tangent, so DEPTH runs
    // across the ring and WIDTH along it.
    quat.setFromAxisAngle(AXIS_Y, angle);
    scl.set(BAR_DEPTH, height, BAR_WIDTH);
    mesh.setMatrixAt(i, mat4.compose(pos, quat, scl));
    mesh.setColorAt(i, color);
  }

  function placeCap(n, angle, height, below) {
    const y = below ? -(height + OVER_RANGE_MARK) : height + OVER_RANGE_MARK;
    pos.set(Math.cos(angle) * (DISC_RADIUS * 0.92), y,
            -Math.sin(angle) * (DISC_RADIUS * 0.92));
    quat.identity();
    if (below) quat.setFromAxisAngle(AXIS_X, Math.PI);
    scl.set(1, 1, 1);
    caps.setMatrixAt(n, mat4.compose(pos, quat, scl));
  }

  function update() {
    let cap = 0;
    for (let i = 0; i < SECTIONS; i++) {
      const b = byBin.get(FIRST_BIN + i);
      const angle = sectionAngles[i];

      // Rotate in the torus's own plane, then lay it flat. The half-arc offset
      // centres the segment on the bin's angle instead of starting there.
      arcs.setMatrixAt(i, mat4.compose(
        ORIGIN,
        quat.setFromAxisAngle(AXIS_Z, angle - SECTION_ARC * 0.43).premultiply(FLAT_Q),
        UNIT));

      const inMeasured = !!b && b.src_cls === "MEASURED";
      const retMeasured = !!b && b.ret_cls === "MEASURED";
      arcs.setColorAt(i, !b || !inMeasured || !retMeasured ? ARC_ABSENT
                         : b.rig_only ? RIG_ONLY_COLOR : ARC_DARK);

      // --- input, above the ring -------------------------------------------
      // Lengths come from the levels; WHETHER a bar exists comes from the Pi's
      // classification (src_on / ret_on), never re-derived here. The first
      // render drew a return bar on every section while the census said
      // "return 0" -- the renderer was second-guessing the boundary.
      const inp = barFor(inMeasured && b.src_on ? b.src_db : null);
      easedIn[i] = inMeasured ? lerp(easedIn[i], inp.h, EASE_HEIGHT) : 0;
      placeBar(inputBars, i, angle, easedIn[i], false,
               tmpColor.copy(INPUT_COLOR).lerp(INPUT_LOUD_COLOR, inp.t));
      if (inp.over && easedIn[i] > 0.005) placeCap(cap++, angle, easedIn[i], false);

      // --- return, level-matched, below the ring ---------------------------
      const ret = barFor(retMeasured && b.ret_on ? b.ret_matched_db : null);
      easedRet[i] = retMeasured ? lerp(easedRet[i], ret.h, EASE_HEIGHT) : 0;
      placeBar(returnBars, i, angle, easedRet[i], true,
               tmpColor.copy(RETURN_COLOR).lerp(RETURN_LOUD_COLOR, ret.t));
      if (ret.over && easedRet[i] > 0.005) placeCap(cap++, angle, easedRet[i], true);
    }
    for (let c = cap; c < SECTIONS * 2; c++) caps.setMatrixAt(c, HIDDEN);

    inputBars.instanceMatrix.needsUpdate = true;
    returnBars.instanceMatrix.needsUpdate = true;
    arcs.instanceMatrix.needsUpdate = true;
    caps.instanceMatrix.needsUpdate = true;
    if (inputBars.instanceColor) inputBars.instanceColor.needsUpdate = true;
    if (returnBars.instanceColor) returnBars.instanceColor.needsUpdate = true;
    if (arcs.instanceColor) arcs.instanceColor.needsUpdate = true;
  }

  // *** THE SPIN RESUMES WHERE YOU LET GO. ***
  //
  // Dragging used to set `spin = false` permanently, so one accidental touch
  // stopped the orbit for the rest of the session and the only way back was a
  // tab change. Releasing now resumes the spin from the CURRENT yaw and pitch,
  // so a drag re-aims the view rather than ending the animation.
  let yaw = 0.0, pitch = -0.42, spin = true;
  let dragging = false, lastX = 0, lastY = 0;
  const el = renderer.domElement;
  const down = (x, y) => { dragging = true; spin = false; lastX = x; lastY = y; };
  const up = () => {
    if (!dragging) return;
    dragging = false;
    spin = true;            // carry on from wherever the finger left it
  };
  const move = (x, y) => {
    if (!dragging) return;
    yaw -= (x - lastX) * 0.008;
    pitch += (y - lastY) * 0.005;
    // Keep the ring in front of the camera: past +/-85 degrees the view passes
    // through the plane and the labels invert.
    pitch = Math.max(-1.48, Math.min(1.48, pitch));
    lastX = x; lastY = y;
  };
  el.addEventListener("mousedown", e => down(e.clientX, e.clientY));
  window.addEventListener("mouseup", up);
  window.addEventListener("mousemove", e => move(e.clientX, e.clientY));
  el.addEventListener("touchstart", e => down(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
  window.addEventListener("touchend", up);
  window.addEventListener("touchcancel", up);
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
    // `tone` is payload.tone_block() output, or null when the frame has none
    // (a RESULT, or no frame yet) -- then every section goes dark.
    setTone(tone) {
      const bins = (tone && Array.isArray(tone.bins)) ? tone.bins : [];
      byBin = new Map(bins.map((b) => [b.i, b]));
      if (bins.length) buildLabels(bins);
    },

    // What the legend must describe. Read, never assumed, so the two cannot
    // drift from the geometry they describe.
    scale() {
      return {
        floorDb: FLOOR_DB,
        fullDb: FULL_DB,
        sections: SECTIONS,
        loHz: geometry ? geometry.loHz : null,
        hiHz: geometry ? geometry.hiHz : null,
        binHz: geometry ? geometry.binHz : null,
      };
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

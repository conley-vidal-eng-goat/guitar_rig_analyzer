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

// The 48 payload bands span 21.5 Hz - 18.6 kHz at 2.47 semitones each. A
// guitar's six open strings occupy 9 of them, so drawing all 48 put the
// player's entire fundamental range in 19% of the circle. The ring is now a
// MUSICAL axis instead of the full spectrum.
//
// 🛑 THE RANGE IS FIXED, DELIBERATELY. An auto-zoom that followed the data
// would change the meaning of a position between two frames, so two moments
// could not be compared -- and comparing two moments is the entire point of
// this instrument. If the range changes it changes because a human changed it.

// *** THE CIRCLE IS A CHROMATIC SCALE, ONE SEMITONE PER SECTION (2026-10-15) ***
//
// 360 / 53 = 6.79 degrees per note, C2 (65.41 Hz) to E6 (1318.51 Hz).
//
// 🔺 THE OPERATOR ASKED FOR "C1 65.4 Hz .. E6 1278.75 Hz, 76 sections". Two of
// those three numbers are corrected here, and the correction is recorded rather
// than applied silently:
//   - 65.4 Hz is C2 in scientific pitch notation, not C1 (C1 is 32.70 Hz).
//     Guitar writing often drops an octave; this file uses scientific naming
//     because that is what the frequencies say.
//   - 1278.75 Hz is nearest D#6; E6 is 1318.51 Hz. E6 is used.
//   - C2..E6 is 52 semitones = 53 inclusive sections, NOT 76. A 76/77-section
//     circle would be C1..E7 or C0..E6 -- 6.3 octaves, far wider than the range
//     described.
const NOTE_LO_MIDI = 36;               // C2
const NOTE_SECTIONS = 53;              // C2..E6 inclusive
const SECTION_ARC = (Math.PI * 2) / NOTE_SECTIONS;
const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

// The ring-band grid the payload actually sends: 48 log bands over 20 Hz-20 kHz.
// Used to find which band covers a note's centre frequency.
const BAND_F_LO = 20.0;
const BAND_LOG_SPAN = Math.log10(20000.0 / 20.0);

const noteHz = (i) => 440 * Math.pow(2, (NOTE_LO_MIDI + i - 69) / 12);
const noteName = (i) => {
  const m = NOTE_LO_MIDI + i;
  return NOTE_NAMES[m % 12] + String(Math.floor(m / 12) - 1);
};
// Which of the 48 payload bands covers this frequency. Several adjacent note
// sections resolve to the SAME band -- that is not a bug, it is the
// instrument's resolution becoming visible, and §RESOLUTION below says so.
const bandOfHz = (hz) =>
  Math.floor((Math.log10(hz / BAND_F_LO) / BAND_LOG_SPAN) * NUM_BANDS);

// *** §RESOLUTION -- READ THIS BEFORE BELIEVING A LIT SECTION IS A NOTE. ***
//
// A lit section is NOT "the instrument identified this note". Measured from the
// live wire 2026-10-15, one transmitted bin is 172.1 Hz, so:
//
//     C2    65.41 Hz : one semitone is  3.89 Hz -> the bin spans 44.2 semitones
//     C4   261.63 Hz : one semitone is 15.56 Hz -> the bin spans 11.1 semitones
//     E6  1318.51 Hz : one semitone is 78.40 Hz -> the bin spans  2.2 semitones
//
// A bin is narrower than a semitone only above ~2894 Hz, which is above this
// entire range. Within C2..E6 the payload carries 22 of its 48 bands, so 22
// values are shown across 53 sections and each band covers ~2.4 of them.
//
// That is why sections light in GROUPS. The group width is the band that fed
// it, so the picture shows the instrument's resolution instead of hiding it.
// Lighting one section per band would assert a precision the wire never
// carried -- the same fabrication that keeps note names off these labels.

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
// ring sits at 3.018, leaving 2.452 of height. 2.25 + the 0.16 cap = 2.41.
// (The bar ring grew when bars were thickened for the chromatic layout, so the
// headroom shrank and this constant came down with it.)
//
// 🔺 The ring was NOT shrunk to achieve this, which was the alternative and
// would have worked against the complaint that prompted the work.
const MAX_BAR_HEIGHT = 2.25;

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

// *** NO DECAY TRAIL. LIVE ONLY. ***
//
// A 7 s fade was built on 2026-10-15 and REMOVED the same evening at the
// operator's request: "live notes only, as long as they sustain in the signal".
// A bar is present exactly while the instrument reports that band as MEASURED.
//
// Recorded so it is not re-proposed as an improvement: persistence was tried,
// and the objection was not that it was dishonest but that it was CLUTTER --
// sustain is already visible in the live signal, so the history added noise
// without adding information.

// Bars are thicker now that each one owns a 6.79-degree section of the circle
// rather than sharing a crowded arc with a mirrored copy of itself.
const BAR_RADIUS_BASE = 0.055;
const BAR_RADIUS_GAIN = 0.065;
const CAMERA_FOV = 52;
// The ring plus a margin must fit the NARROW axis. On 720x1280 portrait that is
// the horizontal one, so a distance tuned on a landscape mock crops the ring.
const FIT_RADIUS = DISC_RADIUS * 1.28;

// *** ONE FULL CIRCLE, NO MIRRORED HALVES. ***
//
// The ring used to run the same 48 bands twice -- a left arc for attenuation and
// a right arc for boost -- so every band appeared at two positions and each got
// less than half the circle. Angle now means ONE thing, frequency, and
// direction moved to the axis it was always available on: a bar rises above the
// ring when the rig boosted that band and drops below it when the rig took it
// away. Same information, twice the angular space, and no duplicate to read.
const ANGLE_START = Math.PI / 2;       // C2 at the top, ascending clockwise
const sectionAngle = (i) => ANGLE_START - i * SECTION_ARC;

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

// Short, unambiguous frequency text, used in the scale line rather than on the
// ring -- the ring carries note names now.
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

function makeLabelSprite(text, { dim = false, dc = false } = {}) {
  const PAD = 6, FONT = 42;
  const c = document.createElement("canvas");
  const g = c.getContext("2d");
  g.font = `600 ${FONT}px ui-monospace, Menlo, monospace`;
  const w = Math.ceil(g.measureText(text).width) + PAD * 2;
  c.width = w; c.height = FONT + PAD * 2;
  const g2 = c.getContext("2d");
  g2.font = `600 ${FONT}px ui-monospace, Menlo, monospace`;
  g2.textBaseline = "middle";
  g2.fillStyle = dc ? "#7d6a3a" : (dim ? "#5c6b7a" : "#aebecf");
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

  const sectionAngles = [];
  for (let i = 0; i < NOTE_SECTIONS; i++) sectionAngles.push(sectionAngle(i));

  const barGeo = new THREE.CylinderGeometry(1, 1, 1, 10, 1, false);
  // `emissive` is specified by the reference implementation and was not ported.
  // Without it the bars are lit only by the two scene lights and read flat when a
  // band faces away from the key light. It is a constant self-illumination, so it
  // cannot encode a value and cannot vary with one.
  const coldMat = new THREE.MeshLambertMaterial({ color: COLD_COLOR, emissive: COLD_EMISSIVE });
  const warmMat = new THREE.MeshLambertMaterial({ color: WARM_COLOR, emissive: WARM_EMISSIVE });
  const missingBars = new THREE.InstancedMesh(barGeo, coldMat, NOTE_SECTIONS);
  const boostBars = new THREE.InstancedMesh(barGeo, warmMat, NOTE_SECTIONS);
  for (const m of [missingBars, boostBars]) {
    m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    m.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(NOTE_SECTIONS * 3), 3);
    scene.add(m);
  }

  // *** THE SECTION ARCS -- "the whole section lights up". ***
  //
  // One torus arc per note, each spanning exactly SECTION_ARC with a small gap
  // so adjacent notes stay distinguishable. All 53 share one geometry and
  // differ only by rotation, which is what makes them instanceable.
  //
  // An arc is lit by the BAND covering that note's centre frequency, so several
  // adjacent notes light together -- see §RESOLUTION. The group IS the
  // measurement's width.
  const arcGeo = new THREE.TorusGeometry(
    DISC_RADIUS, 0.085, 8, 14, SECTION_ARC * 0.86);
  const arcs = new THREE.InstancedMesh(
    arcGeo, new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.95 }), NOTE_SECTIONS);
  arcs.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  arcs.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(NOTE_SECTIONS * 3), 3);
  scene.add(arcs);

  // Over-range caps: shown only when |dB| exceeds the scale, so a bar pinned at
  // full length can never be mistaken for a value of exactly MAX_DB.
  const capGeo = new THREE.ConeGeometry(0.085, OVER_RANGE_MARK, 8);
  const caps = new THREE.InstancedMesh(
    capGeo, new THREE.MeshBasicMaterial({ color: 0xffffff }), NOTE_SECTIONS);
  caps.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  scene.add(caps);

  // Unknown markers: ONE per section now, not one per side -- there is only one
  // position per note since the mirrored arc is gone.
  const markerGeo = new THREE.TorusGeometry(0.17, 0.035, 8, 24);
  const markerMat = new THREE.MeshBasicMaterial({ color: UNKNOWN_COLOR });
  const markers = new THREE.InstancedMesh(markerGeo, markerMat, NOTE_SECTIONS);
  markers.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  scene.add(markers);

  const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);
  const mat4 = new THREE.Matrix4();
  const pos = new THREE.Vector3();
  const scl = new THREE.Vector3();
  const quat = new THREE.Quaternion();
  const flat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);
  const tmpColor = new THREE.Color();
  const ORIGIN = new THREE.Vector3(0, 0, 0);
  const UNIT = new THREE.Vector3(1, 1, 1);
  const AXIS_X = new THREE.Vector3(1, 0, 0);
  const AXIS_Z = new THREE.Vector3(0, 0, 1);
  // A TorusGeometry is authored in its own XY plane, sweeping about LOCAL Z.
  // So a section is positioned by rotating about Z *first* — while the torus is
  // still in its own plane — and only then tilted flat into the ring plane.
  //
  // Doing it the other way round (rotate about world Y, then flatten) scatters
  // the sections onto a plane of their own: observed in the first headless
  // render, 2026-10-15, as a ring of little hooks that did not touch the torus.
  const FLAT_Q = new THREE.Quaternion().setFromAxisAngle(AXIS_X, Math.PI / 2);
  // An UNMEASURED section is drawn as a dark seat, not left absent: the circle
  // is a fixed musical ruler, so every note keeps its place whether or not the
  // instrument measured it. Absence is the DARKNESS, never a gap in the ring.
  const ARC_DARK = new THREE.Color("#161e28");

  // Eased bar heights, and the class each was eased under. A class change snaps.
  const eased = new Array(NOTE_SECTIONS).fill(0);
  const easedCov = new Array(NOTE_SECTIONS).fill(1);
  const easedCls = new Array(NOTE_SECTIONS).fill("UNMEASURED");

  // Which payload band feeds each note section. Fixed for the life of the view,
  // so it is computed once rather than 20 times a second.
  const bandForSection = new Int16Array(NOTE_SECTIONS);
  for (let i = 0; i < NOTE_SECTIONS; i++) bandForSection[i] = bandOfHz(noteHz(i));

  let segments = [];
  let dcEdgeHz = 0;          // bands centred below this are DC-contaminated
  let labelsBuilt = false;
  const labelSprites = [];

  // *** NOTE NAMES ARE A RULER, NOT A MEASUREMENT. ***
  //
  // These are computed from the note's own frequency -- they label a POSITION on
  // a fixed chromatic axis, exactly as "100 Hz" labelled a position before. They
  // are not derived from the data and they assert nothing about what is playing.
  //
  // 🛑 Nothing here, and nothing downstream, may read a lit section as "the
  // instrument identified this note". §RESOLUTION gives the arithmetic: a
  // transmitted bin spans 44 semitones at C2 and 2.2 at E6, so note identity is
  // not on the wire anywhere in this range.
  //
  // Naturals are drawn bright and sharps dim, the way a keyboard reads, so 53
  // labels around one circle stay scannable.
  function buildLabels() {
    if (labelsBuilt) return;
    labelsBuilt = true;
    for (const sp of labelSprites) scene.remove(sp);
    labelSprites.length = 0;
    for (let i = 0; i < NOTE_SECTIONS; i++) {
      const name = noteName(i);
      const sharp = name.includes("#");
      const hz = noteHz(i);
      // A section whose frequency sits below the first clean transmitted bin is
      // DC-contaminated. TODO-92: bin 0 spans 0-150.73 Hz and contains DC, and
      // LIVE refuses to plot it. The ring still shows it -- marked, not silently.
      const dc = dcEdgeHz > 0 && hz < dcEdgeHz;
      const a = sectionAngles[i];
      const sp = makeLabelSprite((dc ? "•" : "") + name,
                                 { dim: sharp || dc, dc });
      sp.position.set(Math.cos(a) * (DISC_RADIUS * 1.17), 0.06,
                      -Math.sin(a) * (DISC_RADIUS * 1.17));
      scene.add(sp);
      labelSprites.push(sp);
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
    let marker = 0;
    let cap = 0;
    for (let i = 0; i < NOTE_SECTIONS; i++) {
      const seg = segments[bandForSection[i]];
      const cls = seg ? seg.cls : "UNMEASURED";
      const angle = sectionAngles[i];

      // --- the section arc: "the whole section lights up" -------------------
      //
      // Lit by the band covering this note. Adjacent notes fed by the same band
      // light as a group, and that group's width is the instrument's resolution
      // rather than a claim about one note (§RESOLUTION).
      // Rotate in the torus's own plane, then lay it flat. The half-arc offset
      // centres the segment on the note's angle instead of starting there.
      arcs.setMatrixAt(i, mat4.compose(
        ORIGIN,
        quat.setFromAxisAngle(AXIS_Z, angle - SECTION_ARC * 0.43).premultiply(FLAT_Q),
        UNIT));

      // --- UNMEASURED and CLAMPED produce no bar ----------------------------
      if (cls !== "MEASURED") {
        eased[i] = 0;
        easedCls[i] = cls;
        missingBars.setMatrixAt(i, HIDDEN);
        boostBars.setMatrixAt(i, HIDDEN);
        arcs.setColorAt(i, cls === "UNMEASURED" ? ARC_DARK : UNKNOWN_COLOR);
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
        eased[i] = easedCls[i] === "MEASURED" ? lerp(eased[i], target, EASE_HEIGHT) : target;

        const cov = seg.coverage ?? 1;
        easedCov[i] = easedCls[i] === "MEASURED"
          ? lerp(easedCov[i], cov, EASE_COVERAGE) : cov;
        easedCls[i] = "MEASURED";

        const radius = BAR_RADIUS_BASE + easedCov[i] * BAR_RADIUS_GAIN;
        // Direction is the AXIS now, not the side of the circle: above the ring
        // the rig added energy, below it the rig took energy away.
        const below = db < 0;
        const color = colorForMagnitude(magnitude, below ? "missing" : "boost");
        placeBar(below ? missingBars : boostBars, i, angle, eased[i], radius, below, color);
        (below ? boostBars : missingBars).setMatrixAt(i, HIDDEN);
        arcs.setColorAt(i, color);

        // Over-range cap at the free end of the bar.
        if (over) {
          const y = below ? -(eased[i] + OVER_RANGE_MARK) : eased[i] + OVER_RANGE_MARK;
          pos.set(Math.cos(angle) * (DISC_RADIUS * 0.92), y,
                  -Math.sin(angle) * (DISC_RADIUS * 0.92));
          quat.identity();
          if (below) quat.setFromAxisAngle(AXIS_X, Math.PI);
          scl.set(1, 1, 1);
          caps.setMatrixAt(cap++, mat4.compose(pos, quat, scl));
        }
      }

      // --- markers for values that exist but are not established ------------
      if (cls === "INDETERMINATE" || cls === "CLAMPED") {
        pos.set(Math.cos(angle) * (DISC_RADIUS * 0.92), 0.02,
                -Math.sin(angle) * (DISC_RADIUS * 0.92));
        scl.set(1, 1, 1);
        markers.setMatrixAt(marker++, mat4.compose(pos, flat, scl));
      }
    }
    for (let m = marker; m < NOTE_SECTIONS; m++) markers.setMatrixAt(m, HIDDEN);
    for (let c = cap; c < NOTE_SECTIONS; c++) caps.setMatrixAt(c, HIDDEN);

    missingBars.instanceMatrix.needsUpdate = true;
    boostBars.instanceMatrix.needsUpdate = true;
    arcs.instanceMatrix.needsUpdate = true;
    markers.instanceMatrix.needsUpdate = true;
    caps.instanceMatrix.needsUpdate = true;
    if (missingBars.instanceColor) missingBars.instanceColor.needsUpdate = true;
    if (boostBars.instanceColor) boostBars.instanceColor.needsUpdate = true;
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
    setSegments(next) {
      segments = next || [];
      // Note labels are a fixed chromatic ruler and do not depend on the data
      // at all, so they are built once and never rebuilt per frame.
      if (!labelsBuilt) buildLabels();
    },

    // The DC edge comes from the frame's own spectrum geometry (the low edge of
    // the first non-DC transmitted bin). Passing it in rather than hardcoding it
    // means the mark follows the instrument if the geometry ever changes.
    setDcEdge(hz) {
      const v = (typeof hz === "number" && isFinite(hz) && hz > 0) ? hz : 0;
      if (v === dcEdgeHz) return;
      dcEdgeHz = v;
      labelsBuilt = false;                  // re-label with the new marking
      buildLabels();
    },

    // What the legend must describe. Read, never assumed, so the two cannot
    // drift. `bandsInRange` is how many DISTINCT payload bands feed the 53
    // sections -- the number the resolution caveat is built on.
    scale() {
      const distinct = new Set();
      for (let i = 0; i < NOTE_SECTIONS; i++) distinct.add(bandForSection[i]);
      return {
        maxDb: MAX_DB,
        sections: NOTE_SECTIONS,
        loNote: noteName(0),
        hiNote: noteName(NOTE_SECTIONS - 1),
        loHz: noteHz(0),
        hiHz: noteHz(NOTE_SECTIONS - 1),
        degPerSection: 360 / NOTE_SECTIONS,
        bandsInRange: distinct.size,
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

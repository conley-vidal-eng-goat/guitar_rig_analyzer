// TONE — the Tone Fingerprint, full-bleed.
//
// *** THIS VIEW DOES NOT REIMPLEMENT THE VISUALISATION. ***
// It owns a container, a census line and a legend. The scene itself is
// fingerprint_split.js, unchanged in geometry, colour, batching, data contract
// and camera behaviour. The committed design (visual_design_document.md §1c) is
// the specification for what is drawn; this file only decides where it sits,
// when it is allowed to run, and what happens when it cannot run at all.
//
// *** THE SCENE IS BUILT LAZILY, AND ITS FAILURE IS CONTAINED. ***
//
// Found on 2026-10-13 with WebGL disabled: constructing the renderer eagerly
// made a GPU failure fatal to the WHOLE interface. three.js throws when it
// cannot create a context, the throw propagated out of view construction, and
// main.js never ran -- so LIVE, LAB and INFO went blank too, though not one of
// them needs a GPU.
//
// That is backwards. The measurement readouts are the part that must survive.
// So the scene is created on first activation, inside a guard, and if it cannot
// be created this view says so plainly while the other three keep working. The
// design brief asks for exactly this: the interface must still be good with the
// 3D disabled.
//
// The census is on this screen deliberately. Both figures are shown -- the
// instrument's own 512-bin coverage and the 48-band ring it was reduced to --
// because the reduction is a presentation step and must never be mistaken for
// the instrument's coverage.

import { createFingerprint } from "./fingerprint_split.js";
import { esc } from "./ui.js";

// The legend is not decoration. Every rule a reader needs in order to not
// misread this picture is stated here, because a 3D view with an implicit scale
// invites confident wrong readings — and under ADR-005 the renderer carries the
// burden of saying what it is showing.
//
// Written 2026-10-15 after the operator's report: "there should be no doubt as
// to how to read this visualization."
const LEGEND = [
  ["sw-cold", "<b>attenuated</b> — the rig took this away (bar drops <b>below</b> the ring)"],
  ["sw-warm", "<b>boosted</b> — the rig added this (bar rises <b>above</b> the ring)"],
  ["sw-unknown", "value present, direction <b>not established</b> — nothing asserted"],
  ["sw-none", "<b>unmeasured</b> — section stays dark. A dark section is not a zero"],
];

export function createToneView(root) {
  const stage = document.createElement("div");
  stage.className = "tone-stage";
  root.appendChild(stage);

  const census = document.createElement("div");
  census.className = "tone-census";
  census.textContent = "connecting…";
  root.appendChild(census);

  const scaleLine = document.createElement("div");
  scaleLine.className = "tone-scale";
  root.appendChild(scaleLine);

  const legend = document.createElement("div");
  legend.className = "tone-legend";
  // The LEGEND strings carry deliberate <b> markup and are authored in this
  // file, so they are not escaped. Nothing from the wire reaches this string.
  legend.innerHTML = LEGEND
    .map(([c, t]) => `<div><span class="sw ${c}"></span>${t}</div>`)
    .join("");
  root.appendChild(legend);

  // Everything about the scale is READ FROM THE SCENE, never restated here, so
  // the legend cannot drift away from the geometry it describes.
  function renderScale() {
    if (!scene || !scene.scale) { scaleLine.textContent = ""; return; }
    const s = scene.scale();
    const perBand = (s.sections / s.bandsInRange).toFixed(1);
    scaleLine.innerHTML =
      `<b>bar length = |dB|</b>, full bar = ${s.maxDb} dB` +
      ` · a bar at the minimum means <i>measured and small</i>, not a value` +
      ` · <b>▲ capped</b> = beyond ${s.maxDb} dB` +
      `<br><b>${s.sections} semitone sections</b>, ${s.loNote} ${fmtHz(s.loHz)}` +
      ` → ${s.hiNote} ${fmtHz(s.hiHz)}, ${s.degPerSection.toFixed(1)}° each` +
      `<br>🔺 <b>a lit group is not one note.</b> The instrument sends` +
      ` <b>${s.bandsInRange} values</b> across these ${s.sections} sections, so each` +
      ` measurement lights about <b>${perBand} sections</b> — that width is its` +
      ` resolution, not a note it identified` +
      (dcEdge ? `<br><b>•</b> marks notes under ${fmtHz(dcEdge)}, where the` +
                ` transmitted bin contains DC and LIVE will not plot it (TODO-92)` : "");
  }

  function fmtHz(hz) {
    return hz < 1000 ? `${Math.round(hz)} Hz` : `${(hz / 1000).toFixed(1)} kHz`;
  }

  let scene = null;
  let failed = false;
  let pending = [];
  let live = false;
  let dcEdge = 0;

  function build() {
    if (scene || failed) return;
    try {
      scene = createFingerprint(stage);
      scene.setSegments(pending);
      scene.setDcEdge(dcEdge);
      renderScale();
    } catch (e) {
      failed = true;
      legend.hidden = true;
      scaleLine.hidden = true;
      stage.innerHTML = `<div class="tone-unavailable">
        <h2>3D view unavailable</h2>
        <p class="note">This device could not create a WebGL context, so the
        fingerprint cannot be drawn.</p>
        <p class="note">${esc(e.message || String(e))}</p>
        <p class="note"><b>Nothing is wrong with the measurement.</b> The
        instrument is unaffected and the other screens are reading it normally —
        this is a graphics failure on the display side only.</p>
      </div>`;
    }
  }

  return {
    update(f) {
      // Segments are kept even while the scene does not exist, so the first
      // visible frame after activation is the current one rather than whatever
      // happens to arrive next.
      pending = f.segments || [];

      // The DC edge is the low edge of the first transmitted bin that is NOT
      // flagged `dc`. Derived from the frame the instrument sent, so if the
      // geometry changes the mark follows it. TODO-92 is the real fix; until
      // then the ring at least says which bands carry the contamination.
      const geo = f.spectra && f.spectra.geometry;
      if (Array.isArray(geo)) {
        const firstClean = geo.find((g) => g && g.dc === false);
        const edge = firstClean && firstClean.lo_hz;
        if (typeof edge === "number" && edge !== dcEdge) dcEdge = edge;
      }

      if (scene) {
        scene.setSegments(pending);
        scene.setDcEdge(dcEdge);
      }
      renderScale();
      census.textContent = f.kind === "unknown"
        ? f.reason
        : `source ${f.census_source.text}   →   ring ${f.census_bands.text}`;
    },

    activate() {
      if (live) return;
      live = true;
      build();
      if (!scene) return;
      // Order matters. While this view was hidden its container was
      // `display:none`, so every measurable dimension on it was 0 and any size
      // taken then is meaningless. Re-measure BEFORE resuming the loop, or the
      // first visible frames render against a dead layout (TODO-80).
      scene.resize();
      scene.resume();
    },

    deactivate() {
      live = false;
      if (scene) scene.pause();
    },
  };
}

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

const LEGEND = [
  ["sw-cold", "measured · attenuated (left, below ring)"],
  ["sw-warm", "measured · boosted (right, above ring)"],
  ["sw-unknown", "value present, not established — no direction asserted"],
  ["sw-none", "unmeasured — nothing drawn"],
];

export function createToneView(root) {
  const stage = document.createElement("div");
  stage.className = "tone-stage";
  root.appendChild(stage);

  const census = document.createElement("div");
  census.className = "tone-census";
  census.textContent = "connecting…";
  root.appendChild(census);

  const legend = document.createElement("div");
  legend.className = "tone-legend";
  legend.innerHTML = LEGEND
    .map(([c, t]) => `<div><span class="sw ${c}"></span>${esc(t)}</div>`)
    .join("");
  root.appendChild(legend);

  let scene = null;
  let failed = false;
  let pending = [];
  let live = false;

  function build() {
    if (scene || failed) return;
    try {
      scene = createFingerprint(stage);
      scene.setSegments(pending);
    } catch (e) {
      failed = true;
      legend.hidden = true;
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
      if (scene) scene.setSegments(pending);
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

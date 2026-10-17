// TONE — the Tone Fingerprint, full-bleed.
//
// *** THIS VIEW DOES NOT REIMPLEMENT THE VISUALISATION. ***
// It owns a container, a census line, the rig-gain readout and a legend. The
// scene itself is fingerprint_split.js; this file only decides where it sits,
// when it is allowed to run, what it says about itself, and what happens when
// it cannot run at all.
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
// The census is on this screen deliberately: how many of the drawn bins carry
// input, return and rig-only energy above the floor, so an empty-looking ring
// can be told apart from a broken one.

import { createFingerprint, fmtHz } from "./fingerprint_split.js";
import { esc } from "./ui.js";

// The legend is not decoration. Every rule a reader needs in order to not
// misread this picture is stated here, because a 3D view with an implicit scale
// invites confident wrong readings — and under ADR-005 the renderer carries the
// burden of saying what it is showing.
//
// Rewritten 2026-10-16 with the input-over-return ring: warm is what went IN,
// cool is what came BACK, white is what the rig added on its own.
const LEGEND = [
  ["sw-warm", "<b>input</b> — the signal going into the rig (bar rises <b>above</b> the ring)"],
  ["sw-cold", "<b>return</b> — what the rig sent back, level-matched (bar drops <b>below</b>); drawn only where the return itself clears the floor"],
  ["sw-rig", "<b>rig-only</b> — the return has energy where the input has none (noise the rig adds)"],
  ["sw-none", "<b>dark</b> — quieter than the floor on both. Measured and quiet, not missing"],
];

export function createToneView(root) {
  const stage = document.createElement("div");
  stage.className = "tone-stage";
  root.appendChild(stage);

  const census = document.createElement("div");
  census.className = "tone-census";
  census.textContent = "connecting…";
  root.appendChild(census);

  // *** THE GAIN IS THE HEADLINE NUMBER ON THIS SCREEN. ***
  //
  // The return is drawn shifted by it, so without it on screen the picture
  // would hide exactly the thing a player most wants to know: is the rig
  // losing level or adding it. Sign always shown; "held" when the input is
  // below the floor and the last established value is being used.
  const gainBox = document.createElement("div");
  gainBox.className = "tone-gain";
  root.appendChild(gainBox);

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
    const span = s.loHz && s.hiHz
      ? `${fmtHz(s.loHz)} → ${fmtHz(s.hiHz)}, each section one bin ${Math.round(s.binHz)} Hz wide`
      : "waiting for bin geometry";
    scaleLine.innerHTML =
      `<b>bar length = level above ${s.floorDb} dB</b>, full bar = ${s.fullDb} dB` +
      ` · linear in dB · <b>▲ capped</b> = louder than ${s.fullDb} dB` +
      ` · dB re FFT 1.0, <i>not dBFS</i>` +
      `<br><b>${s.sections} sections</b>, ${span}` +
      `<br>below ${s.loHz ? fmtHz(s.loHz) : "the first bin"} is not drawn: that bin` +
      ` contains DC and all three low strings at once (TODO-92, phase 2)`;
  }

  function fmtSigned(v) {
    return (v > 0 ? "+" : v < 0 ? "−" : "±") + Math.abs(v).toFixed(1);
  }

  // Sign, size and direction in words, so "−27.1" cannot be misread as a
  // display offset. The shift applied to the return is the gain negated.
  function renderGain(t) {
    if (!t) { gainBox.innerHTML = ""; return; }
    if (t.gain_state === "below_floor") {
      // A bound, not a value: the return is under the floor in every bin
      // where the input is above it, so all that can be said is how far down
      // it is AT LEAST. Never a held number in this state -- the current frame
      // contradicts it.
      gainBox.className = "tone-gain bound";
      gainBox.innerHTML = `<span class="k">rig gain</span>` +
        ` <span class="v">&lt; ${fmtSigned(t.gain_bound_db)} dB</span>` +
        `<div class="sub">return is below the ${t.floor_db} dB floor wherever the input` +
        ` is above it: at least ${Math.abs(t.gain_bound_db).toFixed(1)} dB down.` +
        ` Check the return path.</div>`;
      return;
    }
    if (t.gain_db === null || t.gain_db === undefined) {
      gainBox.innerHTML = `<span class="k">rig gain</span> <span class="v none">—</span>` +
        `<div class="sub">not established yet: play to give it input above ${t.floor_db} dB.` +
        ` Return drawn unmatched.</div>`;
      gainBox.className = "tone-gain";
      return;
    }
    const g = t.gain_db;
    const mag = Math.abs(g).toFixed(1);
    const sign = g > 0.05 ? "+" : g < -0.05 ? "−" : "±";
    const verb = g > 0.05 ? `gaining ${mag} dB` : g < -0.05 ? `losing ${mag} dB` : "level unchanged";
    const held = t.gain_state === "held";
    gainBox.className = "tone-gain" + (held ? " held" : "");
    gainBox.innerHTML =
      `<span class="k">rig gain</span> <span class="v">${sign}${mag} dB</span>` +
      `<div class="sub">${verb} · return drawn ${g > 0 ? "−" : "+"}${mag} dB to match` +
      (held ? " · <b>held</b>: no input above the floor" : ` · from ${t.gain_bins} bins`) +
      `</div>`;
  }

  let scene = null;
  let failed = false;
  let pending = null;
  let live = false;

  function build() {
    if (scene || failed) return;
    try {
      scene = createFingerprint(stage);
      scene.setTone(pending);
      renderScale();
    } catch (e) {
      failed = true;
      legend.hidden = true;
      scaleLine.hidden = true;
      gainBox.hidden = true;
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
      // The tone block is kept even while the scene does not exist, so the
      // first visible frame after activation is the current one rather than
      // whatever happens to arrive next.
      pending = f.tone || null;
      if (scene) scene.setTone(pending);
      renderScale();
      renderGain(pending);

      if (f.kind === "unknown") {
        census.textContent = f.reason;
      } else if (!pending) {
        // A RESULT carries no spectra (payload.result_payload), so there is no
        // input or return to draw. Say so rather than show an empty ring.
        census.textContent = "this frame is a RESULT: it carries no input/return spectra · see LAB";
      } else {
        const c = pending.census;
        census.textContent =
          `input ${c.input_on} · return ${c.return_on} · rig-only ${c.rig_only}` +
          `   of ${c.sections} bins above ${pending.floor_db} dB`;
      }
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

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
//
// 2026-10-18: restyled to LAB's cards at the operator's request ("too hard to
// read"). Same four statements, shorter, at 15-17px instead of 11px, and the
// cards sit beside the ring rather than over it.
const LEGEND = [
  ["sw-warm", "input", "going into the rig · rises <b>above</b> the ring"],
  ["sw-cold", "return", "what came back, level-matched · drops <b>below</b>"],
  ["sw-rig", "rig-only", "energy only the rig produced"],
  ["sw-none", "dark", "quiet on both · measured, not missing"],
];

export function createToneView(root) {
  root.classList.add("tone-view");

  // *** THE GAIN IS THE HEADLINE NUMBER ON THIS SCREEN. ***
  //
  // The return is drawn shifted by it, so without it on screen the picture
  // would hide exactly the thing a player most wants to know: is the rig
  // losing level or adding it. Sign always shown; "held" when the input is
  // below the floor and the last established value is being used.
  const head = document.createElement("header");
  head.className = "tone-head";
  head.innerHTML = `<article class="ld-kpi k-level tone-gain"></article>
    <div class="tone-census"></div>`;
  root.appendChild(head);
  const gainBox = head.querySelector(".tone-gain");
  const census = head.querySelector(".tone-census");
  census.textContent = "connecting…";

  const stage = document.createElement("div");
  stage.className = "tone-stage";
  root.appendChild(stage);

  const foot = document.createElement("footer");
  foot.className = "tone-foot";
  // The LEGEND strings carry deliberate <b> markup and are authored in this
  // file, so they are not escaped. Nothing from the wire reaches this string.
  foot.innerHTML = `<div class="tone-legend">${LEGEND
    .map(([c, name, t]) => `<div><span class="sw ${c}"></span><span><b>${name}</b><br>${t}</span></div>`)
    .join("")}</div><div class="tone-scale"></div>`;
  root.appendChild(foot);
  const legend = foot.querySelector(".tone-legend");
  const scaleLine = foot.querySelector(".tone-scale");

  // Everything about the scale is READ FROM THE SCENE, never restated here, so
  // the legend cannot drift away from the geometry it describes.
  function renderScale() {
    if (!scene || !scene.scale) { scaleLine.textContent = ""; return; }
    const s = scene.scale();
    const span = s.loHz && s.hiHz
      ? `${fmtHz(s.loHz)} → ${fmtHz(s.hiHz)} · ${s.sections} bins, ${Math.round(s.binHz)} Hz each`
      : "waiting for bin geometry";
    scaleLine.innerHTML =
      `<b>Bar length</b> = level above ${s.floorDb} dB · full bar ${s.fullDb} dB · ▲ = louder` +
      ` · dB re FFT 1.0, <i>not dBFS</i><br><b>${span}</b> · below` +
      ` ${s.loHz ? fmtHz(s.loHz) : "the first bin"} not drawn (DC + low strings, TODO-92)`;
  }

  function fmtSigned(v) {
    return (v > 0 ? "+" : v < 0 ? "−" : "±") + Math.abs(v).toFixed(1);
  }

  function tile(cls, valueHtml, sub) {
    gainBox.className = `ld-kpi k-level tone-gain${cls}`;
    gainBox.innerHTML = `<div class="ld-kpi-label">Rig gain</div>
      <div class="ld-kpi-value">${valueHtml}</div><div class="ld-kpi-sub">${sub}</div>`;
  }

  // Sign, size and direction in words, so "−27.1" cannot be misread as a
  // display offset. The shift applied to the return is the gain negated.
  function renderGain(t) {
    if (!t) { gainBox.innerHTML = ""; return; }
    if (t.gain_state === "below_floor" || t.gain_state === "below_floor_held") {
      // A bound, not a value: the return is under the floor in every bin
      // where the input is above it, so all that can be said is how far down
      // it is AT LEAST. Held through the gaps between strums like a gain is,
      // and dimmed when held.
      const held = t.gain_state === "below_floor_held";
      tile(" bound" + (held ? " held" : ""),
        `<span class="ld-num">&lt; ${fmtSigned(t.gain_bound_db)}</span><span class="ld-unit">dB</span>`,
        `return is below the ${t.floor_db} dB floor wherever the input is above it —` +
        ` at least ${Math.abs(t.gain_bound_db).toFixed(1)} dB down. Check the return path.` +
        (held ? ` · <span class="ld-held">held</span>` : ""));
      return;
    }
    if (t.gain_db === null || t.gain_db === undefined) {
      tile("", `<span class="gap">not established yet: play</span>`,
        `needs input above ${t.floor_db} dB · return drawn unmatched`);
      return;
    }
    const g = t.gain_db;
    const mag = Math.abs(g).toFixed(1);
    const sign = g > 0.05 ? "+" : g < -0.05 ? "−" : "±";
    const verb = g > 0.05 ? `gaining ${mag} dB` : g < -0.05 ? `losing ${mag} dB` : "level unchanged";
    const held = t.gain_state === "held";
    tile(held ? " held" : "",
      `<span class="ld-num">${sign}${mag}</span><span class="ld-unit">dB</span>`,
      `${verb} · return drawn ${g > 0 ? "−" : "+"}${mag} dB to match` +
      (held ? ` · <span class="ld-held">held</span>` : ` · from ${t.gain_bins} bins`));
  }

  // The census as chips: how many of the drawn bins carry input, return and
  // rig-only energy, so an empty-looking ring can be told from a broken one.
  function chip(cls, label, n, of) {
    return `<span class="ld-chip tone-chip ${cls}"><i></i>${label}<b>${n}</b><small>/${of}</small></span>`;
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
      head.hidden = true;
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
        census.innerHTML =
          chip("c-in", "input", c.input_on, c.sections) +
          chip("c-out", "return", c.return_on, c.sections) +
          chip("c-rig", "rig-only", c.rig_only, c.sections) +
          `<span class="tone-census-note">bins above ${esc(String(pending.floor_db))} dB</span>`;
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

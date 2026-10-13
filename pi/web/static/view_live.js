// LIVE — the instrument right now: spectrum, levels, state, coverage.
//
// *** TWO DIFFERENT QUANTITIES SHARE THIS SCREEN AND MUST NOT SHARE AN AXIS. ***
//
//   SPECTRUM   per-bin Hann-windowed FFT magnitude, averaged over
//              FFT_AVERAGE_COUNT frames, nominal full scale 1.0 — UNCALIBRATED.
//              Plotted in dB relative to that 1.0. NOT dBFS.
//   METERS     peak_source_dbfs / peak_return_dbfs — a TIME-DOMAIN peak the
//              instrument authored, in dBFS.
//
// On the 2026-09-26 idle capture the loudest spectrum bin is 2.747e-4 (≈ −71 dB
// rel. 1.0) while the instrument reports −63.9 dBFS peak. Both are correct and
// they are not the same measurement. Putting them on one axis would invite a
// reader to treat the 7 dB difference as a finding, so they are kept in separate
// cards with the unit stated on each.
//
// The DOM skeleton is built once and updated in place: re-rendering innerHTML
// every frame would destroy the canvas and its sizing state.

import { card, rows, meter, num, text, gap, esc } from "./ui.js";
import { createSpectrum, FLOOR_DB } from "./spectrum.js";

const UNIT_NOTE = `dB relative to FFT magnitude 1.0 — <b>not dBFS</b>. Hann
  window, averaged bins; the 1.0 reference has never been calibrated against a
  full-scale input on this instrument.`;

export function createLiveView(root) {
  root.innerHTML = `
    <section class="card" id="spec-card">
      <h2>Spectrum — source &amp; return</h2>
      <div class="spectrum-host"></div>
      <div class="spectrum-key">
        <span><i class="k-src"></i>source</span>
        <span><i class="k-ret"></i>return</span>
        <span><i class="k-floor"></i>clipped to display floor</span>
      </div>
      <div id="spec-foot"></div>
    </section>
    <section class="card" id="levels-card"><h2>Levels — time-domain peak</h2>
      <div id="levels-body"></div></section>
    <section class="card" id="state-card"><h2>State</h2>
      <div id="state-body"></div></section>
    <section class="card" id="cov-card"><h2>Coverage</h2>
      <div id="cov-body"></div></section>`;

  const host = root.querySelector(".spectrum-host");
  const foot = root.querySelector("#spec-foot");
  const specCard = root.querySelector("#spec-card");
  const spectrum = createSpectrum(host);

  const set = (id, html) => { root.querySelector(id).innerHTML = html; };

  function noLive(reason) {
    specCard.classList.add("inert");
    spectrum.update(null);
    foot.innerHTML = `<p class="note">${reason}</p>`;
    set("#levels-body", `<p class="note"><b>No live frame.</b> Peak levels are
      LIVE_FRAME fields; a captured RESULT does not contain them, and the last
      live value must not be shown as if it were current.</p>`);
    set("#state-body", `<p class="note">${gap("no live frame")}</p>`);
    set("#cov-body", `<p class="note">${gap("no live frame")}</p>`);
  }

  return {
    update(f) {
      if (f.kind === "unknown") return noLive(esc(f.reason));
      if (f.kind !== "live" || !f.spectra) {
        return noLive(`<b>No live frame.</b> The transport is carrying a captured
          RESULT, which contains no spectrum. See <b>LAB</b> for that result.`);
      }

      specCard.classList.remove("inert");
      const sp = f.spectra;
      spectrum.update(sp);

      const clipped = spectrum.clippedCount();
      const zeros = sp.src.filter((p) => p.value === 0).length
                  + sp.ret.filter((p) => p.value === 0).length;
      const firstUsable = sp.geometry.find((g) => !g.dc);

      foot.innerHTML = `
        <dl class="rows">
          <dt>unit</dt><dd>${UNIT_NOTE}</dd>
          <dt>covered range</dt><dd>${num(firstUsable ? firstUsable.lo_hz : NaN,
            { digits: 0, unit: "Hz", why: "no bins" })} –
            ${num(sp.nyquist_hz, { digits: 0, unit: "Hz" })}</dd>
          <dt>bins plotted</dt><dd>${text(sp.src.length - 1)} of
            ${text(sp.src.length)} <span class="gap">bin 0 spans DC</span></dd>
        </dl>
        <p class="note"><b>Nothing is measured below
          ${esc(Math.round(firstUsable ? firstUsable.lo_hz : 0))} Hz.</b> The
          lowest transmitted bin spans 0 Hz, and the firmware decimates by
          maximum without saying which source bin won, so it cannot be placed on
          a log axis. The hatched region is not a quiet band — it is <i>no
          coverage</i>. A low-E fundamental at 82 Hz falls inside it.</p>
        <p class="note"><b>${esc(clipped.src + clipped.ret)} point(s) drawn at the
          ${esc(FLOOR_DB)} dB display floor</b>${zeros
            ? `, of which ${esc(zeros)} are a measured magnitude of exactly zero`
            : ""}. The floor is where this graph stops, not a noise floor the
          instrument reported. Marked on the baseline.</p>`;

      const a = f.authority || {};
      set("#levels-body", [
        meter("SOURCE", a.peak_source_dbfs, "src", "not reported"),
        meter("RETURN", a.peak_return_dbfs, "ret", "not reported"),
        `<p class="note">A <b>time-domain peak in dBFS</b>, authored by the
         instrument. A different quantity from the spectrum above, which is a
         per-bin averaged magnitude on an uncalibrated reference — do not compare
         the numbers.</p>`,
      ].join(""));

      set("#state-body", rows([
        ["measurement state", text(a.measurement_state)],
        ["transfer-function confidence",
          typeof a.tf_confidence === "number"
            ? num(a.tf_confidence * 100, { digits: 0, unit: "%" })
            : gap("not reported")],
        ["bins at the clamp rail", num(a.tf_clamped_count, { digits: 0 })],
      ]));

      set("#cov-body", rows([
        ["spectrum (source)", text(sp.census_src.text)],
        ["spectrum (return)", text(sp.census_ret.text)],
        ["transfer function", text(f.census_source?.text)],
        ["ring (presentation)", text(f.census_bands?.text)],
      ]) + `<p class="note">The same frame can be fully measured as a spectrum
        and entirely absent as a transfer function. A magnitude has no
        denominator; a transfer function divides by the source, and below the
        source gate there is nothing to divide by.</p>`);
    },

    activate() { spectrum.resize(); },
  };
}

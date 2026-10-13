// Shared rendering helpers for the four views.
//
// *** THE ONLY INTERESTING THING IN THIS FILE IS HOW ABSENCE IS FORMATTED. ***
//
// ADR-005's governing invariant: a renderer may transform how authoritative
// state is displayed, but it may not transform uncertainty, absence, or
// undefined state into asserted measurement.
//
// A formatter is where that rule is easiest to break by accident. `(v ?? 0)`,
// `v.toFixed(1)` on undefined, `|| "--"` — each quietly turns "the instrument
// did not say" into a number or a dash that reads like one. So there is exactly
// one number formatter here, it refuses anything non-finite, and what it
// produces for absence is a WORDED reason, never a digit and never a placeholder
// glyph that could be mistaken for a reading.

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Everything that reaches innerHTML goes through this first. */
export function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ESC[c]);
}

/** Absence, stated. Never "--", never "0", never blank. */
export function gap(why) {
  return `<span class="gap">${esc(why)}</span>`;
}

/**
 * A number the Teensy authored, or a worded absence.
 *
 * `why` says WHY the value is missing, because "not carried by /api/frame yet"
 * and "the instrument reported nothing" are different statements and the
 * operator is entitled to know which one applies.
 */
export function num(v, { digits = 1, unit = "", why = "not reported", cls = "" } = {}) {
  if (typeof v !== "number" || !Number.isFinite(v)) return gap(why);
  const t = `${v.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
  return `<span class="num${cls ? ` ${cls}` : ""}">${esc(t)}</span>`;
}

/** A string the Teensy authored, printed verbatim, or a worded absence. */
export function text(v, { why = "not reported", cls = "" } = {}) {
  if (v === null || v === undefined || v === "") return gap(why);
  return cls ? `<span class="${cls}">${esc(v)}</span>` : esc(v);
}

/** A boolean the Teensy authored. `null`/`undefined` is NOT false. */
export function flag(v, yes, no, { why = "not reported" } = {}) {
  if (v === null || v === undefined) return gap(why);
  return v ? `<span class="good">${esc(yes)}</span>`
           : `<span class="warn">${esc(no)}</span>`;
}

/** `[[label, valueHtml], …]` -> a definition list. Values are pre-escaped. */
export function rows(pairs) {
  return `<dl class="rows">${pairs
    .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`)
    .join("")}</dl>`;
}

export function card(title, bodyHtml) {
  return `<section class="card"><h2>${esc(title)}</h2>${bodyHtml}</section>`;
}

/**
 * A dBFS peak as a bar.
 *
 * The bar's LENGTH is a presentation transform of one Teensy-authored scalar
 * (ADR-005 §7 permits exactly this). The floor is a drawing choice, not a
 * measurement claim, so it is named rather than hidden — and when the scalar is
 * absent the bar is not drawn at all rather than drawn empty, because an empty
 * bar reads as silence and absence is not silence.
 */
export const METER_FLOOR_DBFS = -72;

export function meter(label, dbfs, kind, why) {
  if (typeof dbfs !== "number" || !Number.isFinite(dbfs)) {
    return `<div class="meter">
      <div class="meter-head"><span class="meter-label">${esc(label)}</span>
        <span class="meter-value">${gap(why)}</span></div>
    </div>`;
  }
  const pct = Math.max(0, Math.min(1, (dbfs - METER_FLOOR_DBFS) / -METER_FLOOR_DBFS));
  const hot = dbfs > -1;
  return `<div class="meter">
    <div class="meter-head">
      <span class="meter-label">${esc(label)}</span>
      <span class="meter-value${hot ? " bad" : ""}">${esc(dbfs.toFixed(1))} dBFS</span>
    </div>
    <div class="meter-track"><div class="meter-fill ${esc(kind)}" style="width:${(pct * 100).toFixed(2)}%"></div></div>
  </div>`;
}

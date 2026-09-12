// =============================================================================
// timing_probe.cpp  —  Guitar Rig Analyzer
// =============================================================================
// T1 acceptance harness. See timing_probe.h for what this measures and why the
// pass condition is comparative rather than absolute.
//
// Deliberately compiled in for ALL DISPLAY_TARGETs. The control run is
// DISPLAY_TARGET_NONE, so the harness must exist and behave identically there —
// guarding it to the Pi build would make the control run unmeasurable, which is
// the one thing that would render the whole test meaningless.
// =============================================================================

#include "timing_probe.h"
#include "presentation.h"
#include <Audio.h>      // AudioMemoryUsage / AudioMemoryUsageMax

// =============================================================================
// STATE
// =============================================================================

static uint32_t s_window_start_ms   = 0;

// Block timing
static uint32_t s_last_block_us     = 0;
static bool     s_have_last_block   = false;
static uint32_t s_blocks            = 0;
static uint64_t s_block_us_total    = 0;
static uint32_t s_block_us_max      = 0;
static uint32_t s_block_us_min      = 0xFFFFFFFFu;

// Skipped analysis blocks, from gaps in the canonical block counter
static uint32_t s_last_block_number = 0;
static bool     s_have_block_number = false;
static uint32_t s_skipped_blocks    = 0;
static uint32_t s_skip_events       = 0;
static uint32_t s_largest_gap       = 0;

// Loop iteration timing
static uint32_t s_loop_iters        = 0;
static uint64_t s_loop_us_total     = 0;
static uint32_t s_loop_us_max       = 0;

// =============================================================================

void timingProbe_reset() {
    s_window_start_ms = millis();

    s_last_block_us   = 0;
    s_have_last_block = false;
    s_blocks          = 0;
    s_block_us_total  = 0;
    s_block_us_max    = 0;
    s_block_us_min    = 0xFFFFFFFFu;

    s_last_block_number = 0;
    s_have_block_number = false;
    s_skipped_blocks    = 0;
    s_skip_events       = 0;
    s_largest_gap       = 0;

    s_loop_iters    = 0;
    s_loop_us_total = 0;
    s_loop_us_max   = 0;

    // Reset the library's audio high-water so it reflects THIS window only.
    // Without this, a spike during boot would contaminate every later run and
    // the four runs would not be comparable.
    AudioMemoryUsageMaxReset();
}

void timingProbe_noteBlock(uint32_t output_block_number) {
    const uint32_t now = micros();

    if (s_have_last_block) {
        const uint32_t dt = now - s_last_block_us;
        s_blocks++;
        s_block_us_total += dt;
        if (dt > s_block_us_max) s_block_us_max = dt;
        if (dt < s_block_us_min) s_block_us_min = dt;
    }
    s_last_block_us   = now;
    s_have_last_block = true;

    // Skipped-block detection. The block counter is the system's canonical
    // monotonic timebase, so a gap > 1 means an analysis block was produced that
    // the main loop never processed. This is measurement disturbance, full stop —
    // not a display symptom — and it is the metric that must read zero.
    if (s_have_block_number) {
        const uint32_t gap = output_block_number - s_last_block_number;
        if (gap > 1) {
            s_skipped_blocks += (gap - 1);
            s_skip_events++;
            if (gap > s_largest_gap) s_largest_gap = gap;
        }
    }
    s_last_block_number = output_block_number;
    s_have_block_number = true;
}

void timingProbe_noteLoopIteration(uint32_t duration_us) {
    s_loop_iters++;
    s_loop_us_total += duration_us;
    if (duration_us > s_loop_us_max) s_loop_us_max = duration_us;
}

void timingProbe_report() {
    const uint32_t window_ms = millis() - s_window_start_ms;

    const float blk_mean_ms = s_blocks
        ? ((float)(s_block_us_total / (double)s_blocks) / 1000.0f) : 0.0f;
    const float blk_max_ms  = s_block_us_max / 1000.0f;
    const float blk_min_ms  = (s_block_us_min == 0xFFFFFFFFu)
        ? 0.0f : (s_block_us_min / 1000.0f);
    const float loop_mean_us = s_loop_iters
        ? ((float)(s_loop_us_total / (double)s_loop_iters)) : 0.0f;

    Serial.println();
    Serial.println("[T1] ================ T1 ACCEPTANCE REPORT ================");
    Serial.printf ("[T1] display_target=%s\n", presentation_backendName());
    Serial.printf ("[T1] firmware=%s protocol=%d\n",
                       FIRMWARE_VERSION, PI_PROTOCOL_VERSION);
    Serial.printf ("[T1] window_ms=%lu\n", (unsigned long)window_ms);

    // ---- ACQUISITION: the side that must not move ----
    Serial.println("[T1] --- acquisition (must be indistinguishable across runs) ---");
    Serial.printf ("[T1] block_n=%lu\n", (unsigned long)s_blocks);
    Serial.printf ("[T1] block_ms_mean=%.3f\n", blk_mean_ms);
    Serial.printf ("[T1] block_ms_max=%.3f\n",  blk_max_ms);
    Serial.printf ("[T1] block_ms_min=%.3f\n",  blk_min_ms);
    Serial.printf ("[T1] block_ms_spread=%.3f\n", blk_max_ms - blk_min_ms);

    // The metric that must read zero.
    Serial.printf ("[T1] blocks_skipped=%lu\n", (unsigned long)s_skipped_blocks);
    Serial.printf ("[T1] skip_events=%lu\n",    (unsigned long)s_skip_events);
    Serial.printf ("[T1] largest_block_gap=%lu\n", (unsigned long)s_largest_gap);

    Serial.printf ("[T1] loop_iters=%lu\n",     (unsigned long)s_loop_iters);
    Serial.printf ("[T1] loop_us_max=%lu\n",    (unsigned long)s_loop_us_max);
    Serial.printf ("[T1] loop_us_mean=%.1f\n",  loop_mean_us);

    // Audio buffer pressure. NOTE THE LIMITATION, stated rather than glossed:
    // this is the Audio library's GLOBAL block high-water, not a per-queue
    // overrun counter. audio_capture does not expose a dropped-block count, so
    // blocks_skipped above is the authoritative overrun evidence and this is
    // corroborating pressure data. Do not report it as "capture overruns".
    Serial.printf ("[T1] audio_blocks_used=%u\n",     (unsigned)AudioMemoryUsage());
    Serial.printf ("[T1] audio_blocks_high_water=%u\n", (unsigned)AudioMemoryUsageMax());

    // ---- TRANSPORT: the side that is allowed to degrade ----
    Serial.println("[T1] --- transport (allowed to lose data; must not block) ---");
    presentation_printDiagnostics();

    // ---- The pass condition, restated where it cannot be missed ----
    Serial.println("[T1] --- PASS CONDITION ---");
    Serial.println("[T1] PASS requires block_ms_mean/max/spread and blocks_skipped");
    Serial.println("[T1] to be INDISTINGUISHABLE from the DISPLAY_TARGET_NONE");
    Serial.println("[T1] control run. blocks_skipped MUST be 0 in every run.");
    Serial.println("[T1] A small presentation call time is NOT a pass: a fast call");
    Serial.println("[T1] can still disturb timing via ISR load, DMA contention or");
    Serial.println("[T1] buffer servicing, none of which appear in a call duration.");
    Serial.println("[T1] Transport drops are EXPECTED and acceptable in runs 3 and 4.");
    Serial.println("[T1] =====================================================");
    Serial.println();
}

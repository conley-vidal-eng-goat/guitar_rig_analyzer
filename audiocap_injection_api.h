// =============================================================================
// NEW API — audioCap_setInjectionMode()  (add to audio_capture.h, v0.6.0)
// =============================================================================
// This function is added to audio_capture.h as part of the v0.6 signal_router
// integration. It controls the output send mixer (s_mixer_send) which selects
// between SOURCE_NODE monitoring and generator injection on I2S out channel 0.
//
// Place this in audio_capture.h after the existing audioCap_setInputGain()
// declaration.
// =============================================================================

// -----------------------------------------------------------------------------
// audioCap_setInjectionMode(enabled)
// Controls the output send mixer (s_mixer_send).
//
// When enabled = true:
//   s_mixer_send slot 0 (SOURCE monitoring) = 0.0
//   s_mixer_send slot 1 (generator)         = 1.0
//   I2S out L carries the generator signal → SGTL5000 line-out L → Rig Send
//   Headphone L also carries the generator (user hears stimulus in left ear)
//
// When enabled = false:
//   s_mixer_send slot 0 (SOURCE monitoring) = 1.0
//   s_mixer_send slot 1 (generator)         = 0.0
//   I2S out L carries SOURCE_NODE monitoring (normal)
//
// *** SILENT OPERATION — NO ROUTE_CHANGED EVENT ***
// This function does NOT latch a ROUTE_CHANGED event and does NOT clear
// the accumulator. It is a pure output-path mixer gain switch.
//
// Rationale: the injection switch changes what goes to Rig Send (output),
// not what SOURCE_NODE and RETURN_NODE are measuring (input). The capture
// pipeline — mixers, FFT objects, record queues — is unaffected. Raising
// ROUTE_CHANGED here would cause internal-stimulus measurements to abort
// themselves when they enable their own stimulus injection.
//
// The caller (signal_router, called from measurement_engine during arm
// and teardown) is responsible for ensuring this is called only at safe
// boundaries: during arm() before ARMED, and during teardown after
// capture has ended. It is never called mid-accumulation.
//
// Unexpected topology changes (jack removal) are still detected by
// signalRouter_update() and propagated through the normal
// audioEngine_setRoute() → ROUTE_CHANGED invalidation chain.
// -----------------------------------------------------------------------------
// void audioCap_setInjectionMode(bool enabled);

# signal_router — v0.6 Design Contract

## Physical Signal Flow

```
                                                    ┌──────────────┐
Guitar ──→ [INSTRUMENT IN] ──→ OPA1642 buffer ──┬──→│ SOURCE_NODE  │──→ SGTL5000 Line-In L
                                                 │   │  (tap point) │
                                                 │   └──────────────┘
                                                 │
                                                 └──→ [RELAY_SEND] ─── pos A: buffer out ──→ [RIG SEND jack]
                                                           │
                                              SGTL5000 ←── pos B: codec line-out L
                                              Line-Out L   (generator injection)


DUT output ──→ [RIG RETURN TS jack]  ──→ ┐
                                          ├─ [RELAY_RETURN] ──→ SGTL5000 Line-In R ──→ RETURN_NODE
              [RIG RETURN XLR jack] ──→ ┘
              (balanced → diff receiver)


SGTL5000 Headphone Out:
  Normal mode:     L = SOURCE_NODE,  R = RETURN_NODE
  Injection mode:  L = generator,    R = RETURN_NODE
  (Monitor mode selection is a future enhancement over this base.)
```

## Relay Truth Table

Two relays, each SPDT, controlled by one GPIO each.

| Relay | GPIO LOW (de-energised, default) | GPIO HIGH (energised) |
|-------|------|------|
| RELAY_SEND | Position A: buffer output → Rig Send (normal) | Position B: codec line-out L → Rig Send (injection) |
| RELAY_RETURN | Position A: TS return → codec line-in R | Position B: XLR return → codec line-in R |

**Default power-on state:** Both relays de-energised.
- Rig Send carries the buffered instrument signal (safe — no generator surprises)
- Return path is TS (most common connection for guitar rigs)

## Jack Detection

Four jack-detect switches, active LOW (switch closes to ground when jack inserted).
Each GPIO has an internal pull-up enabled.

| Jack | GPIO reads LOW when | GPIO reads HIGH when |
|------|-------|--------|
| INSTRUMENT_IN | Jack inserted | No jack |
| RIG_SEND | Jack inserted | No jack |
| RETURN_TS | Jack inserted | No jack |
| RETURN_XLR | Jack inserted | No jack |

**Debounce:** 50 ms minimum on all detect inputs. Jack insertion is a mechanical event
with contact bounce; reading immediately after a transition produces false states.

## Routing Policy — Return Source Selection

| return_ts detected | return_xlr detected | user override | RELAY_RETURN state | RETURN_NODE source |
|----|----|----|----|----|
| 0 | 0 | any | A (TS, default) | NONE — no return signal |
| 1 | 0 | any | A (TS) | TS jack |
| 0 | 1 | any | B (XLR) | XLR jack |
| 1 | 1 | NONE | B (XLR) | XLR jack (default priority) |
| 1 | 1 | TS | A (TS) | TS jack (user override) |
| 1 | 1 | XLR | B (XLR) | XLR jack (user override) |

**XLR default priority rationale:** When both are inserted, XLR is preferred because
balanced connections are less susceptible to noise — the user likely connected XLR for a
reason. User override (via Serial command or future touch UI) reverses this.

## Routing Policy — Generator Injection

| rig_send detected | injection requested | RELAY_SEND state | Audio path |
|---|---|---|---|
| 0 | any | A (buffer, default) | Buffer → Rig Send (if anything is plugged in, it gets the guitar) |
| 1 | false | A (buffer) | Buffer → Rig Send (normal guitar signal) |
| 1 | true | B (codec out) | Generator → codec line-out L → Rig Send |

**Arming guard:** If a measurement with internal stimulus is armed but rig_send is not
detected, measurementEngine_arm() should be rejected with a clear error.
signal_router exposes `signalRouter_canInject()` for this check.

## Routing Policy — Measurement Arm Validity

| Stimulus type | Minimum jack requirements | Rejection reason if unmet |
|---|---|---|
| EXTERNAL | At least one return (TS or XLR) | "No return path — connect rig return" |
| INTERNAL_* | At least one return AND rig_send | "No send path — connect rig send jack" or "No return path" |

These checks are advisory — signal_router reports the status, measurement_engine
decides whether to arm based on it.

## Audio Graph Modification (audio_capture.cpp)

The current output wiring:
```
s_mixer_src ──→ s_i2s_out[0]   (SOURCE monitoring → headphone L)
s_mixer_ret ──→ s_i2s_out[1]   (RETURN monitoring → headphone R)
```

Must change to:
```
s_mixer_src ──→ s_mixer_send slot 0  ─┐
                                       ├──→ s_mixer_send ──→ s_i2s_out[0]
s_gen_mixer ──→ s_mixer_send slot 1  ─┘
                                       (headphone L / line-out L)

s_mixer_ret ──→ s_i2s_out[1]          (headphone R — unchanged)
```

`s_mixer_send` is a new AudioMixer4 owned by audio_capture.
- Normal mode: slot 0 = 1.0 (SOURCE monitoring), slot 1 = 0.0
- Injection mode: slot 0 = 0.0, slot 1 = 1.0 (generator drives line-out L)

**Requires:** `s_gen_mixer` in signal_generator.cpp made non-static (same pattern as
`s_mixer_ret`), so audio_capture.cpp can wire to it.

**New public API on audio_capture:**
```c
void audioCap_setInjectionMode(bool enabled);
```
Sets s_mixer_send gains. When enabled, also raises a ROUTE_CHANGED event
(injection mode change invalidates any in-progress measurement).

## State Machine

signal_router has no complex state machine. It is a reactive policy module:

```
signalRouter_update() called once per main loop iteration:
  1. Read jack detect GPIOs (with debounce)
  2. If any detect state changed:
     a. Recompute return source (apply policy table)
     b. If return source changed → set RELAY_RETURN → call audioEngine_setRoute()
     c. If a jack required for the current route is removed → invalidate route
  3. Injection is controlled explicitly by signalRouter_setInjectionEnabled()
     (called by measurement_engine at ARMED/CAPTURE entry/exit)
```

**Route changes from signal_router always go through the existing chain:**
```
signalRouter detects change
  → sets relays
  → calls audioEngine_setRoute(new_route)
    → calls audioCap_notifyRouteChanged()
      → ROUTE_CHANGED event latched
        → main loop → measurementEngine_notifyRouteChanged()
```

This preserves the existing invalidation contract exactly.

## Module Ownership Summary

| Module | Owns | Does NOT own |
|--------|------|-------------|
| signal_router | Relay GPIOs, jack detect GPIOs, routing policy, monitor mode state, injection request state | Audio hardware, codec, I2S, mixers, measurement, display |
| audio_capture | I2S, SGTL5000, all mixers (including s_mixer_send), FFT/peak/queue objects, block timing | Routing decisions, relay hardware |
| signal_generator | DDS oscillator state, s_gen_mixer, synthesis objects | When to start/stop, injection relay state |
| measurement_engine | Measurement state machine, accumulator, result | Hardware routing, audio capture |

## Required Changes to Existing Modules

1. **audio_capture.cpp:** Add `s_mixer_send`, rewire output path, expose `audioCap_setInjectionMode()`.
2. **signal_generator.cpp:** Make `s_gen_mixer` non-static (add extern declaration pattern like `s_mixer_ret`).
3. **measurement_engine.cpp:** Before arming with internal stimulus, check `signalRouter_canInject()`. At CAPTURE entry, call `signalRouter_setInjectionEnabled(true)`. At CAPTURE exit (any path), call `signalRouter_setInjectionEnabled(false)`.
4. **guitar_rig_analyzer.txt (main loop):** Call `signalRouter_update()` once per iteration. Handle jack-change events in Serial diagnostics.
5. **config.h:** Add GPIO pin assignments for relays and jack detect switches.

## Implementation Order

**Phase A — Minimum viable (v0.6.0):**
- signal_router.h / signal_router.cpp: jack detect + relay control + return source policy
- audio_capture.cpp: add s_mixer_send + audioCap_setInjectionMode()
- signal_generator.cpp: make s_gen_mixer non-static
- measurement_engine.cpp: injection guard at arm() + enable/disable at CAPTURE entry/exit
- config.h: GPIO pin constants
- guitar_rig_analyzer.txt: signalRouter_init/update in setup/loop

**Phase B — Monitor policy (v0.6.1):**
- signalRouter_setMonitorMode(SOURCE / RETURN / BLEND)
- Headphone output mix control via s_mixer_send and s_mixer_ret gains

**Phase C — Auto-routing and user override (v0.6.2):**
- signalRouter_setReturnSource(TS / XLR / AUTO)
- Reject illegal combinations
- Serial commands for route override

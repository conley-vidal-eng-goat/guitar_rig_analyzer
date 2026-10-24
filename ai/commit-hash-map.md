# Commit hash map

On 2026-10-24 this repository's git history was rewritten to correct how the
builder is named in the early records. Every commit hash changed; the code,
dates and authorship did not.

Commit hashes cited in the docs, code comments and tests were updated to the
new values. **Old hashes still appear in three places,** on purpose:

- raw captures in [`evidence/`](evidence/) (logs, `.txt` run records), which are
  kept exactly as recorded;
- names of folders on the Raspberry Pi, such as `~/gra-ui-backup-39a7d55` or
  `~/gra-stage-cc994de`, which are real directories;
- the Pi's own copy of the repository.

Use this table to translate. Newest first.

| Old | New | Commit |
|---|---|---|
| `782ee98` | `b9871a4` | docs(pi): the README describes the Pi as it is now |
| `3ac5f8e` | `3b7d982` | docs: rewrite the README and the two disclosure pages in plain language |
| `a7219b4` | `3ca2e7d` | docs: the journal and todo name the builder correctly |
| `999775d` | `c283572` | refactor: move the firmware into firmware/guitar_rig_analyzer/ |
| `4ba1d28` | `ebac1f0` | chore(firmware): remove two patch-note headers nothing includes |
| `2648f2f` | `720c1bd` | fix(web): TONE ring runs edge to edge so the outermost labels are not cut off |
| `bb58c2d` | `508bb0f` | feat(web): TONE readouts restyled to LAB's cards — larger, brighter, beside the ring |
| `2e9ae27` | `55be24a` | fix(web): LAB — what the first real-rig test on the Pi found |
| `ed55d61` | `535adcb` | feat(web): LAB shows what the rig changed — Pi-computed spectral, EQ, dynamics and noise diagnostics |
| `4e25337` | `a9e6762` | evidence(pi): return restored; TONE draws a level-matched return on the panel for the first time |
| `6cc7256` | `3f6f0ed` | todo(93): touch test puts the open between the LINE IN R pad and the codec |
| `94e2f46` | `033279a` | todo(93): loopback and headphone tests both show LINE IN R receiving nothing |
| `a5ce794` | `92dfac5` | todo(93): return fault narrowed to the 16a -> LINE IN R conductor; firmware and route ruled out |
| `c3e3267` | `819b37f` | evidence(pi): TONE input-over-return live on the panel; the return is not carrying the guitar |
| `afd1944` | `2302156` | fix(web): TONE holds a below-floor bound through the gaps between strums |
| `bc3d4b9` | `9dfe254` | feat(web): TONE draws the input over the level-matched return |
| `39a7d55` | `16d3d7a` | feat(web): TONE becomes a chromatic circle — 53 semitones, one full turn |
| `afa4780` | `f62c9fa` | feat(web): TONE shows a guitar-range window, labelled, with a decay trail |
| `976dd4c` | `92db7d0` | feat(web): LIVE polls at 20 Hz, and a guard so a faster poll cannot lie |
| `5bf79a0` | `c16edea` | feat(pi): the Pi boots into the web kiosk — ADR-005 §2 closed |
| `651dbaa` | `b5019c7` | evidence(pi): the web kiosk survived a Teensy power-cycle — ADR-005 §2.4 met |
| `b68d648` | `1278253` | docs: six precision corrections from the builder's review |
| `cfeee8b` | `1f357da` | ai(drafts): preserve two unintegrated journal drafts, contents unchanged |
| `3f2705a` | `49cf748` | docs: the motivation in Conley's words, and his own sentence about using AI |
| `b42c784` | `a70c7cf` | docs(runbook): three links pointed at files that are not in this repository |
| `2c0561f` | `afeb287` | docs(readme): rewrite as a reviewer's entry point, and stop contradicting the code |
| `122b010` | `72bf302` | docs: append attribution notes to the two documents signed with the account name |
| `c9e6e73` | `eafe231` | docs: who built this, and who wrote the code |
| `7ad7e0f` | `1162e88` | evidence: preserve the 10-08 buffer DC checkpoint and the 10-13 live telemetry capture |
| `07c51bb` | `1a3c980` | docs(asbuilt): the relay blocks are drawn, and a row leaves FUTURE_ITEMS only when its drawing exists |
| `7ee100e` | `d4e0f63` | docs: the Headrush A/B procedure, and why a guitar cannot be its stimulus |
| `db46cb3` | `68c8894` | docs(pi): verification — the pulse measured at 15.6%, the framing counter flat, and three things still unseen |
| `72048e3` | `3ab5fd3` | feat(web): LIVE polls at the rate the measurement said it could, and TONE gets its finish back |
| `816cdc4` | `69ddaef` | docs(pi): Gate 4 §6 — the web client rendered a live Teensy frame on the panel |
| `93a4d58` | `dd8ebf9` | docs(pi): Gate 4 §5 — the 4096-byte buffer hypothesis, falsified by measurement |
| `80e5b09` | `a8a8e86` | docs(pi): Gate 4 §4 — 36481 B/s, zero CRC failures, zero interior discards, with the capture itself |
| `6161b5b` | `a5c2319` | docs(pi): Gate 4 §2 baseline, and the instrument's power hangs off a laptop USB port |
| `3ad57d9` | `2a4c40d` | docs(pi): Gate 4 §1 executed — the keyboard-free recovery works, and reading the live environment found what the draft had missed |
| `08dc450` | `e81b16d` | docs(pi): a bench repair recorded as RPT, a reset the instrument cannot explain, and the handoff procedure |
| `3399a94` | `b10cc67` | fix(pi): the kiosk launcher supervises instead of vanishing into exec |
| `cc994de` | `801fe28` | docs(pi): resuming from cold — a staged procedure, and the boot fact it is built around |
| `0a14d46` | `cdba42d` | feat(web): LAB prints the instrument's own findings, and nothing of its own |
| `26bf173` | `c770053` | feat(web): the transport stops withholding what the Teensy already said |
| `7dd6fbb` | `9b61ce9` | feat(pi): the LIVE spectrum — 127 real bins, honest units, and a floor that says so |
| `4f0d57e` | `b6d39f0` | feat(pi): the FFT presentation contract — a spectrum is not a transfer function |
| `96158b7` | `1bbf97a` | evidence(pi): a finger changes the tab — touch navigation confirmed |
| `a232007` | `aa585b9` | evidence(pi): the four-tab shell on the panel — 60 fps, and the pause measured |
| `cc7b704` | `2cf3593` | feat(pi): four-tab shell, and the camera stops guessing the viewport |
| `aa073a6` | `f1e77ef` | evidence(pi): Chromium on the real GPU at 60 fps, and two defects macOS cannot show |
| `9326190` | `f7d2331` | feat(pi): minimal kiosk launcher and a display/GPU diagnostics page |
| `1699f9e` | `0d86957` | docs(ui): import the design sources, and rank them against each other |
| `8fbc0d2` | `c910eaa` | docs(bench): 2026-10-12 closeout — a guitar is audible through the analyzer |
| `66a8529` | `8074389` | evidence(web): two markers and an empty ring, from real captures |
| `c1f47bc` | `6162d65` | feat(pi): web renderer slice 1 — real bytes to ToneFingerprintSplit |
| `d6bb692` | `cbd22c9` | docs(adr): ADR-005 §1a — the UI framework is deliberately unspecified |
| `f87b066` | `4345ebf` | refactor(pi): Tk renderer consumes the shared contract |
| `06fec13` | `f4c20a5` | feat(pi): presentation_semantics — one classification layer, proven on real bytes |
| `0a392a1` | `1edfa3a` | docs(adr): ADR-005 — kiosk web renderer, and semantics as a shared contract |
| `ae79160` | `b84c66f` | docs(readme): lead with what the instrument does and what is not proven |
| `995da78` | `7d07a73` | evidence(pi): power-on to live analyzer, in two reboots |
| `d4eca26` | `09bea8a` | docs(pi): user-level labwc autostart, reversible with one rm |
| `7117344` | `e19c06c` | evidence(pi): energised live TF on the display — the portfolio pair is complete |
| `4935c57` | `24b583c` | evidence(pi): UI reads the live UART on the physical display |
| `df984ff` | `3c26bf9` | evidence(phase10): RESULT transport on hardware; T1 Run 2 stops on a broken metric |
| `c7e1581` | `41af7dc` | feat(pi): production UI first slice, rendering real Teensy telemetry |
| `518ab30` | `d32dc2f` | feat(pi): judge discarded bytes by position, decode Teensy text as UTF-8 |
| `450f368` | `f9948da` | feat(pi): report RESULT arrays as analog observation, never a verdict |
| `63604e9` | `5d37d58` | evidence(phase10): Step A -- 71 ABORTED/TIMEOUT snapshots, zero live frames |
| `0f7f2dd` | `4436237` | feat(pi): --timeline, on Teensy audio time rather than byte position |
| `36a216d` | `6fe6dd9` | test(phase10): CRC rejection and unknown-type tolerance on real bytes |
| `eab3396` | `bf29549` | evidence(phase10): 30 s receive capture; idle RX has sufficient evidence |
| `7f908d8` | `b517e56` | evidence(phase10): first real Teensy -> Pi 5 transport capture |
| `ce682cd` | `86fb78a` | docs(todo): record Phase 10 producer-side complete, blocked on Pi access |
| `1404da3` | `ad87a90` | feat(pi): capture and replay tooling for the first hardware byte stream |
| `f517bd1` | `63fb707` | evidence(phase10): dcfbffa flashed; all four producers live on hardware |
| `8e6c9c6` | `8a38e05` | evidence(firmware): archive the dcfbffa _PI flash candidate |
| `26f2bee` | `dcfbffa` | docs(phase10): reconcile runbook with the final producer contract |
| `10f3ccb` | `42c9907` | fix: stop ROUTER_STATUS transmitting fabricated jack presence |
| `0a70bea` | `48b2ef5` | feat: make measurement state observable to a reconnecting Pi |
| `a75aef2` | `361bc3b` | fix: enforce transport atomicity while a RESULT drains |
| `7817095` | `d1033ee` | feat: add Pi receiver state model |
| `5a7a2ae` | `924b16b` | feat: make Pi HELLO session recoverable |
| `641333d` | `01311c2` | docs(plan): decouple prototype build from Test 4 fixture |
| `e6256e3` | `bcdb4d9` | docs(phase9): reconcile validation records after A C and D |
| `cec814a` | `1f8c7c1` | fix(validation): remove post-hoc tolerance tuning advice |
| `8878bb4` | `0a530d7` | fix(validation): require a characterized Test 3 offset |
| `119a737` | `8daddfc` | docs(phase9): replace the Y-split operator topology with the approved external loopback |
| `0d8d715` | `5082e4a` | docs(records): withdraw the codec-input assumption; freeze Test 4 fixture topology |
| `6650859` | `d3ca33c` | docs(records): document Test 4 criterion defect and fixture analysis |
| `e88f6a4` | `0b738e4` | docs(records): record repository move out of iCloud and the returned-PDF finding |
| `d8e1c9a` | `61a9133` | docs(records): record Phase 9 fixture topology and three physical findings |
| `aec99bf` | `4e347d6` | docs(router): correct stale pin-15 driver status in TS-at-boot comment |
| `928ee86` | `2f4aeee` | docs(records): close TODO-50 on its existing proof line |
| `08f50cf` | `b93f689` | docs(records): close TODO-27 on identified hardware evidence |
| `44c4680` | `029ac05` | fix(timing): use FFT hop consistently for result cadence |
| `7cc77d9` | `18dc2cf` | docs(records): close TODO-53 on positive firmware identity |
| `399e54b` | `4ab4d8e` | fix(firmware): make build identity observable after boot |
| `57dcdc1` | `8a77d5c` | chore(firmware): add permanent boot build identity |
| `7532c7d` | `9f41a9e` | docs(records): close TODO-52's hazard on bench evidence |
| `3fd9f27` | `1a3840a` | docs(records): reconcile Phase 9 TODOs with committed work |
| `49cf75a` | `60bca7f` | docs(runbook): finish C1-01 correction across diagram and background |
| `b6db3d6` | `47edb0f` | docs(runbook): v3.1 correction pass — thirteen build-found defects |
| `b275852` | `61fc0dc` | fix(diagnostics): EXPECTED_BLOCK_MS must use the FFT hop, not the window |
| `3fdde97` | `3c1c59e` | fix(router): sync the route description at boot without a route transition |
| `b2cdb4f` | `65c9a80` | fix(validation): make the harness prompt distinguish consent from cancel |
| `f1b13ed` | `d5d8fe4` | docs: record Rig Send jack and first valid transfer function |
| `c594d9c` | `5419591` | docs: record Phase 8 XLR signal path built and contact-proven |
| `8ed0e11` | `5d78983` | docs: correct Phase 7 jack topology; record relay A/B and open anomalies |
| `62f9d96` | `3258707` | docs: record Phase 7 driver and contact transfer proven |
| `0b675f3` | `17fea95` | docs: record Phase 7 driver build and flash mismatch |
| `98daf6f` | `dae826f` | docs: correct Phase 6 relay coil polarity |
| `dcfda99` | `4ae8c86` | docs: record ADR-004 implementation evidence |
| `3460080` | `ae02a8b` | feat(router): make return source operator-selected |
| `e9ebd75` | `9e41943` | docs(adr): make return source operator-selected |
| `429dcbb` | `dad208e` | ai: archive Phase 6 diode photo; close TODO-47 — original relay is also TQ2-5V |
| `28526d6` | `094885e` | fix(phase6): complete Phase 6 relay driver bring-up |
| `ff6a1b9` | `a480db8` | ai: broaden source-of-truth rule to requirements; flag TODO-23/32 now in     Phase 5's critical path |
| `6550d57` | `ab7e93f` | docs(adr): ADR-003 — jack presence detection is a UX feature, not a            hardware requirement; Phase 5 re-scoped, buy nothing |
| `ab93a98` | `23a178c` | ai: manufacturer search — Switchcraft catalogue confirms the #11 finding;     12B is the candidate; datasheets cannot settle the ring/sleeve question |
| `f652894` | `622f5bb` | ai: CORRECTION — "one D2F-01L exists" was unsupported; assume on hand = 0 |
| `96221ad` | `7471a11` | ai: DECISION — J4 presence detection via independent COM-NC microswitch |
| `b7ed320` | `4f2e9bb` | ai: CORRECTION — installed J4 has no switched contact; Phase 5 detect is     blocked on parts |
| `7b224a6` | `9eb5454` | docs(adr): ADR-002 — generalise the invariant's rationale beyond GPIO pull-ups |
| `4bda8b2` | `6ddbfb9` | docs(adr): ADR-002 — state the constraint as impedance conflict, not            galvanic connection |
| `7d30a3c` | `e72c7dc` | docs(adr): ADR-002 — jack presence sensing must be independent of the            audio signal node |
| `d32a82c` | `b31dcd6` | ai: close the "DC reference on TIP" option with numbers; pin TS terminology |
| `ecdf94e` | `18ede45` | ai: Phase 5 detect null result — conductor never built, and the     prescribed design cannot work on this circuit |
| `b32d04a` | `e5b702b` | feat(phase5): wire jack detect into the live path, per-connector polarity |
| `8c903b1` | `3325a5c` | ai(evidence): TODO-43 closure screenshot with conditions and caveats |
| `51b9737` | `9f6955b` | ai: TODO-43 CLOSED — 1x probe on a 10x-configured scope channel |
| `3d5012e` | `d8a1e51` | ai: TODO-43 — expectation verified sound; suspicion moves to the measured voltage |
| `d63a753` | `2aebbbb` | fix(sgtl): SYS_FS and MCLK_FREQ were swapped in the CLK_CTRL decode |
| `8422d3f` | `7c7cc05` | diagnostic(sgtl): add CHIP_REF_CTRL, CHIP_LINREG_CTRL, CHIP_CLK_CTRL |
| `d57baaf` | `a06f578` | ai(evidence): TODO-43 anomaly reproduces post-stack on new firmware |
| `b76d6bc` | `e2d72f4` | ai: capture SGTL register dump; journal the failed-correction lesson |
| `a298f1c` | `ace5e7c` | diagnostic(sgtl): add read-only codec register dump |
| `358a988` | `1843c30` | test(41B): PASS — 324/324 clean windows, zero detector-v1 outliers on either node |
| `c7cea1f` | `f042e3c` | docs(todo): TODO-42 — generator contaminates the RETURN measurement path |
| `d981af6` | `f6c17dd` | docs(ai): front end costs 5.07 dB on the stack; run D's stimulus was never recorded |
| `3da366a` | `3f249d7` | docs(ai): TODO-41A PASS — native stack collapses channel asymmetry to 0.13 dB |
| `c18fac7` | `4314e52` | feat(config): AUDIO_SHIELD_STACKED guard, and correct a false SPI premise |
| `89685e5` | `79f0c5a` | docs(ai): ground-return path localised — 33.1 dB from moving one wire's return |
| `637edcb` | `13aae20` | docs(ai): withdraw "codec exonerated" — a bare ground jumper reproduces the floor |
| `fb176dc` | `57e2ced` | docs(ai): SOURCE-floor investigation, Phase 5 jack, and the architecture sessions |
| `c64e876` | `305a780` | feat(display): ADR-001 presentation boundary, Protocol v2, and timing probe |
| `1727aca` | `a42989f` | docs(asbuilt): add verification summary and Phase 5 standing rule |
| `97ce50a` | `4073d1b` | docs(asbuilt): audit digital values and part provenance |
| `b764bd6` | `9dc916e` | docs(asbuilt): audit analog schematic against bench evidence |
| `aa9a795` | `8701649` | fix(diagnostics): mark clamped TF bins instead of printing them as valid |
| `e6daac8` | `9aa2322` | ai: analog level SOLVED — signal was in the headphone jack; SOURCE_NODE now -9.0 dBFS vs -10.3 predicted |
| `a25c948` | `a2aab4b` | ai: SOLVED — shortening the I2S interconnect takes corruption to exactly zero |
| `e2479a8` | `f4f84af` | ai: scope clears DOUT timing/driver; flying-lead interconnect is the new leading suspect |
| `c02895a` | `54435d8` | ai: 2nd DOUT rework FAILS — three joint states, none working; pin 8 contention damage hypothesis |
| `df7cc09` | `1e7d429` | ai: DOUT pin 8 found broken — remaking it moved corruption 4.2x, proving causal involvement |
| `cfb1aaf` | `23d8c9c` | diag: add AudioMemory telemetry; cold-start run rules out the leak, refutes warm-up |
| `298e7d6` | `8546ab5` | ai: halt did not reproduce — 47 min continuous; fault improved 8x over the run untouched |
| `070cab3` | `f70bc6d` | ai: unattended control — fault RECOVERS spontaneously, refuting monotonic degradation; board then halted |
| `b873b30` | `3c8bea9` | ai: closure test refutes the pin-8 claim — fault has degraded monotonically all session |
| `3cebf22` | `233ad04` | ai: pin 8 test — loading DOUT makes it far WORSE, strong localization to DOUT |
| `ca09bf9` | `49604fd` | ai: ground-clip test re-run valid — ground doesn't suppress, and we caught a single-word error |
| `8ec5591` | `6ad602d` | ai: ground-clip-only test — ground alone does not suppress the outliers (but confounded) |
| `5a87e1e` | `85d9594` | ai: scope-removed test — corruption returned ~400x rarer, both hypotheses partly true |
| `a7d3691` | `4e29929` | ai: fix entry heading that still carried the retracted 'most likely ground' claim |
| `8c5cbaf` | `1715778` | ai: tighten the diagnosis — physical/interconnect layer, not "most likely ground" |
| `280bd70` | `a1bc041` | ai: FAULT CLEARED — scope proved clocks good, pipeline now decodes the 1 kHz tone |
| `3906db9` | `92ef096` | ai: raw samples show systematic corruption; static I2S format check is a clean negative |
| `765f146` | `c65c98b` | ai: fork resolved — analyzers are fed, the full-scale samples are real |
| `b6f3dc1` | `8a123ac` | fix: guard peak reads against unavailable analyzer data |
| `5b59f93` | `2c113e9` | ai: found it — AudioAnalyzePeak::read() unguarded returns exactly +0.0 dBFS |
| `ca10a83` | `ebf23c3` | ai: withdraw the "transport works" inference — Teensy is I2S master |
| `d091407` | `796f4c7` | ai: disconnect test is decisive — analog front end exonerated, fault is in the I2S path |
| `744ef37` | `14655e6` | ai: correct the I2S-not-wired claim; rule out generator and gain |
| `012b746` | `d3527d9` | ai: display guard verified on hardware — 47x recovery; found a 2x error in EXPECTED_BLOCK_MS |
| `8548c4c` | `5b239c2` | fix: guard display calls when RA8875 init fails |
| `9037726` | `32974f0` | ai: first full-pipeline run — boot reaches audio, but two serious problems |
| `3cbf7ce` | `35ff979` | main: make display init non-fatal so setup() reaches audioCap_init() |
| `eeaec99` | `8410563` | config: move RA8875_RESET_PIN from 8 to 5 — pin 8 is I2S RX_DATA0 |
| `8ffeaa0` | `ed65a64` | ai: two firmware blockers make the SOURCE_NODE test impossible as-is |
| `7ec7668` | `05323ef` | ai: soften two overclaims in the headroom write-up |
| `03d7eb0` | `14b9de0` | ai: record headroom sweep — linear ceiling ~0.5 Vrms, buffer gain is unity |
| `eff6e5f` | `204489f` | ai: record OPA_BIAS bench results — CM fix confirmed, but test level was clipping |
| `eac1510` | `e932fdb` | ai: fix leftover 1.34 V reference in TODO-4 characterisation step |
| `7be21c6` | `8f3c398` | ai: correct the output-swing spec from TI's datasheet; final bias design |
| `c23a1ff` | `d751172` | ai: adopt the 1.34 V temporary rebias; 1.0 V target is not viable |
| `91b52f1` | `2d86111` | ai: gate the Phase 4 fix on an architecture decision; withdraw recommendation |
| `969a015` | `0a396da` | ai: record Phase 3/4 bring-up findings and two Phase 4 runbook defects |
| `6ee4b6d` | `339675e` | Ignore local MCP config |
| `64894d4` | `c163c72` | Initial commit: Guitar Rig Analyzer firmware for Teensy 4.1 |

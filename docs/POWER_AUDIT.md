# Power audit and sleep redesign

Status: implemented, compiled, flashed, serial-verified, and camera-verified on
the supported V2 board on 2026-08-24. Structural power-down behavior is proven;
whole-board current has not been measured, and the battery/charge-only sleep
branch still needs an untethered physical PWR test.

## Result

The former standby was display blanking, not processor sleep. It turned off the
AMOLED and speaker amplifier, but `loop()` continued every 20 ms, both ESP32-S3
cores remained runnable, I2S and the ES8311 codec remained powered, and the
QMI8658 accelerometer stayed enabled.

The checked-in standby path now:

1. Pauses game deadlines without discarding the current round.
2. Mutes and powers down the ES8311, gates the NS4150B amplifier, and disables
   the I2S transmit channel.
3. Disables the accelerometer.
4. Sends display-off and sleep-in to the CO5300 panel.
5. Enters ESP32-S3 light sleep for 50 ms at a time, waking briefly to poll the
   PWR button and returning immediately to sleep.

The checked-in awake path now also removes avoidable work while being designed
to preserve the rendered and audible product contract:

1. I2S is output-only, so the unused microphone/RX channel is not allocated or
   clocked.
2. After the final authored 40 ms silence and a further 750 ms guard, the
   codec is muted and powered down, the speaker amplifier is gated, and the
   I2S transmit channel is disabled. The next cue restores muted clocks,
   preloads silence, enables the amplifier, waits 10 ms, and unmutes before its
   first PCM frame is queued.
3. Native CST820 `TP_INT` gates idle touch I2C reads. Active contact and release
   retain the original 8 ms sampling; a 64 ms safety poll bounds missed-edge
   recovery, and a failed interrupt configuration falls back to the original
   continuous polling path.
4. The awake PWR expander is sampled every 20 ms instead of every 8 ms. This is
   still faster than the existing debounce thresholds and does not change the
   short-release or long-hold interaction.

`STATUS` exposes `audio_power`, `audio_idle_downs`, `touch_irq_gate`,
`touch_polls`, and `power_polls`, so these transitions and I2C cadences can be
verified without inferring them from source.

Light sleep retains RAM, the framebuffer, the round, and deadlines while
clock-gating the CPUs and most digital peripherals. A data-host USB connection
intentionally uses the former awake polling behavior: Espressif documents that
native USB Serial/JTAG can disconnect or fail to recover across light sleep, and
the maintenance verifier depends on that channel. A charge-only cable does not
count as a data host and therefore still uses light sleep.

These changes remove known powered blocks and transactions, but this document
does not claim a percentage or a number of milliamps until the complete board is
measured at the battery or 5 V input. Whole-board draw includes the PMIC,
display controller, touch controller, expander, IMU, codec, flash, PSRAM, and
regulator losses; ESP32 module figures alone are not a valid prediction.

## Why PWR is timer-polled

The published board schematic routes the physical PWR signal through the
AXP2101 and mirrors it to TCA9554/XCA9554 expander P4. The expander's interrupt
output has a pull-up but is not routed to an ESP32-S3 GPIO. The AXP IRQ, RTC IRQ,
and IMU IRQ also enter expander pins rather than native ESP wake pins.

Consequently, the existing PWR interaction cannot directly wake the ESP32 from
an indefinite GPIO light sleep or deep sleep. A 50 ms light-sleep timer
preserves the existing 50 ms debounce threshold and intended human PWR
interaction while keeping the CPUs clock-gated between polls; it does not
preserve the former 20 ms standby polling cadence. An unusually brief
sub-50-ms pulse could fall between timer wakes, which is why untethered physical
PWR testing remains a deployment gate. Touch interrupt is on native GPIO21 and
could provide an immediate touch wake, but changing the product from PWR-to-wake
to touch-to-wake is a separate interaction decision.

Deep sleep is not used because PWR cannot wake it, normal RAM state would be
lost, and rebooting every few milliseconds to poll an I2C expander would defeat
the power goal. PMIC rail switching is also deliberately untouched: the exact V2
rail dependencies need physical confirmation before any rail can safely be
disabled.

## Research reviewed

The implementation is based on primary documentation and open-source reference
implementations:

- [Waveshare's ESP32-S3-Touch-AMOLED-1.8 documentation](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.8)
  identifies the V2 CO5300 display, CST820 touch controller, QMI8658 IMU, and
  AXP2101 PMIC. Its [resources page](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.8/Resources-And-Documents)
  provides the board schematic and component data sheets.
- [Waveshare's open-source board repository](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.8)
  was checked for an exact-board sleep implementation. Its examples establish
  peripheral setup, but do not provide a complete low-power standby for this
  product.
- [ESP-IDF sleep-mode documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/sleep_modes.html)
  defines light-sleep retention, timer wake, peripheral behavior, and flash/PSRAM
  leakage handling.
- [ESP-IDF's open-source light-sleep example](https://github.com/espressif/esp-idf/blob/master/examples/system/light_sleep/README.md)
  demonstrates the timer-wake pattern and calls out the native USB limitation.
  Its measured currents are reference-board results, not predictions for this
  Waveshare assembly.
- [Espressif's current-measurement guidance](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/current-consumption-measurement-modules.html)
  explicitly separates module current from development-board peripheral current
  and recommends measuring the whole system.
- [Espressif's open-source ES8311 suspend implementation](https://github.com/espressif/esp-adf/blob/release/v2.x/components/esp_codec_dev/device/es8311/es8311.c)
  supplies the codec register power-down sequence used here.
- [ESP-IDF power-management documentation](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-reference/system/power_management.html)
  covers dynamic frequency scaling and automatic light sleep, useful for the
  awake-mode follow-up below.
- [LilyGoLib's open T-Watch S3 measurements](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/master/docs/hardware/lilygo-t-watch-s3.md)
  provide a useful whole-device comparison across light sleep, deep sleep,
  touch wake, and PMIC power-off on another ESP32-S3/AXP2101 wearable. The
  hardware differs, so those values are sanity checks only.

The CO5300 data sheet also documents that sleep-in turns its booster off after
120 ms. Its deeper standby command requires a hardware-reset exit, so adopting
that command should wait for V2 hardware validation rather than being folded
into this safe first pass.

## Awake-mode audit

Priority reflects likely energy impact, not implementation difficulty.

| Priority | Finding | Current decision and evidence | Next gate |
| --- | --- | --- | --- |
| High | Audio formerly stayed powered while the awake game was silent | **Implemented.** Output-only I2S plus the guarded codec/amp/TX idle transition are active. The device verifier observed `on -> idle` after replay and an incrementing shutdown counter; mute still reports the separate `suspended` state. The recorded walkthrough completed exactly five cue sequences and exactly five new idle shutdowns. | Measure whole-board awake-silent current before and after. Keep human listening for first-phoneme quality as the final perceptual gate. |
| High | The ESP32 runs at a fixed 240 MHz | **Deferred.** The pinned Arduino SDK has automatic power management disabled. Enabling DFS here would add timing risk to native USB, I2S, and display transfers. | Consider only with a measured benefit and physical audio, USB, touch, and animation regression tests. |
| High | Tiny animations cause full-frame transfers | **Deferred.** A 368 x 448 RGB565 framebuffer is about 322 KiB, but partial updates could create visible composition or edge artifacts. | Prototype coherent dirty rectangles separately and accept only with camera plus hands-on tilt evidence. |
| High | AMOLED brightness is fixed near 75% | **Intentionally unchanged.** `kDisplayBrightness` remains 190/255; lowering it would be immediately perceptible. The mostly black canvas already benefits an AMOLED. | Offer a deliberate product-level brightness choice only after readability and color review. |
| Medium | Touch was polled continuously | **Implemented with fail-safe fallback.** `TP_INT` gates idle reads, active contact/release retains 8 ms sampling, and a 64 ms safety poll bounds a missed interrupt. Serial cadence passed and `touch_irq_gate=yes` was required by the verifier. | Confirm physical taps, holds, and release behavior by hand; retain continuous polling if interrupt setup ever fails. |
| Medium | Awake PWR was sampled every loop | **Implemented.** Expander reads are limited to 20 ms while awake and remain timer-polled in standby because PWR is not on a native wake GPIO. Serial cadence passed. | Confirm short release, long hold, and 100 standby cycles on battery/charge-only power. |
| Medium | IMU is configured above the UI's sample rate | **Intentionally unchanged.** The accelerometer remains high-resolution 62.5 Hz because lower ODR or low-power mode could alter the card feel. Standby still disables it. | Try only as a separately reviewable motion build with hands-on comparison. |
| Low | Always-retained PSRAM has a sleep floor | **Intentionally retained.** The framebuffer and audio pack support instant same-round wake and deterministic offline playback. | Revisit only if a future interaction allows reboot/reconstruction rather than seamless resume. |

Already favorable: Wi-Fi and Bluetooth are not initialized, the UI is mostly
pure black, audio is offline, the SD slot is not mounted, the amplifier has a
hard enable gate, battery polling is infrequent, and display sleep-in is sent.

## Verification completed on the V2 board

- The canonical host suite and both production and ocean-demo firmware builds
  passed. The power pass was first installed as a 1,339,184-byte application
  with SHA-256
  `4895b32390e09538b5ed7a932e92c5c5d7e92b5a9a5f0af9a14832c5712a9c61`.
  The subsequent creature-only refresh did not alter these power paths; its
  currently installed 1,427,872-byte application has SHA-256
  `7133805d7b899392c40cdb5afb90d54eca39133d934b7582f26467d042e1df18`.
- The canonical flash wrote and hash-verified bootloader `0x0`, partition table
  `0x8000`, OTA selector `0xe000`, application `0x10000`, and the unchanged
  audio pack `0x610000` on the exact ESP32-S3 V2 board.
- `scripts/verify_device.py` proved audio wake, playback, the 750 ms idle
  transition, mute/suspend separation, interrupt-gated touch cadence, awake PWR
  cadence, every common and authored-rare creature renderer, palette policy,
  and final cleanup. It finished with the normal game, unmuted audio, and
  `audio_power=idle`.
- A real replay/wrong/replay/correct/next-round walkthrough preserved the card,
  water, creature, label, and transition presentation. Its serial timeline
  started and ended in idle audio state, with `audio_idle_downs` increasing
  from 12 to 17: one completed shutdown for each of its five audio sequences.
- The untouched Insta360/Photo Booth recording is 58.075 seconds, 1620 x 1080
  H.264 with 44.1 kHz mono AAC, SHA-256
  `416c875050681fcc0bc920850711245d16df97ea4574c5e6d04f7326db803797`.
  Its audio is present and unclipped (mean -51.2 dBFS, peak -23.6 dBFS).
  Timeline-aligned waveform and spectrogram inspection found each expected cue
  and no isolated full-scale/broadband wake or shutdown transient. This is
  camera-microphone evidence, not a replacement for human listening at the
  device.

## Remaining physical and measurement gates

1. Measure steady awake-silent and standby current at the same brightness and
   supply, comparing the prior and current builds with an inline whole-board
   meter. Until then, claim only structural savings, not mA or percentage.
2. Test battery, charge-only USB, and a real USB data host separately. This run
   had USB data attached, so it intentionally exercised awake-polled standby
   rather than the 50 ms light-sleep branch.
3. Confirm by hand that a short PWR release resumes the same round and that the
   factory long-hold hard-off remains intact; repeat at least 100 sleep/wake
   cycles on battery or charge-only power.
4. Confirm physical tap/hold/release alignment, replay-circle double-tap mute,
   cable-removal auto-unmute, and card tilt feel. Serial and camera control do
   not exercise a person's fingers or hand motion.
5. Listen at the board for wake pops and a clipped first phoneme. The camera
   track found no obvious artifact, but human listening remains the perceptual
   product gate.
6. Capture serial and current traces for a failed light-sleep start. The code
   falls back to awake 20 ms polling instead of busy-spinning.

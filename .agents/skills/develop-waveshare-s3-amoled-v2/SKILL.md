---
name: develop-waveshare-s3-amoled-v2
description: Plan, build, flash, test, or troubleshoot applications for the exact Waveshare ESP32-S3-Touch-AMOLED-1.8 V2 with CO5300 display and CST820 touch, using this repository as either the Phonics Picker source or a reusable board reference. Do not use for the V1 revision or generic ESP32-S3 boards.
---

# Develop for the Waveshare ESP32-S3 AMOLED V2

Use the repository's verified board knowledge without confusing it with the
Phonics Picker product contract.

## Route the task

- For deploying or changing Phonics Picker, read
  [`../../../AGENTS.md`](../../../AGENTS.md) first, then the sources of truth it
  names. Its five-region flash and physical verification contract is binding.
- For a different application on the same exact board, read
  [`../../../docs/WAVESHARE_S3_AMOLED_V2_DEVELOPMENT.md`](../../../docs/WAVESHARE_S3_AMOLED_V2_DEVELOPMENT.md).
  Treat this repository as a board/workflow reference, not as a generic game
  template.
- For work whose purpose is improving Phonics Picker iteration speed, also read
  [`../../../docs/DEVELOPMENT_SPEED_STRATEGY.md`](../../../docs/DEVELOPMENT_SPEED_STRATEGY.md).
  It distinguishes current commands from proposed work.

## Establish identity before hardware mutation

The supported target is the rear-labeled **V2** board with ESP32-S3R8, 8 MB
PSRAM, 16 MB flash, CO5300 368 x 448 QSPI AMOLED, and CST820 touch. V1 uses
SH8601/FT3168 and is incompatible.

Before flashing:

1. have the human confirm the product name and `V2` rear label;
2. resolve the intended serial port without guessing between candidates;
3. preflight ESP32-S3 and 16 MB flash; and
4. explain which application-owned regions will be replaced.

Preserve or obtain the matching factory image first when recovery matters.
Never treat compilation as hardware verification.

## Keep board and application contracts separate

Reusable board knowledge includes controller choice, pins, initialization,
power/audio/display/touch behavior, host-test seams, diagnostics patterns, and
device qualification.

The following are Phonics Picker-specific and must not be inherited by another
application without an explicit new design:

- its partition scheme and `0x610000` audio pack;
- its build manifest and accepted asset hashes;
- its USB commands, game behavior, volume, timing, and power policy; and
- its release and manual verification checklist.

Create a separate application target, partition/resource layout, compatibility
IDs, flash manifest, diagnostic protocol, and physical verification plan. Do
not use `scripts/flash_firmware.sh` to install a different product.

## Choose the smallest proof that answers the change

Classify the change before building or touching a device:

- pure state or game logic: native host tests;
- renderer/layout: host-rendered goldens, then requested states on the AMOLED;
- touch or motion: deterministic input traces, then physical alignment or
  orientation;
- audio: format/state tests, then codec, sequencing, loudness, and idle/wake
  listening;
- candidate asset: isolated validation and physical development preview, never
  promotion;
- accepted resource: pack/index/schema checks plus compatibility and
  perceptual verification;
- power, board support, partition, bootloader, toolchain, or unknown: broad
  fail-closed tests and the application's full install path.

Keep development and release evidence labeled separately. A partial flash,
serial response, host framebuffer, or camera-free check proves only its stated
scope.

## Make repeated operations deterministic

Prefer ordinary repository tools with documented JSON schemas and exit codes
for discovery, doctor, build receipts, change-impact classification, flashing,
verification, evidence, and asset promotion. Safety belongs in those tools so
humans, CI, and different agent products make the same decision.

A reused build must have a receipt bound to current source/diff, generated
inputs, toolchain, board profile, dependencies, resources, and artifact hashes.
Changed-region development flashing additionally requires a trusted full
install on that physical device and matching partition and compatibility IDs.
Missing evidence falls back to the application's full install.

Keep serial handling bounded and nonblocking. Version structured responses,
separate them from logs, and put length plus CRC around binary transfers. One
process owns a serial port at a time.

## Verify the complete claim

Use host tests for deterministic logic and pixels; use device profiles for
installed identity and subsystem behavior; retain human checks for perceptual
display, touch, motion, audible quality, battery, and power claims. Record the
device/build/resource identities with each result.

For newly purchased boards, qualify display, touch, IMU, audio, PMIC, RTC,
PSRAM, flash, and any used storage before assigning the device a stable alias
or test role.

Do not broaden the user's product request merely because this repository has
phonics, creature, audio, or asset-generation code. Reuse only the board-level
knowledge that serves the requested application.

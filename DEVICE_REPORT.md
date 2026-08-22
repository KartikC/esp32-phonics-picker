# Connected device report

Verified 2026-08-22 on `/dev/cu.usbmodem1401`.

## Hardware

- ESP32-S3 QFN56 rev 0.2, MAC `28:84:85:8D:46:9C`
- dual-core 240 MHz, 8 MB embedded PSRAM, 16 MB flash
- physical V2 display/touch revision: CO5300 + CST820
- I2C scan: `0x15`, `0x18`, `0x20`, `0x34`, `0x51`, `0x6B`, `0x7E`
- the live CST820 address `0x15` supersedes the Amazon listing's V1 claim

## Recovery point

- file: `backups/factory-esp32s3-2884858d469c-2026-08-22.bin`
- size: 16,777,216 bytes
- SHA-256: `6f188fb9d35ee793a3423934a4fa4e7c1fef9cc9dae76f9f177dabe854a6cdb3`
- captured factory app: Waveshare ESP-IDF 5.5.4 `esp-brookesia`

Restore only when explicitly requested:

```sh
.arduino/data/packages/esp32/tools/openocd-esp32/v0.12.0-esp32-20260424/bin/openocd \
  -s .arduino/data/packages/esp32/tools/openocd-esp32/v0.12.0-esp32-20260424/share/openocd/scripts \
  -f board/esp32s3-builtin.cfg -c 'adapter speed 10000' \
  -c 'program_esp backups/factory-esp32s3-2884858d469c-2026-08-22.bin 0x0 verify reset exit'
```

## Installed build

- source: `firmware/PhonicsGame/`
- Arduino-ESP32: `3.3.11`
- Waveshare source commit: `7ab8f957e22ea1ab811256359f4eddcaaf49ee91`
- application SHA-256: `8dd963ad010766fa07f328520c9154357f310c9d7dabca3c4d2379d66ff47472`
- merged-image SHA-256: `b521308cc47e209ae0cffc901905501efefa726ee0ae06117fb4cc1fe9bdb117`
- audio-pack SHA-256: `563943402470eada0150e74720086d33ef9921d8b07e58e14247f18e9175ea72`
- flash verification: all written-region hashes passed
- footprint: 462,048-byte app image (461,896 bytes reported code/data);
  31,088 bytes static RAM
- live display verification: exactly two distinct readable lowercase choices,
  one working replay control, pure-black unused canvas, and no header text.
  Human observation confirmed the corrected portrait motion mapping
  (`screen X = -sensor Y`, `screen Y = sensor X`) moves in the tilt direction.
- game-engine verification: 131,072 seeded rounds plus the focused flow tests;
  every target and distractor differed and C/K never opposed one another.
  Exhaustive geometry tests cover all layouts, integer motion positions, pulse
  sizes, both pulse sides, display bounds, card separation, and replay clearance.
- audio: ES8311 managed logical volume 100 (`DAC_REG32 = 0xC6`), full-resolution
  PCM, deterministic V2 codec reset/configuration, asynchronous playback.
  Live `REPLAY` invoked prompt variant 2 plus `/k/` at volume 100.
- standby: the physical PWR short-press cycle was exercised manually on the V2
  unit. A separate USB cycle reported `standby=yes` with audio suspended, then
  restored the same `k`/`z` round with `audio=ready`; factory PMIC long-hold
  hard-off was deliberately not exercised remotely.

## Installed audio

- 26/26 Cowboy phonics source hashes match Letterboard's canonical manifest
- 16 Cowboy cue candidates were generated from the approved anchor
- 42 total 16 kHz mono PCM WAV assets, 954,220 bytes, 29.713 seconds
- packed payload: 950,976 bytes in raw `ffat` at `0x610000`
- device audio manifest: `audio/generated/device-audio-manifest.json`
- production capture: `previews/device-production-gentle-native48.wav`
- gain-only listening copy: `previews/device-production-gentle-listening.wav`
- exact digital prompt reference: `previews/source-gentle-reference.wav`
- controlled gentler-path capture: `previews/ab-b-gentle-dsp-b2-native48.wav`
- verification: the fixed-prompt capture matches the source more closely than
  the rejected processing path, with no clipping or stream timing loss. The
  MacBook recording peaks near -35 dBFS and is therefore useful only for
  comparison. The gentler processing was accepted by human listening on the
  physical unit; the later volume increase remains within the authored peak
  headroom.

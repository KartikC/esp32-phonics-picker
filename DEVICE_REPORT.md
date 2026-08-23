# Physical-device verification snapshot

This is a sanitized record of the production build tested on a physical
Waveshare ESP32-S3-Touch-AMOLED-1.8 V2 on 2026-08-22. Per-device identifiers,
local serial paths, private factory backups, and raw microphone captures are
intentionally excluded from the public repository.

## Hardware observed

- ESP32-S3 QFN56 rev 0.2, dual-core 240 MHz
- 8 MB embedded PSRAM and 16 MB flash
- physical V2 display/touch revision: CO5300 + CST820
- live I2C devices at `0x15`, `0x18`, `0x20`, `0x34`, `0x51`, `0x6B`, and
  `0x7E`

The observed CST820 at `0x15` and CO5300 panel agree with Waveshare's V2
documentation. Older seller listings describing SH8601 + FT3168 refer to V1
and are not compatible with this firmware.

## Installed build evidence

- source: `firmware/PhonicsGame/`
- Arduino-ESP32: `3.3.11`
- Waveshare source commit: `7ab8f957e22ea1ab811256359f4eddcaaf49ee91`
- accepted audio-pack SHA-256:
  `563943402470eada0150e74720086d33ef9921d8b07e58e14247f18e9175ea72`
- every written flash region passed esptool's post-write verification
- the runtime reported 8 MB PSRAM, ready audio at logical volume 100, a ready
  QMI8658 IMU, two distinct choices, and no preview mode
- 131,072 seeded rounds plus focused state-flow tests passed; targets and
  distractors always differed, and C/K never opposed one another
- exhaustive geometry tests covered all six layouts, both pulse sides, the full
  motion range, display bounds, card separation, and replay-target clearance

## Human-observed behavior

- the display showed exactly two distinct readable lowercase cards, one fixed
  replay control, tiny battery dots, a pure-black unused canvas, and no answer
  or instructional header text
- the full frame remained buffered: no clearing, partial drawing, or animation
  intermediates were visible on the AMOLED
- both cards followed physical tilt in portrait orientation, with a subtle
  independent easing lag while remaining within their original hit regions
- replay produced the current prompt and target phonics sound through the
  onboard speaker
- wrong answers retained the round; correct answers produced the bounded pulse
  and advanced after praise
- a short physical PWR press/release entered standby and woke to the same round
  with audio ready
- the AXP2101 battery indicator was visible as three green dots at full charge

Human listening accepted the checked-in gentle 16 kHz audio path. Automated
hashes and serial status catch missing or corrupt data, but do not replace
listening on the physical speaker.

## Installed audio evidence

- 26 phonics sounds and 16 spoken cues (42 assets total)
- 16 kHz, mono, signed 16-bit PCM
- 954,220 bytes of WAV files; 950,976-byte raw packed payload
- 29.713 seconds total authored audio
- packed at the `ffat` partition offset `0x610000`
- all accepted WAV hashes, pack offsets, payload bytes, and the firmware index
  are checked by `scripts/verify_repo.py`

The public deployment path rebuilds the application from pinned sources and
flashes this same checked-in audio pack. A successful build alone is not a new
physical-device verification; use `scripts/verify_device.py` and repeat the
manual checks in `AGENTS.md` after flashing another unit.

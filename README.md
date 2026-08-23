# ESP32 Phonics Picker

Toddler-focused, offline two-choice phonics game for the Waveshare
ESP32-S3-Touch-AMOLED-1.8 V2 board.

The connected unit is an ESP32-S3 rev 0.2 with 8 MB PSRAM, 16 MB flash, CO5300
368 x 448 AMOLED, and CST820 touch at I2C `0x15`. Its complete factory image is
preserved under `backups/` locally and excluded from git.

## Build

```sh
python3 scripts/generate_gfx_fonts.py

clang++ -std=c++17 -Wall -Wextra -pedantic tests/game_engine_test.cpp -o /tmp/phonics-game-test
/tmp/phonics-game-test

zsh scripts/build_firmware.sh
```

For fast incremental firmware builds, use `scripts/build_firmware.sh`. It keeps
one persistent object cache and names only the six required vendor libraries.

For visual iteration without reflashing, send a completed frame directly to
the running AMOLED preview receiver:

```sh
.venv/bin/python scripts/preview_on_device.py \
  --left a --right m --layout 0 --port /dev/cu.usbmodem1401
```

Send `GAME\n` over the same serial port to restore live gameplay.

The production USB maintenance commands are `STATUS`, `REPLAY`, `SLEEP`, and
`WAKE` (each newline-terminated). They exercise the same replay and standby
paths as touch and the physical PWR button without requiring a diagnostic
firmware build. `STATUS` includes the AXP2101 fuel-gauge percentage, battery
voltage, USB-input state, and charging state.

The live game also shows tiny battery-status dots centered at the extreme top:
three dim green dots mean high/full, two dim yellow dots mean medium, and one
dim red dot means low. This is a parent diagnostic, not a child-facing game
element.

The connected device currently runs the production game with its offline audio
pack enabled at managed logical volume 100. See `PRODUCT_SPEC.md` for the audio
and interaction contract. A short physical PWR press-and-release toggles
logical standby; the PMIC retains ownership of its long-hold hard-off behavior.
Hold PWR for 6 seconds for true power-off; from hard-off, click PWR once to
start. The battery can continue charging over USB while the game is off.

## Audio preparation and verification

The cue corpus is in `audio/cowboy-cues.json`. It uses Letterboard's approved
Cowboy anchor and its canonical Cowboy phonics masters. Regenerate authored
cues only when their source text or Cowboy anchor changes, then prepare and
pack the gently band-limited, level-managed PCM:

```sh
export LETTERBOARD_ROOT=/path/to/Letterboard
"$LETTERBOARD_ROOT/.venv-audio/bin/python" scripts/generate_cowboy_cues.py
python3 scripts/prepare_device_audio.py
python3 scripts/pack_device_audio.py
```

Raw generated cue candidates stay under `audio/generated/cowboy-cues/` and are
excluded from git. The accepted device PCM, verified pack, and manifests are
checked in under `audio/generated/` so a clone can reproduce the installed
audio without access to Letterboard or the original voice-generation service.
The device manifest records 42 assets, their hashes, durations, and speaker
tuning.
The earlier `previews/device-production-final.wav` capture was rejected after
human listening. The current comparative capture is
`previews/device-production-gentle-native48.wav`; it was recorded at low level
by the MacBook microphone, so human listening on the physical unit remains the
acceptance gate. `previews/device-production-gentle-listening.wav` is the same
capture with only +18 dB gain, and `previews/source-gentle-reference.wav` is the
exact PCM sent to the device for one prompt plus `/a/`. The temporary
diagnostic build is not installed. The gentler processing was subsequently
accepted by human listening on the physical unit.

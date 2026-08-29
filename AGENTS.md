# Agent deployment contract

Agents should read this file first. This repository is self-contained for a
normal build, flash, and verification of the checked-in experience.

The supported target is exactly the Waveshare **ESP32-S3-Touch-AMOLED-1.8 V2**
(CO5300 display, CST820 touch, 8 MB PSRAM, 16 MB flash). Do not substitute an
ESP32-C6, the V1 SH8601/FT3168 revision, or a generic ESP32-S3 display board.

## Task routing

For deployment or changes to DEEP SEA PHONICS TOY V2, continue with this file and the
product sources of truth below.

For a **different application on the same exact V2 board**, read
`.agents/skills/develop-waveshare-s3-amoled-v2/SKILL.md` and
`docs/WAVESHARE_S3_AMOLED_V2_DEVELOPMENT.md`. Reuse the board integration and
workflow patterns, but create a separate application, partition/resource
layout, flash manifest, diagnostic protocol, and verification plan. The
DEEP SEA PHONICS TOY V2 audio pack, `0x610000` resource offset, USB commands, product
behavior, and five-region bundle are not generic board defaults. Do not use the
canonical DEEP SEA PHONICS TOY V2 flash script to install a different product.

The project-specific iteration roadmap is in
`docs/DEVELOPMENT_SPEED_STRATEGY.md`. Proposed modes and commands there are not
supported deployment procedures until their implementation and tests are
linked from that document.

## Canonical deployment

From the repository root:

```sh
./scripts/setup_toolchain.sh
./scripts/test.sh
./scripts/list_ports.sh
./scripts/flash_firmware.sh --port PORT --yes
python3 -m pip install -r requirements.txt
python3 scripts/verify_device.py --port PORT
```

Before passing `--yes`, establish that `PORT` is the user's intended board and
that the back label says V2. Flashing replaces its factory application. Never
guess between multiple serial ports.

The flash is not complete unless all five regions are written and verified:

- bootloader at `0x0`
- partition table at `0x8000`
- OTA selector at `0xe000`
- application at `0x10000`
- `audio/generated/phonics-audio-pack.bin` at `0x610000`

Do not use Arduino CLI's application-only upload as the deployment procedure;
it omits the audio pack. The canonical flash script performs chip/flash-size
preflight checks and uses the offsets above.

## Sources of truth

- interaction and visual behavior: `PRODUCT_SPEC.md`
- app firmware: `firmware/PhonicsGame/`
- selected card surface: `firmware/PhonicsGame/CardStoneAsset.h` and
  `firmware/PhonicsGame/CardStoneRendering.h`, generated from the audited
  source recorded in `art/letter_cards/generated/stone_card_report.json`
- selected letter font:
  `firmware/PhonicsGame/fonts/AtkinsonHyperlegibleNextExtraBold112.h`, tied to
  `art/fonts/generated/atkinson_hyperlegible_next_report.json`
- selected replay control: `firmware/PhonicsGame/ReplayButtonAsset.h` generated
  from the audited source recorded in
  `art/replay_button/generated/deep_loop_report.json`
- selected rest timer: `firmware/PhonicsGame/BreakTimerAsset.h` and
  `firmware/PhonicsGame/BreakTimerRendering.h`, generated from the audited
  source recorded in `art/break_timer/generated/tideglass_report.json`
- reviewed creature runtime assets: `firmware/CreatureAssets/` generated from
  `creatures/variation/variation_manifest.json`
- accepted audio: `audio/generated/device-pcm/`
- flashable audio and index: `audio/generated/phonics-audio-pack.bin` and
  `firmware/PhonicsGame/AudioAssetIndex.h`
- board dependency revision: `.gitmodules` plus the gitlink recorded by Git
- toolchain and FQBN: `scripts/setup_toolchain.sh` and
  `scripts/build_firmware.sh`
- exact output hashes and flash offsets: `firmware/BUILD_MANIFEST.json`
- physical validation evidence: `DEVICE_REPORT.md`
- source-faithful public still renderer: `scripts/preview_on_device.py`
- source-faithful rest-timer renderer: `scripts/preview_break_timer.py`

Checked-in generated audio, the pack, card/replay/timer data, and font headers
are authoritative for a normal build. Do not regenerate them merely to deploy.
Regeneration depends on external authoring sources and can change the accepted
experience.

## Required verification

Run `./scripts/test.sh --firmware` after source changes. For a physical install,
also run `scripts/verify_device.py` and manually confirm:

- an active round shows only two tone-on-tone lowercase stone cards, the fixed
  Deep loop play button, and tiny battery dots on a black background; each
  centered white Atkinson glyph has its deep-slate halo, and no bright green
  specks or palette-independent blue lines appear on either card;
- replay is audible;
- a correct reward audibly plays praise, then bubbles, then the matching
  creature gesture; the creature is slightly louder than the bubble bed;
- both cards respond to tilt;
- a wrong tap plays only the neutral response, locks input on the answered
  round, shows a complete black beat, and advances smoothly to a different
  target; a correct tap shows one large water-creature reward before advancing;
- after ten accumulated awake minutes, the selected Shell-inlay tideglass and
  `30:00` rest timer replace gameplay; touches, tilt, replay, and audio stay
  blocked, a mid-countdown second is accurate after standby/wake, and expiry
  starts a fresh spoken challenge with a reset ten-minute allowance;
- with USB data attached, a double tap anywhere in the complete Deep loop
  replay target mutes with a warm-red slash across the control, a second double
  tap unmutes, and disconnect clears mute;
- short PWR press/release sleeps and wakes to the same round.

Never report a hardware deployment as verified from compilation alone.

## Public media

Regenerate the corresponding README still whenever the accepted card,
letter-font, replay, or rest-timer asset changes. Use
`scripts/preview_on_device.py` for the game and mute states and
`scripts/preview_break_timer.py` for the rest screen; both are exact
source-faithful renderers, not physical framebuffer evidence. For a physical
README GIF, use a fresh `scripts/capture_readme_walkthrough.py` session from the
currently installed application, then `scripts/build_readme_media.py`; inspect
its first, reward, and final frames before publication. Keep raw camera masters
and serial timelines under ignored `build/`, and commit only reviewed
derivatives under `docs/images/`. This media-authoring path requires `ffmpeg`
and `ffprobe` on `PATH` plus
`python3 -m pip install -r requirements-authoring.txt`.

## Separate ocean-creature prototype

`firmware/OceanCreatureDemo/` remains a separate visual-audit flash target; its
reviewed generated creature header is also consumed by the canonical Picker's
correct-answer reward. The assets can be audited with
`./scripts/test_creature_pipeline.sh` and the demo compiled with
`./scripts/test_creature_pipeline.sh --firmware`. Do not flash that demo with
the canonical phonics flash command, and do not report a newly changed demo as
device-verified until the separate manual gates in
`docs/CREATURE_SPRITE_PIPELINE.md` pass on a V2 board.

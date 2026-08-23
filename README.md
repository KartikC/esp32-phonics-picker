# ESP32 Phonics Picker

An offline, toddler-friendly listening game for the **Waveshare
ESP32-S3-Touch-AMOLED-1.8 V2**. The child hears a lowercase phonics sound and
taps one of two large letter cards. Everything runs on the board: display,
touch, motion, speech, phonics audio, and speaker playback.

![The Phonics Picker UI: replay button, two battery dots, and two lowercase letter cards](docs/images/phonics-picker-ui.png)

> [!IMPORTANT]
> This firmware is for the **ESP32-S3 V2 board with a CO5300 display and CST820
> touch controller**. It is not for an ESP32-C6, and it is not compatible with
> the older V1 board (SH8601 + FT3168). Check the `V2` label on the back before
> flashing. Waveshare documents the revision difference in its
> [official board documentation](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.8).

## Recommended: give this repository to an agent

The easiest installation path is to point a coding agent at this GitHub
repository and ask it to deploy the project to the connected board. The root
[AGENTS.md](AGENTS.md) tells the agent the exact supported hardware, canonical
commands, five required flash regions, safety checks, and verification steps.
Everything needed for a normal build and installation is in the repository, so
the agent can inspect the contract and carry out the deployment without having
to reconstruct the board configuration.

The human still needs to confirm that the rear label says **V2** and identify
the intended serial port before the agent flashes it. A useful prompt is:

> Read AGENTS.md and deploy this project to my connected Waveshare V2 board.
> Show me the detected port and ask me to confirm it before flashing.

## Materials

Required:

- **Board:** [Buy the Waveshare ESP32-S3-Touch-AMOLED-1.8 from Waveshare](https://www.waveshare.com/product/esp32-s3-touch-amoled-1.8.htm), and confirm it is **V2**
- a USB-C cable that carries data, not a charge-only cable
- a macOS, Linux, or Windows computer with Git, Python 3.10+, a C++17 compiler,
  and internet access for the first toolchain download

You do **not** need an external speaker, screen, SD card, account, API key, or
Wi-Fi connection. A battery is optional; USB powers the experience. If you add
a battery, use a correctly polarized 3.7 V cell made for the board's MX1.25
2-pin connector. See [Hardware and safety](docs/HARDWARE.md) before connecting
one.

## Install the exact experience

Flashing replaces the factory application. Clone with the pinned Waveshare
submodule, connect the board over USB-C, and run:

```sh
git clone --recurse-submodules https://github.com/KartikC/esp32-phonics-picker.git
cd esp32-phonics-picker
./scripts/setup_toolchain.sh
./scripts/test.sh
./scripts/list_ports.sh
./scripts/flash_firmware.sh --port /dev/cu.usbmodemXXXX
```

On Linux the port is commonly `/dev/ttyACM0`; in Git Bash on Windows it is
commonly `COM3`. The flash script asks for confirmation, verifies that the chip
is an ESP32-S3 with 16 MB flash, builds with the pinned toolchain, and writes
both the application and the checked-in audio pack. Add `--yes` only for a
non-interactive agent run after confirming the target board and port.

If the repository was downloaded without submodules, the setup script fetches
the pinned revision automatically. Full clean-clone and troubleshooting steps
are in [Deployment](docs/DEPLOYMENT.md). Instructions intended for coding
agents are in [AGENTS.md](AGENTS.md).

## How the UI works

1. The board speaks a prompt and one target phonics sound.
2. The child taps one of the two lowercase letter cards.
3. A wrong choice gets a calm spoken response and keeps the same round.
4. A correct choice gives one brief card pulse and short praise, then starts a
   new round.

The round never prints or otherwise reveals the answer. The fixed play button
at the top repeats the exact current prompt. Gently tilting the board lets both
cards drift together without changing their touch targets or which answer is
correct.

The tiny dots at the top are parent-facing battery status:

- three green dots: 60-100%
- two yellow dots: 25-59%
- one red dot: 0-24%

A short press and release of **PWR** toggles quiet standby and resumes the same
round. Hold PWR for about six seconds for the board's hardware power-off; click
PWR once to start again. The **BOOT** button is not part of the game.

There are no scores, streaks, ads, accounts, network calls, microphone use, or
runtime speech generation. See [PRODUCT_SPEC.md](PRODUCT_SPEC.md) for the full
interaction contract.

## Reproducibility

The repository pins and includes everything needed for the installed result:

- Arduino CLI 1.5.1, downloaded with an official SHA-256 check
- Arduino-ESP32 core 3.3.11
- Waveshare source commit `7ab8f957e22ea1ab811256359f4eddcaaf49ee91`
- a fixed build epoch taken from the hardware-verified firmware commit, so the
  application binary is byte-reproducible across clean builds
- the slim display, touch, and IMU sources used by the build
- both generated Nunito bitmap-font headers
- all 42 accepted 16 kHz PCM assets and the packed flash image
- the fixed board options and partition layout
- expected byte counts and SHA-256 values for every flashed artifact in
  `firmware/BUILD_MANIFEST.json`

The deployment build does not need ffmpeg, a model service, or any private
source. Those are needed only if an author deliberately regenerates the already
checked-in audio or fonts. `python3 scripts/verify_repo.py` validates every audio
asset, pack offset, manifest hash, and required deployment input.

## Development

```sh
./scripts/test.sh --firmware
```

That command runs the host game/geometry tests, validates the complete audio
pack, installs the pinned toolchain if needed, and compiles the production
firmware. CI runs the same path from a fresh Ubuntu checkout. The most recent
physical-board verification snapshot is in [DEVICE_REPORT.md](DEVICE_REPORT.md).

Production USB maintenance commands are `STATUS`, `REPLAY`, `SLEEP`, `WAKE`,
and `GAME`, each followed by a newline at 115200 baud. They exercise the same
paths as the visible replay control and PWR button.

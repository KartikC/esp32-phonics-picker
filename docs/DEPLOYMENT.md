# Clean-clone deployment

These instructions reproduce the same firmware, partition layout, fonts, and
offline audio pack used by the hardware-verified build.

## 1. Confirm the target

Read [HARDWARE.md](HARDWARE.md) and confirm the board's rear label says V2.
Flashing a V1 board will not make its different display and touch controllers
compatible. Disconnect other ESP boards so the target serial port is
unambiguous.

Flashing replaces the Waveshare factory app. If retaining that app matters,
download the matching V2 factory image from the pinned Waveshare submodule or
make a full 16 MB backup before continuing.

## 2. Clone and set up

```sh
git clone --recurse-submodules https://github.com/KartikC/esp32-phonics-picker.git
cd esp32-phonics-picker
./scripts/setup_toolchain.sh
```

The setup script supports macOS (Intel/Apple Silicon), Linux (x86-64/ARM64),
and 64-bit Windows under Git Bash. Python 3.10+ is required, and the host tests
also need a C++17 compiler. The script downloads Arduino CLI 1.5.1, verifies the
archive against the official release SHA-256, installs Arduino-ESP32 3.3.11
inside this repository, and initializes the pinned Waveshare submodule. It does
not modify a system-wide Arduino installation.

## 3. Verify and build

```sh
./scripts/test.sh --firmware
```

Expected final lines include `Repository payload verified`,
`game_engine_test passed`, `creature_reward_selector_test passed`,
`reward_audio_selector_test passed`, `mute_controller_test passed`, and
`Firmware build verified`. The build uses:

```text
esp32:esp32:esp32s3:FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=opi,CDCOnBoot=cdc
```

The accepted audio image has SHA-256
`262858b9569618ca7bb901ba27fc0fd9034eb2f9e11a82176cda8ace7db19ba0`.
The verifier checks that value, every individual WAV hash and format, every
packed offset, the generated C++ index, all 32 offline reward masters, and the
firmware partition table.
The build also pins `SOURCE_DATE_EPOCH` to the hardware-verified firmware source
commit so Arduino's compile-time diagnostic strings do not change the binary.

## 4. Find the serial port

Connect the board with a data-capable USB-C cable and run:

```sh
./scripts/list_ports.sh
```

Typical ports are `/dev/cu.usbmodem...` on macOS, `/dev/ttyACM0` on Linux, and
`COM3` in Windows Git Bash. If no port appears, try another cable and a direct
computer USB port. On Linux, add the user to the system's serial-port group
(often `dialout`) and log in again if permission is denied.

If automatic reset cannot enter the ROM loader, hold **BOOT**, tap **PWR** or
reconnect USB, then release **BOOT** once the flash connection begins.

## 5. Flash app and audio

```sh
./scripts/flash_firmware.sh --port /dev/cu.usbmodemXXXX
```

The script first asks esptool to identify an ESP32-S3 and detect 16 MB flash. It
then requests confirmation and writes verified data at these exact offsets:

| Offset | Contents |
| --- | --- |
| `0x0` | bootloader |
| `0x8000` | partition table |
| `0xe000` | OTA selector |
| `0x10000` | DEEP SEA PHONICS TOY V2 application |
| `0x610000` | offline audio pack |

It does not erase unrelated flash sectors. This preserves a user's factory
backup opportunity while replacing every region the experience actually uses.

## 6. Verify the running board

Install the small serial-only Python dependency and run the live verifier:

```sh
python3 -m pip install -r requirements.txt
python3 scripts/verify_device.py --port /dev/cu.usbmodemXXXX
```

A pass requires 8 MB PSRAM, ready audio, volume 90, a ready IMU, two distinct
choices, no preview frame, an awake `playing` state with at least 60 seconds of
allowance remaining, and a working CST820 interrupt gate. It proves audio
wake/playback followed by the guarded idle power-down; exercises one real
neutral wrong answer, its locked black beat, and a different next target; plays
two complete single-stream rewards; checks nonrepeating four-way bubble
selection and the species-to-cue mapping; checks the reduced idle touch and
awake PWR polling cadences; temporarily mutes audio; and renders the production
rest screen at `15:00` without aging the real timer. It then forces one timed
common and one timed rare reward and renders all eight species in both common
and authored-rare modes without moving the rarity counters. It also checks the
translucent-species palette restrictions and leaves the board unmuted with
`audio_power=idle`. Complete every manual UI check listed in
[AGENTS.md](../AGENTS.md); the diagnostic rest preview does not prove the real
ten-minute trigger, thirty-minute elapsed countdown, standby aging, or expiry,
and serial output cannot prove reward appearance, double-tap/disconnect
behavior, visible pixels, touch alignment, motion direction, or audible quality.

For a camera or slow live-preview inspection, send `HOLD_REWARD` or
`HOLD_RARE`; the device freezes the exact full-water runtime renderer until
`GAME` is sent, without advancing the game or either rarity counter.
`HOLD_CREATURE 0` through `HOLD_CREATURE 7` and
`HOLD_RARE_CREATURE 0` through `HOLD_RARE_CREATURE 7` select an exact base or
rare-modified species for side-by-side review; the ordinal order is the order
recorded in `creatures/variation/variation_manifest.json`.

For motion review over the USB data connection, `ANIMATE_CREATURE 0` through
`ANIMATE_CREATURE 7` and `ANIMATE_RARE_CREATURE 0` through
`ANIMATE_RARE_CREATURE 7` continuously loop the selected normal or
rare-modified species through the exact production reward renderer. These
commands are intended for tethered camera inspection and do not advance the
game or rarity counters. Send `GAME` to stop the loop and redraw the active
round.

For deterministic catalog capture, send
`ANIMATE_VARIANT CREATURE PALETTE PATTERN RARE SEED`. Creature ordinals are
`0..7`; pattern ordinals `0..3` are solid, spots, stripes, and mottle. Rare must
be `0` for common textures or `1` with pattern `0` for the species-authored
rare treatment. The USB-only command rejects Plum deep and every palette that
automatic production play excludes for that species. It continuously animates
the exact requested combination until another preview command or `GAME`.

## Troubleshooting

### `audio=FAILED`

The application is present but the audio partition is missing or corrupt. Run
the canonical flash script again; do not use an application-only Arduino upload.

### Waiting for CST820 or a dark screen

Recheck that the board is V2. V1 has different controllers and is unsupported.

### `No serial ports found`

Use a known data cable, connect directly rather than through an unpowered hub,
and check OS serial permissions. A charge-only cable can light or charge the
board while exposing no port.

### Restore factory firmware

Use the factory image that matches the physical board revision. The pinned
Waveshare submodule contains its vendor firmware and instructions under
`vendor/waveshare-esp32-s3-touch-amoled-1.8/Firmware/`. A private per-device
backup is intentionally not stored in this public repository.

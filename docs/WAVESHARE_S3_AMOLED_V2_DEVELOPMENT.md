# Developing for the Waveshare ESP32-S3-Touch-AMOLED-1.8 V2

This is the reusable exact-board guide extracted from the Phonics Picker
project. It is intended for people and coding agents building any application
for the Waveshare **ESP32-S3-Touch-AMOLED-1.8 V2**.

It does not turn Phonics Picker into a generic starter project. Instead, it
identifies which knowledge and source paths are useful as a known-good board
reference, which contracts must be redesigned per application, and how to keep
the development loop fast without confusing development evidence with release
evidence.

Agents should start with
[`../.agents/skills/develop-waveshare-s3-amoled-v2/SKILL.md`](../.agents/skills/develop-waveshare-s3-amoled-v2/SKILL.md).
For work on the Phonics Picker product itself, [`../AGENTS.md`](../AGENTS.md),
[`../PRODUCT_SPEC.md`](../PRODUCT_SPEC.md), and
[`DEPLOYMENT.md`](DEPLOYMENT.md) remain authoritative.

The skill is intentionally a small Agent Skills-compatible router with no
Codex-only workflow or OpenAI-specific metadata. This guide and ordinary
repository tools hold the knowledge and safety contract, so another coding
agent, CI job, or human can follow the same process.

## Hard target boundary

This guide supports exactly:

- product name `ESP32-S3-Touch-AMOLED-1.8`;
- rear label `V2`;
- ESP32-S3R8 with 8 MB octal PSRAM and 16 MB flash;
- 368 x 448 portrait QSPI AMOLED with CO5300 controller; and
- CST820 capacitive touch.

It does not support the V1 SH8601/FT3168 revision, an ESP32-C6, another
Waveshare 1.8-inch board, or a generic ESP32-S3 display board. Waveshare's
[current documentation](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.8)
distinguishes the revisions and identifies the rear label as the visible
revision check.

Documentation and marketplace listings can lag a hardware revision. Establish
identity in this order:

1. human confirmation of the product name and `V2` rear label;
2. ESP32-S3 and 16 MB flash reported by the ROM loader/esptool;
3. expected controller/peripheral probes in a board-check application; and
4. the application-specific installed manifest or build identity.

Do not infer V2 solely because a serial port exists. Do not guess between
multiple ports. Flashing replaces the installed application, so confirm the
target and preserve or download the matching V2 factory image when recovery
matters.

## Board resources

| Capability | V2 component or interface | Notes |
| --- | --- | --- |
| MCU | ESP32-S3R8, dual core up to 240 MHz | Native USB is used here for flashing and diagnostics |
| Memory | 8 MB octal PSRAM, 16 MB NOR flash | Verify both on real hardware |
| Display | CO5300, 368 x 448, QSPI | V1 display code is incompatible |
| Touch | CST820, I2C plus interrupt | V1 FT3168 code is incompatible |
| Motion | QMI8658 six-axis IMU | Package orientation must be characterized against portrait display axes |
| Power | AXP2101 PMIC | Battery reporting and rail/codec/display sequencing need hardware tests |
| RTC | PCF85063 | Main-battery and optional backup behavior are distinct |
| Audio | ES8311 codec, onboard microphone and speaker | Speaker amplifier enable and codec idle state affect power and audible behavior |
| Storage | microSD/TF slot | Useful for development-time asset overrides; optional per application |
| Human controls | PWR and BOOT buttons | BOOT affects download mode; PWR also has board-level behavior |

At the pinned Waveshare source revision used by this repository, the Arduino
V2 pin configuration is:

| Function | GPIO |
| --- | --- |
| CO5300 QSPI data 0, 1, 2, 3 | 4, 5, 6, 7 |
| CO5300 clock, chip select | 11, 12 |
| Shared I2C SDA, SCL | 15, 14 |
| CST820 interrupt | 21 |
| ES8311 MCLK, BCLK, word select | 16, 9, 45 |
| ES8311 codec data pins | 10, 8 |
| Speaker-amplifier enable | 46 |
| SDMMC clock, command, data | 2, 1, 3 |

The maintained source for those values is
[`vendor/waveshare-esp32-s3-touch-amoled-1.8/examples/arduino-v2/libraries/Mylibrary/pin_config.h`](../vendor/waveshare-esp32-s3-touch-amoled-1.8/examples/arduino-v2/libraries/Mylibrary/pin_config.h).
Treat the table as a quick reference, not a replacement for the pinned source,
schematic, or a probe. If the vendor revision changes, review the diff before
updating either.

### Known topology and compatibility details

The following details are easy to miss when starting from a generic ESP32-S3
example:

- The V2 touch controller is marketed as CST820, while the current Arduino
  integration uses the compatible `Arduino_CST816x` driver and address `0x15`.
  Do not infer that the hardware is V1 or CST816 merely from that class name.
- The shared I2C bus also exposes the QMI8658 at `0x6B`, XCA/TCA9554 expander
  at `0x20`, AXP2101 at `0x34`, PCF85063 at `0x51`, and ES8311 at `0x18` in the
  current board design. Treat the I2C inventory as a qualification signal, not
  the only revision check.
- The proven startup path configures expander P0-P2 as outputs, drives them low,
  waits 20 ms, and then drives them high before peripheral initialization.
  Preserve that ordering until the schematic and physical tests justify a
  different reset/power sequence.
- The physical PWR signal is visible through expander channel P4. It is not
  ESP GPIO4, and the expander interrupt is not routed to an ESP32 wake GPIO.
  PWR therefore cannot directly wake indefinite deep sleep. The native touch
  interrupt on GPIO21 can wake some sleep modes, but changing from PWR-to-wake
  to touch-to-wake is a product decision.
- PMIC, RTC, IMU, and PWR interrupt paths involve the expander rather than
  independent native wake pins. Review the schematic before designing an
  interrupt or deep-sleep policy.
- With the portrait mapping validated by this game, screen-horizontal motion
  is derived from negative sensor Y and screen-vertical motion from sensor X.
  Recharacterize the axes whenever display rotation or enclosure orientation
  changes.
- The ES8311 output path uses ESP transmit GPIO8. GPIO10 is the unused receive/
  microphone direction in this output-only application. Do not allocate and
  clock an I2S receive channel when the product does not use the microphone.
- One full RGB565 framebuffer is 329,728 bytes. Compose off screen and present
  atomically when intermediate drawing states would be visible on the AMOLED.

[`POWER_AUDIT.md`](POWER_AUDIT.md) records the PWR/interrupt reasoning and
current display, touch, IMU, audio, and standby evidence. The current runtime
bring-up is in
[`firmware/PhonicsGame/PhonicsGame.ino`](../firmware/PhonicsGame/PhonicsGame.ino),
and the output-only audio sequence is in
[`firmware/PhonicsGame/AudioEngine.cpp`](../firmware/PhonicsGame/AudioEngine.cpp).
Preserve the proven expander/reset ordering when extracting a reusable board
layer.

For output shutdown, stop accepting work, invalidate or drain active work,
mute the codec, gate the amplifier low, replace output with silence, power down
the codec, and disable I2S only after no other task can be writing. For resume,
keep the amplifier gated while restoring clocks and muted codec state, prime
silence, then enable the amplifier and unmute. Verify the sequence audibly and
for idle power on the physical board.

Native USB CDC can disconnect or enumerate differently across sleep and reset.
Test tethered diagnostic behavior separately from untethered battery behavior.
A short PWR release is application policy; the roughly six-second PMIC hard-off
is a separate board behavior.

## Evidence levels

Keep claims labeled so reference material does not turn an untested capability
into a product guarantee:

- **Verified in this repository:** the exact V2 display and touch path, 8 MB
  PSRAM, 16 MB flash, native USB diagnostics, QMI8658 motion, ES8311/onboard
  speaker playback, AXP2101 battery reads, PWR handling, and the current
  Phonics Picker standby path. See [`../DEVICE_REPORT.md`](../DEVICE_REPORT.md)
  and [`POWER_AUDIT.md`](POWER_AUDIT.md) for their precise scopes and remaining
  physical gates.
- **Vendor-documented or source-referenced:** RTC, microphone, microSD, exposed
  pads, and capabilities not exercised by this product. Qualify them for a new
  application before claiming them.
- **Proposed workflow:** build receipts, guarded changed-region flashing,
  verifier profiles, a shared `BoardV2` layer, and factory qualification. They
  remain design guidance until the repository links implementations and tests.

## What another application should reuse

| Reuse | Useful source in this repository | Boundary |
| --- | --- | --- |
| Exact board identity and safety checks | [`HARDWARE.md`](HARDWARE.md), flash-script preflight | Keep human V2/port confirmation; use the new app's own flash plan |
| Reproducible Arduino environment | [`config/toolchain.env`](../config/toolchain.env), [`scripts/setup_toolchain.sh`](../scripts/setup_toolchain.sh) | Pin deliberately; do not assume these versions remain best forever |
| CO5300/CST820/QMI8658 source integration | pinned Waveshare submodule and [`vendor/slim`](../vendor/slim) | Preserve license and patch provenance; avoid copying unrelated vendor trees |
| Display and touch bring-up pattern | [`firmware/PhonicsGame/PhonicsGame.ino`](../firmware/PhonicsGame/PhonicsGame.ino) | Extract a board layer; do not copy product rendering or globals wholesale |
| ES8311 playback and idle behavior | [`firmware/PhonicsGame/AudioEngine.cpp`](../firmware/PhonicsGame/AudioEngine.cpp), [`POWER_AUDIT.md`](POWER_AUDIT.md) | Audio format, volume, resources, and perceptual gates are app-specific |
| Native host tests | [`tests`](../tests) and the pure firmware components they exercise | Test the new app's pure logic and layout; do not inherit phonics assertions |
| USB observability and physical verification pattern | [`scripts/verify_device.py`](../scripts/verify_device.py), production diagnostics | Define a versioned protocol and new app-specific profiles |
| Asset provenance and isolated review | [`CREATURE_SPRITE_PIPELINE.md`](CREATURE_SPRITE_PIPELINE.md) | Reuse experiment/promote separation, not the selected art or provider assumptions |

## What is not a board fact

The following belong specifically to Phonics Picker and must not silently
become defaults for another application:

- the `app3M_fat9M_16MB` partition scheme;
- application offset `0x10000` as part of this exact five-region bundle;
- the offline audio pack at `0x610000` and its format/index;
- every value and hash in `firmware/BUILD_MANIFEST.json`;
- the accepted card, font, replay, creature, phonics, speech, and reward assets;
- Phonics Picker USB commands, gameplay behavior, volume, timeouts, and power
  policy; and
- Phonics Picker's manual release checklist.

Another application must define and verify its own partition table, resource
ownership, compatibility rules, flash manifest, application identity,
diagnostic protocol, and physical release gates. Reusing this game's flash
script unchanged is unsafe because it would install unrelated product data.

### Licensing boundary

Public visibility is not permission to copy project-authored code. This
repository may not have a root license, while vendored dependencies retain
their own license files and notices. Agents may learn from the architecture and
workflow documented here, but must inspect the root and applicable dependency/
asset licenses before moving source or assets into another repository. If no
license grants reuse, do not copy. Adding or changing a root license is an owner
decision and should happen before this project is presented as a freely
reusable code library or starter kit.

## Recommended project shape

Keep hardware access outside the game or application layer:

```text
app/
  product state, rules, scenes, and input intentions
platform/waveshare_s3_amoled_v2/
  identity, display, touch, motion, power, RTC, audio, storage, USB diagnostics
host/
  clock, deterministic input, renderer/surface, audio/event spies
resources/
  source assets, generated pack, index, schema, provenance
tools/
  doctor, build, flash, verify, evidence, asset promotion
```

Prefer a small API such as `setup`, `update`, `render`, and `onInput` at the
application boundary. Keep the board layer exact rather than adding dynamic
support for unrelated ESP32 displays. Use fixed allocation in render/audio hot
paths and make clock, random input, and side effects injectable so ordinary
behavior can run on a host.

Large generated assets should have declarations in small headers and data
definitions in exactly one compiled source file, or live in a versioned
resource pack. Do not put multi-megabyte definitions and rendering logic into a
header included by frequently edited application code.

## The two-lane workflow

### Development lane

Optimize for the smallest reliable feedback loop:

1. classify the change;
2. run pure host tests or the host renderer when they can prove it;
3. use a development-only physical display/audio preview when perception
   matters;
4. build once and write a source-bound receipt;
5. flash only proven-compatible application-owned changed regions;
6. run the smallest relevant device profile; and
7. keep the result labeled as development evidence.

### Release lane

Optimize for reproducibility and recovery:

1. build cleanly from pinned inputs;
2. stage rather than mutate compiler-cache artifacts;
3. record exact hashes, sizes, partition offsets, schema, and compatibility
   identities;
4. install every region the application owns;
5. verify the installed identity and all relevant behavior; and
6. complete human display, touch, motion, power, and audio gates.

Never call a development partial flash a release. Do not remove perceptual
gates merely because a serial or framebuffer check passes.

## Change-impact matrix

Every project should encode this classification in a normal CLI or test tool.
The table is a starting policy, not permission to flash a particular device.

| Change | Fastest useful host proof | Likely device work |
| --- | --- | --- |
| Pure state/game logic | Native unit/property/trace tests | None unless integration risk changes |
| Layout or custom renderer | Host renderer plus golden frames | Requested states on real AMOLED; touch alignment when geometry changes |
| Touch routing | Native coordinate/gesture traces | Touch grid and edge/cancel behavior |
| Motion mapping | Native filtering/orientation traces | Physical orientation and drift check |
| Audio selection/state | Native event/format tests | Codec, loudness, sequence, idle/wake listening check |
| Asset candidate | Validation, contact sheet, exact composite | Development preview only; no promotion |
| Accepted runtime asset/resource | Pack/index/schema checks | Resource/application compatibility and perceptual check |
| Power, PMIC, sleep, wake | State-machine tests | Metering where claimed plus cable/battery/PWR scenarios |
| Board support, toolchain, partition, bootloader | Clean compile and manifest checks | Full install, recovery, and board qualification |
| Documentation/public media | Link/media validation | No flash unless the documentation makes a physical claim |
| Unknown or mixed | Broader fail-closed suite | Full install and relevant release profiles |

## Build and flash receipts

A reusable development tool should emit versioned JSON rather than requiring
an agent to infer freshness. A build receipt should cover source/diff inputs,
toolchain, board profile, dependencies, resource compatibility, and artifact
hashes. A flash receipt should add physical device identity, port/location,
preflight results, installed regions, hashes, and reset/reconnect outcome.

Safe changed-region flashing requires a previously trusted full-install
receipt and matching bootloader, partition, app/resource schema, and device
identity. Missing evidence means perform the application's full canonical
install. Safety logic belongs in the CLI and schemas so a human, CI job, or any
agent client gets the same decision.

## Resource and asset architecture

For media-heavy applications, separate code iteration from resource transfer.
A resource pack should have a bounded, self-describing table of contents with
schema version, asset IDs, offsets, lengths, hashes, and application
compatibility. Validate all bounds before use.

Useful stages are:

- initially, whole application versus whole resource-pack writes;
- later, content-addressed or aligned resource chunks with an atomic index;
- optionally, microSD development overrides for rapid asset review; and
- deterministic flash-resident resources for a release when offline behavior
  and reproducibility matter.

Asset generation is an authoring operation. Store prompt/seed/provider/model,
cost, source hash, output hash, transformations, and review state. Keep
candidates outside accepted runtime paths. Promotion must be explicit,
transactional, and independently testable.

## Observability designed for agents and humans

Use a bounded, nonblocking serial/USB protocol. Separate structured responses
from logs and version the protocol. Binary payloads need explicit length and
CRC. At minimum, expose:

- board, build, resource, partition, and protocol identities;
- subsystem health and last fault;
- reset reason, heap/PSRAM high-water marks, render and flush timing, I2C
  failures, and audio underruns;
- deterministic scene/input commands for test-only builds or authenticated
  maintenance contexts; and
- frame CRC or framebuffer capture where the renderer permits it.

Keep destructive actions visibly distinct and require explicit device
selection and confirmation. One process should own a serial port at a time.

## Factory qualification and multiple boards

Before treating a newly purchased board as interchangeable, run a small
qualification application that records:

- rear-label attestation and stable device identity;
- ESP32-S3, 16 MB flash, and 8 MB PSRAM;
- display color bars and full-panel addressing;
- touch grid, interrupt, and edge behavior;
- IMU identity and known physical orientations;
- speaker and, if used, microphone;
- PMIC/battery/PWR behavior;
- RTC; and
- microSD when the application uses it.

Store a local inventory receipt keyed by eFuse MAC and physical USB location,
with a human alias. When several devices are available, assign roles such as
golden/release, daily development, and recovery/soak. Port locks, powered-hub
slot identity, and explicit test roles matter more than adding parallel agents
that compete for the same serial device.

## Arduino and ESP-IDF

Arduino is a reasonable starting point for an application using the existing
known-good integration. ESP-IDF can improve component boundaries, CMake/Ninja
incremental builds, target-specific flashing, pytest-based device tests,
debugging, coredumps, and OTA support. Framework choice should follow a small
measured vertical slice, not a wholesale migration.

Compare clean, no-change, and one-file build times; application flash and boot;
frame-time percentiles; heap/PSRAM; and display, touch, motion, audio, power,
and USB parity. Do not combine a framework evaluation with an LVGL or renderer
rewrite, because the result will not identify which change helped.

The current Waveshare managed component and first-party examples are useful
references, but characterize the exact revision and configuration path before
making them a new application's dependency.

## Open-source patterns worth copying

- [Waveshare's exact-board repository](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.8):
  board-check firmware, first-party examples, firmware archives/manifests, and
  affected-example CI.
- [Espressif esp-bsp](https://github.com/espressif/esp-bsp): a consistent
  board/application capability boundary and managed components.
- [M5Unified](https://github.com/m5stack/M5Unified): a thin application-facing
  hardware API spanning Arduino and ESP-IDF; avoid importing its broad dynamic
  board-detection scope here.
- [Meshtastic firmware](https://github.com/meshtastic/firmware): declarative
  board variants, native tests, sanitizers, and hardware-in-the-loop practice.
- [Meshtastic MCP](https://github.com/meshtastic/meshtastic-mcp): an
  agent-neutral CLI/MCP/device-lab pattern with discovery, doctor, port
  ownership, tiered tests, and multiple-device roles.
- [WLED](https://github.com/wled/WLED): separation of application,
  configuration/content, and update paths. Networking is not automatically
  appropriate for every product.
- [LVGL PC integration](https://lvgl.io/docs/open/integration/pc): run the same
  UI code on a host for future LVGL applications. A custom renderer can adopt
  the same pattern without migrating to LVGL.

## Current reusable maturity

This repository is currently a verified product plus a strong exact-board
reference, not a turnkey new-application SDK.

Ready to use now:

- exact V2 identity and safety guidance;
- pinned toolchain and upstream source baselines;
- known-good display, touch, IMU, power, audio, USB, and framebuffer source
  paths;
- native-test, asset-provenance, device-verification, and evidence patterns;
- the reusable change-impact and development/release design in this guide; and
- an agent-neutral skill that routes tasks without importing product behavior.

Not implemented as reusable artifacts yet:

- an extracted `BoardV2` library;
- a machine-readable board profile checked against source and documentation;
- a factory-qualification application;
- a minimal tested new-application partition example;
- general build/flash receipts and their JSON schemas;
- guarded changed-region flashing;
- a generic `doctor`, device registry, port lock, or verifier-profile CLI; and
- a versioned generic diagnostic protocol.

Until those artifacts exist and are tested, inspect and adapt the named source
paths, create application-specific tooling, and use the application's full
validated install. Do not invent the proposed commands, claim that this is a
drop-in board package, or bypass the existing Phonics Picker deployment
contract when working on this game.

## Prompt for another agent

Point an agent at the repository and use a request like:

> Read `.agents/skills/develop-waveshare-s3-amoled-v2/SKILL.md` and
> `docs/WAVESHARE_S3_AMOLED_V2_DEVELOPMENT.md`. I am building a different
> application for the exact rear-labeled V2 board. Reuse only the board-level
> integration and workflow patterns. Define a new application, partition and
> resource contract, flash manifest, and verification plan; do not install or
> inherit Phonics Picker's audio pack or product behavior.

That gives the agent the accumulated board knowledge while preserving the new
application's product identity and deployment safety.

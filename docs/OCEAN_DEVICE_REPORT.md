# Ocean creature device report

## 2026-08-24 — semantic color and protected-anatomy gate

Target and install evidence:

- The user visually confirmed the rear label says **V2**.
- Read-only preflight identified an ESP32-S3 revision 0.2 with 8 MB embedded
  PSRAM, USB Serial/JTAG, and 16 MB flash.
- The explicit serial target was `/dev/cu.usbmodem1401`; no ambiguous port was
  selected.
- `scripts/flash_ocean_demo.sh` wrote and esptool hash-verified the ocean-demo
  bootloader at `0x0`, partition table at `0x8000`, OTA selector at `0xe000`,
  and application at `0x10000`. It did not rewrite the phonics audio-pack
  region at `0x610000`.
- Flashed application: `build/ocean-demo/OceanCreatureDemo.ino.bin`, 495,680
  bytes, SHA-256
  `a035e1edcfb2df64e2b5446ccdfd8a70dee51282d2d26cd5812430943ebede9d`.

Automated protection evidence from the flashed firmware:

```text
[selftest] PASS creatures=4 frames=16 safe=11971 protected=53318 exercised=2245 invalid_safe=0 protected_changes=0
```

`scripts/verify_ocean_demo.py` accepted that response. This proves that the
flashed semantic and one-bit pattern-safe data cover all four creatures and all
four animation frames, the test probe exercised a nonempty safe region, no safe
pixel was transparent, and the runtime probe changed zero protected pixels.

Physical AMOLED comparison:

- Automatic cycling was stopped and the Giant octopus / Kelp green frame was
  frozen so geometry could not drift between views.
- The normal `COLOR` frame was used as the baseline.
- `SAFE MASK` was shown only as a diagnostic; its purple/green coloring is not
  a shipping palette.
- `TEST PROBE` retained normal creature coloring and added test dots only to
  the authored mantle-safe region.
- After switching back to the identical frozen `COLOR` frame, the user
  confirmed the test looked good. The protected eye, contour, mouth area, and
  arms remained visually intact.
- The board was returned to `COLOR` with animation and automatic palette/species
  cycling enabled.

This report closes stages 1 and 2: semantic runtime color ramps and
pattern-safe/protected-anatomy maps. It does not claim that stages 3 and 4
(shipping procedural textures and rare pre-baked treatments) are implemented.

## Later production-consumer evidence

The historical statement above remains correct for the specific four-creature
Ocean demo flashed in that run. The later eight-creature assets, Stage-3 common
textures, and Stage-4 authored rare treatments have since been integrated,
compiled, flashed, and camera-reviewed through the production PhonicsGame
consumer. Its later exhaustive production-consumer capture records all 180
finite allowed palette/texture/rare combinations on the confirmed V2 display,
plus a real game-transition walkthrough. That current evidence, including exact
artifact and video hashes, is recorded in
[`DEVICE_REPORT.md`](../DEVICE_REPORT.md).

The separate eight-creature Ocean demo itself was host-compiled but was not
flashed during the later production run. Its complete Stage-3/Stage-4 self-test
and diagnostic AMOLED gate therefore remain pending; production-consumer proof
must not be restated as if that separate demo application had passed them.

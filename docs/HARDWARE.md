# Hardware and safety

## Exact board

Use the Waveshare **ESP32-S3-Touch-AMOLED-1.8 V2**, product SKU 29957 or 29958.
The name is easy to confuse with other 1.8-inch Waveshare boards, so check all
of these before flashing:

- `ESP32-S3-Touch-AMOLED-1.8` product name
- `V2` printed on the rear label
- 368 x 448 portrait AMOLED
- CO5300 display controller
- CST820 capacitive-touch controller
- 8 MB PSRAM and 16 MB flash

Waveshare's [current documentation](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.8)
explains that V1 uses SH8601 + FT3168 while V2 uses CO5300 + CST820. The
[official product page](https://www.waveshare.com/product/esp32-s3-touch-amoled-1.8.htm)
lists the onboard speaker, QMI8658 IMU, AXP2101 power management, 8 MB PSRAM,
and 16 MB flash used by this experience.

## Required equipment

| Item | Why it is needed |
| --- | --- |
| V2 board | Runs the complete game; screen, touch, IMU, codec, and speaker are onboard. |
| USB-C data cable | Supplies power and carries firmware/serial data. Charge-only cables do not work. |
| Computer | Runs the checked-in setup, tests, build, flash, and verifier. |

No external speaker, microphone, SD card, breadboard, or Wi-Fi is required.

## Optional battery

The board can run entirely from USB. For portable use, select a protected
3.7 V lithium cell with the board's MX1.25 2-pin plug and enough physical
clearance for the enclosure. Waveshare recommends approximately 3.85 x 24 x
28 mm / 400 mAh in its documentation.

Connector polarity is not guaranteed across generic battery listings. Compare
the wire polarity with the Waveshare schematic/product markings before
connection; never force a similar-looking JST plug. Do not use a swollen,
punctured, or unprotected cell. Keep the board dry; it is not waterproof.

## Controls and ports

- **USB-C:** power, flashing, and 115200-baud maintenance console
- **PWR:** short press/release toggles logical standby; approximately six-second
  hold invokes the board's hardware power-off
- **BOOT:** ESP32 boot strap; not used by the game
- **touchscreen:** play/replay control and the two answer cards
- **speaker:** all prompts, feedback, and phonics audio
- **microphone:** present on the board but never initialized or used here
- **TF/microSD slot:** present but unused

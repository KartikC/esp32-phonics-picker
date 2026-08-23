# Contributing

Run the complete public verification path before opening a change:

```sh
./scripts/test.sh --firmware
```

Keep the supported target limited to the Waveshare ESP32-S3-Touch-AMOLED-1.8
V2. If a product-visible behavior changes, update `PRODUCT_SPEC.md`, the README
UI explanation, host tests, and physical-device evidence together.

The files under `audio/generated/device-pcm/`, the packed audio image, its
manifest, and `AudioAssetIndex.h` form one integrity unit. Change them only via
the authoring/packing scripts and review audio on the onboard speaker. The
checked-in font headers are likewise authoritative for ordinary builds; their
source TTF files are needed only when deliberately regenerating those headers.

Do not commit tool caches, build output, per-device flash backups, raw serial
captures, microphone recordings, API credentials, personal identifiers, or
local absolute paths. Preserve upstream files kept alongside vendored material.

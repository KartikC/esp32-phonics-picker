#!/bin/zsh
set -euo pipefail

project_root=${0:A:h:h}
vendor_root="$project_root/vendor/waveshare-esp32-s3-touch-amoled-1.8/examples/arduino-v2/libraries"
slim_root="$project_root/vendor/slim"
build_root="$project_root/build/incremental-slim/PhonicsGame"
mkdir -p "$build_root"

"$project_root/.tools/arduino-cli-1.5.1/arduino-cli" \
  --config-file "$project_root/.arduino/arduino-cli.yaml" compile \
  --fqbn 'esp32:esp32:esp32s3:FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=opi,CDCOnBoot=cdc' \
  --jobs 8 \
  --build-path "$build_root" \
  --library "$slim_root/GFX_Library_for_Arduino" \
  --library "$slim_root/Arduino_DriveBus" \
  --library "$slim_root/SensorLib" \
  --library "$vendor_root/Adafruit_BusIO" \
  --library "$vendor_root/Adafruit_XCA9554" \
  --library "$vendor_root/Mylibrary" \
  "$project_root/firmware/PhonicsGame"

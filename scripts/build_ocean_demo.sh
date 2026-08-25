#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$project_root/config/toolchain.env"
cd "$project_root"

python_bin=$(command -v python3 || command -v python || true)
if [[ -z "$python_bin" ]]; then
  echo "Python 3 is required." >&2
  exit 1
fi

"$project_root/scripts/setup_toolchain.sh"
"$python_bin" "$project_root/scripts/verify_repo.py"
"$python_bin" "$project_root/scripts/build_creature_pack.py" --check
"$python_bin" "$project_root/scripts/build_creature_variations.py" --check

vendor_root="$project_root/vendor/waveshare-esp32-s3-touch-amoled-1.8/examples/arduino-v2/libraries"
slim_root="$project_root/vendor/slim"
build_root="$project_root/build/ocean-demo"
arduino_cli="$project_root/.tools/arduino-cli-$ARDUINO_CLI_VERSION/arduino-cli"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) arduino_cli="${arduino_cli}.exe" ;;
esac

mkdir -p "$build_root"
export SOURCE_DATE_EPOCH="$BUILD_SOURCE_DATE_EPOCH"
export TZ=UTC
export LC_ALL=C
reproducible_flags="-DARDUINO_HOST_OS=\"reproducible\" -DARDUINO_FQBN=\"$BOARD_FQBN\" -DESP32=ESP32 -DCORE_DEBUG_LEVEL=0 -DARDUINO_RUNNING_CORE=1 -DARDUINO_EVENT_RUNNING_CORE=1 -DBOARD_HAS_PSRAM -DARDUINO_USB_MODE=1 -DARDUINO_USB_CDC_ON_BOOT=1 -DARDUINO_USB_MSC_ON_BOOT=0 -DARDUINO_USB_DFU_ON_BOOT=0 -ffile-prefix-map=$project_root=. -fmacro-prefix-map=$project_root=."

"$arduino_cli" \
  --config-file "$project_root/.arduino/arduino-cli.yaml" compile \
  --fqbn "$BOARD_FQBN" \
  --jobs "${BUILD_JOBS:-8}" \
  --build-path "$build_root" \
  --build-property "build.extra_flags=$reproducible_flags" \
  --library "$slim_root/GFX_Library_for_Arduino" \
  --library "$vendor_root/Adafruit_BusIO" \
  --library "$vendor_root/Adafruit_XCA9554" \
  --library "$vendor_root/Mylibrary" \
  "$project_root/firmware/OceanCreatureDemo"

application="$build_root/OceanCreatureDemo.ino.bin"
application_bytes=$(wc -c < "$application" | tr -d ' ')
if (( application_bytes >= 0x300000 )); then
  echo "Ocean demo exceeds the 3 MB application partition: $application_bytes bytes" >&2
  exit 1
fi
echo "Ocean demo firmware compiled: $application ($application_bytes bytes)"

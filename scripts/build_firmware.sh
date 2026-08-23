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

vendor_root="$project_root/vendor/waveshare-esp32-s3-touch-amoled-1.8/examples/arduino-v2/libraries"
slim_root="$project_root/vendor/slim"
build_root="$project_root/build/production/PhonicsGame"
arduino_cli="$project_root/.tools/arduino-cli-$ARDUINO_CLI_VERSION/arduino-cli"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) arduino_cli="${arduino_cli}.exe" ;;
esac

mkdir -p "$build_root"
export SOURCE_DATE_EPOCH="$BUILD_SOURCE_DATE_EPOCH"
export TZ=UTC
export LC_ALL=C
path_flags="-ffile-prefix-map=$project_root=. -fmacro-prefix-map=$project_root=."
"$arduino_cli" \
  --config-file "$project_root/.arduino/arduino-cli.yaml" compile \
  --fqbn "$BOARD_FQBN" \
  --jobs "${BUILD_JOBS:-8}" \
  --build-path "$build_root" \
  --build-property "compiler.c.extra_flags=$path_flags" \
  --build-property "compiler.cpp.extra_flags=$path_flags" \
  --build-property "compiler.S.extra_flags=$path_flags" \
  --library "$slim_root/GFX_Library_for_Arduino" \
  --library "$slim_root/Arduino_DriveBus" \
  --library "$slim_root/SensorLib" \
  --library "$vendor_root/Adafruit_BusIO" \
  --library "$vendor_root/Adafruit_XCA9554" \
  --library "$vendor_root/Mylibrary" \
  "$project_root/firmware/PhonicsGame"

"$python_bin" "$project_root/scripts/verify_repo.py" --build-dir "$build_root"
echo "Firmware build verified: $build_root"

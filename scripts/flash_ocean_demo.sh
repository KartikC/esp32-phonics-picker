#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$project_root/config/toolchain.env"
cd "$project_root"

port=""
confirmed=false
build_first=true
usage() {
  echo "Usage: $0 --port PORT [--yes] [--no-build]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      port=$2
      shift 2
      ;;
    --yes)
      confirmed=true
      shift
      ;;
    --no-build)
      build_first=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$port" ]]; then
  echo "A serial port is required. Run ./scripts/list_ports.sh, then pass --port." >&2
  exit 2
fi
if [[ "$port" != COM* && ! -e "$port" ]]; then
  echo "Serial port does not exist: $port" >&2
  exit 1
fi

if [[ "$build_first" == true ]]; then
  ./scripts/build_ocean_demo.sh
else
  ./scripts/setup_toolchain.sh
  python3 scripts/build_creature_variations.py --check
fi

build_root="$project_root/build/ocean-demo"
application="$build_root/OceanCreatureDemo.ino.bin"
bootloader="$build_root/OceanCreatureDemo.ino.bootloader.bin"
partitions="$build_root/OceanCreatureDemo.ino.partitions.bin"
ota_selector="$build_root/boot_app0.bin"
for artifact in "$application" "$bootloader" "$partitions" "$ota_selector"; do
  if [[ ! -s "$artifact" ]]; then
    echo "Ocean demo flash artifact is missing or empty: $artifact" >&2
    exit 1
  fi
done

esptool="$project_root/.arduino/data/packages/esp32/tools/esptool_py/5.3.1/esptool"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) esptool="${esptool}.exe" ;;
esac
if [[ ! -x "$esptool" ]]; then
  echo "Pinned esptool was not installed at $esptool" >&2
  exit 1
fi

echo "Checking target chip and flash on $port..."
flash_info=$(
  "$esptool" --chip esp32s3 --port "$port" --before default-reset --after hard-reset flash-id 2>&1
)
echo "$flash_info"
if [[ "$flash_info" != *"Detected flash size: 16MB"* ]]; then
  echo "Refusing to flash: the target did not report the required 16 MB flash." >&2
  exit 1
fi

if [[ "$confirmed" != true ]]; then
  if [[ ! -t 0 ]]; then
    echo "Confirmation is required. Inspect the V2 label and port, then rerun with --yes." >&2
    exit 1
  fi
  echo
  echo "This replaces the current application on $port with the separate ocean demo."
  echo "Required target: Waveshare ESP32-S3-Touch-AMOLED-1.8 V2 (CO5300 + CST820)."
  read -r -p "Type OCEAN-V2 to continue: " answer
  if [[ "$answer" != "OCEAN-V2" ]]; then
    echo "Flash cancelled."
    exit 1
  fi
fi

"$esptool" --chip esp32s3 --port "$port" --baud 921600 \
  --before default-reset --after hard-reset write-flash \
  --flash-mode dio --flash-freq 80m --flash-size 16MB \
  0x0 "$bootloader" \
  0x8000 "$partitions" \
  0xe000 "$ota_selector" \
  0x10000 "$application"

echo
echo "Ocean demo bootloader, partition table, OTA selector, and application flashed and verified by esptool."
echo "This demo intentionally does not rewrite the canonical phonics audio-pack region at 0x610000."
echo "Next: python3 scripts/verify_ocean_demo.py --port $port"
echo "Then send ? at 115200 baud for the physical display-test controls."

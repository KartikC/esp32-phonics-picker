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
  ./scripts/build_firmware.sh
else
  ./scripts/setup_toolchain.sh
fi

build_root="$project_root/build/production/PhonicsGame"
"$python_bin" scripts/verify_repo.py --build-dir "$build_root"
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
  echo "This replaces the factory application on $port."
  echo "Required target: Waveshare ESP32-S3-Touch-AMOLED-1.8 V2 (CO5300 + CST820)."
  read -r -p "Type V2 to continue: " answer
  if [[ "$answer" != "V2" ]]; then
    echo "Flash cancelled."
    exit 1
  fi
fi

"$esptool" --chip esp32s3 --port "$port" --baud 921600 \
  --before default-reset --after hard-reset write-flash \
  --flash-mode dio --flash-freq 80m --flash-size 16MB \
  0x0 "$build_root/PhonicsGame.ino.bootloader.bin" \
  0x8000 "$build_root/PhonicsGame.ino.partitions.bin" \
  0xe000 "$build_root/boot_app0.bin" \
  0x10000 "$build_root/PhonicsGame.ino.bin" \
  0x610000 "$project_root/audio/generated/phonics-audio-pack.bin"

echo
echo "Application and audio pack flashed and verified by esptool."
echo "Next: $python_bin scripts/verify_device.py --port $port"

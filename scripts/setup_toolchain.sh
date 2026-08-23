#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$project_root/config/toolchain.env"
cd "$project_root"

python_bin=""
if command -v python3 >/dev/null 2>&1; then
  python_bin=python3
elif command -v python >/dev/null 2>&1; then
  python_bin=python
else
  echo "Python 3 is required." >&2
  exit 1
fi

vendor_root="$project_root/vendor/waveshare-esp32-s3-touch-amoled-1.8"
vendor_probe="$vendor_root/examples/arduino-v2/libraries/Adafruit_BusIO/library.properties"
if [[ ! -f "$vendor_probe" ]]; then
  if [[ ! -e "$project_root/.git" ]]; then
    echo "The Waveshare submodule is absent and this is not a Git clone." >&2
    echo "Clone with: git clone --recurse-submodules REPOSITORY_URL" >&2
    exit 1
  fi
  echo "Initializing the pinned Waveshare submodule..."
  git submodule update --init --recursive
fi

if [[ -d "$vendor_root/.git" || -f "$vendor_root/.git" ]]; then
  actual_vendor_commit=$(git -C "$vendor_root" rev-parse HEAD)
  if [[ "$actual_vendor_commit" != "$WAVESHARE_COMMIT" ]]; then
    echo "Waveshare submodule is at $actual_vendor_commit; restoring pinned $WAVESHARE_COMMIT." >&2
    git submodule update --init --recursive --checkout
    actual_vendor_commit=$(git -C "$vendor_root" rev-parse HEAD)
  fi
  if [[ "$actual_vendor_commit" != "$WAVESHARE_COMMIT" ]]; then
    echo "Unable to resolve the pinned Waveshare commit $WAVESHARE_COMMIT." >&2
    exit 1
  fi
fi

tool_dir="$project_root/.tools/arduino-cli-$ARDUINO_CLI_VERSION"
cli_name=arduino-cli
archive_name=""
archive_sha=""

os_name=$(uname -s)
arch_name=$(uname -m)
case "$os_name:$arch_name" in
  Darwin:arm64)
    archive_name="arduino-cli_${ARDUINO_CLI_VERSION}_macOS_ARM64.tar.gz"
    archive_sha="cb952e8c1621c95ef5f1d17831c945e3d0ec5973f89c557a7ec8feb9c4f7d4c9"
    ;;
  Darwin:x86_64)
    archive_name="arduino-cli_${ARDUINO_CLI_VERSION}_macOS_64bit.tar.gz"
    archive_sha="c982e940027996bea9901050e95fae99c59c1dcfee54beedecaf28141e7bf2e7"
    ;;
  Linux:x86_64)
    archive_name="arduino-cli_${ARDUINO_CLI_VERSION}_Linux_64bit.tar.gz"
    archive_sha="28a8e119c498a25607821c36cb2dc49e8463941b261a0d99091baa7bc692dd2b"
    ;;
  Linux:aarch64|Linux:arm64)
    archive_name="arduino-cli_${ARDUINO_CLI_VERSION}_Linux_ARM64.tar.gz"
    archive_sha="1e69e077479f300614d4551334e0a33f08ee40b04315d83b8e7e0e94f0d0ee62"
    ;;
  MINGW*:*|MSYS*:*|CYGWIN*:*)
    archive_name="arduino-cli_${ARDUINO_CLI_VERSION}_Windows_64bit.zip"
    archive_sha="fabe42e0eb04d00e776a66178299ff95a46c623dbc260f997e58fd514853dd40"
    cli_name=arduino-cli.exe
    ;;
  *)
    echo "Unsupported host: $os_name $arch_name" >&2
    echo "Supported: macOS Intel/Apple Silicon, Linux x86-64/ARM64, Windows Git Bash." >&2
    exit 1
    ;;
esac

arduino_cli="$tool_dir/$cli_name"
if [[ ! -x "$arduino_cli" ]]; then
  command -v curl >/dev/null 2>&1 || {
    echo "curl is required to download the pinned Arduino CLI." >&2
    exit 1
  }
  download_dir=$(mktemp -d "${TMPDIR:-/tmp}/phonics-cli.XXXXXX")
  trap 'rm -rf "$download_dir"' EXIT
  archive_path="$download_dir/$archive_name"
  release_url="https://github.com/arduino/arduino-cli/releases/download/v${ARDUINO_CLI_VERSION}/${archive_name}"
  echo "Downloading Arduino CLI $ARDUINO_CLI_VERSION..."
  curl --fail --location --retry 3 --output "$archive_path" "$release_url"
  actual_sha=$(
    "$python_bin" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$archive_path"
  )
  if [[ "$actual_sha" != "$archive_sha" ]]; then
    echo "Arduino CLI archive checksum mismatch." >&2
    echo "Expected: $archive_sha" >&2
    echo "Actual:   $actual_sha" >&2
    exit 1
  fi
  mkdir -p "$tool_dir"
  if [[ "$archive_name" == *.zip ]]; then
    "$python_bin" -m zipfile -e "$archive_path" "$tool_dir"
  else
    tar -xzf "$archive_path" -C "$tool_dir"
  fi
  chmod +x "$arduino_cli"
fi

cli_version=$("$arduino_cli" version)
if [[ "$cli_version" != *"Version: $ARDUINO_CLI_VERSION"* ]]; then
  echo "Unexpected Arduino CLI: $cli_version" >&2
  exit 1
fi

installed_core=$(
  "$arduino_cli" --config-file "$project_root/.arduino/arduino-cli.yaml" core list 2>/dev/null |
    awk '$1 == "esp32:esp32" {print $2}'
)
if [[ "$installed_core" != "$ARDUINO_ESP32_VERSION" ]]; then
  mkdir -p .arduino/data .arduino/downloads .arduino/user .arduino/cache
  echo "Installing Arduino-ESP32 $ARDUINO_ESP32_VERSION..."
  "$arduino_cli" --config-file "$project_root/.arduino/arduino-cli.yaml" core update-index
  "$arduino_cli" --config-file "$project_root/.arduino/arduino-cli.yaml" \
    core install "esp32:esp32@$ARDUINO_ESP32_VERSION"
  installed_core=$(
    "$arduino_cli" --config-file "$project_root/.arduino/arduino-cli.yaml" core list |
      awk '$1 == "esp32:esp32" {print $2}'
  )
fi
if [[ "$installed_core" != "$ARDUINO_ESP32_VERSION" ]]; then
  echo "Expected Arduino-ESP32 $ARDUINO_ESP32_VERSION, found ${installed_core:-none}." >&2
  exit 1
fi

echo "Toolchain ready: Arduino CLI $ARDUINO_CLI_VERSION, Arduino-ESP32 $ARDUINO_ESP32_VERSION"

#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$project_root/config/toolchain.env"
arduino_cli="$project_root/.tools/arduino-cli-$ARDUINO_CLI_VERSION/arduino-cli"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) arduino_cli="${arduino_cli}.exe" ;;
esac

if [[ ! -x "$arduino_cli" ]]; then
  echo "Toolchain is not installed. Run ./scripts/setup_toolchain.sh first." >&2
  exit 1
fi

"$arduino_cli" --config-file "$project_root/.arduino/arduino-cli.yaml" board list

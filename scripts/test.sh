#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

python_bin=$(command -v python3 || command -v python || true)
if [[ -z "$python_bin" ]]; then
  echo "Python 3 is required." >&2
  exit 1
fi

with_firmware=false
if [[ "${1:-}" == "--firmware" ]]; then
  with_firmware=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--firmware]" >&2
  exit 2
fi

"$python_bin" scripts/verify_repo.py

cxx=${CXX:-c++}
command -v "$cxx" >/dev/null 2>&1 || {
  echo "A C++17 compiler is required for the host tests (set CXX if needed)." >&2
  exit 1
}
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/phonics-tests.XXXXXX")
trap 'rm -rf "$test_dir"' EXIT
"$cxx" -std=c++17 -Wall -Wextra -pedantic tests/game_engine_test.cpp \
  -o "$test_dir/game_engine_test"
"$test_dir/game_engine_test"
echo "Game engine tests passed"

if [[ "$with_firmware" == true ]]; then
  ./scripts/build_firmware.sh
fi

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
for test_source in \
  tests/game_engine_test.cpp \
  tests/card_stone_asset_test.cpp \
  tests/creature_reward_selector_test.cpp \
  tests/reward_audio_selector_test.cpp \
  tests/mute_controller_test.cpp \
  tests/audio_idle_policy_test.cpp; do
  test_name=$(basename "$test_source" .cpp)
  "$cxx" -std=c++17 -Wall -Wextra -pedantic "$test_source" \
    -o "$test_dir/$test_name"
  "$test_dir/$test_name"
  echo "$test_name passed"
done

if [[ "$with_firmware" == true ]]; then
  ./scripts/build_firmware.sh
fi

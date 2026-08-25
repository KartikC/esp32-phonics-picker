#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

python_bin=$(command -v python3 || command -v python || true)
if [[ -z "$python_bin" ]]; then
  echo "Python 3 is required." >&2
  exit 1
fi

"$python_bin" scripts/build_creature_pack.py
"$python_bin" scripts/build_creature_pack.py --check
"$python_bin" -m py_compile scripts/generate_creature_animation.py
"$python_bin" scripts/review_creature_animation.py
"$python_bin" scripts/build_creature_variations.py
"$python_bin" scripts/build_creature_variations.py --check
"$python_bin" scripts/verify_creature_contract.py
if [[ "${1:-}" == "--firmware" ]]; then
  ./scripts/build_ocean_demo.sh
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--firmware]" >&2
  exit 2
fi

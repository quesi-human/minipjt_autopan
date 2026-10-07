#!/usr/bin/env bash
set -euo pipefail
camera_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
camera_python="${CAMERA_PYTHON:-$camera_script_dir/.venv/bin/python}"
if [[ ! -x "$camera_python" && -x "$camera_script_dir/../.venv/bin/python" ]]; then
  camera_python="$camera_script_dir/../.venv/bin/python"
fi
if [[ ! -x "$camera_python" ]]; then
  echo 'README의 Python 환경 설치를 먼저 수행하세요.' >&2
  exit 1
fi
exec "$camera_python" "$camera_script_dir/web-preview.py" --yolo "$@"

#!/usr/bin/env bash
set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
  echo 'sudo bash로 실행해 주세요.' >&2
  exit 1
fi

if ! command -v udevadm >/dev/null; then
  echo 'udev가 필요합니다. Ubuntu에서는 sudo apt install udev로 설치하세요.' >&2
  exit 1
fi
udevadm control --ping

stlink_target_user="${SUDO_USER:-}"
if [[ -z "$stlink_target_user" || "$stlink_target_user" == root ]]; then
  echo '일반 사용자 WSL 터미널에서 sudo bash install-permissions.sh로 실행하세요.' >&2
  exit 1
fi

if ! getent group plugdev >/dev/null; then
  groupadd plugdev
fi
if [[ " $(id -nG "$stlink_target_user") " != *' plugdev '* ]]; then
  usermod -aG plugdev "$stlink_target_user"
  echo "${stlink_target_user}를 plugdev 그룹에 추가했습니다. 적용 후 WSL 세션을 다시 로그인하세요."
fi

stlink_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install -m 0644 "$stlink_script_dir/99-stlink-wsl.rules" /etc/udev/rules.d/99-stlink-wsl.rules
udevadm control --reload-rules
udevadm trigger --action=add --subsystem-match=usb --attr-match=idVendor=0483 --attr-match=idProduct=374b
udevadm settle
echo 'ST-LINK USB 권한 규칙 설치 및 적용 완료 (plugdev 그룹, 0660).'

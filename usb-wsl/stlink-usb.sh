#!/usr/bin/env bash
set -euo pipefail

usbipd_exe="${USBIPD_EXE:-}"
stlink_hardware_id='0483:374b'
stlink_selector=(--hardware-id "$stlink_hardware_id")
if [[ -n "${STLINK_BUSID:-}" ]]; then
  stlink_selector=(--busid "$STLINK_BUSID")
fi

find_usbipd() {
  if [[ -z "$usbipd_exe" ]]; then
    usbipd_exe="$(command -v usbipd.exe || true)"
    usbipd_exe="${usbipd_exe:-/mnt/c/Program Files/usbipd-win/usbipd.exe}"
  fi
  if [[ ! -f "$usbipd_exe" ]]; then
    echo "usbipd.exe를 찾을 수 없습니다. Windows에 설치하거나 USBIPD_EXE를 지정하세요." >&2
    return 1
  fi
}

find_programmer() {
  programmer_cli="${STM32_PROGRAMMER_CLI:-}"
  if [[ -z "$programmer_cli" ]]; then
    programmer_cli="$(command -v STM32_Programmer_CLI || true)"
  fi
  if [[ -z "$programmer_cli" ]]; then
    shopt -s nullglob
    stlink_programmers=("${XDG_DATA_HOME:-$HOME/.local/share}"/stm32cube/bundles/programmer/*/bin/STM32_Programmer_CLI)
    shopt -u nullglob
    if (( ${#stlink_programmers[@]} > 0 )); then
      programmer_cli="$(printf '%s\n' "${stlink_programmers[@]}" | sort -V | tail -n 1)"
    fi
  fi
  if [[ ! -x "$programmer_cli" ]]; then
    echo 'STM32CubeProgrammer를 설치하거나 STM32_PROGRAMMER_CLI에 실행 파일 경로를 지정하세요.' >&2
    return 1
  fi
}

case "${1:-help}" in
  status|attach|auto|detach)
    find_usbipd
    case "$1" in
      status) "$usbipd_exe" list ;;
      attach) "$usbipd_exe" attach --wsl "${stlink_selector[@]}" ;;
      auto) "$usbipd_exe" attach --wsl "${stlink_selector[@]}" --auto-attach ;;
      detach) "$usbipd_exe" detach "${stlink_selector[@]}" ;;
    esac
    ;;
  check)
    find_programmer
    "$programmer_cli" -l stlink
    ;;
  help|-h|--help)
    echo '사용법: bash usb-wsl/stlink-usb.sh {status|attach|auto|check|detach}'
    echo '선택 환경 변수: USBIPD_EXE, STM32_PROGRAMMER_CLI, STLINK_BUSID'
    ;;
  *)
    echo "알 수 없는 명령: $1" >&2
    exit 2
    ;;
esac

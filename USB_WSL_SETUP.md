# NUCLEO-F411RE USB–WSL 연결 및 권한 설정

확인일: 2026-09-30. 이 문서는 현재 PC에서 확인한 설정과 명령을 기준으로 작성했다.

다른 사람에게 공유할 때는 [usb-wsl/README.md](usb-wsl/README.md)와 `usb-wsl` 폴더 전체 또는 `usb-wsl.tar.gz`를 전달한다. 공유용 README는 사용자명·일련번호를 고정하지 않는 설치 절차를 제공한다.

## 결론

**USB 공유와 Linux 접근 권한은 영구 설정이 가능하다. WSL 연결 자체는 재부팅 후 다시 수행하거나 자동 연결 프로세스를 시작해야 한다.**

| 단계 | 유지 여부 | 방법 |
| --- | --- | --- |
| Windows에서 USB 공유 | 재부팅 후에도 유지 | `usbipd bind`를 장치별로 한 번 실행 |
| WSL에서 일반 사용자 USB 접근 권한 | 규칙 파일을 설치하면 재연결·재부팅 후에도 적용 | ST-LINK용 udev 규칙 설치 |
| Windows USB를 WSL에 연결 | 연결 상태 자체는 영구 설정이 아님 | 작업 시작 시 `attach`, 또는 `--auto-attach` 실행 |
| USB 분리 후 재연결 | 자동 연결 프로세스가 살아 있는 동안 자동화 가능 | `--auto-attach` |
| Windows 로그인 때 자동 연결 시작 | 별도 작업 스케줄러 구성으로 자동화 가능 | 자동 연결 명령을 로그인 작업으로 등록. 이번 작업에서 설치·검증하지 않음 |

`--auto-attach`는 계속 실행되는 재연결 루프이다. Windows/WSL 종료까지 넘어가는 영구 연결을 만드는 옵션은 아니다. 재부팅 뒤에는 루프를 다시 시작해야 한다. 같은 USB 포트를 사용하는 것이 좋으며, 포트를 바꿔 자동 연결이 안 되면 명령을 다시 실행한다.

근거: [Microsoft USB–WSL 안내](https://learn.microsoft.com/en-us/windows/wsl/connect-usb), [usbipd-win WSL 안내](https://github.com/dorssel/usbipd-win/wiki/WSL-support), [자동 재연결 구현](https://github.com/dorssel/usbipd-win/blob/master/Usbipd/Wsl.cs).

## 현재 PC에서 확인한 상태

| 항목 | 확인값 |
| --- | --- |
| 보드 | NUCLEO-F411RE / STM32F411 |
| ST-LINK 일련번호 | `066EFF545589564867132511` |
| USB VID:PID | `0483:374b` (ST-LINK/V2.1) |
| 현재 Windows BUSID | `2-5` — 포트를 바꾸면 달라질 수 있음 |
| 현재 연결 상태 | `Attached` |
| usbipd-win | `5.3.0` |
| WSL 커널 | `6.18.33.2-microsoft-standard-WSL2` |
| systemd / udev | systemd 활성화, `systemd-udevd` 실행 중 |
| 사용자 | `ssafy1`, `plugdev` 그룹 가입 완료 |
| ST-LINK udev 규칙 | `/etc/udev/rules.d/99-stlink-wsl.rules` 설치 완료 |
| 현재 USB 권한 | 재연결 후 자동으로 `root:plugdev`, `0660` 적용됨 |

이전 오류의 직접 원인은 USB 노드가 `root:root`, `0664`여서 일반 사용자에게 쓰기 권한이 없었던 것이다. 임시 권한 수정 뒤 ST-LINK 검색, SWD 연결, 펌웨어 기록 및 GDB 실행이 성공했다.

사용자가 설치 스크립트를 실행한 뒤 영구 규칙 설치를 확인했다. 2026-09-30 11:13 KST에 USB를 WSL에 다시 연결했으며, 새 장치 `/dev/bus/usb/001/005`에 `root:plugdev`, `0660`이 자동 적용됐다. 일반 사용자 `ssafy1`로 `check`를 실행해 NUCLEO-F411RE 인식 성공을 확인했다. 자동 연결 루프와 Windows 로그인 작업은 설치하지 않았다.

보조 스크립트는 Bash 문법 검사, `status`, `attach`, `check` 실행을 통과했다. `auto`·`detach`의 옵션은 설치된 usbipd의 도움말과 대조했으며 실제 실행 시험은 수행하지 않았다.

## 1. Windows USB 공유 — 최초 한 번

현재 보드는 이미 공유·연결돼 있으므로 이 단계는 생략한다. 새 장치나 공유 설정을 해제한 장치에 필요하다.

**Windows 관리자 PowerShell**에서:

```powershell
usbipd list
usbipd bind --hardware-id 0483:374b
```

동일한 VID:PID의 보드가 여러 개면 목록에서 대상 BUSID를 골라 실행한다:

```powershell
usbipd bind --busid 2-5
```

이 공유 설정은 재부팅 후에도 유지된다. 이후 `attach`는 관리자 PowerShell이 필요하지 않다.

## 2. WSL USB 권한 — 최초 한 번, 영구 설정 (현재 완료)

**WSL 터미널**에서 다음 명령을 실행한다. 현재 디렉터리에 제공된 규칙 파일을 시스템 위치에 복사한다.

```bash
sudo install -m 0644 usb-wsl/99-stlink-wsl.rules /etc/udev/rules.d/99-stlink-wsl.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --action=add --subsystem-match=usb --attr-match=idVendor=0483 --attr-match=idProduct=374b
sudo udevadm settle
```

규칙 내용:

```udev
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="0483", ATTR{idProduct}=="374b", GROUP="plugdev", MODE="0660"
```

현재 계정은 이미 `plugdev` 그룹에 속한다. 다른 계정에서 사용한다면 `sudo usermod -aG plugdev 사용자명`을 실행하고 WSL 로그인 세션을 다시 시작한다.

이후 장치가 다시 생성될 때마다 udev가 권한을 적용하므로 `/dev/bus/usb/001/004`처럼 변하는 번호에 `chmod`를 반복할 필요가 없다. 규칙 적용 직후 접근이 안 되면 아래 연결 해제/재연결 명령으로 장치를 다시 생성한다.

## 3. 평소 사용 — WSL 터미널에서 한 줄

문서와 함께 제공한 스크립트는 Windows의 usbipd를 WSL에서 호출한다. WSL 창은 열어 둔다.

```bash
bash usb-wsl/stlink-usb.sh attach
```

USB를 뺐다 꽂을 때 자동으로 다시 연결하려면, 별도 터미널에서:

```bash
bash usb-wsl/stlink-usb.sh auto
```

자동 연결 명령은 터미널을 점유한다. 종료는 `Ctrl+C`이며, 종료 후에도 이미 연결된 장치는 연결 해제 명령을 실행하기 전까지 남을 수 있다.

상태 확인, ST-LINK 접근 확인, 연결 해제:

```bash
bash usb-wsl/stlink-usb.sh status
bash usb-wsl/stlink-usb.sh check
bash usb-wsl/stlink-usb.sh detach
```

스크립트를 사용하지 않는 경우의 직접 명령:

```bash
"/mnt/c/Program Files/usbipd-win/usbipd.exe" attach --wsl --hardware-id 0483:374b
```

이미 `Attached`라면 다시 붙일 필요 없이 `check`를 실행하면 된다. 동일한 VID:PID 장치가 여러 개면 스크립트 대신 직접 명령에 `--busid 대상번호`를 사용한다.

Windows 일반 PowerShell에서도 실행 가능:

```powershell
usbipd attach --wsl --hardware-id 0483:374b
# 재연결 루프를 실행할 때만 아래 명령 사용
usbipd attach --wsl --hardware-id 0483:374b --auto-attach
```

## 4. 성공 여부와 오류 구분

`status`의 해당 장치가 `Attached`이고, `check` 결과에 ST-LINK 일련번호와 `NUCLEO-F411RE`가 표시되면 USB 연결과 사용자 접근이 성공한 것이다. `check`는 장치 검색만 하며 펌웨어를 기록하거나 삭제하지 않는다. 실패 시 CLI가 종료 코드 0을 반환하는 경우도 있으므로 출력 내용을 확인한다.

| 출력/상태 | 조치 |
| --- | --- |
| `Not shared` | Windows 관리자 PowerShell에서 `bind` |
| `Shared` | WSL에서 `attach` |
| `Attached` + `errno=13` / `Permission denied` | udev 규칙과 `plugdev` 그룹 확인 |
| 장치 자체가 목록에 없음 | 데이터 USB 케이블, ST-LINK USB 포트, 보드 전원 확인 |
| `Device busy` | Windows에서 보드를 사용하는 CubeProgrammer/디버거를 종료 후 재시도 |
| USB 확인 성공 후 VS Code 디버그 타임아웃 | 디버그 서버 설정 확인. 기존 Generic 설정의 빈 서버 경로·포트는 별도 문제 |

WSL에 연결된 USB는 그동안 Windows 응용 프로그램에서 사용할 수 없다. Windows 도구로 돌아갈 때는 `detach`를 실행한다.

## 5. 권한 규칙 되돌리기

```bash
sudo rm /etc/udev/rules.d/99-stlink-wsl.rules
sudo udevadm control --reload-rules
```

이후 장치를 연결 해제하고 재연결하면 기본 권한으로 돌아간다. 이 작업은 보드 펌웨어를 지우지 않는다.

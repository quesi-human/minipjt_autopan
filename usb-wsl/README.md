# ST-LINK USB를 WSL에서 사용하기

이 폴더를 통째로 복사하면 다른 PC에서도 설정할 수 있습니다. NUCLEO-F411RE의 **ST-LINK/V2.1 (`0483:374b`)**를 대상으로 합니다. 다른 VID:PID의 보드는 이 권한 규칙의 대상이 아닙니다.

## 무엇이 유지되나요?

| 설정 | 재부팅·USB 재연결 후 |
| --- | --- |
| Windows USB 공유 (`bind`) | 유지됨. 장치별로 최초 한 번 설정 |
| WSL 일반 사용자 접근 권한 (udev 규칙) | 유지됨. 새 USB 장치 번호에도 자동 적용 |
| WSL USB 연결 (`attach`) | 다시 연결해야 함 |
| 자동 재연결 (`auto`) | 명령이 실행 중인 동안 동작. 재부팅 뒤 명령 재실행 필요 |

Windows 로그인 시 자동 실행까지 원한다면 별도로 작업 스케줄러를 구성해야 합니다. 이 폴더는 로그인 작업이나 자동 시작 프로세스를 설치하지 않습니다.

## 준비

- Windows와 WSL 2가 설치된 PC. Ubuntu에서 확인한 절차입니다.
- ST-LINK USB 포트에 연결한 보드와 데이터 전송 가능한 USB 케이블.
- Windows의 **usbipd-win 5.0 이상**.
- WSL의 실행 중인 udev 서비스. `systemctl is-active systemd-udevd`로 확인합니다.
- ST-LINK 검색을 위해 WSL용 STM32CubeProgrammer가 필요합니다. USB 연결 명령 자체에는 필요하지 않습니다.

Windows PowerShell에서 버전과 WSL을 확인합니다:

```powershell
wsl --list --verbose
usbipd --version
```

usbipd가 없다면 **Windows PowerShell**에서 설치합니다:

```powershell
winget install --interactive --exact dorssel.usbipd-win
```

설치 후 터미널을 다시 열고 WSL 창도 열어 둡니다.

## 최초 설정

### 1. Windows에서 장치 공유

**관리자 PowerShell**에서:

```powershell
usbipd list
usbipd bind --hardware-id 0483:374b
```

`0483:374b`인 장치가 여러 개라면 `usbipd list`에서 대상 BUSID를 골라 `usbipd bind --busid 대상번호`로 실행합니다. 이후 연결은 관리자 권한이 필요하지 않습니다.

### 2. WSL에서 USB 권한 설치

복사한 `usb-wsl` 폴더로 이동합니다. **WSL 일반 사용자 터미널**에서:

```bash
cd /복사한/경로/usb-wsl
sudo bash install-permissions.sh
```

이 명령은 다음을 수행합니다:

- `/etc/udev/rules.d/99-stlink-wsl.rules`에 권한 규칙 설치.
- 설치를 실행한 사용자를 `plugdev` 그룹에 추가 (이미 가입했다면 생략).
- udev 규칙을 다시 읽고 현재 연결된 ST-LINK에도 적용.

그룹에 새로 추가됐다는 메시지가 나왔다면 WSL 세션을 다시 로그인합니다. 현재 터미널만 즉시 갱신하려면 `newgrp plugdev`를 실행할 수 있습니다. 기존 VS Code 등의 프로세스는 다시 시작해야 새 그룹 권한을 받습니다.

udev 서비스가 실행되지 않는다면 먼저 이를 해결합니다. Ubuntu에서 systemd를 사용하려면 `/etc/wsl.conf`의 기존 설정을 보존하면서 아래 항목을 설정합니다:

```ini
[boot]
systemd=true
```

작업을 저장한 뒤 Windows PowerShell에서 `wsl --shutdown`을 실행하고 WSL을 다시 엽니다. 이 명령은 실행 중인 모든 WSL 배포판을 종료합니다. `systemctl is-active systemd-udevd`가 `active`인지 확인하고 설치를 다시 실행합니다. udev 자체가 없다면 WSL에서 `sudo apt install udev`로 설치합니다.

## 평소 사용

이하 명령은 **WSL의 `usb-wsl` 폴더 안**에서 실행합니다.

```bash
bash stlink-usb.sh status   # Windows 장치 목록과 연결 상태
bash stlink-usb.sh attach   # WSL에 연결
bash stlink-usb.sh check    # sudo 없이 ST-LINK 검색
```

`status`에 `Attached`가 보이고 `check`에 ST-LINK 일련번호와 보드 이름이 나오면 성공입니다. 이미 연결된 경우 `attach`는 생략합니다. `check`는 펌웨어를 기록하거나 삭제하지 않습니다. 도구가 오류에도 종료 코드 0을 반환할 수 있으므로 출력도 확인하세요.

작업 중 USB 재연결을 자동화하려면 별도 터미널에서:

```bash
bash stlink-usb.sh auto
```

이 명령은 계속 실행됩니다. 종료는 `Ctrl+C`입니다. USB 포트를 바꿔 자동 연결이 안 되면 명령을 다시 시작합니다. WSL 종료나 Windows 재부팅 뒤에도 다시 시작해야 합니다.

Windows 프로그램에서 보드를 사용할 때는 먼저 WSL에서 연결을 해제합니다:

```bash
bash stlink-usb.sh detach
```

같은 VID:PID의 장치가 여러 개일 때 `detach`는 해당 장치를 모두 해제합니다. 한 보드만 대상으로 하려면 **각 명령에 BUSID를 지정**하세요:

```bash
STLINK_BUSID=2-5 bash stlink-usb.sh attach
STLINK_BUSID=2-5 bash stlink-usb.sh auto
STLINK_BUSID=2-5 bash stlink-usb.sh detach
```

`2-5`는 예시입니다. 각 PC의 목록에서 확인한 값으로 바꿉니다. `check`는 연결된 모든 ST-LINK를 검색합니다.

## 도구 설치 경로가 다른 경우

스크립트는 사용자명과 STM32CubeProgrammer 버전을 고정하지 않습니다. CubeProgrammer는 `PATH`에서 찾고, 없으면 현재 사용자의 STM32Cube 번들 경로에서 가장 높은 버전을 선택합니다. 별도로 설치했다면 경로를 직접 지정합니다:

```bash
STM32_PROGRAMMER_CLI='/실제/설치/경로/STM32_Programmer_CLI' bash stlink-usb.sh check
```

usbipd는 `PATH`의 `usbipd.exe`와 기본 Windows 설치 경로를 확인합니다. 위치가 다르면:

```bash
USBIPD_EXE='/mnt/c/실제/설치/경로/usbipd.exe' bash stlink-usb.sh status
```

## 오류 구분

| 증상 | 확인할 사항 |
| --- | --- |
| 장치 목록에 보드가 없음 | ST-LINK USB 포트, 데이터 USB 케이블, 보드 전원 |
| `Not shared` | Windows 관리자 PowerShell에서 `bind` |
| `Shared` | WSL에서 `attach` |
| `Attached`인데 `Permission denied` / `errno=13` | 권한 규칙 설치, `id -nG`에 `plugdev` 포함 여부, 재로그인 |
| `No ST-Link detected` | WSL 연결 여부와 USB 권한 확인 |
| `Device busy` | Windows에서 사용하는 디버거·CubeProgrammer 종료 후 재시도 |
| `check` 성공 후 VS Code 디버그 타임아웃 | GDB 서버 경로·포트 등 디버그 설정을 별도로 확인 |

USB 연결 중에는 Windows 응용 프로그램에서 같은 보드를 사용할 수 없습니다. `/dev/bus/usb/001/004` 같은 장치 번호는 변하므로, 해당 번호에 수동 `chmod`를 반복하기보다 udev 규칙을 사용하세요.

## 되돌리기

권한 규칙을 제거하려면 WSL에서:

```bash
sudo rm /etc/udev/rules.d/99-stlink-wsl.rules
sudo udevadm control --reload-rules
```

그 후 USB를 연결 해제하고 다시 연결하면 기본 권한으로 돌아갑니다. 사용자의 `plugdev` 가입은 유지합니다.

Windows 공유 설정까지 해제하려면 연결 해제 후 **관리자 PowerShell**에서 `usbipd unbind --busid 대상번호`를 실행합니다. 보드 펌웨어에는 영향을 주지 않습니다.

## 검증 범위와 참고 자료

2026-09-30에 NUCLEO-F411RE, usbipd-win 5.3.0, Ubuntu-24.04 WSL 2에서 권한 규칙 설치 후 실제 재연결을 수행했습니다. 새 USB 장치에 `root:plugdev`, `0660` 권한이 자동 적용됐고 일반 사용자로 ST-LINK 검색에 성공했습니다. 자동 재연결 루프와 Windows 로그인 자동화는 실행 검증하지 않았습니다.

- [Microsoft: WSL에서 USB 장치 연결](https://learn.microsoft.com/en-us/windows/wsl/connect-usb)
- [usbipd-win: WSL 지원 및 공유 설정 유지](https://github.com/dorssel/usbipd-win/wiki/WSL-support)
- [usbipd-win: 자동 연결 구현](https://github.com/dorssel/usbipd-win/blob/master/Usbipd/Wsl.cs)

폴더의 세 파일(`stlink-usb.sh`, `install-permissions.sh`, `99-stlink-wsl.rules`)과 이 README를 함께 공유하세요.

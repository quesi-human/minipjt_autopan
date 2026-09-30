# minipjt_autopan

ESP32-CAM의 영상을 USB 시리얼로 WSL에 수신하고, PC에서 YOLO11n으로 사람을 탐지·추적합니다. 바운딩 박스 면적이 가장 큰 사람의 중심 x좌표를 HTTP API로 제공하며, 탐지 인원수를 100ms마다 STM32에 전달해 LED 4개로 표시합니다.

현재 구현은 영상 수신·사람 추적·중심 좌표 추출·LED 인원수 표시까지입니다. 팬 모터 또는 서보 제어는 아직 구현하지 않았습니다. 중심 좌표는 HTTP API에서 제공하며 STM32에는 현재 인원수를 전달합니다.

## 하드웨어와 데이터 흐름

- AI-Thinker ESP32-CAM + OV2640, CH340 USB-UART
- NUCLEO-F411RE, ST-LINK/V2.1 USB 가상 시리얼
- WSL 2 및 Windows 브라우저
- 외부 LED 4개와 각각 330Ω 저항

```text
ESP32-CAM → USB UART → WSL 카메라 서버 → YOLO11n/ByteTrack
                                             ├─ 브라우저 영상 :8765
                                             ├─ /status: 사람 수·박스·추적 ID·중심 x
                                             └─ 100ms 조회 → USB VCP → STM32 D4~D7 LED
```

YOLO는 PC에서 실행합니다. 카메라 연결에 Wi-Fi를 사용하지 않습니다. 원본 영상은 320×240이며 UART 영상 전송은 921600 baud, 부팅·업로드·STM32 통신은 115200 baud입니다.

## 프로젝트 구성

| 폴더 | 내용 |
| --- | --- |
| `esp32-usb-cam/UsbCamera/` | ESP32 카메라 펌웨어 |
| `esp32-usb-cam/` | 영상 수신, 브라우저 서버, YOLO·ByteTrack, 중심 좌표 선택 |
| `esp32-usb-cam/models/` | 실행에 사용하는 YOLO11n 사전 학습 가중치 |
| `test_1/` | STM32F411RE LED 제어 펌웨어 및 CMake 프로젝트 |
| `stm32-yolo-led/` | HTTP → STM32 전송과 보드 검증 스크립트 |
| `usb-wsl/` | ST-LINK 연결·권한 설정 도구 |

## 1. USB를 WSL에 연결

Windows 관리자 PowerShell에서 최초 한 번 공유 설정을 합니다.

```powershell
usbipd bind --hardware-id 1a86:7523
usbipd bind --hardware-id 0483:374b
```

WSL이 실행 중인 상태에서 일반 PowerShell:

```powershell
usbipd attach --wsl --hardware-id 1a86:7523
usbipd attach --wsl --hardware-id 0483:374b
```

WSL에서 시리얼 권한을 설정하고 재로그인하거나 그룹을 갱신합니다.

```bash
sudo usermod -aG dialout "$USER"
newgrp dialout
ls -l /dev/ttyUSB* /dev/ttyACM*
```

ST-LINK 프로그래머 권한은 [usb-wsl 안내](usb-wsl/README.md)와 [USB–WSL 설정 문서](USB_WSL_SETUP.md)를 참고합니다. `bind`와 그룹 권한은 유지되지만 재부팅·재연결 후 `attach`가 필요할 수 있습니다.

## 2. ESP32 펌웨어 업로드

Arduino IDE에 ESP32 보드 패키지를 설치하고 `esp32-usb-cam/UsbCamera/UsbCamera.ino`를 엽니다. 보드는 **AI Thinker ESP32-CAM**, 업로드 속도는 **115200**으로 선택합니다. Arduino-ESP32 3.3.12에서 빌드·업로드를 확인했습니다.

Windows IDE를 사용할 때는 CH340을 WSL에서 먼저 detach합니다. 자동 다운로드를 지원하지 않는 어댑터는 GPIO0–GND 연결 후 RESET으로 업로드하고, 실행 시 GPIO0–GND를 해제합니다. 기존 플래시 백업과 빌드 바이너리는 저장소에 포함하지 않습니다.

## 3. 영상·YOLO 실행

저장소 루트에서 Python 환경을 만듭니다.

```bash
python3 -m venv .venv
.venv/bin/pip install -r esp32-usb-cam/requirements-yolo.txt
.venv/bin/python esp32-usb-cam/web-preview.py --port /dev/ttyUSB0 --yolo
```

Windows 브라우저에서 **http://localhost:8765**를 엽니다. 기본 노출값은 수동 300입니다. 밝기에 따라 `--exposure 150` 등으로 조정하고, 자동 노출은 `--exposure 0`을 사용합니다. GPU 지원은 PyTorch/CUDA 설치 환경에 따라 달라지며, `--device cpu`로 CPU를 지정할 수 있습니다.

카메라만 확인하려면 `--yolo`를 생략합니다. 정상 실내 장면에서 약 5~6 FPS를 확인했습니다. 장면의 JPEG 크기와 UART 누락에 따라 달라집니다.

## 4. STM32 빌드·업로드와 LED 전송

Arm GNU Toolchain, CMake, Ninja, STM32CubeProgrammer를 설치하고 실행 파일을 PATH에 등록합니다.

```bash
cmake -S test_1 -B test_1/build/Debug -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build test_1/build/Debug
STM32_Programmer_CLI -c port=SWD mode=UR -w test_1/build/Debug/test_1.elf -v -rst
```

YOLO 서버를 실행한 채 다른 터미널에서:

```bash
.venv/bin/python stm32-yolo-led/bridge.py --port /dev/ttyACM0
```

각 핀 → 330Ω 저항 → LED 긴 다리(+), LED 짧은 다리(-) → GND로 연결합니다. 1명부터 D4→D5→D6→D7 순서로 켜지고, 4명 이상이면 모두 켜집니다. D4=PB5, D5=PB4, D6=PB10, D7=PA8입니다. 내장 LD2는 최근 유효한 데이터 수신 상태를 나타냅니다.

HTTP 조회와 STM32 전송은 100ms 주기이며 카메라 추론이 그보다 느리면 같은 결과를 반복 전달합니다. 카메라·추론 오류나 1초 이상 결과 정지 시 0명을 전송하고, STM32도 통신이 1초 이상 끊기면 LED를 끕니다. `bridge-status.json`에서 실제 조회 간격과 ACK 수를 확인합니다.

## 좌표 API

```bash
curl -s http://localhost:8765/status
```

`person_count`, `detections`, `closest_person_x`, `closest_person`, `frame_width`, `frame_height`를 제공합니다. 사람 박스는 `xyxy: [왼쪽 x, 위쪽 y, 오른쪽 x, 아래쪽 y]`입니다.

`closest_person_x = (왼쪽 x + 오른쪽 x) / 2`이며 원본 픽셀 좌표입니다. 현재 화면 중앙은 x=160입니다. 대상이 없으면 `closest_person_x`와 `closest_person`은 `null`입니다. `closest_person.track_id`는 신규 검출이 추적 궤적으로 확정되기 전에는 `null`일 수 있습니다.

단안 카메라에서 **박스 면적이 가장 큰 사람을 가장 가까운 사람으로 추정**합니다. 실제 거리 측정은 아니며 체격·자세·가림에 영향을 받습니다. 선택한 대상은 노란 박스와 중심 십자로 표시됩니다. 영상 원본은 `/raw.jpg`, 표시된 프레임은 `/snapshot.jpg`에서 확인할 수 있습니다.

## 검증

```bash
.venv/bin/python esp32-usb-cam/check-closest-person.py
.venv/bin/python esp32-usb-cam/check-live-center.py
# 실행 중인 STM32 브리지를 종료한 뒤 수행
.venv/bin/python stm32-yolo-led/check-board.py --port /dev/ttyACM0
```

실제 보드에서 18가지 인원수·표시 모드, 검사 바이트 오류 무시, 1초 통신 중단 소등을 검증했습니다. 사람 여러 명의 예제에서 최대 면적 선택·중점 계산·추적 ID 유지·대상 해제를 확인했고, 실제 카메라 HTTP 응답에서도 중심 x좌표를 확인했습니다. 이 시험은 탐지 정확도나 실제 거리의 정확도를 보증하는 시험은 아닙니다.

실행 중 카메라가 흰 화면이 되는 현상이 있었습니다. 노출값 조정만으로 복구되지 않는 경우도 있었고, 카메라 펌웨어 재기록 후 정상 영상으로 복구했습니다. `/raw.jpg`와 `/status`의 `camera_warning`으로 원본 상태를 확인합니다.

YOLO 가중치·Ultralytics 및 STM32 생성 코드의 출처는 [THIRD_PARTY.md](THIRD_PARTY.md)에 기록합니다.

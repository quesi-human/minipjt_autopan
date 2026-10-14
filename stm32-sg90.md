# F411RE · YOLO 사람 좌우 추적

ESP32-CAM의 영상을 F411RE가 USB-UART로 PC에 중계합니다.
PC의 기존 YOLO11m/ByteTrack이 사람을 탐지하고, 화면 중심과 대상 중심의
차이를 서보 각도 명령으로 변환합니다. F411RE는 그 명령을 받아 D3에서
SG90 한 개를 제어합니다. 카메라를 서보의 회전부에 장착해야 합니다.
현재는 좌우 한 축이며 일반 각도 제어형 SG90용입니다.

## 배선

| F411RE 핀 | 연결 |
| --- | --- |
| **D3 / PB3 (CN9 4번)** | SG90 주황색 신호선 |
| 5V | SG90 빨간색 전원선 |
| GND | SG90 갈색선 및 ESP32 GND |
| D8 / PA9 TX (CN5 1번) | ESP32-CAM U0R / GPIO3 RX |
| D2 / PA10 RX (CN9 3번) | ESP32-CAM U0T / GPIO1 TX |
| 5V | ESP32-CAM 5V |

서보 신호선을 D2에서 D3로 옮기고, D2에는 카메라 TX만 연결합니다.
ESP32-CAM 펌웨어는 기존 `esp32-usb-cam/UsbCamera/UsbCamera.ino`를 사용합니다.
보드의 CN2 점퍼 두 개가 모두 꽂혀 있어야 합니다.
서보와 카메라를 함께 구동할 때 보드 리셋/떨림이 발생하면 전원을 끊고
전원 공급을 점검하세요. 실제 공급 여유는 이번 검증에 포함되지 않습니다.

## 실행

저장소 루트에서:

```bash
bash esp32-usb-cam/preview.sh --pan --baud 460800 --gap-us 500
```

브라우저: http://localhost:8766
서보가 대상을 반대 방향으로 따라가면 `--pan-reverse`를 추가합니다.
`--pan`은 YOLO 사람 탐지도 활성화합니다. `--pan`을 생략하면 카메라 미리보기만
실행되고, 서보는 통신 명령이 없으면 현재 각도를 유지합니다.
카메라 수신 실패 시 서버가 자동으로 재연결합니다. 카메라와 중계 보드의
속도가 어긋나면 B115200 및 STM32 전용 R 명령으로 부팅 속도를 복구합니다.
서버를 정상 종료할 때도 115200bps 복구를 시도합니다.

최초 선택은 화면에서 가장 큰 사람 박스입니다. 추적 ID가 있는 동안 같은 사람을
유지하며, 대상이 사라지면 정지하고 0.5초 뒤 다시 선택합니다.
화면 중심 부근 ±8%에서는 각도를 유지하고, 그 밖에서는 조금씩 조절합니다.
범위는 nominal 60~120도이며 실제 각도는 서보마다 다를 수 있습니다.
상태 API `/status`에는 `pan`, `pan_commands_sent`, 카메라 및 YOLO 상태가 표시됩니다.
PC의 각도는 보낸 목표값이며 서보 위치 센서로 측정한 값은 아닙니다.

## 구현

- `stm32.c`: HSI PLL 96MHz, USART1 카메라 중계, USART2 ST-LINK VCP,
  D3 / PB3 / AF1 / TIM2_CH2의 50Hz PWM.
- `esp32-usb-cam/pan_tracker.py`: 중심 오차 제어, 추적 ID 유지, 각도 제한.
- `esp32-usb-cam/web-preview.py`: 카메라 요청과 서보 명령을 같은 시리얼 포트에서 전송.
- `stm32-sg90/servo_command.h`: `P90\n` 각도, `S\n` 정지, `R\n` 링크 복구 명령 처리.

서보 명령은 STM32에서 소비하며 ESP32로 전달하지 않습니다.
JPEG 스트림에 별도 응답을 섞지 않습니다.
목표가 사라지거나 추론 결과가 0.4초 이상 오래되면 PC가 정지 명령을 보냅니다.
펌웨어는 마지막 유효 서보 명령 이후 0.5초가 지나면 현재 각도에서 정지합니다.
펌웨어의 최대 각도 변경 속도는 20ms당 1도입니다.

## 빌드·업로드

Arm GNU Toolchain과 CMake를 PATH에 등록합니다.

```bash
cmake -S . -B build/sg90-f411 -DCMAKE_BUILD_TYPE=Release
cmake --build build/sg90-f411
STM32_Programmer_CLI -c port=SWD mode=UR -w build/sg90-f411/stm32_sg90.elf -v -rst
```

새 PC에서는 Python 가상환경을 만들고 `esp32-usb-cam/requirements-yolo.txt`를 설치합니다.
현재 PC의 `.venv`는 설치된 Physical AI 환경의 YOLO/PyTorch 패키지를 `.pth`로
참조하고 pyserial/lap만 로컬 설치했습니다. 이 `.venv`는 다른 PC에 복사하지 않습니다.
기존 `test_1`의 F103 카메라 중계 구현은 별도로 유지됩니다.

## 검증

2026-10-14:

- F411RE용 ARM 빌드와 Flash 기록/읽기 검증 성공.
- 실제 보드에서 PB3 AF1, TIM2_CH2, PSC=95, ARR=19999 확인 (50Hz 설정).
- USB로 `P100\n` 5회 전송 후 `servo_commands=5`, 현재/목표 각도=100,
  CCR2=1556 확인. 모터의 물리적 회전이나 핀 파형은 직접 측정하지 않았습니다.
- 추적 제어/명령 분리 테스트 5개, 기존 카메라 파서 테스트 8개 통과.
- GPU YOLO11m 모델 준비 성공 (RTX 5060 Ti).
- Ultralytics bus.jpg의 실제 탐지에서 P90→P78 명령 10개를 생성해 보드로 전송.
  `servo_commands` 5→15, 현재/목표=78, CCR2=1433 확인.
  빈 이미지에서 S 정지 명령을 보내 `servo_stops` 1→2 확인.
  이 검증은 예제 이미지로 수행했으며 실시간 카메라 추적 검증과 구분됩니다.
- 초기 카메라 연결 실패 원인은 TX/RX 반대 배선이었습니다.
  U0T→D2, U0R→D8로 수정한 후 실제 영상 수신 성공.
- 실제 카메라: 320×240, 921600bps, 598프레임 시점 약 17.9 FPS,
  누락 0, YOLO 추론 570프레임 및 실제 사람 탐지 확인.
- 실제 영상에서 생성한 서보 명령 수신 확인: servo_commands=25
  (앞선 예제 시험 포함), 각도=88, CCR2=1489. 대상이 없는 영상에서는
  S 정지 명령 전송/수신 확인.
- 카메라 정상 프레임 597개 시점에 invalid_frames, uart_errors,
  pc_uart_errors, relay_overflows 모두 0. CFSR/HFSR도 0.
- 영상 1381프레임 이후 카메라가 115200bps로 응답하고 F411이
  921600bps에 남아 있는 상태를 확인했습니다. 속도를 맞춰 복구하고
  수신 스레드 자동 재시도 및 링크 복구 기능을 추가했습니다.
- 추적/명령 테스트 5개와 재연결 순서 테스트 1개 통과. 수정 펌웨어 기록 검증 성공.
- 서버를 http://localhost:8766 에서 실행 상태로 유지했습니다.
  실제 회전 방향과 대상이 중앙에 유지되는지는 서보 장착 상태에서 확인해야 합니다.


기존 Flash 전체 백업: `backups/sg90-f411/before-sg90-20261014.bin` (512KB).

참고:
[NUCLEO 보드 설명서](https://www.st.com/resource/en/user_manual/um1724-.pdf),
[RM0383](https://www.st.com/resource/en/reference_manual/dm00119316.pdf).

2026-10-14 추가 진단: 영상 중단은 반복됐습니다. 서보 PWM을 60초 중지한
상태에서도 중단이 있었으며, 460800bps/500us에서도 재현됐습니다.
직접 정보 명령 I를 보냈을 때 ESP32가 115200bps에서 `CAM_ERROR not_ready`로
응답했습니다. 현재는 ESP32 펌웨어의 cameraReady가 false인 상태로, 카메라
센서 초기화/전원/리본 케이블 상태 확인이 필요합니다. 정확한 초기화 오류 코드는
부팅 로그를 추가 수집해야 합니다. 서버는 CAM_ERROR를 표시하고 재연결을 시도합니다.

서보의 빨간 전원선을 분리하고 ESP32-CAM 전원을 재공급한 뒤 영상이 복구됐습니다.
460800bps/500us 조건에서 60초 관찰 중 frames=268→899, dropped=0, error=null,
camera_reconnects=10 유지(추가 재연결 0), 약 10~11 FPS를 확인했습니다.
실제 사람 탐지와 각도 명령 생성도 확인했습니다. 서보는 전원 분리 상태라
물리적으로 움직이지 않습니다. 전원 분리와 카메라 재부팅을 함께 수행했으므로
전원 부족을 단독 원인으로 확정한 결과는 아닙니다.

서보 전원 재연결 후 90→85→95→90도 명령을 전송해 출력 경로를 시험하고
YOLO 추적을 재시작했습니다. 중앙 상태에서 angle/target=90, CCR2=1500,
TIM2_CCER=0x10을 확인했습니다. 실제 사람 1~2명 탐지에 따라 좌우 각도
명령이 바뀌었으며, 추적 중 angle/target=112 및 CCR2=1622를 확인했습니다.
모터와 카메라의 실제 물리적 이동 및 장착 방향은 현장에서 확인해야 합니다.
현재 시험 서버는 `--pan --baud 460800 --gap-us 500`으로 실행 중입니다.

전원 재연결 후 추적 활성 상태에서 60초 관찰: frames=481→1089, dropped=0,
error=null, camera_reconnects=0 유지, 약 6~8 FPS. 실제 탐지 결과에 따라
목표 각도가 116.6→65.6도로 바뀌는 것을 확인했습니다. 전체 자동 테스트 32개 통과.

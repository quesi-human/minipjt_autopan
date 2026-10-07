# NUCLEO-F103RB 카메라 UART 중계

현재 사용하는 보드는 STM32F103RB입니다. HSI PLL 64MHz, Flash 128KB, RAM 20KB를 사용합니다.
USART2(ST-LINK VCP)와 USART1(ESP32-CAM)을 양방향 중계합니다.
부팅 속도는 115200bps이며 ESP32의 `BAUD` 응답을 PC에 전달한 뒤 양쪽 UART 속도를 함께 변경합니다.
115200·460800·921600bps에서 실제 카메라 수신을 확인했습니다.

| STM32 | ESP32-CAM |
| --- | --- |
| CN5 D8 / PA9 TX | U0R / GPIO3 RX |
| CN9 D2 / PA10 RX | U0T / GPIO1 TX |
| 5V | 5V |
| GND | GND |

CAM-MB를 제거한 상태의 현재 배선입니다. STM32 USB로 PC에 연결합니다.
LD2(PA5)는 CRC32와 JPEG 시작·끝 표식이 맞는 카메라 프레임을 수신하면 켜지고,
마지막 정상 프레임 이후 2초가 지나면 꺼집니다. 부팅 로그와 깨진 프레임은 제외합니다.
1KB 큐 두 개로 중계하며 JPEG 전체를 RAM에 저장하지 않습니다.

## 빌드

Arm GNU Toolchain, CMake, Ninja를 PATH에 등록한 뒤:

```bash
cmake -S test_1 -B test_1/build/Release -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build test_1/build/Release
STM32_Programmer_CLI -c port=SWD mode=UR -w test_1/build/Release/test_1.elf -v -rst
```

STM32만 리셋하면 ESP32는 고속 상태로 남을 수 있습니다. 업로드 후 두 보드를 재부팅해
115200bps에서 시작하거나 기존 속도를 맞춥니다. ST-LINK RTS는 ESP32를 리셋하지 않습니다.

## 진단과 시험

SWD 변수: `valid_frames`, `invalid_frames`, `received_bytes`, `uart_errors`,
`pc_uart_errors`, `relay_overflows`, `last_valid_frame_ms`, `esp_link_active`.
주소는 빌드에 따라 달라지므로 ELF 심볼을 확인합니다.

```bash
python3 -m unittest discover -s tests -p test_camera_link.py -v
```

실제 시험에서 정상 JPEG 3장, LD2 켜짐과 수신 중단 후 꺼짐을 확인했습니다.
921600bps 중계에서도 UART 오류·잘못된 프레임·버퍼 넘침 0을 확인했습니다.
전원 공급 여유와 장시간 안정성을 측정한 결과는 아닙니다.

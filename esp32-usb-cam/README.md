# ESP32 촬영 및 PC 탐지

현재 데이터 경로는 ESP32-CAM ↔ STM32F103RB ↔ PC입니다.
배선과 중계 펌웨어는 [STM32 안내](../test_1/README.md), 설치 및 기본 실행은 [루트 README](../README.md)를 참고하세요.

| 파일 | 역할 |
| --- | --- |
| `UsbCamera/UsbCamera.ino` | AI-Thinker ESP32-CAM/OV2640 JPEG 촬영 |
| `capture.py` | 요청·CRC/JPEG 검증·파일 저장·OpenCV 표시 |
| `web-preview.py` | 브라우저 영상, 상태 API, 선택적 YOLO 실행 |
| `person_detector.py` | YOLO 사람 탐지·ByteTrack·영상 표시 |
| `lanyard_classifier.py` | 목걸이 줄 색으로 학생·직원 추정 |
| `closest_person.py` | 최대 면적 사람 박스와 중심 선택 |
| `check-closest-person.py` | 모델 예제로 박스·추적·중심 확인 |
| `check-live-center.py` | 실행 중인 서버 결과 검증 |
| `preview.sh` | Python 환경을 선택해 YOLO 브라우저 서버 실행 |

## ESP32 펌웨어

AI Thinker ESP32-CAM 보드 설정으로 `UsbCamera/UsbCamera.ino`를 빌드·업로드합니다.
Arduino-ESP32 2.0.17에서 실제 빌드와 115200bps 업로드·검증을 완료했습니다.
현재 펌웨어는 320×240 JPEG, 품질 20, Wi-Fi 비활성, 플래시 LED 꺼짐입니다.
업로드 때는 CAM-MB/USB-UART를 사용하고, 실행 배선으로 돌아갈 때는 전원을 끕니다.

PC가 `F`를 보내면 `ECAM` + 길이(u32) + CRC32(u32) + 순번(u32) +
너비(u16) + 높이(u16)의 20바이트 little-endian 헤더와 JPEG를 반환합니다.

| 명령 | 역할 |
| --- | --- |
| `I` | 카메라 설정 상태 반환 |
| `E150` + 줄바꿈 | 수동 노출 150 (자동 노출·게인 해제) |
| `E0` + 줄바꿈 | 자동 노출 |
| `T256,250` + 줄바꿈 | 256바이트 청크, 250µs 대기 |
| `B921600` + 줄바꿈 | 응답 후 UART 속도 변경 |

부팅은 115200bps입니다. STM32 중계도 `BAUD` 응답 이후 양쪽 UART 속도를 맞춥니다.
서버만 재시작할 때는 `--initial-baud 921600`을 사용합니다.

## 실행과 확인

```bash
.venv/bin/python esp32-usb-cam/web-preview.py --yolo
# 이미 고속 운용 중인 장치를 재사용할 때
.venv/bin/python esp32-usb-cam/web-preview.py --yolo --initial-baud 921600
# 브라우저 없이 사진 3장 저장
.venv/bin/python esp32-usb-cam/capture.py --frames 3
# 모델 예제 검사
.venv/bin/python esp32-usb-cam/check-closest-person.py
# 실제 서버 API 검사
.venv/bin/python esp32-usb-cam/check-live-center.py --url http://127.0.0.1:8766/status
```

사진 수신기는 기본 `/dev/ttyACM0`입니다. CAM-MB 직결 시험은 `--port /dev/ttyUSB0`으로 지정합니다.
사진 검사와 영상 서버는 같은 직렬 포트를 동시에 열지 않습니다.
`CAMERA_PYTHON=/실제/환경/bin/python bash esp32-usb-cam/preview.sh --initial-baud 921600`으로
기존 Python 환경을 사용할 수 있습니다.

## 분류와 검증 범위

하늘색 줄 → 학생, 검정색 줄 → 직원, 불확실 → 미확인입니다.
사람 높이 100픽셀 미만이나 잘린 박스, 두 줄 색이 동시에 검출되는 경우는 미확인입니다.
색상·형태 규칙이므로 옷의 무늬나 그림자와 혼동할 수 있습니다.
목걸이 전용 학습과 실제 목걸이 정답을 이용한 정확도 평가는 아직 수행하지 않았습니다.

7개 합성 색상 시험과 8개 카메라 프레임 시험이 통과했습니다.
실제 중계에서 JPEG 3장과 LD2 수신/소등을 확인했습니다.
같은 장면 25장씩 시험한 115200/460800/921600bps 속도는 2.42/6.57/9.23 FPS입니다.
청크/대기를 256/250으로 조정한 카메라 전용 영상은 약 20 FPS였습니다.
수동 노출 150에서 평균 휘도 43 → 138/255로 조절했고 약 16 FPS를 확인했습니다.
YOLO11m GPU 실행은 160프레임 시점 약 17.4 FPS, 추론 21.9ms, 누락·오류 0이었습니다.
FPS는 장면의 JPEG 크기와 PC 부하에 따라 달라집니다.

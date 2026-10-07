# minipjt_autopan — Raspberry Pi 5

Raspberry Pi 5의 **CAM/DISP 0**에 연결한 Pi Camera에서 영상을 받아, Pi CPU에서 **YOLO11n으로 사람만 탐지**합니다. 같은 프레임에서 가장 큰 사람 바운딩 박스를 선택하고 중심 `(x, y)`를 Pi 내부 Python 호출, HTTP JSON API, 선택적 JSON Lines 출력으로 제공합니다.

현재 범위는 카메라 입력·사람 탐지·최대 박스 선택·중심 좌표 반환·브라우저 표시입니다. GPIO 핀 배정과 LED·모터·서보 출력은 다음 지시까지 보류합니다. Raspberry Pi 실행에는 ESP32, STM32, WSL, 시리얼 브리지가 필요하지 않습니다. 현재 STM32–ESP32 구현은 [루트 README](../README.md)를 참고합니다.

```text
Pi Camera → CAM/DISP 0 → Picamera2 BGR 프레임 → YOLO11n (CPU)
                                               ├─ 가장 큰 사람 박스 → 중심 (x, y)
                                               ├─ Python PersonService.read()
                                               └─ HTTP /center · /status · 영상
```

## 카메라 연결

Pi 전원을 끈 상태에서 Pi 5용 케이블로 **CAM/DISP 0**에 카메라 한 개를 연결합니다. 케이블 방향은 사용하는 카메라의 공식 안내를 따릅니다. 전원을 켠 뒤 확인합니다.

```bash
rpicam-hello --list-cameras
rpicam-hello -t 5000
```

기본 프로그램은 **Picamera2 인덱스 0**을 엽니다. 카메라 한 개가 CAM/DISP 0에서 인식되면 인덱스 0으로 실행합니다. 소프트웨어 카메라 인덱스는 물리 포트 번호 자체가 아닙니다. 이후 두 번째 카메라를 추가하면 `--list-cameras`의 `Id`/`Num`과 `rpicam-hello --list-cameras`를 확인하고 `--camera-num`을 지정해야 합니다. 카메라 모델이 아직 정해지지 않았으므로 센서별 `dtoverlay`는 자동으로 수정하지 않습니다.

## 설치

대상은 **Raspberry Pi OS 64비트**입니다. 저장소 루트에서 실행합니다. Picamera2와 libcamera는 OS와 맞는 apt 패키지를 사용하고, 가상환경에서 시스템 패키지를 볼 수 있도록 합니다.

```bash
sudo apt update
sudo apt install -y python3-venv python3-picamera2 python3-opencv
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r raspberry_pi/requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m raspberry_pi --list-cameras
```

모델은 저장소의 `models/yolo11n.pt`를 사용합니다. 기존 PC의 `.venv`, `vendor`, 실행 바이너리를 복사하지 말고 Pi에서 새로 설치합니다. Ultralytics 및 전이 의존성은 아직 Pi에서 설치 검증한 잠금 파일로 고정하지 않았습니다. 실행 PC의 패키지 조합은 아래 검증 범위와 구분합니다.

## 실행

```bash
.venv/bin/python -m raspberry_pi
```

기본값은 카메라 인덱스 0, 영상 640×480, 카메라 요청 30 FPS, 추론 입력 320, 신뢰도 0.35, CPU 추론입니다. 카메라 FPS는 탐지 FPS가 아닙니다. 추론 입력 크기가 달라도 반환 좌표는 **실제 수신 영상 크기** 기준입니다. 브라우저 주소는 Pi에서 `http://127.0.0.1:8765`입니다.

다른 컴퓨터의 브라우저에서 Pi 영상을 보려면:

```bash
.venv/bin/python -m raspberry_pi --host 0.0.0.0
# 브라우저: http://라즈베리파이의-IP:8765
```

해상도와 추론 설정은 바꿀 수 있습니다.

```bash
.venv/bin/python -m raspberry_pi --camera-num 0 --width 640 --height 480 --imgsz 640 --confidence 0.4
.venv/bin/python -m raspberry_pi --json
```

`--json`은 완료된 탐지 프레임마다 결과를 표준 출력에 한 줄 JSON으로 내보냅니다. 카메라나 추론 오류·정지 상태는 HTTP 또는 Python `read()`로 확인합니다. 종료는 Ctrl+C이며 SIGTERM도 처리합니다. 센서 읽기가 멈추면 결과는 기본 3초 후 오래된 것으로 표시되어 중심이 `null`이 됩니다. 정상 프레임 처리 시간이 3초를 넘는 환경에서는 성능을 조정하거나 `--stale-seconds`를 지정합니다.

## Pi에서 중심 좌표 받기

Pi 내부 제어 프로그램은 다음 API를 조회하면 됩니다.

```bash
curl -s http://127.0.0.1:8765/center
curl -s http://127.0.0.1:8765/status
```

`/center` 응답 예시 (실제 탐지 결과는 장면에 따라 다름):

```json
{
  "center": {"x": 320.0, "y": 240.0},
  "target": {
    "class_id": 0,
    "class": "person",
    "confidence": 0.9,
    "xyxy": [220.0, 100.0, 420.0, 380.0],
    "bbox_area": 56000.0,
    "center_x": 320.0,
    "center_y": 240.0,
    "center_x_normalized": 0.5,
    "center_y_normalized": 0.5
  },
  "person_count": 2,
  "frame_width": 640,
  "frame_height": 480,
  "inference_frames": 10,
  "updated_at": 1790812800.0,
  "result_age_ms": 25.0,
  "stale": false,
  "error": null
}
```

- 원점: 영상 왼쪽 위. x는 오른쪽, y는 아래쪽으로 증가합니다.
- 선택: 사람 클래스만 대상으로 `(x2-x1) × (y2-y1)`이 최대인 유효 박스. 영상 밖 부분은 경계로 보정하며 동률이면 먼저 나온 박스를 선택합니다.
- 중심: `x=(x1+x2)/2`, `y=(y1+y2)/2`. 소수점 좌표를 유지합니다.
- 사람이 없으면 `center`와 `target`은 `null`, `person_count`는 0입니다.
- 준비 중·오류·종료·결과 정지 시에도 중심은 `null`입니다. `stale`, `error`, `result_age_ms`를 함께 확인합니다.
- 박스 크기는 거리 측정값이 아닙니다. 이번 Pi 구현은 매 프레임 최대 박스를 선택하며 추적 ID를 사용하지 않습니다.

`/status`에는 모든 사람 박스와 성능·카메라 정보도 포함됩니다. 기존 중심 x 필드에 대응하는 `closest_person_x`, `closest_person_y`, `closest_person`도 제공합니다. `/snapshot.jpg`는 표시 프레임, `/stream`은 MJPEG 영상입니다. 최신 유효 영상이 없으면 snapshot은 HTTP 503을 반환합니다.

같은 Python 프로세스에서 결과를 반환받는 예시:

```python
import time
from raspberry_pi.camera import PiCamera
from raspberry_pi.service import PersonService
from raspberry_pi.vision import PersonDetector

service = PersonService(lambda: PiCamera(camera_num=0), lambda: PersonDetector())
try:
    service.start()
    while True:
        result = service.read()
        center = result["center"]  # {"x": ..., "y": ...} 또는 None
        if result["error"]:
            raise RuntimeError(result["error"])
        if center is not None:
            print(center["x"], center["y"])
        time.sleep(0.1)
finally:
    service.close()
```

카메라는 한 프로세스만 엽니다. 서버 실행 중 별도의 제어 프로세스는 새 `PiCamera`를 만들지 말고 HTTP로 조회합니다. 핀 제어는 이 반환 좌표를 소비하는 후속 단계입니다.

## 구성과 검증

| 경로 | 용도 |
| --- | --- |
| `raspberry_pi/camera.py` | Picamera2 카메라 입력 |
| `raspberry_pi/vision.py` | YOLO11n 사람 탐지, 최대 박스와 중심 선택 |
| `raspberry_pi/service.py` | 작업 스레드, 최신 결과 반환, 오류·오래된 결과 무효화 |
| `raspberry_pi/web.py` | 좌표 API와 브라우저 표시 |
| `models/yolo11n.pt` | 공용 사전 학습 모델 |
| `tests/` | 카메라 대체 장치와 결과·API 계약 시험 |

```bash
python3 -m unittest discover -s tests -v
.venv/bin/python -m raspberry_pi.check_image
```

첫 검사는 실제 보드와 추가 라이브러리 없이 카메라 설정·선택·중심 계산·결과 무효화·서비스 자원 정리·HTTP 응답을 검사합니다. 두 번째는 설치된 Ultralytics 예제 이미지로 실제 YOLO11n 추론과 빈 화면 대상 해제를 검사합니다. 자동 검사 11개와 x86 환경의 실제 모델·서비스 경로 검사가 통과했습니다. [검증 기록](VALIDATION.md)을 참고하세요. **Pi 5 실물 카메라·ARM 의존성 설치·처리 FPS는 아직 실행 검증하지 않았습니다.** Pi에서 카메라 목록·실시간 API·다수 인원 선택·대상 소실·카메라 정지 후 무효화를 추가 확인해야 합니다.

참고: [Picamera2 공식 문서](https://github.com/raspberrypi/picamera2), [Picamera2 매뉴얼](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf), [Ultralytics Raspberry Pi 안내](https://docs.ultralytics.com/guides/raspberry-pi/), [타사 구성 요소](../THIRD_PARTY.md).

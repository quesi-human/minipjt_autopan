# Raspberry Pi 전환 검증 기록

2026-10-01. Pi 구현에 대해 아래 검사를 수행했다. Raspberry Pi 장치 연결이나 배포는 수행하지 않았다.

## 통과한 검사

- `python3 -m unittest discover -s tests -v`: 11개 통과. 사람 클래스 필터, 최대 면적 선택, 소수점 중심, 경계 보정, 빈 결과, 카메라 인덱스 0과 RGB888 설정, 시작 실패 자원 정리, 결과 만료 및 오류 무효화, 카메라 해제, 실제 HTTP 핸들러의 JSON/snapshot 응답을 검사했다. HTTP 검사는 핸들러를 직접 호출했고 네트워크 소켓은 열지 않았다.
- `python3 -m raspberry_pi --help`: 추가 라이브러리가 없어도 실행 안내를 표시했다.
- `python3 -m raspberry_pi --list-cameras`: 현재 x86 검사 환경의 Picamera2 미설치를 안내하고 종료했다. Pi 카메라 인식을 확인한 결과는 아니다.
- 기존 x86 Python 환경에서 `python -m raspberry_pi.check_image`: 실제 저장소 YOLO11n 모델과 Ultralytics bus 예제로 추론했다. 640×480 프레임에서 4명, 선택 중심 `(110.90748596191406, 289.0377197265625)`를 반환했다. 최대 면적·중점 계산과 빈 화면에서 대상 해제를 확인했다.
- 추가 서비스 통합 검사: Picamera2를 이미지 배열 입력원으로 대체하고 실제 `PersonDetector` → `PersonService` → JPEG 인코딩 경로를 실행했다. 같은 중심이 반환됐고 JPEG 해상도는 640×480이었다. 다음 빈 프레임에서 `center=null`, `person_count=0`으로 갱신됐으며 종료 시 카메라 자원과 결과가 정리됐다.
- 모델 이동 전후 바이트 일치 확인. SHA256: `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
- 새 Python 파일 문법 및 `git diff --check` 통과.

실제 추론에 사용한 기존 환경: Python 3.12, Ultralytics 8.4.153, torch 2.11.0, NumPy 2.5.3, OpenCV 4.13.0.92. Pi에서 새로 설치된 조합을 검증한 것은 아니다. CUDA/NVML 경고가 있었으나 모델 호출은 `device="cpu"`로 수행됐고 검사는 통과했다.

## Pi에서 남은 확인

1. Raspberry Pi OS 64비트의 apt Picamera2/libcamera와 가상환경 의존성 설치 및 `pip check`.
2. CAM/DISP 0에 연결한 카메라 한 개가 `rpicam-hello --list-cameras`와 프로그램 `--list-cameras`에서 인식되는지 확인.
3. 실제 영상 색상, 해상도, 다수 사람의 최대 박스와 중심, 빈 장면 반환 확인.
4. `/center`, `/status`, `/snapshot.jpg`, `/stream` 실제 네트워크 동작 및 처리 시간 확인.
5. 카메라 오류·프레임 정지 시 좌표 무효화와 Ctrl+C/SIGTERM 종료 후 카메라 재실행 확인.

GPIO, LED, 팬, 서보와 모터 제어는 사용자 요청에 따라 미구현이다.

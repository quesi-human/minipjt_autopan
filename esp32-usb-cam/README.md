# ESP32 USB 카메라와 YOLO

설치·업로드·실행은 [루트 README](../README.md)를 참고합니다. ESP32에는 `UsbCamera/UsbCamera.ino`를 업로드하고, PC에서 `web-preview.py --yolo`를 실행합니다.

- `capture.py`: UART JPEG 수신, CRC·JPEG·해상도 검증 및 저장·미리보기
- `web-preview.py`: 브라우저 MJPEG 영상, `/status`, `/raw.jpg`, `/snapshot.jpg`
- `person_detector.py`: YOLO11n 사람 클래스 탐지와 ByteTrack 추적
- `closest_person.py`: 최대 면적 박스 선택과 중점 x좌표 계산
- `check-closest-person.py`: 예제 이미지의 추적·중점 검증
- `check-live-center.py`: 실행 중인 서버의 실시간 좌표 응답 검증

프레임 프로토콜은 PC가 `F`를 보내면 보드가 `ECAM` + JPEG 길이(u32) + CRC32(u32) + 순번(u32) + 너비(u16) + 높이(u16)와 JPEG를 보내는 방식입니다. 정수는 little endian이며 헤더는 20바이트입니다.

부팅 baud는 115200입니다. `E300\n`은 수동 노출 300, `E0\n`은 자동 노출, `T64,1000\n`은 64바이트 전송 묶음과 1000μs 간격, `B921600\n`은 영상 전송 baud 변경입니다. 수신기는 응답 확인 후 같은 baud로 전환합니다. `I`는 카메라 설정 상태를 응답합니다.

원본 해상도는 320×240입니다. 가장 가까운 대상은 단안 영상의 박스 면적으로 추정하며 실제 거리 측정을 하지 않습니다. 중점 좌표는 원본 기준이고, 같은 프레임의 박스·사람 수·좌표가 함께 갱신됩니다.

원본 플래시 백업, 개인 촬영 영상, 설치 라이브러리, 빌드 결과물은 Git에 포함하지 않습니다. 검증 스크립트 실행 결과는 로컬 `captures/`에 저장됩니다.

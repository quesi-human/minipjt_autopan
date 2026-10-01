"""Run with python -m raspberry_pi from the repository root."""
import argparse
import json
from pathlib import Path
import signal
import sys

from .camera import PiCamera, camera_info
from .service import PersonService
from .vision import DEFAULT_MODEL, PersonDetector
from .web import make_server


def main():
    parser = argparse.ArgumentParser(description="Pi 5 CSI camera → YOLO11n → largest person centre (x, y)")
    parser.add_argument("--camera-num", type=int, default=0, help="Picamera2 카메라 인덱스 (기본 0)")
    parser.add_argument("--list-cameras", action="store_true")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=float, default=30, help="카메라 요청 FPS; 추론 FPS와 별개")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--stale-seconds", type=float, default=3)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8765)
    parser.add_argument("--json", action="store_true", help="프레임별 결과를 JSON Lines로 표준 출력")
    args = parser.parse_args()
    if args.list_cameras:
        try:
            print(json.dumps(camera_info(), ensure_ascii=False, indent=2))
        except ImportError as error:
            parser.exit(1, f"Picamera2 설치 필요: {error}\n")
        return
    if args.camera_num < 0 or min(args.width, args.height) < 32 or args.fps <= 0:
        parser.error("camera-num은 0 이상, 해상도는 32 이상, fps는 양수여야 합니다")
    if not 0 < args.confidence <= 1 or args.imgsz < 32 or args.imgsz % 32:
        parser.error("confidence는 0 초과 1 이하, imgsz는 32 이상의 32 배수여야 합니다")
    if args.stale_seconds <= 0 or not 1 <= args.http_port <= 65535:
        parser.error("stale-seconds는 양수, http-port는 1~65535여야 합니다")
    if not args.model.is_file():
        parser.error(f"YOLO11n 모델 파일 없음: {args.model}")
    callback = (lambda result: print(json.dumps(result, ensure_ascii=False), flush=True)) if args.json else None
    service = PersonService(
        lambda: PiCamera(args.camera_num, args.width, args.height, args.fps),
        lambda: PersonDetector(args.model, args.confidence, args.imgsz),
        stale_seconds=args.stale_seconds, on_result=callback)
    server = make_server(service, args.host, args.http_port)

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        service.start()
        print(f"Pi Camera 인덱스 {args.camera_num}, YOLO11n CPU, http://{args.host}:{args.http_port}", file=sys.stderr)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.close()
        server.server_close()


if __name__ == "__main__":
    main()

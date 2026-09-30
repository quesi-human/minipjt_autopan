"""Local browser preview of ESP32-CAM USB JPEG frames."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time

import serial
from capture import receive_frame

PAGE = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESP32-CAM USB 실시간 영상</title>
<style>
body{margin:0;background:#11151b;color:#edf2fa;font:16px system-ui,sans-serif}
main{max-width:1100px;margin:32px auto;padding:0 20px}h1{font-size:24px;margin:0 0 12px}
#status{color:#acd9bd;margin-bottom:16px;min-height:24px}
.screen{background:#000;border-radius:12px;overflow:hidden;min-height:240px}
img{width:100%;display:block;aspect-ratio:4/3;object-fit:contain}
button{margin:16px 0;padding:10px 18px;background:#24334b;color:white;border:0;border-radius:8px;cursor:pointer}
p{color:#9cabbc;line-height:1.6}
</style><main><h1>ESP32-CAM · USB 실시간 영상</h1><div id="status">카메라 연결 중…</div>
<div class="screen" id="screen"><img src="/stream" alt="카메라 연결 중"></div>
<button onclick="document.getElementById('screen').requestFullscreen()">전체 화면</button>
<p>USB로 수신한 320×240 영상을 확대 표시합니다. 가장 큰 사람 박스를 가까운 대상으로 추정해 노란색으로 표시하고 중심 x좌표를 제공합니다.<br>
전체 화면 종료: Esc</p></main>
<script>setInterval(async()=>{try{const r=await fetch('/status',{cache:'no-store'});const s=await r.json();
document.getElementById('status').textContent=s.error?'연결 오류: '+s.error:
s.frames?`USB ${s.fps.toFixed(1)} FPS · 누락 ${s.dropped}`+
(s.yolo_enabled?` · YOLO ${s.inference_fps.toFixed(1)} FPS · 사람 ${s.person_count}명 · ${s.inference_ms.toFixed(1)} ms · ${s.yolo_status}`:' · 탐지 비활성')+
(s.yolo_enabled?(s.closest_person?` · 가까운 대상 #${s.closest_person.track_id} · 중심 x=${s.closest_person.center_x.toFixed(1)}`:' · 추적 대상 없음'):'')+
(s.camera_warning?' · '+s.camera_warning:''):'카메라 연결 중…';
}catch(e){document.getElementById('status').textContent='미리보기 서버 연결 끊김';}},500);</script></html>"""

condition = threading.Condition()
stop = threading.Event()
state = {"jpeg": None, "raw_jpeg": None, "frames": 0, "output_frames": 0,
         "dropped": 0, "fps": 0, "error": None, "baud": 921600,
         "yolo_enabled": False, "yolo_status": "비활성", "model": None,
         "device": None, "inference_fps": 0, "inference_ms": 0,
         "person_count": 0, "detections": [], "inference_frames": 0, "camera_warning": None,
         "closest_person": None, "closest_person_x": None,
         "closest_person_method": "largest_bbox_area", "frame_width": 320, "frame_height": 240}


def camera_worker(args):
    port = serial.Serial()
    port.port, port.baudrate, port.timeout = args.port, 115200, 0.2
    port.dtr = port.rts = False
    try:
        port.open()
        port.rts = True
        time.sleep(0.1)
        port.rts = False
        time.sleep(3)
        port.reset_input_buffer()
        commands = [(b"E0\n", b"EXPOSURE 0")]
        if args.exposure:
            commands.append((f"E{args.exposure}\n".encode(), f"EXPOSURE {args.exposure}".encode()))
        commands.append((b"T64,1000\n", b"TRANSFER 64 1000"))
        if args.baud != 115200:
            commands.append((f"B{args.baud}\n".encode(), f"BAUD {args.baud}".encode()))
        for command, expected in commands:
            port.write(command)
            port.flush()
            deadline = time.monotonic() + 5
            while port.readline().strip() != expected:
                if time.monotonic() >= deadline:
                    raise TimeoutError("USB 전송 설정 응답 없음")
            if command.startswith(b"E"):
                time.sleep(0.3)
        port.baudrate = args.baud
        time.sleep(0.1)
        started = time.monotonic()
        consecutive = 0
        while not stop.is_set():
            port.write(b"F")
            port.flush()
            try:
                jpeg, sequence, width, height = receive_frame(port, 2)
            except (TimeoutError, ValueError) as error:
                with condition:
                    state["dropped"] += 1
                consecutive += 1
                port.reset_input_buffer()
                if consecutive >= 5:
                    raise RuntimeError(f"연속 프레임 수신 실패: {error}")
                continue
            consecutive = 0
            with condition:
                state["raw_jpeg"] = jpeg
                state["frames"] += 1
                state["fps"] = state["frames"] / (time.monotonic() - started)
                if not args.yolo:
                    state["jpeg"] = jpeg
                    state["output_frames"] += 1
                condition.notify_all()
                if state["frames"] == 1 or state["frames"] % 300 == 0:
                    print(f"USB 영상 수신: {state['frames']} frames, {width}x{height}, "
                          f"{state['fps']:.2f} FPS, dropped={state['dropped']}", flush=True)
    except Exception as error:
        with condition:
            state["error"] = str(error)
            condition.notify_all()
        print(f"카메라 연결 오류: {error}", flush=True)
    finally:
        port.close()


def detector_worker(args):
    try:
        from person_detector import PersonDetector
        detector = PersonDetector(args.model, args.confidence, args.imgsz, args.device)
        with condition:
            state["yolo_status"] = "실행 중"
            state["device"] = detector.device_name
        print(f"YOLO11n 준비 완료: {detector.device_name}", flush=True)
        last_frame = -1
        started = None
        while not stop.is_set():
            with condition:
                condition.wait_for(lambda: state["frames"] != last_frame or stop.is_set(), timeout=1)
                if stop.is_set():
                    return
                jpeg, frame_number = state["raw_jpeg"], state["frames"]
            if jpeg is None or frame_number == last_frame:
                time.sleep(0.05)
                continue
            last_frame = frame_number
            if started is None:
                started = time.monotonic()
            annotated, detections, duration_ms = detector.detect(jpeg)
            with condition:
                state["jpeg"] = annotated
                state["output_frames"] += 1
                state["inference_frames"] += 1
                state["inference_ms"] = duration_ms
                state["inference_fps"] = state["inference_frames"] / (time.monotonic() - started)
                state["person_count"] = len(detections)
                state["detections"] = detections
                state["closest_person"] = detector.closest_person
                state["closest_person_x"] = (detector.closest_person["center_x"]
                                             if detector.closest_person is not None else None)
                state["frame_width"] = detector.frame_width
                state["frame_height"] = detector.frame_height
                state["camera_warning"] = detector.camera_warning
                condition.notify_all()
                if state["inference_frames"] == 1 or state["inference_frames"] % 300 == 0:
                    print(f"YOLO: {state['inference_frames']} frames, people={len(detections)}, "
                          f"{duration_ms:.1f} ms, {state['inference_fps']:.2f} FPS", flush=True)
    except Exception as error:
        with condition:
            state["yolo_status"] = "오류"
            state["error"] = f"YOLO: {error}"
            condition.notify_all()
        print(f"YOLO 오류: {error}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            self.respond(PAGE.encode(), "text/html; charset=utf-8")
        elif self.path == "/status":
            with condition:
                status = {k: v for k, v in state.items() if k not in ("jpeg", "raw_jpeg")}
            self.respond(json.dumps(status).encode(), "application/json")
        elif self.path == "/snapshot.jpg":
            with condition:
                jpeg = state["jpeg"]
            if jpeg is None:
                self.send_error(503, "Camera is starting")
            else:
                self.respond(jpeg, "image/jpeg")
        elif self.path == "/raw.jpg":
            with condition:
                jpeg = state["raw_jpeg"]
            if jpeg is None:
                self.send_error(503, "Camera is starting")
            else:
                self.respond(jpeg, "image/jpeg")
        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last_frame = -1
            try:
                while not stop.is_set():
                    with condition:
                        condition.wait_for(lambda: state["output_frames"] != last_frame or stop.is_set(), timeout=2)
                        jpeg, frame_number = state["jpeg"], state["output_frames"]
                    if jpeg is None or frame_number == last_frame:
                        time.sleep(0.05)
                        continue
                    last_frame = frame_number
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                                     str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)

    def respond(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--http-port", type=int, default=8765)
    parser.add_argument("--baud", type=int, default=921600,
                        choices=(115200, 230400, 460800, 921600, 1500000, 2000000))
    parser.add_argument("--yolo", action="store_true", help="YOLO11n 사람 탐지 활성화")
    parser.add_argument("--model", type=Path, default=Path(__file__).parent / "models/yolo11n.pt")
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="auto", help="auto, cpu, 0 등")
    parser.add_argument("--exposure", type=int, default=300,
                        help="OV2640 노출: 0 자동, 1~1200 수동 (기본 300)")
    args = parser.parse_args()
    state["baud"] = args.baud
    if not 0 <= args.exposure <= 1200:
        parser.error("exposure는 0~1200이어야 합니다")
    if not 0 < args.confidence <= 1 or args.imgsz < 32:
        parser.error("confidence는 0~1, imgsz는 32 이상이어야 합니다")
    if args.yolo and not args.model.is_file():
        parser.error(f"모델 파일 없음: {args.model}")
    state["yolo_enabled"] = args.yolo
    state["model"] = args.model.name if args.yolo else None
    state["yolo_status"] = "모델 준비 중" if args.yolo else "비활성"
    server = ThreadingHTTPServer(("127.0.0.1", args.http_port), Handler)
    workers = [threading.Thread(target=camera_worker, args=(args,), daemon=True)]
    if args.yolo:
        workers.append(threading.Thread(target=detector_worker, args=(args,), daemon=True))
    for worker in workers:
        worker.start()
    print(f"미리보기: http://localhost:{args.http_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        with condition:
            condition.notify_all()
        server.server_close()
        for worker in workers:
            worker.join(timeout=10)


if __name__ == "__main__":
    main()

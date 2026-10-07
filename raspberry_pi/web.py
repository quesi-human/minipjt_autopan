"""Browser preview and local coordinates API."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

PAGE = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pi 5 · YOLO11n</title><style>
body{background:#11151b;color:#edf2fa;font:16px system-ui;margin:24px auto;max-width:960px;padding:0 16px}
img{width:100%;background:#000}#status{margin:16px 0;white-space:pre-wrap}
</style><h1>Pi Camera · YOLO11n 사람 탐지</h1>
<p>가장 큰 사람 박스를 노란색으로 표시합니다. 좌표 원점은 영상의 왼쪽 위입니다.</p>
<div id="status">카메라와 모델 준비 중…</div><img src="/stream" alt="탐지 영상">
<script>setInterval(async()=>{try{
const s=await (await fetch('/status',{cache:'no-store'})).json();
document.getElementById('status').textContent=s.error?'오류: '+s.error:
s.stale?'결과 대기 또는 영상 정지':
`사람 ${s.person_count}명 · ${s.inference_ms.toFixed(0)} ms · ${s.frame_width}×${s.frame_height}\n`+
(s.center?`선택 대상 중심: x=${s.center.x.toFixed(1)}, y=${s.center.y.toFixed(1)}`:'탐지된 사람 없음');
}catch(e){document.getElementById('status').textContent='서버 연결 끊김';}},500);</script></html>"""


def make_server(service, host="127.0.0.1", port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, body, content_type, code=200):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self.respond(PAGE.encode(), "text/html; charset=utf-8")
            elif self.path in ("/status", "/center"):
                status = service.read()
                if self.path == "/center":
                    status = {key: status[key] for key in
                              ("center", "target", "person_count", "frame_width", "frame_height",
                               "inference_frames", "updated_at", "result_age_ms", "stale", "error")}
                self.respond(json.dumps(status, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            elif self.path == "/snapshot.jpg":
                jpeg = service.snapshot()
                if jpeg is None:
                    self.send_error(503, "No current camera frame")
                else:
                    self.respond(jpeg, "image/jpeg")
            elif self.path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                previous = -1
                try:
                    while not service.stop_event.is_set():
                        with service.condition:
                            service.condition.wait_for(
                                lambda: service.state["frames"] != previous or service.stop_event.is_set(),
                                timeout=1)
                            sequence = service.state["frames"]
                            jpeg = service.snapshot()
                            if service.state["error"]:
                                return
                        if jpeg is None or sequence == previous:
                            previous = sequence
                            continue
                        previous = sequence
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                                         str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self.send_error(404)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server

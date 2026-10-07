"""Thread-safe latest result for Pi-local Python callers and HTTP clients."""
from copy import deepcopy
import threading
import time


class PersonService:
    def __init__(self, camera_factory, detector_factory, stale_seconds=3, on_result=None):
        if stale_seconds <= 0:
            raise ValueError("stale_seconds must be positive")
        self.camera_factory = camera_factory
        self.detector_factory = detector_factory
        self.stale_seconds = stale_seconds
        self.on_result = on_result
        self.condition = threading.Condition()
        self.stop_event = threading.Event()
        self.thread = None
        self.last_update = None
        self.jpeg = None
        self.state = {"model": "yolo11n", "device": "cpu", "camera": None,
                      "yolo_enabled": True, "frames": 0, "inference_frames": 0,
                      "frame_width": None, "frame_height": None,
                      "person_count": 0, "detections": [], "target": None,
                      "center": None, "inference_ms": 0, "updated_at": None,
                      "error": None, "running": False,
                      "selection_method": "largest_person_bbox_area"}

    def start(self):
        if self.thread is not None:
            raise RuntimeError("service already started")
        self.thread = threading.Thread(target=self._run, name="pi-person-detector", daemon=True)
        self.thread.start()
        return self

    def read(self):
        """Return a copy; center is None before results, on failure, or if stale."""
        with self.condition:
            status = deepcopy(self.state)
            age = time.monotonic() - self.last_update if self.last_update is not None else None
            status["result_age_ms"] = round(age * 1000, 3) if age is not None else None
            status["stale"] = age is None or age > self.stale_seconds
            if status["stale"] or status["error"] or not status["running"]:
                status.update(center=None, target=None, person_count=0, detections=[])
            center = status["center"]
            status["closest_person"] = status["target"]
            status["closest_person_x"] = center["x"] if center else None
            status["closest_person_y"] = center["y"] if center else None
            return status

    def snapshot(self):
        with self.condition:
            status = self.read()
            return self.jpeg if not status["stale"] and not status["error"] and status["running"] else None

    def _run(self):
        camera = None
        try:
            # Initialise YOLO before acquiring the camera, to avoid holding it on model failure.
            detector = self.detector_factory()
            camera = self.camera_factory()
            with self.condition:
                self.state.update(camera=camera.info, running=True)
            while not self.stop_event.is_set():
                frame = camera.read()
                result, annotated = detector.detect(frame)
                import cv2
                ok, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not ok:
                    raise RuntimeError("표시용 JPEG 인코딩 실패")
                with self.condition:
                    if self.stop_event.is_set():
                        break
                    self.state.update(result)
                    self.state["frames"] += 1
                    self.state["inference_frames"] += 1
                    self.state["updated_at"] = time.time()
                    self.last_update = time.monotonic()
                    self.jpeg = encoded.tobytes()
                    self.condition.notify_all()
                if self.on_result:
                    self.on_result(self.read())
        except Exception as error:
            with self.condition:
                self.state["error"] = str(error)
        finally:
            try:
                if camera is not None:
                    camera.close()
            except Exception as error:
                with self.condition:
                    self.state["error"] = self.state["error"] or str(error)
            with self.condition:
                self.state.update(running=False, center=None, target=None,
                                  person_count=0, detections=[])
                self.jpeg = None
                self.condition.notify_all()

    def close(self):
        self.stop_event.set()
        with self.condition:
            self.state["running"] = False
            self.condition.notify_all()
        if self.thread:
            self.thread.join(timeout=10)

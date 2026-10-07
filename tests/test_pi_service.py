import io
import json
import sys
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

from raspberry_pi.camera import PiCamera
from raspberry_pi.service import PersonService
from raspberry_pi.vision import select_largest_person
from raspberry_pi.web import make_server


def person(box, confidence=0.8):
    return {"class_id": 0, "confidence": confidence, "xyxy": box}


class SelectionTests(unittest.TestCase):
    def test_largest_person_not_largest_other_class_or_highest_confidence(self):
        boxes = [person([10, 20, 30, 60], 0.99), person([100.5, 50, 200, 250], 0.6),
                 {"class_id": 2, "xyxy": [0, 0, 640, 480]}]
        target = select_largest_person(boxes, 640, 480)
        self.assertEqual(target["xyxy"], boxes[1]["xyxy"])
        self.assertEqual(target["center_x"], 150.25)
        self.assertEqual(target["center_y"], 150)
        self.assertEqual(target["bbox_area"], 19900)
        self.assertEqual(target["center_x_normalized"], 150.25 / 640)
        self.assertEqual(target["center_y_normalized"], 150 / 480)

    def test_clipping_invalid_and_empty(self):
        self.assertIsNone(select_largest_person([], 640, 480))
        self.assertIsNone(select_largest_person([person([700, 0, 800, 100]),
                                               person([10, 10, 0, 0])], 640, 480))
        target = select_largest_person([person([-10, -20, 20, 40])], 640, 480)
        self.assertEqual(target["xyxy"], [0, 0, 20, 40])
        self.assertEqual((target["center_x"], target["center_y"]), (10, 20))

    def test_tie_keeps_first(self):
        first = person([0, 0, 20, 20])
        self.assertEqual(select_largest_person([first, person([50, 50, 70, 70])], 640, 480)["xyxy"], first["xyxy"])


class CameraTests(unittest.TestCase):
    def test_camera_zero_configuration_and_release(self):
        module = types.SimpleNamespace(Picamera2=Mock())
        module.Picamera2.global_camera_info.return_value = [{"Num": 0, "Id": "cam0"}]
        camera = module.Picamera2.return_value
        with patch.dict(sys.modules, {"picamera2": module}):
            source = PiCamera()
            module.Picamera2.assert_called_once_with(0)
            camera.create_video_configuration.assert_called_once_with(
                main={"size": (640, 480), "format": "RGB888"},
                controls={"FrameRate": 30}, buffer_count=4, queue=False)
            self.assertIs(source.read(), camera.capture_array.return_value)
            camera.capture_array.assert_called_once_with("main")
            source.close()
            source.close()
        camera.stop.assert_called_once()
        camera.close.assert_called_once()

    def test_start_failure_releases_camera(self):
        module = types.SimpleNamespace(Picamera2=Mock())
        module.Picamera2.global_camera_info.return_value = [{"Num": 0}]
        module.Picamera2.return_value.start.side_effect = RuntimeError("start failed")
        with patch.dict(sys.modules, {"picamera2": module}), self.assertRaisesRegex(RuntimeError, "start failed"):
            PiCamera()
        module.Picamera2.return_value.close.assert_called_once()

    def test_missing_or_wrong_camera_does_not_open(self):
        module = types.SimpleNamespace(Picamera2=Mock())
        with patch.dict(sys.modules, {"picamera2": module}):
            module.Picamera2.global_camera_info.return_value = []
            with self.assertRaises(RuntimeError):
                PiCamera()
            module.Picamera2.global_camera_info.return_value = [{"Num": 0}]
            with self.assertRaises(ValueError):
                PiCamera(camera_num=1)
        module.Picamera2.assert_not_called()


class ServiceTests(unittest.TestCase):
    def populated(self):
        service = PersonService(Mock(), Mock())
        service.state.update(running=True, center={"x": 100, "y": 200},
                             target={"center_x": 100, "center_y": 200},
                             person_count=1, detections=[person([0, 0, 200, 400])])
        service.last_update = time.monotonic()
        service.jpeg = b'jpeg'
        return service

    def test_initial_fresh_stale_error_and_copy(self):
        initial = PersonService(Mock(), Mock()).read()
        self.assertIsNone(initial["center"])
        self.assertTrue(initial["stale"])
        service = self.populated()
        result = service.read()
        self.assertFalse(result["stale"])
        self.assertEqual(result["closest_person_y"], 200)
        result["center"]["x"] = -100
        self.assertEqual(service.read()["center"]["x"], 100)
        service.last_update -= 4
        self.assertIsNone(service.read()["center"])
        self.assertIsNone(service.snapshot())
        service.last_update = time.monotonic()
        service.state["error"] = "camera disconnected"
        self.assertEqual(service.read()["person_count"], 0)
        self.assertIsNone(service.read()["target"])
        self.assertIsNone(service.snapshot())
        service.close()
        self.assertIsNone(service.read()["center"])

    def test_worker_returns_results_clears_empty_and_releases(self):
        camera = Mock(info={"Num": 0})
        detector = Mock()
        detected = {"frame_width": 640, "frame_height": 480, "person_count": 1,
                    "detections": [person([0, 0, 200, 400])],
                    "target": {"center_x": 100, "center_y": 200},
                    "center": {"x": 100, "y": 200}, "inference_ms": 20}
        empty = {**detected, "person_count": 0, "detections": [], "target": None, "center": None}
        detector.detect.side_effect = [(detected, object()), (empty, object())]
        results = []
        done = threading.Event()
        def collect(result):
            results.append(result)
            if len(results) == 2:
                service.stop_event.set()
                done.set()
        service = PersonService(lambda: camera, lambda: detector, on_result=collect)
        cv2 = types.SimpleNamespace(IMWRITE_JPEG_QUALITY=1, imencode=Mock(return_value=(True, Mock(tobytes=lambda: b'jpeg'))))
        with patch.dict(sys.modules, {"cv2": cv2}):
            service.start()
            self.assertTrue(done.wait(2))
            service.close()
        self.assertEqual(results[0]["center"], {"x": 100, "y": 200})
        self.assertIsNone(results[1]["center"])
        self.assertEqual(results[1]["inference_frames"], 2)
        camera.close.assert_called_once()

    def test_worker_error_does_not_hold_last_center(self):
        camera = Mock(info={"Num": 0})
        camera.read.side_effect = RuntimeError("CSI disconnected")
        service = PersonService(lambda: camera, lambda: Mock())
        service.start()
        service.thread.join(timeout=2)
        self.assertEqual(service.read()["error"], "CSI disconnected")
        self.assertIsNone(service.read()["center"])
        camera.close.assert_called_once()


class ApiTests(unittest.TestCase):
    def request(self, service, path):
        # Exercise the actual HTTP handler without binding a test network port.
        with patch("raspberry_pi.web.ThreadingHTTPServer") as server:
            make_server(service)
            handler_class = server.call_args.args[1]
        handler = object.__new__(handler_class)
        handler.path = path
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.send_error = Mock()
        handler.do_GET()
        return handler

    def test_center_api_and_no_person(self):
        service = ServiceTests().populated()
        handler = self.request(service, "/center")
        self.assertEqual(json.loads(handler.wfile.getvalue())["center"], {"x": 100, "y": 200})
        service.state.update(center=None, target=None, person_count=0, detections=[])
        payload = json.loads(self.request(service, "/center").wfile.getvalue())
        self.assertIsNone(payload["center"])
        self.assertFalse(payload["stale"])

    def test_error_and_unavailable_snapshot(self):
        service = ServiceTests().populated()
        service.state["error"] = "camera error"
        payload = json.loads(self.request(service, "/status").wfile.getvalue())
        self.assertIsNone(payload["closest_person_x"])
        self.assertEqual(payload["error"], "camera error")
        self.request(service, "/snapshot.jpg").send_error.assert_called_once_with(503, "No current camera frame")


if __name__ == "__main__":
    unittest.main()

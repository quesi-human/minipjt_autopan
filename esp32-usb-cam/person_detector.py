"""YOLO person-only detection on a decoded USB camera frame."""
from pathlib import Path
import time

import cv2
import numpy as np
import torch
from ultralytics import YOLO
from closest_person import select_closest_person
from lanyard_classifier import classify_lanyard


class PersonDetector:
    def __init__(self, model_path, confidence=0.35, image_size=640, device="auto"):
        self.model = YOLO(str(model_path))
        self.model_name = Path(model_path).stem
        if self.model.names[0] != "person":
            raise ValueError("사람 클래스가 0인 COCO 탐지 모델이 필요합니다")
        self.confidence = confidence
        self.image_size = image_size
        self.device = ("0" if torch.cuda.is_available() else "cpu") if device == "auto" else device
        self.device_name = torch.cuda.get_device_name(0) if self.device == "0" else self.device
        self.camera_warning = None
        self.closest_person = None
        self.frame_width, self.frame_height = 320, 240
        self.model.predict(np.zeros((240, 320, 3), dtype=np.uint8),
                           classes=[0], conf=confidence, imgsz=image_size,
                           device=self.device, verbose=False)

    def detect(self, jpeg):
        started = time.perf_counter()
        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("카메라 JPEG를 디코딩할 수 없습니다")
        self.frame_height, self.frame_width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.camera_warning = ("영상이 거의 흰색입니다. 카메라 노출과 촬영 방향을 확인하세요."
                               if float(np.mean(gray > 245)) > 0.97 else None)
        result = self.model.track(frame, classes=[0], conf=self.confidence,
                                  imgsz=self.image_size, device=self.device,
                                  tracker="bytetrack.yaml", persist=True,
                                  verbose=False)[0]
        detections = []
        clean_frame = frame.copy()
        for box in result.boxes.cpu():
            x1, y1, x2, y2 = [int(round(value)) for value in box.xyxy[0].tolist()]
            score = float(box.conf[0])
            track_id = int(box.id[0]) if box.id is not None else None
            classification = classify_lanyard(clean_frame, [x1, y1, x2, y2])
            detections.append({"class": "person", "confidence": round(score, 4),
                               "xyxy": [x1, y1, x2, y2], "track_id": track_id,
                               **classification})
            color = {"student": (255, 220, 80), "staff": (80, 200, 255),
                     "unknown": (160, 160, 160)}[classification["role"]]
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{classification['role']} #{track_id} {score:.2f}",
                        (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        self.closest_person = select_closest_person(detections, self.frame_width, self.frame_height)
        if self.closest_person is not None:
            target = self.closest_person
            x1, y1, x2, y2 = target["xyxy"]
            center = (int(round(target["center_x"])), int(round(target["center_y"])))
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 255), 3)
            cv2.drawMarker(frame, center, (0, 220, 255), cv2.MARKER_CROSS, 16, 2)
            cv2.putText(frame, f"closest #{target['track_id']} x={target['center_x']:.1f}",
                        (5, self.frame_height - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 220, 255), 1)
        cv2.putText(frame, f"{self.model_name} | people: {len(detections)}", (5, 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 100), 1)
        success, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            raise RuntimeError("탐지 결과 JPEG 생성 실패")
        return encoded.tobytes(), detections, (time.perf_counter() - started) * 1000

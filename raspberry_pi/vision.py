"""Person-only YOLO11n inference; all coordinates refer to the camera frame."""
from pathlib import Path
import time

DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "models" / "yolo11n.pt"


def select_largest_person(detections, width, height):
    """Return the largest valid person box, or None (ties keep input order)."""
    candidates = []
    for detection in detections:
        if detection.get("class_id") != 0:
            continue
        x1, y1, x2, y2 = detection["xyxy"]
        x1, x2 = max(0, x1), min(width, x2)
        y1, y2 = max(0, y1), min(height, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        x, y = (x1 + x2) / 2, (y1 + y2) / 2
        candidates.append({**detection, "xyxy": [x1, y1, x2, y2],
                           "bbox_area": (x2 - x1) * (y2 - y1),
                           "center_x": x, "center_y": y,
                           "center_x_normalized": x / width,
                           "center_y_normalized": y / height})
    return max(candidates, key=lambda item: item["bbox_area"], default=None)


class PersonDetector:
    def __init__(self, model_path=DEFAULT_MODEL, confidence=0.35, image_size=320):
        import cv2
        from ultralytics import YOLO

        if not Path(model_path).is_file():
            raise FileNotFoundError(f"YOLO11n 모델 없음: {model_path}")
        self.cv2 = cv2
        self.model = YOLO(str(model_path), task="detect")
        if self.model.names.get(0) != "person":
            raise ValueError("COCO person 클래스가 0인 YOLO11n 모델이 필요합니다")
        self.confidence = confidence
        self.image_size = image_size

    def detect(self, frame):
        """Accept a BGR uint8 array; return (status dictionary, annotated BGR)."""
        started = time.monotonic()
        height, width = frame.shape[:2]
        result = self.model.predict(frame, classes=[0], conf=self.confidence,
                                    imgsz=self.image_size, device="cpu", verbose=False)[0]
        detections = []
        for box in result.boxes.cpu():
            class_id = int(box.cls[0])
            if class_id == 0:
                detections.append({"class_id": 0, "class": "person",
                                   "confidence": float(box.conf[0]),
                                   "xyxy": [float(v) for v in box.xyxy[0].tolist()]})
        target = select_largest_person(detections, width, height)
        annotated = frame.copy()
        for detection in detections:
            x1, y1, x2, y2 = (round(v) for v in detection["xyxy"])
            self.cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 100), 2)
        if target:
            x1, y1, x2, y2 = (round(v) for v in target["xyxy"])
            center = (round(target["center_x"]), round(target["center_y"]))
            self.cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 255), 3)
            self.cv2.drawMarker(annotated, center, (0, 220, 255), self.cv2.MARKER_CROSS, 16, 2)
        return {"frame_width": width, "frame_height": height,
                "person_count": len(detections), "detections": detections,
                "target": target,
                "center": {"x": target["center_x"], "y": target["center_y"]} if target else None,
                "inference_ms": round((time.monotonic() - started) * 1000, 3)}, annotated

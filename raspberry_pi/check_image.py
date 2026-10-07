"""Offline YOLO11n check, without Picamera2 or a connected camera."""
import json
from pathlib import Path

from .vision import PersonDetector


def main():
    import cv2
    import numpy as np
    import ultralytics

    source = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"
    frame = cv2.imread(str(source))
    if frame is None:
        raise RuntimeError(f"Ultralytics 예제 이미지 없음: {source}")
    frame = cv2.resize(frame, (640, 480))
    detector = PersonDetector()
    result, annotated = detector.detect(frame)
    assert result["person_count"] > 0, result
    target = result["target"]
    assert target is not None
    assert all(box["class_id"] == 0 for box in result["detections"])
    assert target["bbox_area"] == max(
        (box["xyxy"][2] - box["xyxy"][0]) * (box["xyxy"][3] - box["xyxy"][1])
        for box in result["detections"])
    x1, y1, x2, y2 = target["xyxy"]
    assert result["center"] == {"x": (x1 + x2) / 2, "y": (y1 + y2) / 2}
    assert annotated.shape == frame.shape
    empty, _ = detector.detect(np.zeros_like(frame))
    assert empty["person_count"] == 0 and empty["target"] is None and empty["center"] is None
    print(json.dumps({"passed": True, "sample": result, "empty_center": empty["center"]}, indent=2))


if __name__ == "__main__":
    main()

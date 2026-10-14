"""Bounded horizontal camera tracking; the camera worker owns serial writes."""
import math

from closest_person import select_closest_person


class PanTracker:
    def __init__(self, reverse=False):
        self.angle = 90.0
        self.reverse = reverse
        self.target_id = None
        self.last_seen = None
        self.last_update = None

    def update(self, detections, width, height, now, frame_age=0.0):
        result = {"angle": round(self.angle, 1), "target_id": self.target_id,
                  "error": None, "status": "대상 없음", "command": "S\n"}
        if not math.isfinite(frame_age) or frame_age > 0.4 or frame_age < 0:
            self.last_update = None
            result["status"] = "오래된 영상: 정지"
            return result
        candidates = detections
        if self.target_id is not None:
            candidates = [d for d in detections if d.get("track_id") == self.target_id]
            if not candidates:
                self.last_update = None
                if self.last_seen is not None and now - self.last_seen < 0.5:
                    result["status"] = "대상 재탐지 대기"
                    return result
                self.target_id = None
                candidates = detections
        if width <= 0 or height <= 0:
            self.last_update = None
            return result
        target = select_closest_person(candidates, width, height)
        if target is None:
            self.last_update = None
            return result
        error = (target["center_x"] - width / 2) / (width / 2)
        if not math.isfinite(error):
            self.last_update = None
            return result
        self.target_id = target.get("track_id")
        self.last_seen = now
        dt = 0.02 if self.last_update is None else max(0.0, min(now - self.last_update, 0.1))
        self.last_update = now
        if abs(error) > 0.08:
            step = max(-2.0, min(2.0, error * 30.0 * dt))
            self.angle = max(60.0, min(120.0, self.angle + (-step if self.reverse else step)))
        return {"angle": round(self.angle, 1), "target_id": self.target_id,
                "error": round(error, 3), "status": "중앙 유지" if abs(error) <= 0.08 else "추적 중",
                "command": f"P{round(self.angle)}\n"}

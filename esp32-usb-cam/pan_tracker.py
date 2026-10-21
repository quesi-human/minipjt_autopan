"""Bounded horizontal camera tracking; the camera worker owns serial writes."""
import math

from closest_person import select_closest_person


class PanTracker:
    # Error is normalized by half the frame width: 0.04 = +/-2% of width.
    CENTER_TOLERANCE = 0.04
    TRACKING_GAIN = 15.0
    MAX_STEP_DEG = 1.0
    CHECK_SETTLE_SECONDS = 0.6
    CHECK_MIN_MOVE_DEG = 2
    CHECK_ERROR_INCREASE = 0.10  # 16px at 320px width.
    CHECK_CONFIRM_FRAMES = 3
    REVERSE_COOLDOWN_SECONDS = 5.0

    def __init__(self, reverse=False):
        self.angle = 90.0
        self.reverse = reverse
        self.target_id = None
        self.last_seen = None
        self.last_update = None
        self.direction_corrections = 0
        self.last_reversal = -math.inf
        self.motion_check = None
        self.worsening_frames = 0

    def reset_motion_check(self):
        self.motion_check = None
        self.worsening_frames = 0

    def check_direction(self, error, now):
        """Compare one tracked person's error after a meaningful commanded move.

        This is visual feedback, not proof of servo position: a moving person
        can also change the error. Require repeated evidence and a cooldown.
        """
        if (self.target_id is None or abs(error) <= self.CENTER_TOLERANCE
                or now - self.last_reversal < self.REVERSE_COOLDOWN_SECONDS):
            self.reset_motion_check()
            return False
        baseline = self.motion_check
        if (baseline is None or baseline[0] != self.target_id
                or baseline[1] * error <= 0
                or abs(error) < abs(baseline[1]) - self.CENTER_TOLERANCE):
            self.motion_check = (self.target_id, error, round(self.angle), now)
            self.worsening_frames = 0
            return False
        _, previous_error, previous_angle, started = baseline
        if (now - started < self.CHECK_SETTLE_SECONDS
                or abs(round(self.angle) - previous_angle) < self.CHECK_MIN_MOVE_DEG):
            return False
        if abs(error) - abs(previous_error) >= self.CHECK_ERROR_INCREASE:
            self.worsening_frames += 1
        else:
            self.worsening_frames = 0
        if self.worsening_frames < self.CHECK_CONFIRM_FRAMES:
            return False
        self.reverse = not self.reverse
        self.direction_corrections += 1
        self.last_reversal = now
        self.reset_motion_check()
        return True

    def update(self, detections, width, height, now, frame_age=0.0):
        result = {"angle": round(self.angle, 1), "target_id": self.target_id,
                  "error": None, "status": "대상 없음", "command": "S\n",
                  "reverse": self.reverse, "direction_corrections": self.direction_corrections}
        if not math.isfinite(frame_age) or frame_age > 0.4 or frame_age < 0:
            self.last_update = None
            self.reset_motion_check()
            result["status"] = "오래된 영상: 정지"
            return result
        candidates = detections
        if self.target_id is not None:
            candidates = [d for d in detections if d.get("track_id") == self.target_id]
            if not candidates:
                self.last_update = None
                self.reset_motion_check()
                if self.last_seen is not None and now - self.last_seen < 0.5:
                    result["status"] = "대상 재탐지 대기"
                    return result
                self.target_id = None
                candidates = detections
        if width <= 0 or height <= 0:
            self.last_update = None
            self.reset_motion_check()
            return result
        target = select_closest_person(candidates, width, height)
        if target is None:
            self.last_update = None
            self.reset_motion_check()
            return result
        error = (target["center_x"] - width / 2) / (width / 2)
        if not math.isfinite(error):
            self.last_update = None
            self.reset_motion_check()
            return result
        self.target_id = target.get("track_id")
        self.last_seen = now
        if self.last_update is not None and now - self.last_update > 0.4:
            self.reset_motion_check()
        corrected = self.check_direction(error, now)
        dt = 0.02 if self.last_update is None else max(0.0, min(now - self.last_update, 0.1))
        self.last_update = now
        if abs(error) > self.CENTER_TOLERANCE:
            step = max(-self.MAX_STEP_DEG,
                       min(self.MAX_STEP_DEG, error * self.TRACKING_GAIN * dt))
            self.angle = max(60.0, min(120.0, self.angle + (-step if self.reverse else step)))
        status = "중앙 유지" if abs(error) <= self.CENTER_TOLERANCE else "추적 중"
        if corrected:
            status = "오차 증가 감지: 방향 반전"
        elif abs(error) > self.CENTER_TOLERANCE and self.angle in (60.0, 120.0):
            status = "회전 한계: 중앙 정렬 미완료"
        return {"angle": round(self.angle, 1), "target_id": self.target_id,
                "error": round(error, 3), "status": status,
                "reverse": self.reverse, "direction_corrections": self.direction_corrections,
                "target_center_x": target["center_x"], "frame_center_x": width / 2,
                "command": f"P{round(self.angle)}\n"}

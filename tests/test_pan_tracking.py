from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'esp32-usb-cam'))
from pan_tracker import PanTracker


def person(center, identity=1, size=60):
    return {"track_id": identity, "xyxy": [center-size/2, 40, center+size/2, 200]}


class PanTests(unittest.TestCase):
    def test_center_and_direction(self):
        p = PanTracker()
        self.assertEqual(p.update([person(160)], 320, 240, 0)["command"], "P90\n")
        self.assertGreater(p.update([person(280)], 320, 240, .1)["angle"], 90)
        reverse = PanTracker(reverse=True)
        self.assertLess(reverse.update([person(280)], 320, 240, 0)["angle"], 90)

    def test_travel_limits_and_step_bound(self):
        for center, boundary in ((300, 120), (20, 60)):
            p = PanTracker()
            previous = 90
            for i in range(100):
                angle = p.update([person(center)], 320, 240, i*.1)["angle"]
                self.assertLessEqual(abs(angle - previous), 1.01)
                self.assertTrue(60 <= angle <= 120)
                previous = angle
            self.assertEqual(angle, boundary)

    def test_small_offset_tracks_slowly_and_center_holds(self):
        for center, direction in ((170, 1), (150, -1)):
            p = PanTracker()
            for i in range(11):
                result = p.update([person(center)], 320, 240, i * .1)
            self.assertEqual(result["status"], "추적 중")
            # A 10px offset was inside the old dead zone. Accumulate small
            # corrections until a whole-degree command reaches the board.
            self.assertEqual(result["command"], f"P{90 + direction}\n")
            self.assertLess(abs(p.angle - 90), 1.1)
            held_angle = p.angle
            for i in range(11, 21):
                result = p.update([person(165)], 320, 240, i * .1)
                self.assertEqual(result["status"], "중앙 유지")
                self.assertEqual(p.angle, held_angle)

    def test_missing_stale_and_invalid_frames_stop(self):
        p = PanTracker()
        p.update([person(280)], 320, 240, 0)
        for detections, width, age in (([], 320, 0), ([person(280)], 320, .5),
                                       ([person(280)], 0, 0)):
            self.assertEqual(p.update(detections, width, 240, .1, age)["command"], "S\n")

    def test_target_lock_and_delayed_reacquisition(self):
        p = PanTracker()
        p.update([person(80, 1)], 320, 240, 0)
        result = p.update([person(80, 1), person(260, 2, 120)], 320, 240, .1)
        self.assertEqual(result["target_id"], 1)
        self.assertEqual(p.update([person(260, 2)], 320, 240, .2)["command"], "S\n")
        self.assertEqual(p.update([person(260, 2)], 320, 240, .7)["target_id"], 2)

    def test_visual_feedback_corrects_wrong_direction_and_centers_target(self):
        for polarity in (-1, 1):
            p = PanTracker()
            reversed_at = None
            for i in range(220):
                # Stationary person; image response to a commanded camera angle.
                center = 240 + polarity * (round(p.angle) - 90) * 8
                result = p.update([person(center)], 320, 240, i * .1)
                if p.direction_corrections and reversed_at is None:
                    reversed_at = i * .1
                    self.assertEqual(result["status"], "오차 증가 감지: 방향 반전")
            self.assertEqual(p.direction_corrections, int(polarity == 1))
            self.assertLessEqual(abs(result["error"]), p.CENTER_TOLERANCE)
            if reversed_at is not None:
                self.assertGreaterEqual(reversed_at, p.CHECK_SETTLE_SECONDS)

    def test_noise_and_single_bad_observation_do_not_reverse(self):
        p = PanTracker()
        for i in range(30):
            center = 265 if i == 15 else 240 + (i % 3 - 1) * 2
            p.update([person(center)], 320, 240, i * .1)
        self.assertFalse(p.reverse)
        self.assertEqual(p.direction_corrections, 0)

    def test_no_movement_at_limit_cannot_establish_wrong_direction(self):
        p = PanTracker()
        p.angle = 120
        for i in range(30):
            result = p.update([person(230 + i)], 320, 240, i * .1)
        self.assertEqual(p.direction_corrections, 0)
        self.assertEqual(result["status"], "회전 한계: 중앙 정렬 미완료")

    def test_missing_or_stale_target_clears_visual_comparison(self):
        for stale in (False, True):
            p = PanTracker()
            for i in range(9):
                p.update([person(240)], 320, 240, i * .1)
            self.assertIsNotNone(p.motion_check)
            p.update([person(270)] if stale else [], 320, 240, .9,
                     frame_age=.5 if stale else 0)
            self.assertIsNone(p.motion_check)
            result = p.update([person(275)], 320, 240, 1)
            self.assertEqual(p.direction_corrections, 0)
            self.assertEqual(result["status"], "추적 중")

    def test_reversal_cooldown_prevents_immediate_flip_back(self):
        p = PanTracker()
        for i in range(30):
            center = 230 if i < 10 else 260
            p.update([person(center)], 320, 240, i * .1)
            if p.direction_corrections:
                break
        self.assertEqual(p.direction_corrections, 1)
        reversed_at = p.last_reversal
        for i in range(1, 40):
            p.update([person(260 + i / 2)], 320, 240, reversed_at + i * .1)
        self.assertEqual(p.direction_corrections, 1)

    def test_new_target_and_center_crossing_start_new_comparison(self):
        for replacement, now in ((person(275, 2), 1.5), (person(80, 1), .9)):
            p = PanTracker()
            for i in range(9):
                p.update([person(240)], 320, 240, i * .1)
            result = p.update([replacement], 320, 240, now)
            self.assertEqual(p.direction_corrections, 0)
            self.assertEqual(p.worsening_frames, 0)
            self.assertEqual(p.motion_check[0], replacement["track_id"])
            self.assertEqual(p.motion_check[3], now)
            self.assertEqual(result["target_id"], replacement["track_id"])

    def test_unidentified_person_does_not_calibrate_direction(self):
        p = PanTracker()
        for i in range(40):
            p.update([person(220 + i, identity=None)], 320, 240, i * .1)
        self.assertEqual(p.direction_corrections, 0)
        self.assertIsNone(p.motion_check)

    def test_native_command_demultiplexing(self):
        source = r'''
#include <assert.h>
#include <string.h>
#include "servo_command.h"
int main(void) {
    servo_command_t parser = {0};
    const char *stream = "E150\nP95\nFT256,250\nS\nB921600\nP999\nP\nP1234\nP-1\nP90\r\nR\n";
    char forwarded[128] = {0};
    unsigned count = 0, angles = 0, stops = 0, resets = 0;
    for (unsigned i = 0; stream[i]; ++i) {
        int result = servo_command_feed(&parser, stream[i]);
        if (!result) forwarded[count++] = stream[i];
        if (result == 2) { ++angles; assert(parser.value == (angles == 1 ? 95 : 90)); }
        if (result == 3) ++stops;
        if (result == 4) ++resets;
    }
    assert(angles == 2 && stops == 1 && resets == 1);
    assert(strcmp(forwarded, "E150\nFT256,250\nB921600\n") == 0);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            c = Path(tmp) / 'check.c'
            binary = Path(tmp) / 'check'
            c.write_text(source)
            subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined',
                            '-I', str(ROOT/'stm32-sg90'), str(c), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()

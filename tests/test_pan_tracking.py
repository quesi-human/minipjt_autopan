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
                self.assertLessEqual(abs(angle - previous), 2.01)
                self.assertTrue(60 <= angle <= 120)
                previous = angle
            self.assertEqual(angle, boundary)

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

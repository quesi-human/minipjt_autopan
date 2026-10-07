"""Native tests for the streaming STM32 camera parser and LD2 deadline."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "camera_frame.h"
int main(int argc, char **argv) {
    camera_frame_t parser = {0};
    unsigned good = 0, bad = 0, index = 0;
    long reset_at = argc > 1 ? strtol(argv[1], 0, 10) : -1;
    assert(!camera_link_recent(0, 0, 0));
    assert(camera_link_recent(1, 100, 100));
    assert(camera_link_recent(1, 100, 2099));
    assert(!camera_link_recent(1, 100, 2100));
    assert(camera_link_recent(1, UINT32_MAX - 100, 50));
    assert(!camera_link_recent(1, UINT32_MAX - 100, 2000));
    int byte;
    while ((byte = getchar()) != EOF) {
        if ((long)index++ == reset_at) camera_frame_reset(&parser);
        int result = camera_frame_feed(&parser, (unsigned char)byte);
        if (result > 0) ++good;
        if (result < 0) ++bad;
    }
    printf("%u %u\n", good, bad);
}
'''


def frame(payload=b'\xff\xd8test\xff\xd9', width=320, height=240):
    return b'ECAM' + struct.pack('<IIIHH', len(payload), zlib.crc32(payload), 0,
                                width, height) + payload


class CameraLinkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        source = Path(cls.tmp.name) / 'check.c'
        cls.binary = Path(cls.tmp.name) / 'check'
        source.write_text(HARNESS)
        subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined', '-I', str(ROOT / 'test_1/Inc'),
                        str(source), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check_stream(self, data, expected, reset_at=None):
        command = [str(self.binary)]
        if reset_at is not None:
            command.append(str(reset_at))
        result = subprocess.run(command, input=data, capture_output=True, check=True)
        self.assertEqual(tuple(map(int, result.stdout.split())), expected)

    def test_boot_logs_do_not_count_as_link(self):
        self.check_stream(b'CAM_READY 320x240\nCAM_ERROR capture_failed\n', (0, 0))

    def test_back_to_back_frames_and_magic_resync(self):
        self.check_stream(b'noiseEE' + frame() + frame(), (2, 0))

    def test_crc_corruption_and_recovery(self):
        bad = bytearray(frame())
        bad[23] ^= 1
        self.check_stream(bytes(bad) + frame(), (1, 1))

    def test_jpeg_markers_required_even_with_valid_crc(self):
        self.check_stream(frame(b'not-jpeg') + frame(), (1, 1))

    def test_invalid_header_size_and_dimensions(self):
        for size in (0, 3, 262145, 0xFFFFFFFF):
            bad = b'ECAM' + struct.pack('<IIIHH', size, 0, 0, 320, 240)
            self.check_stream(bad + frame(), (1, 1))
        self.check_stream(frame(width=0) + frame(), (1, 1))

    def test_payload_larger_than_stm32_ram_streams(self):
        payload = b'\xff\xd8' + bytes(range(256)) * 256 + b'\xff\xd9'
        self.check_stream(frame(payload), (1, 0))

    def test_truncated_frame_does_not_light_led(self):
        self.check_stream(frame()[:-1], (0, 0))

    def test_uart_error_or_gap_reset_recovers(self):
        partial = frame()[:24]
        self.check_stream(partial + frame(), (1, 0), reset_at=len(partial))


if __name__ == '__main__':
    unittest.main()

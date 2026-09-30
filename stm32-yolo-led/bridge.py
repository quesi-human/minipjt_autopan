#!/usr/bin/env python3
"""Poll YOLO HTTP status every 100 ms and send people counts to STM32 VCP."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

import serial


def packet(count, binary=False):
    if type(count) is not int or not 0 <= count <= 65535:
        raise ValueError("person_count must be an integer in 0..65535")
    body = bytes((0xA5, int(binary), count & 255, count >> 8))
    checksum = 0x5A
    for byte in body:
        checksum ^= byte
    return body + bytes((checksum,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--url", default="http://127.0.0.1:8765/status")
    parser.add_argument("--display", choices=("bar", "binary"), default="bar")
    parser.add_argument("--stats", type=Path, default=Path(__file__).with_name("bridge-status.json"))
    args = parser.parse_args()
    binary = args.display == "binary"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    port = serial.Serial()
    port.port, port.baudrate, port.timeout, port.write_timeout = args.port, 115200, 0.02, 0.02
    port.dtr = port.rts = False
    port.open()
    port.reset_input_buffer()
    frame = None
    frame_changed = time.monotonic()
    deadline = time.monotonic()
    logged = 0
    polls = acknowledgements = errors = 0
    intervals = []
    previous_poll = None
    print(f"YOLO → STM32: 100ms, display={args.display}, port={args.port}", flush=True)
    try:
        while True:
            now = time.monotonic()
            if previous_poll is not None:
                intervals.append((now - previous_poll) * 1000)
                intervals = intervals[-100:]
            previous_poll = now
            count, problem = 0, None
            polls += 1
            try:
                with opener.open(args.url, timeout=0.06) as response:
                    status = json.load(response)
                current_frame = status["inference_frames"]
                if current_frame != frame:
                    frame, frame_changed = current_frame, time.monotonic()
                if status.get("error") or status.get("camera_warning"):
                    raise ValueError(status.get("error") or status["camera_warning"])
                if not status.get("yolo_enabled") or not current_frame:
                    raise ValueError("YOLO results unavailable")
                if time.monotonic() - frame_changed > 1:
                    raise ValueError("YOLO frame stale for more than 1s")
                count = status["person_count"]
                packet(count, binary)
            except Exception as error:
                count, problem = 0, str(error)
                errors += 1
            port.write(packet(count, binary))
            cap = min(count, 15 if binary else 4)
            mask = cap if binary else (1 << cap) - 1
            expected = f"ACK {count} {mask}"
            ack = port.readline().decode("ascii", errors="replace").strip()
            if ack == expected:
                acknowledgements += 1
            else:
                problem = f"STM32 ACK mismatch: {ack!r}, expected {expected!r}"
                errors += 1
                port.reset_input_buffer()
            if time.monotonic() - logged >= 1:
                stats = {"person_count": count, "led_mask": mask, "display": args.display,
                         "polls": polls, "acknowledgements": acknowledgements, "errors": errors,
                         "inference_frames": frame, "interval_ms": 100,
                         "mean_poll_interval_ms": round(sum(intervals) / len(intervals), 3) if intervals else None,
                         "error": problem, "updated_at": time.time()}
                args.stats.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
                print(f"people={count}, LEDs={mask:04b}, ACK={ack}, polls={polls}, errors={errors}" +
                      (f", {problem}" if problem else ""), flush=True)
                logged = time.monotonic()
            deadline += 0.1
            if deadline <= time.monotonic():
                deadline += (int((time.monotonic() - deadline) / 0.1) + 1) * 0.1
            time.sleep(max(0, deadline - time.monotonic()))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            port.write(packet(0, binary))
        finally:
            port.close()


if __name__ == "__main__":
    main()

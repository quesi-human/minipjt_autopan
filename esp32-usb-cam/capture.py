"""Receive requested JPEG frames from UsbCamera over USB-UART; no Wi-Fi."""
import argparse
import io
from pathlib import Path
import struct
import time
import zlib

import serial
from PIL import Image


def read_exact(port, count, deadline):
    data = bytearray()
    while len(data) < count:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"수신 시간 초과: {len(data)}/{count} bytes")
        data.extend(port.read(count - len(data)))
    return bytes(data)


def receive_frame(port, timeout):
    deadline = time.monotonic() + timeout
    prefix = bytearray()
    while not prefix.endswith(b"ECAM"):
        prefix.extend(read_exact(port, 1, deadline))
        if b"CAM_ERROR" in prefix and prefix.endswith(b"\n"):
            raise RuntimeError(prefix.decode(errors="replace").strip())
        if len(prefix) > 4096:
            del prefix[:-1024]
    size, checksum, sequence, width, height = struct.unpack(
        "<IIIHH", read_exact(port, 16, deadline)
    )
    if not 4 <= size <= 256 * 1024:
        raise ValueError(f"잘못된 프레임 길이: {size}")
    jpeg = read_exact(port, size, deadline)
    if zlib.crc32(jpeg) != checksum:
        raise ValueError("프레임 CRC 불일치: 시리얼 전송 속도/케이블을 확인하세요")
    with Image.open(io.BytesIO(jpeg)) as image:
        image.load()
        if image.format != "JPEG" or image.size != (width, height):
            raise ValueError("JPEG 형식/해상도가 헤더와 다릅니다")
    return jpeg, sequence, width, height


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=921600,
                        choices=(115200, 230400, 460800, 921600, 1500000, 2000000))
    parser.add_argument("--frames", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--output", type=Path, default=Path("captures"))
    parser.add_argument("--preview", action="store_true", help="OpenCV 실시간 표시 (q로 종료)")
    parser.add_argument("--no-save", action="store_true", help="미리보기 중 JPEG 파일 저장 생략")
    parser.add_argument("--reset", action="store_true", help="RTS로 보드를 리셋한 뒤 수신 (자동 리셋 지원 어댑터)")
    parser.add_argument("--quiet", action="store_true", help="프레임별 로그 생략, 최종 FPS만 출력")
    parser.add_argument("--chunk", type=int, default=64, choices=(32, 64, 128, 256))
    parser.add_argument("--gap-us", type=int, default=1000)
    args = parser.parse_args()
    if args.frames < 1 or args.timeout <= 0:
        parser.error("frames와 timeout은 양수여야 합니다")
    if not 0 <= args.gap_us <= 5000:
        parser.error("gap-us는 0~5000이어야 합니다")
    cv2 = np = None
    if args.preview:
        import cv2
        import numpy as np
        cv2.namedWindow("ESP32-CAM USB", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("ESP32-CAM USB", 960, 720)
    if not args.no_save:
        args.output.mkdir(parents=True, exist_ok=True)
    port = serial.Serial()
    port.port, port.baudrate, port.timeout = args.port, 115200, 0.2
    port.dtr = port.rts = False
    port.open()
    try:
        if args.reset:
            port.rts = True
            time.sleep(0.1)
            port.rts = False
        time.sleep(2)
        port.reset_input_buffer()
        port.write(f"T{args.chunk},{args.gap_us}\n".encode())
        port.flush()
        deadline = time.monotonic() + 5
        expected = f"TRANSFER {args.chunk} {args.gap_us}".encode()
        while port.readline().strip() != expected:
            if time.monotonic() >= deadline:
                raise TimeoutError("전송 설정 응답 없음: 보드 리셋과 최신 펌웨어를 확인하세요")
        if args.baud != 115200:
            port.write(f"B{args.baud}\n".encode())
            port.flush()
            deadline = time.monotonic() + 5
            expected = f"BAUD {args.baud}".encode()
            while port.readline().strip() != expected:
                if time.monotonic() >= deadline:
                    raise TimeoutError("baud 변경 응답 없음: 보드 리셋과 최신 펌웨어를 확인하세요")
            port.baudrate = args.baud
            time.sleep(0.1)
        print(f"연결 속도: {args.baud} baud", flush=True)
        start = time.monotonic()
        received = 0
        total_bytes = 0
        dropped = 0
        consecutive_drops = 0
        for index in range(args.frames):
            port.write(b"F")
            port.flush()
            try:
                jpeg, sequence, width, height = receive_frame(
                    port, min(args.timeout, 2) if args.preview else args.timeout
                )
            except (TimeoutError, ValueError) as error:
                if not args.preview:
                    raise
                dropped += 1
                consecutive_drops += 1
                print(f"프레임 건너뜀 ({dropped}): {error}", flush=True)
                port.reset_input_buffer()
                if consecutive_drops >= 5:
                    raise RuntimeError("연속 5프레임 수신 실패: 케이블과 전송 설정을 확인하세요")
                continue
            consecutive_drops = 0
            path = args.output / f"frame_{index:04d}.jpg"
            if not args.no_save:
                path.write_bytes(jpeg)
            received += 1
            total_bytes += len(jpeg)
            if not args.quiet or received == 1 or received % 300 == 0:
                print(f"seq={sequence}, {width}x{height}, {len(jpeg)} bytes, CRC/JPEG 정상" +
                      (f", 저장: {path}" if not args.no_save else ""), flush=True)
            if args.preview:
                frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                fps = received / (time.monotonic() - start)
                cv2.putText(frame, f"{fps:.1f} FPS | dropped {dropped}", (5, 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
                cv2.imshow("ESP32-CAM USB", frame)
                if cv2.waitKey(1) & 0xff == ord("q"):
                    break
        elapsed = time.monotonic() - start
        average_bytes = total_bytes / received if received else 0
        print(f"수신 완료: {received} frames, {elapsed:.2f}초, {received / elapsed:.2f} FPS, "
              f"평균 {average_bytes:.0f} bytes/frame, 버린 프레임 {dropped}", flush=True)
    finally:
        port.close()
        if args.preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("수신 종료")
    except (serial.SerialException, TimeoutError, ValueError, RuntimeError, OSError) as error:
        raise SystemExit(f"수신 실패: {error}")

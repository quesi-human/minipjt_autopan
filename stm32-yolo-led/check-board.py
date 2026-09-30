"""Validate actual STM32 UART acknowledgements, LED masks and timeout."""
import json
import argparse
from pathlib import Path
import time
import serial
from bridge import packet

results = []
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', default='/dev/ttyACM0')
args = parser.parse_args()
with serial.Serial(args.port, 115200, timeout=0.3) as port:
    port.reset_input_buffer()
    for binary in (False, True):
        for count in (0, 1, 2, 3, 4, 7, 15, 16, 65535):
            cap = min(count, 15 if binary else 4)
            mask = cap if binary else (1 << cap) - 1
            port.write(packet(count, binary))
            ack = port.readline().decode().strip()
            assert ack == f'ACK {count} {mask}', (count, binary, ack)
            results.append({'count': count, 'binary': binary, 'ack': ack})
    bad = bytearray(packet(4))
    bad[-1] ^= 1
    port.write(bad)
    assert port.readline() == b'', 'Corrupt packet unexpectedly acknowledged'
    port.write(b'?')
    assert port.readline().strip() == b'ACK 65535 15', 'Corrupt packet changed LEDs'
    time.sleep(1.1)
    port.write(b'?')
    assert port.readline().strip() == b'ACK 0 0', 'Timeout did not clear LEDs'
Path(__file__).with_name('board-validation.json').write_text(json.dumps(
    {'cases': results, 'checksum_rejection': True, 'timeout_clears_leds': True}, indent=2) + '\n')
print('PASS: 18 count/mode cases, corrupt checksum rejection, 1s timeout clears LEDs')

"""Check current HTTP center coordinates; save a live person result when present."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:8766/status')
parser.add_argument('--wait-seconds', type=float, default=20)
args = parser.parse_args()
if args.wait_seconds < 0:
    parser.error('wait-seconds must be nonnegative')
deadline = time.monotonic() + args.wait_seconds
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
while True:
    with opener.open(args.url, timeout=2) as response:
        status = json.load(response)
    target = status['closest_person']
    assert status['error'] is None and status['camera_warning'] is None, status
    if target is not None:
        assert status['person_count'] > 0
        assert status['closest_person_x'] == target['center_x']
        assert target['center_x'] == (target['xyxy'][0]+target['xyxy'][2])/2
        assert 0 <= target['center_x'] <= status['frame_width']
        assert target['track_id'] in [item['track_id'] for item in status['detections']]
        output = Path(__file__).with_name('captures')
        output.mkdir(parents=True, exist_ok=True)
        output.joinpath('closest-person-live.json').write_text(
            json.dumps(status, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({'person_count':status['person_count'], 'closest_person':target}, indent=2))
        break
    assert status['closest_person_x'] is None
    if time.monotonic() >= deadline:
        print('PASS: live API available, normal camera image, no person currently detected; center=null')
        break
    time.sleep(0.1)

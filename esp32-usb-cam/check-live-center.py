"""Check current HTTP center coordinates; save a live person result when present."""
import json
from pathlib import Path
import time
import urllib.request

deadline = time.monotonic() + 20
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
while True:
    with opener.open('http://127.0.0.1:8765/status', timeout=2) as response:
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

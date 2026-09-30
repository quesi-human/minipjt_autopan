"""Verify nearest-box selection and stable tracking on the YOLO example image."""
import json
from pathlib import Path
import cv2
import numpy as np
import ultralytics
from person_detector import PersonDetector

detector = PersonDetector(Path(__file__).parent / 'models/yolo11n.pt')
source = Path(ultralytics.__file__).parent / 'assets/bus.jpg'
frame = cv2.resize(cv2.imread(str(source)), (320, 240))
success, encoded = cv2.imencode('.jpg', frame)
assert success
_, first, _ = detector.detect(encoded.tobytes())
first_target = detector.closest_person
assert first_target is not None
annotated, second, _ = detector.detect(encoded.tobytes())
target = detector.closest_person
assert target['track_id'] is not None and target['track_id'] == first_target['track_id']
assert target['bbox_area'] == max((b['xyxy'][2]-b['xyxy'][0])*(b['xyxy'][3]-b['xyxy'][1]) for b in second)
assert target['center_x'] == (target['xyxy'][0]+target['xyxy'][2])/2
output = Path(__file__).parent / 'captures'
output.mkdir(parents=True, exist_ok=True)
(output / 'closest-person-validation.jpg').write_bytes(annotated)
report = {'frame_width':320, 'frame_height':240, 'person_count':len(second),
          'closest_person_x':target['center_x'], 'closest_person':target}
_, empty, _ = detector.detect(cv2.imencode('.jpg', np.zeros((240,320,3), dtype=np.uint8))[1].tobytes())
assert empty == [] and detector.closest_person is None
report['empty_frame_clears_target'] = True
(output / 'closest-person-validation.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))

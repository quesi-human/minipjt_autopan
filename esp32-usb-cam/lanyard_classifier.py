"""Conservative lanyard-color estimate from the upper torso, without identity inference."""
import cv2
import numpy as np


def _has_strip(mask, person_width, person_height):
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    for x, y, width, height, area in stats[1:count]:
        if (height >= max(10, person_height * 0.10) and
                width <= max(8, person_width * 0.16) and
                height >= width * 2 and area >= 8):
            return True
    return False


def classify_lanyard(frame, box):
    result = {"role": "unknown", "role_label": "미확인", "lanyard_color": "unknown"}
    x1, y1, x2, y2 = box
    image_height, image_width = frame.shape[:2]
    # A cropped body box has no reliable neck position.
    if x1 < 0 or y1 < 0 or x2 > image_width or y2 > image_height:
        return result
    width, height = x2 - x1, y2 - y1
    if width < 35 or height < 100:
        return result
    torso = frame[y1 + int(height * .16):y1 + int(height * .50),
                  x1 + int(width * .22):x1 + int(width * .78)]
    if not torso.size:
        return result
    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    sky = cv2.inRange(hsv, np.array([85, 40, 95]), np.array([115, 230, 255]))
    gray = cv2.cvtColor(torso, cv2.COLOR_BGR2GRAY)
    kernel_size = max(9, int(width * .25) | 1)
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT,
                              np.ones((kernel_size, kernel_size), np.uint8))
    # Dark clothing alone is insufficient: require a thin dark contrasting strip.
    dark = np.where((hsv[:, :, 2] < 70) & (blackhat > 25), 255, 0).astype(np.uint8)
    sky_seen = _has_strip(sky, width, height)
    dark_seen = _has_strip(dark, width, height)
    if sky_seen and not dark_seen:
        return {"role": "student", "role_label": "학생", "lanyard_color": "sky_blue"}
    if dark_seen and not sky_seen:
        return {"role": "staff", "role_label": "직원", "lanyard_color": "black"}
    return result

"""Estimate nearest person by bounding-box area in a monocular image."""


def select_closest_person(detections, frame_width, frame_height):
    candidates = []
    for detection in detections:
        x1, y1, x2, y2 = detection["xyxy"]
        x1, x2 = max(0, x1), min(frame_width, x2)
        y1, y2 = max(0, y1), min(frame_height, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
        candidates.append({**detection, "xyxy": [x1, y1, x2, y2],
                           "center_x": center_x, "center_y": center_y,
                           "center_x_normalized": center_x / frame_width,
                           "bbox_area": (x2 - x1) * (y2 - y1)})
    return max(candidates, key=lambda item: item["bbox_area"], default=None)

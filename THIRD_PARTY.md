# Third-party components

- YOLO11n pretrained weights (`models/yolo11n.pt`) and the Python inference dependency come from [Ultralytics](https://github.com/ultralytics/ultralytics). Refer to the upstream [license](https://github.com/ultralytics/ultralytics/blob/main/LICENSE) and model documentation for applicable terms.
- Raspberry Pi camera access uses [Picamera2](https://github.com/raspberrypi/picamera2) and libcamera, installed through Raspberry Pi OS apt packages.
- Python dependencies are declared in `raspberry_pi/requirements.txt`; installed package directories are not included.

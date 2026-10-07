# Third-party components

- YOLO11m (`models/yolo11m.pt`) and YOLO11n (`models/yolo11n.pt`) pretrained weights and Python inference come from [Ultralytics](https://github.com/ultralytics/ultralytics). YOLO11m was downloaded from the [official assets release](https://github.com/ultralytics/assets/releases/tag/v8.4.0). Refer to the upstream [license](https://github.com/ultralytics/ultralytics/blob/main/LICENSE) and model documentation.
- ESP32 firmware uses [Arduino-ESP32](https://github.com/espressif/arduino-esp32) and [esp32-camera](https://github.com/espressif/esp32-camera).
- The STM32 linker script originated from STM32CubeIDE generated support; its original copyright notice is retained. The F103 startup and polling relay are project code.
- The separate Raspberry Pi implementation uses [Picamera2](https://github.com/raspberrypi/picamera2) and libcamera, installed through Raspberry Pi OS apt packages.
- Python dependencies are declared in `esp32-usb-cam/requirements*.txt` and `raspberry_pi/requirements.txt`. Installed packages and generated firmware are excluded from Git.

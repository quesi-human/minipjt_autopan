"""CSI camera adapter. RGB888 capture arrays are BGR, as OpenCV expects."""


def camera_info():
    from picamera2 import Picamera2
    return Picamera2.global_camera_info()


class PiCamera:
    def __init__(self, camera_num=0, width=640, height=480, fps=30):
        from picamera2 import Picamera2

        self.camera = None
        cameras = camera_info()
        if not cameras:
            raise RuntimeError("카메라가 없습니다. CAM/DISP 0 케이블과 rpicam-hello --list-cameras를 확인하세요")
        if camera_num not in range(len(cameras)):
            raise ValueError(f"카메라 인덱스 {camera_num} 없음: {cameras}")
        self.info = cameras[camera_num]
        self.camera = Picamera2(camera_num)
        try:
            config = self.camera.create_video_configuration(
                main={"size": (width, height), "format": "RGB888"},
                controls={"FrameRate": fps}, buffer_count=4, queue=False)
            self.camera.configure(config)
            self.camera.start()
        except BaseException:
            self.camera.close()
            self.camera = None
            raise

    def read(self):
        return self.camera.capture_array("main")

    def close(self):
        if self.camera is not None:
            try:
                self.camera.stop()
            finally:
                self.camera.close()
                self.camera = None

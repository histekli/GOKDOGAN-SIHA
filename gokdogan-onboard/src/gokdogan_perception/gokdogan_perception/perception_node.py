"""Algı düğümü (SAD §10): kamera → inference → /perception/detections.

source:=synthetic|video|gazebo|usb, backend:=mock|onnxruntime|tensorrt (⚠️ tensorrt/usb ON-DEVICE).
YOLO her N karede (SAD: 5). Kritik döngüyü bloklamamak için ayrı callback group.
"""
import rclpy
from rclpy.node import Node

from gokdogan_msgs.msg import Detections, BBox
from gokdogan_common import qos
from gokdogan_perception.camera import make_camera
from gokdogan_perception.inference import make_detector


class PerceptionNode(Node):
    def __init__(self):
        super().__init__("perception")
        self.declare_parameter("source", "synthetic")
        self.declare_parameter("backend", "mock")
        self.declare_parameter("fps", 50.0)
        self.declare_parameter("roi_frac", 0.7)
        self.declare_parameter("yolo_every_n", 5)
        self.declare_parameter("model_path", "")
        self.declare_parameter("conf", 0.35)      # YOLO güven eşiği (sim primitifi için düşür: ~0.12)
        self.declare_parameter("iou", 0.45)       # NMS IoU eşiği

        source = self.get_parameter("source").value
        backend = self.get_parameter("backend").value
        self._n = int(self.get_parameter("yolo_every_n").value)
        self._i = 0

        self._detector = make_detector(
            backend, roi_frac=float(self.get_parameter("roi_frac").value),
            model_path=self.get_parameter("model_path").value,
            conf=float(self.get_parameter("conf").value),
            iou=float(self.get_parameter("iou").value))

        self._pub = self.create_publisher(Detections, "/perception/detections", qos.detections())

        self._cam = None
        self._sub_img = None
        if source in ("synthetic", "video"):
            self._cam = make_camera(source, fps=float(self.get_parameter("fps").value),
                                    path=self.get_parameter("model_path").value)
            dt = 1.0 / float(self.get_parameter("fps").value)
            self.create_timer(dt, self._tick)
        elif source == "gazebo":
            from sensor_msgs.msg import Image
            self.create_subscription(Image, "/camera/image", self._on_image, qos.sensor_stream())
        elif source == "usb":
            raise RuntimeError("usb kaynağı ⚠️ ON-DEVICE (GStreamer v4l2src) — x86 dev'de synthetic/video kullanın")
        self.get_logger().info(f"perception: source={source} backend={backend}")

    def _tick(self):
        frame, _gt = self._cam.read()
        if frame is None:                  # sentetik senaryo bitti → yeniden başlat (dev döngü)
            self._cam = make_camera(self.get_parameter("source").value,
                                    fps=float(self.get_parameter("fps").value))
            return
        self._process(frame)

    def _on_image(self, msg):
        frame = self._to_bgr(msg)
        if frame is not None:
            self._process(frame)

    def _to_bgr(self, msg):
        """ROS Image → BGR ndarray. cv_bridge varsa onu kullan; yoksa manuel numpy
        (Gazebo/dev'de cv_bridge olmayabilir → taşınabilir). rgb8/bgr8 destekli."""
        try:
            from cv_bridge import CvBridge
            return CvBridge().imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception:  # noqa: BLE001 — cv_bridge yok → manuel yola düş
            pass
        try:
            import numpy as np
            img = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(
                msg.height, msg.width, 3)
            if (msg.encoding or "rgb8").lower() == "rgb8":
                img = img[:, :, ::-1]           # RGB→BGR
            return np.ascontiguousarray(img)
        except Exception as e:  # noqa: BLE001
            self.get_logger().warn(f"görüntü dönüştürme hatası: {e}")
            return None

    def _process(self, frame):
        self._i += 1
        if self._i % self._n != 0:         # YOLO her N karede
            return
        try:
            dets = self._detector.detect(frame)
        except Exception as e:  # noqa: BLE001
            self.get_logger().warn(f"inference hatası (kare atlandı): {e}")
            return
        msg = Detections()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "camera"
        for (cx, cy, w, h, score) in dets:
            b = BBox()
            b.x = float(cx - w / 2.0)
            b.y = float(cy - h / 2.0)
            b.w = float(w)
            b.h = float(h)
            b.score = float(score)
            b.track_id = -1
            b.stamp = msg.header.stamp
            msg.boxes.append(b)
        self._pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = PerceptionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

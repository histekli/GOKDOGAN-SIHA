"""Kilit denetimi düğümü (SAD §7/§12): /perception/tracks + /aircraft/state → /lock/event.

5 kural + zaman penceresi + last_locked_id. Canlı progress (GCS aynası) + geçerlilik yayınlar.
"""
import rclpy
from rclpy.node import Node

from gokdogan_msgs.msg import Tracks, LockEvent, BBox
from gokdogan_msgs.msg import AircraftState
from gokdogan_common import qos
from gokdogan_lock_validator.lock_rules import Box, LockParams, LockValidator


class LockValidatorNode(Node):
    def __init__(self):
        super().__init__("lock_validator")
        # Kilit parametreleri (config'ten override edilebilir)
        self.declare_parameter("lock_w_frac", 0.5)
        self.declare_parameter("lock_h_frac", 0.5)
        self.declare_parameter("size_min_frac", 0.06)
        self.declare_parameter("containment_min", 0.90)
        self.declare_parameter("window_s", 5.0)
        self.declare_parameter("valid_s", 4.0)
        self.declare_parameter("tolerance_s", 0.2)
        self.declare_parameter("min_lock_alt_m", 5.0)

        p = LockParams(
            lock_w_frac=float(self.get_parameter("lock_w_frac").value),
            lock_h_frac=float(self.get_parameter("lock_h_frac").value),
            size_min_frac=float(self.get_parameter("size_min_frac").value),
            containment_min=float(self.get_parameter("containment_min").value),
            window_s=float(self.get_parameter("window_s").value),
            valid_s=float(self.get_parameter("valid_s").value),
            tolerance_s=float(self.get_parameter("tolerance_s").value),
            min_lock_alt_m=float(self.get_parameter("min_lock_alt_m").value))
        self._val = LockValidator(p=p)

        self._alt = 0.0
        self._autonomous = False

        self.create_subscription(AircraftState, "/aircraft/state", self._on_state,
                                 qos.sensor_stream())
        self.create_subscription(Tracks, "/perception/tracks", self._on_tracks,
                                 qos.sensor_stream())
        self._pub = self.create_publisher(LockEvent, "/lock/event", qos.lock_event())

    def _on_state(self, msg):
        self._alt = float(msg.alt)
        self._autonomous = bool(msg.is_autonomous)

    def _on_tracks(self, msg):
        sel = msg.selected_id
        if sel < 0:
            return
        tr = next((t for t in msg.tracks if t.id == sel), None)
        if tr is None:
            return
        b = tr.box
        box = Box(b.x, b.y, b.w, b.h)
        t = self.get_clock().now().nanoseconds * 1e-9
        r = self._val.process(t, sel, box, self._alt, self._autonomous)

        ev = LockEvent()
        ev.valid = bool(r.valid)
        ev.target_id = int(sel)
        ev.box = b
        ev.center = [float(box.cx), float(box.cy)]
        ev.progress_s = float(r.progress_s)
        ev.lock_end_time = self.get_clock().now().to_msg()
        self._pub.publish(ev)
        if r.valid:
            self.get_logger().info(f"GEÇERLİ KİLİT ✅ hedef={sel} (progress {r.progress_s:.1f}s)")


def main(args=None):
    rclpy.init(args=args)
    node = LockValidatorNode()
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

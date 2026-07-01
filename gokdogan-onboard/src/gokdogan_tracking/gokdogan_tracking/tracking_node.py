"""Takip düğümü (SAD §10): /perception/detections → Kalman/Hungarian → /perception/tracks + selected_bbox."""
import rclpy
from rclpy.node import Node

from gokdogan_msgs.msg import Detections, Tracks, Track, BBox
from gokdogan_common import qos
from gokdogan_tracking.tracker import MultiTracker


class TrackingNode(Node):
    def __init__(self):
        super().__init__("tracking")
        self.declare_parameter("iou_gate", 0.3)
        self.declare_parameter("max_age", 15)
        self.declare_parameter("select_policy", "largest")
        self._trk = MultiTracker(
            iou_gate=float(self.get_parameter("iou_gate").value),
            max_age=int(self.get_parameter("max_age").value))
        self._policy = self.get_parameter("select_policy").value
        self._last_t = None

        self.create_subscription(Detections, "/perception/detections", self._on_det,
                                 qos.detections())
        self._pub_tracks = self.create_publisher(Tracks, "/perception/tracks", qos.sensor_stream())
        self._pub_sel = self.create_publisher(BBox, "/perception/selected_bbox", qos.sensor_stream())

    def _on_det(self, msg):
        now = self.get_clock().now().nanoseconds * 1e-9
        dt = 0.1 if self._last_t is None else max(1e-3, now - self._last_t)
        self._last_t = now
        dets = [(b.x + b.w / 2.0, b.y + b.h / 2.0, b.w, b.h, b.score) for b in msg.boxes]
        tracks = self._trk.update(dets, dt)
        sel = self._trk.select_target(self._policy)

        out = Tracks()
        out.header = msg.header
        out.selected_id = sel
        for tr in tracks:
            t = Track()
            t.id = tr.id
            cx, cy, w, h = tr.box
            t.box = self._bbox(cx, cy, w, h, tr.score, tr.id, msg)
            t.vx, t.vy = [float(v) for v in tr.kf.vel]
            t.age = float(tr.age)
            t.predicted = bool(tr.predicted)
            out.tracks.append(t)
            if tr.id == sel:
                self._pub_sel.publish(t.box)
        self._pub_tracks.publish(out)

    @staticmethod
    def _bbox(cx, cy, w, h, score, tid, msg):
        b = BBox()
        b.x = float(cx - w / 2.0)
        b.y = float(cy - h / 2.0)
        b.w = float(w)
        b.h = float(h)
        b.score = float(score)
        b.track_id = int(tid)
        b.stamp = msg.header.stamp
        return b


def main(args=None):
    rclpy.init(args=args)
    node = TrackingNode()
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

"""GÖKDOĞAN mavlink_iface — /aircraft/state derleyici (SAD §5/§8).

MAVROS topic'lerinden (state, global_position, imu, battery) birleşik AircraftState
üretir (20Hz). Downstream (guidance, GCS aynası) tek topic'ten okur.
Attitude ENU (REP-103) olarak yayınlanır; ENU↔NED dönüşümü tüketicide frames ile yapılır.
"""
import math

import rclpy
from rclpy.node import Node

from mavros_msgs.msg import State
from sensor_msgs.msg import NavSatFix, Imu
from geometry_msgs.msg import TwistStamped
from std_msgs.msg import Float64
from sensor_msgs.msg import BatteryState

from gokdogan_msgs.msg import AircraftState
from gokdogan_common import qos

_AUTONOMOUS_MODES = {"GUIDED", "AUTO", "RTL", "LOITER", "TAKEOFF", "LAND", "QRTL"}


def _quat_to_euler(x, y, z, w):
    """Quaternion → (roll, pitch, yaw) rad."""
    t0 = 2.0 * (w * x + y * z)
    t1 = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(t0, t1)
    t2 = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
    pitch = math.asin(t2)
    t3 = 2.0 * (w * z + x * y)
    t4 = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(t3, t4)
    return roll, pitch, yaw


class AircraftStateNode(Node):
    def __init__(self):
        super().__init__("aircraft_state")
        self.declare_parameter("publish_rate_hz", 20.0)

        self._state = State()
        self._fix = None
        self._rel_alt = 0.0
        self._imu = None
        self._vel = None
        self._batt = 100.0

        self.create_subscription(State, "/mavros/state", self._on_state, 10)
        self.create_subscription(NavSatFix, "/mavros/global_position/global",
                                 self._on_fix, qos.sensor_stream())
        self.create_subscription(Float64, "/mavros/global_position/rel_alt",
                                 self._on_alt, qos.sensor_stream())
        self.create_subscription(Imu, "/mavros/imu/data", self._on_imu, qos.sensor_stream())
        self.create_subscription(TwistStamped, "/mavros/local_position/velocity_local",
                                 self._on_vel, qos.sensor_stream())
        self.create_subscription(BatteryState, "/mavros/battery",
                                 self._on_batt, qos.sensor_stream())

        self._pub = self.create_publisher(AircraftState, "/aircraft/state", qos.sensor_stream())
        dt = 1.0 / float(self.get_parameter("publish_rate_hz").value)
        self.create_timer(dt, self._publish)

    def _on_state(self, m): self._state = m
    def _on_fix(self, m): self._fix = m
    def _on_alt(self, m): self._rel_alt = m.data
    def _on_imu(self, m): self._imu = m
    def _on_vel(self, m): self._vel = m

    def _on_batt(self, m):
        # MAVROS battery percentage 0..1 (varsa) → 0..100
        if m.percentage is not None and m.percentage >= 0.0:
            self._batt = m.percentage * 100.0

    def _publish(self):
        msg = AircraftState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "map"
        if self._fix is not None:
            msg.lat = self._fix.latitude
            msg.lon = self._fix.longitude
        msg.alt = float(self._rel_alt)
        if self._imu is not None:
            q = self._imu.orientation
            roll, pitch, yaw = _quat_to_euler(q.x, q.y, q.z, q.w)
            msg.roll, msg.pitch, msg.yaw = roll, pitch, yaw
        if self._vel is not None:
            v = self._vel.twist.linear
            msg.vground = math.sqrt(v.x * v.x + v.y * v.y)
            msg.vair = msg.vground  # SITL: airspeed≈groundspeed; gerçek uçakta ARSPD ayrı
        msg.batt = float(self._batt)
        msg.mode = self._state.mode
        msg.armed = bool(self._state.armed)
        msg.is_autonomous = self._state.mode in _AUTONOMOUS_MODES
        self._pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = AircraftStateNode()
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

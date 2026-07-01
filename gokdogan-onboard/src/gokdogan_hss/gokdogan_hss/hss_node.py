"""HSS kaçınma düğümü (SAD §13): /server/hss + /aircraft/state + /target/selected → APF setpoint.

TEK-YAZICI: yalnız active_service==SVC_HSS iken yazar (FSM acil kaçınmada HSS'e öncelik verir).
APF ile hedefe ilerlerken HSS yarıçapını ASLA ihlal etmez (0 ihlal). Lookahead pozisyon setpoint'i.
"""
import rclpy
from rclpy.node import Node

from mavros_msgs.msg import GlobalPositionTarget
from gokdogan_msgs.msg import HssList, AircraftState, Target, MissionMode
from gokdogan_common import qos
from gokdogan_guidance import geo
from gokdogan_hss.apf import ApfParams, ApfPlanner


class HssNode(Node):
    def __init__(self):
        super().__init__("hss")
        self.declare_parameter("k_att", 0.8)
        self.declare_parameter("k_rep", 12.0)
        self.declare_parameter("hss_margin_m", 25.0)
        self.declare_parameter("v_max", 10.0)
        self.declare_parameter("lookahead_s", 3.0)
        self.declare_parameter("control_rate_hz", 10.0)
        p = ApfParams(
            k_att=float(self.get_parameter("k_att").value),
            k_rep=float(self.get_parameter("k_rep").value),
            hss_margin_m=float(self.get_parameter("hss_margin_m").value),
            v_max=float(self.get_parameter("v_max").value))
        self._planner = ApfPlanner(p=p)

        self._hss = []
        self._own = None
        self._goal = None
        self._active = False
        self._speed = 0.0

        self.create_subscription(HssList, "/server/hss", self._on_hss, qos.server_data())
        self.create_subscription(AircraftState, "/aircraft/state", self._on_state,
                                 qos.sensor_stream())
        self.create_subscription(Target, "/target/selected", self._on_target,
                                 qos.target_selected())
        self.create_subscription(MissionMode, "/mission/mode", self._on_mode, qos.mission_mode())
        self._pub = self.create_publisher(
            GlobalPositionTarget, "/mavros/setpoint_raw/global", qos.sensor_stream())
        self.create_timer(1.0 / float(self.get_parameter("control_rate_hz").value), self._control)

    def _on_hss(self, msg):
        self._hss = [(z.enlem, z.boylam, z.yaricap) for z in msg.zones]

    def _on_state(self, msg):
        self._own = msg
        self._speed = float(msg.vground)

    def _on_target(self, msg):
        self._goal = (msg.lead_lat, msg.lead_lon)

    def _on_mode(self, msg):
        self._active = (msg.active_service == MissionMode.SVC_HSS)

    def _control(self):
        # TEK-YAZICI: yalnız HSS aktif servisken (§13 tahkim)
        if not self._active or self._own is None or self._goal is None:
            return
        ref_lat, ref_lon = self._own.lat, self._own.lon
        pos = (0.0, 0.0)   # kendi konumumuz yerel orijin
        goal_n, goal_e = geo.ll_to_ned(self._goal[0], self._goal[1], ref_lat, ref_lon)
        # HSS'leri yerel NED'e çevir (APF x=north, y=east)
        hss_xy = [(*geo.ll_to_ned(hlat, hlon, ref_lat, ref_lon), r)
                  for (hlat, hlon, r) in self._hss]
        vx, vy = self._planner.step(pos, (goal_n, goal_e), hss_xy, self._speed)
        # Lookahead pozisyon (yerel) → lat/lon
        la = float(self.get_parameter("lookahead_s").value)
        tgt_n, tgt_e = pos[0] + vx * la, pos[1] + vy * la
        lat, lon = geo.ned_to_ll(tgt_n, tgt_e, ref_lat, ref_lon)

        sp = GlobalPositionTarget()
        sp.header.stamp = self.get_clock().now().to_msg()
        sp.coordinate_frame = GlobalPositionTarget.FRAME_GLOBAL_REL_ALT
        sp.type_mask = (
            GlobalPositionTarget.IGNORE_VX | GlobalPositionTarget.IGNORE_VY
            | GlobalPositionTarget.IGNORE_VZ | GlobalPositionTarget.IGNORE_AFX
            | GlobalPositionTarget.IGNORE_AFY | GlobalPositionTarget.IGNORE_AFZ
            | GlobalPositionTarget.IGNORE_YAW | GlobalPositionTarget.IGNORE_YAW_RATE)
        sp.latitude = float(lat)
        sp.longitude = float(lon)
        sp.altitude = float(self._own.alt)
        self._pub.publish(sp)


def main(args=None):
    from rclpy.executors import ExternalShutdownException
    rclpy.init(args=args)
    node = HssNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

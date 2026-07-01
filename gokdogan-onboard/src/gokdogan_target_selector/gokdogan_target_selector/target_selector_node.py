"""Hedef seçimi düğümü (SAD §11): opponents+hss+aircraft_state → /target/selected.

S = 0.40·mesafe + 0.30·açı + 0.20·geçmiş − 0.10·risk. Ağırlıklar param (GCS override).
"""
import math

import rclpy
from rclpy.node import Node

from gokdogan_msgs.msg import Opponents, HssList, AircraftState, Target
from gokdogan_common import qos
from gokdogan_target_selector.selector import (
    Opponent, OwnState, Weights, SelectorParams, select_target,
)


class TargetSelectorNode(Node):
    def __init__(self):
        super().__init__("target_selector")
        self.declare_parameter("rate_hz", 2.0)
        self.declare_parameter("w_mesafe", 0.40)
        self.declare_parameter("w_aci", 0.30)
        self.declare_parameter("w_gecmis", 0.20)
        self.declare_parameter("w_risk", 0.10)
        self.declare_parameter("d_ref_m", 1000.0)

        self._opps = []
        self._hss = []
        self._own = None

        self.create_subscription(Opponents, "/server/opponents", self._on_opp, qos.server_data())
        self.create_subscription(HssList, "/server/hss", self._on_hss, qos.server_data())
        self.create_subscription(AircraftState, "/aircraft/state", self._on_state,
                                 qos.sensor_stream())
        self._pub = self.create_publisher(Target, "/target/selected", qos.target_selected())
        self.create_timer(1.0 / float(self.get_parameter("rate_hz").value), self._tick)

    def _on_opp(self, msg):
        self._opps = [Opponent(
            takim_no=o.takim_no, lat=o.enlem, lon=o.boylam, alt=o.irtifa,
            heading_rad=math.radians(o.yonelme), speed=o.hiz, zaman_farki=o.zaman_farki)
            for o in msg.opponents]

    def _on_hss(self, msg):
        self._hss = [(z.enlem, z.boylam, z.yaricap) for z in msg.zones]

    def _on_state(self, msg):
        self._own = OwnState(lat=msg.lat, lon=msg.lon, speed=msg.vground, heading_rad=msg.yaw)

    def _tick(self):
        if self._own is None or not self._opps:
            return
        w = Weights(
            mesafe=float(self.get_parameter("w_mesafe").value),
            aci=float(self.get_parameter("w_aci").value),
            gecmis=float(self.get_parameter("w_gecmis").value),
            risk=float(self.get_parameter("w_risk").value))
        p = SelectorParams(d_ref_m=float(self.get_parameter("d_ref_m").value))
        sel = select_target(self._own, self._opps, self._hss, w, p)
        if sel is None:
            return
        t = Target()
        t.takim_no = int(sel.opponent.takim_no)
        t.lat = float(sel.opponent.lat)
        t.lon = float(sel.opponent.lon)
        t.alt = float(sel.opponent.alt)
        t.lead_lat = float(sel.lead_lat)
        t.lead_lon = float(sel.lead_lon)
        t.score = float(sel.score)
        self._pub.publish(t)


def main(args=None):
    rclpy.init(args=args)
    node = TargetSelectorNode()
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

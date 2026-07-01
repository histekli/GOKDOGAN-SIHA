#!/usr/bin/env python3
"""HSS SITL probe (Kabul Kapısı 5): copter'ın konumuna göre HSS bölgesi + hedef enjekte eder,
APF kaçınmasının HSS yarıçapını ASLA ihlal etmediğini (0 ihlal) doğrular.

CRUISE'da HSS bölgesi olunca mission_fsm active_service=SVC_HSS verir → hss_node yazar.
"""
import sys
import time

import rclpy
from rclpy.node import Node

from gokdogan_msgs.msg import HssList, Hss, Target, AircraftState
from gokdogan_common import qos
from gokdogan_guidance import geo

GOAL_N = 220.0   # hedef ~220m kuzey
HSS_N = 110.0    # HSS ~110m kuzey (arada)
HSS_R = 40.0


class HssProbe(Node):
    def __init__(self):
        super().__init__("hss_probe")
        self._own = None
        self._goal = None
        self._hss = None
        self.create_subscription(AircraftState, "/aircraft/state", self._on_state,
                                 qos.sensor_stream())
        self._pub_hss = self.create_publisher(HssList, "/server/hss", qos.server_data())
        self._pub_tgt = self.create_publisher(Target, "/target/selected", qos.target_selected())
        self.create_timer(0.5, self._pub)

    def _on_state(self, m):
        self._own = m

    def _pub(self):
        if self._goal is None:
            return
        h = HssList()
        h.header.stamp = self.get_clock().now().to_msg()
        z = Hss()
        z.id = 1
        z.enlem, z.boylam = self._hss
        z.yaricap = HSS_R
        h.zones.append(z)
        self._pub_hss.publish(h)
        t = Target()
        t.takim_no = 0
        t.lat, t.lon = self._goal
        t.lead_lat, t.lead_lon = self._goal
        self._pub_tgt.publish(t)

    def clearance(self):
        if self._own is None or self._hss is None:
            return None
        d = geo.distance(self._own.lat, self._own.lon, self._hss[0], self._hss[1])
        return d - HSS_R

    def dist_goal(self):
        if self._own is None:
            return None
        return geo.distance(self._own.lat, self._own.lon, self._goal[0], self._goal[1])


def main():
    rclpy.init()
    n = HssProbe()
    t0 = time.time()
    while n._own is None and time.time() - t0 < 30:
        rclpy.spin_once(n, timeout_sec=0.2)
    if n._own is None:
        print("HSS_PROBE: /aircraft/state yok"); return 1
    n._goal = geo.ned_to_ll(GOAL_N, 0.0, n._own.lat, n._own.lon)
    n._hss = geo.ned_to_ll(HSS_N, 0.0, n._own.lat, n._own.lon)
    print(f"HSS_PROBE: hedef {GOAL_N}m K, HSS {HSS_N}m K (r={HSS_R})")

    min_clear = 1e9
    reached = False
    t0 = time.time()
    while time.time() - t0 < 60:
        rclpy.spin_once(n, timeout_sec=0.2)
        c = n.clearance()
        dg = n.dist_goal()
        if c is not None:
            min_clear = min(min_clear, c)
            if int((time.time() - t0)) % 4 == 0:
                print(f"  t={time.time()-t0:4.0f}s clearance={c:6.1f}m dist_goal={dg:6.1f}m")
            if dg < 15.0:
                reached = True
                break
        time.sleep(0.4)
    print(f"HSS_RESULT min_clearance={min_clear:.1f} reached={reached}")
    n.destroy_node(); rclpy.shutdown()
    # 0 İHLAL: min_clearance her zaman > 0 (HSS yarıçapı ihlal edilmedi)
    return 0 if min_clear > 0.0 else 1


if __name__ == "__main__":
    sys.exit(main())

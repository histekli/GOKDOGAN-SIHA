#!/usr/bin/env python3
"""Güdüm kaba-faz probe (Kabul Kapısı 4): copter'ın SITL konumuna göre rakip enjekte eder,
FSM'i LOCKING'e alır, guidance'ın rakibe YAKLAŞMASINI (mesafe azalması) doğrular.

Kamera olmadığından hassas faz tetiklenmez (bbox bayat → COARSE kalır) — kaba GPS+PN yaklaşımı test edilir.
"""
import sys
import time

import rclpy
from rclpy.node import Node

from gokdogan_msgs.msg import Opponents, Opponent
from gokdogan_msgs.srv import SetMissionMode
from gokdogan_msgs.msg import AircraftState, MissionMode
from gokdogan_common import qos
from gokdogan_guidance import geo

OFFSET_LAT = 0.0032   # ~355m kuzey


class Probe(Node):
    def __init__(self):
        super().__init__("guidance_probe")
        self._own = None
        self._opp = None
        self.create_subscription(AircraftState, "/aircraft/state", self._on_state,
                                 qos.sensor_stream())
        self._pub = self.create_publisher(Opponents, "/server/opponents", qos.server_data())
        self._cli = self.create_client(SetMissionMode, "/mission_fsm/set_mission_mode")
        self.create_timer(0.5, self._pub_opp)

    def _on_state(self, m):
        self._own = m

    def _pub_opp(self):
        if self._opp is None:
            return
        msg = Opponents()
        msg.header.stamp = self.get_clock().now().to_msg()
        o = Opponent()
        o.takim_no = 42
        o.enlem, o.boylam = self._opp
        o.irtifa = 100.0
        msg.opponents.append(o)
        self._pub.publish(msg)

    def set_locking(self):
        req = SetMissionMode.Request()
        req.mode = MissionMode.LOCKING
        self._cli.wait_for_service(timeout_sec=5.0)
        fut = self._cli.call_async(req)
        rclpy.spin_until_future_complete(self, fut, timeout_sec=5.0)
        return fut.result()

    def dist_to_opp(self):
        if self._own is None or self._opp is None:
            return None
        return geo.distance(self._own.lat, self._own.lon, self._opp[0], self._opp[1])


def main():
    rclpy.init()
    n = Probe()
    # kendi konumumuzu bekle
    t0 = time.time()
    while n._own is None and time.time() - t0 < 30:
        rclpy.spin_once(n, timeout_sec=0.2)
    if n._own is None:
        print("PROBE: /aircraft/state yok"); return 1
    n._opp = (n._own.lat + OFFSET_LAT, n._own.lon)
    print(f"PROBE: rakip {n._opp[0]:.6f},{n._opp[1]:.6f} (~355m kuzey)")
    time.sleep(1.0)
    res = n.set_locking()
    print(f"PROBE: LOCKING geçiş: {res}")

    d0 = None
    dmin = 1e9
    t0 = time.time()
    while time.time() - t0 < 45:
        rclpy.spin_once(n, timeout_sec=0.2)
        d = n.dist_to_opp()
        if d is not None:
            if d0 is None:
                d0 = d
            dmin = min(dmin, d)
            if int((time.time() - t0)) % 3 == 0:
                print(f"  t={time.time()-t0:4.0f}s dist={d:6.1f}m (min {dmin:.1f})")
        time.sleep(0.5)
    print(f"PROBE_RESULT d0={d0:.1f} dmin={dmin:.1f}")
    n.destroy_node(); rclpy.shutdown()
    # %25+ yaklaşma → başarı (kaba faz çalışıyor)
    return 0 if (d0 and dmin < d0 * 0.75) else 1


if __name__ == "__main__":
    sys.exit(main())

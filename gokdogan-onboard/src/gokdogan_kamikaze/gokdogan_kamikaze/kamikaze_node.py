"""Kamikaze düğümü (SAD §12): ExecuteKamikaze action → KamikazeFsm sürer + QR okur.

FSM'i /aircraft/state (irtifa/hız) ile ilerletir; QR fazında /perception/qr_image'den okur.
Feedback=faz; result={success, qr_text, max_g, detail}. Uçuş komutları (dalış/pull-up attitude)
⚠️ SABİT-KANAT: ArduCopter SITL'de gerçekçi değil → sim/HITL fazında (Faz 7) doğrulanır.
"""
import time

import rclpy
from rclpy.action import ActionServer
from rclpy.node import Node

from gokdogan_msgs.action import ExecuteKamikaze
from gokdogan_msgs.msg import AircraftState, MissionMode
from gokdogan_common import qos
from gokdogan_kamikaze.kamikaze_fsm import KamikazeFsm, KamikazeParams, DONE, ABORT, QR
from gokdogan_kamikaze import qr as qr_pipeline


class KamikazeNode(Node):
    def __init__(self):
        super().__init__("kamikaze")
        self.declare_parameter("timeout_s", 120.0)
        self._fsm = KamikazeFsm(KamikazeParams())
        self._alt = 0.0
        self._airspeed = 0.0
        self._active = False
        self._qr_image = None

        self.create_subscription(AircraftState, "/aircraft/state", self._on_state,
                                 qos.sensor_stream())
        self.create_subscription(MissionMode, "/mission/mode", self._on_mode, qos.mission_mode())
        try:
            from sensor_msgs.msg import Image
            self.create_subscription(Image, "/perception/qr_image", self._on_qr_image,
                                     qos.sensor_stream())
        except Exception:  # noqa: BLE001
            pass

        self._server = ActionServer(
            self, ExecuteKamikaze, "/kamikaze/execute", self._execute)

    def _on_state(self, msg):
        self._alt = float(msg.alt)
        self._airspeed = float(msg.vair)

    def _on_mode(self, msg):
        self._active = (msg.active_service == MissionMode.SVC_KAMIKAZE)

    def _on_qr_image(self, msg):
        try:
            from cv_bridge import CvBridge
            self._qr_image = CvBridge().imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception:  # noqa: BLE001
            self._qr_image = None

    def _try_qr(self):
        if self._qr_image is None:
            return False, ""
        text = qr_pipeline.decode_qr(self._qr_image)
        return (text is not None), (text or "")

    def _execute(self, goal_handle):
        self.get_logger().info("Kamikaze başladı (⚠️ dalış komutları sim/HITL fazında)")
        self._fsm = KamikazeFsm(KamikazeParams())
        self._fsm.start()
        t0 = time.time()
        timeout = float(self.get_parameter("timeout_s").value)
        fb = ExecuteKamikaze.Feedback()
        while rclpy.ok():
            if goal_handle.is_cancel_requested:
                self._fsm.abort()
            qr_found, qr_text = (False, "")
            if self._fsm.s.phase == QR:
                qr_found, qr_text = self._try_qr()
            phase, detail = self._fsm.update(
                self._alt, self._airspeed, aligned=True, qr_found=qr_found, qr_text=qr_text)
            fb.phase = int(phase)
            fb.altitude = float(self._alt)
            fb.airspeed = float(self._airspeed)
            fb.g_load = float(self._fsm.s.max_g_seen)
            fb.detail = detail
            goal_handle.publish_feedback(fb)
            if phase in (DONE, ABORT) or (time.time() - t0) > timeout:
                break
            time.sleep(0.1)

        res = ExecuteKamikaze.Result()
        res.success = (self._fsm.s.phase == DONE)
        res.qr_text = self._fsm.s.qr_text
        res.max_g = float(self._fsm.s.max_g_seen)
        res.detail = self._fsm.s.detail
        goal_handle.succeed()
        return res


def main(args=None):
    rclpy.init(args=args)
    from rclpy.executors import MultiThreadedExecutor
    node = KamikazeNode()
    from rclpy.executors import ExternalShutdownException
    ex = MultiThreadedExecutor()
    ex.add_node(node)
    try:
        ex.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

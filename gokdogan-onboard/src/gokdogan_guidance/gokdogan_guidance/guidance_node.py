"""Güdüm düğümü (SAD §11): iki-faz cascade (kaba GPS+PN → hassas piksel+PID).

TEK-YAZICI (§8): yalnız active_service==SVC_GUIDANCE iken setpoint yazar. Faz geçişi histerezisli
(480/520m + bbox taze) → flapping yok. Setpoint sürekli (≥10Hz) → ArduPilot GUIDED'dan çıkmaz.
Hassas faz görsel-servo kamera ister (⚠️ Gazebo, sim fazında); kaba faz SITL'de test.
"""
import math
import time

import rclpy
from rclpy.node import Node

from mavros_msgs.msg import GlobalPositionTarget, AttitudeTarget
from gokdogan_msgs.msg import MissionMode, Target, BBox, AircraftState
from gokdogan_common import qos
from gokdogan_guidance import geo
from gokdogan_guidance import controllers as C


def _euler_to_quat(roll, pitch, yaw):
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return (
        sr * cp * cy - cr * sp * sy,   # x
        cr * sp * cy + sr * cp * sy,   # y
        cr * cp * sy - sr * sp * cy,   # z
        cr * cp * cy + sr * sp * sy,   # w
    )


class GuidanceNode(Node):
    def __init__(self):
        super().__init__("guidance")
        # PID kazançları (SAD §11 — sihirli sayı yok)
        self.declare_parameter("kp", 0.042)
        self.declare_parameter("ki", 0.0008)
        self.declare_parameter("kd", 0.025)
        self.declare_parameter("phi_max_deg", 45.0)
        self.declare_parameter("theta_max_deg", 30.0)
        self.declare_parameter("phi_rate_deg_s", 20.0)
        self.declare_parameter("lpf_alpha", 0.3)
        self.declare_parameter("enter_d_m", 480.0)
        self.declare_parameter("exit_d_m", 520.0)
        self.declare_parameter("bbox_stale_s", 0.5)
        self.declare_parameter("control_rate_hz", 20.0)
        self.declare_parameter("img_w", 1920.0)
        self.declare_parameter("img_h", 1200.0)

        phi = math.radians(float(self.get_parameter("phi_max_deg").value))
        theta = math.radians(float(self.get_parameter("theta_max_deg").value))
        kp, ki, kd = (float(self.get_parameter(k).value) for k in ("kp", "ki", "kd"))
        self._pid_x = C.PID(kp, ki, kd, -phi, phi)
        self._pid_y = C.PID(kp, ki, kd, -theta, theta)
        rate = math.radians(float(self.get_parameter("phi_rate_deg_s").value))
        self._rl_roll = C.RateLimiter(rate)
        self._rl_pitch = C.RateLimiter(rate)
        self._lpf_roll = C.LPF(float(self.get_parameter("lpf_alpha").value))
        self._lpf_pitch = C.LPF(float(self.get_parameter("lpf_alpha").value))
        self._fsm = C.PhaseFSM(float(self.get_parameter("enter_d_m").value),
                               float(self.get_parameter("exit_d_m").value))

        self._active = False
        self._target = None
        self._bbox = None
        self._bbox_t = 0.0
        self._own = None

        self.create_subscription(MissionMode, "/mission/mode", self._on_mode, qos.mission_mode())
        self.create_subscription(Target, "/target/selected", self._on_target,
                                 qos.target_selected())
        self.create_subscription(BBox, "/perception/selected_bbox", self._on_bbox,
                                 qos.sensor_stream())
        self.create_subscription(AircraftState, "/aircraft/state", self._on_state,
                                 qos.sensor_stream())

        self._pub_global = self.create_publisher(
            GlobalPositionTarget, "/mavros/setpoint_raw/global", qos.sensor_stream())
        self._pub_att = self.create_publisher(
            AttitudeTarget, "/mavros/setpoint_raw/attitude", qos.sensor_stream())

        self._last_t = None
        dt = 1.0 / float(self.get_parameter("control_rate_hz").value)
        self.create_timer(dt, self._control)

    def _on_mode(self, msg):
        was = self._active
        self._active = (msg.active_service == MissionMode.SVC_GUIDANCE)
        if self._active and not was:      # LOCKING'e girişte denetleyicileri sıfırla
            for c in (self._pid_x, self._pid_y, self._rl_roll, self._rl_pitch,
                      self._lpf_roll, self._lpf_pitch):
                c.reset()

    def _on_target(self, msg):
        self._target = msg

    def _on_bbox(self, msg):
        self._bbox = msg
        self._bbox_t = time.time()

    def _on_state(self, msg):
        self._own = msg

    def _bbox_fresh(self):
        return self._bbox is not None and \
            (time.time() - self._bbox_t) < float(self.get_parameter("bbox_stale_s").value)

    def _control(self):
        # TEK-YAZICI: yalnız güdüm aktif servisken yaz (§8)
        if not self._active or self._own is None or self._target is None:
            return
        now = time.time()
        dt = 0.05 if self._last_t is None else max(1e-3, now - self._last_t)
        self._last_t = now

        d = geo.distance(self._own.lat, self._own.lon,
                         self._target.lead_lat, self._target.lead_lon)
        phase = self._fsm.update(d, self._bbox_fresh())

        if phase == C.PRECISE:
            self._precise(dt)
        else:
            self._coarse()

    def _coarse(self):
        """Kaba faz: lead-angle konumuna global setpoint (PN yönü). SITL'de test edilir."""
        sp = GlobalPositionTarget()
        sp.header.stamp = self.get_clock().now().to_msg()
        sp.coordinate_frame = GlobalPositionTarget.FRAME_GLOBAL_REL_ALT
        # pozisyon kullan; hız/ivme/yaw yoksay
        sp.type_mask = (
            GlobalPositionTarget.IGNORE_VX | GlobalPositionTarget.IGNORE_VY
            | GlobalPositionTarget.IGNORE_VZ | GlobalPositionTarget.IGNORE_AFX
            | GlobalPositionTarget.IGNORE_AFY | GlobalPositionTarget.IGNORE_AFZ
            | GlobalPositionTarget.IGNORE_YAW | GlobalPositionTarget.IGNORE_YAW_RATE)
        sp.latitude = float(self._target.lead_lat)
        sp.longitude = float(self._target.lead_lon)
        sp.altitude = float(self._own.alt)     # mevcut (rel) irtifayı koru
        self._pub_global.publish(sp)

    def _precise(self, dt):
        """Hassas faz: piksel hatası → PID → φ,θ (rate-limit + LPF) → attitude setpoint."""
        w = float(self.get_parameter("img_w").value)
        h = float(self.get_parameter("img_h").value)
        cx = self._bbox.x + self._bbox.w / 2.0
        cy = self._bbox.y + self._bbox.h / 2.0
        ex = (cx - w / 2.0) / (w / 2.0)        # normalize [-1,1]
        ey = (cy - h / 2.0) / (h / 2.0)
        roll = self._pid_x.update(ex, dt)      # sağ piksel → sağa yatış
        pitch = self._pid_y.update(-ey, dt)    # yukarı piksel → burun yukarı
        roll = self._lpf_roll.update(self._rl_roll.update(roll, dt))
        pitch = self._lpf_pitch.update(self._rl_pitch.update(pitch, dt))
        yaw = float(self._own.yaw)
        qx, qy, qz, qw = _euler_to_quat(roll, pitch, yaw)
        sp = AttitudeTarget()
        sp.header.stamp = self.get_clock().now().to_msg()
        sp.type_mask = AttitudeTarget.IGNORE_ROLL_RATE | AttitudeTarget.IGNORE_PITCH_RATE \
            | AttitudeTarget.IGNORE_YAW_RATE
        sp.orientation.x, sp.orientation.y, sp.orientation.z, sp.orientation.w = qx, qy, qz, qw
        sp.thrust = 0.5
        self._pub_att.publish(sp)


def main(args=None):
    rclpy.init(args=args)
    node = GuidanceNode()
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

"""GÖKDOĞAN mission_link node — ROS2 ↔ soket köprüsü (SAD §9).

Diller-arası TEK sınır. UDP 5005 (aircraft_vision↑, latest-wins) + TCP 5006 (kontrol).
Onboard = TCP SUNUCU (GCS bağlanır); UDP hedefi TCP peer IP'sinden öğrenilir.
TCP kopması → onboard OTONOM DEVAM (İ2); yeniden accept. Bozuk/partial frame → drop+log.
"""

import socket
import threading

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup

from std_msgs.msg import String

from gokdogan_msgs.msg import (
    MissionMode,
    MissionCommand,
    LockEvent,
    BBox,
    AircraftState,
    Opponents,
    Opponent,
    HssList,
    Hss,
)
from gokdogan_common import qos
from gokdogan_mission_link import protocol as P
from gokdogan_mission_link.metrics import LinkStats

_CMD_MAP = {
    "START_LOCK": MissionCommand.START_LOCK,
    "ABORT": MissionCommand.ABORT,
    "SELECT_TARGET": MissionCommand.SELECT_TARGET,
    "START_KAMIKAZE": MissionCommand.START_KAMIKAZE,
    "SET_MODE": MissionCommand.SET_MODE,
}


class MissionLinkNode(Node):
    def __init__(self):
        super().__init__("mission_link")
        self.declare_parameter("udp_port", P.UDP_PORT)
        self.declare_parameter("tcp_port", P.TCP_PORT)
        self.declare_parameter("vision_rate_hz", 20.0)
        self.declare_parameter("heartbeat_hz", 1.0)
        self.declare_parameter("heartbeat_timeout_s", 5.0)
        self.declare_parameter("schema_path", "")

        self._validator = P.SchemaValidator(self.get_parameter("schema_path").value or None)

        # Durum önbelleği (latest-wins)
        self._mode = MissionMode()
        self._bbox = None
        self._lock = None
        self._seq_udp = 0
        self._seq_tcp = 0

        # Soket durumu
        self._gcs_ip = None
        self._tcp_conn = None
        self._tcp_lock = threading.Lock()
        self._last_gcs_hb = None
        self._link_up = False
        self._stop = threading.Event()

        cbg = ReentrantCallbackGroup()
        # Yukarı (onboard→GCS) için abonelikler
        self.create_subscription(MissionMode, "/mission/mode", self._on_mode, qos.mission_mode(), callback_group=cbg)
        self.create_subscription(
            BBox, "/perception/selected_bbox", self._on_bbox, qos.sensor_stream(), callback_group=cbg
        )
        self.create_subscription(LockEvent, "/lock/event", self._on_lock, qos.lock_event(), callback_group=cbg)
        self.create_subscription(
            AircraftState, "/aircraft/state", lambda m: None, qos.sensor_stream(), callback_group=cbg
        )

        # Aşağı (GCS→onboard) için yayıncılar
        self._pub_cmd = self.create_publisher(MissionCommand, "/mission/command", qos.mission_command())
        self._pub_opp = self.create_publisher(Opponents, "/server/opponents", qos.server_data())
        self._pub_hss = self.create_publisher(HssList, "/server/hss", qos.server_data())
        # Link kalite metrikleri (SAD §22): gelen (down) seq-kayıp % + tek-yön gecikme
        self._stats = LinkStats()
        self._pub_health = self.create_publisher(String, "/health/mission_link", 10)

        # UDP soket (aircraft_vision gönderimi)
        self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Timer'lar
        vdt = 1.0 / float(self.get_parameter("vision_rate_hz").value)
        hdt = 1.0 / float(self.get_parameter("heartbeat_hz").value)
        self.create_timer(vdt, self._send_vision, callback_group=cbg)
        self.create_timer(hdt, self._heartbeat_tick, callback_group=cbg)
        self.create_timer(1.0, self._publish_link_health, callback_group=cbg)

        # TCP sunucu thread'i
        self._tcp_thread = threading.Thread(target=self._tcp_server_loop, daemon=True)
        self._tcp_thread.start()
        self.get_logger().info(
            f"mission_link: TCP :{self.get_parameter('tcp_port').value} sunucu, "
            f"UDP →:{self.get_parameter('udp_port').value}"
        )

    # ---- ROS abonelik önbellekleri ----
    def _on_mode(self, msg):
        self._mode = msg

    def _on_bbox(self, msg):
        self._bbox = msg

    def _on_lock(self, msg):
        self._lock = msg
        # Geçerli kilit olayı → TCP lock_valid (kritik, güvenilir)
        if msg.valid:
            self._send_tcp(
                P.build(
                    "lock_valid",
                    self._next_tcp(),
                    valid=True,
                    target_id=int(msg.target_id),
                    center=[float(msg.center[0]), float(msg.center[1])],
                    box={"x": msg.box.x, "y": msg.box.y, "w": msg.box.w, "h": msg.box.h},
                    lock_end_ts=P.now_ts(),
                )
            )

    # ---- seq sayaçları ----
    def _next_udp(self):
        self._seq_udp += 1
        return self._seq_udp

    def _next_tcp(self):
        self._seq_tcp += 1
        return self._seq_tcp

    # ---- Yukarı: UDP aircraft_vision ----
    def _send_vision(self):
        if self._gcs_ip is None:
            return
        bb = self._bbox
        lk = self._lock
        msg = P.build(
            "aircraft_vision",
            self._next_udp(),
            target_center_x=(bb.x + bb.w / 2.0) if bb else None,
            target_center_y=(bb.y + bb.h / 2.0) if bb else None,
            target_width=(bb.w if bb else None),
            target_height=(bb.h if bb else None),
            is_locked=bool(lk.valid) if lk else False,
            lock_progress_s=(float(lk.progress_s) if lk else 0.0),
            target_team_number=None,
            score=(float(bb.score) if bb else None),
            fsm_state=int(self._mode.state),
            active_service=int(self._mode.active_service),
        )
        try:
            self._udp.sendto(P.encode(msg), (self._gcs_ip, int(self.get_parameter("udp_port").value)))
        except OSError as e:
            self.get_logger().warn(f"UDP gönderim hatası: {e}")

    # ---- Heartbeat + link sağlığı ----
    def _heartbeat_tick(self):
        self._send_tcp(P.build("heartbeat", self._next_tcp(), role="onboard"))
        # GCS heartbeat timeout → link-lost (onboard otonom devam eder)
        if self._last_gcs_hb is not None:
            timeout = float(self.get_parameter("heartbeat_timeout_s").value)
            if self._link_up and (P.now_ts() - self._last_gcs_hb) > timeout:
                self._link_up = False
                self.get_logger().warn("mission_link heartbeat timeout → LINK-LOST (onboard otonom devam)")

    # ---- TCP sunucu ----
    def _tcp_server_loop(self):
        port = int(self.get_parameter("tcp_port").value)
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", port))
        srv.listen(1)
        srv.settimeout(1.0)
        while not self._stop.is_set() and rclpy.ok():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.get_logger().info(f"GCS bağlandı: {addr[0]}")
            self._gcs_ip = addr[0]
            self._tcp_conn = conn
            self._link_up = True
            self._last_gcs_hb = P.now_ts()
            self._handle_client(conn)
            # Kopma → onboard devam, yeniden accept
            with self._tcp_lock:
                self._tcp_conn = None
            self._link_up = False
            self.get_logger().warn("GCS bağlantısı koptu → yeniden bekleniyor (onboard devam)")
        srv.close()

    def _handle_client(self, conn):
        conn.settimeout(1.0)
        framer = P.TcpFramer(on_error=lambda m: self.get_logger().warn(f"TCP frame: {m}"))
        while not self._stop.is_set() and rclpy.ok():
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break  # peer kapattı
            for msg in framer.feed(data):
                self._route_down(msg)
        try:
            conn.close()
        except OSError:
            pass

    def _route_down(self, msg):
        # Şema doğrulama (opsiyonel) — uyumsuz → reddet+log (prompt §5)
        ok, err = self._validator.check(msg)
        if not ok:
            self.get_logger().warn(f"şema-dışı mesaj reddedildi ({msg.get('type')}): {err}")
            return
        # link kalite metriği: TÜM down-link mesajları tek monotonik seq paylaşır (heartbeat dahil)
        t = msg.get("type")
        if isinstance(msg.get("seq"), int):
            self._stats.observe(msg["seq"], ts=msg.get("ts"), now=P.now_ts())
        if t == "heartbeat":
            self._last_gcs_hb = P.now_ts()
        elif t == "operator_cmd":
            self._publish_operator_cmd(msg)
        elif t == "server_data":
            self._publish_server_data(msg)
        elif t == "config":
            self.get_logger().info(f"config alındı: {msg.get('autonomy_weights')}")
        # bilinmeyen tür TcpFramer'da zaten elenir

    def _publish_link_health(self):
        """SAD §22: link kalite metriği (seq-kayıp %, gecikme) → GCS Sistem Sağlığı."""
        import json

        snap = self._stats.snapshot()
        snap["link_up"] = self._link_up
        m = String()
        m.data = json.dumps(snap)
        self._pub_health.publish(m)

    def _publish_operator_cmd(self, msg):
        cmd = msg.get("cmd")
        if cmd not in _CMD_MAP:
            self.get_logger().warn(f"bilinmeyen operator_cmd: {cmd}")
            return
        out = MissionCommand()
        out.type = _CMD_MAP[cmd]
        out.target_id = int(msg.get("target_id") or -1)
        out.mode = str(msg.get("mode") or "")
        import json

        out.params_json = json.dumps(msg.get("params") or {})
        self._pub_cmd.publish(out)
        self.get_logger().info(f"operator_cmd → /mission/command: {cmd}")

    def _publish_server_data(self, msg):
        opps = msg.get("opponents") or []
        if opps:
            om = Opponents()
            om.header.stamp = self.get_clock().now().to_msg()
            for o in opps:
                e = Opponent()
                e.takim_no = int(o.get("takim_no", 0))
                e.enlem = float(o.get("enlem", 0.0))
                e.boylam = float(o.get("boylam", 0.0))
                e.irtifa = float(o.get("irtifa", 0.0))
                e.dikilme = float(o.get("dikilme", 0.0))
                e.yonelme = float(o.get("yonelme", 0.0))
                e.yatis = float(o.get("yatis", 0.0))
                e.hiz = float(o.get("hiz", 0.0))
                e.zaman_farki = float(o.get("zaman_farki", 0.0))
                om.opponents.append(e)
            self._pub_opp.publish(om)
        hss = msg.get("hss") or []
        if hss:
            hm = HssList()
            hm.header.stamp = self.get_clock().now().to_msg()
            for h in hss:
                z = Hss()
                z.id = int(h.get("id", 0))
                z.enlem = float(h.get("enlem", 0.0))
                z.boylam = float(h.get("boylam", 0.0))
                z.yaricap = float(h.get("yaricap", 0.0))
                hm.zones.append(z)
            self._pub_hss.publish(hm)

    # ---- TCP gönderim (kilitli) ----
    def _send_tcp(self, msg):
        with self._tcp_lock:
            conn = self._tcp_conn
            if conn is None:
                return
            try:
                conn.sendall(P.frame_tcp(msg))
            except OSError as e:
                self.get_logger().warn(f"TCP gönderim hatası: {e}")
                self._tcp_conn = None

    def shutdown(self):
        self._stop.set()
        try:
            self._udp.close()
        except OSError:
            pass


def main(args=None):
    rclpy.init(args=args)
    from rclpy.executors import MultiThreadedExecutor

    node = MissionLinkNode()
    ex = MultiThreadedExecutor()
    ex.add_node(node)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

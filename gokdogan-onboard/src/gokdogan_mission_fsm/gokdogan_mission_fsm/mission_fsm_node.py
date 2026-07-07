"""GÖKDOĞAN Görev FSM — lifecycle node (SAD §5.2/§12).

- IDLE'da başlar; MAVROS `/mavros/state` active değilse TAKEOFF'a geçmeyi reddeder (yazılım kapısı).
- SetMissionMode servisi ile yüksek-seviye geçiş (operatör/mission_link Faz 2).
- `/mission/mode` (MissionMode) yayınlar → tek-yazıcı tahkimi (active_service).
- TAKEOFF'ta MAVROS set_mode/arming/takeoff çağırır (araç-agnostik, config'ten).
  Kontrol timer'ı asla bloklanmaz (call_async + tek in-flight future).

KIRMIZI ÇİZGİ: Setpoint yazma hakkı yalnız active_service'te; bu düğüm TAKEOFF/RTL/LAND'de
MISSION_FSM servisidir. Faz 1'de setpoint yazan başka node yok.
"""

import queue
import threading
import time

import rclpy
from rclpy.context import Context
from rclpy.lifecycle import LifecycleNode, TransitionCallbackReturn
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup

from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, CommandTOL, SetMode, StreamRate
from std_msgs.msg import Float64, Bool, String

from gokdogan_msgs.msg import MissionMode, MissionCommand, HssList, AircraftState
from gokdogan_msgs.srv import SetMissionMode
from gokdogan_common import qos
from gokdogan_common.watchdog import Watchdog
from gokdogan_common.structured_log import StructuredLogger, TimeBase

from gokdogan_mission_fsm import fsm_core as fc
from gokdogan_mission_fsm import failsafe_core as fsc

# ArduPilot otonom modları — bunların DIŞINDA bir mod + armed = pilot RC override (MANUAL, §12/§18)
_AUTONOMOUS_MODES = {"GUIDED", "AUTO", "RTL", "LAND", "LOITER", "GUIDED_NOGPS", "QRTL", "QLAND"}

# Kalkış alt-fazları (kontrol timer'ında ilerler; bloklamaz)
T_IDLE, T_WAIT_CONNECT, T_SET_MODE, T_ARM, T_TAKEOFF_CMD, T_CLIMB, T_DONE, T_FAILED = range(8)
_T_NAMES = {
    T_IDLE: "-",
    T_WAIT_CONNECT: "WAIT_CONNECT",
    T_SET_MODE: "SET_MODE",
    T_ARM: "ARM",
    T_TAKEOFF_CMD: "TAKEOFF_CMD",
    T_CLIMB: "CLIMB",
    T_DONE: "DONE",
    T_FAILED: "FAILED",
}


class MissionFsmNode(LifecycleNode):
    def __init__(self):
        super().__init__("mission_fsm")
        # Parametreler (config/{sitl,hardware}.yaml — sihirli sayı yok, §2.10)
        self.declare_parameter("vehicle", "ArduCopter")
        self.declare_parameter("takeoff_method", "guided_takeoff")  # guided_takeoff | auto_mission
        self.declare_parameter("guided_mode", "GUIDED")
        self.declare_parameter("takeoff_alt_m", 10.0)
        self.declare_parameter("arm_timeout_s", 60.0)
        self.declare_parameter("connect_timeout_s", 60.0)
        self.declare_parameter("publish_rate_hz", 1.0)
        self.declare_parameter("control_rate_hz", 2.0)
        self.declare_parameter("stream_rate_hz", 10)  # MAVROS FCU stream rate (SAD §8; Faz 4→50)
        self.declare_parameter("prearm_settle_s", 15.0)  # arm öncesi EKF/GPS oturma süresi
        self.declare_parameter("autostart", True)
        # Failsafe (SAD §18) — katman-2 degraded state yönetimi (native FS ⚠️ ArduPilot param)
        self.declare_parameter("failsafe_enabled", True)
        self.declare_parameter("fs_rc_loss_s", 5.0)
        self.declare_parameter("fs_gcs_loss_s", 10.0)
        self.declare_parameter("fs_gps_glitch_s", 2.0)
        self.declare_parameter("fs_batt_rtl_pct", 20.0)
        self.declare_parameter("fs_rate_hz", 5.0)
        self.declare_parameter("watchdog_timeout_s", 3.0)
        self.declare_parameter("critical_nodes", ["aircraft_state"])

        self.core = fc.FsmCore()
        self._mav = State()
        self._rel_alt = None
        self._connected_since = None
        self._hss_count = 0
        # ---- failsafe & gözlemlenebilirlik durumu (SAD §18/§22) ----
        self._fs = fsc.FailsafeMonitor(
            fsc.FailsafeParams(
                rc_loss_s=float(self.get_parameter("fs_rc_loss_s").value),
                gcs_loss_s=float(self.get_parameter("fs_gcs_loss_s").value),
                gps_glitch_s=float(self.get_parameter("fs_gps_glitch_s").value),
                batt_rtl_pct=float(self.get_parameter("fs_batt_rtl_pct").value),
            )
        )
        self._wdt = Watchdog(float(self.get_parameter("watchdog_timeout_s").value))
        self._slog = StructuredLogger(
            "mission_fsm", TimeBase(), sink=lambda line: self.get_logger().info(f"JSONLOG {line}")
        )
        self._batt = 0.0  # /aircraft/state.batt (0 = raporlanmadı → failsafe yok)
        self._rc_ok = True
        self._gcs_ok = True  # RF/GCS telemetri linki (injectable /failsafe/gcs_ok)
        self._gps_ok = True
        self._geofence_ok = True
        self._fs_action = fsc.FS_NONE  # uygulanan failsafe aksiyonu (tekrar tetiği önle)
        self._takeoff_phase = T_IDLE
        self._phase_t0 = 0.0
        self._pending = None  # (kullanılmıyor; _phase temizler)
        self._last_fire = {}  # komut başına son gönderim zamanı (fire-and-forget)
        self._queued = set()  # worker kuyruğunda bekleyen komut anahtarları (dedupe)
        self._detail = "boot"
        self._cli = {}
        self._configured = False
        self._streams_requested = False
        self._stop = threading.Event()
        self._helper_ctx = None
        self._helper_thread = None

    # ---- lifecycle ----
    def on_configure(self, state) -> TransitionCallbackReturn:
        cbg_io = ReentrantCallbackGroup()
        cbg_ctrl = MutuallyExclusiveCallbackGroup()

        self._pub_mode = self.create_lifecycle_publisher(MissionMode, "/mission/mode", qos.mission_mode())

        self.create_subscription(State, "/mavros/state", self._on_state, 10, callback_group=cbg_io)
        self.create_subscription(
            Float64, "/mavros/global_position/rel_alt", self._on_alt, qos.sensor_stream(), callback_group=cbg_io
        )

        self._srv = self.create_service(SetMissionMode, "~/set_mission_mode", self._on_set_mode, callback_group=cbg_io)
        # Operatör komutu (mission_link → /mission/command → FSM geçişi, SAD §12)
        self.create_subscription(
            MissionCommand, "/mission/command", self._on_command, qos.mission_command(), callback_group=cbg_io
        )
        # HSS bölge sayısı (tahkim: CRUISE'da HSS varsa yazma hakkı HSS'e, §13)
        self.create_subscription(
            HssList,
            "/server/hss",
            lambda m: setattr(self, "_hss_count", len(m.zones)),
            qos.server_data(),
            callback_group=cbg_io,
        )

        # ---- failsafe girdileri (SAD §18) ----
        # /aircraft/state: batarya + freshness (watchdog "aircraft_state" liveness)
        self.create_subscription(
            AircraftState, "/aircraft/state", self._on_aircraft, qos.sensor_stream(), callback_group=cbg_io
        )
        # injectable link/GPS/geofence bayrakları (RF yokken SITL/test tetiği; varsayılan sağlıklı)
        self.create_subscription(
            Bool, "/failsafe/gcs_ok", lambda m: setattr(self, "_gcs_ok", m.data), 10, callback_group=cbg_io
        )
        self.create_subscription(
            Bool, "/failsafe/rc_ok", lambda m: setattr(self, "_rc_ok", m.data), 10, callback_group=cbg_io
        )
        self.create_subscription(
            Bool, "/failsafe/gps_ok", lambda m: setattr(self, "_gps_ok", m.data), 10, callback_group=cbg_io
        )
        self.create_subscription(
            Bool, "/failsafe/geofence_ok", lambda m: setattr(self, "_geofence_ok", m.data), 10, callback_group=cbg_io
        )
        # opsiyonel node heartbeat (std_msgs/String = node adı) → watchdog
        self.create_subscription(
            String, "/health/heartbeat", lambda m: self._wdt.beat(m.data, time.time()), 10, callback_group=cbg_io
        )
        self._pub_health = self.create_lifecycle_publisher(String, "/health/status", 10)
        now0 = time.time()
        for n in self.get_parameter("critical_nodes").value:
            self._wdt.register(n, required=True, now=now0)  # başlangıç grace'i

        # MAVROS servis çağrıları AYRI yardımcı node'da ve TEK bir worker thread'de
        # SENKRON yürütülür (diag ile doğrulanmış düz-node deseni: wait_for_service +
        # spin_until_future_complete AYNI thread'de). Ana LifecycleNode/MultiThreadedExecutor
        # bağlamında client keşfi (özellikle /mavros/cmd/arming) güvenilmezdi; bu izolasyon
        # keşif+çağrıyı sağlamlaştırır. Kontrol timer'ı yalnız komut kuyruğa atar (bloklamaz).
        # AYRI rclpy Context → ayrı DDS participant (ana LifecycleNode'dan tam izolasyon;
        # diag.py'nin izole process'ini birebir taklit eder — paylaşılan context'te
        # /mavros/cmd/arming keşfedilemiyordu).
        self._helper_ctx = Context()
        rclpy.init(context=self._helper_ctx)
        self._helper_node = rclpy.create_node(self.get_name() + "_mav", context=self._helper_ctx)
        self._cli["arming"] = self._helper_node.create_client(CommandBool, "/mavros/cmd/arming")
        self._cli["set_mode"] = self._helper_node.create_client(SetMode, "/mavros/set_mode")
        self._cli["takeoff"] = self._helper_node.create_client(CommandTOL, "/mavros/cmd/takeoff")
        self._cli["stream_rate"] = self._helper_node.create_client(StreamRate, "/mavros/set_stream_rate")
        self._cmd_q = queue.Queue()
        self._helper_thread = threading.Thread(target=self._helper_worker, daemon=True)
        self._helper_thread.start()

        pub_dt = 1.0 / float(self.get_parameter("publish_rate_hz").value)
        ctl_dt = 1.0 / float(self.get_parameter("control_rate_hz").value)
        self._pub_timer = self.create_timer(pub_dt, self._publish_mode, callback_group=cbg_ctrl)
        self._ctl_timer = self.create_timer(ctl_dt, self._control_step, callback_group=cbg_ctrl)
        fs_dt = 1.0 / float(self.get_parameter("fs_rate_hz").value)
        self._fs_timer = self.create_timer(fs_dt, self._failsafe_step, callback_group=cbg_ctrl)
        self._pub_timer.cancel()
        self._ctl_timer.cancel()
        self._fs_timer.cancel()

        self._configured = True
        self._detail = "configured (IDLE)"
        self.get_logger().info("mission_fsm configured → IDLE")
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state) -> TransitionCallbackReturn:
        self._pub_timer.reset()
        self._ctl_timer.reset()
        if self.get_parameter("failsafe_enabled").value:
            self._fs_timer.reset()
        self.get_logger().info("mission_fsm ACTIVE")
        return super().on_activate(state)

    def on_deactivate(self, state) -> TransitionCallbackReturn:
        self._pub_timer.cancel()
        self._ctl_timer.cancel()
        self._fs_timer.cancel()
        return super().on_deactivate(state)

    # ---- abonelik geri çağırımları ----
    def _on_state(self, msg):
        # RC override → MANUAL algısı (§12): mode elle MANUAL/STABILIZE olursa FSM setpoint bırakır
        if msg.connected and self._connected_since is None:
            self._connected_since = time.time()
        self._mav = msg

    def _on_alt(self, msg):
        self._rel_alt = msg.data

    def _on_aircraft(self, msg):
        self._batt = float(msg.batt)
        self._wdt.beat("aircraft_state", time.time())  # aircraft_state_node canlılığı

    # ---- failsafe döngüsü (SAD §18) ----
    def _rc_override_active(self):
        """Pilot RC ile otonom-dışı moda aldıysa MANUAL (pilot üstün, §12/§18)."""
        return bool(self._mav.armed) and self._mav.mode not in _AUTONOMOUS_MODES and self._mav.mode != ""

    def _in_flight(self):
        return self.core.state in (fc.CRUISE, fc.LOCKING, fc.KAMIKAZE, fc.RTL, fc.LAND)

    def _failsafe_step(self):
        now = time.time()
        healthy = self._wdt.healthy(now)
        inputs = fsc.FailsafeInputs(
            now=now,
            battery_pct=self._batt,
            rc_ok=self._rc_ok,
            gcs_ok=self._gcs_ok,
            gps_ok=self._gps_ok,
            geofence_ok=self._geofence_ok,
            rc_override=self._rc_override_active(),
            node_health_ok=healthy,
            armed=bool(self._mav.armed),
            in_flight=self._in_flight(),
        )
        action, reason = self._fs.update(inputs)

        # sağlık durumunu yayınla (GCS Sistem Sağlığı, §22)
        stale = self._wdt.stale_required(now)
        h = String()
        h.data = f"fs={fsc.action_name(action)} state={self.core.state_name} " f"batt={self._batt:.0f} stale={stale}"
        try:
            self._pub_health.publish(h)
        except Exception:  # noqa: BLE001
            pass

        if action == fsc.FS_NONE:
            return
        if action != self._fs_action:
            self._apply_failsafe(action, reason)
        elif action in (fsc.FS_RTL, fsc.FS_LAND):
            # zaten uygulandı; mod henüz alınmadıysa yeniden iste (setpoint timeout/ret güvence)
            want = "RTL" if action == fsc.FS_RTL else "LAND"
            if self._mav.mode != want:
                self._request_mode(want)

    def _apply_failsafe(self, action, reason):
        self._fs_action = action
        self._slog.emit(
            "failsafe",
            action=fsc.action_name(action),
            reason=reason,
            frm=self.core.state_name,
            batt=round(self._batt, 1),
        )
        self.get_logger().warn(f"FAILSAFE {fsc.action_name(action)}: {reason}")
        if action == fsc.FS_MANUAL:
            self.core.force(fc.MANUAL)  # pilot kontrolde; setpoint bırakılır (SVC_NONE)
        elif action == fsc.FS_RTL:
            self.core.force(fc.RTL)
            self._request_mode("RTL")
        elif action == fsc.FS_LAND:
            self.core.force(fc.LAND)
            self._request_mode("LAND")
        self._publish_mode()

    def _request_mode(self, mode_str):
        """MAVROS set_mode'u worker kuyruğuna at (bloklamaz, dedupe)."""
        req = SetMode.Request()
        req.custom_mode = mode_str
        self._enqueue_once(f"failsafe_mode_{mode_str}", req)

    # ---- ortak geçiş uygulaması (servis + operatör komutu) ----
    def _apply_transition(self, target):
        """DFA geçişini guard'larla uygular. (ok, reason) döndürür."""
        # TAKEOFF için yazılım kapısı: MAVROS bağlı olmalı (arming check benzeri, §5.2)
        if target == fc.TAKEOFF and not self._mav.connected:
            self.get_logger().warn("MAVROS bağlı değil — TAKEOFF reddedildi (degraded)")
            return False, "MAVROS bağlı değil"
        ok, reason = self.core.transition(target)
        if ok:
            self.get_logger().info(f"FSM geçiş → {self.core.state_name} ({reason})")
            if target == fc.TAKEOFF:
                self._start_takeoff()
            else:
                self._takeoff_phase = T_IDLE
            self._publish_mode()
        else:
            self.get_logger().warn(f"Geçiş reddedildi: {reason}")
        return ok, reason

    # ---- servis: yüksek-seviye geçiş ----
    def _on_set_mode(self, req, resp):
        resp.success, resp.message = self._apply_transition(req.mode)
        return resp

    # ---- operatör komutu (mission_link → /mission/command) ----
    def _on_command(self, msg):
        t = msg.type
        if t == MissionCommand.START_LOCK:
            self._apply_transition(fc.LOCKING)
        elif t == MissionCommand.ABORT:
            self._apply_transition(fc.CRUISE)
        elif t == MissionCommand.START_KAMIKAZE:
            self._apply_transition(fc.KAMIKAZE)
        elif t == MissionCommand.SELECT_TARGET:
            self.get_logger().info(f"SELECT_TARGET hedef={msg.target_id} (Faz 4 target_selector)")
        elif t == MissionCommand.SET_MODE:
            self._apply_command_set_mode(msg.mode)
        else:
            self.get_logger().warn(f"bilinmeyen MissionCommand.type={t}")

    def _apply_command_set_mode(self, mode):
        m = (mode or "").upper()
        mapping = {"TAKEOFF": fc.TAKEOFF, "RTL": fc.RTL, "LAND": fc.LAND, "CRUISE": fc.CRUISE, "MANUAL": fc.MANUAL}
        if m in mapping:
            self._apply_transition(mapping[m])
        else:
            self.get_logger().info(f"SET_MODE '{mode}' — doğrudan MAVLink modu (FSM geçişi yok)")

    # ---- kalkış sekanslayıcı (bloklamaz) ----
    def _start_takeoff(self):
        self._takeoff_phase = T_WAIT_CONNECT
        self._phase_t0 = time.time()
        self._last_fire = {}
        self._detail = "takeoff: WAIT_CONNECT"

    def _phase(self, p, detail):
        self._takeoff_phase = p
        self._phase_t0 = time.time()
        self._detail = detail
        self._pending = None  # faz değişince eski (bir önceki faza ait) future sızmasın
        self.get_logger().info(f"takeoff → {_T_NAMES[p]}")

    def _fail(self, why):
        self.get_logger().error(f"Kalkış BAŞARISIZ: {why} → IDLE (degraded)")
        self.core.force(fc.IDLE)
        self._takeoff_phase = T_FAILED
        self._detail = f"takeoff FAILED: {why}"
        self._publish_mode()

    def _fire_every(self, key, interval, client, req):
        """Komutu periyodik olarak yardımcı worker kuyruğuna atar (bloklamaz). İlerleme
        /mavros/state üzerinden. Gerçek servis çağrısı _helper_worker'da senkron yürür."""
        now = time.time()
        if now - self._last_fire.get(key, 0.0) < interval:
            return
        if key in self._queued:  # aynı komut zaten worker kuyruğunda/işlemede
            return
        self._last_fire[key] = now
        self._queued.add(key)
        self._cmd_q.put((key, req))

    def _enqueue_once(self, key, payload):
        """Aynı komut kuyrukta değilse worker'a at (dedupe + _last_fire kaydı)."""
        if key in self._queued:
            return
        self._last_fire[key] = time.time()
        self._queued.add(key)
        self._cmd_q.put((key, payload))

    def _call_sync(self, key, req):
        """Yardımcı node'da tek servisi SENKRON çağır; (ok, result) döndür."""
        client = self._cli.get(key)
        if client is None:
            return False, None
        if not client.wait_for_service(timeout_sec=30.0):
            self.get_logger().warn(f"{key}: servis yok (wait_for_service timeout)")
            return False, None
        fut = client.call_async(req)
        rclpy.spin_until_future_complete(self._helper_node, fut, timeout_sec=5.0)
        r = fut.result()
        ok = bool(getattr(r, "success", getattr(r, "mode_sent", r is not None)))
        self.get_logger().info(
            f"{key} sonucu: success={getattr(r, 'success', getattr(r, 'mode_sent', None))} "
            f"result={getattr(r, 'result', None)}"
        )
        return ok, r

    def _call_sync_with(self, client_key, log_key, req):
        """Belirli bir client (client_key) ile senkron çağır; log/dedupe log_key altında."""
        client = self._cli.get(client_key)
        if client is None:
            return False, None
        if not client.wait_for_service(timeout_sec=10.0):
            self.get_logger().warn(f"{log_key}: {client_key} servisi yok")
            return False, None
        fut = client.call_async(req)
        rclpy.spin_until_future_complete(self._helper_node, fut, timeout_sec=5.0)
        r = fut.result()
        self.get_logger().info(f"{log_key} → mode_sent={getattr(r, 'mode_sent', None)}")
        return bool(getattr(r, "mode_sent", r is not None)), r

    def _helper_worker(self):
        """Tek thread: MAVROS servis çağrılarını SENKRON yürütür (wait_for_service +
        spin_until_future_complete AYNI thread'de — diag ile doğrulanmış desen)."""
        while not self._stop.is_set() and rclpy.ok():
            try:
                key, payload = self._cmd_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if key == "arm_takeoff":
                    # Servisleri ÖNCE keşfet (takeoff arm'dan hemen sonra gecikmesiz gitsin;
                    # ArduCopter GUIDED'da arm sonrası ~1s içinde takeoff gelmezse disarm eder).
                    self._cli["arming"].wait_for_service(timeout_sec=30.0)
                    self._cli["takeoff"].wait_for_service(timeout_sec=30.0)
                    arm_ok, _ = self._call_sync("arming", CommandBool.Request(value=True))
                    if arm_ok:
                        to = CommandTOL.Request()
                        to.altitude = float(payload)
                        self._call_sync("takeoff", to)  # arm'dan hemen sonra
                elif key.startswith("failsafe_mode_"):
                    # failsafe RTL/LAND → MAVROS set_mode (SAD §18)
                    self._call_sync_with("set_mode", key, payload)
                else:
                    self._call_sync(key, payload)
            except Exception as e:  # noqa: BLE001
                self.get_logger().warn(f"{key} çağrı hatası: {e}")
            finally:
                self._queued.discard(key)

    def _maybe_request_streams(self):
        """Bağlantı kurulunca FCU stream rate'lerini iste (SAD §8 — varsayılan düşük).
        MAVProxy yokken FCU pozisyon/attitude yollamaz → rel_alt/local_position boş kalır."""
        if self._streams_requested or not self._mav.connected:
            return
        rate = int(self.get_parameter("stream_rate_hz").value)
        req = StreamRate.Request()
        req.stream_id = 0  # 0 = TÜM streamler
        req.message_rate = rate
        req.on_off = True
        self._cmd_q.put(("stream_rate", req))  # worker'da senkron yürür
        self._streams_requested = True
        self.get_logger().info(f"MAVROS stream rate {rate}Hz istendi (SAD §8)")

    def _control_step(self):
        self._maybe_request_streams()
        ph = self._takeoff_phase
        if ph in (T_IDLE, T_DONE, T_FAILED):
            return
        alt_target = float(self.get_parameter("takeoff_alt_m").value)
        arm_timeout = float(self.get_parameter("arm_timeout_s").value)
        conn_timeout = float(self.get_parameter("connect_timeout_s").value)
        now = time.time()

        if ph == T_WAIT_CONNECT:
            if self._mav.connected:
                self._phase(T_SET_MODE, "set GUIDED")
            elif now - self._phase_t0 > conn_timeout:
                self._fail("MAVROS bağlanmadı")

        elif ph == T_SET_MODE:
            gmode = self.get_parameter("guided_mode").value
            if self._mav.mode == gmode:
                self._phase(T_ARM, "arm (retry)")
                return
            if now - self._phase_t0 > conn_timeout:
                self._fail("mode GUIDED alınamadı")
                return
            req = SetMode.Request()
            req.custom_mode = gmode
            self._fire_every("set_mode", 2.0, self._cli["set_mode"], req)

        elif ph == T_ARM:
            # EKF/GPS oturması için settle bekle, sonra arm+takeoff'u BİRLİKTE tetikle.
            if now - self._phase_t0 > arm_timeout:
                self._fail("arming timeout (prearm/EKF)")
                return
            settle = float(self.get_parameter("prearm_settle_s").value)
            if self._connected_since is not None and now - self._connected_since < settle:
                self._detail = f"arm settle ({now - self._connected_since:.0f}/{settle:.0f}s)"
                return
            # arm+takeoff birleşik (worker'da art arda, gecikmesiz) — 1s disarm'ı önler.
            self._enqueue_once("arm_takeoff", alt_target)
            self._phase(T_CLIMB, f"climb → {alt_target} m")

        elif ph == T_CLIMB:
            if self._rel_alt is not None and self._rel_alt >= 0.95 * alt_target:
                self.get_logger().info(f"Kalkış TAMAM: rel_alt={self._rel_alt:.2f} m → CRUISE")
                self.core.transition(fc.CRUISE)
                self._takeoff_phase = T_DONE
                self._detail = "airborne (CRUISE)"
                self._publish_mode()
                return
            if now - self._last_fire.get("climb_log", 0.0) > 3.0:
                self._last_fire["climb_log"] = now
                self.get_logger().info(f"climb: rel_alt={self._rel_alt} armed={self._mav.armed} mode={self._mav.mode}")
            # Tırmanış başlamadıysa arm+takeoff'u yeniden dene (disarm olmuşsa yeniden arm eder)
            if (
                (self._rel_alt is None or self._rel_alt < 1.0)
                and now - self._phase_t0 > 6.0
                and now - self._last_fire.get("arm_takeoff", 0.0) > 6.0
            ):
                self._enqueue_once("arm_takeoff", alt_target)
            if now - self._phase_t0 > 90.0:
                self._fail("tırmanış timeout")

    def shutdown_helper(self):
        """Yardımcı worker thread + ayrı context'i temiz kapat (kapanışta segfault önler)."""
        self._stop.set()
        if self._helper_thread is not None:
            self._helper_thread.join(timeout=3.0)
        try:
            if self._helper_ctx is not None and self._helper_ctx.ok():
                self._helper_ctx.try_shutdown()
        except Exception:  # noqa: BLE001
            pass

    # ---- /mission/mode yayını ----
    def _active_service(self):
        """Tahkim (§13): CRUISE'da aktif HSS bölgesi varsa yazma hakkı HSS'e verilir."""
        svc = self.core.active_service
        if self.core.state == fc.CRUISE and self._hss_count > 0:
            return MissionMode.SVC_HSS
        return svc

    def _publish_mode(self):
        msg = MissionMode()
        msg.state = self.core.state
        msg.active_service = self._active_service()
        msg.detail = self._detail
        # lifecycle publisher yalnız active iken yayınlar
        try:
            self._pub_mode.publish(msg)
        except Exception:
            pass


def main(args=None):
    rclpy.init(args=args)
    node = MissionFsmNode()
    # autostart: configure → activate (SITL/CI için; gerçekte lifecycle yöneticisi)
    if node.get_parameter("autostart").value:
        node.trigger_configure()
        node.trigger_activate()
    from rclpy.executors import MultiThreadedExecutor

    ex = MultiThreadedExecutor()
    ex.add_node(node)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown_helper()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

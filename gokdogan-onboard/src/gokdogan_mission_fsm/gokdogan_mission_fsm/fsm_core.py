"""Görev FSM çekirdeği (saf Python, ROS-bağımsız → birim test edilebilir). SAD §12.

DFA geçiş tablosu + her state'in tek `active_service`'i (tek-yazıcı tahkimi, İ1/§8).
ROS düğümü (mission_fsm_node) bu çekirdeği MAVROS G/Ç ile sarar.
"""
from gokdogan_msgs.msg import MissionMode as MM

# Durum isimleri (MissionMode sabitleriyle birebir)
IDLE = MM.IDLE
TAKEOFF = MM.TAKEOFF
CRUISE = MM.CRUISE
LOCKING = MM.LOCKING
KAMIKAZE = MM.KAMIKAZE
RTL = MM.RTL
LAND = MM.LAND
MANUAL = MM.MANUAL

STATE_NAMES = {
    IDLE: "IDLE", TAKEOFF: "TAKEOFF", CRUISE: "CRUISE", LOCKING: "LOCKING",
    KAMIKAZE: "KAMIKAZE", RTL: "RTL", LAND: "LAND", MANUAL: "MANUAL",
}

# İzin verilen geçişler (SAD §12 DFA). MANUAL her state'ten RC override ile girilebilir.
_TRANSITIONS = {
    IDLE:     {TAKEOFF, MANUAL},
    TAKEOFF:  {CRUISE, RTL, MANUAL},
    CRUISE:   {LOCKING, KAMIKAZE, RTL, LAND, MANUAL},
    LOCKING:  {CRUISE, RTL, MANUAL},
    KAMIKAZE: {CRUISE, RTL, MANUAL},
    RTL:      {LAND, MANUAL},
    LAND:     {IDLE, MANUAL},
    MANUAL:   {IDLE, CRUISE},   # pilot devreder
}

# Her state'te setpoint yazma hakkı olan tek servis (tek-yazıcı invaryantı, §8).
_ACTIVE_SERVICE = {
    IDLE:     MM.SVC_NONE,
    TAKEOFF:  MM.SVC_MISSION_FSM,
    CRUISE:   MM.SVC_NONE,        # CRUISE'de HSS arka planda olabilir; acil kaçınmada FSM devreder
    LOCKING:  MM.SVC_GUIDANCE,
    KAMIKAZE: MM.SVC_KAMIKAZE,
    RTL:      MM.SVC_MISSION_FSM,
    LAND:     MM.SVC_MISSION_FSM,
    MANUAL:   MM.SVC_NONE,        # pilot kontrolde; hiçbir node setpoint yazmaz
}


class FsmCore:
    """Saf durum makinesi. Geçiş guard'ları (bağlantı/arm) ROS katmanında uygulanır."""

    def __init__(self, state=IDLE):
        self._state = state

    @property
    def state(self):
        return self._state

    @property
    def active_service(self):
        return _ACTIVE_SERVICE[self._state]

    @property
    def state_name(self):
        return STATE_NAMES[self._state]

    def can_transition(self, target):
        return target in _TRANSITIONS.get(self._state, set())

    def transition(self, target):
        """Geçişi dener. (ok, reason) döndürür; ok=False ise state değişmez."""
        if target == self._state:
            return True, "no-op (zaten bu state)"
        if target not in STATE_NAMES:
            return False, f"bilinmeyen state: {target}"
        if not self.can_transition(target):
            return False, f"{self.state_name} → {STATE_NAMES[target]} yasak (DFA)"
        self._state = target
        return True, "ok"

    def force(self, target):
        """Guard'sız zorla (ör. RC override → MANUAL, failsafe → RTL). Her zaman geçer."""
        self._state = target

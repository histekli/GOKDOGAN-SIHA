"""Failsafe karar çekirdeği (saf Python, ROS-bağımsız → birim test edilebilir). SAD §18.

Tetik → aksiyon eşlemesi + **öncelik** + **debounce** (sürekli koşul) + **latch** (mod-değişimi
failsafe'i bir kez tetiklenince kalıcı). Katman-2 (mission_fsm degraded); katman-1 ArduPilot native
FS (RC/batt/GPS/geofence — parametrelerle, ⚠️ on-device). RC override (MANUAL) HER ZAMAN üstün.

KIRMIZI ÇİZGİ (İ2): mission_link/Wi-Fi kaybı **failsafe DEĞİL** — onboard otonom devam eder.
Yalnız RF/GCS telemetri kaybı (10s) RTL tetikler.

Öncelik (yüksekten düşüğe):
  RC override → MANUAL  >  GPS glitch → LAND  >  geofence → RTL  >  batarya → RTL
  >  node-health (watchdog) → RTL  >  RC loss → (config: LAND/RTL)  >  GCS loss → RTL
"""

from dataclasses import dataclass

# Failsafe aksiyonları (mission_fsm_node bunları fc.RTL/LAND/MANUAL'e eşler)
FS_NONE = 0
FS_RTL = 1
FS_LAND = 2
FS_MANUAL = 3
_ACTION_NAMES = {FS_NONE: "NONE", FS_RTL: "RTL", FS_LAND: "LAND", FS_MANUAL: "MANUAL"}


def action_name(a):
    return _ACTION_NAMES.get(a, f"?{a}")


@dataclass
class FailsafeParams:
    rc_loss_s: float = 5.0  # RC linki kayıp süresi → rc_action (ArduPilot FS_THR)
    gcs_loss_s: float = 10.0  # RF/GCS telemetri kayıp süresi → RTL (KTR)
    gps_glitch_s: float = 2.0  # GPS bozulması bu süre sürerse → LAND (dead-reckoning)
    batt_rtl_pct: float = 20.0  # batarya bu yüzdenin altında → RTL
    rc_action: int = FS_LAND  # RC loss aksiyonu (SAD §18: LAND/RTL — araç/config'e göre)


@dataclass
class FailsafeInputs:
    now: float
    battery_pct: float = 100.0
    rc_ok: bool = True  # RC linki sağlıklı mı (False = kayıp)
    gcs_ok: bool = True  # RF/GCS telemetri linki sağlıklı mı
    gps_ok: bool = True  # GPS/EKF sağlıklı mı
    geofence_ok: bool = True  # geofence içinde mi
    mission_link_ok: bool = True  # Wi-Fi veri linki (İ2: kayıp → failsafe DEĞİL)
    rc_override: bool = False  # pilot MANUAL'a aldı (üstün)
    node_health_ok: bool = True  # watchdog: kritik node'lar canlı mı
    armed: bool = True
    in_flight: bool = True  # havada mı (yerdeyken failsafe tetiklenmez)


class FailsafeMonitor:
    """Durumlu failsafe monitörü. update(inputs) → (action, reason). Latch + debounce içerir."""

    def __init__(self, p: FailsafeParams = None):
        self.p = p or FailsafeParams()
        self._rc_lost_since = None
        self._gcs_lost_since = None
        self._gps_bad_since = None
        self._latched_action = FS_NONE  # mod-değişimi failsafe'i latch'lenir (RC override hariç)
        self._latched_reason = ""
        self._last = (FS_NONE, "boot")

    @property
    def latched(self):
        return self._latched_action

    @property
    def last(self):
        return self._last

    def reset(self):
        """Latch + debounce zamanlayıcılarını sıfırla (ör. RTL sonrası yeniden CRUISE)."""
        self._rc_lost_since = None
        self._gcs_lost_since = None
        self._gps_bad_since = None
        self._latched_action = FS_NONE
        self._latched_reason = ""

    def _sustained(self, ok, since_attr, threshold, now):
        """Bir koşul (not-ok) 'threshold' saniye SÜRDÜ mü? since zamanlayıcısını yönetir.

        Eşik=0 → ilk gözlemde anında tetikler (since=now → now−now=0 ≥ 0)."""
        if ok:
            setattr(self, since_attr, None)
            return False
        since = getattr(self, since_attr)
        if since is None:
            since = now
            setattr(self, since_attr, since)
        return (now - since) >= threshold

    def update(self, i: FailsafeInputs):
        p = self.p

        # 0) RC override HER ZAMAN üstün — pilot devraldı (latch'i ezer, sıfırlamaz)
        if i.rc_override:
            self._last = (FS_MANUAL, "RC override — pilot kontrolde")
            return self._last

        # yerde / disarm → failsafe yok (zamanlayıcıları sıfırla)
        if not i.armed or not i.in_flight:
            self._rc_lost_since = self._gcs_lost_since = self._gps_bad_since = None
            self._last = (
                (self._latched_action, self._latched_reason) if self._latched_action else (FS_NONE, "yerde/disarm")
            )
            return self._last

        # debounce zamanlayıcılarını her koşulda güncelle (sustained hesapları)
        rc_lost = self._sustained(i.rc_ok, "_rc_lost_since", p.rc_loss_s, i.now)
        gcs_lost = self._sustained(i.gcs_ok, "_gcs_lost_since", p.gcs_loss_s, i.now)
        gps_bad = self._sustained(i.gps_ok, "_gps_bad_since", p.gps_glitch_s, i.now)

        # aday tetikler → (öncelik, aksiyon, sebep); düşük öncelik sayısı = daha acil
        candidates = []
        if gps_bad:
            candidates.append((1, FS_LAND, f"GPS glitch ≥{p.gps_glitch_s:g}s → LAND"))
        if not i.geofence_ok:
            candidates.append((2, FS_RTL, "geofence ihlali → RTL"))
        # batarya: 0/negatif = bilinmeyen/raporlanmadı (SITL) → yok say (yanlış-tetik önle)
        if 0.0 < i.battery_pct < p.batt_rtl_pct:
            candidates.append((3, FS_RTL, f"batarya %{i.battery_pct:g} < %{p.batt_rtl_pct:g} → RTL"))
        if not i.node_health_ok:
            candidates.append((4, FS_RTL, "kritik node ölü (watchdog) → RTL"))
        if rc_lost:
            candidates.append((5, p.rc_action, f"RC kaybı ≥{p.rc_loss_s:g}s → {action_name(p.rc_action)}"))
        if gcs_lost:
            candidates.append((6, FS_RTL, f"GCS/telemetri kaybı ≥{p.gcs_loss_s:g}s → RTL"))
        # İ2: mission_link_ok=False bilinçli olarak DEĞERLENDİRİLMEZ (otonom devam)

        if candidates:
            candidates.sort(key=lambda c: c[0])
            _, action, reason = candidates[0]
            # latch: yeni failsafe latch'le (daha acil olan öncekini ezer)
            if self._latched_action == FS_NONE or action != self._latched_action:
                self._latched_action = action
                self._latched_reason = reason

        # latch varsa onu sürdür (koşul iyileşse bile RTL/LAND'de kal — güvenli)
        if self._latched_action != FS_NONE:
            self._last = (self._latched_action, self._latched_reason)
        else:
            self._last = (FS_NONE, "nominal")
        return self._last

"""Kamikaze alt-FSM (SAD §12, KESIN_PLAN §7). Saf Python — guard'lar test edilebilir.

Idle→Intikal(100m AGL, Pure Pursuit)→Dalış(−45°, TECS, 28-30 m/s)→QR(50m↓)→PullUp(R45m, 2.7G, min-alt).
Guard'lar: irtifa eşikleri, QR bulunamazsa min-alt'ta HER HALÜKARDA pull-up, G≤3 clamp, max 2 deneme.
"""
from dataclasses import dataclass, field

IDLE, INTIKAL, DALIS, QR, PULLUP, DONE, ABORT = range(7)
_NAMES = {IDLE: "IDLE", INTIKAL: "INTIKAL", DALIS: "DALIS", QR: "QR",
          PULLUP: "PULLUP", DONE: "DONE", ABORT: "ABORT"}


@dataclass
class KamikazeParams:
    climb_alt_m: float = 100.0      # intikal irtifası
    dive_pitch_deg: float = -45.0
    dive_speed_min: float = 28.0
    dive_speed_max: float = 30.0
    qr_start_alt_m: float = 50.0    # QR okuma bu irtifanın altında başlar
    min_pullup_alt_m: float = 30.0  # KESİN güvenlik: bu irtifada her halükarda pull-up
    pullup_g: float = 2.7
    g_limit: float = 3.0            # aşılamaz
    pullup_exit_alt_m: float = 80.0  # pull-up bu irtifaya çıkınca tamam
    max_attempts: int = 2


@dataclass
class KamikazeState:
    phase: int = IDLE
    attempts: int = 0
    qr_text: str = ""
    max_g_seen: float = 0.0
    detail: str = ""


class KamikazeFsm:
    def __init__(self, p: KamikazeParams = None):
        self.p = p or KamikazeParams()
        self.s = KamikazeState()

    def start(self):
        self.s = KamikazeState(phase=INTIKAL, detail="intikal başladı")

    def abort(self):
        self.s.phase = ABORT

    @property
    def phase_name(self):
        return _NAMES[self.s.phase]

    def commanded_g(self):
        """Pull-up G komutu — g_limit ile clamp (aşım guard)."""
        return min(self.p.pullup_g, self.p.g_limit)

    def commanded_pitch(self):
        if self.s.phase == DALIS or self.s.phase == QR:
            return self.p.dive_pitch_deg
        return 0.0

    def update(self, alt_agl, airspeed, aligned=True, qr_found=False, qr_text=""):
        """Bir kare: irtifa/hız/QR girdisiyle faz ilerlet. (phase, detail) döndürür."""
        p, s = self.p, self.s

        if s.phase == INTIKAL:
            # 100m'ye tırman + hedefe hizalan (Pure Pursuit). Hazırsa dalışa geç.
            if alt_agl >= p.climb_alt_m and aligned:
                s.phase = DALIS
                s.detail = "dalış −45°"

        elif s.phase == DALIS:
            # −45° dalış; QR irtifasına inince QR fazına
            if alt_agl <= p.qr_start_alt_m:
                s.phase = QR
                s.detail = "QR okuma"

        elif s.phase == QR:
            if qr_found:
                s.qr_text = qr_text
                s.phase = PULLUP
                s.detail = f"QR bulundu: {qr_text} → pull-up"
            elif alt_agl <= p.min_pullup_alt_m:
                # KESİN GÜVENLİK: QR bulunamadı ama min irtifa → her halükarda pull-up
                s.phase = PULLUP
                s.detail = "min-alt güvenlik pull-up (QR yok)"

        elif s.phase == PULLUP:
            # 2.7G (≤3 clamp) ile toparlan; G izle; güvenli irtifaya çıkınca değerlendir
            g = self.commanded_g()
            s.max_g_seen = max(s.max_g_seen, g)
            if alt_agl >= p.pullup_exit_alt_m:
                if s.qr_text:
                    s.phase = DONE
                    s.detail = f"kamikaze tamam (QR: {s.qr_text})"
                else:
                    s.attempts += 1
                    if s.attempts >= p.max_attempts:
                        s.phase = DONE
                        s.detail = "kamikaze bitti (QR yok, 2 deneme)"
                    else:
                        s.phase = INTIKAL
                        s.detail = f"tekrar dene ({s.attempts}/{p.max_attempts})"
        return s.phase, s.detail

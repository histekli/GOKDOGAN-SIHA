"""GÖKDOĞAN kilit denetimi kuralları (SAD §7/§12, KESIN_PLAN §7). Saf Python — test edilebilir.

500 puanlık çekirdek. Kamera 1920×1200, merkez (960,600). Tüm eşikler PARAMETRE (sihirli sayı yok).

Kurallar (KTR):
  1. Merkez     — hedef merkezi, ekran ortasındaki kilit dörtgeni içinde (genişlik W·lock_w, yükseklik H·lock_h).
  2. Boyut      — hedef bbox alanı ≥ %eşik (kilit dörtgeni alanına göre) — yeterince büyük/yakın.
  3. İçerme     — hedefin ≥%90'ı kilit dörtgeni içinde (KESIN_PLAN "IoU≥0.9" pratik yorumu: containment).
  4. Yerdeki hedef reddi — kendi irtifamız min üstünde (yerdeyken/çok alçakken kilit yok).
  5. Otonom şart — yalnız otonom modda geçerli.
  + Zaman penceresi — 5s pencerede ≥4s kesintisiz (200ms tolerans, baş/bitişte yok).
  + last_locked_id — aynı hedefe ardışık kilit yasak.
"""
from dataclasses import dataclass, field

FRAME_W = 1920.0
FRAME_H = 1200.0


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def area(self):
        return max(0.0, self.w) * max(0.0, self.h)

    @property
    def cx(self):
        return self.x + self.w / 2.0

    @property
    def cy(self):
        return self.y + self.h / 2.0


def intersection_area(a: Box, b: Box) -> float:
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x + a.w, b.x + b.w)
    y2 = min(a.y + a.h, b.y + b.h)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return (x2 - x1) * (y2 - y1)


def iou(a: Box, b: Box) -> float:
    inter = intersection_area(a, b)
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


@dataclass
class LockParams:
    frame_w: float = FRAME_W
    frame_h: float = FRAME_H
    lock_w_frac: float = 0.5       # kilit dörtgeni genişliği (ekranın oranı) — "yatay≤W/2"
    lock_h_frac: float = 0.5       # kilit dörtgeni yüksekliği — "dikey≤H/2"
    size_min_frac: float = 0.06    # bbox alanı / kilit dörtgeni alanı ≥ %6
    containment_min: float = 0.90  # hedefin kilit dörtgeni içinde kalma oranı ≥ %90
    window_s: float = 5.0
    valid_s: float = 4.0
    tolerance_s: float = 0.2       # tek boşluk toleransı (baş/bitişte yok)
    min_lock_alt_m: float = 5.0    # bu irtifanın altında kilit yok (yerdeki hedef/yerde reddi)

    def lock_rect(self) -> Box:
        w = self.frame_w * self.lock_w_frac
        h = self.frame_h * self.lock_h_frac
        return Box((self.frame_w - w) / 2.0, (self.frame_h - h) / 2.0, w, h)


# ---- Anlık kurallar (saf fonksiyonlar) ----

def rule_center(box: Box, p: LockParams) -> bool:
    """Kural 1: hedef merkezi kilit dörtgeni içinde."""
    r = p.lock_rect()
    return r.x <= box.cx <= r.x + r.w and r.y <= box.cy <= r.y + r.h


def rule_size(box: Box, p: LockParams) -> bool:
    """Kural 2: hedef bbox alanı / kilit dörtgeni alanı ≥ eşik."""
    r = p.lock_rect()
    if r.area <= 0:
        return False
    return (box.area / r.area) >= p.size_min_frac


def rule_containment(box: Box, p: LockParams) -> bool:
    """Kural 3: hedefin ≥%90'ı kilit dörtgeni içinde (KESIN_PLAN IoU≥0.9 pratik yorumu)."""
    if box.area <= 0:
        return False
    return (intersection_area(box, p.lock_rect()) / box.area) >= p.containment_min


def rule_not_ground(aircraft_alt_m: float, p: LockParams) -> bool:
    """Kural 4: kendi irtifamız min üstünde (yerdeyken kilit yok)."""
    return aircraft_alt_m >= p.min_lock_alt_m


def rule_autonomous(is_autonomous: bool) -> bool:
    """Kural 5: otonom mod şartı."""
    return bool(is_autonomous)


def instant_ok(box: Box, aircraft_alt_m: float, is_autonomous: bool, p: LockParams) -> bool:
    """Anlık (tek kare) tüm konum/koşul kuralları sağlanıyor mu."""
    return (
        rule_center(box, p)
        and rule_size(box, p)
        and rule_containment(box, p)
        and rule_not_ground(aircraft_alt_m, p)
        and rule_autonomous(is_autonomous)
    )


@dataclass
class LockResult:
    valid: bool
    progress_s: float
    target_id: int
    box: Box
    reason: str = ""


@dataclass
class LockValidator:
    """Zaman penceresi + last_locked_id durum makinesi. process() her karede çağrılır."""
    p: LockParams = field(default_factory=LockParams)
    last_locked_id: int = -1
    _target_id: int = -1
    _start_t: float = None
    _last_on_t: float = None

    def reset_attempt(self):
        self._start_t = None
        self._last_on_t = None

    def process(self, t: float, target_id: int, box: Box,
                aircraft_alt_m: float, is_autonomous: bool) -> LockResult:
        # Hedef değişti → yeni deneme
        if target_id != self._target_id:
            self._target_id = target_id
            self.reset_attempt()

        # Aynı hedefe ardışık kilit yasak (last_locked_id)
        forbidden = (target_id == self.last_locked_id)
        on = (not forbidden) and instant_ok(box, aircraft_alt_m, is_autonomous, self.p)

        if on:
            if self._start_t is None:
                self._start_t = t
                self._last_on_t = t
            elif (t - self._last_on_t) <= self.p.tolerance_s:
                self._last_on_t = t                 # boşluk toleransta → devam
            else:
                self._start_t = t                   # boşluk büyük → yeniden başla
                self._last_on_t = t
        else:
            # on değil: toleransı aşan boşluk → deneme kırılır
            if self._start_t is not None and (t - self._last_on_t) > self.p.tolerance_s:
                self.reset_attempt()

        progress = (self._last_on_t - self._start_t) if self._start_t is not None else 0.0
        progress = min(progress, self.p.window_s)

        if on and progress >= self.p.valid_s:
            self.last_locked_id = target_id         # bu hedef artık ardışık yasak
            self.reset_attempt()
            self._target_id = -1
            return LockResult(True, self.p.valid_s, target_id, box, "geçerli kilit")

        reason = "forbidden(last_locked_id)" if forbidden else ("on-target" if on else "off-target")
        return LockResult(False, progress, target_id, box, reason)

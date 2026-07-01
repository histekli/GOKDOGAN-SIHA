"""GÖKDOĞAN — ENU↔NED çerçeve dönüşümleri (Python). SAD §8.

KIRMIZI ÇİZGİ (prompt §2.4): ENU↔NED dönüşümü TEK YERDE. Başka hiçbir yerde elle
yaw/koordinat çevirme YOK — klasik kontrol-bozan hata kaynağı.

- Pozisyon/hız: ENU (x=Doğu, y=Kuzey, z=Yukarı)  ↔  NED (x=Kuzey, y=Doğu, z=Aşağı)
- Açı: ENU yaw = Doğu'dan CCW  ·  NED heading = Kuzey'den CW  →  yaw_enu = π/2 − heading_ned
- C++ karşılığı: frames.hpp (birebir aynı — test round-trip ile doğrulanır).
"""
import math

TWO_PI = 2.0 * math.pi
HALF_PI = 0.5 * math.pi


def wrap_to_pi(angle: float) -> float:
    """Açıyı (−π, π] aralığına sar."""
    a = math.fmod(angle + math.pi, TWO_PI)
    if a <= 0.0:
        a += TWO_PI
    return a - math.pi


def wrap_to_2pi(angle: float) -> float:
    """Açıyı [0, 2π) aralığına sar (heading konvansiyonu)."""
    a = math.fmod(angle, TWO_PI)
    if a < 0.0:
        a += TWO_PI
    return a


# ---- Pozisyon / hız (self-inverse: aynı dönüşüm her iki yönde) -------------

def enu_to_ned(east: float, north: float, up: float):
    """ENU → NED. (E,N,U) → (N,E,−U)."""
    return (north, east, -up)


def ned_to_enu(north: float, east: float, down: float):
    """NED → ENU. (N,E,D) → (E,N,−D)."""
    return (east, north, -down)


def enu_vel_to_ned(ve: float, vn: float, vu: float):
    """ENU hız → NED hız (pozisyonla aynı eksen dönüşümü)."""
    return enu_to_ned(ve, vn, vu)


def ned_vel_to_enu(vn: float, ve: float, vd: float):
    """NED hız → ENU hız."""
    return ned_to_enu(vn, ve, vd)


# ---- Açı (yaw / heading) --------------------------------------------------

def yaw_enu_from_heading_ned(heading_ned: float) -> float:
    """NED heading (Kuzey'den CW) → ENU yaw (Doğu'dan CCW). (−π, π] döndürür."""
    return wrap_to_pi(HALF_PI - heading_ned)


def heading_ned_from_yaw_enu(yaw_enu: float) -> float:
    """ENU yaw (Doğu'dan CCW) → NED heading (Kuzey'den CW). [0, 2π) döndürür."""
    return wrap_to_2pi(HALF_PI - yaw_enu)

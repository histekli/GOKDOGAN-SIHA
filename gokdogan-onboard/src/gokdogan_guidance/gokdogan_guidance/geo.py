"""Coğrafi yardımcılar (SAD §11): flat-Earth WGS-84 → yerel NED, mesafe/kerteriz, lead-angle.

Küçük savaş alanı ölçeğinde (< birkaç km) flat-Earth yeterli (KESIN_PLAN §7). Saf Python.
NED: x=Kuzey, y=Doğu (metre). ENU dönüşümü için frames.py.
"""
import math

_R_EARTH = 6378137.0            # WGS-84 ekvator yarıçapı (m)
_DEG = math.pi / 180.0


def ll_to_ned(lat, lon, ref_lat, ref_lon):
    """(lat,lon) → referans noktaya göre yerel (north, east) metre (flat-Earth)."""
    north = (lat - ref_lat) * _DEG * _R_EARTH
    east = (lon - ref_lon) * _DEG * _R_EARTH * math.cos(ref_lat * _DEG)
    return north, east


def ned_to_ll(north, east, ref_lat, ref_lon):
    """Yerel (north,east) → (lat,lon)."""
    lat = ref_lat + (north / (_DEG * _R_EARTH))
    lon = ref_lon + (east / (_DEG * _R_EARTH * math.cos(ref_lat * _DEG)))
    return lat, lon


def distance(lat1, lon1, lat2, lon2):
    """İki nokta arası yatay mesafe (m)."""
    n, e = ll_to_ned(lat2, lon2, lat1, lon1)
    return math.hypot(n, e)


def bearing_rad(lat1, lon1, lat2, lon2):
    """1→2 kerteriz (NED, Kuzey'den CW, [0,2π))."""
    n, e = ll_to_ned(lat2, lon2, lat1, lon1)
    return math.atan2(e, n) % (2 * math.pi)


def angle_diff(a, b):
    """En kısa açı farkı (a−b), (−π, π]."""
    d = (a - b) % (2 * math.pi)
    if d > math.pi:
        d -= 2 * math.pi
    return d


def lead_point(tgt_lat, tgt_lon, tgt_speed, tgt_heading_rad, t_int):
    """Hedefin t_int saniye sonraki tahmini konumu (sabit hız/yön). (lat, lon)."""
    n = tgt_speed * t_int * math.cos(tgt_heading_rad)
    e = tgt_speed * t_int * math.sin(tgt_heading_rad)
    return ned_to_ll(n, e, tgt_lat, tgt_lon)


def lead_intercept_time(own_lat, own_lon, own_speed, tgt_lat, tgt_lon):
    """Basit kesişim süresi tahmini: mesafe / kendi hızımız (kaba). t_int (s)."""
    d = distance(own_lat, own_lon, tgt_lat, tgt_lon)
    if own_speed <= 0.1:
        return 0.0
    return d / own_speed

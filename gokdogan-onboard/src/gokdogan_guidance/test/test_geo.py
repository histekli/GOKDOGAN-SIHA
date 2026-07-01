"""Coğrafi yardımcı testleri (SAD §11): flat-Earth NED round-trip, mesafe, kerteriz, lead."""
import math

import pytest

from gokdogan_guidance import geo

REF_LAT, REF_LON = 39.90, 32.80


def test_ned_roundtrip():
    for dn, de in [(100.0, 50.0), (-500.0, 300.0), (0.0, 0.0)]:
        lat, lon = geo.ned_to_ll(dn, de, REF_LAT, REF_LON)
        n, e = geo.ll_to_ned(lat, lon, REF_LAT, REF_LON)
        assert n == pytest.approx(dn, abs=1e-3)
        assert e == pytest.approx(de, abs=1e-3)


def test_distance_known():
    # ~100m kuzey
    lat2, lon2 = geo.ned_to_ll(100.0, 0.0, REF_LAT, REF_LON)
    assert geo.distance(REF_LAT, REF_LON, lat2, lon2) == pytest.approx(100.0, abs=0.5)


def test_bearing_cardinal():
    north = geo.ned_to_ll(100.0, 0.0, REF_LAT, REF_LON)
    east = geo.ned_to_ll(0.0, 100.0, REF_LAT, REF_LON)
    assert geo.bearing_rad(REF_LAT, REF_LON, *north) == pytest.approx(0.0, abs=1e-3)      # Kuzey
    assert geo.bearing_rad(REF_LAT, REF_LON, *east) == pytest.approx(math.pi / 2, abs=1e-3)  # Doğu


def test_angle_diff():
    assert geo.angle_diff(0.1, 6.2) == pytest.approx(0.1 - 6.2 + 2 * math.pi, abs=1e-6)


def test_lead_point_moves_target():
    # Hedef doğuya 20 m/s, 5s → ~100m doğu
    lat, lon = geo.lead_point(REF_LAT, REF_LON, 20.0, math.pi / 2, 5.0)
    n, e = geo.ll_to_ned(lat, lon, REF_LAT, REF_LON)
    assert e == pytest.approx(100.0, abs=1.0)
    assert abs(n) < 1.0

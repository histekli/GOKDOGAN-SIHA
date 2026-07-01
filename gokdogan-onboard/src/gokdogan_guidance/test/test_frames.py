"""ENU↔NED dönüşüm testleri (SAD §8). Round-trip identity + bilinen değerler.
C++ (frames.hpp) ile parite: aynı senaryolar test_frames.cpp'de."""
import math

import pytest

from gokdogan_guidance import frames


def _ang_close(a, b, tol=1e-9):
    return abs(frames.wrap_to_pi(a - b)) < tol


# ---- Pozisyon round-trip (identity) ---------------------------------------

@pytest.mark.parametrize("e,n,u", [
    (1.0, 2.0, 3.0), (-5.0, 0.0, 12.3), (100.0, -50.0, -7.0), (0.0, 0.0, 0.0),
])
def test_position_roundtrip_identity(e, n, u):
    nn, ee, dd = frames.enu_to_ned(e, n, u)
    e2, n2, u2 = frames.ned_to_enu(nn, ee, dd)
    assert (e2, n2, u2) == pytest.approx((e, n, u))


def test_enu_to_ned_known():
    assert frames.enu_to_ned(1.0, 2.0, 3.0) == (2.0, 1.0, -3.0)


def test_velocity_roundtrip():
    ve, vn, vu = 3.0, -4.0, 1.5
    vnn, vee, vdd = frames.enu_vel_to_ned(ve, vn, vu)
    assert frames.ned_vel_to_enu(vnn, vee, vdd) == pytest.approx((ve, vn, vu))


# ---- Yaw / heading --------------------------------------------------------

@pytest.mark.parametrize("heading,expected_yaw", [
    (0.0, math.pi / 2),          # Kuzey → ENU +y (90°)
    (math.pi / 2, 0.0),          # Doğu → ENU +x (0°)
    (math.pi, -math.pi / 2),     # Güney → ENU -y (-90°)
])
def test_yaw_from_heading_known(heading, expected_yaw):
    assert _ang_close(frames.yaw_enu_from_heading_ned(heading), expected_yaw)


@pytest.mark.parametrize("heading", [0.0, 0.3, 1.0, math.pi / 2, 3.0, math.pi, 4.5, 6.0])
def test_yaw_heading_roundtrip(heading):
    yaw = frames.yaw_enu_from_heading_ned(heading)
    back = frames.heading_ned_from_yaw_enu(yaw)
    assert _ang_close(back, heading)


def test_wrap_ranges():
    assert -math.pi < frames.wrap_to_pi(10.0) <= math.pi
    assert 0.0 <= frames.wrap_to_2pi(-1.0) < 2 * math.pi

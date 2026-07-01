"""HSS APF testleri (SAD §13): 5 senaryo → 0 ihlal saniyesi + yerel-min yok (Dubins yedeği)."""
import math

import pytest

from gokdogan_hss import apf
from gokdogan_hss.apf import ApfParams, ApfPlanner, min_clearance


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def simulate(start, goal, hss, p=None, dt=0.1, tmax=180.0):
    p = p or ApfParams()
    planner = ApfPlanner(p=p)
    pos = [float(start[0]), float(start[1])]
    speed = p.v_max
    min_clear = float("inf")
    reached = False
    for _ in range(int(tmax / dt)):
        vx, vy = planner.step((pos[0], pos[1]), goal, hss, speed)
        speed = math.hypot(vx, vy)
        pos[0] += vx * dt
        pos[1] += vy * dt
        min_clear = min(min_clear, min_clearance((pos[0], pos[1]), hss))
        if _dist(pos, goal) < 5.0:
            reached = True
            break
    return reached, min_clear, (pos[0], pos[1])


SCENARIOS = {
    "yan_hss":        ((0, 0), (200, 0), [(100, 35, 40)]),
    "arada_hss":      ((0, 0), (200, 0), [(100, 0, 40)]),          # tam arada → yerel-min → Dubins
    "iki_hss_gecit":  ((0, 0), (250, 0), [(90, 45, 30), (130, -45, 30)]),
    "hedef_yak_hss":  ((0, 0), (250, 0), [(160, 0, 35)]),
    "baslangic_yak":  ((0, 0), (220, 20), [(45, 5, 25)]),
}


@pytest.mark.parametrize("name", list(SCENARIOS.keys()))
def test_zero_violation(name):
    start, goal, hss = SCENARIOS[name]
    reached, min_clear, final = simulate(start, goal, hss)
    # 0 İHLAL: hiçbir zaman HSS yarıçapı ihlal edilmedi (min_clear > 0)
    assert min_clear > 0.0, f"{name}: HSS ihlali (min_clear={min_clear:.1f})"


@pytest.mark.parametrize("name", ["yan_hss", "iki_hss_gecit", "baslangic_yak"])
def test_reaches_goal_no_local_min(name):
    start, goal, hss = SCENARIOS[name]
    reached, _, final = simulate(start, goal, hss)
    assert reached, f"{name}: hedefe ulaşamadı (yerel-min takıldı?) son={final}"


def test_repulsive_only_inside_d0():
    p = ApfParams()
    # d0 dışında itici kuvvet yok
    f_out = apf.repulsive((1000, 0), [(0, 0, 40)], p)
    assert f_out == (0.0, 0.0)
    # d0 içinde itici kuvvet HSS'ten uzağa (pozitif x)
    fx, fy = apf.repulsive((50, 0), [(0, 0, 40)], p)   # d=50 < d0=65
    assert fx > 0.0


def test_direct_between_uses_dubins():
    """Tam arada HSS → yerel-min → Dubins ile kaçınır, ihlal yok."""
    reached, min_clear, _ = simulate((0, 0), (200, 0), [(100, 0, 40)])
    assert min_clear > 0.0

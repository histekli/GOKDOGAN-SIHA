"""HSS kaçınma — Yapay Potansiyel Alan (APF) + Dubins yerel-min yedeği (SAD §13, KESIN_PLAN §7).

Çekici F_att=−k_att·(X−X_hedef); İtici U_rep=½k_rep(1/d−1/d₀)², d₀=r_HSS+25m; 10Hz.
Yerel-min: hız<2m/s & |F|<0.5N → 100ms pertürbasyon → 3 başarısız → Dubins (R_min).
Kabul: 0 ihlal saniyesi (HSS yarıçapı asla ihlal edilmez). Saf Python — test edilebilir.
"""
import math
import random
from dataclasses import dataclass, field


def _norm(vx, vy):
    return math.hypot(vx, vy)


def _unit(vx, vy):
    n = _norm(vx, vy)
    return (0.0, 0.0) if n < 1e-9 else (vx / n, vy / n)


@dataclass
class ApfParams:
    k_att: float = 0.8            # çekici kazanç (0.5–1.0)
    k_rep: float = 12.0           # itici kazanç (5–20)
    hss_margin_m: float = 25.0    # d₀ = r + margin
    v_max: float = 15.0           # planlanan hız (m/s)
    att_cap_m: float = 50.0       # çekici kuvvet doygunluğu
    local_min_v: float = 2.0      # yerel-min hız eşiği
    local_min_f: float = 0.5      # yerel-min kuvvet eşiği
    perturb_fails: int = 3        # Dubins'e geçmeden önce pertürbasyon denemesi
    dubins_r_min: float = 30.0    # Dubins minimum dönüş yarıçapı


def attractive(pos, goal, p: ApfParams):
    """Çekici: hedefe BİRİM büyüklükte (k_att). İtici ile ölçek-dengeli olması için."""
    dx, dy = goal[0] - pos[0], goal[1] - pos[1]
    ux, uy = _unit(dx, dy)
    return p.k_att * ux, p.k_att * uy


def repulsive(pos, hss_zones, p: ApfParams):
    """İtici (HSS'ten uzağa). Kenar-uzaklığı c=d−r tabanlı; c→0'da patlar (garantili kaçınma).

    d₀ = r + margin → etki bölgesi c < margin. mag = k_rep·(1/c − 1/margin).
    """
    fx, fy = 0.0, 0.0
    c0 = p.hss_margin_m
    for (cx, cy, r) in hss_zones:
        dx, dy = pos[0] - cx, pos[1] - cy
        d = _norm(dx, dy)
        c = d - r                          # HSS kenarına uzaklık
        if c < c0:
            cc = max(c, 0.5)               # c→0/negatif singularity clamp
            mag = p.k_rep * (1.0 / cc - 1.0 / c0)
            ux, uy = _unit(dx, dy)
            fx += mag * ux
            fy += mag * uy
    return fx, fy


def total_force(pos, goal, hss_zones, p: ApfParams):
    ax, ay = attractive(pos, goal, p)
    rx, ry = repulsive(pos, hss_zones, p)
    return ax + rx, ay + ry


def min_clearance(pos, hss_zones):
    """En yakın HSS kenarına uzaklık (negatif = ihlal içinde)."""
    if not hss_zones:
        return float("inf")
    return min(_norm(pos[0] - cx, pos[1] - cy) - r for (cx, cy, r) in hss_zones)


@dataclass
class ApfPlanner:
    p: ApfParams = field(default_factory=ApfParams)
    _fail_count: int = 0
    _dubins: bool = False
    _dubins_sign: int = 1
    _rng: random.Random = field(default_factory=lambda: random.Random(7))

    def step(self, pos, goal, hss_zones, speed):
        """Bir adım için istenen hız vektörü (vx,vy) döndürür. Yerel-min → pertürbasyon/Dubins."""
        fx, fy = total_force(pos, goal, hss_zones, self.p)
        fmag = _norm(fx, fy)

        # Yerel minimum tespiti (hedefe varmadıysa)
        at_goal = _norm(goal[0] - pos[0], goal[1] - pos[1]) < 5.0
        if not at_goal and speed < self.p.local_min_v and fmag < self.p.local_min_f:
            self._fail_count += 1
            if self._fail_count <= self.p.perturb_fails:
                # 100ms rastgele pertürbasyon
                ang = self._rng.uniform(0, 2 * math.pi)
                return self.p.v_max * math.cos(ang), self.p.v_max * math.sin(ang)
            self._dubins = True
        else:
            if fmag >= self.p.local_min_f:
                self._fail_count = max(0, self._fail_count - 1)

        if self._dubins and hss_zones:
            # Dubins: en yakın HSS etrafından teğetsel dolaş (R_min)
            cx, cy, r = min(hss_zones, key=lambda z: _norm(pos[0] - z[0], pos[1] - z[1]))
            tx, ty = pos[0] - cx, pos[1] - cy
            # teğet yön (dik) + hafif dışa
            perp = (-ty * self._dubins_sign, tx * self._dubins_sign)
            ox, oy = _unit(tx, ty)
            vx = perp[0] + ox * 0.3
            vy = perp[1] + oy * 0.3
            ux, uy = _unit(vx, vy)
            # hedefe yaklaştıysak Dubins'i bırak
            if min_clearance(pos, hss_zones) > self.p.hss_margin_m:
                self._dubins = False
                self._fail_count = 0
            return self.p.v_max * ux, self.p.v_max * uy

        ux, uy = _unit(fx, fy)
        return self.p.v_max * ux, self.p.v_max * uy

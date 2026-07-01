"""Güdüm denetleyicileri (SAD §11): PID (anti-windup), PN (a_c=N·V_c·λ̇), rate-limit+LPF, faz-FSM.

Hassas faz: piksel hatası → PID → açı komutu. Kaba faz: PN uzun-vadeli yön. Saf Python.
KIRMIZI ÇİZGİ: sihirli sayı yok (kazanç/limit parametre); PN'de V_c≈0 guard; PID windup clamp.
"""
import math


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


class PID:
    """Anti-windup'lı PID. update(error, dt) → çıkış (out_min..out_max)."""

    def __init__(self, kp, ki, kd, out_min, out_max, i_limit=None):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.out_min, self.out_max = out_min, out_max
        self.i_limit = i_limit if i_limit is not None else abs(out_max)
        self._i = 0.0
        self._prev_err = None

    def reset(self):
        self._i = 0.0
        self._prev_err = None

    def update(self, error, dt):
        if dt <= 0:
            dt = 1e-3
        self._i += error * dt
        self._i = clamp(self._i, -self.i_limit, self.i_limit)   # integral anti-windup clamp
        d = 0.0 if self._prev_err is None else (error - self._prev_err) / dt
        self._prev_err = error
        raw = self.kp * error + self.ki * self._i + self.kd * d
        out = clamp(raw, self.out_min, self.out_max)
        # Saturation back-calc: doymuşsa integral birikimini geri al (windup önle)
        if raw != out:
            self._i -= (raw - out) * dt
            self._i = clamp(self._i, -self.i_limit, self.i_limit)
        return out


def pn_accel(v_closing, los_rate, n=4.0, v_eps=0.5):
    """Oransal seyrüsefer ivmesi a_c = N·V_c·λ̇. V_c≈0 → 0 (divide/degenerate guard)."""
    if abs(v_closing) < v_eps:
        return 0.0
    return n * v_closing * los_rate


class LosRate:
    """Ardışık kerterizlerden görüş-hattı açısal hızı λ̇ (rad/s)."""

    def __init__(self):
        self._prev = None

    def update(self, bearing_rad, dt):
        if self._prev is None or dt <= 0:
            self._prev = bearing_rad
            return 0.0
        d = (bearing_rad - self._prev + math.pi) % (2 * math.pi) - math.pi
        self._prev = bearing_rad
        return d / dt


class RateLimiter:
    """Komut değişim hızını sınırla (Δφ_max °/s → rad/s). Kanada zarar veren ani komut yok."""

    def __init__(self, max_rate):
        self.max_rate = max_rate
        self._y = None

    def reset(self, value=None):
        self._y = value

    def update(self, target, dt):
        if self._y is None:
            self._y = target
            return self._y
        max_step = self.max_rate * dt
        self._y += clamp(target - self._y, -max_step, max_step)
        return self._y


class LPF:
    """Birinci derece alçak-geçiren: y = α·x + (1−α)·y_prev."""

    def __init__(self, alpha):
        self.alpha = alpha
        self._y = None

    def reset(self, value=None):
        self._y = value

    def update(self, x):
        self._y = x if self._y is None else self.alpha * x + (1 - self.alpha) * self._y
        return self._y


# ---- Faz FSM (kaba ↔ hassas, histerezis → flapping yok) ----
COARSE, PRECISE = 0, 1
_PHASE_NAMES = {COARSE: "COARSE", PRECISE: "PRECISE"}


class PhaseFSM:
    """d<enter_d & taze → PRECISE; d>exit_d | bayat → COARSE. enter<exit → flapping yok."""

    def __init__(self, enter_d=480.0, exit_d=520.0):
        assert enter_d < exit_d, "histerezis için enter_d < exit_d olmalı"
        self.enter_d = enter_d
        self.exit_d = exit_d
        self.phase = COARSE

    def update(self, distance_m, bbox_fresh):
        if self.phase == COARSE:
            if distance_m < self.enter_d and bbox_fresh:
                self.phase = PRECISE
        else:  # PRECISE
            if distance_m > self.exit_d or not bbox_fresh:
                self.phase = COARSE
        return self.phase

    @property
    def name(self):
        return _PHASE_NAMES[self.phase]


def estimate_distance_pinhole(bbox_w_px, real_w_m, focal_px):
    """Pinhole ile mesafe: d = W·f / W_piksel (SAD §11: W≈2m, W_piksel≈1100→~50m)."""
    if bbox_w_px <= 1e-6:
        return float("inf")
    return real_w_m * focal_px / bbox_w_px

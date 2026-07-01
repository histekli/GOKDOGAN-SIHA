"""Hedef seçimi (SAD §11, KESIN_PLAN §7). Saf Python — test edilebilir.

S = 0.40·P_mesafe + 0.30·P_açı + 0.20·P_geçmiş − 0.10·P_risk.
Ağırlıklar GCS AutonomyOptions'tan (config, mission_link) override edilebilir.
lead-angle: hedefin kesişim anındaki tahmini konumu (zaman_farki + hız/yön ile).
"""
import math
from dataclasses import dataclass

from gokdogan_guidance import geo


@dataclass
class Weights:
    mesafe: float = 0.40
    aci: float = 0.30
    gecmis: float = 0.20
    risk: float = 0.10


@dataclass
class SelectorParams:
    d_ref_m: float = 1000.0     # P_mesafe normalizasyonu
    t_ref_s: float = 2.0        # P_geçmiş (zaman_farki tazeliği)
    hss_margin_m: float = 25.0  # risk d0 = yarıçap + margin (SAD §13)


def _clamp01(x):
    return max(0.0, min(1.0, x))


@dataclass
class Opponent:
    takim_no: int
    lat: float
    lon: float
    alt: float = 0.0
    heading_rad: float = 0.0
    speed: float = 0.0
    zaman_farki: float = 0.0


@dataclass
class OwnState:
    lat: float
    lon: float
    speed: float = 0.0
    heading_rad: float = 0.0


def p_mesafe(own, opp, p):
    d = geo.distance(own.lat, own.lon, opp.lat, opp.lon)
    return _clamp01(1.0 - d / p.d_ref_m), d


def p_aci(own, opp):
    brg = geo.bearing_rad(own.lat, own.lon, opp.lat, opp.lon)
    err = abs(geo.angle_diff(brg, own.heading_rad))
    return _clamp01(1.0 - err / math.pi)


def p_gecmis(opp, p):
    return _clamp01(1.0 - opp.zaman_farki / p.t_ref_s)


def p_risk(opp, hss_zones, p):
    """En yakın HSS'e göre risk [0,1]. hss_zones: [(lat,lon,radius),...]."""
    risk = 0.0
    for (hlat, hlon, r) in hss_zones:
        d0 = r + p.hss_margin_m
        d = geo.distance(opp.lat, opp.lon, hlat, hlon)
        risk = max(risk, _clamp01(1.0 - d / d0)) if d0 > 0 else risk
    return risk


def score(own, opp, hss_zones, w: Weights, p: SelectorParams):
    pm, d = p_mesafe(own, opp, p)
    pa = p_aci(own, opp)
    pg = p_gecmis(opp, p)
    pr = p_risk(opp, hss_zones, p)
    s = w.mesafe * pm + w.aci * pa + w.gecmis * pg - w.risk * pr
    return s, {"d": d, "P_mesafe": pm, "P_aci": pa, "P_gecmis": pg, "P_risk": pr}


@dataclass
class Selection:
    opponent: Opponent
    score: float
    lead_lat: float
    lead_lon: float
    detail: dict


def select_target(own, opponents, hss_zones=(), w=None, p=None):
    """En yüksek skorlu rakibi seç + lead-angle kesişim noktası. Yoksa None."""
    w = w or Weights()
    p = p or SelectorParams()
    best = None
    for opp in opponents:
        s, det = score(own, opp, hss_zones, w, p)
        if best is None or s > best.score:
            t_int = geo.lead_intercept_time(own.lat, own.lon, own.speed, opp.lat, opp.lon)
            lead_lat, lead_lon = geo.lead_point(
                opp.lat, opp.lon, opp.speed, opp.heading_rad, t_int)
            best = Selection(opp, s, lead_lat, lead_lon, det)
    return best

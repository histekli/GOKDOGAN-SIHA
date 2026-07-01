"""Hedef seçimi testleri (SAD §11): S skoru bileşenleri, seçim, risk, lead-angle."""
import math

from gokdogan_guidance import geo
from gokdogan_target_selector.selector import (
    Opponent, OwnState, Weights, SelectorParams, select_target, score,
)

OWN = OwnState(lat=39.90, lon=32.80, speed=25.0, heading_rad=0.0)


def _opp_at(dn, de, **kw):
    lat, lon = geo.ned_to_ll(dn, de, OWN.lat, OWN.lon)
    return Opponent(takim_no=kw.pop("takim_no", 1), lat=lat, lon=lon, **kw)


def test_closer_scores_higher():
    near = _opp_at(200.0, 0.0)
    far = _opp_at(900.0, 0.0)
    s_near, _ = score(OWN, near, [], Weights(), SelectorParams())
    s_far, _ = score(OWN, far, [], Weights(), SelectorParams())
    assert s_near > s_far


def test_select_picks_best():
    opps = [_opp_at(900.0, 0.0, takim_no=1), _opp_at(150.0, 0.0, takim_no=2)]
    sel = select_target(OWN, opps)
    assert sel.opponent.takim_no == 2       # yakın olan


def test_angle_component_prefers_ahead():
    ahead = _opp_at(300.0, 0.0)             # kuzey (heading 0 ile hizalı)
    side = _opp_at(0.0, 300.0)              # doğu (90° yanda)
    _, da = score(OWN, ahead, [], Weights(), SelectorParams())
    _, ds = score(OWN, side, [], Weights(), SelectorParams())
    assert da["P_aci"] > ds["P_aci"]


def test_risk_reduces_score():
    opp = _opp_at(300.0, 0.0)
    hss_lat, hss_lon = opp.lat, opp.lon     # HSS tam hedefin üstünde → yüksek risk
    s_no, _ = score(OWN, opp, [], Weights(), SelectorParams())
    s_risk, det = score(OWN, opp, [(hss_lat, hss_lon, 50.0)], Weights(), SelectorParams())
    assert det["P_risk"] > 0.5
    assert s_risk < s_no


def test_lead_angle_predicts_intercept():
    # Doğuya 20 m/s giden hedef → lead noktası hedefin doğusunda
    opp = _opp_at(500.0, 0.0, speed=20.0, heading_rad=math.pi / 2)
    sel = select_target(OWN, [opp])
    n, e = geo.ll_to_ned(sel.lead_lat, sel.lead_lon, opp.lat, opp.lon)
    assert e > 5.0                          # doğuya kaymış

"""Senaryo runner testleri (Faz 7, SAD §8/§23).

Kapsam: kabul değerlendirici (GEÇEN + KALAN girdi → kriter gerçekten ayırt ediyor mu),
spec loader (eksik/bozuk), 8 senaryonun HER birinin kabul kriterini karşıladığı + kriterlerin
gevşetilmediği (bir parametre bozulunca senaryo BAŞARISIZ olmalı). Deterministik → CI'da hızlı.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scenario_runner as R  # noqa: E402

SCEN_DIR = pathlib.Path(__file__).resolve().parent / "scenarios"


# --------------------------------------------------------- değerlendirici (saf)


@pytest.mark.parametrize(
    "value,spec,ok",
    [
        (11.0, {"lte": 12.0}, True),
        (12.1, {"lte": 12.0}, False),
        (5, {"gte": 2}, True),
        (1, {"gte": 2}, False),
        ("IDLE", {"eq": "IDLE"}, True),
        ("CRUISE", {"eq": "IDLE"}, False),
        ("RTL", {"in": ["RTL", "LAND"]}, True),
        ("CRUISE", {"in": ["RTL", "LAND"]}, False),
        (5.0, {"between": [0.0, 10.0]}, True),
        (11.0, {"between": [0.0, 10.0]}, False),
    ],
)
def test_check_criterion(value, spec, ok):
    got, _ = R.check_criterion(value, spec)
    assert got is ok


def test_check_criterion_unknown_op():
    ok, detail = R.check_criterion(1.0, {"approx": 1.0})
    assert not ok and "bilinmeyen" in detail


def test_evaluate_missing_metric_fails():
    results, ok = R.evaluate({"foo": {"eq": 1}}, {"bar": 2})
    assert not ok
    assert results[0][0] == "foo" and results[0][1] is False


def test_evaluate_multi_criterion():
    acc = {"a": {"lte": 10}, "b": {"eq": "X"}}
    _, ok = R.evaluate(acc, {"a": 5, "b": "X"})
    assert ok
    _, ok2 = R.evaluate(acc, {"a": 5, "b": "Y"})
    assert not ok2


def test_multi_op_single_criterion():
    # aynı kriterde birden çok operatör → hepsi sağlanmalı
    ok, _ = R.check_criterion(5.0, {"gte": 0.0, "lte": 10.0})
    assert ok
    bad, _ = R.check_criterion(15.0, {"gte": 0.0, "lte": 10.0})
    assert not bad


# ----------------------------------------------------------------- spec loader


def test_load_all_scenarios_valid():
    paths = sorted(SCEN_DIR.glob("*.yaml"))
    assert len(paths) == 8, "8 KTR senaryosu bekleniyor"
    ids = set()
    for p in paths:
        spec = R.load_scenario(str(p))
        assert spec["kind"] in R.SIMULATORS
        ids.add(spec["id"])
    assert len(ids) == 8, "senaryo id'leri benzersiz olmalı"


def test_load_missing_field(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("id: '99'\nname: x\n", encoding="utf-8")  # kind + acceptance yok
    with pytest.raises(ValueError):
        R.load_scenario(str(f))


def test_load_unknown_kind(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("id: '99'\nname: x\nkind: uzay\nacceptance: {}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        R.load_scenario(str(f))


# --------------------------------------------------- 8 senaryo: hepsi GEÇMELİ


def test_all_scenarios_pass():
    for p in sorted(SCEN_DIR.glob("*.yaml")):
        spec = R.load_scenario(str(p))
        res = R.run_scenario(spec)
        assert res["passed"], f"{p.name} beklenmedik şekilde BAŞARISIZ: {res['criteria']}"


# ------------------------------------- kriterler gevşek değil (bozarsak düşer)


def _load(name):
    return R.load_scenario(str(SCEN_DIR / name))


def test_hss_violation_fails_scenario():
    """HSS zonu yolu tamamen kapatacak kadar büyürse (margin ile) ihlal → BAŞARISIZ."""
    spec = _load("04_hss_kacinma.yaml")
    # start [0,0] → goal [0,300]; devasa zon → kaçış zor, kenar-uzaklığı bozulur
    spec["world"]["hss_ne_r"] = [[0.0, 150.0, 149.0]]
    spec["params"]["tmax_s"] = 30.0
    res = R.run_scenario(spec)
    assert not res["passed"]


def test_takeoff_land_overspeed_fails():
    spec = _load("01_otonom_kalkis_inis.yaml")
    spec["world"]["wind_mps"] = 20.0  # 8 + 20 = 28 > 12 sınırı
    res = R.run_scenario(spec)
    assert not res["passed"]


def test_lock_too_far_fails():
    spec = _load("03_coklu_iha_kilit.yaml")
    spec["world"]["opponents"] = [{"range_m": 5000.0, "closing_mps": 5.0}]  # >30s
    res = R.run_scenario(spec)
    assert not res["passed"]


def test_kamikaze_g_limit_holds():
    """Pull-up G komutu her zaman ≤ 3 (clamp guard) — senaryo bunu doğrular."""
    spec = _load("05_kamikaze_tam.yaml")
    res = R.run_scenario(spec)
    assert res["metrics"]["max_g"] <= 3.0
    assert res["passed"]


def test_full_match_low_score_fails():
    spec = _load("06_tam_musabaka.yaml")
    spec["world"]["locks"] = 0
    spec["world"]["kamikazes"] = 0
    res = R.run_scenario(spec)
    assert res["metrics"]["total_score"] <= 800
    assert not res["passed"]


def test_comms_loss_below_threshold_no_failsafe():
    spec = _load("07_haberlesme_kaybi.yaml")
    spec["world"]["loss_duration_s"] = 5.0  # < 10s eşik → tetiklenmez
    res = R.run_scenario(spec)
    assert res["metrics"]["failsafe_triggered"] is False
    assert not res["passed"]  # senaryo failsafe bekliyordu → BAŞARISIZ


def test_battery_triggers_rtl():
    spec = _load("08_batarya_failsafe.yaml")
    res = R.run_scenario(spec)
    assert res["metrics"]["final_state"] == "RTL"
    assert res["metrics"]["trigger_battery_pct"] <= 20.0

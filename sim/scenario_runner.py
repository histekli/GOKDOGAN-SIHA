#!/usr/bin/env python3
"""GÖKDOĞAN senaryo runner — 8 KTR görev testini otomatik koşar (SAD §8/§23, KTR 8.3).

YAML senaryosu (rakip/HSS/QR/rüzgâr + kabul kriterleri) → deterministik simülasyon → metrikler →
kabul değerlendirmesi → JSON rapor. HSS ve kamikaze senaryoları GERÇEK çekirdekleri
(`gokdogan_hss.apf`, `gokdogan_kamikaze.kamikaze_fsm`) sürer; diğerleri fiziğe dayalı kinematik
modeller. Değerlendirici (`evaluate`) saftır → birim-test edilir (geçen VE kalan girdilerle).

Not: Kamera-in-the-loop (görsel-servo kilit) ve sabit-kanat kamikaze dalışı Gazebo/plane
gerektirir → analitik çekirdek koşulur, canlı SITL fidelity ilgili `live_target` make hedefiyle.

Kullanım:
  python3 sim/scenario_runner.py --scenario sim/scenarios/04_hss.yaml
  python3 sim/scenario_runner.py --all sim/scenarios [--report out.json]
"""

import argparse
import glob
import json
import math
import pathlib
import sys

import yaml

# --- Gerçek çekirdekleri reuse et (import-saf modüller: math/dataclass, rclpy YOK) ---
_SRC = pathlib.Path(__file__).resolve().parents[1] / "gokdogan-onboard" / "src"
for _p in ("gokdogan_hss", "gokdogan_kamikaze"):
    _d = str(_SRC / _p)
    if _d not in sys.path:
        sys.path.insert(0, _d)
try:
    from gokdogan_hss.apf import ApfParams, ApfPlanner, min_clearance
except ImportError:  # pragma: no cover
    ApfPlanner = None
try:
    from gokdogan_kamikaze.kamikaze_fsm import KamikazeFsm, KamikazeParams
except ImportError:  # pragma: no cover
    KamikazeFsm = None


# =========================================================================== #
#  Kabul değerlendirici (SAF — birim-test edilir)                             #
# =========================================================================== #


def _op_in(value, target):
    return value in target


def _op_between(value, target):
    lo, hi = target
    return lo <= value <= hi


_OPS = {
    "lte": lambda v, t: v <= t,
    "lt": lambda v, t: v < t,
    "gte": lambda v, t: v >= t,
    "gt": lambda v, t: v > t,
    "eq": lambda v, t: v == t,
    "in": _op_in,
    "between": _op_between,
}


def check_criterion(value, spec):
    """spec: {op: target} (ör {"lte": 12.0}). Tüm operatörler sağlanmalı → (ok, detay)."""
    for op, target in spec.items():
        fn = _OPS.get(op)
        if fn is None:
            return False, f"bilinmeyen operatör '{op}'"
        if not fn(value, target):
            return False, f"{value!r} !{op} {target!r}"
    return True, f"{value!r} ✓"


def evaluate(acceptance, metrics):
    """Her kabul kriterini metriğe karşı denetle → (results, all_ok).

    results: [(ad, ok, detay), ...]. Metrik yoksa o kriter BAŞARISIZ.
    """
    results = []
    for name, spec in acceptance.items():
        if name not in metrics:
            results.append((name, False, "metrik üretilmedi"))
            continue
        ok, detail = check_criterion(metrics[name], spec)
        results.append((name, ok, detail))
    return results, all(ok for _, ok, _ in results)


# =========================================================================== #
#  Senaryo spec loader                                                        #
# =========================================================================== #

REQUIRED_FIELDS = {"id", "name", "kind", "acceptance"}


def load_scenario(path):
    data = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: senaryo bir sözlük olmalı")
    missing = REQUIRED_FIELDS - set(data)
    if missing:
        raise ValueError(f"{path}: eksik alan(lar): {sorted(missing)}")
    if data["kind"] not in SIMULATORS:
        raise ValueError(f"{path}: bilinmeyen kind '{data['kind']}' " f"(geçerli: {sorted(SIMULATORS)})")
    data.setdefault("world", {})
    data.setdefault("params", {})
    return data


# =========================================================================== #
#  Senaryo simülatörleri — her biri metrik sözlüğü döndürür                   #
#  (deterministik; YAML parametreleriyle sonuç değişir → boş/kof pass değil)  #
# =========================================================================== #


def sim_takeoff_land(spec):
    """Otonom kalkış → seyir → iniş. KTR: iniş/otonom hız < 12 m/s (SAD §8)."""
    w, p = spec["world"], spec["params"]
    alt = float(w.get("takeoff_alt_m", 40.0))
    wind = float(w.get("wind_mps", 0.0))
    cruise_speed = float(p.get("cruise_speed_mps", 8.0))
    climb_rate = float(p.get("climb_rate_mps", 2.5))
    descent_rate = float(p.get("descent_rate_mps", 1.5))
    cruise_time = float(p.get("cruise_time_s", 20.0))
    # zaman: tırman + seyir + in
    t = alt / climb_rate + cruise_time + alt / descent_rate
    # yer hızı: seyirde cruise + rüzgâr bileşeni (worst-case toplam)
    max_ground_speed = cruise_speed + wind
    states = ["IDLE", "TAKEOFF", "CRUISE", "LAND", "IDLE"]
    return {
        "max_ground_speed_mps": round(max_ground_speed, 2),
        "landing_vertical_speed_mps": round(descent_rate, 2),
        "mission_time_s": round(t, 1),
        "final_state": states[-1],
        "reached_cruise": True,
        "sequence": states,
    }


def sim_waypoint(spec):
    """Waypoint rota takibi. KTR: çapraz-hata (cross-track) < 5 m (SAD §8)."""
    w, p = spec["world"], spec["params"]
    wps = w.get("waypoints_ne", [[0, 0], [200, 0], [200, 200]])
    wind = float(w.get("wind_mps", 3.0))
    gain = float(p.get("track_gain", 0.9))  # yanal kontrol kazancı (0..1)
    v = float(p.get("speed_mps", 10.0))
    dt = 0.1
    # Basit yanal dinamik: her bacakta çizgiden dik hata; rüzgâr iter, kontrol çeker.
    # Kararlı-durum cross-track ≈ wind / (gain * v) * ölçek; başlangıç ofseti sönümlenir.
    max_ct = 0.0
    for i in range(1, len(wps)):
        a, b = wps[i - 1], wps[i]
        seg = _seg_len(a, b)
        n = max(1, int(seg / (v * dt)))
        ct = _initial_offset(i)  # bacak başı ofset (önceki dönüşten)
        for _ in range(n):
            # rüzgâr diklemesine iter, P-kontrol geri çeker
            ct += (wind * dt) - (gain * ct)
            max_ct = max(max_ct, abs(ct))
    return {
        "max_cross_track_m": round(max_ct, 3),
        "waypoints": len(wps),
        "final_state": "CRUISE",
    }


def sim_lock(spec):
    """Çoklu-İHA kilit. KTR: geçerli kilit < 30 s (SAD §8, KTR 6.1)."""
    w, p = spec["world"], spec["params"]
    opponents = w.get("opponents", [{"range_m": 700.0, "closing_mps": 18.0}])
    detect_range = float(p.get("detect_range_m", 500.0))
    lock_window_s = float(p.get("lock_window_s", 4.0))  # KTR: 4s kesintisiz
    # En yakın/uygun rakibe kilit süresi = menzile kapanma + kilit penceresi
    best = float("inf")
    for opp in opponents:
        d = float(opp.get("range_m", 700.0))
        vc = max(0.1, float(opp.get("closing_mps", 15.0)))
        t_close = max(0.0, (d - detect_range) / vc)
        best = min(best, t_close + lock_window_s)
    return {
        "lock_time_s": round(best, 2),
        "num_opponents": len(opponents),
        "detected": True,
        "final_state": "LOCKING",
    }


def sim_hss(spec):
    """HSS kaçınma — GERÇEK APF çekirdeği. KTR: %100 kaçınma, 0 ihlal saniyesi (SAD §13)."""
    if ApfPlanner is None:  # pragma: no cover
        raise RuntimeError("gokdogan_hss.apf import edilemedi")
    w = spec["world"]
    p = spec["params"]
    start = list(map(float, w.get("start_ne", [0.0, 0.0])))
    goal = list(map(float, w.get("goal_ne", [0.0, 300.0])))
    zones = [tuple(map(float, z)) for z in w.get("hss_ne_r", [[0.0, 150.0, 40.0]])]
    params = ApfParams(
        k_att=float(p.get("k_att", 0.8)),
        k_rep=float(p.get("k_rep", 12.0)),
        hss_margin_m=float(p.get("hss_margin_m", 25.0)),
        v_max=float(p.get("v_max", 12.0)),
    )
    planner = ApfPlanner(p=params)
    pos = list(start)
    dt = float(p.get("dt", 0.1))
    tmax = float(p.get("tmax_s", 180.0))
    alpha = float(p.get("vel_lpf_alpha", 0.3))  # araç atalet/filtre → GERÇEK yer hızı
    min_clear = float("inf")
    violation_s = 0.0
    reached = False
    # step() daima v_max büyüklüğünde KOMUT döndürür; yerel-min tespiti gerçek vground'a bakar.
    # Aracın hızını LPF ile modelle (yön hızla değişince büyüklük düşer → yerel-min tetiklenir).
    vel = [0.0, params.v_max]
    speed = params.v_max
    steps = int(tmax / dt)
    for _ in range(steps):
        cvx, cvy = planner.step(pos, goal, zones, speed)
        vel[0] = alpha * cvx + (1 - alpha) * vel[0]
        vel[1] = alpha * cvy + (1 - alpha) * vel[1]
        speed = math.hypot(vel[0], vel[1])
        pos[0] += vel[0] * dt
        pos[1] += vel[1] * dt
        cl = min_clearance(pos, zones)
        min_clear = min(min_clear, cl)
        if cl < 0:
            violation_s += dt
        if math.hypot(goal[0] - pos[0], goal[1] - pos[1]) < 5.0:
            reached = True
            break
    return {
        "min_clearance_m": round(min_clear, 3),
        "violation_seconds": round(violation_s, 2),
        "reached_goal": reached,
        "final_state": "CRUISE",
    }


def sim_kamikaze(spec):
    """Kamikaze — GERÇEK FSM çekirdeği. KTR: G≤3, QR okundu, pull-up tamam (SAD §12)."""
    if KamikazeFsm is None:  # pragma: no cover
        raise RuntimeError("gokdogan_kamikaze.kamikaze_fsm import edilemedi")
    w, p = spec["world"], spec["params"]
    fsm = KamikazeFsm(KamikazeParams())
    fsm.start()
    alt = float(w.get("start_alt_m", 120.0))
    airspeed = float(p.get("airspeed_mps", 29.0))
    qr_available = bool(w.get("qr_available", True))
    qr_text = str(w.get("qr_text", "GOKDOGAN"))
    dt = 0.1
    max_g = 0.0
    min_alt = alt
    dive_alt_rate = airspeed * math.sin(math.radians(45.0))  # −45° dalış düşey hızı
    got_qr = False
    for _ in range(4000):
        phase = fsm.phase_name
        # irtifa dinamiği: dalış/QR'da alçal, pull-up'ta yüksel
        if phase in ("DALIS", "QR"):
            alt -= dive_alt_rate * dt
        elif phase == "PULLUP":
            alt += 8.0 * dt
        alt = max(0.0, alt)
        min_alt = min(min_alt, alt)
        qr_found = qr_available and phase == "QR" and alt <= 45.0
        got_qr = got_qr or qr_found
        fsm.update(alt, airspeed, aligned=True, qr_found=qr_found, qr_text=qr_text)
        max_g = max(max_g, fsm.s.max_g_seen)
        if fsm.phase_name in ("DONE", "ABORT") or (fsm.phase_name == "PULLUP" and alt >= 80.0):
            break
    return {
        "max_g": round(max(max_g, fsm.commanded_g()), 3),
        "qr_success": got_qr,
        "min_alt_m": round(min_alt, 2),
        "final_phase": fsm.phase_name,
        "result_latency_s": float(p.get("result_latency_s", 1.0)),
    }


def sim_full_match(spec):
    """Tam müsabaka — puan toplamı (KTR 6: kilit 500 / kamikaze 300 / uçuş+telemetri)."""
    w, p = spec["world"], spec["params"]
    locks = int(w.get("locks", 3))
    kamikazes = int(w.get("kamikazes", 1))
    flight_ok = bool(w.get("autonomous_flight_ok", True))
    telemetry_ok = bool(w.get("telemetry_ok", True))
    hss_violations = int(w.get("hss_violation_seconds", 0))
    # KTR puan modeli (SAD/KTR 6): kilit≈250/adet, kamikaze≈300, uçuş 150, telemetri 50, HSS ceza
    score = (
        locks * int(p.get("points_per_lock", 250))
        + kamikazes * int(p.get("points_per_kamikaze", 300))
        + (150 if flight_ok else 0)
        + (50 if telemetry_ok else 0)
        - hss_violations * int(p.get("penalty_per_violation_s", 20))
    )
    return {
        "total_score": score,
        "locks": locks,
        "kamikazes": kamikazes,
        "hss_violation_seconds": hss_violations,
        "final_state": "CRUISE",
    }


def sim_comms_loss(spec):
    """Haberleşme (RF/GCS telemetri) kaybı → failsafe. SAD §18: 10s → RTL (KTR)."""
    w, p = spec["world"], spec["params"]
    loss_s = float(w.get("loss_duration_s", 15.0))
    threshold_s = float(p.get("gcs_fs_threshold_s", 10.0))
    triggered = loss_s >= threshold_s
    reaction = threshold_s + float(p.get("reaction_margin_s", 0.5)) if triggered else float("inf")
    return {
        "failsafe_triggered": triggered,
        "reaction_time_s": round(reaction, 2) if triggered else 9999.0,
        "final_state": "RTL" if triggered else "CRUISE",
    }


def sim_battery(spec):
    """Batarya failsafe. SAD §18/KTR: batarya < %20 → RTL."""
    w, p = spec["world"], spec["params"]
    start_pct = float(w.get("start_battery_pct", 100.0))
    drain_pct_per_s = float(w.get("drain_pct_per_s", 0.5))
    threshold_pct = float(p.get("batt_fs_threshold_pct", 20.0))
    # eşiğe düşme zamanı
    if start_pct <= threshold_pct:
        trigger_pct, t = start_pct, 0.0
    else:
        t = (start_pct - threshold_pct) / max(1e-6, drain_pct_per_s)
        trigger_pct = threshold_pct
    return {
        "trigger_battery_pct": round(trigger_pct, 1),
        "trigger_time_s": round(t, 1),
        "final_state": "RTL",
    }


SIMULATORS = {
    "takeoff_land": sim_takeoff_land,
    "waypoint": sim_waypoint,
    "lock": sim_lock,
    "hss": sim_hss,
    "kamikaze": sim_kamikaze,
    "full_match": sim_full_match,
    "comms_loss": sim_comms_loss,
    "battery": sim_battery,
}


# --- küçük yardımcılar (waypoint) ---


def _seg_len(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _initial_offset(leg_index):
    # her bacak başında dönüşten kalan küçük ofset (deterministik, sönümlenir)
    return 2.0 if leg_index > 1 else 0.0


# =========================================================================== #
#  Koşum + rapor                                                              #
# =========================================================================== #


def run_scenario(spec):
    """Senaryoyu simüle et → metrik → değerlendir → sonuç sözlüğü."""
    metrics = SIMULATORS[spec["kind"]](spec)
    results, ok = evaluate(spec["acceptance"], metrics)
    return {
        "id": spec["id"],
        "name": spec["name"],
        "kind": spec["kind"],
        "passed": ok,
        "metrics": metrics,
        "criteria": [{"name": n, "ok": o, "detail": d} for n, o, d in results],
        "live_target": spec.get("live_target"),
    }


def _print_result(res):
    mark = "✅" if res["passed"] else "❌"
    print(f"{mark} [{res['id']}] {res['name']} ({res['kind']})")
    for c in res["criteria"]:
        cm = "✓" if c["ok"] else "✗"
        print(f"      {cm} {c['name']}: {c['detail']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="GÖKDOĞAN senaryo runner (8 KTR senaryosu)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--scenario", help="tek senaryo YAML yolu")
    g.add_argument("--all", metavar="DIR", help="dizindeki tüm *.yaml senaryolarını koş")
    ap.add_argument("--report", help="JSON rapor yaz")
    args = ap.parse_args(argv)

    if args.scenario:
        paths = [args.scenario]
    else:
        paths = sorted(glob.glob(str(pathlib.Path(args.all) / "*.yaml")))
    if not paths:
        print("senaryo bulunamadı", file=sys.stderr)
        return 2

    results = []
    print("=" * 58)
    print(" GÖKDOĞAN — KTR Senaryo Runner")
    print("=" * 58)
    for path in paths:
        spec = load_scenario(path)
        res = run_scenario(spec)
        results.append(res)
        _print_result(res)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print("-" * 58)
    print(f" SONUÇ: {passed}/{total} senaryo GEÇTİ")
    if args.report:
        pathlib.Path(args.report).write_text(
            json.dumps({"passed": passed, "total": total, "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f" Rapor: {args.report}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

"""mission_link JSON Schema doğrulama testi (Faz 0 dondurma kapısı).

- Şemanın kendisi geçerli JSON Schema (Draft 2020-12).
- Her mesaj türü için geçerli örnek VALİDE olur.
- Bozuk örnekler (eksik zarf, yanlış enum, fazladan alan, aralık dışı) REDDEDİLİR.
- WPF FlightState eşleme alanları şemada mevcut.

Çalıştırma (dev container içinde): pytest -q contracts/test_mission_link_schema.py
"""
import json
import pathlib

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

SCHEMA_PATH = pathlib.Path(__file__).parent / "mission_link.schema.json"


@pytest.fixture(scope="module")
def validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)  # şema kendisi geçerli mi
    return Draft202012Validator(schema)


def _env(t, **body):
    base = {"type": t, "seq": 1, "ts": 1234.5}
    base.update(body)
    return base


VALID = [
    _env("aircraft_vision", target_center_x=960.0, target_center_y=600.0,
         target_width=120.0, target_height=90.0, is_locked=False,
         lock_progress_s=0.0, target_team_number=42, score=0.87,
         fsm_state=3, active_service=1),
    _env("aircraft_vision", target_center_x=None, target_center_y=None,
         target_width=None, target_height=None, is_locked=False, fsm_state=2),
    _env("lock_valid", valid=True, target_id=7, target_team_number=42,
         center=[960.0, 600.0], box={"x": 900.0, "y": 555.0, "w": 120.0, "h": 90.0},
         lock_end_ts=1250.0),
    _env("kamikaze_result", success=True, qr_text="TF-2026-ABC", max_g=2.6, detail="ok"),
    _env("operator_cmd", cmd="START_LOCK"),
    _env("operator_cmd", cmd="SELECT_TARGET", target_id=7),
    _env("server_data",
         opponents=[{"takim_no": 42, "enlem": 39.9, "boylam": 32.8, "irtifa": 100.0,
                     "dikilme": 5.0, "yonelme": 270.0, "yatis": -3.0, "hiz": 25.0,
                     "zaman_farki": 0.2}],
         hss=[{"id": 1, "enlem": 39.91, "boylam": 32.81, "yaricap": 50.0}],
         qr={"lat": 39.92, "lon": 32.82, "alt": 30.0}, server_time=1234.0),
    _env("config", autonomy_weights={"mesafe": 0.40, "aci": 0.30, "gecmis": 0.20, "risk": 0.10}),
    _env("heartbeat", role="onboard"),
]

INVALID = [
    {"type": "aircraft_vision", "seq": 1},                                   # ts + zorunlu alan yok
    _env("aircraft_vision", is_locked=False, fsm_state=99),                  # fsm_state aralık dışı
    _env("aircraft_vision", is_locked=False, fsm_state=2, bogus=1),          # fazladan alan
    _env("operator_cmd", cmd="FLY_TO_MOON"),                                 # enum dışı
    _env("config", autonomy_weights={"mesafe": 0.4}),                        # eksik ağırlık
    _env("server_data",
         opponents=[{"takim_no": 1, "enlem": 39.9, "boylam": 32.8, "dikilme": 120.0}]),  # dikilme>90
    {"type": "unknown_type", "seq": 1, "ts": 0.0},                           # bilinmeyen tür
    _env("lock_valid", valid=True),                                          # target_id yok
]


@pytest.mark.parametrize("msg", VALID)
def test_valid_messages_pass(validator, msg):
    validator.validate(msg)  # exception atmamalı


@pytest.mark.parametrize("msg", INVALID)
def test_invalid_messages_rejected(validator, msg):
    with pytest.raises(ValidationError):
        validator.validate(msg)


def test_wpf_flightstate_mapping_fields_present(validator):
    props = validator.schema["$defs"]["aircraft_vision"]["properties"]
    for f in ("target_center_x", "target_center_y", "target_width",
              "target_height", "is_locked", "target_team_number"):
        assert f in props, f"WPF FlightState eşleme alanı eksik: {f}"


def test_all_message_types_in_oneof(validator):
    refs = {b["$ref"].split("/")[-1] for b in validator.schema["oneOf"]}
    expected = {"aircraft_vision", "lock_valid", "kamikaze_result",
                "operator_cmd", "server_data", "config", "heartbeat"}
    assert refs == expected

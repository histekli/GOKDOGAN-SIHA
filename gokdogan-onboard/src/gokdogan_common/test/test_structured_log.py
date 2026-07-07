"""Yapısal log + zaman tabanı testleri (SAD §22)."""

import json

from gokdogan_common.structured_log import StructuredLogger, TimeBase


def test_timebase_server_offset():
    tb = TimeBase(clock=lambda: 1000.0)
    tb.set_server_offset(50.0)
    s = tb.stamp()
    assert s["sys"] == 1000.0 and s["server"] == 1050.0 and s["server_offset"] == 50.0


def test_logger_emit_is_json_with_fields():
    sink = []
    lg = StructuredLogger("mission_fsm", TimeBase(clock=lambda: 5.0), sink=sink.append)
    line = lg.emit("state_transition", frm="CRUISE", to="RTL", reason="batarya")
    rec = json.loads(line)
    assert rec["src"] == "mission_fsm" and rec["kind"] == "state_transition"
    assert rec["frm"] == "CRUISE" and rec["to"] == "RTL"
    assert rec["server"] == 5.0
    assert sink == [line]


def test_logger_without_sink_returns_line():
    lg = StructuredLogger("x")
    line = lg.emit("evt", a=1)
    assert json.loads(line)["a"] == 1


def test_ros_offset_tracked():
    tb = TimeBase(clock=lambda: 0.0)
    tb.set_ros_offset(-3.2)
    assert tb.stamp()["ros_offset"] == -3.2

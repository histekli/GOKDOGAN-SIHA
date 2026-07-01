"""FSM çekirdeği birim testleri (SAD §12 DFA + tek-yazıcı active_service)."""
from gokdogan_msgs.msg import MissionMode as MM

from gokdogan_mission_fsm import fsm_core as fc


def test_initial_state_idle():
    f = fc.FsmCore()
    assert f.state == MM.IDLE
    assert f.active_service == MM.SVC_NONE


def test_valid_takeoff_flow():
    f = fc.FsmCore()
    assert f.transition(MM.TAKEOFF)[0]
    assert f.state == MM.TAKEOFF
    assert f.active_service == MM.SVC_MISSION_FSM
    assert f.transition(MM.CRUISE)[0]
    assert f.transition(MM.LOCKING)[0]
    assert f.active_service == MM.SVC_GUIDANCE
    assert f.transition(MM.CRUISE)[0]
    assert f.transition(MM.KAMIKAZE)[0]
    assert f.active_service == MM.SVC_KAMIKAZE


def test_illegal_transitions_rejected():
    f = fc.FsmCore()
    ok, reason = f.transition(MM.KAMIKAZE)   # IDLE'dan KAMIKAZE yok
    assert not ok
    assert f.state == MM.IDLE                # state değişmedi
    ok, _ = f.transition(MM.LOCKING)         # IDLE'dan LOCKING yok
    assert not ok


def test_locking_only_from_cruise():
    f = fc.FsmCore()
    f.transition(MM.TAKEOFF)
    assert not f.transition(MM.LOCKING)[0]   # TAKEOFF'tan LOCKING yok
    f.transition(MM.CRUISE)
    assert f.transition(MM.LOCKING)[0]       # CRUISE'dan LOCKING var


def test_manual_from_any_and_force():
    for s in (MM.IDLE, MM.CRUISE, MM.LOCKING, MM.KAMIKAZE):
        f = fc.FsmCore(state=s)
        assert f.transition(MM.MANUAL)[0], f"{s} → MANUAL olmalı"
    # force guard'sız (failsafe → RTL)
    f = fc.FsmCore(state=MM.LOCKING)
    f.force(MM.RTL)
    assert f.state == MM.RTL


def test_noop_transition():
    f = fc.FsmCore(state=MM.CRUISE)
    ok, reason = f.transition(MM.CRUISE)
    assert ok and "no-op" in reason


def test_every_state_has_active_service():
    for s in fc.STATE_NAMES:
        f = fc.FsmCore(state=s)
        assert f.active_service in (
            MM.SVC_NONE, MM.SVC_GUIDANCE, MM.SVC_KAMIKAZE, MM.SVC_HSS, MM.SVC_MISSION_FSM)

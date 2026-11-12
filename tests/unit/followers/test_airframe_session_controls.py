from dataclasses import replace

import pytest

from classes.aircraft_state import AirframePhase, AirspeedObservation, GuidanceSessionIdentity
from classes.airframe_session_controls import AirframeSessionControls
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


def controls(*, phase=AirframePhase.MULTICOPTER):
    state = aircraft_state(phase=phase)
    identity = GuidanceSessionIdentity("follow", state.binding, 1)
    owner = AirframeSessionControls(identity, multicopter_startup_m_s=0., multicopter_ceiling_m_s=6., step_m_s=.5)
    owner.enter_phase(identity, state, now=100., timeout_s=.5)
    return owner, state, identity


@pytest.mark.parametrize('measured,expected', [(True, 20.), (False, 18.)])
def test_fixed_wing_only_controls_start_from_native_eas_or_trim_without_an_mc_request(measured, expected):
    state = aircraft_state(phase=AirframePhase.FIXED_WING)
    if not measured:
        state = replace(state, airspeed=AirspeedObservation('unavailable', None, None, 100., False))
    identity = GuidanceSessionIdentity('fw_follow', state.binding, 1)
    owner = AirframeSessionControls.for_fixed_wing(identity, step_m_s=.5)
    assert owner.current_control is None
    assert owner.snapshot(client_contract_version=2) is None
    owner.enter_phase(identity, state, now=100., timeout_s=.5)
    snapshot = owner.snapshot(client_contract_version=2)
    assert snapshot['value'] == expected
    assert snapshot['minimum'] == state.fixed_wing_envelope.minimum_eas_m_s
    assert snapshot['maximum'] == state.fixed_wing_envelope.maximum_eas_m_s
    assert snapshot['speed_basis'] == 'equivalent_airspeed'
    assert snapshot['step'] == .5
    with pytest.raises(ValueError, match='out_of_range'):
        owner.update(0., identity=identity, expected_revision=snapshot['revision'])
    assert owner.current_control.value == expected


@pytest.mark.parametrize('phase', [AirframePhase.MULTICOPTER, AirframePhase.VTOL_TRANSITION])
def test_fixed_wing_only_control_refuses_other_phases_without_changing_current_request(phase):
    state = aircraft_state(phase=AirframePhase.FIXED_WING, is_vtol=True)
    identity = GuidanceSessionIdentity('fw_follow', state.binding, 1)
    owner = AirframeSessionControls.for_fixed_wing(identity, step_m_s=.5)
    owner.enter_phase(identity, state, now=100., timeout_s=.5)
    before = owner.snapshot(client_contract_version=2)
    with pytest.raises(ValueError, match='identity_stale'):
        owner.enter_phase(replace(identity, guidance_generation=2), replace(state, phase=phase), now=100., timeout_s=.5)
    assert owner.identity == identity
    assert owner.snapshot(client_contract_version=2) == before


@pytest.mark.parametrize('step', [0., -1., float('nan'), float('inf'), True])
def test_fixed_wing_only_control_step_is_explicit_and_validated(step):
    state = aircraft_state()
    identity = GuidanceSessionIdentity('fw_follow', state.binding, 1)
    with pytest.raises(ValueError):
        AirframeSessionControls.for_fixed_wing(identity, step_m_s=step)


def test_selected_phase_is_bound_once_without_rotating_identity():
    owner, state, identity = controls()
    before = owner.snapshot(client_contract_version=2)
    with pytest.raises(ValueError, match="phase_already_bound"):
        owner.enter_phase(identity, replace(state, phase=AirframePhase.FIXED_WING), now=100., timeout_s=.5)
    assert owner.snapshot(client_contract_version=2) == before
    with pytest.raises(ValueError, match="identity_stale"):
        owner.enter_phase(replace(identity, guidance_generation=2), state, now=100., timeout_s=.5)
    assert owner.identity == identity



def test_ended_control_owner_rejects_old_editor_and_cannot_resume():
    owner, state, identity = controls()
    revision = owner.current_control.revision
    owner.end()
    with pytest.raises(ValueError, match="identity_stale"):
        owner.update(2., identity=identity, expected_revision=revision)
    assert owner.snapshot(client_contract_version=2) is None
    with pytest.raises(ValueError, match="session_ended"):
        owner.enter_phase(identity, state, now=100., timeout_s=.5)



def test_initial_transition_is_not_a_control_phase():
    state = aircraft_state(is_vtol=True, phase=AirframePhase.VTOL_TRANSITION)
    identity = GuidanceSessionIdentity("follow", state.binding, 1)
    owner = AirframeSessionControls.for_fixed_wing(identity, step_m_s=.5)
    with pytest.raises(ValueError, match="aircraft_phase_unknown"):
        owner.enter_phase(identity, state, now=100., timeout_s=.5)
    assert owner.current_control is None



def test_sensorless_starts_from_trim_and_recovery_allows_reductions_only():
    state = aircraft_state(phase=AirframePhase.FIXED_WING)
    identity = GuidanceSessionIdentity("follow", state.binding, 1)
    owner = AirframeSessionControls.for_fixed_wing(identity, step_m_s=.5)
    next_identity = identity
    state = replace(state, phase=AirframePhase.FIXED_WING,
                    airspeed=AirspeedObservation("unavailable", None, None, 100., False))
    owner.enter_phase(next_identity, state, now=100., timeout_s=.5)
    snapshot = owner.snapshot(client_contract_version=2)
    assert snapshot["value"] == 18.
    with pytest.raises(ValueError, match="increase_unavailable"):
        owner.update(20., identity=next_identity, expected_revision=snapshot["revision"], recovering=True)
    updated = owner.update(16., identity=next_identity, expected_revision=snapshot["revision"], recovering=True)
    assert updated.value == 16.
    with pytest.raises(ValueError, match="out_of_range"):
        owner.update(0., identity=next_identity, expected_revision=updated.revision)


def test_unrestricted_policy_reset_reinstates_native_envelope_without_losing_minimum():
    state = aircraft_state(phase=AirframePhase.FIXED_WING)
    identity = GuidanceSessionIdentity("follow", state.binding, 1)
    owner = AirframeSessionControls.for_fixed_wing(identity, step_m_s=.5)
    next_identity = identity
    owner.enter_phase(next_identity, replace(state, phase=AirframePhase.FIXED_WING),
                      now=100., timeout_s=.5, unrestricted_verified=True)
    snapshot = owner.snapshot(client_contract_version=2)
    assert snapshot["maximum"] is None
    assert snapshot["configured_maximum"] == 30.
    updated = owner.update(40., identity=next_identity, expected_revision=snapshot["revision"])
    restored = owner.update(None, identity=next_identity, expected_revision=updated.revision)
    assert restored.value == 30.
    assert not restored.override_active


def test_invalid_initial_transaction_can_be_corrected_without_minting_identity():
    state = aircraft_state(phase=AirframePhase.FIXED_WING)
    identity = GuidanceSessionIdentity("follow", state.binding, 1)
    owner = AirframeSessionControls.for_fixed_wing(identity, step_m_s=.5)
    with pytest.raises(ValueError, match="envelope_unavailable"):
        owner.enter_phase(identity, replace(state, fixed_wing_envelope=None), now=100., timeout_s=.5)
    assert owner.current_control is None
    assert owner.identity == identity
    owner.enter_phase(identity, state, now=100., timeout_s=.5)
    assert owner.current_control.value == 20.



def test_phase_change_is_refused_and_capability_is_boolean():
    owner, state, identity = controls()
    with pytest.raises(ValueError, match="phase_already_bound"):
        owner.enter_phase(identity, replace(state, phase=AirframePhase.FIXED_WING), now=100., timeout_s=.5)
    with pytest.raises(ValueError, match="capability_invalid"):
        owner.enter_phase(identity, state, now=100., timeout_s=.5, unrestricted_verified="false")



def test_dynamic_native_envelope_refresh_does_not_ratchet_speed_or_starve_valid_edits():
    state = aircraft_state(phase=AirframePhase.FIXED_WING)
    identity = GuidanceSessionIdentity("follow", state.binding, 1)
    owner = AirframeSessionControls.for_fixed_wing(identity, step_m_s=.5)
    fw_identity = identity
    state = replace(state, phase=AirframePhase.FIXED_WING)
    owner.enter_phase(fw_identity, state, now=100., timeout_s=.5)
    before = owner.snapshot(client_contract_version=2)
    loaded = replace(state, fixed_wing_envelope=replace(state.fixed_wing_envelope, minimum_eas_m_s=24.))
    assert owner.refresh_envelope(loaded, now=100., timeout_s=.5)
    current = owner.snapshot(client_contract_version=2)
    assert current["minimum"] == 24.
    assert current["value"] == 20.
    assert current["revision"] == before["revision"]
    with pytest.raises(ValueError, match="out_of_range"):
        owner.update(20.5, identity=fw_identity, expected_revision=before["revision"])
    assert owner.refresh_envelope(state, now=100., timeout_s=.5)
    assert owner.snapshot(client_contract_version=2)["value"] == 20.
    assert not owner.refresh_envelope(state, now=100., timeout_s=.5)
    assert owner.update(20.5, identity=fw_identity, expected_revision=before["revision"]).value == 20.5


def test_native_parameter_changes_invalidate_an_editor_without_changing_the_request():
    state = aircraft_state(phase=AirframePhase.FIXED_WING)
    identity = GuidanceSessionIdentity("follow", state.binding, 1)
    owner = AirframeSessionControls.for_fixed_wing(identity, step_m_s=.5)
    fw_identity = identity
    state = replace(state, phase=AirframePhase.FIXED_WING)
    owner.enter_phase(fw_identity, state, now=100., timeout_s=.5)
    before = owner.snapshot(client_contract_version=2)
    changed = replace(state, fixed_wing_envelope=replace(state.fixed_wing_envelope, revision="parameters-2"))
    owner.refresh_envelope(changed, now=100., timeout_s=.5)
    assert owner.snapshot(client_contract_version=2)["value"] == before["value"]
    with pytest.raises(ValueError, match="revision_stale"):
        owner.update(20.5, identity=fw_identity, expected_revision=before["revision"])





def test_existing_mc_override_is_preserved_until_end_without_affecting_a_new_fw_start():
    owner, state, identity = controls()
    updated = owner.update(9., identity=identity, expected_revision=owner.current_control.revision)
    assert updated.override_active
    with pytest.raises(ValueError, match="phase_already_bound"):
        owner.enter_phase(identity, replace(state, phase=AirframePhase.FIXED_WING), now=100., timeout_s=.5)
    assert owner.current_control is updated
    owner.end()
    fresh, _, _ = controls(phase=AirframePhase.FIXED_WING)
    assert fresh.current_control.value == 20.
    assert not fresh.current_control.override_active



def test_dry_run_validation_preserves_the_authoritative_request_and_revision():
    owner, _, identity = controls()
    before = owner.snapshot(client_contract_version=2)
    proposed = owner.validate_update(2., identity=identity, expected_revision=before["revision"])
    assert proposed.value == 2.
    assert proposed.revision == before["revision"] + 1
    assert owner.snapshot(client_contract_version=2) == before
    with pytest.raises(ValueError, match="revision_stale"):
        owner.validate_update(3., identity=identity, expected_revision=proposed.revision)
    assert owner.snapshot(client_contract_version=2) == before

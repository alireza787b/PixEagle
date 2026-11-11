from dataclasses import replace

import pytest

from classes.aircraft_state import AirframePhase, AirspeedObservation, GuidanceSessionIdentity
from classes.airframe_session_controls import AirframeSessionControls
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


def controls():
    state = aircraft_state(phase=AirframePhase.MULTICOPTER)
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
    with pytest.raises(ValueError, match='phase_unavailable'):
        owner.enter_phase(replace(identity, guidance_generation=2), replace(state, phase=phase), now=100., timeout_s=.5)
    assert owner.identity == identity
    assert owner.snapshot(client_contract_version=2) == before


@pytest.mark.parametrize('step', [0., -1., float('nan'), float('inf'), True])
def test_fixed_wing_only_control_step_is_explicit_and_validated(step):
    state = aircraft_state()
    identity = GuidanceSessionIdentity('fw_follow', state.binding, 1)
    with pytest.raises(ValueError):
        AirframeSessionControls.for_fixed_wing(identity, step_m_s=step)


def test_zero_mc_request_never_becomes_fixed_wing_request_and_each_phase_retains_its_value():
    owner, state, identity = controls()
    assert owner.snapshot(client_contract_version=2)["value"] == 0.
    fw_identity = replace(identity, guidance_generation=2)
    owner.enter_phase(fw_identity, replace(state, phase=AirframePhase.FIXED_WING), now=100., timeout_s=.5)
    snapshot = owner.snapshot(client_contract_version=2)
    assert snapshot["value"] == 20.
    assert snapshot["minimum"] == 12.
    assert snapshot["speed_basis"] == "equivalent_airspeed"
    owner.update(22., identity=fw_identity, expected_revision=snapshot["revision"])
    mc_identity = replace(identity, guidance_generation=3)
    owner.enter_phase(mc_identity, state, now=100., timeout_s=.5)
    assert owner.snapshot(client_contract_version=2)["value"] == 0.
    fw_identity = replace(identity, guidance_generation=4)
    owner.enter_phase(fw_identity, replace(state, phase=AirframePhase.FIXED_WING), now=100., timeout_s=.5)
    assert owner.snapshot(client_contract_version=2)["value"] == 22.


def test_old_mc_editor_cannot_apply_after_phase_change_even_if_revision_is_current():
    owner, state, identity = controls()
    owner.enter_phase(replace(identity, guidance_generation=2), replace(state, phase=AirframePhase.FIXED_WING),
                      now=100., timeout_s=.5)
    snapshot = owner.snapshot(client_contract_version=2)
    with pytest.raises(ValueError, match="identity_stale"):
        owner.update(25., identity=identity, expected_revision=snapshot["revision"])
    assert owner.snapshot(client_contract_version=1) is None
    assert owner.snapshot(client_contract_version=2)["value"] == 20.


def test_transition_disables_edits_without_changing_phase_requests():
    owner, state, identity = controls()
    next_identity = replace(identity, guidance_generation=2)
    transition = replace(state, is_vtol=True, phase=AirframePhase.VTOL_TRANSITION)
    owner.enter_phase(next_identity, transition, now=100., timeout_s=.5)
    assert owner.snapshot(client_contract_version=2) is None
    with pytest.raises(ValueError, match="phase_unavailable"):
        owner.update(1., identity=next_identity, expected_revision=2)


def test_sensorless_starts_from_trim_and_recovery_allows_reductions_only():
    owner, state, identity = controls()
    next_identity = replace(identity, guidance_generation=2)
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
    owner, state, identity = controls()
    next_identity = replace(identity, guidance_generation=2)
    owner.enter_phase(next_identity, replace(state, phase=AirframePhase.FIXED_WING),
                      now=100., timeout_s=.5, unrestricted_verified=True)
    snapshot = owner.snapshot(client_contract_version=2)
    assert snapshot["maximum"] is None
    assert snapshot["configured_maximum"] == 30.
    updated = owner.update(40., identity=next_identity, expected_revision=snapshot["revision"])
    restored = owner.update(None, identity=next_identity, expected_revision=updated.revision)
    assert restored.value == 30.
    assert not restored.override_active


def test_invalid_phase_transaction_preserves_the_previous_value_and_generation():
    owner, state, identity = controls()
    before = owner.snapshot(client_contract_version=2)
    with pytest.raises(ValueError, match="envelope_unavailable"):
        owner.enter_phase(replace(identity, guidance_generation=2),
                          replace(state, phase=AirframePhase.FIXED_WING, fixed_wing_envelope=None),
                          now=100., timeout_s=.5)
    assert owner.snapshot(client_contract_version=2) == before
    owner.end()
    assert owner.snapshot(client_contract_version=2) is None
    with pytest.raises(ValueError, match="session_ended"):
        owner.enter_phase(identity, state, now=100., timeout_s=.5)


def test_phase_change_requires_new_generation_and_boolean_capability():
    owner, state, identity = controls()
    with pytest.raises(ValueError, match="generation_not_advanced"):
        owner.enter_phase(identity, replace(state, phase=AirframePhase.FIXED_WING), now=100., timeout_s=.5)
    with pytest.raises(ValueError, match="capability_invalid"):
        owner.enter_phase(replace(identity, guidance_generation=2), replace(state, phase=AirframePhase.FIXED_WING),
                          now=100., timeout_s=.5, unrestricted_verified="false")


def test_dynamic_native_envelope_refresh_does_not_ratchet_speed_or_starve_valid_edits():
    owner, state, identity = controls()
    fw_identity = replace(identity, guidance_generation=2)
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
    owner, state, identity = controls()
    fw_identity = replace(identity, guidance_generation=2)
    state = replace(state, phase=AirframePhase.FIXED_WING)
    owner.enter_phase(fw_identity, state, now=100., timeout_s=.5)
    before = owner.snapshot(client_contract_version=2)
    changed = replace(state, fixed_wing_envelope=replace(state.fixed_wing_envelope, revision="parameters-2"))
    owner.refresh_envelope(changed, now=100., timeout_s=.5)
    assert owner.snapshot(client_contract_version=2)["value"] == before["value"]
    with pytest.raises(ValueError, match="revision_stale"):
        owner.update(20.5, identity=fw_identity, expected_revision=before["revision"])


def test_fw_request_is_retained_when_returning_from_transition_with_a_higher_speed_floor():
    owner, state, identity = controls()
    state = replace(state, phase=AirframePhase.FIXED_WING)
    owner.enter_phase(replace(identity, guidance_generation=2), state, now=100., timeout_s=.5)
    owner.enter_phase(replace(identity, guidance_generation=3),
                      replace(state, phase=AirframePhase.VTOL_TRANSITION, is_vtol=True), now=100., timeout_s=.5)
    loaded = replace(state, fixed_wing_envelope=replace(state.fixed_wing_envelope, minimum_eas_m_s=24.))
    owner.enter_phase(replace(identity, guidance_generation=4), loaded, now=100., timeout_s=.5)
    returned = owner.snapshot(client_contract_version=2)
    assert returned["minimum"] == 24.
    assert returned["value"] == 20.


def test_existing_mc_override_survives_phase_changes_without_changing_fw_request():
    owner, state, identity = controls()
    snapshot = owner.snapshot(client_contract_version=2)
    assert snapshot["maximum"] is None
    updated = owner.update(9., identity=identity, expected_revision=snapshot["revision"])
    assert updated.override_active
    fw_identity = replace(identity, guidance_generation=2)
    owner.enter_phase(fw_identity, replace(state, phase=AirframePhase.FIXED_WING), now=100., timeout_s=.5)
    assert owner.snapshot(client_contract_version=2)["value"] == 20.
    assert owner.snapshot(client_contract_version=2)["maximum"] == 30.
    next_mc_identity = replace(identity, guidance_generation=3)
    owner.enter_phase(next_mc_identity, state, now=100., timeout_s=.5)
    returned = owner.snapshot(client_contract_version=2)
    assert returned["value"] == 9.
    assert returned["override_active"]
    restored = owner.update(None, identity=next_mc_identity, expected_revision=returned["revision"])
    assert restored.value == 6.


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

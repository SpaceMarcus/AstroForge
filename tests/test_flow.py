"""Tests for flow-case plausibility helpers."""

from dataclasses import replace

from engine.flow import FlowCase, adapt_inputs_for_flow_case, classify_input_flow_case
from engine.models import InputParameters


def make_inputs() -> InputParameters:
    return InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=7.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=20.0,
        ambient_pressure_pa=101_325.0,
    )


def test_classify_input_flow_case_marks_low_backpressure_case_as_choked() -> None:
    assessment = classify_input_flow_case(make_inputs(), gamma=1.20)

    assert assessment.flow_case is FlowCase.CHOKED_SUPERSONIC
    assert assessment.nozzle_geometry_enabled is True


def test_classify_input_flow_case_marks_high_backpressure_case_as_subsonic() -> None:
    assessment = classify_input_flow_case(
        replace(make_inputs(), ambient_pressure_pa=5.0e6),
        gamma=1.20,
    )

    assert assessment.flow_case is FlowCase.SUBSONIC
    assert assessment.nozzle_geometry_enabled is False


def test_adapt_inputs_for_subsonic_case_forces_throat_only_geometry() -> None:
    inputs = replace(
        make_inputs(),
        expansion_ratio=18.0,
        bell_length_fraction_percent=85.0,
        manual_nozzle_length_m=0.65,
    )
    assessment = classify_input_flow_case(
        replace(inputs, ambient_pressure_pa=5.0e6),
        gamma=1.20,
    )

    adapted = adapt_inputs_for_flow_case(inputs, assessment)

    assert adapted.expansion_ratio == 1.0
    assert adapted.bell_length_fraction_percent is None
    assert adapted.manual_nozzle_length_m is None

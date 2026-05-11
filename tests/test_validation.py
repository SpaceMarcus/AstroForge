"""Tests for input validation helpers."""

from engine.models import ChemistryMode, InputParameters
from engine.utils.validation import InputValidationError, ensure_valid_input, validate_input_parameters


def make_valid_inputs() -> InputParameters:
    return InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=8.0e6,
        thrust_n=1.0e5,
        mixture_ratio=2.6,
        expansion_ratio=20.0,
        ambient_pressure_pa=101_325.0,
        contraction_ratio=3.0,
        characteristic_length_m=1.0,
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
    )


def test_validate_input_parameters_accepts_valid_case() -> None:
    assert validate_input_parameters(make_valid_inputs()) == []


def test_validate_input_parameters_reports_multiple_errors() -> None:
    invalid = make_valid_inputs()
    invalid.fuel = " "
    invalid.chamber_pressure_pa = -1.0
    invalid.ambient_pressure_pa = 5.0
    invalid.contraction_ratio = 0.8
    invalid.contour_method = "bad"  # type: ignore[assignment]

    errors = validate_input_parameters(invalid)

    assert "Fuel must not be empty." in errors
    assert "Pc must be greater than 0 Pa." in errors
    assert "Ac/At must be greater than 1 when it is provided." in errors
    assert "Nozzle contour method is invalid." in errors


def test_ensure_valid_input_raises_collected_validation_error() -> None:
    invalid = make_valid_inputs()
    invalid.expansion_ratio = 0.0

    try:
        ensure_valid_input(invalid)
    except InputValidationError as exc:
        assert "Expansion ratio" in str(exc)
    else:
        raise AssertionError("InputValidationError was not raised.")

"""Tests for RocketCEA backend error handling."""

import pytest

from engine.chemistry.base import ThermochemistryBackendUnavailableError
from engine.chemistry.rocketcea_backend import RocketCEABackend
from engine.models import ChemistryMode, InputParameters


def make_valid_inputs() -> InputParameters:
    return InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=8.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=20.0,
        ambient_pressure_pa=101_325.0,
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
    )


def test_backend_raises_friendly_error_when_rocketcea_is_unavailable() -> None:
    backend = RocketCEABackend()
    backend._cea_cls = None
    backend._import_error = ModuleNotFoundError("rocketcea")

    with pytest.raises(ThermochemistryBackendUnavailableError) as exc_info:
        backend.calculate(make_valid_inputs())

    assert "RocketCEA is not installed" in str(exc_info.value)

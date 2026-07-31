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


def test_exact_vacuum_ambient_uses_vacuum_performance_without_rocketcea_call() -> None:
    class AmbientMethodsMustNotRun:
        def estimate_Ambient_Isp(self, **_kwargs):
            raise AssertionError("Ambient RocketCEA method must not run for Pa=0.")

        def get_PambCf(self, **_kwargs):
            raise AssertionError("Ambient RocketCEA method must not run for Pa=0.")

    inputs = make_valid_inputs()
    inputs.ambient_pressure_pa = 0.0
    backend = RocketCEABackend()

    isp_amb, cf_amb, mode = backend._ambient_performance(
        cea=AmbientMethodsMustNotRun(),
        pc_psia=1_000.0,
        pa_psia=0.0,
        c_star_m_s=1_800.0,
        isp_vac_s=350.0,
        inputs=inputs,
        flags=backend._mode_flags(inputs.chemistry_mode),
    )

    assert isp_amb == 350.0
    assert cf_amb == pytest.approx(350.0 * 9.80665 / 1_800.0)
    assert mode == "vacuum"

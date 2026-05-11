"""Tests for the orchestration layer in app.py."""

from app import EngineDesignApplication, build_example_inputs
from engine.chemistry.base import ThermochemistryBackend
from engine.models import (
    ChemistryMode,
    InputParameters,
    OFSweepPoint,
    OFSweepResult,
    ThermochemistryResult,
    ThermochemistryState,
)


class FakeBackend(ThermochemistryBackend):
    def calculate(self, inputs: InputParameters) -> ThermochemistryResult:
        return ThermochemistryResult(
            chemistry_mode=ChemistryMode.EQUILIBRIUM,
            propellant_description=f"{inputs.oxidizer} / {inputs.fuel}",
            chamber_temperature_k=3500.0,
            c_star_m_s=1750.0,
            isp_vac_s=320.0,
            isp_amb_s=285.0,
            cf_vac=1.79,
            cf_amb=1.60,
            gamma=1.2,
            molecular_weight_kg_per_mol=0.022,
            cp_j_per_kg_k=3200.0,
            viscosity_pa_s=8.0e-5,
            thermal_conductivity_w_per_m_k=0.2,
            prandtl_number=0.7,
            station_states={
                "chamber": ThermochemistryState(label="chamber", area_ratio=3.0, temperature_k=3500.0),
                "throat": ThermochemistryState(label="throat", area_ratio=1.0, temperature_k=3200.0),
                "exit": ThermochemistryState(label="exit", area_ratio=20.0, temperature_k=2100.0),
            },
        )

    def estimate_ambient_matched_expansion_ratio(
        self,
        inputs: InputParameters,
    ) -> float | None:
        return 15.5

    def build_of_sweep(
        self,
        inputs: InputParameters,
        *,
        sample_count: int = 41,
    ) -> OFSweepResult:
        return OFSweepResult(
            fuel=inputs.fuel,
            oxidizer=inputs.oxidizer,
            chemistry_mode=inputs.chemistry_mode,
            chamber_pressure_pa=inputs.chamber_pressure_pa,
            expansion_ratio=inputs.expansion_ratio,
            stoichiometric_mixture_ratio=3.4,
            peak_isp_vac_mixture_ratio=2.8,
            peak_c_star_mixture_ratio=2.9,
            points=[
                OFSweepPoint(
                    mixture_ratio=2.6,
                    equivalence_ratio=1.3,
                    c_star_m_s=1750.0,
                    isp_vac_s=320.0,
                    chamber_temperature_k=3500.0,
                    is_fuel_rich=True,
                    is_oxidizer_rich=False,
                )
            ],
        )


def test_application_runs_full_pipeline_without_gui() -> None:
    application = EngineDesignApplication(backend=FakeBackend())

    bundle = application.run_case(build_example_inputs())

    assert bundle.inputs.fuel == "RP-1"
    assert bundle.thermochemistry.c_star_m_s == 1750.0
    assert bundle.geometry.throat_area_m2 > 0.0
    assert len(bundle.contour) > 0
    assert len(bundle.thermochemistry_profile) == len(bundle.contour)
    assert bundle.of_sweep is not None


def test_application_exposes_ambient_matched_expansion_ratio_estimate() -> None:
    application = EngineDesignApplication(backend=FakeBackend())

    estimate = application.estimate_ambient_matched_expansion_ratio(build_example_inputs())

    assert estimate == 15.5

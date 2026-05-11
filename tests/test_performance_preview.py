"""Tests for compact Current Design performance-preview helpers."""

from engine.models import (
    ChemistryMode,
    ExportBundle,
    GeometryResult,
    InputParameters,
    ThermochemistryResult,
)
from engine.performance_preview import compute_performance_preview, eta_cstar_band


def make_preview_bundle() -> ExportBundle:
    inputs = InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=7.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=20.0,
        ambient_pressure_pa=101_325.0,
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
    )
    thermo = ThermochemistryResult(
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        propellant_description="LOX / RP-1",
        chamber_temperature_k=3500.0,
        c_star_m_s=1750.0,
        isp_vac_s=320.0,
        isp_amb_s=285.0,
        cf_vac=1.79,
        cf_amb=1.60,
    )
    geometry = GeometryResult(
        throat_area_m2=0.0078,
        throat_radius_m=0.0498,
        exit_area_m2=0.156,
        exit_radius_m=0.223,
        mass_flow_kg_per_s=35.7,
        current_expansion_ratio=20.0,
    )
    return ExportBundle(
        inputs=inputs,
        thermochemistry=thermo,
        geometry=geometry,
        contour=[],
    )


def test_compute_performance_preview_uses_eta_cstar_design_for_mdot() -> None:
    bundle = make_preview_bundle()

    preview = compute_performance_preview(bundle.inputs, bundle, 0.95)

    assert preview.c_star_theoretical_m_s == 1750.0
    assert preview.c_star_design_m_s == 1662.5
    assert preview.mass_flow_kg_per_s is not None
    assert abs(preview.mass_flow_kg_per_s - (7.0e6 * 0.0078 / 1662.5)) < 1.0e-9
    assert preview.thrust_estimate_n == 0.95 * 1.60 * 7.0e6 * 0.0078
    assert preview.thrust_deviation_exceeds_threshold is True


def test_eta_cstar_band_returns_expected_color_bands() -> None:
    assert eta_cstar_band(0.99) == "success"
    assert eta_cstar_band(0.96) == "normal"
    assert eta_cstar_band(0.94) == "warning"
    assert eta_cstar_band(1.01) == "invalid"

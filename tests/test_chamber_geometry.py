"""Tests for the preliminary chamber-geometry helper."""

import math

import pytest

from engine.chamber_geometry import (
    ChamberGeometryInputs,
    ChamberGeometryModel,
    LStarSelectionMode,
    calculate_chamber_geometry,
    calculate_temporal_average_gamma,
    estimate_contraction_ratio_guidance,
    estimate_residence_time_metrics,
    infer_lstar_mode,
    select_lstar_value,
    suggest_lstar_propellant,
)
from engine.models import (
    ChemistryMode,
    ExportBundle,
    GeometryResult,
    InputParameters,
    NozzlePoint,
    ThermochemistryProfilePoint,
    ThermochemistryResult,
    ThermochemistryState,
)


def test_nominal_lstar_for_lox_rp1_uses_midpoint() -> None:
    assert select_lstar_value("LOX / RP-1", LStarSelectionMode.NOMINAL) == pytest.approx(1.145)


def test_calculate_chamber_geometry_returns_expected_primary_values() -> None:
    result = calculate_chamber_geometry(
        ChamberGeometryInputs(
            propellant_name="LOX / RP-1",
            throat_diameter_m=0.1,
            contraction_ratio=3.0,
            convergent_half_angle_deg=45.0,
            lstar_mode=LStarSelectionMode.NOMINAL,
            chamber_model=ChamberGeometryModel.CYLINDRICAL,
        )
    )

    throat_area = math.pi / 4.0 * 0.1**2
    chamber_area = 3.0 * throat_area
    selected_lstar = 0.5 * (1.02 + 1.27)

    assert result.throat_area_m2 == pytest.approx(throat_area)
    assert result.chamber_area_m2 == pytest.approx(chamber_area)
    assert result.selected_lstar_m == pytest.approx(selected_lstar)
    assert result.required_chamber_volume_m3 == pytest.approx(selected_lstar * throat_area)
    assert result.chamber_diameter_m > result.throat_diameter_m
    assert result.total_chamber_length_to_throat_m > 0.0
    assert result.hot_gas_wall_area_m2 > 0.0


def test_chamber_geometry_emits_expected_warnings_for_extreme_case() -> None:
    result = calculate_chamber_geometry(
        ChamberGeometryInputs(
            propellant_name="LOX / RP-1",
            throat_diameter_m=0.1,
            contraction_ratio=10.0,
            convergent_half_angle_deg=20.0,
            lstar_mode=LStarSelectionMode.MIN,
            chamber_model=ChamberGeometryModel.CYLINDRICAL,
        )
    )

    assert result.cylindrical_section_length_m <= 0.0
    assert any("non-positive cylindrical chamber length" in warning for warning in result.warnings)
    assert any("High contraction ratio" in warning for warning in result.warnings)


def test_non_cylindrical_modes_remain_unimplemented() -> None:
    with pytest.raises(ValueError):
        calculate_chamber_geometry(
            ChamberGeometryInputs(
                propellant_name="LOX / RP-1",
                throat_diameter_m=0.1,
                contraction_ratio=3.0,
                convergent_half_angle_deg=45.0,
                lstar_mode=LStarSelectionMode.NOMINAL,
                chamber_model=ChamberGeometryModel.SPHERICAL,
            )
        )


def test_propellant_mapping_and_lstar_mode_inference() -> None:
    assert suggest_lstar_propellant("LOX", "RP-1") == "LOX / RP-1"
    mode, custom = infer_lstar_mode("LOX / RP-1", 1.145)
    assert mode is LStarSelectionMode.NOMINAL
    assert custom == pytest.approx(1.145)


def test_figure_8_15_guidance_returns_dc_dt_and_eps_band() -> None:
    guidance = estimate_contraction_ratio_guidance(1.0e-2)

    assert guidance.dc_dt_min < guidance.dc_dt_max
    assert guidance.contraction_ratio_min == pytest.approx(guidance.dc_dt_min**2)
    assert guidance.contraction_ratio_max == pytest.approx(guidance.dc_dt_max**2)
    assert guidance.clamped_to_data_range is False


def test_corner_radius_adds_arc_length_and_reduces_remaining_cone() -> None:
    baseline = calculate_chamber_geometry(
        ChamberGeometryInputs(
            propellant_name="LOX / RP-1",
            throat_diameter_m=0.1,
            contraction_ratio=3.0,
            convergent_half_angle_deg=45.0,
            lstar_mode=LStarSelectionMode.NOMINAL,
            chamber_model=ChamberGeometryModel.CYLINDRICAL,
            corner_radius_m=0.0,
        )
    )
    rounded = calculate_chamber_geometry(
        ChamberGeometryInputs(
            propellant_name="LOX / RP-1",
            throat_diameter_m=0.1,
            contraction_ratio=3.0,
            convergent_half_angle_deg=45.0,
            lstar_mode=LStarSelectionMode.NOMINAL,
            chamber_model=ChamberGeometryModel.CYLINDRICAL,
            corner_radius_m=0.01,
        )
    )

    assert rounded.rounded_corner_arc_length_m > 0.0
    assert rounded.remaining_straight_cone_length_m < baseline.remaining_straight_cone_length_m
    assert rounded.hot_gas_wall_area_m2 > 0.0


def test_temporal_average_gamma_and_residence_metrics_are_available_from_bundle() -> None:
    bundle = ExportBundle(
        inputs=InputParameters(
            fuel="RP-1",
            oxidizer="LOX",
            chamber_pressure_pa=7.0e6,
            thrust_n=100_000.0,
            mixture_ratio=2.6,
            expansion_ratio=20.0,
            ambient_pressure_pa=101_325.0,
            contraction_ratio=3.0,
            characteristic_length_m=1.145,
            chemistry_mode=ChemistryMode.EQUILIBRIUM,
        ),
        thermochemistry=ThermochemistryResult(
            chemistry_mode=ChemistryMode.EQUILIBRIUM,
            propellant_description="LOX / RP-1",
            chamber_temperature_k=3500.0,
            c_star_m_s=1750.0,
            isp_vac_s=320.0,
            gamma=1.20,
            chamber_density_kg_per_m3=5.0,
        ),
        geometry=GeometryResult(
            throat_area_m2=0.00785,
            throat_radius_m=0.05,
            exit_area_m2=0.156,
            exit_radius_m=0.223,
            mass_flow_kg_per_s=20.0,
            chamber_area_m2=0.02355,
            chamber_radius_m=0.0866,
            chamber_volume_m3=0.01,
            chamber_length_m=0.32,
        ),
        contour=[NozzlePoint(x_m=0.0, radius_m=0.05, area_m2=0.00785)],
        thermochemistry_profile=[
            ThermochemistryProfilePoint(
                x_m=-0.30,
                radius_m=0.09,
                area_m2=0.025,
                region="chamber",
                state=ThermochemistryState(
                    label="chamber",
                    gamma=1.22,
                    velocity_m_per_s=25.0,
                ),
            ),
            ThermochemistryProfilePoint(
                x_m=-0.08,
                radius_m=0.07,
                area_m2=0.015,
                region="converging",
                state=ThermochemistryState(
                    label="converging",
                    gamma=1.19,
                    velocity_m_per_s=65.0,
                ),
            ),
            ThermochemistryProfilePoint(
                x_m=0.0,
                radius_m=0.05,
                area_m2=0.00785,
                region="throat",
                state=ThermochemistryState(
                    label="throat",
                    gamma=1.16,
                    velocity_m_per_s=450.0,
                ),
            ),
        ],
    )

    gamma_temporal_mean, gamma_source = calculate_temporal_average_gamma(
        bundle.thermochemistry_profile,
        fallback_gamma=bundle.thermochemistry.gamma,
    )
    metrics = estimate_residence_time_metrics(
        bundle,
        chamber_volume_m3=0.01,
        lstar_m=1.145,
    )

    assert gamma_temporal_mean is not None
    assert 1.16 < gamma_temporal_mean < 1.22
    assert gamma_source == "temporal mean injector-to-throat"
    assert metrics.gas_residence_time_s == pytest.approx(0.0025)
    assert metrics.cstar_residence_m_s is not None
    assert metrics.cstar_theoretical_m_s == pytest.approx(1750.0)
    assert metrics.eta_v is not None
    assert metrics.eta_c is not None
    assert metrics.eta_c == pytest.approx(math.sqrt(metrics.eta_v))

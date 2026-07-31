"""Tests for RPA-style delivered-performance and operating-map helpers."""

from __future__ import annotations

import math

import pytest

from engine.delivered_performance import (
    DeliveredPerformanceAssumptions,
    build_performance_map,
    compute_multiphase_efficiency,
    compute_wall_shear_friction_efficiency,
    estimate_finite_rate_combustion_efficiency,
    evaluate_delivered_performance,
    schmucker_separation_pressure_ratio,
    standard_atmosphere_pressure_pa,
)
from engine.models import (
    ChemistryMode,
    ExportBundle,
    GeometryResult,
    InputParameters,
    ThermochemistryResult,
    ThermochemistryState,
    NozzlePoint,
)


def make_bundle() -> ExportBundle:
    inputs = InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=7.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=20.0,
        ambient_pressure_pa=101_325.0,
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        bell_length_fraction_percent=80.0,
    )
    thermo = ThermochemistryResult(
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        propellant_description="LOX / RP-1",
        chamber_temperature_k=3500.0,
        c_star_m_s=1750.0,
        isp_vac_s=320.0,
        isp_amb_s=285.0,
        cf_vac=320.0 * 9.80665 / 1750.0,
        cf_amb=1.60,
        gamma=1.20,
        exit_pressure_pa=35_000.0,
        exit_temperature_k=2100.0,
        station_states={
            "exit": ThermochemistryState(
                label="exit",
                mach_number=3.1,
                velocity_m_per_s=2800.0,
                temperature_k=2100.0,
            )
        },
    )
    geometry = GeometryResult(
        throat_area_m2=0.0078,
        throat_radius_m=0.0498,
        exit_area_m2=0.156,
        exit_radius_m=0.223,
        mass_flow_kg_per_s=31.2,
        current_expansion_ratio=20.0,
        top_nozzle_length_fraction_percent=80.0,
    )
    return ExportBundle(inputs=inputs, thermochemistry=thermo, geometry=geometry, contour=[])


def test_standard_atmosphere_reference_pressures() -> None:
    assert standard_atmosphere_pressure_pa(0.0) == pytest.approx(101_325.0)
    assert standard_atmosphere_pressure_pa(11_000.0) == pytest.approx(22_700.0, rel=0.01)
    assert standard_atmosphere_pressure_pa(20_000.0) == pytest.approx(5_529.0, rel=0.01)


def test_finite_rate_estimate_recognizes_lox_kerosene() -> None:
    efficiency, geometry_loss, pressure_loss, source = (
        estimate_finite_rate_combustion_efficiency(
            chamber_pressure_pa=7.0e6,
            throat_radius_m=0.05,
            exit_radius_m=0.22,
            oxidizer="LOX",
            fuel="RP-1",
        )
    )

    assert 0.95 < efficiency <= 1.0
    assert geometry_loss > 0.0
    assert pressure_loss > 0.0
    assert "kerosene" in source


def test_multiphase_efficiency_is_unity_without_condensed_phase() -> None:
    assert compute_multiphase_efficiency(
        condensed_mass_fraction=0.0,
        condensed_specific_heat_j_per_kg_k=900.0,
        exit_velocity_m_per_s=2800.0,
        chamber_temperature_k=3500.0,
        exit_temperature_k=2100.0,
    ) == 1.0


def test_delivered_performance_keeps_pressure_term_explicit() -> None:
    bundle = make_bundle()
    assumptions = DeliveredPerformanceAssumptions(
        combustion_efficiency=0.96,
        friction_efficiency=0.99,
        divergence_efficiency=0.98,
    )

    result = evaluate_delivered_performance(bundle, assumptions=assumptions)

    expected_nozzle_efficiency = 0.99 * 0.98
    expected_cf = (
        expected_nozzle_efficiency * bundle.thermochemistry.cf_vac
        - bundle.inputs.expansion_ratio
        * bundle.inputs.ambient_pressure_pa
        / bundle.inputs.chamber_pressure_pa
    )
    assert result.delivered_c_star_m_per_s == 0.96 * 1750.0
    assert result.delivered_cf_ambient == pytest.approx(expected_cf)
    assert result.delivered_thrust_n == pytest.approx(
        expected_cf * 7.0e6 * 0.0078
    )
    assert result.delivered_isp_vac_s == pytest.approx(
        0.96 * expected_nozzle_efficiency * 320.0
    )


def test_altitude_throttle_map_has_requested_grid() -> None:
    points = build_performance_map(
        make_bundle(),
        altitudes_m=[0.0, 10_000.0, 20_000.0],
        throttle_fractions=[0.5, 1.0],
    )

    assert len(points) == 6
    assert {point.throttle_fraction for point in points} == {0.5, 1.0}
    sea_level = next(
        point
        for point in points
        if point.altitude_m == 0.0 and point.throttle_fraction == 1.0
    )
    high_altitude = next(
        point
        for point in points
        if point.altitude_m == 20_000.0 and point.throttle_fraction == 1.0
    )
    assert high_altitude.result.delivered_thrust_n > sea_level.result.delivered_thrust_n


def test_schmucker_criterion_decreases_with_mach() -> None:
    assert schmucker_separation_pressure_ratio(3.0) < (
        schmucker_separation_pressure_ratio(2.0)
    )


def test_wall_shear_friction_integral_matches_cylindrical_reference() -> None:
    contour = [
        NozzlePoint(x_m=0.0, radius_m=0.1, area_m2=math.pi * 0.1**2),
        NozzlePoint(x_m=0.5, radius_m=0.1, area_m2=math.pi * 0.1**2),
        NozzlePoint(x_m=1.0, radius_m=0.1, area_m2=math.pi * 0.1**2),
    ]
    efficiency, loss = compute_wall_shear_friction_efficiency(
        contour=contour,
        wall_shear_stress_pa=[1_000.0, 1_000.0, 1_000.0],
        ideal_thrust_coefficient=1.5,
        throat_area_m2=0.01,
        chamber_stagnation_pressure_pa=10.0e6,
    )
    expected_loss = 2.0 * math.pi * 1_000.0 * 0.1 * 1.0 / (
        1.5 * 0.01 * 10.0e6
    )
    assert loss == pytest.approx(expected_loss)
    assert efficiency == pytest.approx(1.0 - expected_loss)

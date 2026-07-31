"""Energy-balance tests for coupled regenerative cooling."""

from __future__ import annotations

import math

import pytest

from engine.cooling import (
    AxialProfile,
    ChannelLayout,
    ChannelShape,
    CoolantCircuit,
    CoupledThermalSettings,
    run_coupled_regenerative_analysis,
)
from engine.models import (
    ChemistryMode,
    ExportBundle,
    GeometryResult,
    InputParameters,
    NozzlePoint,
    ThermochemistryResult,
)
from engine.properties import CoolantProperties, MaterialProperties


COOLANT = CoolantProperties(
    density_kg_per_m3=850.0,
    cp_j_per_kg_k=2_400.0,
    viscosity_pa_s=8.0e-4,
    thermal_conductivity_w_per_m_k=0.13,
    prandtl_number=14.769230769,
    source="test",
)

WALL = MaterialProperties(
    density_kg_per_m3=8_900.0,
    cp_j_per_kg_k=390.0,
    thermal_conductivity_w_per_m_k=310.0,
    youngs_modulus_pa=120.0e9,
    poisson_ratio=0.34,
    cte_1_per_k=17.0e-6,
    yield_strength_pa=300.0e6,
    ultimate_tensile_strength_pa=420.0e6,
    source="test",
)


def _coolant_provider(
    _fluid: str,
    _temperature: float,
    _pressure: float | None,
) -> CoolantProperties:
    return COOLANT


def _material_provider(_material: str, _temperature: float) -> MaterialProperties:
    return WALL


def _bundle() -> ExportBundle:
    inputs = InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=7.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=4.0,
        ambient_pressure_pa=101_325.0,
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        wall_thickness_m=0.001,
        throat_upstream_radius_m=0.075,
        liner_material="CuCrZr",
    )
    thermo = ThermochemistryResult(
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        propellant_description="synthetic hot gas",
        chamber_temperature_k=3_500.0,
        c_star_m_s=1_750.0,
        isp_vac_s=300.0,
        gamma=1.20,
        cp_j_per_kg_k=3_200.0,
        viscosity_pa_s=8.0e-5,
        prandtl_number=0.70,
    )
    geometry = GeometryResult(
        throat_area_m2=math.pi * 0.05**2,
        throat_radius_m=0.05,
        exit_area_m2=math.pi * 0.10**2,
        exit_radius_m=0.10,
        mass_flow_kg_per_s=10.0,
    )
    contour = [
        NozzlePoint(x_m=0.0, radius_m=0.08, area_m2=math.pi * 0.08**2),
        NozzlePoint(x_m=0.10, radius_m=0.05, area_m2=math.pi * 0.05**2),
        NozzlePoint(x_m=0.30, radius_m=0.10, area_m2=math.pi * 0.10**2),
    ]
    return ExportBundle(inputs, thermo, geometry, contour)


def _layout() -> ChannelLayout:
    return ChannelLayout(
        shape=ChannelShape.RECTANGULAR,
        channel_count=AxialProfile.constant(120.0),
        width_m=AxialProfile.constant(0.0015),
        height_m=AxialProfile.constant(0.0030),
        rib_width_m=AxialProfile.constant(0.0008),
        hot_wall_thickness_m=AxialProfile.constant(0.0010),
        roughness_m=AxialProfile.constant(5.0e-6),
    )


def _circuit() -> CoolantCircuit:
    return CoolantCircuit(
        circuit_id="regen",
        coolant_id="RP-1",
        mass_flow_kg_per_s=2.0,
        inlet_temperature_k=293.15,
        inlet_pressure_pa=12.0e6,
        opposite_hot_gas_flow=True,
    )


def _settings(*, radiation: bool) -> CoupledThermalSettings:
    return CoupledThermalSettings(
        radiation_enabled=radiation,
        initial_heat_flux_w_per_m2=1.0e6,
        maximum_iterations=80,
        wall_temperature_tolerance_k=0.1,
        relaxation_factor=0.60,
    )


def test_coupled_solver_converges_and_conserves_coolant_energy() -> None:
    result = run_coupled_regenerative_analysis(
        _bundle(),
        _layout(),
        _circuit(),
        settings=_settings(radiation=False),
        coolant_property_provider=_coolant_provider,
        material_property_provider=_material_provider,
    )

    assert result.converged
    assert result.maximum_total_heat_flux_w_per_m2 > 0.0
    assert result.coolant_outlet_pressure_pa < _circuit().inlet_pressure_pa
    assert result.total_heat_into_coolant_w == pytest.approx(
        _circuit().mass_flow_kg_per_s
        * COOLANT.cp_j_per_kg_k
        * (result.coolant_outlet_temperature_k - _circuit().inlet_temperature_k),
        rel=1.0e-9,
    )
    for station in result.stations:
        assert station.wall_temperature_hot_gas_side_k > station.wall_temperature_coolant_side_k
        assert station.wall_temperature_coolant_side_k > station.coolant_temperature_k
        assert station.radiation_heat_flux_w_per_m2 == 0.0


def test_enabled_radiation_adds_heat_to_the_regenerative_circuit() -> None:
    without_radiation = run_coupled_regenerative_analysis(
        _bundle(),
        _layout(),
        _circuit(),
        settings=_settings(radiation=False),
        coolant_property_provider=_coolant_provider,
        material_property_provider=_material_provider,
    )
    with_radiation = run_coupled_regenerative_analysis(
        _bundle(),
        _layout(),
        _circuit(),
        settings=_settings(radiation=True),
        coolant_property_provider=_coolant_provider,
        material_property_provider=_material_provider,
    )

    assert with_radiation.converged
    assert with_radiation.total_heat_into_coolant_w > without_radiation.total_heat_into_coolant_w
    assert with_radiation.maximum_hot_wall_temperature_k > 0.0
    assert max(row.radiation_heat_flux_w_per_m2 for row in with_radiation.stations) > 0.0

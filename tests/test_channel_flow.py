"""Reference and conservation tests for variable regenerative channels."""

from __future__ import annotations

import math

import pytest

from engine.cooling import (
    AxialKeyframe,
    AxialProfile,
    ChannelCrossSection,
    ChannelLayout,
    ChannelShape,
    CoolantCircuit,
    channel_fin_area_factor,
    darcy_friction_factor,
    evaluate_channel_transport,
    march_channel_circuit,
    rpa_regenerative_nusselt_number,
)
from engine.models import NozzlePoint
from engine.properties import CoolantProperties
from engine.station_mesh import build_engine_station_mesh


WATER = CoolantProperties(
    density_kg_per_m3=1_000.0,
    cp_j_per_kg_k=4_000.0,
    viscosity_pa_s=1.0e-3,
    thermal_conductivity_w_per_m_k=0.6,
    prandtl_number=6.6666666667,
    source="test",
)


def _constant_water(_fluid: str, _temperature: float, _pressure: float | None) -> CoolantProperties:
    return WATER


def _layout(*, width_m: float = 0.002, height_m: float = 0.003, helix_deg: float = 0.0) -> ChannelLayout:
    return ChannelLayout(
        shape=ChannelShape.RECTANGULAR,
        channel_count=AxialProfile.constant(100.0, minimum_value=1.0),
        width_m=AxialProfile.constant(width_m, minimum_value=1.0e-8),
        height_m=AxialProfile.constant(height_m, minimum_value=1.0e-8),
        rib_width_m=AxialProfile.constant(0.001, minimum_value=0.0),
        roughness_m=AxialProfile.constant(0.0, minimum_value=0.0),
        helix_angle_deg=AxialProfile.constant(
            helix_deg,
            minimum_value=-80.0,
            maximum_value=80.0,
        ),
    )


def _mesh() -> object:
    return build_engine_station_mesh(
        [
            NozzlePoint(x_m=0.0, radius_m=0.10, area_m2=math.pi * 0.10**2),
            NozzlePoint(x_m=0.5, radius_m=0.10, area_m2=math.pi * 0.10**2),
            NozzlePoint(x_m=1.0, radius_m=0.10, area_m2=math.pi * 0.10**2),
        ]
    )


def test_laminar_rectangular_friction_uses_shape_poiseuille_number() -> None:
    section = ChannelCrossSection(
        ChannelShape.RECTANGULAR,
        width_m=0.002,
        height_m=0.004,
    )

    factor, regime = darcy_friction_factor(1_000.0, 0.0, section)

    aspect = 0.5
    poiseuille = 96.0 * (
        1.0
        - 1.3553 * aspect
        + 1.9467 * aspect**2
        - 1.7012 * aspect**3
        + 0.9564 * aspect**4
        - 0.2537 * aspect**5
    )
    assert factor == pytest.approx(poiseuille / 1_000.0)
    assert regime == "laminar"


def test_local_transport_matches_mass_conservation_and_gnielinski() -> None:
    section = _layout().section_at(0.0)

    result = evaluate_channel_transport(
        section,
        coolant_properties=WATER,
        mass_flow_kg_per_s=1.2,
        station_radius_m=0.10,
    )

    assert result.mass_flux_kg_per_m2_s == pytest.approx(
        1.2 / section.total_flow_area_m2
    )
    assert result.velocity_m_per_s == pytest.approx(
        1.2 / (WATER.density_kg_per_m3 * section.total_flow_area_m2)
    )
    assert result.reynolds_number > 4_000.0
    assert result.flow_regime == "turbulent"
    assert result.nusselt_method == "gnielinski"
    assert result.heat_transfer_coefficient_w_per_m2_k > 0.0
    assert result.ligament_margin_m is not None


def test_helix_increases_friction_path_and_produces_dean_diagnostic() -> None:
    circuit = CoolantCircuit(
        circuit_id="water",
        coolant_id="water",
        mass_flow_kg_per_s=1.2,
        inlet_temperature_k=300.0,
        inlet_pressure_pa=5.0e6,
        opposite_hot_gas_flow=False,
    )

    straight = march_channel_circuit(
        _mesh(),
        _layout(helix_deg=0.0),
        circuit,
        property_provider=_constant_water,
    )
    helical = march_channel_circuit(
        _mesh(),
        _layout(helix_deg=60.0),
        circuit,
        property_provider=_constant_water,
    )

    assert helical.total_friction_pressure_drop_pa == pytest.approx(
        2.0 * straight.total_friction_pressure_drop_pa
    )
    assert helical.stations[0].transport.dean_number > 0.0
    assert straight.stations[0].transport.dean_number == 0.0


def test_channel_march_conserves_prescribed_heat_and_reports_both_areas() -> None:
    mesh = _mesh()
    circuit = CoolantCircuit(
        circuit_id="water",
        coolant_id="water",
        mass_flow_kg_per_s=2.0,
        inlet_temperature_k=300.0,
        inlet_pressure_pa=10.0e6,
        opposite_hot_gas_flow=False,
    )
    heat_flux = 1.0e6

    result = march_channel_circuit(
        mesh,
        _layout(),
        circuit,
        hot_wall_heat_flux_w_per_m2=heat_flux,
        property_provider=_constant_water,
    )

    expected_hot_area = 2.0 * math.pi * 0.10 * 1.0
    expected_heat = heat_flux * expected_hot_area
    assert result.total_heat_added_w == pytest.approx(expected_heat)
    assert result.outlet_temperature_k == pytest.approx(
        300.0 + expected_heat / (2.0 * WATER.cp_j_per_kg_k)
    )
    assert sum(
        station.hot_wall_area_from_previous_m2 for station in result.stations
    ) == pytest.approx(expected_hot_area)
    assert sum(
        station.coolant_wetted_area_from_previous_m2 for station in result.stations
    ) > expected_hot_area
    assert result.outlet_pressure_pa < result.inlet_pressure_pa


def test_counterflow_march_starts_at_nozzle_exit() -> None:
    circuit = CoolantCircuit(
        circuit_id="water",
        coolant_id="water",
        mass_flow_kg_per_s=1.0,
        inlet_temperature_k=300.0,
        inlet_pressure_pa=10.0e6,
        opposite_hot_gas_flow=True,
    )

    result = march_channel_circuit(
        _mesh(),
        _layout(),
        circuit,
        property_provider=_constant_water,
    )

    assert result.coolant_flow_direction == "exit-to-chamber"
    assert result.stations[0].station.station_id == "STA-00002"
    assert result.stations[-1].station.station_id == "STA-00000"


def test_variable_area_reports_signed_acceleration_pressure_change() -> None:
    layout = ChannelLayout(
        shape=ChannelShape.RECTANGULAR,
        channel_count=AxialProfile.constant(100.0, minimum_value=1.0),
        width_m=AxialProfile(
            (AxialKeyframe(0.0, 0.003), AxialKeyframe(1.0, 0.0015)),
            minimum_value=1.0e-8,
        ),
        height_m=AxialProfile.constant(0.003, minimum_value=1.0e-8),
        roughness_m=AxialProfile.constant(0.0, minimum_value=0.0),
    )
    circuit = CoolantCircuit(
        circuit_id="water",
        coolant_id="water",
        mass_flow_kg_per_s=1.0,
        inlet_temperature_k=300.0,
        inlet_pressure_pa=10.0e6,
        opposite_hot_gas_flow=False,
    )

    result = march_channel_circuit(
        _mesh(),
        layout,
        circuit,
        property_provider=_constant_water,
    )

    assert result.total_acceleration_pressure_change_pa > 0.0
    assert result.total_pressure_drop_pa == pytest.approx(
        result.total_friction_pressure_drop_pa
        + result.total_minor_pressure_drop_pa
        + result.total_acceleration_pressure_change_pa
    )


def test_rpa_coolant_specific_correlations_and_fin_factor_are_available() -> None:
    rp1 = rpa_regenerative_nusselt_number(
        100_000.0,
        10.0,
        coolant_id="RP-1",
        coolant_temperature_k=400.0,
        coolant_wall_temperature_k=800.0,
    )
    generic = rpa_regenerative_nusselt_number(
        100_000.0,
        10.0,
        coolant_id="water",
        coolant_temperature_k=400.0,
        coolant_wall_temperature_k=800.0,
    )
    factor = channel_fin_area_factor(
        channel_width_m=0.002,
        channel_height_m=0.003,
        rib_width_m=0.001,
        coolant_heat_transfer_coefficient_w_per_m2_k=20_000.0,
        wall_thermal_conductivity_w_per_m_k=300.0,
    )

    assert rp1 < generic
    assert factor > 1.0

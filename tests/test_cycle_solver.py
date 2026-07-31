"""Equation and shaft-closure tests for engine-cycle components."""

from __future__ import annotations

import pytest

from engine.cycle import (
    CycleDefinition,
    CycleType,
    PumpDefinition,
    ShaftDefinition,
    TurbineDefinition,
    evaluate_pump,
    evaluate_turbine,
    solve_cycle,
)


def _pump(pump_id: str, mass_flow: float, density: float) -> PumpDefinition:
    return PumpDefinition(
        pump_id=pump_id,
        fluid_id=pump_id,
        mass_flow_kg_per_s=mass_flow,
        density_kg_per_m3=density,
        inlet_pressure_pa=0.5e6,
        discharge_pressure_pa=12.5e6,
        efficiency=0.75,
        inlet_temperature_k=100.0,
        specific_heat_j_per_kg_k=2_000.0,
    )


def _turbine(turbine_id: str, mass_flow: float | None = None) -> TurbineDefinition:
    return TurbineDefinition(
        turbine_id=turbine_id,
        mass_flow_kg_per_s=mass_flow,
        inlet_temperature_k=900.0,
        inlet_pressure_pa=8.0e6,
        pressure_ratio=4.0,
        specific_heat_j_per_kg_k=3_000.0,
        gamma=1.25,
        isentropic_efficiency=0.75,
        mechanical_efficiency=0.98,
    )


def test_pump_power_is_volume_flow_times_pressure_rise_over_efficiency() -> None:
    pump = _pump("oxidizer", mass_flow=60.0, density=1_200.0)

    result = evaluate_pump(pump)

    expected_ideal = 60.0 / 1_200.0 * 12.0e6
    assert result.ideal_hydraulic_power_w == pytest.approx(expected_ideal)
    assert result.shaft_power_required_w == pytest.approx(expected_ideal / 0.75)
    assert result.estimated_temperature_rise_k == pytest.approx(5.0 / 3.0)


def test_turbine_uses_isentropic_temperature_drop_and_efficiencies() -> None:
    turbine = _turbine("turbine", mass_flow=3.0)

    result = evaluate_turbine(turbine)

    expected_isentropic_temperature = 900.0 * 4.0 ** (-(1.25 - 1.0) / 1.25)
    expected_outlet = 900.0 - 0.75 * (900.0 - expected_isentropic_temperature)
    expected_gas_power = 3.0 * 3_000.0 * (900.0 - expected_outlet)
    assert result.isentropic_outlet_temperature_k == pytest.approx(
        expected_isentropic_temperature
    )
    assert result.outlet_temperature_k == pytest.approx(expected_outlet)
    assert result.gas_power_extracted_w == pytest.approx(expected_gas_power)
    assert result.shaft_power_delivered_w == pytest.approx(expected_gas_power * 0.98)


def test_unspecified_turbine_flow_closes_single_shaft_power_balance() -> None:
    oxidizer_pump = _pump("oxidizer", mass_flow=60.0, density=1_200.0)
    fuel_pump = _pump("fuel", mass_flow=20.0, density=800.0)
    turbine = _turbine("main-turbine")
    cycle = CycleDefinition(
        cycle_type=CycleType.GAS_GENERATOR,
        primary_propellant_mass_flow_kg_per_s=80.0,
        pumps=(oxidizer_pump, fuel_pump),
        turbines=(turbine,),
        shafts=(
            ShaftDefinition(
                shaft_id="main-shaft",
                pump_ids=("oxidizer", "fuel"),
                turbine_ids=("main-turbine",),
                accessory_power_w=25_000.0,
            ),
        ),
    )

    result = solve_cycle(cycle)

    assert result.all_shafts_balanced
    assert result.shafts[0].power_balance_w == pytest.approx(0.0, abs=1.0e-8)
    assert result.turbines[0].mass_flow_was_solved
    assert result.turbines[0].mass_flow_kg_per_s > 0.0
    assert result.estimated_total_engine_inlet_mass_flow_kg_per_s == pytest.approx(
        80.0 + result.turbines[0].mass_flow_kg_per_s
    )


def test_independent_shafts_close_with_independent_turbine_flows() -> None:
    cycle = CycleDefinition(
        cycle_type=CycleType.STAGED_COMBUSTION,
        primary_propellant_mass_flow_kg_per_s=80.0,
        pumps=(
            _pump("oxidizer", mass_flow=60.0, density=1_200.0),
            _pump("fuel", mass_flow=20.0, density=800.0),
        ),
        turbines=(_turbine("ot"), _turbine("ft")),
        shafts=(
            ShaftDefinition("oxidizer-shaft", ("oxidizer",), ("ot",)),
            ShaftDefinition("fuel-shaft", ("fuel",), ("ft",)),
        ),
    )

    result = solve_cycle(cycle)

    assert result.all_shafts_balanced
    assert len(result.shafts) == 2
    assert result.estimated_total_engine_inlet_mass_flow_kg_per_s == 80.0
    assert result.turbines[0].mass_flow_kg_per_s != result.turbines[1].mass_flow_kg_per_s


def test_cycle_rejects_unassigned_component() -> None:
    with pytest.raises(ValueError, match="Every pump"):
        CycleDefinition(
            cycle_type=CycleType.GAS_GENERATOR,
            primary_propellant_mass_flow_kg_per_s=80.0,
            pumps=(
                _pump("oxidizer", mass_flow=60.0, density=1_200.0),
                _pump("fuel", mass_flow=20.0, density=800.0),
            ),
            turbines=(_turbine("t"),),
            shafts=(ShaftDefinition("shaft", ("oxidizer",), ("t",)),),
        )

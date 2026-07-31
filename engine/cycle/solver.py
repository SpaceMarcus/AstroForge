"""Component and shaft-power solver for preliminary engine cycles."""

from __future__ import annotations

import math

from engine.cycle.models import (
    CycleDefinition,
    CycleResult,
    CycleType,
    PumpDefinition,
    PumpResult,
    ShaftResult,
    TurbineDefinition,
    TurbineResult,
)


DEFAULT_SHAFT_CLOSURE_TOLERANCE = 1.0e-6


def evaluate_pump(definition: PumpDefinition) -> PumpResult:
    """Evaluate incompressible pump power from volume flow and pressure rise."""

    pressure_rise = definition.discharge_pressure_pa - definition.inlet_pressure_pa
    volumetric_flow = definition.mass_flow_kg_per_s / definition.density_kg_per_m3
    ideal_power = volumetric_flow * pressure_rise
    shaft_power = ideal_power / definition.efficiency
    specific_work = shaft_power / definition.mass_flow_kg_per_s
    temperature_rise = None
    if definition.specific_heat_j_per_kg_k is not None:
        # Hydraulic energy remains in pressure; only inefficiency is treated as
        # local fluid heating in this preliminary incompressible model.
        temperature_rise = (
            pressure_rise
            / definition.density_kg_per_m3
            * (1.0 / definition.efficiency - 1.0)
            / definition.specific_heat_j_per_kg_k
        )
    return PumpResult(
        definition=definition,
        pressure_rise_pa=pressure_rise,
        volumetric_flow_m3_per_s=volumetric_flow,
        ideal_hydraulic_power_w=ideal_power,
        shaft_power_required_w=shaft_power,
        specific_shaft_work_j_per_kg=specific_work,
        estimated_temperature_rise_k=temperature_rise,
    )


def turbine_specific_work(definition: TurbineDefinition) -> tuple[float, float, float]:
    """Return isentropic outlet T, actual outlet T and delivered shaft work."""

    exponent = (definition.gamma - 1.0) / definition.gamma
    isentropic_outlet_temperature = (
        definition.inlet_temperature_k
        * definition.pressure_ratio ** (-exponent)
    )
    isentropic_drop = (
        definition.inlet_temperature_k - isentropic_outlet_temperature
    )
    actual_temperature_drop = definition.isentropic_efficiency * isentropic_drop
    outlet_temperature = definition.inlet_temperature_k - actual_temperature_drop
    gas_specific_work = definition.specific_heat_j_per_kg_k * actual_temperature_drop
    shaft_specific_work = gas_specific_work * definition.mechanical_efficiency
    return isentropic_outlet_temperature, outlet_temperature, shaft_specific_work


def evaluate_turbine(
    definition: TurbineDefinition,
    *,
    solved_mass_flow_kg_per_s: float | None = None,
) -> TurbineResult:
    """Evaluate one adiabatic turbine at a given or solved mass flow."""

    mass_flow = definition.mass_flow_kg_per_s
    was_solved = mass_flow is None
    if mass_flow is None:
        if solved_mass_flow_kg_per_s is None or solved_mass_flow_kg_per_s < 0.0:
            raise ValueError("An unresolved turbine requires a non-negative solved mass flow.")
        mass_flow = solved_mass_flow_kg_per_s
    isentropic_outlet, outlet_temperature, shaft_specific_work = (
        turbine_specific_work(definition)
    )
    gas_specific_work = shaft_specific_work / definition.mechanical_efficiency
    return TurbineResult(
        definition=definition,
        mass_flow_kg_per_s=mass_flow,
        outlet_pressure_pa=definition.inlet_pressure_pa / definition.pressure_ratio,
        isentropic_outlet_temperature_k=isentropic_outlet,
        outlet_temperature_k=outlet_temperature,
        gas_specific_work_j_per_kg=gas_specific_work,
        shaft_specific_work_j_per_kg=shaft_specific_work,
        gas_power_extracted_w=mass_flow * gas_specific_work,
        shaft_power_delivered_w=mass_flow * shaft_specific_work,
        mass_flow_was_solved=was_solved,
    )


def solve_cycle(
    definition: CycleDefinition,
    *,
    shaft_closure_tolerance: float = DEFAULT_SHAFT_CLOSURE_TOLERANCE,
) -> CycleResult:
    """Close each shaft, solving one unspecified turbine flow per shaft."""

    if not math.isfinite(shaft_closure_tolerance) or shaft_closure_tolerance < 0.0:
        raise ValueError("Shaft closure tolerance must be finite and non-negative.")
    pump_results = {pump.pump_id: evaluate_pump(pump) for pump in definition.pumps}
    turbine_definitions = {
        turbine.turbine_id: turbine for turbine in definition.turbines
    }
    turbine_results: dict[str, TurbineResult] = {}
    shaft_results: list[ShaftResult] = []

    for shaft in definition.shafts:
        pump_power = sum(
            pump_results[pump_id].shaft_power_required_w for pump_id in shaft.pump_ids
        )
        power_required = pump_power + shaft.accessory_power_w
        unresolved = [
            turbine_definitions[turbine_id]
            for turbine_id in shaft.turbine_ids
            if turbine_definitions[turbine_id].mass_flow_kg_per_s is None
        ]
        if len(unresolved) > 1:
            raise ValueError(
                f"Shaft {shaft.shaft_id!r} has more than one unresolved turbine flow."
            )
        fixed_results = [
            evaluate_turbine(turbine_definitions[turbine_id])
            for turbine_id in shaft.turbine_ids
            if turbine_definitions[turbine_id].mass_flow_kg_per_s is not None
        ]
        for result in fixed_results:
            turbine_results[result.definition.turbine_id] = result
        fixed_power = sum(result.shaft_power_delivered_w for result in fixed_results)
        if unresolved:
            turbine = unresolved[0]
            _isentropic, _outlet, specific_work = turbine_specific_work(turbine)
            remaining_power = max(power_required - fixed_power, 0.0)
            solved_flow = remaining_power / specific_work
            result = evaluate_turbine(
                turbine,
                solved_mass_flow_kg_per_s=solved_flow,
            )
            turbine_results[turbine.turbine_id] = result
        turbine_power = sum(
            turbine_results[turbine_id].shaft_power_delivered_w
            for turbine_id in shaft.turbine_ids
        )
        balance = turbine_power - power_required
        closure = abs(balance) / max(power_required, 1.0)
        shaft_results.append(
            ShaftResult(
                definition=shaft,
                pump_power_required_w=pump_power,
                accessory_power_w=shaft.accessory_power_w,
                total_power_required_w=power_required,
                turbine_power_delivered_w=turbine_power,
                power_balance_w=balance,
                closure_relative=closure,
                balanced=closure <= shaft_closure_tolerance,
            )
        )

    ordered_pumps = tuple(pump_results[pump.pump_id] for pump in definition.pumps)
    ordered_turbines = tuple(
        turbine_results[turbine.turbine_id] for turbine in definition.turbines
    )
    turbine_flow = sum(result.mass_flow_kg_per_s for result in ordered_turbines)
    total_pump_power = sum(result.shaft_power_required_w for result in ordered_pumps)
    total_accessory = sum(shaft.accessory_power_w for shaft in definition.shafts)
    total_turbine_power = sum(
        result.shaft_power_delivered_w for result in ordered_turbines
    )
    inlet_mass_flow = definition.primary_propellant_mass_flow_kg_per_s
    notes = [
        "pump power: incompressible volume-flow pressure work divided by efficiency",
        "turbine power: ideal-gas isentropic temperature drop with isentropic and mechanical efficiencies",
    ]
    if definition.cycle_type is CycleType.GAS_GENERATOR:
        inlet_mass_flow += turbine_flow
        notes.append(
            "gas-generator turbine flow is treated as additional open-cycle propellant flow"
        )
    else:
        notes.append(
            "closed-cycle turbine working flow is reported but not added to engine inlet mass flow"
        )
    return CycleResult(
        definition=definition,
        pumps=ordered_pumps,
        turbines=ordered_turbines,
        shafts=tuple(shaft_results),
        total_pump_power_required_w=total_pump_power,
        total_accessory_power_w=total_accessory,
        total_turbine_power_delivered_w=total_turbine_power,
        total_power_balance_w=total_turbine_power - total_pump_power - total_accessory,
        turbine_working_mass_flow_kg_per_s=turbine_flow,
        turbine_working_mass_flow_fraction=(
            turbine_flow / definition.primary_propellant_mass_flow_kg_per_s
        ),
        estimated_total_engine_inlet_mass_flow_kg_per_s=inlet_mass_flow,
        all_shafts_balanced=all(result.balanced for result in shaft_results),
        notes=tuple(notes),
    )

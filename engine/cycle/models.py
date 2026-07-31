"""Domain models for preliminary liquid-rocket feed-system cycles."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math


class CycleType(str, Enum):
    """Supported topology labels; component equations remain topology-neutral."""

    PRESSURE_FED = "pressure-fed"
    GAS_GENERATOR = "gas-generator"
    STAGED_COMBUSTION = "staged-combustion"
    FULL_FLOW_STAGED_COMBUSTION = "full-flow-staged-combustion"
    EXPANDER = "expander"


@dataclass(frozen=True, slots=True)
class PumpDefinition:
    pump_id: str
    fluid_id: str
    mass_flow_kg_per_s: float
    density_kg_per_m3: float
    inlet_pressure_pa: float
    discharge_pressure_pa: float
    efficiency: float
    inlet_temperature_k: float | None = None
    specific_heat_j_per_kg_k: float | None = None

    def __post_init__(self) -> None:
        if not self.pump_id.strip() or not self.fluid_id.strip():
            raise ValueError("Pump and fluid IDs must not be empty.")
        _positive(self.mass_flow_kg_per_s, "Pump mass flow")
        _positive(self.density_kg_per_m3, "Pump fluid density")
        _positive(self.inlet_pressure_pa, "Pump inlet pressure")
        if self.discharge_pressure_pa <= self.inlet_pressure_pa:
            raise ValueError("Pump discharge pressure must exceed inlet pressure.")
        _efficiency(self.efficiency, "Pump efficiency")
        if self.inlet_temperature_k is not None:
            _positive(self.inlet_temperature_k, "Pump inlet temperature")
        if self.specific_heat_j_per_kg_k is not None:
            _positive(self.specific_heat_j_per_kg_k, "Pump fluid specific heat")


@dataclass(frozen=True, slots=True)
class TurbineDefinition:
    turbine_id: str
    mass_flow_kg_per_s: float | None
    inlet_temperature_k: float
    inlet_pressure_pa: float
    pressure_ratio: float
    specific_heat_j_per_kg_k: float
    gamma: float
    isentropic_efficiency: float
    mechanical_efficiency: float = 0.98

    def __post_init__(self) -> None:
        if not self.turbine_id.strip():
            raise ValueError("Turbine ID must not be empty.")
        if self.mass_flow_kg_per_s is not None:
            _positive(self.mass_flow_kg_per_s, "Turbine mass flow")
        _positive(self.inlet_temperature_k, "Turbine inlet temperature")
        _positive(self.inlet_pressure_pa, "Turbine inlet pressure")
        if not math.isfinite(self.pressure_ratio) or self.pressure_ratio <= 1.0:
            raise ValueError("Turbine pressure ratio must exceed one.")
        _positive(self.specific_heat_j_per_kg_k, "Turbine gas specific heat")
        if not math.isfinite(self.gamma) or self.gamma <= 1.0:
            raise ValueError("Turbine gas gamma must exceed one.")
        _efficiency(self.isentropic_efficiency, "Turbine isentropic efficiency")
        _efficiency(self.mechanical_efficiency, "Turbine mechanical efficiency")


@dataclass(frozen=True, slots=True)
class ShaftDefinition:
    shaft_id: str
    pump_ids: tuple[str, ...]
    turbine_ids: tuple[str, ...]
    accessory_power_w: float = 0.0

    def __post_init__(self) -> None:
        if not self.shaft_id.strip():
            raise ValueError("Shaft ID must not be empty.")
        if not self.pump_ids:
            raise ValueError("Each shaft must drive at least one pump.")
        if not self.turbine_ids:
            raise ValueError("Each shaft must include at least one turbine.")
        if not math.isfinite(self.accessory_power_w) or self.accessory_power_w < 0.0:
            raise ValueError("Shaft accessory power must be finite and non-negative.")


@dataclass(frozen=True, slots=True)
class CycleDefinition:
    cycle_type: CycleType
    primary_propellant_mass_flow_kg_per_s: float
    pumps: tuple[PumpDefinition, ...]
    turbines: tuple[TurbineDefinition, ...]
    shafts: tuple[ShaftDefinition, ...]
    label: str = "Engine cycle"
    metadata: dict[str, str | float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("Cycle label must not be empty.")
        _positive(
            self.primary_propellant_mass_flow_kg_per_s,
            "Primary propellant mass flow",
        )
        if not self.pumps:
            raise ValueError("A turbopump cycle requires at least one pump.")
        if not self.turbines:
            raise ValueError("A turbopump cycle requires at least one turbine.")
        if not self.shafts:
            raise ValueError("A turbopump cycle requires at least one shaft.")
        _unique_ids((pump.pump_id for pump in self.pumps), "pump")
        _unique_ids((turbine.turbine_id for turbine in self.turbines), "turbine")
        _unique_ids((shaft.shaft_id for shaft in self.shafts), "shaft")
        pump_ids = {pump.pump_id for pump in self.pumps}
        turbine_ids = {turbine.turbine_id for turbine in self.turbines}
        assigned_pumps = [pump_id for shaft in self.shafts for pump_id in shaft.pump_ids]
        assigned_turbines = [
            turbine_id for shaft in self.shafts for turbine_id in shaft.turbine_ids
        ]
        if set(assigned_pumps) != pump_ids or len(assigned_pumps) != len(pump_ids):
            raise ValueError("Every pump must be assigned to exactly one shaft.")
        if set(assigned_turbines) != turbine_ids or len(assigned_turbines) != len(turbine_ids):
            raise ValueError("Every turbine must be assigned to exactly one shaft.")


@dataclass(frozen=True, slots=True)
class PumpResult:
    definition: PumpDefinition
    pressure_rise_pa: float
    volumetric_flow_m3_per_s: float
    ideal_hydraulic_power_w: float
    shaft_power_required_w: float
    specific_shaft_work_j_per_kg: float
    estimated_temperature_rise_k: float | None


@dataclass(frozen=True, slots=True)
class TurbineResult:
    definition: TurbineDefinition
    mass_flow_kg_per_s: float
    outlet_pressure_pa: float
    isentropic_outlet_temperature_k: float
    outlet_temperature_k: float
    gas_specific_work_j_per_kg: float
    shaft_specific_work_j_per_kg: float
    gas_power_extracted_w: float
    shaft_power_delivered_w: float
    mass_flow_was_solved: bool


@dataclass(frozen=True, slots=True)
class ShaftResult:
    definition: ShaftDefinition
    pump_power_required_w: float
    accessory_power_w: float
    total_power_required_w: float
    turbine_power_delivered_w: float
    power_balance_w: float
    closure_relative: float
    balanced: bool


@dataclass(frozen=True, slots=True)
class CycleResult:
    definition: CycleDefinition
    pumps: tuple[PumpResult, ...]
    turbines: tuple[TurbineResult, ...]
    shafts: tuple[ShaftResult, ...]
    total_pump_power_required_w: float
    total_accessory_power_w: float
    total_turbine_power_delivered_w: float
    total_power_balance_w: float
    turbine_working_mass_flow_kg_per_s: float
    turbine_working_mass_flow_fraction: float
    estimated_total_engine_inlet_mass_flow_kg_per_s: float
    all_shafts_balanced: bool
    notes: tuple[str, ...] = ()


def _positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite.")


def _efficiency(value: float, label: str) -> None:
    if not math.isfinite(value) or not 0.0 < value <= 1.0:
        raise ValueError(f"{label} must lie in (0, 1].")


def _unique_ids(values, label: str) -> None:
    identifiers = list(values)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"Duplicate {label} IDs are not allowed.")

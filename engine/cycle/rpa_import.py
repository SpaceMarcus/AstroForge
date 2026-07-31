"""Map RPA 2.3 propellant-feed blocks into reviewable cycle seeds."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from engine.cycle.models import CycleType


@dataclass(frozen=True, slots=True)
class RpaBoosterPumpSeed:
    inlet_pressure_pa: float | None
    discharge_pressure_pa: float | None
    efficiency: float | None
    hydraulic_turbine: bool
    turbine_pressure_ratio: float | None
    turbine_efficiency: float | None
    rotational_speed_rpm: float | None


@dataclass(frozen=True, slots=True)
class RpaMainPumpSeed:
    side: str
    inlet_pressure_pa: float | None
    inlet_velocity_m_per_s: float | None
    efficiency: float | None
    valve_pressure_drop_pa: float
    cooling_pressure_drop_pa: float
    injector_pressure_drop_pa: float
    fixed_pressure_drop_pa: float
    booster_pump: RpaBoosterPumpSeed | None
    branch_count: int

    @property
    def known_main_path_pressure_drop_pa(self) -> float:
        return (
            self.valve_pressure_drop_pa
            + self.cooling_pressure_drop_pa
            + self.injector_pressure_drop_pa
            + self.fixed_pressure_drop_pa
        )


@dataclass(frozen=True, slots=True)
class RpaCombustionDeviceSeed:
    device_type: str
    pressure_pa: float | None
    pressure_recovery_factor: float | None
    maximum_temperature_k: float | None


@dataclass(frozen=True, slots=True)
class RpaTurbineSeed:
    arrangement: str
    pressure_ratio: float
    efficiency: float
    rotational_speed_rpm: float | None


@dataclass(frozen=True, slots=True)
class RpaCycleSeed:
    cycle_type: CycleType
    oxidizer_pump: RpaMainPumpSeed
    fuel_pump: RpaMainPumpSeed
    combustion_devices: tuple[RpaCombustionDeviceSeed, ...]
    turbines: tuple[RpaTurbineSeed, ...]
    estimate_dry_mass: bool
    warnings: tuple[str, ...] = ()


def cycle_seed_from_rpa_config(raw_config: dict[str, Any]) -> RpaCycleSeed | None:
    """Return an SI cycle seed when an RPA turbopump block is present."""

    feed_root = _mapping(
        raw_config.get("propelantFeedSystem")
        or raw_config.get("propellantFeedSystem")
    )
    turbopump = _mapping(feed_root.get("turbopumpFeedSystem"))
    if not turbopump:
        return None
    cycle_type = _cycle_type(str(turbopump.get("cycle", "")))
    warnings: list[str] = []
    oxidizer = _main_pump_seed("oxidizer", turbopump.get("oxidizerFeedSystem"))
    fuel = _main_pump_seed("fuel", turbopump.get("fuelFeedSystem"))
    devices = tuple(
        _combustion_device_seed(item)
        for item in _sequence(turbopump.get("gasGenerators"))
        if isinstance(item, dict)
    )
    turbines = tuple(
        _turbine_seed(item)
        for item in _sequence(turbopump.get("turbines"))
        if isinstance(item, dict)
    )
    if not turbines:
        warnings.append("RPA cycle block does not define a turbine.")
    if oxidizer.booster_pump is not None or fuel.booster_pump is not None:
        warnings.append(
            "RPA booster-pump data was imported for review but is not yet included in the active shaft solve."
        )
    if oxidizer.branch_count or fuel.branch_count:
        warnings.append(
            "RPA optional feed branches were counted but require explicit mass-flow allocation before solving."
        )
    return RpaCycleSeed(
        cycle_type=cycle_type,
        oxidizer_pump=oxidizer,
        fuel_pump=fuel,
        combustion_devices=devices,
        turbines=turbines,
        estimate_dry_mass=bool(feed_root.get("estimateDryMass", False)),
        warnings=tuple(warnings),
    )


def _main_pump_seed(side: str, value: Any) -> RpaMainPumpSeed:
    block = _mapping(value)
    branches = _sequence(block.get("branches"))
    booster = _mapping(block.get("boosterPump"))
    return RpaMainPumpSeed(
        side=side,
        inlet_pressure_pa=_quantity(block.get("inletPressure"), "pressure"),
        inlet_velocity_m_per_s=_quantity(block.get("inletVelocity"), "velocity"),
        efficiency=_optional_number(block.get("pumpEfficiency")),
        valve_pressure_drop_pa=_quantity(block.get("valvePressureDrop"), "pressure") or 0.0,
        cooling_pressure_drop_pa=_quantity(block.get("coolingPressureDrop"), "pressure") or 0.0,
        injector_pressure_drop_pa=_quantity(block.get("injectorPressureDrop"), "pressure") or 0.0,
        fixed_pressure_drop_pa=_quantity(block.get("fixedPressureDrop"), "pressure") or 0.0,
        booster_pump=(
            RpaBoosterPumpSeed(
                inlet_pressure_pa=_quantity(booster.get("inletPressure"), "pressure"),
                discharge_pressure_pa=_quantity(
                    booster.get("dischargePressure"), "pressure"
                ),
                efficiency=_optional_number(booster.get("pumpEfficiency")),
                hydraulic_turbine=bool(booster.get("hydraulicTurbine", False)),
                turbine_pressure_ratio=_optional_number(
                    booster.get("turbinePressureRatio")
                ),
                turbine_efficiency=_optional_number(booster.get("turbineEfficiency")),
                rotational_speed_rpm=_quantity(
                    booster.get("rotationalSpeed"), "speed"
                ),
            )
            if booster
            else None
        ),
        branch_count=len(branches),
    )


def _combustion_device_seed(value: dict[str, Any]) -> RpaCombustionDeviceSeed:
    return RpaCombustionDeviceSeed(
        device_type=str(value.get("ggType", "unspecified")),
        pressure_pa=_quantity(value.get("pressure"), "pressure"),
        pressure_recovery_factor=_optional_number(value.get("sigma")),
        maximum_temperature_k=_quantity(value.get("maxTemperature"), "temperature"),
    )


def _turbine_seed(value: dict[str, Any]) -> RpaTurbineSeed:
    pressure_ratio = _required_number(
        value.get("turbinePressureRatio"), "turbine pressure ratio"
    )
    efficiency = _required_number(value.get("turbineEfficiency"), "turbine efficiency")
    return RpaTurbineSeed(
        arrangement=str(value.get("ggType", "unspecified")),
        pressure_ratio=pressure_ratio,
        efficiency=efficiency,
        rotational_speed_rpm=_quantity(value.get("rotationalSpeed"), "speed"),
    )


def _cycle_type(value: str) -> CycleType:
    normalized = " ".join(value.lower().replace("_", " ").replace("-", " ").split())
    aliases = {
        "gas generator": CycleType.GAS_GENERATOR,
        "staged combustion": CycleType.STAGED_COMBUSTION,
        "full flow staged combustion": CycleType.FULL_FLOW_STAGED_COMBUSTION,
        "expander": CycleType.EXPANDER,
        "expander cycle": CycleType.EXPANDER,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported RPA turbopump cycle type: {value!r}.") from exc


def _quantity(value: Any, quantity: str) -> float | None:
    block = _mapping(value)
    if not block:
        return None
    number = _optional_number(block.get("value"))
    if number is None:
        return None
    unit = str(block.get("unit", "")).strip().lower().replace(" ", "")
    factors = {
        "pressure": {
            "pa": 1.0,
            "kpa": 1.0e3,
            "mpa": 1.0e6,
            "bar": 1.0e5,
            "atm": 101_325.0,
            "psi": 6_894.757293168,
        },
        "velocity": {"m/s": 1.0, "ft/s": 0.3048},
        "temperature": {"k": 1.0},
        "speed": {"rpm": 1.0, "1/min": 1.0},
    }
    factor = factors[quantity].get(unit)
    if factor is None:
        raise ValueError(f"Unsupported RPA {quantity} unit: {block.get('unit')!r}.")
    return number * factor


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [] if value is None else [value]


def _optional_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _required_number(value: Any, label: str) -> float:
    result = _optional_number(value)
    if result is None:
        raise ValueError(f"RPA {label} must be finite and numeric.")
    return result

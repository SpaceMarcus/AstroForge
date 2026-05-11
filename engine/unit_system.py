"""Central unit presets and SI/display conversions for AstraForge."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

NEWTONS_PER_TF = 9_806.65
PASCALS_PER_BAR = 100_000.0
PASCALS_PER_MPA = 1_000_000.0
PASCALS_PER_PSI = 6_894.757293168
METERS_PER_MILLIMETER = 1.0e-3
METERS_PER_INCH = 0.0254
METERS_PER_FOOT = 0.3048
KILOGRAMS_PER_LBM = 0.45359237
SQUARE_METERS_PER_SQUARE_INCH = METERS_PER_INCH**2
CUBIC_METERS_PER_CUBIC_INCH = METERS_PER_INCH**3
KG_PER_M3_PER_LBM_PER_FT3 = 16.01846337396014


class UnitPreset(str, Enum):
    """User-selectable display presets. Internal calculations remain in SI."""

    SI = "si"
    SI_CAD = "si-cad"
    US = "us"
    COMMON = "common"


@dataclass(frozen=True, slots=True)
class UnitSpec:
    """Unit conversion spec for one quantity inside one preset."""

    symbol: str
    scale_to_display: float
    offset_to_display: float = 0.0
    decimals: int = 3

    def to_display(self, value_si: float) -> float:
        return value_si * self.scale_to_display + self.offset_to_display

    def from_display(self, value_display: float) -> float:
        return (value_display - self.offset_to_display) / self.scale_to_display


UNIT_PRESET_LABELS: dict[UnitPreset, str] = {
    UnitPreset.SI: "SI",
    UnitPreset.SI_CAD: "SI-CAD",
    UnitPreset.US: "US",
    UnitPreset.COMMON: "Common",
}


_IDENTITY = UnitSpec(symbol="", scale_to_display=1.0, decimals=4)

UNIT_SPECS: dict[UnitPreset, dict[str, UnitSpec]] = {
    UnitPreset.SI: {
        "force": UnitSpec("N", 1.0, decimals=2),
        "pressure": UnitSpec("Pa", 1.0, decimals=0),
        "length": UnitSpec("m", 1.0, decimals=4),
        "area": UnitSpec("m^2", 1.0, decimals=6),
        "volume": UnitSpec("m^3", 1.0, decimals=6),
        "mass": UnitSpec("kg", 1.0, decimals=3),
        "mass_flow": UnitSpec("kg/s", 1.0, decimals=4),
        "temperature": UnitSpec("K", 1.0, decimals=2),
        "velocity": UnitSpec("m/s", 1.0, decimals=2),
        "density": UnitSpec("kg/m^3", 1.0, decimals=4),
        "heat_flux": UnitSpec("W/m^2", 1.0, decimals=2),
        "heat_transfer_coefficient": UnitSpec("W/m^2/K", 1.0, decimals=2),
        "isp": UnitSpec("s", 1.0, decimals=2),
        "specific_energy": UnitSpec("J/kg", 1.0, decimals=2),
        "specific_heat": UnitSpec("J/kg/K", 1.0, decimals=2),
        "viscosity": UnitSpec("Pa s", 1.0, decimals=6),
        "thermal_conductivity": UnitSpec("W/m/K", 1.0, decimals=5),
        "molecular_weight": UnitSpec("g/mol", 1_000.0, decimals=4),
        "dimensionless": UnitSpec("", 1.0, decimals=4),
    },
    UnitPreset.SI_CAD: {
        "force": UnitSpec("kN", 1.0e-3, decimals=3),
        "pressure": UnitSpec("bar", 1.0 / PASCALS_PER_BAR, decimals=4),
        "length": UnitSpec("mm", 1.0 / METERS_PER_MILLIMETER, decimals=2),
        "area": UnitSpec("mm^2", 1.0 / (METERS_PER_MILLIMETER**2), decimals=2),
        "volume": UnitSpec("mm^3", 1.0 / (METERS_PER_MILLIMETER**3), decimals=2),
        "mass": UnitSpec("kg", 1.0, decimals=3),
        "mass_flow": UnitSpec("kg/s", 1.0, decimals=4),
        "temperature": UnitSpec("K", 1.0, decimals=2),
        "velocity": UnitSpec("m/s", 1.0, decimals=2),
        "density": UnitSpec("kg/m^3", 1.0, decimals=4),
        "heat_flux": UnitSpec("W/m^2", 1.0, decimals=2),
        "heat_transfer_coefficient": UnitSpec("W/m^2/K", 1.0, decimals=2),
        "isp": UnitSpec("s", 1.0, decimals=2),
        "specific_energy": UnitSpec("J/kg", 1.0, decimals=2),
        "specific_heat": UnitSpec("J/kg/K", 1.0, decimals=2),
        "viscosity": UnitSpec("Pa s", 1.0, decimals=6),
        "thermal_conductivity": UnitSpec("W/m/K", 1.0, decimals=5),
        "molecular_weight": UnitSpec("g/mol", 1_000.0, decimals=4),
        "dimensionless": UnitSpec("", 1.0, decimals=4),
    },
    UnitPreset.US: {
        "force": UnitSpec("lbf", 1.0 / 4.4482216152605, decimals=2),
        "pressure": UnitSpec("psia", 1.0 / PASCALS_PER_PSI, decimals=3),
        "length": UnitSpec("in", 1.0 / METERS_PER_INCH, decimals=3),
        "area": UnitSpec("in^2", 1.0 / SQUARE_METERS_PER_SQUARE_INCH, decimals=3),
        "volume": UnitSpec("in^3", 1.0 / CUBIC_METERS_PER_CUBIC_INCH, decimals=3),
        "mass": UnitSpec("lbm", 1.0 / KILOGRAMS_PER_LBM, decimals=3),
        "mass_flow": UnitSpec("lbm/s", 1.0 / KILOGRAMS_PER_LBM, decimals=4),
        "temperature": UnitSpec("degR", 9.0 / 5.0, decimals=2),
        "velocity": UnitSpec("ft/s", 1.0 / METERS_PER_FOOT, decimals=2),
        "density": UnitSpec("lbm/ft^3", 1.0 / KG_PER_M3_PER_LBM_PER_FT3, decimals=4),
        "heat_flux": UnitSpec("W/m^2", 1.0, decimals=2),
        "heat_transfer_coefficient": UnitSpec("W/m^2/K", 1.0, decimals=2),
        "isp": UnitSpec("s", 1.0, decimals=2),
        "specific_energy": UnitSpec("J/kg", 1.0, decimals=2),
        "specific_heat": UnitSpec("J/kg/K", 1.0, decimals=2),
        "viscosity": UnitSpec("Pa s", 1.0, decimals=6),
        "thermal_conductivity": UnitSpec("W/m/K", 1.0, decimals=5),
        "molecular_weight": UnitSpec("g/mol", 1_000.0, decimals=4),
        "dimensionless": UnitSpec("", 1.0, decimals=4),
    },
    UnitPreset.COMMON: {
        "force": UnitSpec("kN", 1.0e-3, decimals=3),
        "pressure": UnitSpec("bar", 1.0 / PASCALS_PER_BAR, decimals=4),
        "length": UnitSpec("mm", 1.0 / METERS_PER_MILLIMETER, decimals=2),
        "area": UnitSpec("cm^2", 10_000.0, decimals=3),
        "volume": UnitSpec("cm^3", 1_000_000.0, decimals=3),
        "mass": UnitSpec("kg", 1.0, decimals=3),
        "mass_flow": UnitSpec("kg/s", 1.0, decimals=4),
        "temperature": UnitSpec("K", 1.0, decimals=2),
        "velocity": UnitSpec("m/s", 1.0, decimals=2),
        "density": UnitSpec("kg/m^3", 1.0, decimals=4),
        "heat_flux": UnitSpec("W/m^2", 1.0, decimals=2),
        "heat_transfer_coefficient": UnitSpec("W/m^2/K", 1.0, decimals=2),
        "isp": UnitSpec("s", 1.0, decimals=2),
        "specific_energy": UnitSpec("J/kg", 1.0, decimals=2),
        "specific_heat": UnitSpec("J/kg/K", 1.0, decimals=2),
        "viscosity": UnitSpec("Pa s", 1.0, decimals=6),
        "thermal_conductivity": UnitSpec("W/m/K", 1.0, decimals=5),
        "molecular_weight": UnitSpec("g/mol", 1_000.0, decimals=4),
        "dimensionless": UnitSpec("", 1.0, decimals=4),
    },
}


def convert_to_display(value_si: float | None, quantity: str, preset: UnitPreset) -> float | None:
    """Convert an SI value into the selected display preset."""

    if value_si is None:
        return None
    spec = UNIT_SPECS[preset].get(quantity, _IDENTITY)
    return spec.to_display(value_si)


def convert_from_display(value_display: float | None, quantity: str, preset: UnitPreset) -> float | None:
    """Convert a displayed value back into SI."""

    if value_display is None:
        return None
    spec = UNIT_SPECS[preset].get(quantity, _IDENTITY)
    return spec.from_display(value_display)


def get_unit_symbol(quantity: str, preset: UnitPreset) -> str:
    """Return the display symbol for the selected quantity/preset pair."""

    return UNIT_SPECS[preset].get(quantity, _IDENTITY).symbol


def format_number(value: float, decimals: int) -> str:
    """Format a float compactly while keeping the requested precision."""

    return f"{value:.{decimals}f}"


def format_quantity(
    value_si: float | None,
    quantity: str,
    preset: UnitPreset,
    *,
    include_unit: bool = False,
    include_secondary: bool = False,
) -> str:
    """Format an SI value for display in the selected unit preset."""

    if value_si is None:
        return "--"

    spec = UNIT_SPECS[preset].get(quantity, _IDENTITY)
    display_value = spec.to_display(value_si)
    text = format_number(display_value, spec.decimals)
    if include_unit and spec.symbol:
        text = f"{text} {spec.symbol}"

    if include_secondary and preset is UnitPreset.COMMON and quantity == "force":
        tf_value = value_si / NEWTONS_PER_TF
        text = f"{text} ({tf_value:.3f} tf)" if include_unit else f"{text} ({tf_value:.3f} tf)"

    return text


def format_axis_label(name: str, quantity: str, preset: UnitPreset) -> str:
    """Return a display label with the preset-specific unit symbol."""

    symbol = get_unit_symbol(quantity, preset)
    return f"{name} [{symbol}]" if symbol else name

"""Shared domain models used across validation, chemistry, geometry and export."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ChemistryMode(str, Enum):
    """Supported thermochemistry modes exposed to the rest of the project."""

    EQUILIBRIUM = "equilibrium"
    FROZEN = "frozen"
    FROZEN_AT_THROAT = "frozen-at-throat"


class NozzleContourMethod(str, Enum):
    """Supported nozzle contour families."""

    BELL = "bell"
    CONICAL = "conical"
    CONIC = "conical"
    AEROSPIKE = "aerospike"


class BellContourVariant(str, Enum):
    """Bell-nozzle subtypes shown in the GUI."""

    PARABOLA = "parabola"
    TIC = "tic"
    TOC = "toc"


class ManufacturingMode(str, Enum):
    """High-level manufacturing families prepared in the GUI."""

    TRADITIONAL = "traditional"
    ADDITIVE = "additive"


class ManufacturingRoute(str, Enum):
    """Manufacturing routes prepared for liner and cooling-wall choices."""

    MILLED_CHANNELS_CLOSEOUT = "milled-channels-closeout"
    TUBE_WALL_BRAZED_TUBE = "tube-wall-brazed-tube"
    ELECTROFORMED_CLOSEOUT = "electroformed-closeout"
    LPBF = "lpbf"
    LPDED = "lp-ded"


class WallThicknessMode(str, Enum):
    """How the hot-gas-to-coolant separating wall is described in the MVP."""

    CONSTANT = "constant"
    VARIABLE_FUTURE = "variable-future"


class OFSweepMetric(str, Enum):
    """Selectable ordinate for the O/F sweep plot."""

    ISP_VAC = "isp_vac"
    C_STAR = "c_star"


@dataclass(slots=True)
class InputParameters:
    """Validated engine design inputs kept internally in SI units."""

    fuel: str
    oxidizer: str
    chamber_pressure_pa: float
    thrust_n: float
    mixture_ratio: float
    expansion_ratio: float
    ambient_pressure_pa: float
    contraction_ratio: float | None = None
    characteristic_length_m: float | None = None
    chemistry_mode: ChemistryMode = ChemistryMode.EQUILIBRIUM
    contour_method: NozzleContourMethod = NozzleContourMethod.BELL
    bell_variant: BellContourVariant = BellContourVariant.PARABOLA
    manual_nozzle_length_m: float | None = None
    throat_upstream_radius_m: float | None = None
    throat_downstream_radius_m: float | None = None
    convergent_half_angle_deg: float = 45.0
    manufacturing_mode: ManufacturingMode = ManufacturingMode.TRADITIONAL
    manufacturing_route: ManufacturingRoute = ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT
    liner_material: str = "CuCrZr"
    liner_coating_enabled: bool = False
    liner_coating: str | None = None
    wall_thickness_mode: WallThicknessMode = WallThicknessMode.CONSTANT
    wall_thickness_m: float | None = 0.0015


@dataclass(slots=True)
class ThermochemistryState:
    """Thermochemical state for a discrete chamber, throat, exit or interpolated point."""

    label: str
    area_ratio: float | None = None
    temperature_k: float | None = None
    density_kg_per_m3: float | None = None
    enthalpy_j_per_kg: float | None = None
    cp_j_per_kg_k: float | None = None
    viscosity_pa_s: float | None = None
    thermal_conductivity_w_per_m_k: float | None = None
    prandtl_number: float | None = None
    gamma: float | None = None
    molecular_weight_kg_per_mol: float | None = None
    mach_number: float | None = None
    velocity_m_per_s: float | None = None
    reynolds_number: float | None = None
    adiabatic_wall_temperature_k: float | None = None
    thermal_boundary_layer_thickness_m: float | None = None
    velocity_boundary_layer_thickness_m: float | None = None
    species_mass_fractions: dict[str, float] = field(default_factory=dict)
    species_mole_fractions: dict[str, float] = field(default_factory=dict)
    source: str = "rocketcea"


@dataclass(slots=True)
class ThermochemistryResult:
    """Thermochemical performance and transport properties in SI units."""

    chemistry_mode: ChemistryMode
    propellant_description: str
    chamber_temperature_k: float
    c_star_m_s: float
    isp_vac_s: float
    isp_amb_s: float | None = None
    cf_vac: float | None = None
    cf_amb: float | None = None
    gamma: float | None = None
    molecular_weight_kg_per_mol: float | None = None
    cp_j_per_kg_k: float | None = None
    viscosity_pa_s: float | None = None
    thermal_conductivity_w_per_m_k: float | None = None
    prandtl_number: float | None = None
    chamber_density_kg_per_m3: float | None = None
    exit_pressure_pa: float | None = None
    exit_temperature_k: float | None = None
    optimal_expansion_ratio: float | None = None
    species_mass_fractions: dict[str, float] = field(default_factory=dict)
    species_mole_fractions: dict[str, float] = field(default_factory=dict)
    species_summary: dict[str, dict[str, float]] = field(default_factory=dict)
    station_states: dict[str, ThermochemistryState] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GeometryResult:
    """First-order engine geometry derived from performance and design inputs."""

    throat_area_m2: float
    throat_radius_m: float
    exit_area_m2: float
    exit_radius_m: float
    mass_flow_kg_per_s: float
    chamber_area_m2: float | None = None
    chamber_radius_m: float | None = None
    chamber_volume_m3: float | None = None
    chamber_length_m: float | None = None
    contour_length_m: float | None = None
    current_expansion_ratio: float | None = None
    optimal_expansion_ratio: float | None = None
    reference_conical_length_m: float | None = None
    current_nozzle_length_m: float | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NozzlePoint:
    """Axisymmetric nozzle contour point."""

    x_m: float
    radius_m: float
    area_m2: float


@dataclass(slots=True)
class ThermochemistryProfilePoint:
    """Thermochemical state mapped to a contour point."""

    x_m: float
    radius_m: float
    area_m2: float
    region: str
    state: ThermochemistryState
    station_index: int | None = None


@dataclass(slots=True)
class SeparationCriterion:
    """Named separation rule that can be swapped out later."""

    name: str
    wall_to_ambient_pressure_ratio_limit: float


@dataclass(slots=True)
class PredictedSeparationPoint:
    """Predicted separation point on the current contour."""

    station_index: int
    x_m: float
    radius_m: float
    area_ratio: float
    static_pressure_pa: float | None
    criterion_name: str
    reason: str


@dataclass(slots=True)
class ContourMarker:
    """Visual marker shown on a contour plot."""

    label: str
    x_m: float
    radius_m: float
    color: str = "#101010"
    station_index: int | None = None


@dataclass(slots=True)
class OFSweepPoint:
    """Single O/F sweep sample for plotting and metric selection."""

    mixture_ratio: float
    equivalence_ratio: float | None
    c_star_m_s: float
    isp_vac_s: float
    chamber_temperature_k: float
    is_fuel_rich: bool
    is_oxidizer_rich: bool


@dataclass(slots=True)
class OFSweepResult:
    """Sweep of O/F ratio versus key performance metrics for one propellant pair."""

    fuel: str
    oxidizer: str
    chemistry_mode: ChemistryMode
    chamber_pressure_pa: float
    expansion_ratio: float
    stoichiometric_mixture_ratio: float | None
    peak_isp_vac_mixture_ratio: float
    peak_c_star_mixture_ratio: float
    points: list[OFSweepPoint]


@dataclass(slots=True)
class ExportBundle:
    """Bundle passed to exporters after a complete design run."""

    inputs: InputParameters
    thermochemistry: ThermochemistryResult
    geometry: GeometryResult
    contour: list[NozzlePoint]
    thermochemistry_profile: list[ThermochemistryProfilePoint] = field(default_factory=list)
    of_sweep: OFSweepResult | None = None
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

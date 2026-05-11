"""Preliminary chamber-geometry helpers and empirical L* reference data."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

from engine.models import ExportBundle, ThermochemistryProfilePoint

NASA_LSTAR_SOURCE = (
    "Source: NASA SP-125, Huzel & Huang, Design of Liquid Propellant Rocket Engines"
)
FIGURE_8_15_SOURCE = (
    "Source: NASA SP-125, Huzel & Huang, Design of Liquid Propellant Rocket Engines, Fig. 8-15"
)

LSTAR_DATA: dict[str, dict[str, float]] = {
    "Nitric acid / Hydrazine-base fuel": {"min_m": 0.76, "max_m": 0.89},
    "N2O4 / Hydrazine-base fuel": {"min_m": 0.76, "max_m": 0.89},
    "H2O2 / RP-1 including catalyst bed": {"min_m": 1.52, "max_m": 1.78},
    "LOX / RP-1": {"min_m": 1.02, "max_m": 1.27},
    "LOX / Ammonia": {"min_m": 0.76, "max_m": 1.02},
    "LOX / LH2, GH2 injection": {"min_m": 0.56, "max_m": 0.71},
    "LOX / LH2, LH2 injection": {"min_m": 0.76, "max_m": 1.02},
    "F2 / LH2, GH2 injection": {"min_m": 0.56, "max_m": 0.66},
    "F2 / LH2, LH2 injection": {"min_m": 0.64, "max_m": 0.76},
    "F2 / Hydrazine": {"min_m": 0.61, "max_m": 0.71},
    "ClF3 / Hydrazine-base fuel": {"min_m": 0.51, "max_m": 0.89},
}

DEFAULT_LSTAR_PROPELLANT = "LOX / RP-1"
UNIVERSAL_GAS_CONSTANT_J_PER_MOL_K = 8.31446261815324


class LStarSelectionMode(str, Enum):
    """Selectable empirical L* choice inside the chamber-sizing helper."""

    MIN = "min"
    NOMINAL = "nominal"
    MAX = "max"
    CUSTOM = "custom"


class ChamberGeometryModel(str, Enum):
    """Conceptual chamber-shape options shown in the chamber-sizing helper."""

    CYLINDRICAL = "cylindrical"
    NEAR_SPHERICAL_CONVERGENT = "near-spherical-convergent"
    SPHERICAL = "spherical"


@dataclass(slots=True)
class ChamberGeometryInputs:
    """Inputs used by the empirical chamber-sizing helper."""

    propellant_name: str
    throat_diameter_m: float
    contraction_ratio: float
    convergent_half_angle_deg: float
    lstar_mode: LStarSelectionMode
    custom_lstar_m: float | None = None
    chamber_model: ChamberGeometryModel = ChamberGeometryModel.CYLINDRICAL
    corner_radius_m: float = 0.0


@dataclass(slots=True)
class ChamberGeometryResult:
    """Calculated preliminary chamber geometry derived from L* and throat size."""

    propellant_name: str
    lstar_min_m: float
    lstar_max_m: float
    selected_lstar_m: float
    throat_area_m2: float
    chamber_area_m2: float
    throat_diameter_m: float
    chamber_diameter_m: float
    contraction_ratio: float
    convergent_half_angle_deg: float
    corner_radius_m: float
    required_chamber_volume_m3: float
    cylindrical_section_length_m: float
    convergent_section_length_m: float
    rounded_corner_arc_length_m: float
    remaining_straight_cone_length_m: float
    total_chamber_length_to_throat_m: float
    hot_gas_wall_area_m2: float
    warnings: list[str]


@dataclass(slots=True)
class WorkingChamberGeometryState:
    """Stored sandbox state for chamber exploration before anything is committed."""

    inputs: ChamberGeometryInputs
    lstar_justification: str = ""
    contraction_ratio_justification: str = ""


@dataclass(slots=True)
class StoredChamberGeometryCalculation:
    """Last explicitly applied chamber calculation in the geometry sandbox."""

    working_state: WorkingChamberGeometryState
    result: ChamberGeometryResult
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ChamberVolumeGuidance:
    """Approximate Dc/Dt and epsilon_c band inferred from NASA SP-125 figure 8-15."""

    volume_m3: float
    dc_dt_min: float
    dc_dt_max: float
    contraction_ratio_min: float
    contraction_ratio_max: float
    clamped_to_data_range: bool = False


@dataclass(slots=True)
class ResidenceTimeEstimate:
    """Residence-time based c* and efficiency guidance for the current chamber result."""

    chamber_density_kg_per_m3: float | None
    chamber_density_source: str
    resident_gas_mass_kg: float | None
    gas_residence_time_s: float | None
    gamma_temporal_mean: float | None
    gamma_source: str
    cstar_residence_m_s: float | None
    cstar_theoretical_m_s: float | None
    eta_v: float | None
    eta_c: float | None


def list_lstar_propellants() -> list[str]:
    """Return the propellant combinations in display order."""

    return list(LSTAR_DATA)


def suggest_lstar_propellant(oxidizer: str, fuel: str) -> str | None:
    """Best-effort mapping from the current engine inputs to the empirical L* table."""

    oxidizer_key = _normalize_propellant_name(oxidizer)
    fuel_key = _normalize_propellant_name(fuel)

    if oxidizer_key in {"lox", "liquidoxygen", "o2"}:
        if fuel_key in {"rp1", "kerosene"}:
            return "LOX / RP-1"
        if fuel_key in {"ammonia", "nh3"}:
            return "LOX / Ammonia"
        if fuel_key in {"lh2", "liquidhydrogen", "h2", "gh2"}:
            if "gh2" in fuel.lower():
                return "LOX / LH2, GH2 injection"
            return "LOX / LH2, LH2 injection"
    if oxidizer_key in {"h2o2", "hydrogenperoxide"} and fuel_key in {"rp1", "kerosene"}:
        return "H2O2 / RP-1 including catalyst bed"
    if oxidizer_key in {"n2o4"} and fuel_key in {"hydrazine", "mmh", "udmh"}:
        return "N2O4 / Hydrazine-base fuel"
    if oxidizer_key in {"nitricacid", "hno3"} and fuel_key in {"hydrazine", "mmh", "udmh"}:
        return "Nitric acid / Hydrazine-base fuel"
    if oxidizer_key in {"f2", "fluorine"} and fuel_key in {"lh2", "liquidhydrogen", "h2", "gh2"}:
        if "gh2" in fuel.lower():
            return "F2 / LH2, GH2 injection"
        return "F2 / LH2, LH2 injection"
    if oxidizer_key in {"f2", "fluorine"} and fuel_key in {"hydrazine", "mmh", "udmh"}:
        return "F2 / Hydrazine"
    if oxidizer_key in {"clf3"} and fuel_key in {"hydrazine", "mmh", "udmh"}:
        return "ClF3 / Hydrazine-base fuel"
    return None


def get_lstar_range(propellant_name: str) -> tuple[float, float]:
    """Return the empirical minimum and maximum L* for the selected propellant."""

    entry = LSTAR_DATA.get(propellant_name)
    if entry is None:
        raise ValueError(f"Unknown propellant combination for chamber sizing: {propellant_name!r}.")
    return entry["min_m"], entry["max_m"]


def select_lstar_value(
    propellant_name: str,
    mode: LStarSelectionMode,
    custom_lstar_m: float | None = None,
) -> float:
    """Resolve the selected L* value from the empirical range and UI mode."""

    min_m, max_m = get_lstar_range(propellant_name)
    if mode is LStarSelectionMode.MIN:
        return min_m
    if mode is LStarSelectionMode.NOMINAL:
        return 0.5 * (min_m + max_m)
    if mode is LStarSelectionMode.MAX:
        return max_m
    if custom_lstar_m is None or not math.isfinite(custom_lstar_m) or custom_lstar_m <= 0.0:
        raise ValueError("Custom L* must be greater than 0 m.")
    return custom_lstar_m


def calculate_chamber_geometry(inputs: ChamberGeometryInputs) -> ChamberGeometryResult:
    """Calculate a first-order cylindrical chamber from empirical L* guidance."""

    if inputs.chamber_model is not ChamberGeometryModel.CYLINDRICAL:
        raise ValueError(
            "Only the cylindrical chamber model is implemented in this MVP. "
            "Near-spherical and spherical chambers are prepared for later work."
        )

    if not math.isfinite(inputs.throat_diameter_m) or inputs.throat_diameter_m <= 0.0:
        raise ValueError("Throat diameter Dt must be greater than 0 m.")
    if not math.isfinite(inputs.contraction_ratio) or inputs.contraction_ratio <= 1.0:
        raise ValueError("Chamber contraction ratio epsilon_c must be greater than 1.")
    if (
        not math.isfinite(inputs.convergent_half_angle_deg)
        or inputs.convergent_half_angle_deg <= 0.0
        or inputs.convergent_half_angle_deg >= 90.0
    ):
        raise ValueError("Convergent half angle theta must stay between 0 and 90 deg.")
    if not math.isfinite(inputs.corner_radius_m) or inputs.corner_radius_m < 0.0:
        raise ValueError("Rounded-corner radius must be finite and at least 0 m.")

    theta_rad = math.radians(inputs.convergent_half_angle_deg)
    tan_theta = math.tan(theta_rad)
    sin_theta = math.sin(theta_rad)
    cos_theta = math.cos(theta_rad)
    if abs(tan_theta) < 1.0e-12 or abs(sin_theta) < 1.0e-12:
        raise ValueError("Convergent half angle is too close to 0 deg for chamber sizing.")

    lstar_min_m, lstar_max_m = get_lstar_range(inputs.propellant_name)
    selected_lstar_m = select_lstar_value(
        inputs.propellant_name,
        inputs.lstar_mode,
        custom_lstar_m=inputs.custom_lstar_m,
    )

    throat_area_m2 = (math.pi / 4.0) * inputs.throat_diameter_m**2
    chamber_area_m2 = inputs.contraction_ratio * throat_area_m2
    chamber_diameter_m = math.sqrt((4.0 * chamber_area_m2) / math.pi)
    chamber_radius_m = 0.5 * chamber_diameter_m
    throat_radius_m = 0.5 * inputs.throat_diameter_m
    required_chamber_volume_m3 = selected_lstar_m * throat_area_m2

    convergent_volume_term = (
        (1.0 / 3.0)
        * math.sqrt(throat_area_m2 / math.pi)
        * (1.0 / tan_theta)
        * (inputs.contraction_ratio**1.5 - 1.0)
    )
    cylindrical_section_length_m = (
        required_chamber_volume_m3 / throat_area_m2 - convergent_volume_term
    ) / inputs.contraction_ratio

    sharp_convergent_axial_length_m = (
        chamber_diameter_m - inputs.throat_diameter_m
    ) / (2.0 * tan_theta)

    tangency_distance_m = inputs.corner_radius_m * math.tan(0.5 * theta_rad)
    rounded_corner_arc_length_m = inputs.corner_radius_m * theta_rad
    radius_at_cone_tangent_m = chamber_radius_m - inputs.corner_radius_m * (1.0 - cos_theta)
    remaining_straight_cone_length_raw_m = (
        radius_at_cone_tangent_m - throat_radius_m
    ) / sin_theta
    remaining_straight_cone_length_m = max(remaining_straight_cone_length_raw_m, 0.0)
    rounded_corner_axial_length_m = inputs.corner_radius_m * sin_theta
    convergent_section_length_m = rounded_corner_axial_length_m + remaining_straight_cone_length_m * cos_theta
    total_chamber_length_to_throat_m = cylindrical_section_length_m + convergent_section_length_m

    cylindrical_surface_area_m2 = 2.0 * math.pi * chamber_radius_m * cylindrical_section_length_m
    if inputs.corner_radius_m > 0.0:
        rounded_corner_surface_area_m2 = (
            2.0
            * math.pi
            * inputs.corner_radius_m
            * ((chamber_radius_m - inputs.corner_radius_m) * theta_rad + inputs.corner_radius_m * sin_theta)
        )
    else:
        rounded_corner_surface_area_m2 = 0.0
    straight_cone_surface_area_m2 = (
        math.pi * (radius_at_cone_tangent_m + throat_radius_m) * remaining_straight_cone_length_m
    )
    hot_gas_wall_area_m2 = (
        cylindrical_surface_area_m2 + rounded_corner_surface_area_m2 + straight_cone_surface_area_m2
    )

    warnings: list[str] = []
    if cylindrical_section_length_m <= 0.0:
        warnings.append(
            "Invalid geometry: selected L*, contraction ratio or convergent angle leads to non-positive cylindrical chamber length."
        )
    if radius_at_cone_tangent_m <= throat_radius_m or remaining_straight_cone_length_raw_m <= 0.0:
        warnings.append(
            "Rounded corner is too large for the current chamber/throat geometry, so the remaining straight convergent cone collapses."
        )
    if inputs.contraction_ratio < 1.5:
        warnings.append(
            "Low contraction ratio: may require longer chamber and can increase injector/chamber coupling sensitivity."
        )
    if inputs.contraction_ratio > 5.0:
        warnings.append(
            "High contraction ratio: check chamber diameter, wall thickness, cooling demand and mass impact."
        )
    if inputs.convergent_half_angle_deg < 20.0 or inputs.convergent_half_angle_deg > 45.0:
        warnings.append(
            "Convergent angle outside typical preliminary range. Check manufacturability and flow behavior."
        )
    if math.sqrt(inputs.contraction_ratio) > 5.0:
        warnings.append(
            "Dc/Dt exceeds 5. Check whether the chamber diameter stays practical for packaging, cooling and mass."
        )

    return ChamberGeometryResult(
        propellant_name=inputs.propellant_name,
        lstar_min_m=lstar_min_m,
        lstar_max_m=lstar_max_m,
        selected_lstar_m=selected_lstar_m,
        throat_area_m2=throat_area_m2,
        chamber_area_m2=chamber_area_m2,
        throat_diameter_m=inputs.throat_diameter_m,
        chamber_diameter_m=chamber_diameter_m,
        contraction_ratio=inputs.contraction_ratio,
        convergent_half_angle_deg=inputs.convergent_half_angle_deg,
        corner_radius_m=inputs.corner_radius_m,
        required_chamber_volume_m3=required_chamber_volume_m3,
        cylindrical_section_length_m=cylindrical_section_length_m,
        convergent_section_length_m=convergent_section_length_m,
        rounded_corner_arc_length_m=rounded_corner_arc_length_m,
        remaining_straight_cone_length_m=remaining_straight_cone_length_m,
        total_chamber_length_to_throat_m=total_chamber_length_to_throat_m,
        hot_gas_wall_area_m2=hot_gas_wall_area_m2,
        warnings=warnings,
    )


def infer_lstar_mode(propellant_name: str, characteristic_length_m: float | None) -> tuple[LStarSelectionMode, float | None]:
    """Infer a useful UI L* mode from a current characteristic-length input."""

    if characteristic_length_m is None:
        return LStarSelectionMode.NOMINAL, None

    min_m, max_m = get_lstar_range(propellant_name)
    nominal_m = 0.5 * (min_m + max_m)
    if math.isclose(characteristic_length_m, min_m, rel_tol=0.0, abs_tol=1.0e-6):
        return LStarSelectionMode.MIN, characteristic_length_m
    if math.isclose(characteristic_length_m, nominal_m, rel_tol=0.0, abs_tol=1.0e-6):
        return LStarSelectionMode.NOMINAL, characteristic_length_m
    if math.isclose(characteristic_length_m, max_m, rel_tol=0.0, abs_tol=1.0e-6):
        return LStarSelectionMode.MAX, characteristic_length_m
    return LStarSelectionMode.CUSTOM, characteristic_length_m


FIGURE_8_15_BAND_POINTS: tuple[tuple[float, float, float], ...] = (
    (3.0e-4, 3.30, 3.48),
    (1.0e-3, 2.70, 3.15),
    (3.0e-3, 2.20, 2.60),
    (1.0e-2, 1.75, 2.10),
    (3.0e-2, 1.42, 1.75),
    (1.0e-1, 1.20, 1.48),
    (3.0e-1, 1.08, 1.34),
)


def estimate_contraction_ratio_guidance(volume_m3: float) -> ChamberVolumeGuidance:
    """Estimate a typical Dc/Dt and epsilon_c band from the scanned NASA SP-125 figure 8-15.

    The band is a rough log-scale interpolation of anchor points digitized from the
    published scatter band. It is suitable as preliminary design guidance only.
    """

    if not math.isfinite(volume_m3) or volume_m3 <= 0.0:
        raise ValueError("Chamber volume guidance requires a positive volume.")

    first_volume = FIGURE_8_15_BAND_POINTS[0][0]
    last_volume = FIGURE_8_15_BAND_POINTS[-1][0]
    clamped = False
    if volume_m3 < first_volume:
        volume_m3 = first_volume
        clamped = True
    elif volume_m3 > last_volume:
        volume_m3 = last_volume
        clamped = True

    dc_dt_min = _log_interp_band_component(volume_m3, component_index=1)
    dc_dt_max = _log_interp_band_component(volume_m3, component_index=2)
    return ChamberVolumeGuidance(
        volume_m3=volume_m3,
        dc_dt_min=dc_dt_min,
        dc_dt_max=dc_dt_max,
        contraction_ratio_min=dc_dt_min**2,
        contraction_ratio_max=dc_dt_max**2,
        clamped_to_data_range=clamped,
    )


def calculate_temporal_average_gamma(
    profile: list[ThermochemistryProfilePoint],
    *,
    fallback_gamma: float | None = None,
) -> tuple[float | None, str]:
    """Estimate a temporal mean gamma from injector-side chamber points to the throat.

    The weighting is based on local travel time between consecutive profile points.
    If the current profile does not carry enough transport information, the chamber
    gamma from the thermochemistry bundle is used as a robust fallback.
    """

    injector_to_throat = _injector_to_throat_profile(profile)
    if len(injector_to_throat) >= 2:
        weighted_gamma = 0.0
        total_time = 0.0
        for start, end in zip(injector_to_throat, injector_to_throat[1:]):
            mean_gamma = _mean_available(start.state.gamma, end.state.gamma)
            mean_velocity = _mean_available(start.state.velocity_m_per_s, end.state.velocity_m_per_s)
            if mean_gamma is None or mean_velocity is None or mean_velocity <= 0.0:
                continue
            segment_length_m = math.hypot(end.x_m - start.x_m, end.radius_m - start.radius_m)
            if segment_length_m <= 0.0:
                continue
            segment_time_s = segment_length_m / mean_velocity
            weighted_gamma += mean_gamma * segment_time_s
            total_time += segment_time_s
        if total_time > 0.0:
            return weighted_gamma / total_time, "temporal mean injector-to-throat"

    if fallback_gamma is not None and math.isfinite(fallback_gamma) and fallback_gamma > 0.0:
        return fallback_gamma, "chamber gamma fallback"

    return None, "gamma unavailable"


def estimate_residence_time_metrics(
    bundle: ExportBundle,
    *,
    chamber_volume_m3: float | None,
    lstar_m: float | None,
) -> ResidenceTimeEstimate:
    """Estimate residence-time-based c* and associated preliminary efficiencies."""

    chamber_density_kg_per_m3, chamber_density_source = _estimate_chamber_density(bundle)
    resident_gas_mass_kg: float | None = None
    gas_residence_time_s: float | None = None
    mass_flow_kg_per_s = bundle.geometry.mass_flow_kg_per_s
    if (
        chamber_density_kg_per_m3 is not None
        and chamber_volume_m3 is not None
        and math.isfinite(chamber_volume_m3)
        and chamber_volume_m3 > 0.0
    ):
        resident_gas_mass_kg = chamber_density_kg_per_m3 * chamber_volume_m3
    if (
        resident_gas_mass_kg is not None
        and math.isfinite(mass_flow_kg_per_s)
        and mass_flow_kg_per_s > 0.0
    ):
        gas_residence_time_s = resident_gas_mass_kg / mass_flow_kg_per_s
    gamma_temporal_mean, gamma_source = calculate_temporal_average_gamma(
        bundle.thermochemistry_profile,
        fallback_gamma=bundle.thermochemistry.gamma,
    )

    cstar_residence_m_s: float | None = None
    if (
        gas_residence_time_s is not None
        and gas_residence_time_s > 0.0
        and lstar_m is not None
        and math.isfinite(lstar_m)
        and lstar_m > 0.0
        and gamma_temporal_mean is not None
        and gamma_temporal_mean > 0.0
    ):
        cstar_residence_m_s = lstar_m / (gamma_temporal_mean**2 * gas_residence_time_s)

    cstar_theoretical_m_s = bundle.thermochemistry.c_star_m_s
    if not math.isfinite(cstar_theoretical_m_s) or cstar_theoretical_m_s <= 0.0:
        cstar_theoretical_m_s = None

    eta_v: float | None = None
    eta_c: float | None = None
    if (
        cstar_residence_m_s is not None
        and cstar_theoretical_m_s is not None
        and cstar_theoretical_m_s > 0.0
    ):
        eta_v = cstar_residence_m_s / cstar_theoretical_m_s
        if eta_v >= 0.0:
            eta_c = math.sqrt(eta_v)

    return ResidenceTimeEstimate(
        chamber_density_kg_per_m3=chamber_density_kg_per_m3,
        chamber_density_source=chamber_density_source,
        resident_gas_mass_kg=resident_gas_mass_kg,
        gas_residence_time_s=gas_residence_time_s,
        gamma_temporal_mean=gamma_temporal_mean,
        gamma_source=gamma_source,
        cstar_residence_m_s=cstar_residence_m_s,
        cstar_theoretical_m_s=cstar_theoretical_m_s,
        eta_v=eta_v,
        eta_c=eta_c,
    )


def _normalize_propellant_name(name: str) -> str:
    cleaned = "".join(character for character in name.lower() if character.isalnum())
    return cleaned


def validate_chamber_justifications(
    inputs: ChamberGeometryInputs,
    *,
    lstar_justification: str,
    contraction_ratio_justification: str,
) -> list[str]:
    """Return justification errors for the current chamber-sandbox inputs."""

    errors: list[str] = []
    if not lstar_justification.strip():
        errors.append("Justification for Selected L* is required.")
    if not contraction_ratio_justification.strip():
        errors.append("Justification for Contraction Ratio epsilon_c is required.")
    return errors


def _estimate_chamber_density(bundle: ExportBundle) -> tuple[float | None, str]:
    chamber_pressure_pa = bundle.inputs.chamber_pressure_pa
    chamber_temperature_k = bundle.thermochemistry.chamber_temperature_k
    molecular_weight_kg_per_mol = bundle.thermochemistry.molecular_weight_kg_per_mol
    if (
        math.isfinite(chamber_pressure_pa)
        and chamber_pressure_pa > 0.0
        and math.isfinite(chamber_temperature_k)
        and chamber_temperature_k > 0.0
        and molecular_weight_kg_per_mol is not None
        and math.isfinite(molecular_weight_kg_per_mol)
        and molecular_weight_kg_per_mol > 0.0
    ):
        return (
            chamber_pressure_pa * molecular_weight_kg_per_mol
            / (UNIVERSAL_GAS_CONSTANT_J_PER_MOL_K * chamber_temperature_k),
            "ideal-gas estimate",
        )

    chamber_density_kg_per_m3 = bundle.thermochemistry.chamber_density_kg_per_m3
    if (
        chamber_density_kg_per_m3 is None
        or not math.isfinite(chamber_density_kg_per_m3)
        or chamber_density_kg_per_m3 <= 0.0
    ):
        return None, "density unavailable"
    return chamber_density_kg_per_m3, "thermochemistry fallback"


def _injector_to_throat_profile(
    profile: list[ThermochemistryProfilePoint],
) -> list[ThermochemistryProfilePoint]:
    collected: list[ThermochemistryProfilePoint] = []
    for point in profile:
        collected.append(point)
        if point.region == "throat":
            break
        if point.region == "diverging":
            break
    return collected


def _mean_available(first: float | None, second: float | None) -> float | None:
    values = [
        value
        for value in (first, second)
        if value is not None and math.isfinite(value)
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _log_interp_band_component(volume_m3: float, *, component_index: int) -> float:
    log_volume = math.log10(volume_m3)
    for left, right in zip(FIGURE_8_15_BAND_POINTS, FIGURE_8_15_BAND_POINTS[1:]):
        left_volume = left[0]
        right_volume = right[0]
        if left_volume <= volume_m3 <= right_volume:
            left_log = math.log10(left_volume)
            right_log = math.log10(right_volume)
            blend = 0.0 if math.isclose(left_log, right_log) else (log_volume - left_log) / (right_log - left_log)
            return left[component_index] + blend * (right[component_index] - left[component_index])
    if math.isclose(volume_m3, FIGURE_8_15_BAND_POINTS[0][0]):
        return FIGURE_8_15_BAND_POINTS[0][component_index]
    return FIGURE_8_15_BAND_POINTS[-1][component_index]

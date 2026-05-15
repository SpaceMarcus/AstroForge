"""Station-wise annulus cooling reference model for AstraForge.

This module intentionally keeps the MVP cooling logic separate from the GUI.
The current implementation is a predesign-level annulus reference model, not a
full regenerative channel solver. It reuses the committed Current Design
geometry and thermochemistry data and adds only the cooling-side assumptions
that are specific to the thermal analysis workflow.

The coolant-side correlations currently assume fully developed annular flow.
That is a conservative predesign choice for wall heat transfer because real
entry regions often show stronger local mixing and therefore higher local
coolant-side heat-transfer coefficients than the fully developed baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math

from engine.models import ExportBundle, NozzlePoint, ThermochemistryProfilePoint
from engine.utils.validation import InputValidationError

_DEFAULT_GAS_SIDE_HTC_W_PER_M2_K = 2_500.0
_DEFAULT_STATION_TOLERANCE = 1.0e-5
_DEFAULT_MAX_ITERATIONS = 25
_DEFAULT_RELAXATION_FACTOR = 0.6
_DEFAULT_ANNULUS_GAP_M = 1.5e-3
_DEFAULT_ROUGHNESS_M = 15.0e-6
_DEFAULT_COOLANT_INLET_TEMPERATURE_K = 293.15
_ANNULAR_TURBULENT_RE_MIN = 1_664.0


class CoolingFlowDirection(str, Enum):
    """Allowed coolant marching directions for the MVP annulus reference model."""

    NOZZLE_TO_INJECTOR = "nozzle-to-injector"
    INJECTOR_TO_NOZZLE = "injector-to-nozzle"


class ThermalModelType(str, Enum):
    """Cooling-model families exposed in the thermal-analysis UI."""

    ANNULUS = "annulus"
    ANNULUS_WITH_FILM_FUTURE = "annulus-with-film-future"
    CHANNELS_FUTURE = "channels-future"
    CHANNELS_WITH_FILM_FUTURE = "channels-with-film-future"


class ThermalSolverType(str, Enum):
    """Station update schemes exposed in the thermal-analysis UI."""

    FORWARD_EULER = "forward-euler"
    BACKWARD_EULER = "backward-euler"
    CRANK_NICOLSON = "crank-nicolson"
    NTU_EXPONENTIAL = "ntu-exponential"


class StationDistributionMode(str, Enum):
    """How the station list is generated for the cooling calculation."""

    MANUAL = "manual"
    CEA_PROFILE = "cea-profile"


class PressureCalculationMode(str, Enum):
    """Pressure post-processing modes for the thermal-analysis MVP."""

    BACKWARD_REQUIRED_PUMP = "backward-required-pump"
    FORWARD_PUMP_CHECK = "forward-pump-check"


@dataclass(slots=True)
class SolverSettings:
    """Numerical settings for the station-wise cooling calculation."""

    solver_type: ThermalSolverType = ThermalSolverType.NTU_EXPONENTIAL
    station_distribution_mode: StationDistributionMode = StationDistributionMode.MANUAL
    pressure_mode: PressureCalculationMode = PressureCalculationMode.BACKWARD_REQUIRED_PUMP
    station_count: int = 32
    station_tolerance: float = _DEFAULT_STATION_TOLERANCE
    max_iterations_per_station: int = _DEFAULT_MAX_ITERATIONS
    relaxation_factor: float = _DEFAULT_RELAXATION_FACTOR


@dataclass(slots=True)
class ThermalAnalysisInputs:
    """Cooling-side assumptions that are specific to the thermal-analysis page."""

    coolant_mass_flow_kg_per_s: float | None = None
    coolant_type: str = "RP-1"
    model_type: ThermalModelType = ThermalModelType.ANNULUS
    coolant_inlet_temperature_k: float = 293.15
    annulus_gap_m: float = _DEFAULT_ANNULUS_GAP_M
    coolant_roughness_m: float = _DEFAULT_ROUGHNESS_M
    injector_pressure_drop_pa: float = 5.0e5
    pressure_margin_pa: float = 2.0e5
    external_feed_pressure_drop_pa: float = 1.0e5
    pump_discharge_pressure_pa: float | None = None
    flow_direction: CoolingFlowDirection = CoolingFlowDirection.NOZZLE_TO_INJECTOR
    solver_settings: SolverSettings = field(default_factory=SolverSettings)


@dataclass(slots=True)
class AnnulusCoolingGeometry:
    """Local annulus geometry derived from the committed inner contour."""

    r_inner_m: float
    r_outer_m: float
    r_mean_m: float
    area_annulus_m2: float
    wetted_perimeter_m: float
    hydraulic_diameter_m: float
    hot_wall_area_m2: float


@dataclass(slots=True)
class ThermalStationResult:
    """One station row shown in the thermal-analysis output table."""

    station_index: int
    x_start_m: float
    x_end_m: float
    x_mid_m: float
    r_inner_m: float
    r_outer_m: float
    r_mean_m: float
    area_gas_m2: float
    area_hot_m2: float
    area_annulus_m2: float
    hydraulic_diameter_m: float
    recovery_temperature_k: float | None
    h_g_w_per_m2_k: float | None
    h_c_w_per_m2_k: float | None
    q_station_w: float | None
    q_hot_w_per_m2: float | None
    coolant_temperature_in_k: float | None
    coolant_temperature_bulk_k: float | None
    coolant_temperature_out_k: float | None
    wall_temperature_hot_gas_side_k: float | None
    wall_temperature_coolant_side_k: float | None
    wall_delta_t_k: float | None
    required_pressure_out_pa: float | None
    required_pressure_in_pa: float | None
    pressure_drop_station_pa: float | None
    reynolds_coolant: float | None
    nusselt_coolant: float | None
    friction_factor: float | None
    thermal_margin_k: float | None
    status: str = ""


@dataclass(slots=True)
class ThermalAnalysisSummary:
    """Compact headline values shown above the station table."""

    max_wall_temperature_hot_gas_side_k: float | None
    max_wall_temperature_coolant_side_k: float | None
    coolant_outlet_temperature_k: float | None
    total_heat_into_coolant_w: float | None
    total_coolant_pressure_drop_pa: float | None
    required_cooling_inlet_pressure_pa: float | None
    required_pump_discharge_pressure_pa: float | None
    injector_pressure_drop_pa: float | None
    external_feed_pressure_drop_pa: float | None
    pressure_margin_pa: float | None
    minimum_thermal_margin_k: float | None
    propellant_enthalpy_gain_j_per_kg: float | None
    estimated_isp_gain_s: float | None
    estimated_isp_gain_note: str
    pressure_mode_note: str


@dataclass(slots=True)
class ThermalAnalysisResult:
    """Full result bundle for the Thermal Analysis page."""

    inputs: ThermalAnalysisInputs
    summary: ThermalAnalysisSummary
    stations: list[ThermalStationResult]
    method: str = "Annulus-cooling MVP reference model"
    spacer_ribs_note: str = (
        "3 spacer ribs are treated as a mechanical support assumption only and are excluded from the MVP annulus calculation."
    )
    generated_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class _CoolantProperties:
    density_kg_per_m3: float
    cp_j_per_kg_k: float
    viscosity_pa_s: float
    thermal_conductivity_w_per_m_k: float


@dataclass(slots=True)
class _SamplePoint:
    x_start_m: float
    x_end_m: float
    x_m: float
    radius_m: float
    area_m2: float
    ds_m: float
    profile_point: ThermochemistryProfilePoint | None


def default_thermal_analysis_inputs(
    bundle: ExportBundle | None = None,
    *,
    fuel_name: str | None = None,
) -> ThermalAnalysisInputs:
    """Create a conservative default thermal-analysis state.

    The current MVP assumes that the fuel stream is the default regenerative
    coolant candidate. If a committed design result is available, the default
    coolant mass flow is seeded from the derived fuel mass flow so the page can
    be used immediately without silently inventing a new total-flow basis.
    """

    coolant_type = fuel_name or "RP-1"
    coolant_mass_flow = _default_coolant_mass_flow_kg_per_s(bundle)
    return ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=coolant_mass_flow,
        coolant_type=coolant_type,
        coolant_inlet_temperature_k=_default_coolant_inlet_temperature_k(coolant_type),
        injector_pressure_drop_pa=_default_injector_pressure_drop_pa(bundle),
        pressure_margin_pa=_default_pressure_margin_pa(bundle),
        external_feed_pressure_drop_pa=_default_external_feed_pressure_drop_pa(bundle),
    )


def run_thermal_analysis(
    bundle: ExportBundle,
    thermal_inputs: ThermalAnalysisInputs,
) -> ThermalAnalysisResult:
    """Run the station-wise annulus cooling reference model.

    The solver marches along the selected coolant direction and evaluates one
    local energy/momentum balance per station. The current implementation is
    intentionally simple and reusable: it avoids channel-specific geometry so it
    can later serve as a baseline comparison for detailed regenerative cooling.
    """

    _ensure_valid_thermal_inputs(bundle, thermal_inputs)

    station_samples = _build_station_samples(bundle, thermal_inputs.solver_settings)
    if thermal_inputs.flow_direction is CoolingFlowDirection.NOZZLE_TO_INJECTOR:
        station_samples = list(reversed(station_samples))

    wall_conductivity = _wall_material_conductivity_w_per_m_k(bundle.inputs.liner_material)
    wall_temperature_limit_k = _wall_material_limit_k(bundle.inputs.liner_material)
    wall_thickness_m = _resolved_wall_thickness_m(bundle)
    coolant_state = _coolant_properties(thermal_inputs.coolant_type)

    coolant_mass_flow = thermal_inputs.coolant_mass_flow_kg_per_s or 0.0
    coolant_temperature_in_k = thermal_inputs.coolant_inlet_temperature_k
    station_results: list[ThermalStationResult] = []

    for station_index, sample in enumerate(station_samples):
        station_geometry = _build_annulus_geometry(sample, thermal_inputs.annulus_gap_m)
        recovery_temperature_k, gas_temperature_source = _recovery_temperature(sample.profile_point)
        h_g_w_per_m2_k, h_g_source = _gas_side_heat_transfer_coefficient(sample.profile_point)

        hydraulic_diameter = station_geometry.hydraulic_diameter_m
        area_annulus = station_geometry.area_annulus_m2
        coolant_velocity_m_per_s = coolant_mass_flow / max(coolant_state.density_kg_per_m3 * area_annulus, 1.0e-12)
        reynolds_coolant = (
            coolant_state.density_kg_per_m3 * coolant_velocity_m_per_s * hydraulic_diameter
            / max(coolant_state.viscosity_pa_s, 1.0e-12)
        )
        prandtl_coolant = _coolant_prandtl_number(coolant_state)
        regime_label = _coolant_regime_label(reynolds_coolant)
        nusselt_coolant = _coolant_nusselt_number(reynolds_coolant, prandtl_coolant)
        h_c_w_per_m2_k = nusselt_coolant * coolant_state.thermal_conductivity_w_per_m_k / max(hydraulic_diameter, 1.0e-12)

        overall_heat_transfer = _overall_heat_transfer_w_per_m2_k(
            h_g_w_per_m2_k,
            h_c_w_per_m2_k,
            wall_thickness_m,
            wall_conductivity,
        )
        coolant_temperature_out_k = _solve_station_temperature_outlet(
            recovery_temperature_k,
            coolant_temperature_in_k,
            overall_heat_transfer,
            station_geometry.hot_wall_area_m2,
            coolant_mass_flow,
            coolant_state.cp_j_per_kg_k,
            thermal_inputs.solver_settings,
        )
        coolant_temperature_bulk_k = 0.5 * (coolant_temperature_in_k + coolant_temperature_out_k)
        q_station_w = coolant_mass_flow * coolant_state.cp_j_per_kg_k * (
            coolant_temperature_out_k - coolant_temperature_in_k
        )
        q_hot_w_per_m2 = q_station_w / max(station_geometry.hot_wall_area_m2, 1.0e-12)
        wall_temperature_coolant_side_k = coolant_temperature_bulk_k + q_hot_w_per_m2 / max(h_c_w_per_m2_k, 1.0e-12)
        wall_temperature_hot_gas_side_k = wall_temperature_coolant_side_k + q_hot_w_per_m2 * wall_thickness_m / max(wall_conductivity, 1.0e-12)
        wall_delta_t_k = wall_temperature_hot_gas_side_k - wall_temperature_coolant_side_k

        friction_factor = _friction_factor(
            reynolds_coolant,
            thermal_inputs.coolant_roughness_m,
            hydraulic_diameter,
        )
        pressure_drop_station_pa = friction_factor * (
            sample.ds_m / max(hydraulic_diameter, 1.0e-12)
        ) * 0.5 * coolant_state.density_kg_per_m3 * coolant_velocity_m_per_s**2
        thermal_margin_k = wall_temperature_limit_k - wall_temperature_hot_gas_side_k
        status_messages: list[str] = []
        if gas_temperature_source != "adiabatic-wall":
            status_messages.append("gas-side recovery placeholder")
        if h_g_source != "boundary-layer":
            status_messages.append("gas-side h_g placeholder")
        if thermal_margin_k < 0.0:
            status_messages.append("wall temperature above material limit")
        status_messages.append(f"coolant regime: {regime_label}")

        station_results.append(
            ThermalStationResult(
                station_index=station_index,
                x_start_m=sample.x_start_m,
                x_end_m=sample.x_end_m,
                x_mid_m=sample.x_m,
                r_inner_m=station_geometry.r_inner_m,
                r_outer_m=station_geometry.r_outer_m,
                r_mean_m=station_geometry.r_mean_m,
                area_gas_m2=sample.area_m2,
                area_hot_m2=station_geometry.hot_wall_area_m2,
                area_annulus_m2=station_geometry.area_annulus_m2,
                hydraulic_diameter_m=station_geometry.hydraulic_diameter_m,
                recovery_temperature_k=recovery_temperature_k,
                h_g_w_per_m2_k=h_g_w_per_m2_k,
                h_c_w_per_m2_k=h_c_w_per_m2_k,
                q_station_w=q_station_w,
                q_hot_w_per_m2=q_hot_w_per_m2,
                coolant_temperature_in_k=coolant_temperature_in_k,
                coolant_temperature_bulk_k=coolant_temperature_bulk_k,
                coolant_temperature_out_k=coolant_temperature_out_k,
                wall_temperature_hot_gas_side_k=wall_temperature_hot_gas_side_k,
                wall_temperature_coolant_side_k=wall_temperature_coolant_side_k,
                wall_delta_t_k=wall_delta_t_k,
                required_pressure_out_pa=None,
                required_pressure_in_pa=None,
                pressure_drop_station_pa=pressure_drop_station_pa,
                reynolds_coolant=reynolds_coolant,
                nusselt_coolant=nusselt_coolant,
                friction_factor=friction_factor,
                thermal_margin_k=thermal_margin_k,
                status=", ".join(status_messages) if status_messages else "ok",
            )
        )

        coolant_temperature_in_k = coolant_temperature_out_k

    pressure_summary = _reconstruct_pressures(
        station_results,
        chamber_pressure_pa=bundle.inputs.chamber_pressure_pa,
        thermal_inputs=thermal_inputs,
    )
    summary = _build_summary(station_results, thermal_inputs, pressure_summary)
    return ThermalAnalysisResult(
        inputs=thermal_inputs,
        summary=summary,
        stations=station_results,
    )


def _ensure_valid_thermal_inputs(bundle: ExportBundle, thermal_inputs: ThermalAnalysisInputs) -> None:
    errors: list[str] = []
    if thermal_inputs.model_type is not ThermalModelType.ANNULUS:
        errors.append(
            "Only the annulus reference model is active in this MVP. Channels and film-cooling options are planned for a later version."
        )
    if bundle.contour is None or len(bundle.contour) < 2:
        errors.append("Current Design contour is not available. Calculate Current Design before running Thermal Analysis.")
    if thermal_inputs.coolant_mass_flow_kg_per_s is None or thermal_inputs.coolant_mass_flow_kg_per_s <= 0.0:
        errors.append("Coolant mass flow must be greater than 0 kg/s.")
    if thermal_inputs.coolant_inlet_temperature_k <= 0.0:
        errors.append("Coolant inlet temperature must be greater than 0 K.")
    if thermal_inputs.annulus_gap_m <= 0.0:
        errors.append("Annulus gap height must be greater than 0 m.")
    if thermal_inputs.coolant_roughness_m < 0.0:
        errors.append("Coolant roughness must not be negative.")
    if thermal_inputs.injector_pressure_drop_pa < 0.0:
        errors.append("Injector pressure drop must not be negative.")
    if thermal_inputs.pressure_margin_pa < 0.0:
        errors.append("Pressure margin must not be negative.")
    if thermal_inputs.external_feed_pressure_drop_pa < 0.0:
        errors.append("External feed pressure drop must not be negative.")
    if (
        thermal_inputs.solver_settings.pressure_mode is PressureCalculationMode.FORWARD_PUMP_CHECK
        and (thermal_inputs.pump_discharge_pressure_pa is None or thermal_inputs.pump_discharge_pressure_pa <= 0.0)
    ):
        errors.append("Forward pressure check requires a pump discharge pressure greater than 0 Pa.")
    if (
        thermal_inputs.solver_settings.station_distribution_mode is StationDistributionMode.MANUAL
        and thermal_inputs.solver_settings.station_count < 3
    ):
        errors.append("Number of stations must be at least 3.")
    if (
        thermal_inputs.solver_settings.station_distribution_mode is StationDistributionMode.CEA_PROFILE
        and len(bundle.thermochemistry_profile) < 2
    ):
        errors.append("CEA-profile station mode requires at least two thermochemistry profile points.")
    if thermal_inputs.solver_settings.station_tolerance <= 0.0:
        errors.append("Station tolerance must be greater than 0.")
    if thermal_inputs.solver_settings.max_iterations_per_station < 1:
        errors.append("Maximum iterations per station must be at least 1.")
    if not 0.0 < thermal_inputs.solver_settings.relaxation_factor <= 1.0:
        errors.append("Relaxation factor must be greater than 0 and at most 1.")
    if not thermal_inputs.coolant_type.strip():
        errors.append("Coolant type must not be empty.")
    if errors:
        raise InputValidationError(errors)


def _default_coolant_mass_flow_kg_per_s(bundle: ExportBundle | None) -> float | None:
    if bundle is None:
        return None
    mass_flow = bundle.geometry.mass_flow_kg_per_s
    mixture_ratio = bundle.inputs.mixture_ratio
    if mass_flow <= 0.0 or mixture_ratio < 0.0:
        return None
    return mass_flow / (1.0 + mixture_ratio)


def _default_coolant_inlet_temperature_k(coolant_type: str | None) -> float:
    coolant_key = (coolant_type or "").strip().lower()
    if coolant_key in {"ch4", "methane"}:
        return 111.0
    if coolant_key in {"lh2", "h2"}:
        return 25.0
    return _DEFAULT_COOLANT_INLET_TEMPERATURE_K


def _default_injector_pressure_drop_pa(bundle: ExportBundle | None) -> float:
    if bundle is None:
        return 5.0e5
    return max(0.15 * bundle.inputs.chamber_pressure_pa, 1.0e5)


def _default_pressure_margin_pa(bundle: ExportBundle | None) -> float:
    if bundle is None:
        return 2.0e5
    return max(0.03 * bundle.inputs.chamber_pressure_pa, 5.0e4)


def _default_external_feed_pressure_drop_pa(bundle: ExportBundle | None) -> float:
    if bundle is None:
        return 1.0e5
    return max(0.02 * bundle.inputs.chamber_pressure_pa, 5.0e4)


def _build_station_samples(bundle: ExportBundle, solver_settings: SolverSettings) -> list[_SamplePoint]:
    if solver_settings.station_distribution_mode is StationDistributionMode.CEA_PROFILE:
        return _build_station_samples_from_profile(bundle)
    return _build_station_samples_manual(bundle, solver_settings.station_count)


def _build_station_samples_manual(bundle: ExportBundle, station_count: int) -> list[_SamplePoint]:
    contour = bundle.contour
    profile = bundle.thermochemistry_profile
    cumulative_lengths = _cumulative_arc_lengths(contour)
    total_length = cumulative_lengths[-1]
    if total_length <= 0.0:
        raise InputValidationError(["Current Design contour length is invalid for thermal station generation."])

    samples: list[_SamplePoint] = []
    for index in range(station_count):
        s_start = total_length * index / station_count
        s_end = total_length * (index + 1) / station_count
        s_mid = 0.5 * (s_start + s_end)
        x_start_m, _, _ = _interpolate_contour_at_s(contour, cumulative_lengths, s_start)
        x_end_m, _, _ = _interpolate_contour_at_s(contour, cumulative_lengths, s_end)
        x_m, radius_m, area_m2 = _interpolate_contour_at_s(contour, cumulative_lengths, s_mid)
        profile_point = _nearest_profile_point(profile, contour, cumulative_lengths, s_mid)
        samples.append(
            _SamplePoint(
                x_start_m=x_start_m,
                x_end_m=x_end_m,
                x_m=x_m,
                radius_m=radius_m,
                area_m2=area_m2,
                ds_m=s_end - s_start,
                profile_point=profile_point,
            )
        )
    return samples


def _build_station_samples_from_profile(bundle: ExportBundle) -> list[_SamplePoint]:
    """Use the committed thermochemistry-profile stations as the thermal grid.

    This mode keeps the cooling table aligned with the existing CEA-derived
    thermochemistry/profile sampling rather than redistributing the contour into
    a new manual station count.
    """

    profile = bundle.thermochemistry_profile
    if len(profile) < 2:
        raise InputValidationError(["CEA-profile station mode requires at least two thermochemistry profile points."])

    samples: list[_SamplePoint] = []
    for left_point, right_point in zip(profile, profile[1:]):
        x_start_m = left_point.x_m
        x_end_m = right_point.x_m
        x_mid_m = 0.5 * (x_start_m + x_end_m)
        radius_m = 0.5 * (left_point.radius_m + right_point.radius_m)
        area_m2 = math.pi * radius_m**2
        ds_m = math.hypot(
            right_point.x_m - left_point.x_m,
            right_point.radius_m - left_point.radius_m,
        )
        samples.append(
            _SamplePoint(
                x_start_m=x_start_m,
                x_end_m=x_end_m,
                x_m=x_mid_m,
                radius_m=radius_m,
                area_m2=area_m2,
                ds_m=ds_m,
                profile_point=_average_profile_point(left_point, right_point),
            )
        )
    return samples


def _cumulative_arc_lengths(contour: list[NozzlePoint]) -> list[float]:
    cumulative = [0.0]
    for previous, current in zip(contour, contour[1:]):
        ds = math.hypot(current.x_m - previous.x_m, current.radius_m - previous.radius_m)
        cumulative.append(cumulative[-1] + ds)
    return cumulative


def _interpolate_contour_at_s(
    contour: list[NozzlePoint],
    cumulative_lengths: list[float],
    target_s: float,
) -> tuple[float, float, float]:
    if target_s <= 0.0:
        point = contour[0]
        return point.x_m, point.radius_m, point.area_m2
    if target_s >= cumulative_lengths[-1]:
        point = contour[-1]
        return point.x_m, point.radius_m, point.area_m2

    for index in range(len(cumulative_lengths) - 1):
        s0 = cumulative_lengths[index]
        s1 = cumulative_lengths[index + 1]
        if s0 <= target_s <= s1:
            p0 = contour[index]
            p1 = contour[index + 1]
            fraction = 0.0 if math.isclose(s0, s1) else (target_s - s0) / (s1 - s0)
            return (
                _lerp(p0.x_m, p1.x_m, fraction),
                _lerp(p0.radius_m, p1.radius_m, fraction),
                _lerp(p0.area_m2, p1.area_m2, fraction),
            )

    point = contour[-1]
    return point.x_m, point.radius_m, point.area_m2


def _nearest_profile_point(
    profile: list[ThermochemistryProfilePoint],
    contour: list[NozzlePoint],
    cumulative_lengths: list[float],
    target_s: float,
) -> ThermochemistryProfilePoint | None:
    if not profile or len(profile) != len(contour):
        return None

    closest_index = 0
    closest_distance = abs(cumulative_lengths[0] - target_s)
    for index, current_s in enumerate(cumulative_lengths):
        distance = abs(current_s - target_s)
        if distance < closest_distance:
            closest_distance = distance
            closest_index = index
    return profile[closest_index]


def _build_annulus_geometry(sample: _SamplePoint, annulus_gap_m: float) -> AnnulusCoolingGeometry:
    r_inner = sample.radius_m
    r_outer = r_inner + annulus_gap_m
    r_mean = 0.5 * (r_inner + r_outer)
    area_annulus = math.pi * (r_outer**2 - r_inner**2)
    wetted_perimeter = 2.0 * math.pi * (r_inner + r_outer)
    hydraulic_diameter = 4.0 * area_annulus / max(wetted_perimeter, 1.0e-12)
    hot_wall_area = 2.0 * math.pi * r_inner * sample.ds_m
    return AnnulusCoolingGeometry(
        r_inner_m=r_inner,
        r_outer_m=r_outer,
        r_mean_m=r_mean,
        area_annulus_m2=area_annulus,
        wetted_perimeter_m=wetted_perimeter,
        hydraulic_diameter_m=hydraulic_diameter,
        hot_wall_area_m2=hot_wall_area,
    )


def _recovery_temperature(profile_point: ThermochemistryProfilePoint | None) -> tuple[float, str]:
    if profile_point is None:
        return 1_200.0, "placeholder"
    state = profile_point.state
    if state.adiabatic_wall_temperature_k is not None:
        return state.adiabatic_wall_temperature_k, "adiabatic-wall"
    if state.temperature_k is not None:
        return state.temperature_k, "static-temperature"
    return 1_200.0, "placeholder"


def _gas_side_heat_transfer_coefficient(
    profile_point: ThermochemistryProfilePoint | None,
) -> tuple[float, str]:
    if profile_point is None:
        return _DEFAULT_GAS_SIDE_HTC_W_PER_M2_K, "placeholder"
    state = profile_point.state
    conductivity = state.thermal_conductivity_w_per_m_k
    thermal_boundary_layer = state.thermal_boundary_layer_thickness_m
    if (
        conductivity is not None
        and conductivity > 0.0
        and thermal_boundary_layer is not None
        and thermal_boundary_layer > 0.0
    ):
        return conductivity / thermal_boundary_layer, "boundary-layer"
    return _DEFAULT_GAS_SIDE_HTC_W_PER_M2_K, "placeholder"


def _coolant_properties(coolant_type: str) -> _CoolantProperties:
    coolant_key = coolant_type.strip().lower()
    database = {
        "rp-1": _CoolantProperties(810.0, 2_200.0, 1.8e-3, 0.13),
        "kerosene": _CoolantProperties(810.0, 2_200.0, 1.8e-3, 0.13),
        "ch4": _CoolantProperties(420.0, 3_500.0, 1.2e-4, 0.19),
        "methane": _CoolantProperties(420.0, 3_500.0, 1.2e-4, 0.19),
        "lh2": _CoolantProperties(70.0, 9_600.0, 1.3e-5, 0.10),
        "h2": _CoolantProperties(70.0, 9_600.0, 1.3e-5, 0.10),
        "water": _CoolantProperties(997.0, 4_180.0, 1.0e-3, 0.60),
    }
    return database.get(coolant_key, _CoolantProperties(810.0, 2_200.0, 1.8e-3, 0.13))


def _coolant_prandtl_number(coolant_state: _CoolantProperties) -> float:
    """Return a constant-property Prandtl number for the current coolant state."""

    return (
        coolant_state.cp_j_per_kg_k
        * coolant_state.viscosity_pa_s
        / max(coolant_state.thermal_conductivity_w_per_m_k, 1.0e-12)
    )


def _coolant_regime_label(reynolds_number: float) -> str:
    if reynolds_number < _ANNULAR_TURBULENT_RE_MIN:
        return "laminar"
    return "turbulent"


def _coolant_nusselt_number(reynolds_number: float, prandtl_number: float) -> float:
    if reynolds_number <= 0.0:
        return 0.0
    if reynolds_number < _ANNULAR_TURBULENT_RE_MIN:
        return 3.66
    return 0.023 * reynolds_number**0.8 * max(prandtl_number, 1.0e-12) ** 0.4


def _overall_heat_transfer_w_per_m2_k(
    h_g_w_per_m2_k: float,
    h_c_w_per_m2_k: float,
    wall_thickness_m: float,
    wall_conductivity_w_per_m_k: float,
) -> float:
    resistance = (
        1.0 / max(h_g_w_per_m2_k, 1.0e-12)
        + wall_thickness_m / max(wall_conductivity_w_per_m_k, 1.0e-12)
        + 1.0 / max(h_c_w_per_m2_k, 1.0e-12)
    )
    return 1.0 / max(resistance, 1.0e-12)


def _solve_station_temperature_outlet(
    recovery_temperature_k: float,
    coolant_temperature_in_k: float,
    overall_heat_transfer_w_per_m2_k: float,
    hot_wall_area_m2: float,
    coolant_mass_flow_kg_per_s: float,
    coolant_cp_j_per_kg_k: float,
    solver_settings: SolverSettings,
) -> float:
    capacity_rate = max(coolant_mass_flow_kg_per_s * coolant_cp_j_per_kg_k, 1.0e-12)
    ntu = overall_heat_transfer_w_per_m2_k * hot_wall_area_m2 / capacity_rate

    if solver_settings.solver_type is ThermalSolverType.FORWARD_EULER:
        return coolant_temperature_in_k + ntu * (recovery_temperature_k - coolant_temperature_in_k)

    if solver_settings.solver_type is ThermalSolverType.BACKWARD_EULER:
        return (
            coolant_temperature_in_k + ntu * recovery_temperature_k
        ) / max(1.0 + ntu, 1.0e-12)

    if solver_settings.solver_type is ThermalSolverType.CRANK_NICOLSON:
        numerator = coolant_temperature_in_k + ntu * (recovery_temperature_k - 0.5 * coolant_temperature_in_k)
        denominator = max(1.0 + 0.5 * ntu, 1.0e-12)
        return numerator / denominator

    # The NTU / exponential station model is the default because it gives a
    # compact closed-form station update without implying full transient fidelity.
    return recovery_temperature_k - (recovery_temperature_k - coolant_temperature_in_k) * math.exp(-ntu)


def _friction_factor(reynolds_number: float, roughness_m: float, hydraulic_diameter_m: float) -> float:
    if reynolds_number <= 0.0:
        return 0.0
    if reynolds_number < _ANNULAR_TURBULENT_RE_MIN:
        return 64.0 / reynolds_number
    relative_roughness = roughness_m / max(hydraulic_diameter_m, 1.0e-12)
    return 0.25 / (
        math.log10(relative_roughness / 3.7 + 5.74 / reynolds_number**0.9)
    ) ** 2


def _wall_material_conductivity_w_per_m_k(material: str) -> float:
    material_key = material.strip().lower()
    database = {
        "cucrzr": 320.0,
        "grcop-42": 230.0,
        "inconel 718": 11.0,
        "316l stainless steel": 16.0,
    }
    return database.get(material_key, 25.0)


def _wall_material_limit_k(material: str) -> float:
    material_key = material.strip().lower()
    database = {
        "cucrzr": 820.0,
        "grcop-42": 950.0,
        "inconel 718": 1_100.0,
        "316l stainless steel": 900.0,
    }
    return database.get(material_key, 900.0)


def _resolved_wall_thickness_m(bundle: ExportBundle) -> float:
    wall_thickness_m = bundle.inputs.wall_thickness_m
    if wall_thickness_m is None or wall_thickness_m <= 0.0:
        return 1.5e-3
    return wall_thickness_m


def _build_summary(
    stations: list[ThermalStationResult],
    thermal_inputs: ThermalAnalysisInputs,
    pressure_summary: _PressureSummary,
) -> ThermalAnalysisSummary:
    q_values = [station.q_station_w for station in stations if station.q_station_w is not None]
    p_drop_values = [station.pressure_drop_station_pa for station in stations if station.pressure_drop_station_pa is not None]
    twg_values = [
        station.wall_temperature_hot_gas_side_k
        for station in stations
        if station.wall_temperature_hot_gas_side_k is not None
    ]
    twc_values = [
        station.wall_temperature_coolant_side_k
        for station in stations
        if station.wall_temperature_coolant_side_k is not None
    ]
    margin_values = [station.thermal_margin_k for station in stations if station.thermal_margin_k is not None]

    total_heat_w = sum(q_values) if q_values else None
    coolant_outlet_temperature_k = stations[-1].coolant_temperature_out_k if stations else None
    delta_h_regen = None
    if total_heat_w is not None and thermal_inputs.coolant_mass_flow_kg_per_s not in {None, 0.0}:
        delta_h_regen = total_heat_w / thermal_inputs.coolant_mass_flow_kg_per_s

    return ThermalAnalysisSummary(
        max_wall_temperature_hot_gas_side_k=max(twg_values) if twg_values else None,
        max_wall_temperature_coolant_side_k=max(twc_values) if twc_values else None,
        coolant_outlet_temperature_k=coolant_outlet_temperature_k,
        total_heat_into_coolant_w=total_heat_w,
        total_coolant_pressure_drop_pa=sum(p_drop_values) if p_drop_values else None,
        required_cooling_inlet_pressure_pa=pressure_summary.required_cooling_inlet_pressure_pa,
        required_pump_discharge_pressure_pa=pressure_summary.required_pump_discharge_pressure_pa,
        injector_pressure_drop_pa=thermal_inputs.injector_pressure_drop_pa,
        external_feed_pressure_drop_pa=thermal_inputs.external_feed_pressure_drop_pa,
        pressure_margin_pa=thermal_inputs.pressure_margin_pa,
        minimum_thermal_margin_k=min(margin_values) if margin_values else None,
        propellant_enthalpy_gain_j_per_kg=delta_h_regen,
        estimated_isp_gain_s=None,
        estimated_isp_gain_note=(
            "Preliminary placeholder only; the annulus MVP does not yet turn coolant enthalpy gain into an Isp benefit."
        ),
        pressure_mode_note=pressure_summary.note,
    )


def _lerp(start: float, end: float, fraction: float) -> float:
    return start + (end - start) * fraction


def _average_profile_point(
    left_point: ThermochemistryProfilePoint,
    right_point: ThermochemistryProfilePoint,
) -> ThermochemistryProfilePoint:
    """Create a midpoint profile state for station-wise thermal post-processing."""

    left_state = left_point.state
    right_state = right_point.state
    return ThermochemistryProfilePoint(
        x_m=0.5 * (left_point.x_m + right_point.x_m),
        radius_m=0.5 * (left_point.radius_m + right_point.radius_m),
        area_m2=0.5 * (left_point.area_m2 + right_point.area_m2),
        region=left_point.region if left_point.region == right_point.region else f"{left_point.region}->{right_point.region}",
        station_index=left_point.station_index,
        state=type(left_state)(
            label=f"{left_state.label}->{right_state.label}",
            area_ratio=_avg_optional(left_state.area_ratio, right_state.area_ratio),
            temperature_k=_avg_optional(left_state.temperature_k, right_state.temperature_k),
            density_kg_per_m3=_avg_optional(left_state.density_kg_per_m3, right_state.density_kg_per_m3),
            enthalpy_j_per_kg=_avg_optional(left_state.enthalpy_j_per_kg, right_state.enthalpy_j_per_kg),
            cp_j_per_kg_k=_avg_optional(left_state.cp_j_per_kg_k, right_state.cp_j_per_kg_k),
            viscosity_pa_s=_avg_optional(left_state.viscosity_pa_s, right_state.viscosity_pa_s),
            thermal_conductivity_w_per_m_k=_avg_optional(
                left_state.thermal_conductivity_w_per_m_k,
                right_state.thermal_conductivity_w_per_m_k,
            ),
            prandtl_number=_avg_optional(left_state.prandtl_number, right_state.prandtl_number),
            gamma=_avg_optional(left_state.gamma, right_state.gamma),
            molecular_weight_kg_per_mol=_avg_optional(
                left_state.molecular_weight_kg_per_mol,
                right_state.molecular_weight_kg_per_mol,
            ),
            mach_number=_avg_optional(left_state.mach_number, right_state.mach_number),
            velocity_m_per_s=_avg_optional(left_state.velocity_m_per_s, right_state.velocity_m_per_s),
            reynolds_number=_avg_optional(left_state.reynolds_number, right_state.reynolds_number),
            adiabatic_wall_temperature_k=_avg_optional(
                left_state.adiabatic_wall_temperature_k,
                right_state.adiabatic_wall_temperature_k,
            ),
            thermal_boundary_layer_thickness_m=_avg_optional(
                left_state.thermal_boundary_layer_thickness_m,
                right_state.thermal_boundary_layer_thickness_m,
            ),
            velocity_boundary_layer_thickness_m=_avg_optional(
                left_state.velocity_boundary_layer_thickness_m,
                right_state.velocity_boundary_layer_thickness_m,
            ),
            source=left_state.source if left_state.source == right_state.source else "interpolated",
        ),
    )


def _avg_optional(left_value: float | None, right_value: float | None) -> float | None:
    if left_value is None and right_value is None:
        return None
    if left_value is None:
        return right_value
    if right_value is None:
        return left_value
    return 0.5 * (left_value + right_value)


@dataclass(slots=True)
class _PressureSummary:
    required_cooling_inlet_pressure_pa: float | None
    required_pump_discharge_pressure_pa: float | None
    note: str


def _reconstruct_pressures(
    stations: list[ThermalStationResult],
    *,
    chamber_pressure_pa: float,
    thermal_inputs: ThermalAnalysisInputs,
) -> _PressureSummary:
    """Post-process required or checked pressures from the station loss results.

    The thermal MVP first evaluates station heat pickup and local pressure loss.
    Pressure reconstruction is kept separate so later versions can iterate
    temperature and pressure together without rewriting the UI-facing result
    structure.
    """

    total_cooling_pressure_drop_pa = sum(
        station.pressure_drop_station_pa or 0.0 for station in stations
    )
    injector_inlet_pressure_pa = (
        chamber_pressure_pa
        + thermal_inputs.injector_pressure_drop_pa
        + thermal_inputs.pressure_margin_pa
    )

    if thermal_inputs.solver_settings.pressure_mode is PressureCalculationMode.BACKWARD_REQUIRED_PUMP:
        if stations:
            stations[-1].required_pressure_out_pa = injector_inlet_pressure_pa
            for index in range(len(stations) - 1, -1, -1):
                station = stations[index]
                outlet_pressure = station.required_pressure_out_pa
                if outlet_pressure is None:
                    continue
                inlet_pressure = outlet_pressure + (station.pressure_drop_station_pa or 0.0)
                station.required_pressure_in_pa = inlet_pressure
                if index > 0:
                    stations[index - 1].required_pressure_out_pa = inlet_pressure
        required_cooling_inlet_pressure_pa = stations[0].required_pressure_in_pa if stations else None
        required_pump_discharge_pressure_pa = None
        if required_cooling_inlet_pressure_pa is not None:
            required_pump_discharge_pressure_pa = (
                required_cooling_inlet_pressure_pa + thermal_inputs.external_feed_pressure_drop_pa
            )
        return _PressureSummary(
            required_cooling_inlet_pressure_pa=required_cooling_inlet_pressure_pa,
            required_pump_discharge_pressure_pa=required_pump_discharge_pressure_pa,
            note="Backward required pump pressure from injector-side boundary condition.",
        )

    available_pump_discharge_pressure_pa = thermal_inputs.pump_discharge_pressure_pa
    available_cooling_inlet_pressure_pa = None
    if available_pump_discharge_pressure_pa is not None:
        available_cooling_inlet_pressure_pa = (
            available_pump_discharge_pressure_pa - thermal_inputs.external_feed_pressure_drop_pa
        )
    if stations and available_cooling_inlet_pressure_pa is not None:
        running_pressure = available_cooling_inlet_pressure_pa
        for station in stations:
            station.required_pressure_in_pa = running_pressure
            station.required_pressure_out_pa = running_pressure - (station.pressure_drop_station_pa or 0.0)
            running_pressure = station.required_pressure_out_pa
        outlet_pressure = stations[-1].required_pressure_out_pa or 0.0
        margin_to_injector_pa = outlet_pressure - injector_inlet_pressure_pa
        status_message = (
            f"Forward pressure check margin to injector requirement: {margin_to_injector_pa:.0f} Pa."
        )
        if margin_to_injector_pa < 0.0:
            stations[-1].status = f"{stations[-1].status}, insufficient outlet pressure".strip(", ")
        return _PressureSummary(
            required_cooling_inlet_pressure_pa=available_cooling_inlet_pressure_pa,
            required_pump_discharge_pressure_pa=available_pump_discharge_pressure_pa,
            note=status_message,
        )

    return _PressureSummary(
        required_cooling_inlet_pressure_pa=None,
        required_pump_discharge_pressure_pa=None,
        note="Forward pressure check selected, but no pump discharge pressure was available.",
    )

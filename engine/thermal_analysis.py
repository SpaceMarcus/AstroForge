"""Station-wise annulus cooling reference model for AstraForge.

This module intentionally keeps the MVP cooling logic separate from the GUI.
The current implementation is a predesign-level annulus reference model, not a
full regenerative channel solver. It consumes the active ExportBundle from the
committed Current Design path and adds only the cooling-side assumptions that
are specific to the thermal analysis workflow.

The coolant-side correlations currently assume fully developed annular flow.
That is a conservative predesign choice for wall heat transfer because real
entry regions often show stronger local mixing and therefore higher local
coolant-side heat-transfer coefficients than the fully developed baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re

from engine.models import ExportBundle, NozzlePoint, ThermochemistryProfilePoint
from engine.models import ManufacturingRoute
from engine.properties import CoolantProperties, MaterialProperties, get_coolant_properties, get_material_properties
from engine.utils.validation import InputValidationError

_DEFAULT_STATION_TOLERANCE = 0.1
_DEFAULT_MAX_ITERATIONS = 25
_DEFAULT_RELAXATION_FACTOR = 0.6
_DEFAULT_ANNULUS_GAP_M = 1.5e-3
_DEFAULT_ROUGHNESS_M = 15.0e-6
_DEFAULT_COOLANT_INLET_TEMPERATURE_K = 293.15
_COOLANT_LAMINAR_RE_MAX = 2_300.0
_COOLANT_TURBULENT_RE_MIN = 10_000.0
_GNIELINSKI_RE_MIN = 3_000.0
_SMALL_DELTA_K = 1.0e-6
_MECHANICAL_REFERENCE_TEMPERATURE_K = 293.15
_HIGH_SCREENING_STRAIN_LIMIT = 3.0e-3
_DEFAULT_MEAN_THERMAL_RESTRAINT_FACTOR = 0.0
_DEFAULT_GRADIENT_THERMAL_RESTRAINT_FACTOR = 1.0
_STEFAN_BOLTZMANN_CONSTANT_W_PER_M2_K4 = 5.670374419e-8
_RADIATING_SPECIES_COEFFICIENTS = {
    "co2": 0.05,
    "h2o": 0.08,
    "co": 0.025,
    "oh": 0.02,
    "no": 0.015,
    "no2": 0.04,
    "so2": 0.05,
    "ch4": 0.03,
}
_DEFAULT_POLYATOMIC_RADIATION_COEFFICIENT = 0.02


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


class CoolingSegmentModelType(str, Enum):
    """Segment model label kept for the thermal network preview and future builders."""

    ANNULUS = "annulus"


class ThermalSolverType(str, Enum):
    """Station update schemes exposed in the thermal-analysis UI."""

    FORWARD_EULER = "forward-euler"
    BACKWARD_EULER = "backward-euler"
    CRANK_NICOLSON = "crank-nicolson"
    NTU_EXPONENTIAL = "ntu-exponential"
    SIMPSON_CONDUCTANCE = "simpson-conductance"


class CoolantNusseltMethod(str, Enum):
    """Primary coolant-side Nu_c choices for the annulus MVP."""

    DITTUS_BOELTER = "dittus-boelter"
    SIEDER_TATE = "sieder-tate"
    GNIELINSKI = "gnielinski"


class StationDistributionMode(str, Enum):
    """How the station list is generated for the cooling calculation."""

    MANUAL = "manual"
    CEA_PROFILE = "cea-profile"


class StationEvaluationPoint(str, Enum):
    """Where local geometry and gas-side station values are evaluated."""

    SOLVER_DEFAULT = "solver-default"
    COOLANT_UPSTREAM = "coolant-upstream"
    MIDPOINT = "midpoint"
    COOLANT_DOWNSTREAM = "coolant-downstream"
    TRAPEZOIDAL = "trapezoidal"


class CoolantBulkTemperatureReference(str, Enum):
    """Which coolant temperature definition is used for local property lookup."""

    SOLVER_DEFAULT = "solver-default"
    COOLANT_INLET = "coolant-inlet"
    COOLANT_OUTLET = "coolant-outlet"
    STATION_MEAN = "station-mean"
    ITERATED_MEAN = "iterated-mean"


class PressureCalculationMode(str, Enum):
    """Pressure post-processing modes for the thermal-analysis MVP."""

    BACKWARD_REQUIRED_PUMP = "backward-required-pump"
    FORWARD_PUMP_CHECK = "forward-pump-check"


class BartzThroatCurvatureMode(str, Enum):
    """How the constant Bartz throat-curvature term is selected for the nozzle."""

    UPSTREAM = "upstream"
    MEAN = "mean"
    DOWNSTREAM = "downstream"


class RadiationModelType(str, Enum):
    """Hot-gas-side radiation models available in the MVP thermal solver."""

    OFF = "off"
    GREY_GAS = "grey-gas"
    USER_FIXED_HEAT_FLUX = "user-fixed-heat-flux"
    PARTICIPATING_MEDIA_EFFECTIVE_EMISSIVITY = "participating-media-effective-emissivity"


class RadiationTemperatureSource(str, Enum):
    """How the effective radiation temperature is selected per station."""

    LOCAL_GAS_TEMPERATURE = "local-gas-temperature"
    ADIABATIC_WALL_TEMPERATURE = "adiabatic-wall-temperature"
    CHAMBER_TEMPERATURE = "chamber-temperature"


class ParticipatingMediaModelType(str, Enum):
    """Placeholder families for later participating-media refinements."""

    EFFECTIVE_EMISSIVITY = "effective-emissivity"
    SIMPLE_CO2_H2O_PLACEHOLDER = "simple-co2-h2o-placeholder"


class ParticipatingSpeciesMode(str, Enum):
    """Which local species participate in the screening radiation estimate."""

    CO2_H2O_ONLY = "co2-h2o-only"
    ALL_RADIATING_POLYATOMIC = "all-radiating-polyatomic"


class OpticalPathLengthMode(str, Enum):
    """Optical-path definitions for the screening radiation model."""

    LOCAL_DIAMETER = "local-diameter"
    USER_FIXED = "user-fixed"
    MEAN_BEAM_LENGTH_PLACEHOLDER = "mean-beam-length-placeholder"


class StationSelectorType(str, Enum):
    """Selector types for future station-range-based thermal conditions."""

    FULL_CONTOUR = "full-contour"
    X_VALUE = "x-value"
    AREA_RATIO = "area-ratio"
    STATION_INDEX = "station-index"
    REGION = "region"
    MARKER = "marker"


class ThermalConditionType(str, Enum):
    """Range and event placeholders for later thermal-scenario expansion."""

    COOLING_ACTIVE_RANGE = "cooling-active-range"
    FLOW_DIRECTION_CHANGE = "flow-direction-change"
    RADIATION_ACTIVE_RANGE = "radiation-active-range"
    FILM_COOLING_PLACEHOLDER = "film-cooling-placeholder"
    LOCAL_ROUGHNESS_OVERRIDE = "local-roughness-override"
    LOCAL_WALL_THICKNESS_OVERRIDE = "local-wall-thickness-override"
    PRESSURE_LOSS_ELEMENT = "pressure-loss-element"


class ThermalMechanismType(str, Enum):
    """Heat-transfer mechanisms that can later be switched per station range."""

    HOT_GAS_CONVECTION = "hot-gas-convection"
    COOLANT_CONVECTION = "coolant-convection"
    WALL_CONDUCTION = "wall-conduction"
    RADIATION = "radiation"
    FILM_COOLING_FUTURE = "film-cooling-future"
    CHANNEL_RIB_NETWORK_FUTURE = "channel-rib-network-future"


class SolverExecutionMode(str, Enum):
    """Execution-plan modes for the modular thermal scenario skeleton."""

    SINGLE_RUN = "single-run"
    PARALLEL_COMPARISON = "parallel-comparison"
    SEQUENTIAL_PIPELINE = "sequential-pipeline"


@dataclass(slots=True)
class RadiationSettings:
    """Optional hot-gas-side radiation settings for the annulus MVP.

    Radiation stays explicitly separate from the Bartz convection path so the
    solver can report, plot and later calibrate radiative heat transfer
    without hiding it inside an effective gas-side heat-transfer coefficient.
    """

    enabled: bool = False
    model: RadiationModelType = RadiationModelType.GREY_GAS
    wall_emissivity: float = 0.8
    gas_effective_emissivity: float = 0.15
    radiation_temperature_source: RadiationTemperatureSource = RadiationTemperatureSource.LOCAL_GAS_TEMPERATURE
    participating_media_enabled: bool = False
    participating_media_model: ParticipatingMediaModelType = ParticipatingMediaModelType.EFFECTIVE_EMISSIVITY
    participating_species_mode: ParticipatingSpeciesMode = ParticipatingSpeciesMode.CO2_H2O_ONLY
    co2_mole_fraction: float | None = None
    h2o_mole_fraction: float | None = None
    optical_path_length_mode: OpticalPathLengthMode = OpticalPathLengthMode.LOCAL_DIAMETER
    user_optical_path_length_m: float | None = None
    soot_factor: float = 0.0
    radiation_relaxation_factor: float = 1.0
    fixed_radiation_heat_flux_w_per_m2: float | None = None


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
    primary_coolant_nusselt_method: CoolantNusseltMethod = CoolantNusseltMethod.GNIELINSKI
    model_type: ThermalModelType = ThermalModelType.ANNULUS
    coolant_inlet_temperature_k: float = 293.15
    annulus_gap_m: float = _DEFAULT_ANNULUS_GAP_M
    coolant_roughness_m: float = _DEFAULT_ROUGHNESS_M
    injector_pressure_drop_pa: float = 5.0e5
    pressure_margin_pa: float = 2.0e5
    external_feed_pressure_drop_pa: float = 1.0e5
    pump_discharge_pressure_pa: float | None = None
    bartz_throat_curvature_mode: BartzThroatCurvatureMode = BartzThroatCurvatureMode.UPSTREAM
    flow_direction: CoolingFlowDirection = CoolingFlowDirection.NOZZLE_TO_INJECTOR
    solver_settings: SolverSettings = field(default_factory=SolverSettings)
    radiation_settings: RadiationSettings = field(default_factory=RadiationSettings)


@dataclass(slots=True)
class StationSelector:
    """Selector placeholder for future range-based thermal conditions."""

    selector_type: StationSelectorType
    value: float | int | str | None = None


@dataclass(slots=True)
class ThermalCondition:
    """Stored thermal condition for later range-aware solver extensions."""

    condition_type: ThermalConditionType
    start: StationSelector
    end: StationSelector
    enabled: bool = True
    priority: int = 0
    parameters: dict[str, object] = field(default_factory=dict)
    note: str = ""


@dataclass(slots=True)
class ThermalMechanism:
    """Mechanism toggle plus local settings for the modular scenario skeleton."""

    mechanism_type: ThermalMechanismType
    enabled: bool = True
    start: StationSelector | None = None
    end: StationSelector | None = None
    settings: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class CoolantPass:
    """One coolant pass definition used to prebuild the thermal R-network path."""

    name: str
    start: StationSelector
    end: StationSelector
    direction: CoolingFlowDirection
    mass_flow_fraction: float = 1.0
    enabled: bool = True


@dataclass(slots=True)
class CoolantCircuit:
    """Coolant-path skeleton for later multi-pass or split-flow extensions."""

    name: str
    passes: list[CoolantPass] = field(default_factory=list)


@dataclass(slots=True)
class ThermalSolverPlan:
    """Execution plan metadata for the modular scenario builder."""

    execution_mode: SolverExecutionMode = SolverExecutionMode.SINGLE_RUN
    run_parallel_nusselt_comparison: bool = True
    run_parallel_pressure_modes: bool = False
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class ThermalScenario:
    """Modular thermal-scenario skeleton wrapped around the MVP annulus solver."""

    name: str = "Default Thermal Scenario"
    global_conditions: ThermalAnalysisInputs = field(default_factory=ThermalAnalysisInputs)
    coolant_circuit: CoolantCircuit = field(
        default_factory=lambda: CoolantCircuit(
            name="Single pass",
            passes=[
                CoolantPass(
                    name="Pass 1",
                    start=StationSelector(StationSelectorType.FULL_CONTOUR),
                    end=StationSelector(StationSelectorType.FULL_CONTOUR),
                    direction=CoolingFlowDirection.NOZZLE_TO_INJECTOR,
                )
            ],
        )
    )
    mechanisms: list[ThermalMechanism] = field(default_factory=list)
    conditions: list[ThermalCondition] = field(default_factory=list)
    solver_plan: ThermalSolverPlan = field(default_factory=ThermalSolverPlan)


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
    coolant_wall_area_m2: float
    wall_mean_area_m2: float


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
    coolant_prandtl_number: float | None
    coolant_cp_j_per_kg_k: float | None
    coolant_viscosity_pa_s: float | None
    nusselt_coolant: float | None
    nusselt_coolant_method: str | None = None
    nusselt_dittus_boelter: float | None = None
    nusselt_sieder_tate: float | None = None
    nusselt_gnielinski: float | None = None
    nusselt_spread_fraction: float | None = None
    friction_factor: float | None = None
    h_c_dittus_boelter_w_per_m2_k: float | None = None
    h_c_sieder_tate_w_per_m2_k: float | None = None
    h_c_gnielinski_w_per_m2_k: float | None = None
    thermal_margin_k: float | None = None
    wall_mean_temperature_k: float | None = None
    pressure_delta_pa: float | None = None
    pressure_hoop_stress_pa: float | None = None
    pressure_longitudinal_stress_pa: float | None = None
    hoop_stress_pa: float | None = None
    longitudinal_stress_pa: float | None = None
    thermal_strain: float | None = None
    free_mean_thermal_strain: float | None = None
    differential_thermal_strain: float | None = None
    thermal_stress_pa: float | None = None
    thermal_membrane_stress_upper_bound_pa: float | None = None
    thermal_gradient_stress_upper_bound_pa: float | None = None
    equivalent_von_mises_stress_pa: float | None = None
    von_mises_hot_side_pa: float | None = None
    von_mises_cold_side_pa: float | None = None
    material_yield_strength_pa: float | None = None
    yield_strength_hot_side_pa: float | None = None
    yield_strength_cold_side_pa: float | None = None
    material_strength_margin: float | None = None
    material_margin_hot_side: float | None = None
    material_margin_cold_side: float | None = None
    material_margin_status: str | None = None
    plasticity_expected_hot_side: bool | None = None
    plasticity_expected_cold_side: bool | None = None
    closeout_thickness_m: float | None = None
    closeout_material: str | None = None
    closeout_hoop_stress_pa: float | None = None
    closeout_material_yield_strength_pa: float | None = None
    closeout_material_strength_margin: float | None = None
    elastic_strain_pressure: float | None = None
    elastic_strain_thermal: float | None = None
    total_screening_strain: float | None = None
    mechanical_model_note: str | None = None
    q_conv_w_per_m2: float | None = None
    q_rad_w_per_m2: float | None = None
    q_total_w_per_m2: float | None = None
    q_radiation_station_w: float | None = None
    radiation_temperature_k: float | None = None
    gas_effective_emissivity: float | None = None
    wall_emissivity: float | None = None
    optical_path_length_m: float | None = None
    radiation_model_note: str | None = None
    participating_species_mode: str | None = None
    participating_species_used: str | None = None
    x_ref_m: float | None = None
    r_ref_m: float | None = None
    area_ref_m2: float | None = None
    eps_ref: float | None = None
    station_reference_label: str | None = None
    station_reference_reason: str | None = None
    x_engine_start_m: float | None = None
    x_engine_end_m: float | None = None
    x_engine_mid_m: float | None = None
    r_start_m: float | None = None
    r_mid_m: float | None = None
    r_end_m: float | None = None
    eps_start: float | None = None
    eps_mid: float | None = None
    eps_end: float | None = None
    region_label: str | None = None
    engine_station_index: int | None = None
    coolant_path_index: int | None = None
    coolant_pass_id: str | None = None
    coolant_bulk_temperature_reference_label: str | None = None
    coolant_bulk_temperature_reference_reason: str | None = None
    coolant_wall_viscosity_pa_s: float | None = None
    sieder_tate_viscosity_ratio: float | None = None
    sieder_tate_correction_factor: float | None = None
    status_summary: str = "ok"
    warning_summary: str = "--"
    status: str = ""
    status_notes: tuple[str, ...] = ()
    warning_notes: tuple[str, ...] = ()
    iterations: int | None = None
    converged: bool | None = None
    residual_k: float | None = None
    solver_scheme_label: str | None = None
    conductance_rule_label: str | None = None
    gas_conductance_w_per_k: float | None = None
    coolant_conductance_w_per_k: float | None = None
    gas_resistance_k_per_w: float | None = None
    wall_resistance_k_per_w: float | None = None
    coolant_resistance_k_per_w: float | None = None
    coolant_flow_area_m2: float | None = None
    coolant_wall_area_m2: float | None = None


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
    thermal_scenario_name: str | None = None
    primary_coolant_nusselt_method: str | None = None
    nusselt_comparison_enabled: bool = True
    active_mechanisms_summary: str | None = None
    global_conditions_summary: str | None = None
    station_condition_summary: str | None = None
    coolant_property_source: str | None = None
    material_property_source: str | None = None
    stations_with_property_warnings: int | None = None
    stations_outside_property_table_range: int | None = None
    max_nusselt_spread_fraction: float | None = None
    stations_with_large_nusselt_spread: int | None = None
    stations_outside_nusselt_validity: int | None = None
    stations_with_high_h_c: int | None = None
    total_radiation_heat_w: float | None = None
    max_radiation_heat_flux_w_per_m2: float | None = None
    radiation_fraction_of_total_heat: float | None = None
    radiation_enabled: bool = False
    max_von_mises_stress_pa: float | None = None
    min_material_strength_margin: float | None = None
    max_thermal_stress_pa: float | None = None
    max_thermal_strain: float | None = None
    max_total_screening_strain: float | None = None
    stations_with_material_margin_exceeded: int | None = None
    stations_with_low_material_margin: int | None = None
    closeout_min_material_strength_margin: float | None = None


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
class CoolingSegmentAssignment:
    """Structured solver-facing view of one active cooling segment."""

    segment_node_id: str
    segment_label: str
    segment_model_type: CoolingSegmentModelType
    range_label: str
    flow_direction: CoolingFlowDirection
    mass_flow_fraction: float
    parameters: dict[str, object]
    active_mechanisms: tuple[ThermalMechanismType, ...]


@dataclass(slots=True)
class ThermalNetworkNode:
    """One node in the previewable station thermal network."""

    id: str
    label: str
    node_type: str
    temperature_role: str | None = None


@dataclass(slots=True)
class ThermalNetworkElement:
    """One resistive or source element in the previewable station network."""

    id: str
    label: str
    element_type: str
    from_node_id: str
    to_node_id: str
    value: float | None
    unit: str
    source: str
    active: bool = True
    note: str = ""


@dataclass(slots=True)
class StationThermalNetwork:
    """Preview object representing one station-wise thermal network."""

    station_id: int
    engine_station_index: int | None
    coolant_path_index: int | None
    coolant_pass_id: str | None
    region_label: str
    segment_node_id: str
    segment_label: str
    segment_model_type: CoolingSegmentModelType
    active_mechanisms: tuple[ThermalMechanismType, ...]
    nodes: tuple[ThermalNetworkNode, ...]
    elements: tuple[ThermalNetworkElement, ...]
    warnings: tuple[str, ...]
    notes: tuple[str, ...]
    integration_rule_label: str
    network_sketch: str
    flow_direction: CoolingFlowDirection
    hot_wall_area_m2: float | None = None
    coolant_wall_area_m2: float | None = None
    flow_area_m2: float | None = None
    hydraulic_diameter_m: float | None = None


@dataclass(slots=True)
class ThermalNetworkBuildResult:
    """Pre-solve network build artifact used by the GUI and the solver."""

    status: str
    build_id: str
    station_networks: tuple[StationThermalNetwork, ...]
    segment_assignments: tuple[CoolingSegmentAssignment, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    summary: str
    setup_summary: str
    active_station_network_builder: str
    design_fingerprint: str
    solver_settings_fingerprint: str
    mechanism_settings_fingerprint: str
    effective_inputs: ThermalAnalysisInputs
    station_samples: tuple[_SamplePoint, ...]


@dataclass(slots=True)
class CommittedThermalNetwork:
    """Committed thermal-network artifact that downstream solver pages consume."""

    build_id: str
    created_at: str
    design_fingerprint: str
    geometry_fingerprint: str
    material_fingerprint: str
    manufacturing_fingerprint: str
    cooling_layout_fingerprint: str
    solver_mechanism_fingerprint: str
    network_build_result: ThermalNetworkBuildResult
    status: str
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class _CoolantNusseltCorrelationResult:
    """Selected plus comparison Nu_c values for one iteration-local coolant state."""

    selected_method: CoolantNusseltMethod
    selected_nusselt: float
    dittus_boelter: float | None
    sieder_tate: float | None
    gnielinski: float | None
    spread_fraction: float | None
    regime_label: str
    validity_note: str
    sieder_tate_viscosity_ratio: float | None = None
    sieder_tate_correction_factor: float | None = None
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class _GasSideProperties:
    """Gas-side transport and state data reused directly from CEA/profile output."""

    cp_j_per_kg_k: float
    viscosity_pa_s: float
    prandtl_number: float
    gamma: float
    mach_number: float
    local_gas_temperature_k: float
    recovery_temperature_k: float
    chamber_temperature_k: float
    throat_curvature_radius_m: float
    throat_curvature_mode: BartzThroatCurvatureMode


@dataclass(slots=True)
class _CoolantTransportState:
    """Iteration-local coolant transport state for one annulus station.

    The MVP still uses constant fallback properties per coolant, but the state
    object is built inside the station loop so a later temperature/pressure-
    dependent property lookup can replace the current constants without
    changing the rest of the station solver structure.
    """

    properties: CoolantProperties
    velocity_m_per_s: float
    prandtl_number: float
    reynolds_number: float
    nusselt_number: float
    nusselt_method: str
    nusselt_dittus_boelter: float | None
    nusselt_sieder_tate: float | None
    nusselt_gnielinski: float | None
    nusselt_spread_fraction: float | None
    h_c_w_per_m2_k: float
    h_c_dittus_boelter_w_per_m2_k: float | None
    h_c_sieder_tate_w_per_m2_k: float | None
    h_c_gnielinski_w_per_m2_k: float | None
    friction_factor: float
    coolant_regime_label: str
    friction_regime_label: str
    pressure_drop_friction_pa: float
    pressure_drop_minor_pa: float
    pressure_drop_acceleration_pa: float
    pressure_drop_total_pa: float
    bulk_temperature_reference_label: str
    bulk_temperature_reference_reason: str
    wall_viscosity_pa_s: float | None = None
    sieder_tate_viscosity_ratio: float | None = None
    sieder_tate_correction_factor: float | None = None
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class _StationHeatBalanceResult:
    """Fully coupled station solution used to populate one output row."""

    h_g_w_per_m2_k: float
    h_c_w_per_m2_k: float
    recovery_temperature_k: float
    coolant_temperature_out_k: float
    coolant_temperature_bulk_k: float
    q_station_w: float
    q_hot_w_per_m2: float
    q_conv_w_per_m2: float
    q_rad_w_per_m2: float
    q_total_w_per_m2: float
    q_radiation_station_w: float
    wall_temperature_coolant_side_k: float
    wall_temperature_hot_gas_side_k: float
    wall_delta_t_k: float
    coolant_bulk_temperature_reference_label: str
    coolant_bulk_temperature_reference_reason: str
    radiation_temperature_k: float | None
    gas_effective_emissivity: float | None
    wall_emissivity: float | None
    optical_path_length_m: float | None
    radiation_model_note: str | None
    participating_species_mode: str | None
    participating_species_used: str | None
    reynolds_coolant: float
    prandtl_coolant: float
    coolant_cp_j_per_kg_k: float
    coolant_viscosity_pa_s: float
    nusselt_coolant: float
    nusselt_coolant_method: str
    nusselt_dittus_boelter: float | None
    nusselt_sieder_tate: float | None
    nusselt_gnielinski: float | None
    nusselt_spread_fraction: float | None
    friction_factor: float
    h_c_dittus_boelter_w_per_m2_k: float | None
    h_c_sieder_tate_w_per_m2_k: float | None
    h_c_gnielinski_w_per_m2_k: float | None
    coolant_wall_viscosity_pa_s: float | None
    sieder_tate_viscosity_ratio: float | None
    sieder_tate_correction_factor: float | None
    gas_conductance_w_per_k: float
    coolant_conductance_w_per_k: float
    gas_resistance_k_per_w: float
    wall_resistance_k_per_w: float
    coolant_resistance_k_per_w: float
    coolant_flow_area_m2: float
    coolant_wall_area_m2: float
    conductance_rule_label: str
    solver_scheme_label: str
    pressure_drop_station_pa: float
    wall_material_properties: MaterialProperties
    iterations: int
    converged: bool
    residual_k: float
    status_notes: tuple[str, ...] = ()


@dataclass(slots=True)
class _StationReferenceState:
    """One explicit evaluation state inside a station segment."""

    x_m: float
    radius_m: float
    area_m2: float
    eps: float
    profile_point: ThermochemistryProfilePoint | None


@dataclass(slots=True)
class _StationSubpoint:
    """One geometric/gas-side evaluation point inside a station."""

    name: str
    x_m: float
    radius_m: float
    r_outer_m: float
    r_mean_m: float
    area_gas_m2: float
    eps: float
    coolant_flow_area_m2: float
    hot_wall_area_m2: float
    coolant_wall_area_m2: float
    wall_mean_area_m2: float
    hydraulic_diameter_m: float
    profile_point: ThermochemistryProfilePoint | None


@dataclass(slots=True)
class _LocalClosureState:
    """One local closure evaluation used by the station integration rule."""

    subpoint: _StationSubpoint
    gas_side_properties: _GasSideProperties
    coolant_transport: _CoolantTransportState
    h_g_w_per_m2_k: float
    g_gas_w_per_k: float
    g_coolant_w_per_k: float
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class _StationConductanceState:
    """Aggregated conductance state owned by the selected station scheme."""

    integration_scheme_label: str
    conductance_rule_label: str
    display_subpoint_name: str
    x_display_m: float
    radius_display_m: float
    area_display_m2: float
    eps_display: float
    recovery_temperature_k: float
    coolant_bulk_temperature_k: float
    g_gas_w_per_k: float
    g_coolant_w_per_k: float
    h_g_station_w_per_m2_k: float
    h_c_station_w_per_m2_k: float
    nusselt_station: float
    reynolds_station: float
    prandtl_station: float
    hot_area_station_m2: float
    coolant_area_station_m2: float
    flow_area_station_m2: float
    wall_mean_area_station_m2: float
    hydraulic_diameter_station_m: float
    pressure_drop_station_pa: float
    coolant_cp_j_per_kg_k: float
    coolant_viscosity_pa_s: float
    coolant_wall_viscosity_pa_s: float | None
    nusselt_method: str
    nusselt_dittus_boelter: float | None
    nusselt_sieder_tate: float | None
    nusselt_gnielinski: float | None
    nusselt_spread_fraction: float | None
    h_c_dittus_boelter_w_per_m2_k: float | None
    h_c_sieder_tate_w_per_m2_k: float | None
    h_c_gnielinski_w_per_m2_k: float | None
    friction_factor: float
    sieder_tate_viscosity_ratio: float | None
    sieder_tate_correction_factor: float | None
    representative_profile_point: ThermochemistryProfilePoint | None
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class _RadiationHeatTransferResult:
    """Radiation contribution kept separate from Bartz convection in one station."""

    q_rad_w_per_m2: float
    q_radiation_station_w: float
    radiation_temperature_k: float | None
    gas_effective_emissivity: float | None
    wall_emissivity: float | None
    optical_path_length_m: float | None
    model_note: str
    participating_species_mode: str | None = None
    participating_species_used: str | None = None
    status_notes: tuple[str, ...] = ()


@dataclass(slots=True)
class _MechanicalStationScreeningResult:
    """Predesign pressure/thermal stress screening derived from one station."""

    wall_mean_temperature_k: float | None
    pressure_delta_pa: float | None
    pressure_hoop_stress_pa: float | None
    pressure_longitudinal_stress_pa: float | None
    hoop_stress_pa: float | None
    longitudinal_stress_pa: float | None
    thermal_strain: float | None
    free_mean_thermal_strain: float | None
    differential_thermal_strain: float | None
    thermal_stress_pa: float | None
    thermal_membrane_stress_upper_bound_pa: float | None
    thermal_gradient_stress_upper_bound_pa: float | None
    equivalent_von_mises_stress_pa: float | None
    von_mises_hot_side_pa: float | None
    von_mises_cold_side_pa: float | None
    material_yield_strength_pa: float | None
    yield_strength_hot_side_pa: float | None
    yield_strength_cold_side_pa: float | None
    material_strength_margin: float | None
    material_margin_hot_side: float | None
    material_margin_cold_side: float | None
    material_margin_status: str | None
    plasticity_expected_hot_side: bool | None
    plasticity_expected_cold_side: bool | None
    closeout_thickness_m: float | None
    closeout_material: str | None
    closeout_hoop_stress_pa: float | None
    closeout_material_yield_strength_pa: float | None
    closeout_material_strength_margin: float | None
    elastic_strain_pressure: float | None
    elastic_strain_thermal: float | None
    total_screening_strain: float | None
    mechanical_model_note: str | None
    status_notes: tuple[str, ...] = ()


@dataclass(slots=True)
class _SamplePoint:
    x_start_m: float
    radius_start_m: float
    area_start_m2: float
    eps_start: float
    x_mid_m: float
    radius_mid_m: float
    area_mid_m2: float
    eps_mid: float
    x_end_m: float
    radius_end_m: float
    area_end_m2: float
    eps_end: float
    x_ref_m: float
    radius_ref_m: float
    area_ref_m2: float
    eps_ref: float
    reference_label: str
    reference_reason: str
    profile_point_start: ThermochemistryProfilePoint | None
    profile_point_mid: ThermochemistryProfilePoint | None
    profile_point_end: ThermochemistryProfilePoint | None
    profile_point_ref: ThermochemistryProfilePoint | None
    ds_m: float
    engine_station_index: int
    coolant_path_index: int = 0
    coolant_pass_id: str | None = None

    @property
    def x_m(self) -> float:
        return self.x_ref_m

    @property
    def radius_m(self) -> float:
        return self.radius_ref_m

    @property
    def area_m2(self) -> float:
        return self.area_ref_m2

    @property
    def profile_point(self) -> ThermochemistryProfilePoint | None:
        return self.profile_point_ref

    @property
    def region_label(self) -> str:
        region = self.profile_point_ref.region if self.profile_point_ref is not None else ""
        if region:
            return region
        if self.x_ref_m < 0.0:
            return "chamber"
        if math.isclose(self.x_ref_m, 0.0, abs_tol=1.0e-9):
            return "throat"
        return "nozzle"


@dataclass(slots=True)
class _ThermalPrecalculation:
    """Shared thermal-model precalculation before the station-by-station solve.

    This stage turns the selected coolant circuit and station grid into the
    effective R-network path the later station solver marches over. Keeping it
    explicit avoids hidden recomputation from stale setup fragments.
    """

    scenario: ThermalScenario
    effective_inputs: ThermalAnalysisInputs
    station_samples: list[_SamplePoint]
    bundle_status_notes: tuple[str, ...]
    wall_temperature_limit_k: float
    wall_thickness_m: float
    wall_material_id: str
    reference_coolant_pressure_estimate_pa: float


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


def default_thermal_scenario(
    bundle: ExportBundle | None = None,
    *,
    fuel_name: str | None = None,
) -> ThermalScenario:
    """Return the default modular thermal scenario wrapped around the MVP solver."""

    return thermal_scenario_from_inputs(
        default_thermal_analysis_inputs(bundle, fuel_name=fuel_name),
        name="Annulus baseline",
    )


def thermal_scenario_from_inputs(
    thermal_inputs: ThermalAnalysisInputs,
    *,
    name: str = "Annulus baseline",
) -> ThermalScenario:
    """Wrap the current thermal input set in the modular scenario skeleton."""

    full_contour_selector = StationSelector(StationSelectorType.FULL_CONTOUR)
    coolant_pass = CoolantPass(
        name="Pass 1",
        start=full_contour_selector,
        end=full_contour_selector,
        direction=thermal_inputs.flow_direction,
    )
    mechanisms = [
        ThermalMechanism(
            mechanism_type=ThermalMechanismType.HOT_GAS_CONVECTION,
            enabled=True,
            settings={"model": "Bartz"},
        ),
        ThermalMechanism(
            mechanism_type=ThermalMechanismType.COOLANT_CONVECTION,
            enabled=True,
            settings={
                "primary_nusselt_method": thermal_inputs.primary_coolant_nusselt_method.value,
                "background_comparison": True,
            },
        ),
        ThermalMechanism(
            mechanism_type=ThermalMechanismType.WALL_CONDUCTION,
            enabled=True,
        ),
        ThermalMechanism(
            mechanism_type=ThermalMechanismType.RADIATION,
            enabled=thermal_inputs.radiation_settings.enabled,
            settings={"model": thermal_inputs.radiation_settings.model.value},
        ),
        ThermalMechanism(
            mechanism_type=ThermalMechanismType.FILM_COOLING_FUTURE,
            enabled=False,
            settings={"status": "planned"},
        ),
        ThermalMechanism(
            mechanism_type=ThermalMechanismType.CHANNEL_RIB_NETWORK_FUTURE,
            enabled=False,
            settings={"status": "planned"},
        ),
    ]
    conditions = [
        ThermalCondition(
            condition_type=ThermalConditionType.COOLING_ACTIVE_RANGE,
            start=full_contour_selector,
            end=full_contour_selector,
            enabled=True,
            note="MVP uses the full contour as the active cooling range.",
        ),
        ThermalCondition(
            condition_type=ThermalConditionType.RADIATION_ACTIVE_RANGE,
            start=full_contour_selector,
            end=full_contour_selector,
            enabled=thermal_inputs.radiation_settings.enabled,
            note="Range-local radiation conditions are planned; MVP applies one global setting.",
        ),
    ]
    return ThermalScenario(
        name=name,
        global_conditions=thermal_inputs,
        coolant_circuit=CoolantCircuit(name="Single pass", passes=[coolant_pass]),
        mechanisms=mechanisms,
        conditions=conditions,
        solver_plan=ThermalSolverPlan(
            execution_mode=SolverExecutionMode.SINGLE_RUN,
            run_parallel_nusselt_comparison=True,
            run_parallel_pressure_modes=False,
            notes=(
                "Model precalculation builds the annulus resistance path from the active coolant circuit before the station solver runs.",
            ),
        ),
    )


def _default_active_mechanisms(
    thermal_inputs: ThermalAnalysisInputs,
) -> tuple[ThermalMechanismType, ...]:
    mechanisms = [
        ThermalMechanismType.HOT_GAS_CONVECTION,
        ThermalMechanismType.COOLANT_CONVECTION,
        ThermalMechanismType.WALL_CONDUCTION,
    ]
    if thermal_inputs.radiation_settings.enabled:
        mechanisms.append(ThermalMechanismType.RADIATION)
    return tuple(mechanisms)


def _build_default_segment_assignment(
    thermal_inputs: ThermalAnalysisInputs,
) -> CoolingSegmentAssignment:
    """Build the current MVP annulus segment assignment without graph objects."""

    return CoolingSegmentAssignment(
        segment_node_id="annulus-baseline",
        segment_label="Annulus Baseline",
        segment_model_type=CoolingSegmentModelType.ANNULUS,
        range_label="full contour",
        flow_direction=thermal_inputs.flow_direction,
        mass_flow_fraction=1.0,
        parameters={
            "annulus_gap_m": thermal_inputs.annulus_gap_m,
            "roughness_m": thermal_inputs.coolant_roughness_m,
            "model_type": thermal_inputs.model_type.value,
        },
        active_mechanisms=_default_active_mechanisms(thermal_inputs),
    )


def _build_network_setup_summary(thermal_inputs: ThermalAnalysisInputs) -> str:
    return (
        "Cooling path: single annulus baseline over full contour\n"
        f"Flow direction: {thermal_inputs.flow_direction.value}\n"
        f"Annulus gap: {thermal_inputs.annulus_gap_m:.6g} m | "
        f"Roughness: {thermal_inputs.coolant_roughness_m:.6g} m"
    )


def _build_station_thermal_network(
    station_id: int,
    sample: _SamplePoint,
    segment: CoolingSegmentAssignment,
    effective_inputs: ThermalAnalysisInputs,
) -> StationThermalNetwork:
    geometry = _build_annulus_geometry(sample, effective_inputs.annulus_gap_m)
    nodes = (
        ThermalNetworkNode(id="hot_gas", label="T_aw", node_type="hot_gas", temperature_role="recovery"),
        ThermalNetworkNode(id="hot_wall", label="T_wg", node_type="hot_wall", temperature_role="wall_hot"),
        ThermalNetworkNode(id="coolant_wall", label="T_wc", node_type="coolant_wall", temperature_role="wall_coolant"),
        ThermalNetworkNode(id="coolant_bulk", label="T_b,c", node_type="coolant_bulk", temperature_role="bulk"),
    )
    elements = [
        ThermalNetworkElement(
            id="R_g",
            label="R_g",
            element_type="gas_convection_resistance",
            from_node_id="hot_gas",
            to_node_id="hot_wall",
            value=None,
            unit="K/W",
            source="requires solve / initial estimate",
            note="Gas-side conductance is built from h_g * A_hot during the station solve.",
        ),
        ThermalNetworkElement(
            id="R_wall",
            label="R_wall",
            element_type="wall_conduction_resistance",
            from_node_id="hot_wall",
            to_node_id="coolant_wall",
            value=None,
            unit="K/W",
            source="requires solve / initial estimate",
            note="Wall conduction uses temperature-dependent material properties during the solve.",
        ),
        ThermalNetworkElement(
            id="R_c",
            label="R_c",
            element_type="coolant_convection_resistance",
            from_node_id="coolant_wall",
            to_node_id="coolant_bulk",
            value=None,
            unit="K/W",
            source="requires solve / initial estimate",
            note="Coolant-side conductance is built from h_c * A_cool during the station solve.",
        ),
    ]
    if ThermalMechanismType.RADIATION in segment.active_mechanisms:
        elements.append(
            ThermalNetworkElement(
                id="Q_rad",
                label="Q_rad",
                element_type="radiation_heat_source",
                from_node_id="hot_gas",
                to_node_id="hot_wall",
                value=None,
                unit="W",
                source="requires solve / initial estimate",
                note="Radiation is kept separate from Bartz convection and integrated as additive station heat.",
            )
        )
    return StationThermalNetwork(
        station_id=station_id,
        engine_station_index=sample.engine_station_index,
        coolant_path_index=sample.coolant_path_index,
        coolant_pass_id=sample.coolant_pass_id,
        region_label=sample.region_label,
        segment_node_id=segment.segment_node_id,
        segment_label=segment.segment_label,
        segment_model_type=segment.segment_model_type,
        active_mechanisms=segment.active_mechanisms,
        nodes=nodes,
        elements=tuple(elements),
        warnings=(),
        notes=(
            f"Range: {segment.range_label}",
            f"Integration rule: {_solver_scheme_label(effective_inputs.solver_settings.solver_type)}",
            "A_flow is used for Re and pressure drop; A_hot/A_cool are used for station conductance.",
        ),
        integration_rule_label=_solver_scheme_label(effective_inputs.solver_settings.solver_type),
        network_sketch="T_aw -- R_g -- T_wg -- R_wall -- T_wc -- R_c -- T_b,c",
        flow_direction=segment.flow_direction,
        hot_wall_area_m2=geometry.hot_wall_area_m2,
        coolant_wall_area_m2=geometry.coolant_wall_area_m2,
        flow_area_m2=geometry.area_annulus_m2,
        hydraulic_diameter_m=geometry.hydraulic_diameter_m,
    )


def _fingerprint_payload(payload: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _design_fingerprint(bundle: ExportBundle) -> str:
    contour_payload = [
        {
            "x_m": point.x_m,
            "radius_m": point.radius_m,
            "area_m2": point.area_m2,
        }
        for point in bundle.contour
    ]
    profile_payload = [
        {
            "x_m": point.x_m,
            "radius_m": point.radius_m,
            "area_m2": point.area_m2,
            "region": point.region,
        }
        for point in bundle.thermochemistry_profile
    ]
    return _fingerprint_payload(
        {
            "geometry": {
                "throat_area_m2": bundle.geometry.throat_area_m2,
                "throat_radius_m": bundle.geometry.throat_radius_m,
                "exit_area_m2": bundle.geometry.exit_area_m2,
                "exit_radius_m": bundle.geometry.exit_radius_m,
            },
            "contour": contour_payload,
            "thermochemistry_profile": profile_payload,
        }
    )


def _geometry_fingerprint(bundle: ExportBundle) -> str:
    return _fingerprint_payload(
        {
            "throat_area_m2": bundle.geometry.throat_area_m2,
            "throat_radius_m": bundle.geometry.throat_radius_m,
            "exit_area_m2": bundle.geometry.exit_area_m2,
            "exit_radius_m": bundle.geometry.exit_radius_m,
            "contour": [
                {
                    "x_m": point.x_m,
                    "radius_m": point.radius_m,
                    "area_m2": point.area_m2,
                }
                for point in bundle.contour
            ],
        }
    )


def _material_fingerprint(bundle: ExportBundle) -> str:
    inputs = bundle.inputs
    return _fingerprint_payload(
        {
            "liner_material": inputs.liner_material,
            "wall_thickness_m": inputs.wall_thickness_m,
            "wall_thickness_mode": getattr(inputs.wall_thickness_mode, "value", inputs.wall_thickness_mode),
            "closeout_enabled": getattr(inputs, "closeout_enabled", None),
            "closeout_thickness_m": getattr(inputs, "closeout_thickness_m", None),
            "closeout_material": getattr(inputs, "closeout_material", None),
        }
    )


def _manufacturing_fingerprint(bundle: ExportBundle) -> str:
    inputs = bundle.inputs
    return _fingerprint_payload(
        {
            "manufacturing_route": getattr(inputs.manufacturing_route, "value", inputs.manufacturing_route),
            "coolant_roughness_m": getattr(inputs, "coolant_roughness_m", None),
            "liner_material": inputs.liner_material,
            "closeout_material": getattr(inputs, "closeout_material", None),
        }
    )


def _cooling_layout_fingerprint(thermal_inputs: ThermalAnalysisInputs) -> str:
    return _fingerprint_payload(
        {
            "model_type": thermal_inputs.model_type.value,
            "flow_direction": thermal_inputs.flow_direction.value,
            "annulus_gap_m": thermal_inputs.annulus_gap_m,
            "coolant_roughness_m": thermal_inputs.coolant_roughness_m,
        }
    )


def _solver_settings_fingerprint(thermal_inputs: ThermalAnalysisInputs) -> str:
    solver_settings = thermal_inputs.solver_settings
    return _fingerprint_payload(
        {
            "solver_type": solver_settings.solver_type.value,
            "station_distribution_mode": solver_settings.station_distribution_mode.value,
            "pressure_mode": solver_settings.pressure_mode.value,
            "station_count": solver_settings.station_count,
            "station_tolerance": solver_settings.station_tolerance,
            "max_iterations_per_station": solver_settings.max_iterations_per_station,
            "relaxation_factor": solver_settings.relaxation_factor,
            "bartz_curvature_mode": thermal_inputs.bartz_throat_curvature_mode.value,
        }
    )


def _mechanism_settings_fingerprint(
    thermal_inputs: ThermalAnalysisInputs,
) -> str:
    return _fingerprint_payload(
        {
            "model_type": thermal_inputs.model_type.value,
            "flow_direction": thermal_inputs.flow_direction.value,
            "annulus_gap_m": thermal_inputs.annulus_gap_m,
            "coolant_roughness_m": thermal_inputs.coolant_roughness_m,
            "primary_nusselt_method": thermal_inputs.primary_coolant_nusselt_method.value,
            "coolant_type": thermal_inputs.coolant_type,
            "coolant_mass_flow_kg_per_s": thermal_inputs.coolant_mass_flow_kg_per_s,
            "coolant_inlet_temperature_k": thermal_inputs.coolant_inlet_temperature_k,
            "radiation_settings": {
                "enabled": thermal_inputs.radiation_settings.enabled,
                "model": thermal_inputs.radiation_settings.model.value,
                "wall_emissivity": thermal_inputs.radiation_settings.wall_emissivity,
                "gas_effective_emissivity": thermal_inputs.radiation_settings.gas_effective_emissivity,
                "participating_media_enabled": thermal_inputs.radiation_settings.participating_media_enabled,
                "participating_species_mode": thermal_inputs.radiation_settings.participating_species_mode.value,
                "optical_path_length_mode": thermal_inputs.radiation_settings.optical_path_length_mode.value,
                "co2_mole_fraction": thermal_inputs.radiation_settings.co2_mole_fraction,
                "h2o_mole_fraction": thermal_inputs.radiation_settings.h2o_mole_fraction,
                "soot_factor": thermal_inputs.radiation_settings.soot_factor,
            },
        }
    )


def thermal_network_build_is_stale(
    bundle: ExportBundle,
    thermal_inputs: ThermalAnalysisInputs,
    network_build: ThermalNetworkBuildResult | None,
) -> tuple[bool, tuple[str, ...]]:
    """Compare stored and current fingerprints to detect stale network builds."""

    if network_build is None:
        return True, ("R-Network has not been built yet.",)
    warnings: list[str] = []
    current_design_fingerprint = _design_fingerprint(bundle)
    current_solver_fingerprint = _solver_settings_fingerprint(thermal_inputs)
    current_mechanism_fingerprint = _mechanism_settings_fingerprint(thermal_inputs)
    if current_design_fingerprint != network_build.design_fingerprint:
        warnings.append("Committed geometry / contour / profile changed after the last network build.")
    if current_solver_fingerprint != network_build.solver_settings_fingerprint:
        warnings.append("Solver settings changed after the last network build.")
    if current_mechanism_fingerprint != network_build.mechanism_settings_fingerprint:
        warnings.append("Thermal setup, coolant or radiation settings changed after the last network build.")
    return bool(warnings), tuple(warnings)


def create_committed_thermal_network(
    bundle: ExportBundle,
    thermal_inputs: ThermalAnalysisInputs,
    network_build: ThermalNetworkBuildResult,
    *,
    notes: tuple[str, ...] = (),
) -> CommittedThermalNetwork:
    """Freeze one validated network build as the committed design-side artifact."""

    return CommittedThermalNetwork(
        build_id=network_build.build_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        design_fingerprint=_design_fingerprint(bundle),
        geometry_fingerprint=_geometry_fingerprint(bundle),
        material_fingerprint=_material_fingerprint(bundle),
        manufacturing_fingerprint=_manufacturing_fingerprint(bundle),
        cooling_layout_fingerprint=_cooling_layout_fingerprint(thermal_inputs),
        solver_mechanism_fingerprint=_fingerprint_payload(
            {
                "solver": _solver_settings_fingerprint(thermal_inputs),
                "mechanisms": _mechanism_settings_fingerprint(thermal_inputs),
            }
        ),
        network_build_result=network_build,
        status="committed",
        notes=notes,
    )


def committed_thermal_network_is_stale(
    bundle: ExportBundle,
    thermal_inputs: ThermalAnalysisInputs,
    committed_network: CommittedThermalNetwork | None,
) -> tuple[bool, tuple[str, ...]]:
    """Check whether the committed R-network still matches the active design context."""

    if committed_network is None:
        return True, ("No committed R-Network available.",)
    warnings: list[str] = []
    if _geometry_fingerprint(bundle) != committed_network.geometry_fingerprint:
        warnings.append("Committed contour or station grid changed after the R-Network was committed.")
    if _material_fingerprint(bundle) != committed_network.material_fingerprint:
        warnings.append("Material or wall-stack assumptions changed after the R-Network was committed.")
    if _manufacturing_fingerprint(bundle) != committed_network.manufacturing_fingerprint:
        warnings.append("Manufacturing assumptions changed after the R-Network was committed.")
    if _cooling_layout_fingerprint(thermal_inputs) != committed_network.cooling_layout_fingerprint:
        warnings.append("Cooling layout inputs changed after the R-Network was committed.")
    current_solver_mechanism = _fingerprint_payload(
        {
            "solver": _solver_settings_fingerprint(thermal_inputs),
            "mechanisms": _mechanism_settings_fingerprint(thermal_inputs),
        }
    )
    if current_solver_mechanism != committed_network.solver_mechanism_fingerprint:
        warnings.append("Solver or active thermal-mechanism settings changed after the R-Network was committed.")
    return bool(warnings), tuple(warnings)


def build_thermal_network(
    bundle: ExportBundle,
    thermal_inputs: ThermalAnalysisInputs,
) -> ThermalNetworkBuildResult:
    """Build the station-wise thermal network from the active annulus setup."""

    effective_inputs = replace(thermal_inputs)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        _ensure_valid_thermal_inputs(bundle, effective_inputs)
    except InputValidationError as exc:
        errors.extend(line for line in str(exc).splitlines() if line.strip())
    scenario = thermal_scenario_from_inputs(effective_inputs)
    precalculation = _precalculate_thermal_model(bundle, scenario)
    assignment = _build_default_segment_assignment(effective_inputs)
    station_networks: list[StationThermalNetwork] = []
    for station_id, sample in enumerate(precalculation.station_samples):
        station_networks.append(
            _build_station_thermal_network(station_id, sample, assignment, effective_inputs)
        )
    status = "ok"
    if errors:
        status = "error"
    elif warnings:
        status = "warning"
    summary = (
        f"Annulus baseline setup, 1 segment, "
        f"{len(station_networks)} station network(s), builder AnnulusStationNetworkBuilder"
    )
    return ThermalNetworkBuildResult(
        status=status,
        build_id=f"network-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        station_networks=tuple(station_networks),
        segment_assignments=(assignment,),
        warnings=tuple(dict.fromkeys(warnings)),
        errors=tuple(dict.fromkeys(errors)),
        summary=summary,
        setup_summary=_build_network_setup_summary(effective_inputs),
        active_station_network_builder="AnnulusStationNetworkBuilder",
        design_fingerprint=_design_fingerprint(bundle),
        solver_settings_fingerprint=_solver_settings_fingerprint(effective_inputs),
        mechanism_settings_fingerprint=_mechanism_settings_fingerprint(effective_inputs),
        effective_inputs=effective_inputs,
        station_samples=tuple(precalculation.station_samples),
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

    # The legacy one-call fallback intentionally remains annulus-only. Future
    # segment models must enter through the explicit graph -> R-network build
    # path so the GUI never hides a different solver interpretation than the
    # one shown in the cooling circuit preview.
    _ensure_valid_thermal_inputs(bundle, thermal_inputs)
    network_build = build_thermal_network(bundle, thermal_inputs)
    return run_thermal_analysis_from_network(bundle, thermal_inputs, network_build)


def run_thermal_analysis_from_network(
    bundle: ExportBundle,
    thermal_inputs: ThermalAnalysisInputs,
    network_build: ThermalNetworkBuildResult,
) -> ThermalAnalysisResult:
    """Run Thermal Analysis only from an already built network preview/result."""

    stale, stale_notes = thermal_network_build_is_stale(
        bundle,
        thermal_inputs,
        network_build,
    )
    if network_build.errors:
        raise InputValidationError(list(network_build.errors))
    if stale:
        raise InputValidationError(
            ["R-Network is stale. Rebuild before solving.", *stale_notes]
        )
    if network_build.status == "error":
        raise InputValidationError(["R-Network is not valid. Rebuild and inspect the reported errors."])
    scenario = thermal_scenario_from_inputs(network_build.effective_inputs)
    return _run_annulus_baseline(bundle, scenario, prebuilt_network=network_build)


def run_thermal_scenario(
    bundle: ExportBundle,
    scenario: ThermalScenario,
) -> ThermalAnalysisResult:
    """Run the active thermal scenario through the current annulus MVP backend."""

    _ensure_valid_thermal_inputs(bundle, scenario.global_conditions)
    return _run_annulus_baseline(bundle, scenario)


def _run_annulus_baseline(
    bundle: ExportBundle,
    scenario: ThermalScenario,
    *,
    prebuilt_network: ThermalNetworkBuildResult | None = None,
) -> ThermalAnalysisResult:
    """Execute the current annulus baseline using the modular scenario shell."""

    thermal_inputs = prebuilt_network.effective_inputs if prebuilt_network is not None else scenario.global_conditions
    precalculation = _precalculate_thermal_model(bundle, thermal_scenario_from_inputs(thermal_inputs))
    if prebuilt_network is not None:
        precalculation.station_samples = list(prebuilt_network.station_samples)
        extra_notes = [
            f"R-network build id: {prebuilt_network.build_id}",
            f"R-network status: {prebuilt_network.status}",
            f"R-network builder: {prebuilt_network.active_station_network_builder}",
        ]
        extra_notes.extend(prebuilt_network.warnings)
        precalculation.bundle_status_notes = tuple(
            dict.fromkeys((*extra_notes, *precalculation.bundle_status_notes))
        )
    station_samples = precalculation.station_samples
    bundle_status_notes = precalculation.bundle_status_notes
    wall_temperature_limit_k = precalculation.wall_temperature_limit_k
    wall_thickness_m = precalculation.wall_thickness_m
    wall_material_id = precalculation.wall_material_id

    coolant_mass_flow = thermal_inputs.coolant_mass_flow_kg_per_s or 0.0
    coolant_temperature_in_k = thermal_inputs.coolant_inlet_temperature_k
    station_results: list[ThermalStationResult] = []
    reference_coolant_pressure_estimate_pa = precalculation.reference_coolant_pressure_estimate_pa

    for station_index, sample in enumerate(station_samples):
        station_geometry = _build_annulus_geometry(sample, thermal_inputs.annulus_gap_m)
        _representative_gas_side_properties, gas_temperature_source = _gas_side_properties(
            bundle,
            sample,
            thermal_inputs.bartz_throat_curvature_mode,
        )
        station_solution = _solve_station_heat_balance(
            bundle=bundle,
            sample=sample,
            station_geometry=station_geometry,
            flow_direction=thermal_inputs.flow_direction,
            curvature_mode=thermal_inputs.bartz_throat_curvature_mode,
            coolant_temperature_in_k=coolant_temperature_in_k,
            coolant_type=thermal_inputs.coolant_type,
            coolant_mass_flow_kg_per_s=coolant_mass_flow,
            local_pressure_estimate_pa=reference_coolant_pressure_estimate_pa,
            wall_thickness_m=wall_thickness_m,
            wall_material_id=wall_material_id,
            coolant_roughness_m=thermal_inputs.coolant_roughness_m,
            primary_coolant_nusselt_method=thermal_inputs.primary_coolant_nusselt_method,
            solver_settings=thermal_inputs.solver_settings,
            radiation_settings=thermal_inputs.radiation_settings,
            previous_station_result=station_results[-1] if station_results else None,
        )
        thermal_margin_k = wall_temperature_limit_k - station_solution.wall_temperature_hot_gas_side_k
        status_messages = list(station_solution.status_notes)
        if station_index == 0:
            status_messages.extend(bundle_status_notes)
        status_messages.append(f"station reference: {sample.reference_reason}")
        if gas_temperature_source != "adiabatic-wall":
            status_messages.append("gas-side recovery placeholder")
        if thermal_margin_k < 0.0:
            status_messages.append("wall temperature above material screening limit")
        status_notes, warning_notes = _split_station_notes(status_messages)

        station_results.append(
            ThermalStationResult(
                station_index=station_index,
                x_start_m=sample.x_start_m,
                x_end_m=sample.x_end_m,
                x_mid_m=sample.x_mid_m,
                r_inner_m=station_geometry.r_inner_m,
                r_outer_m=station_geometry.r_outer_m,
                r_mean_m=station_geometry.r_mean_m,
                area_gas_m2=sample.area_ref_m2,
                area_hot_m2=station_geometry.hot_wall_area_m2,
                area_annulus_m2=station_geometry.area_annulus_m2,
                hydraulic_diameter_m=station_geometry.hydraulic_diameter_m,
                recovery_temperature_k=station_solution.recovery_temperature_k,
                h_g_w_per_m2_k=station_solution.h_g_w_per_m2_k,
                h_c_w_per_m2_k=station_solution.h_c_w_per_m2_k,
                q_station_w=station_solution.q_station_w,
                q_hot_w_per_m2=station_solution.q_hot_w_per_m2,
                coolant_temperature_in_k=coolant_temperature_in_k,
                coolant_temperature_bulk_k=station_solution.coolant_temperature_bulk_k,
                coolant_temperature_out_k=station_solution.coolant_temperature_out_k,
                wall_temperature_hot_gas_side_k=station_solution.wall_temperature_hot_gas_side_k,
                wall_temperature_coolant_side_k=station_solution.wall_temperature_coolant_side_k,
                wall_delta_t_k=station_solution.wall_delta_t_k,
                required_pressure_out_pa=None,
                required_pressure_in_pa=None,
                pressure_drop_station_pa=station_solution.pressure_drop_station_pa,
                reynolds_coolant=station_solution.reynolds_coolant,
                coolant_prandtl_number=station_solution.prandtl_coolant,
                coolant_cp_j_per_kg_k=station_solution.coolant_cp_j_per_kg_k,
                coolant_viscosity_pa_s=station_solution.coolant_viscosity_pa_s,
                nusselt_coolant=station_solution.nusselt_coolant,
                nusselt_coolant_method=station_solution.nusselt_coolant_method,
                nusselt_dittus_boelter=station_solution.nusselt_dittus_boelter,
                nusselt_sieder_tate=station_solution.nusselt_sieder_tate,
                nusselt_gnielinski=station_solution.nusselt_gnielinski,
                nusselt_spread_fraction=station_solution.nusselt_spread_fraction,
                friction_factor=station_solution.friction_factor,
                h_c_dittus_boelter_w_per_m2_k=station_solution.h_c_dittus_boelter_w_per_m2_k,
                h_c_sieder_tate_w_per_m2_k=station_solution.h_c_sieder_tate_w_per_m2_k,
                h_c_gnielinski_w_per_m2_k=station_solution.h_c_gnielinski_w_per_m2_k,
                thermal_margin_k=thermal_margin_k,
                q_conv_w_per_m2=station_solution.q_conv_w_per_m2,
                q_rad_w_per_m2=station_solution.q_rad_w_per_m2,
                q_total_w_per_m2=station_solution.q_total_w_per_m2,
                q_radiation_station_w=station_solution.q_radiation_station_w,
                radiation_temperature_k=station_solution.radiation_temperature_k,
                gas_effective_emissivity=station_solution.gas_effective_emissivity,
                wall_emissivity=station_solution.wall_emissivity,
                optical_path_length_m=station_solution.optical_path_length_m,
                radiation_model_note=station_solution.radiation_model_note,
                participating_species_mode=station_solution.participating_species_mode,
                participating_species_used=station_solution.participating_species_used,
                x_ref_m=sample.x_ref_m,
                r_ref_m=sample.radius_ref_m,
                area_ref_m2=sample.area_ref_m2,
                eps_ref=sample.eps_ref,
                station_reference_label=sample.reference_label,
                station_reference_reason=sample.reference_reason,
                x_engine_start_m=sample.x_start_m,
                x_engine_end_m=sample.x_end_m,
                x_engine_mid_m=sample.x_mid_m,
                r_start_m=sample.radius_start_m,
                r_mid_m=sample.radius_mid_m,
                r_end_m=sample.radius_end_m,
                eps_start=sample.eps_start,
                eps_mid=sample.eps_mid,
                eps_end=sample.eps_end,
                region_label=sample.region_label,
                engine_station_index=sample.engine_station_index,
                coolant_path_index=sample.coolant_path_index,
                coolant_pass_id=sample.coolant_pass_id,
                coolant_bulk_temperature_reference_label=station_solution.coolant_bulk_temperature_reference_label,
                coolant_bulk_temperature_reference_reason=station_solution.coolant_bulk_temperature_reference_reason,
                coolant_wall_viscosity_pa_s=station_solution.coolant_wall_viscosity_pa_s,
                sieder_tate_viscosity_ratio=station_solution.sieder_tate_viscosity_ratio,
                sieder_tate_correction_factor=station_solution.sieder_tate_correction_factor,
                status_summary=_join_station_note_group(status_notes, empty_value="ok"),
                warning_summary=_join_station_note_group(warning_notes, empty_value="--"),
                status=", ".join(status_messages) if status_messages else "ok",
                status_notes=status_notes,
                warning_notes=warning_notes,
                iterations=station_solution.iterations,
                converged=station_solution.converged,
                residual_k=station_solution.residual_k,
                solver_scheme_label=station_solution.solver_scheme_label,
                conductance_rule_label=station_solution.conductance_rule_label,
                gas_conductance_w_per_k=station_solution.gas_conductance_w_per_k,
                coolant_conductance_w_per_k=station_solution.coolant_conductance_w_per_k,
                gas_resistance_k_per_w=station_solution.gas_resistance_k_per_w,
                wall_resistance_k_per_w=station_solution.wall_resistance_k_per_w,
                coolant_resistance_k_per_w=station_solution.coolant_resistance_k_per_w,
                coolant_flow_area_m2=station_solution.coolant_flow_area_m2,
                coolant_wall_area_m2=station_solution.coolant_wall_area_m2,
            )
        )

        coolant_temperature_in_k = station_solution.coolant_temperature_out_k

    pressure_summary = _reconstruct_pressures(
        station_results,
        chamber_pressure_pa=bundle.inputs.chamber_pressure_pa,
        thermal_inputs=thermal_inputs,
    )
    _apply_mechanical_screening(
        station_results,
        station_samples=station_samples,
        bundle=bundle,
        thermal_inputs=thermal_inputs,
        wall_thickness_m=wall_thickness_m,
    )
    summary = _build_summary(station_results, scenario, pressure_summary)
    return ThermalAnalysisResult(
        inputs=thermal_inputs,
        summary=summary,
        stations=station_results,
    )


def _precalculate_thermal_model(
    bundle: ExportBundle,
    scenario: ThermalScenario,
) -> _ThermalPrecalculation:
    """Prebuild the active annulus resistance path from the selected coolant circuit."""

    thermal_inputs = scenario.global_conditions
    station_samples = _build_station_samples_for_flow_direction(
        bundle,
        thermal_inputs.solver_settings,
        thermal_inputs.flow_direction,
    )
    if thermal_inputs.flow_direction is CoolingFlowDirection.NOZZLE_TO_INJECTOR:
        station_samples = list(reversed(station_samples))
        for coolant_path_index, sample in enumerate(station_samples):
            sample.coolant_path_index = coolant_path_index
    bundle_status_notes = _bundle_status_notes(
        bundle,
        thermal_inputs.solver_settings,
        station_sample_count=len(station_samples),
    )
    precalc_note = "thermal precalculation: annulus resistance path built from the active single-pass coolant circuit"
    if precalc_note not in bundle_status_notes:
        bundle_status_notes = (precalc_note, *bundle_status_notes)
    return _ThermalPrecalculation(
        scenario=scenario,
        effective_inputs=thermal_inputs,
        station_samples=station_samples,
        bundle_status_notes=bundle_status_notes,
        wall_temperature_limit_k=_wall_material_screening_limit_k(bundle.inputs.liner_material),
        wall_thickness_m=_resolved_wall_thickness_m(bundle),
        wall_material_id=bundle.inputs.liner_material,
        reference_coolant_pressure_estimate_pa=_reference_coolant_pressure_estimate_pa(bundle, thermal_inputs),
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
    radiation_settings = thermal_inputs.radiation_settings
    if radiation_settings.enabled:
        if not 0.0 <= radiation_settings.wall_emissivity <= 1.0:
            errors.append("Wall emissivity must be between 0 and 1.")
        if not 0.0 <= radiation_settings.gas_effective_emissivity <= 1.0:
            errors.append("Gas effective emissivity must be between 0 and 1.")
        if radiation_settings.soot_factor < 0.0:
            errors.append("Soot factor must not be negative.")
        if (
            radiation_settings.fixed_radiation_heat_flux_w_per_m2 is not None
            and radiation_settings.fixed_radiation_heat_flux_w_per_m2 < 0.0
        ):
            errors.append("Fixed radiation heat flux must not be negative.")
        use_participating_media = (
            radiation_settings.model is RadiationModelType.PARTICIPATING_MEDIA_EFFECTIVE_EMISSIVITY
            or radiation_settings.participating_media_enabled
        )
        if (
            use_participating_media
            and radiation_settings.optical_path_length_mode is OpticalPathLengthMode.USER_FIXED
            and (
                radiation_settings.user_optical_path_length_m is None
                or radiation_settings.user_optical_path_length_m <= 0.0
            )
        ):
            errors.append("User optical path length must be greater than 0 m.")
        if (
            radiation_settings.user_optical_path_length_m is not None
            and radiation_settings.user_optical_path_length_m <= 0.0
        ):
            errors.append("User optical path length must be greater than 0 m.")
        for label, value in (
            ("CO2 mole fraction", radiation_settings.co2_mole_fraction),
            ("H2O mole fraction", radiation_settings.h2o_mole_fraction),
        ):
            if value is not None and not 0.0 <= value <= 1.0:
                errors.append(f"{label} must be between 0 and 1.")
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


def _resolve_station_evaluation_point(
    solver_settings: SolverSettings,
) -> StationEvaluationPoint:
    """Return the effective local geometry/gas reference point for the station."""

    if solver_settings.solver_type is ThermalSolverType.FORWARD_EULER:
        return StationEvaluationPoint.COOLANT_UPSTREAM
    if solver_settings.solver_type is ThermalSolverType.BACKWARD_EULER:
        return StationEvaluationPoint.COOLANT_DOWNSTREAM
    return StationEvaluationPoint.MIDPOINT


def _resolve_coolant_bulk_temperature_reference(
    solver_settings: SolverSettings,
) -> CoolantBulkTemperatureReference:
    """Return the effective coolant bulk temperature rule used for properties."""

    if solver_settings.solver_type is ThermalSolverType.FORWARD_EULER:
        return CoolantBulkTemperatureReference.COOLANT_INLET
    if solver_settings.solver_type is ThermalSolverType.BACKWARD_EULER:
        return CoolantBulkTemperatureReference.COOLANT_OUTLET
    if solver_settings.solver_type is ThermalSolverType.CRANK_NICOLSON:
        return CoolantBulkTemperatureReference.ITERATED_MEAN
    return CoolantBulkTemperatureReference.ITERATED_MEAN


def _select_station_reference_state(
    *,
    station_start_state: _StationReferenceState,
    station_mid_state: _StationReferenceState,
    station_end_state: _StationReferenceState,
    flow_direction: CoolingFlowDirection,
    station_evaluation_point: StationEvaluationPoint,
    solver_settings: SolverSettings,
) -> tuple[_StationReferenceState, str, str]:
    """Pick the explicit local station reference for geometry and gas-side data."""

    if station_evaluation_point is StationEvaluationPoint.SOLVER_DEFAULT:
        station_evaluation_point = _resolve_station_evaluation_point(solver_settings)
    if station_evaluation_point is StationEvaluationPoint.MIDPOINT:
        return station_mid_state, "midpoint", "midpoint reference for geometry and gas-side properties"
    if station_evaluation_point is StationEvaluationPoint.TRAPEZOIDAL:
        return (
            station_mid_state,
            "midpoint",
            "trapezoidal start/end averaging planned; midpoint reference used for this MVP",
        )
    if station_evaluation_point is StationEvaluationPoint.COOLANT_UPSTREAM:
        if flow_direction is CoolingFlowDirection.INJECTOR_TO_NOZZLE:
            return (
                station_start_state,
                "coolant upstream",
                "coolant-upstream reference mapped to geometric station start",
            )
        return (
            station_end_state,
            "coolant upstream",
            "coolant-upstream reference mapped to geometric station end",
        )
    if flow_direction is CoolingFlowDirection.INJECTOR_TO_NOZZLE:
        return (
            station_end_state,
            "coolant downstream",
            "coolant-downstream reference mapped to geometric station end",
        )
    return (
        station_start_state,
        "coolant downstream",
        "coolant-downstream reference mapped to geometric station start",
    )


def _build_station_samples_for_flow_direction(
    bundle: ExportBundle,
    solver_settings: SolverSettings,
    flow_direction: CoolingFlowDirection,
) -> list[_SamplePoint]:
    if solver_settings.station_distribution_mode is StationDistributionMode.CEA_PROFILE:
        samples = _build_station_samples_from_profile(bundle, solver_settings, flow_direction)
    else:
        samples = _build_station_samples_manual(bundle, solver_settings, flow_direction)
    for coolant_path_index, sample in enumerate(samples):
        sample.coolant_path_index = coolant_path_index
    return samples


def _build_station_samples_manual(
    bundle: ExportBundle,
    solver_settings: SolverSettings,
    flow_direction: CoolingFlowDirection,
) -> list[_SamplePoint]:
    contour = bundle.contour
    profile = bundle.thermochemistry_profile
    cumulative_lengths = _cumulative_arc_lengths(contour)
    total_length = cumulative_lengths[-1]
    if total_length <= 0.0:
        raise InputValidationError(["Current Design contour length is invalid for thermal station generation."])

    samples: list[_SamplePoint] = []
    throat_area_m2 = max(bundle.geometry.throat_area_m2, 1.0e-12)
    station_evaluation_point = _resolve_station_evaluation_point(solver_settings)
    station_count = solver_settings.station_count
    for index in range(station_count):
        s_start = total_length * index / station_count
        s_end = total_length * (index + 1) / station_count
        s_mid = 0.5 * (s_start + s_end)
        x_start_m, radius_start_m, area_start_m2 = _interpolate_contour_at_s(contour, cumulative_lengths, s_start)
        x_end_m, radius_end_m, area_end_m2 = _interpolate_contour_at_s(contour, cumulative_lengths, s_end)
        x_mid_m, radius_mid_m, area_mid_m2 = _interpolate_contour_at_s(contour, cumulative_lengths, s_mid)
        start_state = _StationReferenceState(
            x_m=x_start_m,
            radius_m=radius_start_m,
            area_m2=area_start_m2,
            eps=area_start_m2 / throat_area_m2,
            profile_point=_nearest_profile_point(profile, x_start_m),
        )
        mid_state = _StationReferenceState(
            x_m=x_mid_m,
            radius_m=radius_mid_m,
            area_m2=area_mid_m2,
            eps=area_mid_m2 / throat_area_m2,
            profile_point=_nearest_profile_point(profile, x_mid_m),
        )
        end_state = _StationReferenceState(
            x_m=x_end_m,
            radius_m=radius_end_m,
            area_m2=area_end_m2,
            eps=area_end_m2 / throat_area_m2,
            profile_point=_nearest_profile_point(profile, x_end_m),
        )
        reference_state, reference_label, reference_reason = _select_station_reference_state(
            station_start_state=start_state,
            station_mid_state=mid_state,
            station_end_state=end_state,
            flow_direction=flow_direction,
            station_evaluation_point=station_evaluation_point,
            solver_settings=solver_settings,
        )
        samples.append(
            _SamplePoint(
                x_start_m=x_start_m,
                radius_start_m=radius_start_m,
                area_start_m2=area_start_m2,
                eps_start=start_state.eps,
                x_mid_m=x_mid_m,
                radius_mid_m=radius_mid_m,
                area_mid_m2=area_mid_m2,
                eps_mid=mid_state.eps,
                x_end_m=x_end_m,
                radius_end_m=radius_end_m,
                area_end_m2=area_end_m2,
                eps_end=end_state.eps,
                x_ref_m=reference_state.x_m,
                radius_ref_m=reference_state.radius_m,
                area_ref_m2=reference_state.area_m2,
                eps_ref=reference_state.eps,
                reference_label=reference_label,
                reference_reason=reference_reason,
                profile_point_start=start_state.profile_point,
                profile_point_mid=mid_state.profile_point,
                profile_point_end=end_state.profile_point,
                profile_point_ref=reference_state.profile_point,
                ds_m=s_end - s_start,
                engine_station_index=index,
            )
        )
    return samples


def _build_station_samples_from_profile(
    bundle: ExportBundle,
    solver_settings: SolverSettings,
    flow_direction: CoolingFlowDirection,
) -> list[_SamplePoint]:
    """Use the committed thermochemistry-profile stations as the thermal grid.

    This mode keeps the cooling table aligned with the existing CEA-derived
    thermochemistry/profile sampling rather than redistributing the contour into
    a new manual station count.
    """

    profile = bundle.thermochemistry_profile
    if len(profile) < 2:
        raise InputValidationError(["CEA-profile station mode requires at least two thermochemistry profile points."])

    throat_area_m2 = max(bundle.geometry.throat_area_m2, 1.0e-12)
    station_evaluation_point = _resolve_station_evaluation_point(solver_settings)
    samples: list[_SamplePoint] = []
    for left_point, right_point in zip(profile, profile[1:]):
        x_start_m = left_point.x_m
        x_end_m = right_point.x_m
        x_mid_m = 0.5 * (x_start_m + x_end_m)
        radius_mid_m = 0.5 * (left_point.radius_m + right_point.radius_m)
        area_mid_m2 = 0.5 * (left_point.area_m2 + right_point.area_m2)
        ds_m = math.hypot(
            right_point.x_m - left_point.x_m,
            right_point.radius_m - left_point.radius_m,
        )
        midpoint_profile = _average_profile_point(left_point, right_point)
        start_state = _StationReferenceState(
            x_m=x_start_m,
            radius_m=left_point.radius_m,
            area_m2=left_point.area_m2,
            eps=left_point.area_m2 / throat_area_m2,
            profile_point=left_point,
        )
        mid_state = _StationReferenceState(
            x_m=x_mid_m,
            radius_m=radius_mid_m,
            area_m2=area_mid_m2,
            eps=area_mid_m2 / throat_area_m2,
            profile_point=midpoint_profile,
        )
        end_state = _StationReferenceState(
            x_m=x_end_m,
            radius_m=right_point.radius_m,
            area_m2=right_point.area_m2,
            eps=right_point.area_m2 / throat_area_m2,
            profile_point=right_point,
        )
        reference_state, reference_label, reference_reason = _select_station_reference_state(
            station_start_state=start_state,
            station_mid_state=mid_state,
            station_end_state=end_state,
            flow_direction=flow_direction,
            station_evaluation_point=station_evaluation_point,
            solver_settings=solver_settings,
        )
        samples.append(
            _SamplePoint(
                x_start_m=x_start_m,
                radius_start_m=left_point.radius_m,
                area_start_m2=left_point.area_m2,
                eps_start=start_state.eps,
                x_mid_m=x_mid_m,
                radius_mid_m=radius_mid_m,
                area_mid_m2=area_mid_m2,
                eps_mid=mid_state.eps,
                x_end_m=x_end_m,
                radius_end_m=right_point.radius_m,
                area_end_m2=right_point.area_m2,
                eps_end=end_state.eps,
                x_ref_m=reference_state.x_m,
                radius_ref_m=reference_state.radius_m,
                area_ref_m2=reference_state.area_m2,
                eps_ref=reference_state.eps,
                reference_label=reference_label,
                reference_reason=reference_reason,
                profile_point_start=left_point,
                profile_point_mid=midpoint_profile,
                profile_point_end=right_point,
                profile_point_ref=reference_state.profile_point,
                ds_m=ds_m,
                engine_station_index=left_point.station_index,
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
    target_x_m: float,
) -> ThermochemistryProfilePoint | None:
    """Return the nearest thermochemistry profile point for a manual station.

    Manual thermal stations do not require a one-to-one contour/profile point
    count. The nearest profile point is chosen by axial location so preview or
    remapped profiles can still provide local gas properties without silently
    falling back just because the grids differ in length.
    """

    if not profile:
        return None
    return min(profile, key=lambda point: abs(point.x_m - target_x_m))


def _bundle_status_notes(
    bundle: ExportBundle,
    solver_settings: SolverSettings,
    *,
    station_sample_count: int,
) -> tuple[str, ...]:
    """Return bundle-level guard notes for the first station status field."""

    notes: list[str] = []
    contour = bundle.contour
    profile = bundle.thermochemistry_profile
    if contour:
        notes.append(
            "bundle debug: "
            f"contour pts={len(contour)}, profile pts={len(profile)}, station samples={station_sample_count}, "
            f"start=({contour[0].x_m:.4f},{contour[0].radius_m:.4f}) m, "
            f"end=({contour[-1].x_m:.4f},{contour[-1].radius_m:.4f}) m, "
            f"throat r={bundle.geometry.throat_radius_m:.4f} m"
        )
    if solver_settings.station_distribution_mode is StationDistributionMode.CEA_PROFILE:
        notes.extend(_cea_profile_alignment_notes(bundle))
    return tuple(notes)


def _cea_profile_alignment_notes(bundle: ExportBundle) -> tuple[str, ...]:
    """Return warnings if the thermochemistry profile looks stale against the contour."""

    contour = bundle.contour
    profile = bundle.thermochemistry_profile
    if not contour or not profile:
        return ()

    notes: list[str] = []
    contour_x_span = abs(contour[-1].x_m - contour[0].x_m)
    x_tolerance_m = max(1.0e-6, 0.02 * contour_x_span)
    if abs(profile[0].x_m - contour[0].x_m) > x_tolerance_m or abs(profile[-1].x_m - contour[-1].x_m) > x_tolerance_m:
        notes.append(
            "CEA-profile alignment warning: profile start/end x does not match the active contour closely."
        )

    contour_min_radius_m = min(point.radius_m for point in contour)
    contour_max_radius_m = max(point.radius_m for point in contour)
    profile_min_radius_m = min(point.radius_m for point in profile)
    profile_max_radius_m = max(point.radius_m for point in profile)
    radius_scale_m = max(contour_max_radius_m - contour_min_radius_m, contour_max_radius_m, 1.0e-9)
    if (
        abs(profile_min_radius_m - contour_min_radius_m) > 0.05 * radius_scale_m
        or abs(profile_max_radius_m - contour_max_radius_m) > 0.05 * radius_scale_m
    ):
        notes.append(
            "CEA-profile alignment warning: profile radius range differs noticeably from the active contour."
        )

    if len(profile) != len(contour):
        notes.append(
            "CEA-profile alignment warning: profile and contour point counts differ; verify that the profile was remapped from the current contour."
        )
    return tuple(notes)


def _build_annulus_geometry(sample: _SamplePoint, annulus_gap_m: float) -> AnnulusCoolingGeometry:
    r_inner = sample.radius_m
    r_outer = r_inner + annulus_gap_m
    r_mean = 0.5 * (r_inner + r_outer)
    area_annulus = math.pi * (r_outer**2 - r_inner**2)
    wetted_perimeter = 2.0 * math.pi * (r_inner + r_outer)
    hydraulic_diameter = 4.0 * area_annulus / max(wetted_perimeter, 1.0e-12)
    hot_wall_area = 2.0 * math.pi * r_inner * sample.ds_m
    coolant_wall_area = 2.0 * math.pi * r_outer * sample.ds_m
    wall_mean_area = 2.0 * math.pi * r_mean * sample.ds_m
    return AnnulusCoolingGeometry(
        r_inner_m=r_inner,
        r_outer_m=r_outer,
        r_mean_m=r_mean,
        area_annulus_m2=area_annulus,
        wetted_perimeter_m=wetted_perimeter,
        hydraulic_diameter_m=hydraulic_diameter,
        hot_wall_area_m2=hot_wall_area,
        coolant_wall_area_m2=coolant_wall_area,
        wall_mean_area_m2=wall_mean_area,
    )


def _build_station_subpoints(
    sample: _SamplePoint,
    annulus_gap_m: float,
) -> dict[str, _StationSubpoint]:
    """Build start/mid/end subpoints with explicit flow and heat-transfer areas."""

    def make_subpoint(name: str, x_m: float, radius_m: float, area_m2: float, eps: float, profile_point: ThermochemistryProfilePoint | None) -> _StationSubpoint:
        geometry = _build_annulus_geometry(
            _SamplePoint(
                x_start_m=sample.x_start_m,
                radius_start_m=sample.radius_start_m,
                area_start_m2=sample.area_start_m2,
                eps_start=sample.eps_start,
                x_mid_m=sample.x_mid_m,
                radius_mid_m=sample.radius_mid_m,
                area_mid_m2=sample.area_mid_m2,
                eps_mid=sample.eps_mid,
                x_end_m=sample.x_end_m,
                radius_end_m=sample.radius_end_m,
                area_end_m2=sample.area_end_m2,
                eps_end=sample.eps_end,
                x_ref_m=x_m,
                radius_ref_m=radius_m,
                area_ref_m2=area_m2,
                eps_ref=eps,
                reference_label=name,
                reference_reason=f"{name} subpoint",
                profile_point_start=sample.profile_point_start,
                profile_point_mid=sample.profile_point_mid,
                profile_point_end=sample.profile_point_end,
                profile_point_ref=profile_point,
                ds_m=sample.ds_m,
                engine_station_index=sample.engine_station_index,
                coolant_path_index=sample.coolant_path_index,
                coolant_pass_id=sample.coolant_pass_id,
            ),
            annulus_gap_m,
        )
        return _StationSubpoint(
            name=name,
            x_m=x_m,
            radius_m=radius_m,
            r_outer_m=geometry.r_outer_m,
            r_mean_m=geometry.r_mean_m,
            area_gas_m2=area_m2,
            eps=eps,
            coolant_flow_area_m2=geometry.area_annulus_m2,
            hot_wall_area_m2=geometry.hot_wall_area_m2,
            coolant_wall_area_m2=geometry.coolant_wall_area_m2,
            wall_mean_area_m2=geometry.wall_mean_area_m2,
            hydraulic_diameter_m=geometry.hydraulic_diameter_m,
            profile_point=profile_point,
        )

    return {
        "start": make_subpoint(
            "start",
            sample.x_start_m,
            sample.radius_start_m,
            sample.area_start_m2,
            sample.eps_start,
            sample.profile_point_start,
        ),
        "mid": make_subpoint(
            "mid",
            sample.x_mid_m,
            sample.radius_mid_m,
            sample.area_mid_m2,
            sample.eps_mid,
            sample.profile_point_mid,
        ),
        "end": make_subpoint(
            "end",
            sample.x_end_m,
            sample.radius_end_m,
            sample.area_end_m2,
            sample.eps_end,
            sample.profile_point_end,
        ),
    }


def _gas_side_properties(
    bundle: ExportBundle,
    sample: _SamplePoint,
    curvature_mode: BartzThroatCurvatureMode,
) -> tuple[_GasSideProperties, str]:
    return _gas_side_properties_from_profile_point(
        bundle,
        sample.profile_point,
        curvature_mode,
    )


def _gas_side_properties_from_profile_point(
    bundle: ExportBundle,
    profile_point: ThermochemistryProfilePoint | None,
    curvature_mode: BartzThroatCurvatureMode,
) -> tuple[_GasSideProperties, str]:
    """Collect one gas-side property set from existing CEA/profile output.

    The thermal-analysis module should not recreate gas transport properties
    that AstraForge already gets from RocketCEA. This helper therefore reuses
    the local thermochemistry-profile state whenever possible and only falls
    back to the bundle-level thermochemistry result when a profile field is not
    available yet.
    """

    state = profile_point.state if profile_point is not None else None
    recovery_temperature_k = _first_positive(
        getattr(state, "adiabatic_wall_temperature_k", None),
        getattr(state, "temperature_k", None),
        bundle.thermochemistry.chamber_temperature_k,
        default_value=1_200.0,
    )
    gas_temperature_source = (
        "adiabatic-wall"
        if getattr(state, "adiabatic_wall_temperature_k", None) not in {None, 0.0}
        else "fallback"
    )
    return (
        _GasSideProperties(
            cp_j_per_kg_k=_first_positive(
                getattr(state, "cp_j_per_kg_k", None),
                bundle.thermochemistry.cp_j_per_kg_k,
                default_value=3_200.0,
            ),
            viscosity_pa_s=_first_positive(
                getattr(state, "viscosity_pa_s", None),
                bundle.thermochemistry.viscosity_pa_s,
                default_value=8.0e-5,
            ),
            prandtl_number=_first_positive(
                getattr(state, "prandtl_number", None),
                bundle.thermochemistry.prandtl_number,
                default_value=0.7,
            ),
            gamma=_first_positive(
                getattr(state, "gamma", None),
                bundle.thermochemistry.gamma,
                default_value=1.2,
            ),
            mach_number=max(getattr(state, "mach_number", 0.0) or 0.0, 0.0),
            local_gas_temperature_k=_first_positive(
                getattr(state, "temperature_k", None),
                bundle.thermochemistry.chamber_temperature_k,
                default_value=3_200.0,
            ),
            recovery_temperature_k=recovery_temperature_k,
            chamber_temperature_k=max(bundle.thermochemistry.chamber_temperature_k, 1.0),
            throat_curvature_radius_m=_resolved_throat_curvature_radius_m(bundle, curvature_mode),
            throat_curvature_mode=curvature_mode,
        ),
        gas_temperature_source,
    )


def _reference_coolant_pressure_estimate_pa(
    bundle: ExportBundle,
    thermal_inputs: ThermalAnalysisInputs,
) -> float:
    """Return a simple local pressure estimate for coolant-property lookup.

    The current MVP now reads coolant properties from editable f(T,p) tables.
    This pressure estimate is still simple and station-global, but it already
    travels through the same solver path a later fully coupled pressure-
    dependent property model will use.
    """

    if (
        thermal_inputs.solver_settings.pressure_mode is PressureCalculationMode.FORWARD_PUMP_CHECK
        and thermal_inputs.pump_discharge_pressure_pa is not None
    ):
        return max(
            thermal_inputs.pump_discharge_pressure_pa - thermal_inputs.external_feed_pressure_drop_pa,
            1.0,
        )
    return max(
        bundle.inputs.chamber_pressure_pa
        + thermal_inputs.injector_pressure_drop_pa
        + thermal_inputs.pressure_margin_pa,
        1.0,
    )


def _resolved_coolant_bulk_temperature(
    solver_settings: SolverSettings,
    coolant_temperature_in_k: float,
    coolant_temperature_out_guess_k: float,
) -> tuple[float, str, str]:
    """Return the explicit T_b,c used for coolant-side property evaluation."""

    reference = _resolve_coolant_bulk_temperature_reference(solver_settings)
    if reference is CoolantBulkTemperatureReference.COOLANT_INLET:
        return (
            coolant_temperature_in_k,
            "coolant inlet",
            "T_b,c reference: coolant inlet for explicit forward station properties",
        )
    if reference is CoolantBulkTemperatureReference.COOLANT_OUTLET:
        return (
            coolant_temperature_out_guess_k,
            "coolant outlet",
            "T_b,c reference: coolant outlet from iterated station guess",
        )
    if reference is CoolantBulkTemperatureReference.STATION_MEAN:
        return (
            0.5 * (coolant_temperature_in_k + coolant_temperature_out_guess_k),
            "station mean",
            "T_b,c reference: station mean of coolant inlet and outlet",
        )
    return (
        0.5 * (coolant_temperature_in_k + coolant_temperature_out_guess_k),
        "iterated station mean",
        "T_b,c reference: iterated station mean of coolant inlet and outlet",
    )


def _solver_scheme_label(solver_type: ThermalSolverType) -> str:
    if solver_type is ThermalSolverType.FORWARD_EULER:
        return "Forward Euler"
    if solver_type is ThermalSolverType.BACKWARD_EULER:
        return "Backward Euler"
    if solver_type is ThermalSolverType.CRANK_NICOLSON:
        return "Crank-Nicolson / trapezoidal"
    if solver_type is ThermalSolverType.SIMPSON_CONDUCTANCE:
        return "Simpson conductance averaging"
    return "NTU / exponential"


def _upstream_subpoint_name(flow_direction: CoolingFlowDirection) -> str:
    return "start" if flow_direction is CoolingFlowDirection.INJECTOR_TO_NOZZLE else "end"


def _downstream_subpoint_name(flow_direction: CoolingFlowDirection) -> str:
    return "end" if flow_direction is CoolingFlowDirection.INJECTOR_TO_NOZZLE else "start"


def _evaluate_local_station_closure(
    *,
    bundle: ExportBundle,
    subpoint: _StationSubpoint,
    curvature_mode: BartzThroatCurvatureMode,
    coolant_type: str,
    coolant_mass_flow_kg_per_s: float,
    coolant_temperature_bulk_k: float,
    local_pressure_estimate_pa: float | None,
    coolant_roughness_m: float,
    coolant_wall_temperature_k: float | None,
    primary_coolant_nusselt_method: CoolantNusseltMethod,
    coolant_bulk_temperature_reference_label: str,
    coolant_bulk_temperature_reference_reason: str,
    wall_temperature_guess_k: float,
    station_length_m: float,
) -> _LocalClosureState:
    gas_side_properties, gas_temperature_source = _gas_side_properties_from_profile_point(
        bundle,
        subpoint.profile_point,
        curvature_mode,
    )
    geometry = AnnulusCoolingGeometry(
        r_inner_m=subpoint.radius_m,
        r_outer_m=subpoint.r_outer_m,
        r_mean_m=subpoint.r_mean_m,
        area_annulus_m2=subpoint.coolant_flow_area_m2,
        wetted_perimeter_m=2.0 * math.pi * (subpoint.radius_m + subpoint.r_outer_m),
        hydraulic_diameter_m=subpoint.hydraulic_diameter_m,
        hot_wall_area_m2=subpoint.hot_wall_area_m2,
        coolant_wall_area_m2=subpoint.coolant_wall_area_m2,
        wall_mean_area_m2=subpoint.wall_mean_area_m2,
    )
    coolant_transport = _evaluate_coolant_transport(
        geometry,
        station_length_m,
        coolant_type,
        coolant_mass_flow_kg_per_s,
        coolant_temperature_bulk_k,
        local_pressure_estimate_pa,
        coolant_roughness_m,
        coolant_wall_temperature_k=coolant_wall_temperature_k,
        primary_coolant_nusselt_method=primary_coolant_nusselt_method,
        coolant_bulk_temperature_reference_label=coolant_bulk_temperature_reference_label,
        coolant_bulk_temperature_reference_reason=coolant_bulk_temperature_reference_reason,
    )
    h_g_w_per_m2_k = _bartz_gas_side_heat_transfer_coefficient_for_area(
        bundle,
        subpoint.area_gas_m2,
        gas_side_properties,
        wall_temperature_guess_k,
    )
    notes = list(coolant_transport.notes)
    if gas_temperature_source != "adiabatic-wall":
        notes.append("gas-side recovery placeholder")
    return _LocalClosureState(
        subpoint=subpoint,
        gas_side_properties=gas_side_properties,
        coolant_transport=coolant_transport,
        h_g_w_per_m2_k=h_g_w_per_m2_k,
        g_gas_w_per_k=h_g_w_per_m2_k * subpoint.hot_wall_area_m2,
        g_coolant_w_per_k=coolant_transport.h_c_w_per_m2_k * subpoint.coolant_wall_area_m2,
        notes=tuple(notes),
    )


def _weighted_sum(values: list[float], weights: list[float]) -> float:
    return sum(value * weight for value, weight in zip(values, weights))


def _weighted_optional_average(values: list[float | None], weights: list[float]) -> float | None:
    usable = [(value, weight) for value, weight in zip(values, weights) if value is not None]
    if not usable:
        return None
    weight_sum = sum(weight for _, weight in usable)
    return sum(value * weight for value, weight in usable) / max(weight_sum, 1.0e-12)


def _aggregate_station_conductance_state(
    *,
    solver_settings: SolverSettings,
    flow_direction: CoolingFlowDirection,
    closures: dict[str, _LocalClosureState],
    coolant_temperature_bulk_k: float,
) -> _StationConductanceState:
    solver_type = solver_settings.solver_type
    if solver_type is ThermalSolverType.FORWARD_EULER:
        display_name = _upstream_subpoint_name(flow_direction)
        weights = [1.0]
        selected = [closures[display_name]]
        conductance_rule_label = "upstream rectangle"
    elif solver_type is ThermalSolverType.BACKWARD_EULER:
        display_name = _downstream_subpoint_name(flow_direction)
        weights = [1.0]
        selected = [closures[display_name]]
        conductance_rule_label = "downstream rectangle / implicit"
    elif solver_type is ThermalSolverType.CRANK_NICOLSON:
        display_name = "mid"
        selected = [closures["start"], closures["end"]]
        weights = [0.5, 0.5]
        conductance_rule_label = "trapezoidal conductance averaging"
    elif solver_type is ThermalSolverType.SIMPSON_CONDUCTANCE:
        display_name = "mid"
        selected = [closures["start"], closures["mid"], closures["end"]]
        weights = [1.0 / 6.0, 4.0 / 6.0, 1.0 / 6.0]
        conductance_rule_label = "Simpson area-conductance averaging"
    else:
        display_name = "mid"
        weights = [1.0]
        selected = [closures["mid"]]
        conductance_rule_label = "NTU midpoint/lumped conductance"

    display_closure = closures[display_name]
    g_gas_w_per_k = _weighted_sum([closure.g_gas_w_per_k for closure in selected], weights)
    g_coolant_w_per_k = _weighted_sum([closure.g_coolant_w_per_k for closure in selected], weights)
    hot_area_station_m2 = _weighted_sum([closure.subpoint.hot_wall_area_m2 for closure in selected], weights)
    coolant_area_station_m2 = _weighted_sum([closure.subpoint.coolant_wall_area_m2 for closure in selected], weights)
    flow_area_station_m2 = _weighted_sum([closure.subpoint.coolant_flow_area_m2 for closure in selected], weights)
    wall_mean_area_station_m2 = _weighted_sum([closure.subpoint.wall_mean_area_m2 for closure in selected], weights)
    hydraulic_diameter_station_m = _weighted_sum([closure.subpoint.hydraulic_diameter_m for closure in selected], weights)
    recovery_temperature_k = _weighted_sum([closure.gas_side_properties.recovery_temperature_k for closure in selected], weights)
    h_g_station_w_per_m2_k = g_gas_w_per_k / max(hot_area_station_m2, 1.0e-12)
    h_c_station_w_per_m2_k = g_coolant_w_per_k / max(coolant_area_station_m2, 1.0e-12)
    notes: list[str] = [conductance_rule_label]
    for closure in selected:
        for note in closure.notes:
            if note not in notes:
                notes.append(note)
    return _StationConductanceState(
        integration_scheme_label=_solver_scheme_label(solver_type),
        conductance_rule_label=conductance_rule_label,
        display_subpoint_name=display_name,
        x_display_m=display_closure.subpoint.x_m,
        radius_display_m=display_closure.subpoint.radius_m,
        area_display_m2=display_closure.subpoint.area_gas_m2,
        eps_display=display_closure.subpoint.eps,
        recovery_temperature_k=recovery_temperature_k,
        coolant_bulk_temperature_k=coolant_temperature_bulk_k,
        g_gas_w_per_k=g_gas_w_per_k,
        g_coolant_w_per_k=g_coolant_w_per_k,
        h_g_station_w_per_m2_k=h_g_station_w_per_m2_k,
        h_c_station_w_per_m2_k=h_c_station_w_per_m2_k,
        nusselt_station=_weighted_sum([closure.coolant_transport.nusselt_number for closure in selected], weights),
        reynolds_station=_weighted_sum([closure.coolant_transport.reynolds_number for closure in selected], weights),
        prandtl_station=_weighted_sum([closure.coolant_transport.prandtl_number for closure in selected], weights),
        hot_area_station_m2=hot_area_station_m2,
        coolant_area_station_m2=coolant_area_station_m2,
        flow_area_station_m2=flow_area_station_m2,
        wall_mean_area_station_m2=wall_mean_area_station_m2,
        hydraulic_diameter_station_m=hydraulic_diameter_station_m,
        pressure_drop_station_pa=_weighted_sum([closure.coolant_transport.pressure_drop_total_pa for closure in selected], weights),
        coolant_cp_j_per_kg_k=_weighted_sum([closure.coolant_transport.properties.cp_j_per_kg_k for closure in selected], weights),
        coolant_viscosity_pa_s=_weighted_sum([closure.coolant_transport.properties.viscosity_pa_s for closure in selected], weights),
        coolant_wall_viscosity_pa_s=_weighted_optional_average(
            [closure.coolant_transport.wall_viscosity_pa_s for closure in selected],
            weights,
        ),
        nusselt_method=display_closure.coolant_transport.nusselt_method,
        nusselt_dittus_boelter=_weighted_optional_average(
            [closure.coolant_transport.nusselt_dittus_boelter for closure in selected],
            weights,
        ),
        nusselt_sieder_tate=_weighted_optional_average(
            [closure.coolant_transport.nusselt_sieder_tate for closure in selected],
            weights,
        ),
        nusselt_gnielinski=_weighted_optional_average(
            [closure.coolant_transport.nusselt_gnielinski for closure in selected],
            weights,
        ),
        nusselt_spread_fraction=_weighted_optional_average(
            [closure.coolant_transport.nusselt_spread_fraction for closure in selected],
            weights,
        ),
        h_c_dittus_boelter_w_per_m2_k=_weighted_optional_average(
            [closure.coolant_transport.h_c_dittus_boelter_w_per_m2_k for closure in selected],
            weights,
        ),
        h_c_sieder_tate_w_per_m2_k=_weighted_optional_average(
            [closure.coolant_transport.h_c_sieder_tate_w_per_m2_k for closure in selected],
            weights,
        ),
        h_c_gnielinski_w_per_m2_k=_weighted_optional_average(
            [closure.coolant_transport.h_c_gnielinski_w_per_m2_k for closure in selected],
            weights,
        ),
        friction_factor=_weighted_sum([closure.coolant_transport.friction_factor for closure in selected], weights),
        sieder_tate_viscosity_ratio=_weighted_optional_average(
            [closure.coolant_transport.sieder_tate_viscosity_ratio for closure in selected],
            weights,
        ),
        sieder_tate_correction_factor=_weighted_optional_average(
            [closure.coolant_transport.sieder_tate_correction_factor for closure in selected],
            weights,
        ),
        representative_profile_point=display_closure.subpoint.profile_point,
        notes=tuple(notes),
    )


def _station_wall_resistance_k_per_w(
    wall_thickness_m: float,
    wall_conductivity_w_per_m_k: float,
    wall_mean_area_m2: float,
) -> float:
    return wall_thickness_m / max(wall_conductivity_w_per_m_k * wall_mean_area_m2, 1.0e-12)


def _station_total_conductance_w_per_k(
    gas_conductance_w_per_k: float,
    coolant_conductance_w_per_k: float,
    wall_resistance_k_per_w: float,
) -> tuple[float, float, float]:
    gas_resistance_k_per_w = 1.0 / max(gas_conductance_w_per_k, 1.0e-12)
    coolant_resistance_k_per_w = 1.0 / max(coolant_conductance_w_per_k, 1.0e-12)
    total_resistance_k_per_w = gas_resistance_k_per_w + wall_resistance_k_per_w + coolant_resistance_k_per_w
    return (
        1.0 / max(total_resistance_k_per_w, 1.0e-12),
        gas_resistance_k_per_w,
        coolant_resistance_k_per_w,
    )


def _solve_station_heat_balance(
    bundle: ExportBundle,
    sample: _SamplePoint,
    station_geometry: AnnulusCoolingGeometry,
    flow_direction: CoolingFlowDirection,
    curvature_mode: BartzThroatCurvatureMode,
    coolant_temperature_in_k: float,
    coolant_type: str,
    coolant_mass_flow_kg_per_s: float,
    local_pressure_estimate_pa: float | None,
    wall_thickness_m: float,
    wall_material_id: str,
    coolant_roughness_m: float,
    primary_coolant_nusselt_method: CoolantNusseltMethod,
    solver_settings: SolverSettings,
    radiation_settings: RadiationSettings,
    previous_station_result: ThermalStationResult | None = None,
) -> _StationHeatBalanceResult:
    """Solve one station as a coupled fixed-point annulus heat-balance problem.

    All coupled coolant- and gas-side quantities are recomputed inside the
    iteration loop. That keeps the MVP internally consistent now and leaves a
    clean seam for later temperature/pressure-dependent coolant properties.
    """

    representative_gas_side_properties, _ = _gas_side_properties(
        bundle,
        sample,
        curvature_mode,
    )
    recovery_temperature_k = max(
        representative_gas_side_properties.recovery_temperature_k,
        coolant_temperature_in_k + _SMALL_DELTA_K,
    )
    wall_temperature_guess_k = _initial_wall_temperature_guess(
        recovery_temperature_k,
        coolant_temperature_in_k,
        previous_station_result,
    )
    coolant_temperature_out_guess_k = max(coolant_temperature_in_k + 10.0, coolant_temperature_in_k + _SMALL_DELTA_K)
    radiation_heat_flux_guess_w_per_m2 = 0.0
    station_subpoints = _build_station_subpoints(
        sample,
        station_geometry.r_outer_m - station_geometry.r_inner_m,
    )

    last_solution: _StationHeatBalanceResult | None = None
    last_coolant_transport: _CoolantTransportState | None = None
    for iteration in range(max(solver_settings.max_iterations_per_station, 1)):
        (
            coolant_temperature_bulk_k,
            coolant_bulk_temperature_reference_label,
            coolant_bulk_temperature_reference_reason,
        ) = _resolved_coolant_bulk_temperature(
            solver_settings,
            coolant_temperature_in_k,
            coolant_temperature_out_guess_k,
        )
        coolant_wall_temperature_guess_k = (
            last_solution.wall_temperature_coolant_side_k
            if last_solution is not None and last_solution.wall_temperature_coolant_side_k is not None
            else max(coolant_temperature_bulk_k, min(wall_temperature_guess_k, recovery_temperature_k))
        )
        solver_type = solver_settings.solver_type
        if solver_type is ThermalSolverType.FORWARD_EULER:
            subpoint_names = (_upstream_subpoint_name(flow_direction),)
        elif solver_type is ThermalSolverType.BACKWARD_EULER:
            subpoint_names = (_downstream_subpoint_name(flow_direction),)
        elif solver_type is ThermalSolverType.CRANK_NICOLSON:
            subpoint_names = ("start", "end")
        elif solver_type is ThermalSolverType.SIMPSON_CONDUCTANCE:
            subpoint_names = ("start", "mid", "end")
        else:
            subpoint_names = ("mid",)
        local_closures: dict[str, _LocalClosureState] = {}
        for subpoint_name in subpoint_names:
            local_closures[subpoint_name] = _evaluate_local_station_closure(
                bundle=bundle,
                subpoint=station_subpoints[subpoint_name],
                curvature_mode=curvature_mode,
                coolant_type=coolant_type,
                coolant_mass_flow_kg_per_s=coolant_mass_flow_kg_per_s,
                coolant_temperature_bulk_k=coolant_temperature_bulk_k,
                local_pressure_estimate_pa=local_pressure_estimate_pa,
                coolant_roughness_m=coolant_roughness_m,
                coolant_wall_temperature_k=coolant_wall_temperature_guess_k,
                primary_coolant_nusselt_method=primary_coolant_nusselt_method,
                coolant_bulk_temperature_reference_label=coolant_bulk_temperature_reference_label,
                coolant_bulk_temperature_reference_reason=coolant_bulk_temperature_reference_reason,
                wall_temperature_guess_k=wall_temperature_guess_k,
                station_length_m=sample.ds_m,
            )
        if "mid" not in local_closures:
            local_closures["mid"] = _evaluate_local_station_closure(
                bundle=bundle,
                subpoint=station_subpoints["mid"],
                curvature_mode=curvature_mode,
                coolant_type=coolant_type,
                coolant_mass_flow_kg_per_s=coolant_mass_flow_kg_per_s,
                coolant_temperature_bulk_k=coolant_temperature_bulk_k,
                local_pressure_estimate_pa=local_pressure_estimate_pa,
                coolant_roughness_m=coolant_roughness_m,
                coolant_wall_temperature_k=coolant_wall_temperature_guess_k,
                primary_coolant_nusselt_method=primary_coolant_nusselt_method,
                coolant_bulk_temperature_reference_label=coolant_bulk_temperature_reference_label,
                coolant_bulk_temperature_reference_reason=coolant_bulk_temperature_reference_reason,
                wall_temperature_guess_k=wall_temperature_guess_k,
                station_length_m=sample.ds_m,
            )
        conductance_state = _aggregate_station_conductance_state(
            solver_settings=solver_settings,
            flow_direction=flow_direction,
            closures=local_closures,
            coolant_temperature_bulk_k=coolant_temperature_bulk_k,
        )
        representative_closure = local_closures[conductance_state.display_subpoint_name]
        coolant_transport = representative_closure.coolant_transport
        last_coolant_transport = coolant_transport
        wall_mean_temperature_guess_k = 0.5 * (
            wall_temperature_guess_k + coolant_wall_temperature_guess_k
        )
        wall_material_properties = get_material_properties(
            wall_material_id,
            wall_mean_temperature_guess_k,
        )
        wall_conductivity_w_per_m_k = max(
            wall_material_properties.thermal_conductivity_w_per_m_k or 25.0,
            1.0e-12,
        )
        wall_resistance_k_per_w = _station_wall_resistance_k_per_w(
            wall_thickness_m,
            wall_conductivity_w_per_m_k,
            conductance_state.wall_mean_area_station_m2,
        )
        overall_station_conductance_w_per_k, gas_resistance_k_per_w, coolant_resistance_k_per_w = _station_total_conductance_w_per_k(
            conductance_state.g_gas_w_per_k,
            conductance_state.g_coolant_w_per_k,
            wall_resistance_k_per_w,
        )
        coolant_temperature_out_conv_k = _clamp_coolant_outlet_temperature(
            _solve_station_temperature_outlet(
                conductance_state.recovery_temperature_k,
                coolant_temperature_in_k,
                overall_station_conductance_w_per_k,
                coolant_mass_flow_kg_per_s,
                conductance_state.coolant_cp_j_per_kg_k,
                solver_settings,
            ),
            coolant_temperature_in_k,
            recovery_temperature_k,
        )
        q_conv_station_w = coolant_mass_flow_kg_per_s * conductance_state.coolant_cp_j_per_kg_k * (
            coolant_temperature_out_conv_k - coolant_temperature_in_k
        )
        q_conv_w_per_m2 = q_conv_station_w / max(conductance_state.hot_area_station_m2, 1.0e-12)
        radiation_result = _compute_station_radiation(
            bundle=bundle,
            sample=sample,
            station_geometry=station_geometry,
            gas_side_properties=representative_closure.gas_side_properties,
            wall_temperature_hot_gas_side_k=wall_temperature_guess_k,
            local_pressure_estimate_pa=local_pressure_estimate_pa,
            radiation_settings=radiation_settings,
        )
        if radiation_settings.enabled:
            relaxation = min(max(radiation_settings.radiation_relaxation_factor, 0.0), 1.0)
            relaxed_q_rad_w_per_m2 = radiation_heat_flux_guess_w_per_m2 + relaxation * (
                radiation_result.q_rad_w_per_m2 - radiation_heat_flux_guess_w_per_m2
            )
            radiation_result = _RadiationHeatTransferResult(
                q_rad_w_per_m2=relaxed_q_rad_w_per_m2,
                q_radiation_station_w=relaxed_q_rad_w_per_m2 * conductance_state.hot_area_station_m2,
                radiation_temperature_k=radiation_result.radiation_temperature_k,
                gas_effective_emissivity=radiation_result.gas_effective_emissivity,
                wall_emissivity=radiation_result.wall_emissivity,
                optical_path_length_m=radiation_result.optical_path_length_m,
                model_note=radiation_result.model_note,
                participating_species_mode=radiation_result.participating_species_mode,
                participating_species_used=radiation_result.participating_species_used,
                status_notes=radiation_result.status_notes,
            )
        q_station_w = q_conv_station_w + radiation_result.q_radiation_station_w
        coolant_temperature_out_new_k = _clamp_coolant_outlet_temperature(
            coolant_temperature_in_k + q_station_w / max(coolant_mass_flow_kg_per_s * conductance_state.coolant_cp_j_per_kg_k, 1.0e-12),
            coolant_temperature_in_k,
            recovery_temperature_k,
        )
        q_hot_w_per_m2 = q_station_w / max(conductance_state.hot_area_station_m2, 1.0e-12)
        wall_temperature_coolant_side_k = coolant_temperature_bulk_k + q_station_w / max(conductance_state.g_coolant_w_per_k, 1.0e-12)
        wall_temperature_hot_gas_side_k = _clamp_hot_wall_temperature(
            wall_temperature_coolant_side_k + q_station_w * wall_resistance_k_per_w,
            recovery_temperature_k,
            coolant_temperature_in_k,
        )
        wall_delta_t_k = wall_temperature_hot_gas_side_k - wall_temperature_coolant_side_k
        residual_k = max(
            abs(wall_temperature_hot_gas_side_k - wall_temperature_guess_k),
            abs(coolant_temperature_out_new_k - coolant_temperature_out_guess_k),
        )

        last_solution = _StationHeatBalanceResult(
            h_g_w_per_m2_k=conductance_state.h_g_station_w_per_m2_k,
            h_c_w_per_m2_k=conductance_state.h_c_station_w_per_m2_k,
            recovery_temperature_k=conductance_state.recovery_temperature_k,
            coolant_temperature_out_k=coolant_temperature_out_new_k,
            coolant_temperature_bulk_k=coolant_temperature_bulk_k,
            q_station_w=q_station_w,
            q_hot_w_per_m2=q_hot_w_per_m2,
            q_conv_w_per_m2=q_conv_w_per_m2,
            q_rad_w_per_m2=radiation_result.q_rad_w_per_m2,
            q_total_w_per_m2=q_hot_w_per_m2,
            q_radiation_station_w=radiation_result.q_radiation_station_w,
            wall_temperature_coolant_side_k=wall_temperature_coolant_side_k,
            wall_temperature_hot_gas_side_k=wall_temperature_hot_gas_side_k,
            wall_delta_t_k=wall_delta_t_k,
            coolant_bulk_temperature_reference_label=coolant_transport.bulk_temperature_reference_label,
            coolant_bulk_temperature_reference_reason=coolant_transport.bulk_temperature_reference_reason,
            radiation_temperature_k=radiation_result.radiation_temperature_k,
            gas_effective_emissivity=radiation_result.gas_effective_emissivity,
            wall_emissivity=radiation_result.wall_emissivity,
            optical_path_length_m=radiation_result.optical_path_length_m,
            radiation_model_note=radiation_result.model_note,
            participating_species_mode=radiation_result.participating_species_mode,
            participating_species_used=radiation_result.participating_species_used,
            reynolds_coolant=conductance_state.reynolds_station,
            prandtl_coolant=conductance_state.prandtl_station,
            coolant_cp_j_per_kg_k=conductance_state.coolant_cp_j_per_kg_k,
            coolant_viscosity_pa_s=conductance_state.coolant_viscosity_pa_s,
            nusselt_coolant=conductance_state.nusselt_station,
            nusselt_coolant_method=conductance_state.nusselt_method,
            nusselt_dittus_boelter=conductance_state.nusselt_dittus_boelter,
            nusselt_sieder_tate=conductance_state.nusselt_sieder_tate,
            nusselt_gnielinski=conductance_state.nusselt_gnielinski,
            nusselt_spread_fraction=conductance_state.nusselt_spread_fraction,
            friction_factor=conductance_state.friction_factor,
            h_c_dittus_boelter_w_per_m2_k=conductance_state.h_c_dittus_boelter_w_per_m2_k,
            h_c_sieder_tate_w_per_m2_k=conductance_state.h_c_sieder_tate_w_per_m2_k,
            h_c_gnielinski_w_per_m2_k=conductance_state.h_c_gnielinski_w_per_m2_k,
            coolant_wall_viscosity_pa_s=conductance_state.coolant_wall_viscosity_pa_s,
            sieder_tate_viscosity_ratio=conductance_state.sieder_tate_viscosity_ratio,
            sieder_tate_correction_factor=conductance_state.sieder_tate_correction_factor,
            gas_conductance_w_per_k=conductance_state.g_gas_w_per_k,
            coolant_conductance_w_per_k=conductance_state.g_coolant_w_per_k,
            gas_resistance_k_per_w=gas_resistance_k_per_w,
            wall_resistance_k_per_w=wall_resistance_k_per_w,
            coolant_resistance_k_per_w=coolant_resistance_k_per_w,
            coolant_flow_area_m2=conductance_state.flow_area_station_m2,
            coolant_wall_area_m2=conductance_state.coolant_area_station_m2,
            conductance_rule_label=conductance_state.conductance_rule_label,
            solver_scheme_label=conductance_state.integration_scheme_label,
            pressure_drop_station_pa=conductance_state.pressure_drop_station_pa,
            wall_material_properties=wall_material_properties,
            iterations=iteration + 1,
            converged=False,
            residual_k=residual_k,
            status_notes=tuple(conductance_state.notes) + radiation_result.status_notes,
        )

        if residual_k < solver_settings.station_tolerance:
            return _finalize_station_solution(
                last_solution,
                coolant_transport,
                representative_gas_side_properties.throat_curvature_mode,
                converged=True,
            )

        wall_temperature_guess_k = _clamp_hot_wall_temperature(
            wall_temperature_guess_k
            + solver_settings.relaxation_factor * (wall_temperature_hot_gas_side_k - wall_temperature_guess_k),
            recovery_temperature_k,
            coolant_temperature_in_k,
        )
        coolant_temperature_out_guess_k = _clamp_coolant_outlet_temperature(
            coolant_temperature_out_guess_k
            + solver_settings.relaxation_factor * (coolant_temperature_out_new_k - coolant_temperature_out_guess_k),
            coolant_temperature_in_k,
            recovery_temperature_k,
        )
        radiation_heat_flux_guess_w_per_m2 = radiation_result.q_rad_w_per_m2

    if last_solution is None:  # pragma: no cover - defensive guard
        raise InputValidationError(["Thermal station solver did not produce a result."])
    if last_coolant_transport is None:  # pragma: no cover - defensive guard
        raise InputValidationError(["Thermal station transport state did not produce a result."])
    return _finalize_station_solution(
        last_solution,
        last_coolant_transport,
        representative_gas_side_properties.throat_curvature_mode,
        converged=False,
    )


def _bartz_gas_side_heat_transfer_coefficient(
    bundle: ExportBundle,
    sample: _SamplePoint,
    gas_side_properties: _GasSideProperties,
    wall_temperature_k: float,
) -> float:
    """Return the local Bartz gas-side heat-transfer coefficient in SI units.

    These TOP/chamber thermal studies are still preliminary, but Bartz gives a
    better steady-state hot-gas-side trend than the older boundary-layer-thick-
    ness placeholder. The implementation reuses existing CEA outputs: `Taw`,
    `cp`, `mu`, `Pr`, `gamma`, `M`, `c*` and the current geometry areas.

    TODO: add Ievlev/Ivlev as a future hot-gas-side h_g alternative after
    verifying the exact formula, variable definitions and validity range.
    It should not be mixed into the coolant-side Nu_c comparison path.
    """

    return _bartz_gas_side_heat_transfer_coefficient_for_area(
        bundle,
        sample.area_m2,
        gas_side_properties,
        wall_temperature_k,
    )


def _bartz_gas_side_heat_transfer_coefficient_for_area(
    bundle: ExportBundle,
    local_area_m2: float,
    gas_side_properties: _GasSideProperties,
    wall_temperature_k: float,
) -> float:
    throat_diameter_m = 2.0 * max(bundle.geometry.throat_radius_m, 1.0e-12)
    local_area_ratio = max(local_area_m2 / max(bundle.geometry.throat_area_m2, 1.0e-12), 1.0)
    throat_curvature_radius_m = max(gas_side_properties.throat_curvature_radius_m, 1.0e-12)
    chamber_pressure_over_cstar = (
        max(bundle.inputs.chamber_pressure_pa, 1.0)
        / max(bundle.thermochemistry.c_star_m_s, 1.0e-12)
    )
    mach_term = 1.0 + 0.5 * max(gas_side_properties.gamma - 1.0, 0.0) * gas_side_properties.mach_number**2
    sigma_term = (
        0.5
        * max(wall_temperature_k, 1.0)
        / max(gas_side_properties.chamber_temperature_k, 1.0)
        * mach_term
        + 0.5
    )
    sigma = sigma_term ** (-0.68) * mach_term ** (-0.12)
    return (
        0.026
        * (max(gas_side_properties.viscosity_pa_s, 1.0e-12) ** 0.2)
        * gas_side_properties.cp_j_per_kg_k
        / max(gas_side_properties.prandtl_number, 1.0e-12) ** 0.6
        * chamber_pressure_over_cstar**0.8
        * max(throat_diameter_m, 1.0e-12) ** (-0.2)
        * max(throat_diameter_m / throat_curvature_radius_m, 1.0e-12) ** 0.1
        * max(1.0 / local_area_ratio, 1.0e-12) ** 0.9
        * sigma
    )


def _compute_station_radiation(
    *,
    bundle: ExportBundle,
    sample: _SamplePoint,
    station_geometry: AnnulusCoolingGeometry,
    gas_side_properties: _GasSideProperties,
    wall_temperature_hot_gas_side_k: float,
    local_pressure_estimate_pa: float | None,
    radiation_settings: RadiationSettings,
) -> _RadiationHeatTransferResult:
    """Return the explicit gas-side radiation contribution for one station.

    Radiation stays separate from the Bartz convection path so the solver can
    report q_conv and q_rad independently. The current implementation is a
    screening-level model only; it is not a spectral or CFD radiation solver.
    """

    if not radiation_settings.enabled or radiation_settings.model is RadiationModelType.OFF:
        return _RadiationHeatTransferResult(
            q_rad_w_per_m2=0.0,
            q_radiation_station_w=0.0,
            radiation_temperature_k=None,
            gas_effective_emissivity=0.0,
            wall_emissivity=radiation_settings.wall_emissivity,
            optical_path_length_m=None,
            model_note="radiation disabled",
            participating_species_mode=radiation_settings.participating_species_mode.value,
            participating_species_used=None,
            status_notes=("radiation disabled",),
        )

    if radiation_settings.model is RadiationModelType.USER_FIXED_HEAT_FLUX:
        fixed_heat_flux_w_per_m2 = max(radiation_settings.fixed_radiation_heat_flux_w_per_m2 or 0.0, 0.0)
        return _RadiationHeatTransferResult(
            q_rad_w_per_m2=fixed_heat_flux_w_per_m2,
            q_radiation_station_w=fixed_heat_flux_w_per_m2 * station_geometry.hot_wall_area_m2,
            radiation_temperature_k=None,
            gas_effective_emissivity=radiation_settings.gas_effective_emissivity,
            wall_emissivity=radiation_settings.wall_emissivity,
            optical_path_length_m=None,
            model_note="radiation: user fixed heat flux",
            participating_species_mode=radiation_settings.participating_species_mode.value,
            participating_species_used=None,
            status_notes=(
                "radiation: user fixed heat flux",
                "radiation model is screening-level, not spectral",
            ),
        )

    radiation_temperature_k = _resolved_radiation_temperature_k(bundle, gas_side_properties, radiation_settings)
    gas_effective_emissivity = radiation_settings.gas_effective_emissivity
    optical_path_length_m: float | None = None
    status_notes: list[str] = []
    participating_species_used: str | None = None

    use_participating_media = (
        radiation_settings.model is RadiationModelType.PARTICIPATING_MEDIA_EFFECTIVE_EMISSIVITY
        or radiation_settings.participating_media_enabled
    )
    if use_participating_media:
        gas_effective_emissivity, optical_path_length_m, participating_notes, participating_species_used = _participating_media_emissivity(
            sample=sample,
            station_geometry=station_geometry,
            local_pressure_estimate_pa=local_pressure_estimate_pa,
            radiation_settings=radiation_settings,
        )
        status_notes.extend(participating_notes)
        model_note = "radiation: participating-media effective-emissivity screening model"
    else:
        model_note = "radiation: grey gas"

    q_rad_w_per_m2 = (
        radiation_settings.wall_emissivity
        * gas_effective_emissivity
        * _STEFAN_BOLTZMANN_CONSTANT_W_PER_M2_K4
        * (max(radiation_temperature_k, 1.0) ** 4 - max(wall_temperature_hot_gas_side_k, 1.0) ** 4)
    )
    if q_rad_w_per_m2 < 0.0:
        q_rad_w_per_m2 = 0.0
        status_notes.append("radiation heat flux clamped to non-negative")

    status_notes.extend(
        (
            model_note,
            "radiation model is screening-level, not spectral",
        )
    )
    deduplicated_notes: list[str] = []
    for note in status_notes:
        if note not in deduplicated_notes:
            deduplicated_notes.append(note)

    return _RadiationHeatTransferResult(
        q_rad_w_per_m2=q_rad_w_per_m2,
        q_radiation_station_w=q_rad_w_per_m2 * station_geometry.hot_wall_area_m2,
        radiation_temperature_k=radiation_temperature_k,
        gas_effective_emissivity=gas_effective_emissivity,
        wall_emissivity=radiation_settings.wall_emissivity,
        optical_path_length_m=optical_path_length_m,
        model_note=model_note,
        participating_species_mode=radiation_settings.participating_species_mode.value,
        participating_species_used=participating_species_used,
        status_notes=tuple(deduplicated_notes),
    )


def _resolved_radiation_temperature_k(
    bundle: ExportBundle,
    gas_side_properties: _GasSideProperties,
    radiation_settings: RadiationSettings,
) -> float:
    """Return the source temperature used in the screening radiation model."""

    if radiation_settings.radiation_temperature_source is RadiationTemperatureSource.ADIABATIC_WALL_TEMPERATURE:
        return gas_side_properties.recovery_temperature_k
    if radiation_settings.radiation_temperature_source is RadiationTemperatureSource.CHAMBER_TEMPERATURE:
        return bundle.thermochemistry.chamber_temperature_k
    return gas_side_properties.local_gas_temperature_k or bundle.thermochemistry.chamber_temperature_k


def _participating_media_emissivity(
    *,
    sample: _SamplePoint,
    station_geometry: AnnulusCoolingGeometry,
    local_pressure_estimate_pa: float | None,
    radiation_settings: RadiationSettings,
) -> tuple[float, float | None, tuple[str, ...], str | None]:
    """Return a bounded screening emissivity driven by local or fallback species data."""

    optical_path_length_m, path_notes = _radiation_optical_path_length_m(
        station_geometry,
        radiation_settings,
    )
    local_species_mole_fractions, local_species_notes = extract_station_species_mole_fractions(sample.profile_point)
    species_notes = [*path_notes, *local_species_notes]
    species_source_note = "species source: local CEA mole fractions"

    selected_species_mole_fractions = local_species_mole_fractions
    if not selected_species_mole_fractions:
        fallback_species = _fallback_species_mole_fractions(radiation_settings)
        if fallback_species:
            selected_species_mole_fractions = fallback_species
            species_source_note = "species source: user fallback mole fractions"
        else:
            return (
                min(max(radiation_settings.gas_effective_emissivity, 0.0), 0.95),
                optical_path_length_m,
                tuple(
                    [
                        *species_notes,
                        "participating media fallback: fixed effective gas emissivity",
                    ]
                ),
                None,
            )

    effective_emissivity, emission_notes, participating_species_used = compute_effective_gas_emissivity_from_species(
        species_mole_fractions=selected_species_mole_fractions,
        pressure_pa=local_pressure_estimate_pa or 0.0,
        optical_path_length_m=optical_path_length_m or 0.0,
        radiation_settings=radiation_settings,
    )
    return (
        effective_emissivity,
        optical_path_length_m,
        tuple(
            [
                *species_notes,
                species_source_note,
                *emission_notes,
            ]
        ),
        participating_species_used,
    )


def _radiation_optical_path_length_m(
    station_geometry: AnnulusCoolingGeometry,
    radiation_settings: RadiationSettings,
) -> tuple[float | None, tuple[str, ...]]:
    """Return the screening optical path length used for participating media."""

    if radiation_settings.optical_path_length_mode is OpticalPathLengthMode.USER_FIXED:
        return radiation_settings.user_optical_path_length_m, ()
    if radiation_settings.optical_path_length_mode is OpticalPathLengthMode.MEAN_BEAM_LENGTH_PLACEHOLDER:
        return 2.0 * station_geometry.r_inner_m, ("optical path placeholder: local diameter used",)
    return 2.0 * station_geometry.r_inner_m, ()


def extract_station_species_mole_fractions(
    profile_point: ThermochemistryProfilePoint | None,
) -> tuple[dict[str, float] | None, tuple[str, ...]]:
    """Return local station mole fractions if the profile state exposes them safely."""

    if profile_point is None or getattr(profile_point, "state", None) is None:
        return None, ("no local CEA species mole fractions available",)

    state = profile_point.state
    for attribute_name in (
        "species_mole_fractions",
        "mole_fractions",
        "cea_species_mole_fractions",
    ):
        value = getattr(state, attribute_name, None)
        if isinstance(value, dict) and value:
            return _normalized_species_fraction_dict(value), ()

    for attribute_name in ("species", "composition"):
        value = getattr(state, attribute_name, None)
        if isinstance(value, dict) and value:
            fraction_basis = getattr(state, "species_fraction_basis", None)
            if isinstance(fraction_basis, str) and fraction_basis.strip().lower() == "mole":
                return _normalized_species_fraction_dict(value), ()
            return None, (
                "species fractions available but not confirmed as mole fractions; participating media fallback used",
            )

    for attribute_name in ("species_mass_fractions", "mass_fractions"):
        value = getattr(state, attribute_name, None)
        if isinstance(value, dict) and value:
            return None, (
                "species fractions available but not confirmed as mole fractions; participating media fallback used",
            )

    return None, ("no local CEA species mole fractions available",)


def classify_radiating_species(
    species_mole_fractions: dict[str, float],
    mode: ParticipatingSpeciesMode,
) -> dict[str, float]:
    """Select the radiating species used by the screening participating-media model."""

    normalized_species = {
        _canonical_species_name(species_name): mole_fraction
        for species_name, mole_fraction in species_mole_fractions.items()
        if mole_fraction > 0.0
    }
    if mode is ParticipatingSpeciesMode.CO2_H2O_ONLY:
        return {
            canonical_name: normalized_species.get(canonical_name, 0.0)
            for canonical_name in ("co2", "h2o")
            if normalized_species.get(canonical_name, 0.0) > 0.0
        }

    selected: dict[str, float] = {}
    for canonical_name, mole_fraction in normalized_species.items():
        if _is_radiating_species(canonical_name):
            selected[canonical_name] = mole_fraction
    return dict(sorted(selected.items(), key=lambda item: item[1], reverse=True))


def compute_effective_gas_emissivity_from_species(
    species_mole_fractions: dict[str, float],
    pressure_pa: float,
    optical_path_length_m: float,
    radiation_settings: RadiationSettings,
) -> tuple[float, list[str], str | None]:
    """Return a bounded gas emissivity from local station mole fractions.

    This remains a screening-level effective-emissivity model. It uses local
    station species mole fractions, pressure and optical path length, but it
    is not a spectral band or WSGG radiation solver.
    """

    participating_species = classify_radiating_species(
        species_mole_fractions,
        radiation_settings.participating_species_mode,
    )
    pressure_bar = max(pressure_pa / 1.0e5, 0.0)
    optical_factor = math.sqrt(max(pressure_bar * optical_path_length_m, 0.0))
    notes: list[str] = []

    if radiation_settings.participating_species_mode is ParticipatingSpeciesMode.CO2_H2O_ONLY:
        x_co2 = participating_species.get("co2", 0.0)
        x_h2o = participating_species.get("h2o", 0.0)
        if x_co2 <= 0.0 and x_h2o <= 0.0:
            notes.append("no CO2/H2O mole fraction found in local CEA station")
        effective_emissivity = _clamp_effective_emissivity(
            radiation_settings.gas_effective_emissivity
            + 0.08 * x_h2o * optical_factor
            + 0.05 * x_co2 * optical_factor
            + radiation_settings.soot_factor
        )
    else:
        species_sum = 0.0
        for canonical_name, mole_fraction in participating_species.items():
            species_sum += _RADIATING_SPECIES_COEFFICIENTS.get(
                canonical_name,
                _DEFAULT_POLYATOMIC_RADIATION_COEFFICIENT,
            ) * mole_fraction
        effective_emissivity = _clamp_effective_emissivity(
            radiation_settings.gas_effective_emissivity
            + optical_factor * species_sum
            + radiation_settings.soot_factor
        )

    participating_species_used = _format_participating_species_used(participating_species)
    if participating_species_used is not None:
        notes.append(f"participating species: {participating_species_used}")
    return effective_emissivity, notes, participating_species_used


def _fallback_species_mole_fractions(radiation_settings: RadiationSettings) -> dict[str, float] | None:
    fallback_species: dict[str, float] = {}
    if radiation_settings.co2_mole_fraction is not None and radiation_settings.co2_mole_fraction > 0.0:
        fallback_species["co2"] = radiation_settings.co2_mole_fraction
    if radiation_settings.h2o_mole_fraction is not None and radiation_settings.h2o_mole_fraction > 0.0:
        fallback_species["h2o"] = radiation_settings.h2o_mole_fraction
    return fallback_species or None


def _normalized_species_fraction_dict(values: dict[str, float]) -> dict[str, float]:
    normalized = {
        _canonical_species_name(species_name): float(mole_fraction)
        for species_name, mole_fraction in values.items()
        if mole_fraction is not None and float(mole_fraction) > 0.0
    }
    return dict(sorted(normalized.items(), key=lambda item: item[1], reverse=True))


def _canonical_species_name(species_name: str) -> str:
    normalized = species_name.strip().lower()
    normalized = normalized.replace("(g)", "").replace("(l)", "").replace("(v)", "")
    normalized = normalized.replace(" ", "").replace("-", "").replace("_", "")
    aliases = {
        "carbondioxide": "co2",
        "co2": "co2",
        "water": "h2o",
        "h2o": "h2o",
        "carbonmonoxide": "co",
        "co": "co",
        "hydroxyl": "oh",
        "oh": "oh",
        "nitricoxide": "no",
        "no": "no",
        "nitrogendioxide": "no2",
        "no2": "no2",
        "sulfurdioxide": "so2",
        "sulphurdioxide": "so2",
        "so2": "so2",
        "methane": "ch4",
        "ch4": "ch4",
        "nitrogen": "n2",
        "n2": "n2",
        "oxygen": "o2",
        "o2": "o2",
        "hydrogen": "h2",
        "h2": "h2",
    }
    return aliases.get(normalized, normalized)


def _is_radiating_species(canonical_name: str) -> bool:
    if canonical_name in _RADIATING_SPECIES_COEFFICIENTS:
        return True
    if canonical_name in {"n2", "o2", "h2"}:
        return False
    if _parsed_atom_count(canonical_name) >= 3:
        return True
    return False


def _parsed_atom_count(formula_or_name: str) -> int:
    formula = re.sub(r"[^A-Za-z0-9]", "", formula_or_name)
    if not formula:
        return 0
    parts = re.findall(r"[A-Z][a-z]?\d*|[a-z]+\d*", formula)
    if not parts:
        parts = re.findall(r"[a-z]+\d*", formula.lower())
    atom_count = 0
    for part in parts:
        match = re.match(r"([A-Za-z]+)(\d*)", part)
        if not match:
            continue
        count = int(match.group(2)) if match.group(2) else 1
        atom_count += count
    return atom_count


def _format_participating_species_used(participating_species: dict[str, float]) -> str | None:
    if not participating_species:
        return None
    ordered_species = sorted(participating_species.items(), key=lambda item: item[1], reverse=True)
    return ", ".join(f"{species.upper()}={value:.3f}" for species, value in ordered_species[:6])


def _clamp_effective_emissivity(value: float) -> float:
    return min(max(value, 0.0), 0.95)


def _coolant_prandtl_number(coolant_state: CoolantProperties) -> float:
    """Return a constant-property Prandtl number for the current coolant state."""

    if coolant_state.prandtl_number is not None and coolant_state.prandtl_number > 0.0:
        return coolant_state.prandtl_number
    return (
        coolant_state.cp_j_per_kg_k
        * coolant_state.viscosity_pa_s
        / max(coolant_state.thermal_conductivity_w_per_m_k, 1.0e-12)
    )


def _evaluate_coolant_transport(
    station_geometry: AnnulusCoolingGeometry,
    station_length_m: float,
    coolant_type: str,
    coolant_mass_flow_kg_per_s: float,
    coolant_temperature_bulk_k: float,
    local_pressure_estimate_pa: float | None,
    coolant_roughness_m: float,
    *,
    coolant_wall_temperature_k: float | None = None,
    primary_coolant_nusselt_method: CoolantNusseltMethod = CoolantNusseltMethod.GNIELINSKI,
    coolant_bulk_temperature_reference_label: str = "iterated station mean",
    coolant_bulk_temperature_reference_reason: str = "T_b,c reference: iterated station mean of coolant inlet and outlet",
) -> _CoolantTransportState:
    """Evaluate the coolant-side transport state from the current station guess."""

    coolant_state = get_coolant_properties(coolant_type, coolant_temperature_bulk_k, local_pressure_estimate_pa)
    density_kg_per_m3 = max(coolant_state.density_kg_per_m3, 1.0e-12)
    area_annulus_m2 = max(station_geometry.area_annulus_m2, 1.0e-12)
    hydraulic_diameter_m = max(station_geometry.hydraulic_diameter_m, 1.0e-12)
    velocity_m_per_s = coolant_mass_flow_kg_per_s / (density_kg_per_m3 * area_annulus_m2)
    reynolds_number = (
        density_kg_per_m3 * velocity_m_per_s * hydraulic_diameter_m
        / max(coolant_state.viscosity_pa_s, 1.0e-12)
    )
    prandtl_number = _coolant_prandtl_number(coolant_state)
    friction_factor, friction_regime_label, friction_notes = _friction_factor(
        reynolds_number,
        coolant_roughness_m,
        hydraulic_diameter_m,
    )
    wall_viscosity_pa_s: float | None = None
    wall_property_notes: list[str] = []
    if coolant_wall_temperature_k is not None and coolant_wall_temperature_k > 0.0:
        coolant_wall_state = get_coolant_properties(
            coolant_type,
            coolant_wall_temperature_k,
            local_pressure_estimate_pa,
        )
        wall_viscosity_pa_s = coolant_wall_state.viscosity_pa_s
        wall_property_notes.extend(_split_note_string(coolant_wall_state.note))
    nusselt_result = _coolant_nusselt_correlations(
        reynolds_number,
        prandtl_number,
        friction_factor,
        mu_bulk_pa_s=coolant_state.viscosity_pa_s,
        mu_wall_pa_s=wall_viscosity_pa_s,
        method=primary_coolant_nusselt_method,
    )
    h_c_w_per_m2_k = (
        nusselt_result.selected_nusselt
        * coolant_state.thermal_conductivity_w_per_m_k
        / hydraulic_diameter_m
    )
    h_c_db = _nusselt_to_heat_transfer_coefficient(
        nusselt_result.dittus_boelter,
        coolant_state.thermal_conductivity_w_per_m_k,
        hydraulic_diameter_m,
    )
    h_c_st = _nusselt_to_heat_transfer_coefficient(
        nusselt_result.sieder_tate,
        coolant_state.thermal_conductivity_w_per_m_k,
        hydraulic_diameter_m,
    )
    h_c_gn = _nusselt_to_heat_transfer_coefficient(
        nusselt_result.gnielinski,
        coolant_state.thermal_conductivity_w_per_m_k,
        hydraulic_diameter_m,
    )
    transport_notes = [
        coolant_bulk_temperature_reference_reason,
        *_split_note_string(coolant_state.note),
        *wall_property_notes,
        *nusselt_result.notes,
        *(() if not nusselt_result.validity_note else (nusselt_result.validity_note,)),
        *friction_notes,
    ]
    if h_c_w_per_m2_k > 200_000.0:
        transport_notes.append(
            "coolant h_c very high for MVP annulus screening; validate with refined channel model"
        )
    pressure_drop_friction_pa = friction_factor * (
        station_length_m / hydraulic_diameter_m
    ) * 0.5 * density_kg_per_m3 * velocity_m_per_s**2
    # The MVP only carries the friction term numerically. These explicit zero
    # placeholders keep the result assembly ready for later minor-loss and
    # acceleration-loss terms without changing the public station fields again.
    pressure_drop_minor_pa = 0.0
    pressure_drop_acceleration_pa = 0.0

    return _CoolantTransportState(
        properties=coolant_state,
        velocity_m_per_s=velocity_m_per_s,
        prandtl_number=prandtl_number,
        reynolds_number=reynolds_number,
        nusselt_number=nusselt_result.selected_nusselt,
        nusselt_method=nusselt_result.selected_method.value,
        nusselt_dittus_boelter=nusselt_result.dittus_boelter,
        nusselt_sieder_tate=nusselt_result.sieder_tate,
        nusselt_gnielinski=nusselt_result.gnielinski,
        nusselt_spread_fraction=nusselt_result.spread_fraction,
        h_c_w_per_m2_k=h_c_w_per_m2_k,
        h_c_dittus_boelter_w_per_m2_k=h_c_db,
        h_c_sieder_tate_w_per_m2_k=h_c_st,
        h_c_gnielinski_w_per_m2_k=h_c_gn,
        friction_factor=friction_factor,
        coolant_regime_label=nusselt_result.regime_label,
        friction_regime_label=friction_regime_label,
        pressure_drop_friction_pa=pressure_drop_friction_pa,
        pressure_drop_minor_pa=pressure_drop_minor_pa,
        pressure_drop_acceleration_pa=pressure_drop_acceleration_pa,
        pressure_drop_total_pa=pressure_drop_friction_pa + pressure_drop_minor_pa + pressure_drop_acceleration_pa,
        bulk_temperature_reference_label=coolant_bulk_temperature_reference_label,
        bulk_temperature_reference_reason=coolant_bulk_temperature_reference_reason,
        wall_viscosity_pa_s=wall_viscosity_pa_s,
        sieder_tate_viscosity_ratio=nusselt_result.sieder_tate_viscosity_ratio,
        sieder_tate_correction_factor=nusselt_result.sieder_tate_correction_factor,
        notes=tuple(transport_notes),
    )


def _coolant_nusselt_correlations(
    reynolds_number: float,
    prandtl_number: float,
    friction_factor: float | None,
    *,
    mu_bulk_pa_s: float,
    mu_wall_pa_s: float | None,
    method: CoolantNusseltMethod,
) -> _CoolantNusseltCorrelationResult:
    """Return selected and background Nu_c values for the current station."""

    if reynolds_number <= 0.0:
        return _CoolantNusseltCorrelationResult(
            selected_method=method,
            selected_nusselt=0.0,
            dittus_boelter=None,
            sieder_tate=None,
            gnielinski=None,
            spread_fraction=None,
            regime_label="invalid",
            validity_note="invalid coolant Reynolds number",
            sieder_tate_viscosity_ratio=None,
            sieder_tate_correction_factor=None,
            notes=("invalid coolant Reynolds number",),
        )

    notes: list[str] = []
    validity_notes: list[str] = []
    laminar_nusselt = 3.66
    prandtl_positive = max(prandtl_number, 1.0e-12)
    sieder_tate_viscosity_ratio: float | None = None
    sieder_tate_correction_factor: float | None = None

    db_nusselt = 0.023 * reynolds_number**0.8 * prandtl_positive**0.4
    if reynolds_number < _COOLANT_TURBULENT_RE_MIN or not 0.7 <= prandtl_number <= 160.0:
        validity_notes.append(
            "coolant Nu validity: Dittus-Boelter guidance is Re >= 1e4 and 0.7 <= Pr <= 160"
        )

    st_nusselt: float | None = None
    if mu_wall_pa_s is None or mu_wall_pa_s <= 0.0:
        notes.append("wall viscosity missing for Sieder-Tate")
    else:
        sieder_tate_viscosity_ratio = mu_bulk_pa_s / max(mu_wall_pa_s, 1.0e-12)
        clamped_ratio = min(max(sieder_tate_viscosity_ratio, 0.05), 20.0)
        if not math.isclose(sieder_tate_viscosity_ratio, clamped_ratio):
            notes.append("Sieder-Tate viscosity ratio clamped")
        sieder_tate_correction_factor = clamped_ratio**0.14
        st_nusselt = 0.027 * reynolds_number**0.8 * prandtl_positive ** (1.0 / 3.0) * sieder_tate_correction_factor
        if reynolds_number < _COOLANT_TURBULENT_RE_MIN or not 0.7 <= prandtl_number <= 16_700.0:
            validity_notes.append(
                "coolant Nu validity: Sieder-Tate guidance is Re >= 1e4 and 0.7 <= Pr <= 16700"
            )

    gn_nusselt: float | None = None
    if friction_factor is None or friction_factor <= 0.0 or reynolds_number <= 1_000.0:
        notes.append("Gnielinski unavailable: invalid friction factor or Reynolds number")
    else:
        denominator = 1.0 + 12.7 * math.sqrt(friction_factor / 8.0) * (prandtl_positive ** (2.0 / 3.0) - 1.0)
        if denominator > 0.0:
            gn_nusselt = ((friction_factor / 8.0) * (reynolds_number - 1_000.0) * prandtl_positive) / denominator
        if reynolds_number < _GNIELINSKI_RE_MIN or reynolds_number > 5.0e6 or not 0.5 <= prandtl_number <= 2_000.0:
            validity_notes.append(
                "coolant Nu validity: Gnielinski guidance is 3e3 <= Re <= 5e6 and 0.5 <= Pr <= 2000"
            )

    available_turbulent = {
        CoolantNusseltMethod.DITTUS_BOELTER: db_nusselt,
        CoolantNusseltMethod.SIEDER_TATE: st_nusselt,
        CoolantNusseltMethod.GNIELINSKI: gn_nusselt,
    }
    selected_method = method
    selected_turbulent = available_turbulent.get(method)
    if selected_turbulent is None:
        for fallback_method in (
            CoolantNusseltMethod.GNIELINSKI,
            CoolantNusseltMethod.SIEDER_TATE,
            CoolantNusseltMethod.DITTUS_BOELTER,
        ):
            fallback_value = available_turbulent.get(fallback_method)
            if fallback_value is not None:
                selected_method = fallback_method
                selected_turbulent = fallback_value
                if fallback_method is not method:
                    notes.append(
                        f"coolant Nu method fallback: requested {method.value}, using {fallback_method.value}"
                    )
                break

    regime_label = "turbulent"
    selected_nusselt = selected_turbulent if selected_turbulent is not None else laminar_nusselt
    if reynolds_number < _COOLANT_LAMINAR_RE_MAX:
        regime_label = "laminar"
        selected_nusselt = laminar_nusselt
        selected_method = method
        notes.append("laminar annulus fallback Nu=3.66; turbulent Nu correlations are out of range")
        db_nusselt = None
        st_nusselt = None
        gn_nusselt = None
    elif reynolds_number < _COOLANT_TURBULENT_RE_MIN:
        regime_label = "transitional"
        interpolation = (reynolds_number - _COOLANT_LAMINAR_RE_MAX) / (
            _COOLANT_TURBULENT_RE_MIN - _COOLANT_LAMINAR_RE_MAX
        )
        selected_nusselt = _lerp(laminar_nusselt, selected_turbulent or laminar_nusselt, interpolation)
        notes.append("transition regime: coolant Nu correlation uncertain")

    available_values = [
        value for value in (db_nusselt, st_nusselt, gn_nusselt) if value is not None and value > 0.0
    ]
    spread_fraction = None
    if len(available_values) >= 2 and selected_nusselt > 0.0:
        spread_fraction = (max(available_values) - min(available_values)) / selected_nusselt
        if spread_fraction > 0.30:
            notes.append("coolant Nu correlation spread > 30%; thermal result is correlation-sensitive")

    if reynolds_number > 1.0e6:
        notes.append("coolant Re very high; Nu correlation range should be checked")
    if selected_nusselt > 3_000.0:
        notes.append("coolant Nu very high; verify geometry/properties/correlation")

    validity_note = ""
    if selected_method is CoolantNusseltMethod.DITTUS_BOELTER and (
        reynolds_number < _COOLANT_TURBULENT_RE_MIN or not 0.7 <= prandtl_number <= 160.0
    ):
        validity_note = "coolant Nu validity: selected Dittus-Boelter station is outside suggested guidance"
    elif selected_method is CoolantNusseltMethod.SIEDER_TATE and (
        st_nusselt is None or reynolds_number < _COOLANT_TURBULENT_RE_MIN or not 0.7 <= prandtl_number <= 16_700.0
    ):
        validity_note = "coolant Nu validity: selected Sieder-Tate station is outside suggested guidance"
    elif selected_method is CoolantNusseltMethod.GNIELINSKI and (
        gn_nusselt is None or reynolds_number < _GNIELINSKI_RE_MIN or reynolds_number > 5.0e6 or not 0.5 <= prandtl_number <= 2_000.0
    ):
        validity_note = "coolant Nu validity: selected Gnielinski station is outside suggested guidance"
    elif validity_notes:
        validity_note = validity_notes[0]

    return _CoolantNusseltCorrelationResult(
        selected_method=selected_method,
        selected_nusselt=selected_nusselt,
        dittus_boelter=db_nusselt,
        sieder_tate=st_nusselt,
        gnielinski=gn_nusselt,
        spread_fraction=spread_fraction,
        regime_label=regime_label,
        validity_note=validity_note,
        sieder_tate_viscosity_ratio=sieder_tate_viscosity_ratio,
        sieder_tate_correction_factor=sieder_tate_correction_factor,
        notes=tuple(notes),
    )


def _nusselt_to_heat_transfer_coefficient(
    nusselt_number: float | None,
    thermal_conductivity_w_per_m_k: float,
    hydraulic_diameter_m: float,
) -> float | None:
    if nusselt_number is None:
        return None
    return nusselt_number * thermal_conductivity_w_per_m_k / max(hydraulic_diameter_m, 1.0e-12)


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
    station_conductance_w_per_k: float,
    coolant_mass_flow_kg_per_s: float,
    coolant_cp_j_per_kg_k: float,
    solver_settings: SolverSettings,
) -> float:
    capacity_rate = max(coolant_mass_flow_kg_per_s * coolant_cp_j_per_kg_k, 1.0e-12)
    ntu = station_conductance_w_per_k / capacity_rate

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

    if solver_settings.solver_type is ThermalSolverType.SIMPSON_CONDUCTANCE:
        return recovery_temperature_k - (recovery_temperature_k - coolant_temperature_in_k) * math.exp(-ntu)

    # The NTU / exponential station model is the default because it gives a
    # compact closed-form station update without implying full transient fidelity.
    return recovery_temperature_k - (recovery_temperature_k - coolant_temperature_in_k) * math.exp(-ntu)


def _initial_wall_temperature_guess(
    recovery_temperature_k: float,
    coolant_temperature_in_k: float,
    previous_station_result: ThermalStationResult | None,
) -> float:
    """Seed the hot-wall iteration from the previous station when possible."""

    if previous_station_result is not None:
        previous_wall_temperature_k = previous_station_result.wall_temperature_hot_gas_side_k
        if previous_wall_temperature_k is not None:
            return _clamp_hot_wall_temperature(
                previous_wall_temperature_k,
                recovery_temperature_k,
                coolant_temperature_in_k,
            )
    return _clamp_hot_wall_temperature(
        coolant_temperature_in_k + 0.3 * (recovery_temperature_k - coolant_temperature_in_k),
        recovery_temperature_k,
        coolant_temperature_in_k,
    )


def _clamp_hot_wall_temperature(
    wall_temperature_k: float,
    recovery_temperature_k: float,
    coolant_temperature_in_k: float,
) -> float:
    """Keep the wall-temperature guess inside a physically meaningful range."""

    lower_bound_k = coolant_temperature_in_k + _SMALL_DELTA_K
    upper_bound_k = recovery_temperature_k - _SMALL_DELTA_K
    return min(upper_bound_k, max(lower_bound_k, wall_temperature_k))


def _clamp_coolant_outlet_temperature(
    coolant_temperature_out_k: float,
    coolant_temperature_in_k: float,
    recovery_temperature_k: float,
) -> float:
    """Keep the station outlet temperature between inlet and recovery limits."""

    lower_bound_k = coolant_temperature_in_k + _SMALL_DELTA_K
    upper_bound_k = recovery_temperature_k - _SMALL_DELTA_K
    return min(upper_bound_k, max(lower_bound_k, coolant_temperature_out_k))


def _finalize_station_solution(
    solution: _StationHeatBalanceResult,
    coolant_transport: _CoolantTransportState,
    throat_curvature_mode: BartzThroatCurvatureMode,
    *,
    converged: bool,
) -> _StationHeatBalanceResult:
    """Attach convergence and regime metadata to the last iteration result."""

    raw_status_notes = [
        f"gas-side h_g: Bartz ({throat_curvature_mode.value} Rc,t)",
        f"coolant regime: {coolant_transport.coolant_regime_label}",
        f"coolant Nu method: {coolant_transport.nusselt_method}",
        coolant_transport.bulk_temperature_reference_reason,
    ]
    if coolant_transport.friction_regime_label != coolant_transport.coolant_regime_label:
        raw_status_notes.append(f"coolant friction regime: {coolant_transport.friction_regime_label}")
    raw_status_notes.extend(coolant_transport.notes)
    raw_status_notes.extend(_split_note_string(solution.wall_material_properties.note))
    raw_status_notes.extend(solution.status_notes)
    if converged:
        raw_status_notes.append(f"converged in {solution.iterations} iterations")
    else:
        raw_status_notes.append("station did not converge within max iterations")

    status_notes: list[str] = []
    for note in raw_status_notes:
        if note not in status_notes:
            status_notes.append(note)

    return _StationHeatBalanceResult(
        h_g_w_per_m2_k=solution.h_g_w_per_m2_k,
        h_c_w_per_m2_k=solution.h_c_w_per_m2_k,
        recovery_temperature_k=solution.recovery_temperature_k,
        coolant_temperature_out_k=solution.coolant_temperature_out_k,
        coolant_temperature_bulk_k=solution.coolant_temperature_bulk_k,
        q_station_w=solution.q_station_w,
        q_hot_w_per_m2=solution.q_hot_w_per_m2,
        q_conv_w_per_m2=solution.q_conv_w_per_m2,
        q_rad_w_per_m2=solution.q_rad_w_per_m2,
        q_total_w_per_m2=solution.q_total_w_per_m2,
        q_radiation_station_w=solution.q_radiation_station_w,
        wall_temperature_coolant_side_k=solution.wall_temperature_coolant_side_k,
        wall_temperature_hot_gas_side_k=solution.wall_temperature_hot_gas_side_k,
        wall_delta_t_k=solution.wall_delta_t_k,
        coolant_bulk_temperature_reference_label=solution.coolant_bulk_temperature_reference_label,
        coolant_bulk_temperature_reference_reason=solution.coolant_bulk_temperature_reference_reason,
        radiation_temperature_k=solution.radiation_temperature_k,
        gas_effective_emissivity=solution.gas_effective_emissivity,
        wall_emissivity=solution.wall_emissivity,
        optical_path_length_m=solution.optical_path_length_m,
        radiation_model_note=solution.radiation_model_note,
        participating_species_mode=solution.participating_species_mode,
        participating_species_used=solution.participating_species_used,
        reynolds_coolant=solution.reynolds_coolant,
        prandtl_coolant=solution.prandtl_coolant,
        coolant_cp_j_per_kg_k=solution.coolant_cp_j_per_kg_k,
        coolant_viscosity_pa_s=solution.coolant_viscosity_pa_s,
        nusselt_coolant=solution.nusselt_coolant,
        nusselt_coolant_method=solution.nusselt_coolant_method,
        nusselt_dittus_boelter=solution.nusselt_dittus_boelter,
        nusselt_sieder_tate=solution.nusselt_sieder_tate,
        nusselt_gnielinski=solution.nusselt_gnielinski,
        nusselt_spread_fraction=solution.nusselt_spread_fraction,
        friction_factor=solution.friction_factor,
        h_c_dittus_boelter_w_per_m2_k=solution.h_c_dittus_boelter_w_per_m2_k,
        h_c_sieder_tate_w_per_m2_k=solution.h_c_sieder_tate_w_per_m2_k,
        h_c_gnielinski_w_per_m2_k=solution.h_c_gnielinski_w_per_m2_k,
        coolant_wall_viscosity_pa_s=solution.coolant_wall_viscosity_pa_s,
        sieder_tate_viscosity_ratio=solution.sieder_tate_viscosity_ratio,
        sieder_tate_correction_factor=solution.sieder_tate_correction_factor,
        gas_conductance_w_per_k=solution.gas_conductance_w_per_k,
        coolant_conductance_w_per_k=solution.coolant_conductance_w_per_k,
        gas_resistance_k_per_w=solution.gas_resistance_k_per_w,
        wall_resistance_k_per_w=solution.wall_resistance_k_per_w,
        coolant_resistance_k_per_w=solution.coolant_resistance_k_per_w,
        coolant_flow_area_m2=solution.coolant_flow_area_m2,
        coolant_wall_area_m2=solution.coolant_wall_area_m2,
        conductance_rule_label=solution.conductance_rule_label,
        solver_scheme_label=solution.solver_scheme_label,
        pressure_drop_station_pa=solution.pressure_drop_station_pa,
        wall_material_properties=solution.wall_material_properties,
        iterations=solution.iterations,
        converged=converged,
        residual_k=solution.residual_k,
        status_notes=tuple(status_notes),
    )


def _friction_factor(
    reynolds_number: float,
    roughness_m: float,
    hydraulic_diameter_m: float,
) -> tuple[float, str, tuple[str, ...]]:
    if reynolds_number <= 0.0:
        return 0.0, "invalid", ("invalid coolant Reynolds number",)
    if reynolds_number < _COOLANT_LAMINAR_RE_MAX:
        return 64.0 / reynolds_number, "laminar", ()
    relative_roughness = roughness_m / max(hydraulic_diameter_m, 1.0e-12)
    turbulent_friction_factor = 0.25 / (
        math.log10(relative_roughness / 3.7 + 5.74 / reynolds_number**0.9)
    ) ** 2
    if reynolds_number < _COOLANT_TURBULENT_RE_MIN:
        laminar_friction_factor = 64.0 / reynolds_number
        interpolation = (reynolds_number - _COOLANT_LAMINAR_RE_MAX) / (
            _COOLANT_TURBULENT_RE_MIN - _COOLANT_LAMINAR_RE_MAX
        )
        return (
            _lerp(laminar_friction_factor, turbulent_friction_factor, interpolation),
            "transitional",
            ("transition regime: coolant friction correlation uncertain",),
        )
    return turbulent_friction_factor, "turbulent", ()


def _wall_material_screening_limit_k(material: str) -> float:
    material_key = material.strip().lower()
    database = {
        "cucrzr": 820.0,
        "grcop-42": 950.0,
        "inconel 718": 1_100.0,
        "in718": 1_100.0,
        "316l stainless steel": 900.0,
        "316 stainless steel": 900.0,
        "316l": 900.0,
        "316": 900.0,
    }
    return database.get(material_key, 900.0)


def _resolved_wall_thickness_m(bundle: ExportBundle) -> float:
    wall_thickness_m = bundle.inputs.wall_thickness_m
    if wall_thickness_m is None or wall_thickness_m <= 0.0:
        return 1.5e-3
    return wall_thickness_m


def _route_default_closeout_enabled(route: ManufacturingRoute) -> bool:
    return route in {
        ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT,
        ManufacturingRoute.ELECTROFORMED_CLOSEOUT,
    }


def _resolved_closeout_configuration(bundle: ExportBundle) -> tuple[bool, float | None, str | None]:
    """Resolve closeout defaults from the committed material setup."""

    inputs = bundle.inputs
    closeout_enabled = bool(inputs.closeout_enabled)
    if (
        not closeout_enabled
        and inputs.closeout_thickness_m is None
        and inputs.closeout_material is None
        and _route_default_closeout_enabled(inputs.manufacturing_route)
    ):
        closeout_enabled = True
    if not closeout_enabled:
        return False, None, None
    closeout_thickness_m = inputs.closeout_thickness_m
    if closeout_thickness_m is None or closeout_thickness_m <= 0.0:
        closeout_thickness_m = 0.003
    closeout_material = (inputs.closeout_material or inputs.liner_material).strip() or inputs.liner_material
    return True, closeout_thickness_m, closeout_material


def _station_local_gas_pressure_pa(
    bundle: ExportBundle,
    sample: _SamplePoint,
) -> tuple[float, tuple[str, ...]]:
    """Return the local hot-gas pressure when available, otherwise chamber fallback."""

    profile_point = sample.profile_point
    if profile_point is not None:
        state = profile_point.state
        for candidate in (
            getattr(state, "pressure_pa", None),
            getattr(state, "static_pressure_pa", None),
            getattr(profile_point, "pressure_pa", None),
            getattr(profile_point, "static_pressure_pa", None),
        ):
            if candidate is not None and candidate > 0.0:
                return float(candidate), ()
    return bundle.inputs.chamber_pressure_pa, ("local gas pressure unavailable: chamber pressure fallback",)


def _station_local_coolant_pressure_pa(
    station: ThermalStationResult,
    fallback_pressure_pa: float,
) -> float:
    """Return the best available local coolant pressure for mechanical screening."""

    candidates = [
        value
        for value in (station.required_pressure_in_pa, station.required_pressure_out_pa)
        if value is not None and value > 0.0
    ]
    if len(candidates) == 2:
        return 0.5 * (candidates[0] + candidates[1])
    if candidates:
        return candidates[0]
    return fallback_pressure_pa


def _material_margin_status(margin: float | None) -> str:
    """Collapse the screening margin into a compact status label."""

    if margin is None:
        return "unknown"
    if margin < 0.0:
        return "exceeded"
    if margin < 0.25:
        return "low margin"
    return "ok"


def _compute_station_mechanical_screening(
    *,
    station: ThermalStationResult,
    gas_pressure_pa: float,
    coolant_pressure_pa: float,
    wall_thickness_m: float,
    wall_material_id: str,
    reference_temperature_k: float,
    closeout_enabled: bool,
    closeout_thickness_m: float | None,
    closeout_material_id: str | None,
) -> _MechanicalStationScreeningResult:
    """Compute first-order pressure and thermal screening for one station.

    The thermal part is intentionally a screening indicator, not a realized
    chamber-wall stress model. Mean thermal restraint defaults to zero for the
    MVP because a free chamber segment can expand globally, while through-wall
    gradient restraint stays as an elastic upper-bound indicator.
    """

    status_notes: list[str] = []
    mechanical_model_note = (
        "Mechanical results are predesign screening values. Pressure stresses use thin-shell assumptions. "
        "Thermal stresses are elastic restraint indicators; if they exceed Rp0.2(T), local plasticity/LCF evaluation and FEM are required."
    )
    wall_temperature_hot_gas_side_k = station.wall_temperature_hot_gas_side_k
    wall_temperature_coolant_side_k = station.wall_temperature_coolant_side_k
    if wall_temperature_hot_gas_side_k is None or wall_temperature_coolant_side_k is None:
        return _MechanicalStationScreeningResult(
            wall_mean_temperature_k=None,
            pressure_delta_pa=None,
            pressure_hoop_stress_pa=None,
            pressure_longitudinal_stress_pa=None,
            hoop_stress_pa=None,
            longitudinal_stress_pa=None,
            thermal_strain=None,
            free_mean_thermal_strain=None,
            differential_thermal_strain=None,
            thermal_stress_pa=None,
            thermal_membrane_stress_upper_bound_pa=None,
            thermal_gradient_stress_upper_bound_pa=None,
            equivalent_von_mises_stress_pa=None,
            von_mises_hot_side_pa=None,
            von_mises_cold_side_pa=None,
            material_yield_strength_pa=None,
            yield_strength_hot_side_pa=None,
            yield_strength_cold_side_pa=None,
            material_strength_margin=None,
            material_margin_hot_side=None,
            material_margin_cold_side=None,
            material_margin_status="unknown",
            plasticity_expected_hot_side=None,
            plasticity_expected_cold_side=None,
            closeout_thickness_m=closeout_thickness_m if closeout_enabled else None,
            closeout_material=closeout_material_id if closeout_enabled else None,
            closeout_hoop_stress_pa=None,
            closeout_material_yield_strength_pa=None,
            closeout_material_strength_margin=None,
            elastic_strain_pressure=None,
            elastic_strain_thermal=None,
            total_screening_strain=None,
            mechanical_model_note=mechanical_model_note,
            status_notes=("mechanical screening unavailable: missing wall temperature",),
        )

    wall_mean_temperature_k = 0.5 * (
        wall_temperature_hot_gas_side_k + wall_temperature_coolant_side_k
    )
    wall_delta_t_k = wall_temperature_hot_gas_side_k - wall_temperature_coolant_side_k
    pressure_delta_pa = coolant_pressure_pa - gas_pressure_pa
    pressure_delta_abs_pa = abs(pressure_delta_pa)
    if pressure_delta_pa < 0.0:
        status_notes.append(
            "gas pressure exceeds coolant pressure; pressure stress sign not represented in scalar screening output"
        )

    pressure_hoop_stress_pa = pressure_delta_abs_pa * station.r_inner_m / max(wall_thickness_m, 1.0e-12)
    pressure_longitudinal_stress_pa = pressure_delta_abs_pa * station.r_inner_m / max(
        2.0 * wall_thickness_m,
        1.0e-12,
    )
    hoop_stress_pa = pressure_hoop_stress_pa
    longitudinal_stress_pa = pressure_longitudinal_stress_pa

    wall_material_mean = get_material_properties(wall_material_id, wall_mean_temperature_k)
    wall_material_hot = get_material_properties(wall_material_id, wall_temperature_hot_gas_side_k)
    wall_material_cold = get_material_properties(wall_material_id, wall_temperature_coolant_side_k)
    for material_properties in (wall_material_mean, wall_material_hot, wall_material_cold):
        status_notes.extend(_split_note_string(material_properties.note))
    if wall_material_mean.source == "screening-table":
        status_notes.append("mechanical properties from screening table")
    else:
        status_notes.append("fallback material properties used for mechanical screening")

    modulus_mean_pa = wall_material_mean.youngs_modulus_pa
    alpha_mean_1_per_k = wall_material_mean.cte_1_per_k
    poisson_mean = wall_material_mean.poisson_ratio

    free_mean_thermal_strain = None
    if alpha_mean_1_per_k is not None:
        free_mean_thermal_strain = alpha_mean_1_per_k * (
            wall_mean_temperature_k - reference_temperature_k
        )
    differential_thermal_strain = None
    if alpha_mean_1_per_k is not None:
        differential_thermal_strain = alpha_mean_1_per_k * wall_delta_t_k

    sigma_mean_thermal_pa = None
    sigma_gradient_pa = None
    if (
        modulus_mean_pa is None
        or alpha_mean_1_per_k is None
        or poisson_mean is None
        or poisson_mean >= 1.0
    ):
        status_notes.append("thermal stress unavailable: missing material property")
    else:
        sigma_mean_thermal_pa = (
            -_DEFAULT_MEAN_THERMAL_RESTRAINT_FACTOR
            * modulus_mean_pa
            * (free_mean_thermal_strain or 0.0)
            / max(1.0 - poisson_mean, 1.0e-12)
        )
        sigma_gradient_pa = (
            _DEFAULT_GRADIENT_THERMAL_RESTRAINT_FACTOR
            * modulus_mean_pa
            * (differential_thermal_strain or 0.0)
            / max(2.0 * (1.0 - poisson_mean), 1.0e-12)
        )

    sigma_theta_hot_pa = pressure_hoop_stress_pa
    sigma_z_hot_pa = pressure_longitudinal_stress_pa
    sigma_theta_cold_pa = pressure_hoop_stress_pa
    sigma_z_cold_pa = pressure_longitudinal_stress_pa
    if sigma_mean_thermal_pa is not None:
        sigma_theta_hot_pa += sigma_mean_thermal_pa
        sigma_z_hot_pa += sigma_mean_thermal_pa
        sigma_theta_cold_pa += sigma_mean_thermal_pa
        sigma_z_cold_pa += sigma_mean_thermal_pa
    if sigma_gradient_pa is not None:
        sigma_theta_hot_pa -= sigma_gradient_pa
        sigma_z_hot_pa -= sigma_gradient_pa
        sigma_theta_cold_pa += sigma_gradient_pa
        sigma_z_cold_pa += sigma_gradient_pa

    von_mises_hot_side_pa = math.sqrt(
        max(
            sigma_theta_hot_pa * sigma_theta_hot_pa
            + sigma_z_hot_pa * sigma_z_hot_pa
            - sigma_theta_hot_pa * sigma_z_hot_pa,
            0.0,
        )
    )
    von_mises_cold_side_pa = math.sqrt(
        max(
            sigma_theta_cold_pa * sigma_theta_cold_pa
            + sigma_z_cold_pa * sigma_z_cold_pa
            - sigma_theta_cold_pa * sigma_z_cold_pa,
            0.0,
        )
    )
    equivalent_von_mises_stress_pa = max(von_mises_hot_side_pa, von_mises_cold_side_pa)

    yield_strength_hot_side_pa = wall_material_hot.yield_strength_pa
    yield_strength_cold_side_pa = wall_material_cold.yield_strength_pa
    yield_candidates = [
        value
        for value in (yield_strength_hot_side_pa, yield_strength_cold_side_pa)
        if value is not None and value > 0.0
    ]
    material_yield_strength_pa = min(yield_candidates) if yield_candidates else None

    material_margin_hot_side = None
    if yield_strength_hot_side_pa is not None and von_mises_hot_side_pa > 0.0:
        material_margin_hot_side = yield_strength_hot_side_pa / von_mises_hot_side_pa - 1.0
    material_margin_cold_side = None
    if yield_strength_cold_side_pa is not None and von_mises_cold_side_pa > 0.0:
        material_margin_cold_side = yield_strength_cold_side_pa / von_mises_cold_side_pa - 1.0
    margin_candidates = [
        value
        for value in (material_margin_hot_side, material_margin_cold_side)
        if value is not None
    ]
    material_strength_margin = min(margin_candidates) if margin_candidates else None
    if material_yield_strength_pa is None:
        status_notes.append("material margin unavailable: missing yield strength")
    material_margin_status = _material_margin_status(material_strength_margin)

    plasticity_expected_hot_side = None
    if yield_strength_hot_side_pa is not None:
        plasticity_expected_hot_side = von_mises_hot_side_pa > yield_strength_hot_side_pa
    plasticity_expected_cold_side = None
    if yield_strength_cold_side_pa is not None:
        plasticity_expected_cold_side = von_mises_cold_side_pa > yield_strength_cold_side_pa
    if plasticity_expected_hot_side or plasticity_expected_cold_side:
        status_notes.append(
            "elastic screening exceeds Rp0.2(T); local plasticity expected; use FEM/LCF assessment for final margin"
        )

    thermal_stress_pa = None
    if sigma_mean_thermal_pa is not None or sigma_gradient_pa is not None:
        thermal_stress_pa = max(
            abs(sigma_mean_thermal_pa or 0.0),
            abs(sigma_gradient_pa or 0.0),
        )

    elastic_strain_pressure = None
    if modulus_mean_pa is not None and modulus_mean_pa > 0.0 and equivalent_von_mises_stress_pa > 0.0:
        elastic_strain_pressure = equivalent_von_mises_stress_pa / modulus_mean_pa
    elastic_strain_thermal = (
        abs(differential_thermal_strain) if differential_thermal_strain is not None else None
    )
    total_screening_strain = None
    strain_candidates = [
        abs(value)
        for value in (elastic_strain_pressure, differential_thermal_strain)
        if value is not None
    ]
    if strain_candidates:
        total_screening_strain = max(strain_candidates)

    if material_strength_margin is not None and material_strength_margin < 0.0:
        status_notes.append(
            "material screening margin exceeded: increase wall thickness, add stringers, change material, reduce pressure delta, or redesign cooling geometry"
        )
    elif material_strength_margin is not None and material_strength_margin < 0.25:
        status_notes.append("low material screening margin")

    if total_screening_strain is not None and total_screening_strain > _HIGH_SCREENING_STRAIN_LIMIT:
        status_notes.append("strain screening value high; detailed structural analysis required")

    closeout_hoop_stress_pa = None
    closeout_material_yield_strength_pa = None
    closeout_material_strength_margin = None
    if closeout_enabled and closeout_thickness_m is not None and closeout_material_id is not None:
        closeout_hoop_stress_pa = (
            pressure_delta_abs_pa * station.r_outer_m / max(closeout_thickness_m, 1.0e-12)
        )
        closeout_material_properties = get_material_properties(
            closeout_material_id,
            wall_temperature_coolant_side_k,
        )
        status_notes.append(
            "closeout stress is screening-level shell estimate; local rib/closeout bending not modeled"
        )
        status_notes.extend(_split_note_string(closeout_material_properties.note))
        closeout_material_yield_strength_pa = closeout_material_properties.yield_strength_pa
        if (
            closeout_material_yield_strength_pa is not None
            and closeout_hoop_stress_pa is not None
            and closeout_hoop_stress_pa > 0.0
        ):
            closeout_material_strength_margin = (
                closeout_material_yield_strength_pa / closeout_hoop_stress_pa - 1.0
            )
        else:
            status_notes.append("closeout material margin unavailable")
        if closeout_material_strength_margin is not None and closeout_material_strength_margin < 0.0:
            status_notes.append(
                "closeout screening margin exceeded: increase closeout thickness, add stringers, change closeout material, or redesign load path"
            )

    return _MechanicalStationScreeningResult(
        wall_mean_temperature_k=wall_mean_temperature_k,
        pressure_delta_pa=pressure_delta_pa,
        pressure_hoop_stress_pa=pressure_hoop_stress_pa,
        pressure_longitudinal_stress_pa=pressure_longitudinal_stress_pa,
        hoop_stress_pa=hoop_stress_pa,
        longitudinal_stress_pa=longitudinal_stress_pa,
        thermal_strain=free_mean_thermal_strain,
        free_mean_thermal_strain=free_mean_thermal_strain,
        differential_thermal_strain=differential_thermal_strain,
        thermal_stress_pa=thermal_stress_pa,
        thermal_membrane_stress_upper_bound_pa=(
            abs(sigma_mean_thermal_pa) if sigma_mean_thermal_pa is not None else None
        ),
        thermal_gradient_stress_upper_bound_pa=(
            abs(sigma_gradient_pa) if sigma_gradient_pa is not None else None
        ),
        equivalent_von_mises_stress_pa=equivalent_von_mises_stress_pa,
        von_mises_hot_side_pa=von_mises_hot_side_pa,
        von_mises_cold_side_pa=von_mises_cold_side_pa,
        material_yield_strength_pa=material_yield_strength_pa,
        yield_strength_hot_side_pa=yield_strength_hot_side_pa,
        yield_strength_cold_side_pa=yield_strength_cold_side_pa,
        material_strength_margin=material_strength_margin,
        material_margin_hot_side=material_margin_hot_side,
        material_margin_cold_side=material_margin_cold_side,
        material_margin_status=material_margin_status,
        plasticity_expected_hot_side=plasticity_expected_hot_side,
        plasticity_expected_cold_side=plasticity_expected_cold_side,
        closeout_thickness_m=closeout_thickness_m if closeout_enabled else None,
        closeout_material=closeout_material_id if closeout_enabled else None,
        closeout_hoop_stress_pa=closeout_hoop_stress_pa,
        closeout_material_yield_strength_pa=closeout_material_yield_strength_pa,
        closeout_material_strength_margin=closeout_material_strength_margin,
        elastic_strain_pressure=elastic_strain_pressure,
        elastic_strain_thermal=elastic_strain_thermal,
        total_screening_strain=total_screening_strain,
        mechanical_model_note=mechanical_model_note,
        status_notes=tuple(status_notes),
    )


def _apply_mechanical_screening(
    stations: list[ThermalStationResult],
    *,
    station_samples: list[_SamplePoint],
    bundle: ExportBundle,
    thermal_inputs: ThermalAnalysisInputs,
    wall_thickness_m: float,
) -> None:
    """Update station results with post-processed mechanical screening values."""

    closeout_enabled, closeout_thickness_m, closeout_material_id = _resolved_closeout_configuration(bundle)
    coolant_pressure_fallback_pa = _reference_coolant_pressure_estimate_pa(bundle, thermal_inputs)
    for station, sample in zip(stations, station_samples):
        gas_pressure_pa, gas_pressure_notes = _station_local_gas_pressure_pa(bundle, sample)
        coolant_pressure_pa = _station_local_coolant_pressure_pa(
            station,
            coolant_pressure_fallback_pa,
        )
        screening = _compute_station_mechanical_screening(
            station=station,
            gas_pressure_pa=gas_pressure_pa,
            coolant_pressure_pa=coolant_pressure_pa,
            wall_thickness_m=wall_thickness_m,
            wall_material_id=bundle.inputs.liner_material,
            reference_temperature_k=_MECHANICAL_REFERENCE_TEMPERATURE_K,
            closeout_enabled=closeout_enabled,
            closeout_thickness_m=closeout_thickness_m,
            closeout_material_id=closeout_material_id,
        )
        station.wall_mean_temperature_k = screening.wall_mean_temperature_k
        station.pressure_delta_pa = screening.pressure_delta_pa
        station.pressure_hoop_stress_pa = screening.pressure_hoop_stress_pa
        station.pressure_longitudinal_stress_pa = screening.pressure_longitudinal_stress_pa
        station.hoop_stress_pa = screening.hoop_stress_pa
        station.longitudinal_stress_pa = screening.longitudinal_stress_pa
        station.thermal_strain = screening.thermal_strain
        station.free_mean_thermal_strain = screening.free_mean_thermal_strain
        station.differential_thermal_strain = screening.differential_thermal_strain
        station.thermal_stress_pa = screening.thermal_stress_pa
        station.thermal_membrane_stress_upper_bound_pa = screening.thermal_membrane_stress_upper_bound_pa
        station.thermal_gradient_stress_upper_bound_pa = screening.thermal_gradient_stress_upper_bound_pa
        station.equivalent_von_mises_stress_pa = screening.equivalent_von_mises_stress_pa
        station.von_mises_hot_side_pa = screening.von_mises_hot_side_pa
        station.von_mises_cold_side_pa = screening.von_mises_cold_side_pa
        station.material_yield_strength_pa = screening.material_yield_strength_pa
        station.yield_strength_hot_side_pa = screening.yield_strength_hot_side_pa
        station.yield_strength_cold_side_pa = screening.yield_strength_cold_side_pa
        station.material_strength_margin = screening.material_strength_margin
        station.material_margin_hot_side = screening.material_margin_hot_side
        station.material_margin_cold_side = screening.material_margin_cold_side
        station.material_margin_status = screening.material_margin_status
        station.plasticity_expected_hot_side = screening.plasticity_expected_hot_side
        station.plasticity_expected_cold_side = screening.plasticity_expected_cold_side
        station.closeout_thickness_m = screening.closeout_thickness_m
        station.closeout_material = screening.closeout_material
        station.closeout_hoop_stress_pa = screening.closeout_hoop_stress_pa
        station.closeout_material_yield_strength_pa = screening.closeout_material_yield_strength_pa
        station.closeout_material_strength_margin = screening.closeout_material_strength_margin
        station.elastic_strain_pressure = screening.elastic_strain_pressure
        station.elastic_strain_thermal = screening.elastic_strain_thermal
        station.total_screening_strain = screening.total_screening_strain
        station.mechanical_model_note = screening.mechanical_model_note
        _append_station_notes(station, *gas_pressure_notes, *screening.status_notes)


def _resolved_throat_curvature_radius_m(
    bundle: ExportBundle,
    curvature_mode: BartzThroatCurvatureMode,
) -> float:
    """Return the constant Bartz throat-curvature radius used along the contour."""

    throat_radius_m = max(bundle.geometry.throat_radius_m, 1.0e-12)
    upstream_radius_m = bundle.inputs.throat_upstream_radius_m
    downstream_radius_m = bundle.inputs.throat_downstream_radius_m
    if upstream_radius_m is None or upstream_radius_m <= 0.0:
        upstream_radius_m = 1.5 * throat_radius_m
    if downstream_radius_m is None or downstream_radius_m <= 0.0:
        downstream_radius_m = 0.382 * throat_radius_m
    if curvature_mode is BartzThroatCurvatureMode.DOWNSTREAM:
        return downstream_radius_m
    if curvature_mode is BartzThroatCurvatureMode.MEAN:
        return 0.5 * (upstream_radius_m + downstream_radius_m)
    return upstream_radius_m


def _build_summary(
    stations: list[ThermalStationResult],
    scenario: ThermalScenario,
    pressure_summary: _PressureSummary,
) -> ThermalAnalysisSummary:
    thermal_inputs = scenario.global_conditions
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
    q_radiation_values = [
        station.q_radiation_station_w
        for station in stations
        if station.q_radiation_station_w is not None
    ]
    q_radiation_flux_values = [
        station.q_rad_w_per_m2
        for station in stations
        if station.q_rad_w_per_m2 is not None
    ]
    von_mises_values = [
        station.equivalent_von_mises_stress_pa
        for station in stations
        if station.equivalent_von_mises_stress_pa is not None
    ]
    material_margin_values = [
        station.material_strength_margin
        for station in stations
        if station.material_strength_margin is not None
    ]
    thermal_stress_values = [
        station.thermal_stress_pa
        for station in stations
        if station.thermal_stress_pa is not None
    ]
    thermal_strain_values = [
        station.thermal_strain
        for station in stations
        if station.thermal_strain is not None
    ]
    total_strain_values = [
        station.total_screening_strain
        for station in stations
        if station.total_screening_strain is not None
    ]
    closeout_margin_values = [
        station.closeout_material_strength_margin
        for station in stations
        if station.closeout_material_strength_margin is not None
    ]
    nusselt_spread_values = [
        station.nusselt_spread_fraction
        for station in stations
        if station.nusselt_spread_fraction is not None
    ]
    scenario_summary = _thermal_scenario_summary_strings(scenario)

    total_heat_w = sum(q_values) if q_values else None
    total_radiation_heat_w = sum(q_radiation_values) if q_radiation_values else 0.0
    coolant_outlet_temperature_k = stations[-1].coolant_temperature_out_k if stations else None
    delta_h_regen = None
    if total_heat_w is not None and thermal_inputs.coolant_mass_flow_kg_per_s not in {None, 0.0}:
        delta_h_regen = total_heat_w / thermal_inputs.coolant_mass_flow_kg_per_s
    property_warning_count = sum(
        1
        for station in stations
        if any(
            marker in station.status
            for marker in (
                "fallback",
                "outside table range",
                "oxygen property state is not liquid",
            )
        )
    )
    outside_range_count = sum(
        1 for station in stations if "outside table range" in station.status
    )
    nusselt_validity_warning_count = sum(
        1 for station in stations if "coolant Nu validity:" in station.status
    )
    high_h_c_count = sum(
        1 for station in stations if "coolant h_c very high" in station.status
    )
    coolant_property_source = _summary_source_label(stations, "coolant")
    material_property_source = _summary_source_label(stations, "material")

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
        thermal_scenario_name=scenario.name,
        primary_coolant_nusselt_method=thermal_inputs.primary_coolant_nusselt_method.value,
        nusselt_comparison_enabled=scenario.solver_plan.run_parallel_nusselt_comparison,
        active_mechanisms_summary=scenario_summary[0],
        global_conditions_summary=scenario_summary[1],
        station_condition_summary=scenario_summary[2],
        coolant_property_source=coolant_property_source,
        material_property_source=material_property_source,
        stations_with_property_warnings=property_warning_count,
        stations_outside_property_table_range=outside_range_count,
        max_nusselt_spread_fraction=max(nusselt_spread_values) if nusselt_spread_values else None,
        stations_with_large_nusselt_spread=sum(
            1 for value in nusselt_spread_values if value > 0.30
        ),
        stations_outside_nusselt_validity=nusselt_validity_warning_count,
        stations_with_high_h_c=high_h_c_count,
        total_radiation_heat_w=total_radiation_heat_w,
        max_radiation_heat_flux_w_per_m2=max(q_radiation_flux_values) if q_radiation_flux_values else 0.0,
        radiation_fraction_of_total_heat=(
            total_radiation_heat_w / total_heat_w
            if total_heat_w not in {None, 0.0}
            else 0.0
        ),
        radiation_enabled=thermal_inputs.radiation_settings.enabled,
        max_von_mises_stress_pa=max(von_mises_values) if von_mises_values else None,
        min_material_strength_margin=min(material_margin_values) if material_margin_values else None,
        max_thermal_stress_pa=max(thermal_stress_values) if thermal_stress_values else None,
        max_thermal_strain=max(thermal_strain_values) if thermal_strain_values else None,
        max_total_screening_strain=max(total_strain_values) if total_strain_values else None,
        stations_with_material_margin_exceeded=sum(
            1 for station in stations if station.material_margin_status == "exceeded"
        ),
        stations_with_low_material_margin=sum(
            1 for station in stations if station.material_margin_status == "low margin"
        ),
        closeout_min_material_strength_margin=min(closeout_margin_values) if closeout_margin_values else None,
    )


def _thermal_scenario_summary_strings(scenario: ThermalScenario) -> tuple[str, str, str]:
    """Return compact readable summary lines for the modular thermal scenario."""

    thermal_inputs = scenario.global_conditions
    active_mechanisms = [
        mechanism
        for mechanism in scenario.mechanisms
        if mechanism.enabled and mechanism.mechanism_type not in {
            ThermalMechanismType.FILM_COOLING_FUTURE,
            ThermalMechanismType.CHANNEL_RIB_NETWORK_FUTURE,
        }
    ]
    active_mechanisms_summary = ", ".join(
        mechanism.mechanism_type.value for mechanism in active_mechanisms
    ) or "none"
    global_conditions_summary = (
        f"Coolant {thermal_inputs.coolant_type} enters at {thermal_inputs.coolant_inlet_temperature_k:.2f} K, "
        f"flow path {thermal_inputs.flow_direction.value}, pressure mode {thermal_inputs.solver_settings.pressure_mode.value}, "
        f"primary Nu_c {thermal_inputs.primary_coolant_nusselt_method.value}, "
        f"solver scheme {_solver_scheme_label(thermal_inputs.solver_settings.solver_type)}"
    )
    station_condition_summary = ", ".join(
        condition.condition_type.value
        for condition in scenario.conditions
        if condition.enabled
    ) or "full contour"
    return active_mechanisms_summary, global_conditions_summary, station_condition_summary


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


def _split_note_string(note: str | None) -> tuple[str, ...]:
    if note is None:
        return ()
    return tuple(part.strip() for part in note.split(",") if part.strip())


def _note_is_warning(note: str) -> bool:
    """Classify station notes into searchable warnings versus normal status."""

    normalized_note = note.strip().lower()
    if not normalized_note or normalized_note == "ok":
        return False
    warning_markers = (
        "warning",
        "uncertain",
        "fallback",
        "outside table range",
        "not liquid",
        "did not converge",
        "invalid",
        "above material screening limit",
        "screening margin exceeded",
        "low material screening margin",
        "structural analysis required",
        "plasticity expected",
        "thermal stress unavailable",
        "material margin unavailable",
        "closeout material margin unavailable",
        "local gas pressure unavailable",
        "clamped",
        "placeholder",
        "suspicious",
        "no local cea species mole fractions available",
        "species fractions available but not confirmed as mole fractions",
        "insufficient outlet pressure",
    )
    return any(marker in normalized_note for marker in warning_markers)


def _split_station_notes(notes: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separate station notes into compact status and warning groups."""

    status_notes: list[str] = []
    warning_notes: list[str] = []
    for note in notes:
        target = warning_notes if _note_is_warning(note) else status_notes
        if note not in target:
            target.append(note)
    return tuple(status_notes), tuple(warning_notes)


def _join_station_note_group(notes: tuple[str, ...], *, empty_value: str) -> str:
    """Render one station-note group as a compact semicolon-separated string."""

    return "; ".join(notes) if notes else empty_value


def _station_note_tuple_add(notes: tuple[str, ...], *new_notes: str) -> tuple[str, ...]:
    """Append station notes without duplicating existing entries."""

    merged = list(notes)
    for note in new_notes:
        cleaned = note.strip()
        if cleaned and cleaned not in merged:
            merged.append(cleaned)
    return tuple(merged)


def _refresh_station_note_strings(station: ThermalStationResult) -> None:
    """Rebuild the compact text fields after status/warning notes change."""

    station.status_summary = _join_station_note_group(station.status_notes, empty_value="ok")
    station.warning_summary = _join_station_note_group(station.warning_notes, empty_value="--")
    all_notes = station.status_notes + tuple(note for note in station.warning_notes if note not in station.status_notes)
    station.status = ", ".join(all_notes) if all_notes else "ok"


def _append_station_notes(station: ThermalStationResult, *notes: str) -> None:
    """Classify and append new notes to the station result in place."""

    for note in notes:
        cleaned = note.strip()
        if not cleaned:
            continue
        if _note_is_warning(cleaned):
            station.warning_notes = _station_note_tuple_add(station.warning_notes, cleaned)
        else:
            station.status_notes = _station_note_tuple_add(station.status_notes, cleaned)
    _refresh_station_note_strings(station)


def _summary_source_label(stations: list[ThermalStationResult], family: str) -> str | None:
    """Collapse station-level source notes into one compact summary label."""

    if not stations:
        return None
    status_blob = " | ".join(station.status for station in stations)
    if family == "coolant":
        if "fallback constant coolant properties used" in status_blob:
            return "mixed/fallback"
        if "coolant properties from table" in status_blob:
            return "table"
        return None
    if "fallback material properties used" in status_blob:
        return "mixed/fallback"
    if "material properties from screening table" in status_blob:
        return "screening-table"
    return None


@dataclass(slots=True)
class _PressureSummary:
    required_cooling_inlet_pressure_pa: float | None
    required_pump_discharge_pressure_pa: float | None
    note: str


def _first_positive(*values: float | None, default_value: float) -> float:
    """Return the first physically usable value from an ordered fallback chain."""

    for value in values:
        if value is not None and value > 0.0:
            return value
    return default_value


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

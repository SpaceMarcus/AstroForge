"""Coupled hot-gas, wall and variable-channel regenerative analysis."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from engine.cooling.channel_flow import (
    ChannelCircuitResult,
    ChannelTransportState,
    PropertyProvider,
    channel_fin_area_factor,
    march_channel_circuit,
)
from engine.cooling.models import ChannelLayout, CoolantCircuit
from engine.models import ExportBundle, ThermochemistryProfilePoint
from engine.properties import (
    MaterialProperties,
    get_coolant_properties,
    get_material_properties,
)
from engine.station_mesh import EngineStation, EngineStationMesh, build_engine_station_mesh


_STEFAN_BOLTZMANN_W_PER_M2_K4 = 5.670374419e-8


@dataclass(frozen=True, slots=True)
class CoupledThermalSettings:
    wall_material_id: str = "CuCrZr"
    radiation_enabled: bool = True
    wall_emissivity: float = 0.70
    gas_effective_emissivity: float = 0.15
    throat_curvature_mode: str = "upstream"
    initial_heat_flux_w_per_m2: float = 5.0e6
    maximum_iterations: int = 40
    wall_temperature_tolerance_k: float = 0.25
    relaxation_factor: float = 0.55

    def __post_init__(self) -> None:
        if not self.wall_material_id.strip():
            raise ValueError("Wall material ID must not be empty.")
        for label, value in (
            ("wall emissivity", self.wall_emissivity),
            ("gas effective emissivity", self.gas_effective_emissivity),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{label} must lie in [0, 1].")
        if self.throat_curvature_mode not in {"upstream", "mean", "downstream"}:
            raise ValueError("Throat curvature mode must be upstream, mean or downstream.")
        if not math.isfinite(self.initial_heat_flux_w_per_m2) or self.initial_heat_flux_w_per_m2 <= 0.0:
            raise ValueError("Initial heat flux must be positive.")
        if self.maximum_iterations < 1:
            raise ValueError("Maximum thermal iterations must be at least one.")
        if self.wall_temperature_tolerance_k <= 0.0:
            raise ValueError("Wall-temperature tolerance must be positive.")
        if not 0.0 < self.relaxation_factor <= 1.0:
            raise ValueError("Thermal relaxation factor must lie in (0, 1].")


@dataclass(frozen=True, slots=True)
class CoupledThermalStation:
    station: EngineStation
    coolant_temperature_k: float
    coolant_pressure_pa: float
    recovery_temperature_k: float
    gas_temperature_k: float
    gas_heat_transfer_coefficient_w_per_m2_k: float
    coolant_heat_transfer_coefficient_w_per_m2_k: float
    effective_coolant_heat_transfer_coefficient_w_per_m2_k: float
    channel_fin_area_factor: float
    convective_heat_flux_w_per_m2: float
    radiation_heat_flux_w_per_m2: float
    total_heat_flux_w_per_m2: float
    wall_temperature_hot_gas_side_k: float
    wall_temperature_coolant_side_k: float
    wall_thermal_conductivity_w_per_m_k: float
    transport: ChannelTransportState
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CoupledRegenerativeResult:
    channel_result: ChannelCircuitResult
    stations: tuple[CoupledThermalStation, ...]
    converged: bool
    iterations: int
    residual_k: float
    total_heat_into_coolant_w: float
    maximum_total_heat_flux_w_per_m2: float
    maximum_hot_wall_temperature_k: float
    maximum_coolant_wall_temperature_k: float
    coolant_outlet_temperature_k: float
    coolant_outlet_pressure_pa: float
    notes: tuple[str, ...] = ()


MaterialProvider = Callable[[str, float], MaterialProperties]


@dataclass(frozen=True, slots=True)
class _GasState:
    gas_temperature_k: float
    recovery_temperature_k: float
    cp_j_per_kg_k: float
    viscosity_pa_s: float
    prandtl_number: float
    gamma: float
    mach_number: float


def run_coupled_regenerative_analysis(
    bundle: ExportBundle,
    layout: ChannelLayout,
    circuit: CoolantCircuit,
    *,
    settings: CoupledThermalSettings | None = None,
    station_mesh: EngineStationMesh | None = None,
    coolant_property_provider: PropertyProvider = get_coolant_properties,
    material_property_provider: MaterialProvider = get_material_properties,
) -> CoupledRegenerativeResult:
    """Iterate Bartz/radiation, wall conduction and channel coolant heating."""

    if len(bundle.contour) < 2:
        raise ValueError("Coupled regenerative analysis requires a committed contour.")
    settings = settings or CoupledThermalSettings(
        wall_material_id=bundle.inputs.liner_material,
    )
    mesh = station_mesh or build_engine_station_mesh(bundle.contour)
    heat_flux = [settings.initial_heat_flux_w_per_m2] * len(mesh.stations)
    previous_hot_wall: dict[str, float] = {}
    converged = False
    residual = math.inf
    station_solutions: list[CoupledThermalStation] = []
    channel_result: ChannelCircuitResult | None = None

    for iteration in range(1, settings.maximum_iterations + 1):
        channel_result = march_channel_circuit(
            mesh,
            layout,
            circuit,
            hot_wall_heat_flux_w_per_m2=heat_flux,
            property_provider=coolant_property_provider,
        )
        coolant_by_station = {
            row.station.station_id: row for row in channel_result.stations
        }
        new_solutions: list[CoupledThermalStation] = []
        raw_heat_flux: list[float] = []
        residual = 0.0
        for station in mesh.stations:
            coolant_row = coolant_by_station[station.station_id]
            solution = _solve_coupled_station(
                bundle=bundle,
                station=station,
                layout=layout,
                coolant_temperature_k=coolant_row.coolant_temperature_k,
                coolant_pressure_pa=coolant_row.coolant_pressure_pa,
                transport=coolant_row.transport,
                settings=settings,
                material_property_provider=material_property_provider,
            )
            new_solutions.append(solution)
            raw_heat_flux.append(solution.total_heat_flux_w_per_m2)
            old_temperature = previous_hot_wall.get(station.station_id)
            if old_temperature is not None:
                residual = max(
                    residual,
                    abs(solution.wall_temperature_hot_gas_side_k - old_temperature),
                )
        station_solutions = new_solutions
        previous_hot_wall = {
            row.station.station_id: row.wall_temperature_hot_gas_side_k
            for row in station_solutions
        }
        if iteration > 1 and residual <= settings.wall_temperature_tolerance_k:
            heat_flux = raw_heat_flux
            converged = True
            break
        heat_flux = [
            previous + settings.relaxation_factor * (raw - previous)
            for previous, raw in zip(heat_flux, raw_heat_flux)
        ]

    # Re-march once with the final heat-flux field so energy, pressure and the
    # reported station temperatures all refer to the same converged load.
    channel_result = march_channel_circuit(
        mesh,
        layout,
        circuit,
        hot_wall_heat_flux_w_per_m2=heat_flux,
        property_provider=coolant_property_provider,
    )
    coolant_by_station = {
        row.station.station_id: row for row in channel_result.stations
    }
    station_solutions = [
        _solve_coupled_station(
            bundle=bundle,
            station=station,
            layout=layout,
            coolant_temperature_k=coolant_by_station[station.station_id].coolant_temperature_k,
            coolant_pressure_pa=coolant_by_station[station.station_id].coolant_pressure_pa,
            transport=coolant_by_station[station.station_id].transport,
            settings=settings,
            material_property_provider=material_property_provider,
        )
        for station in mesh.stations
    ]
    notes = [
        "gas-side convection: Bartz",
        "coolant-side convection: canonical channel transport with rib/fin area factor",
        "wall conduction: local temperature-dependent material table",
    ]
    if settings.radiation_enabled:
        notes.append("radiation: grey-gas effective-emissivity screening model")
    if not converged:
        notes.append("coupled thermal iteration did not meet the requested tolerance")
    return CoupledRegenerativeResult(
        channel_result=channel_result,
        stations=tuple(station_solutions),
        converged=converged,
        iterations=iteration,
        residual_k=residual,
        total_heat_into_coolant_w=channel_result.total_heat_added_w,
        maximum_total_heat_flux_w_per_m2=max(
            row.total_heat_flux_w_per_m2 for row in station_solutions
        ),
        maximum_hot_wall_temperature_k=max(
            row.wall_temperature_hot_gas_side_k for row in station_solutions
        ),
        maximum_coolant_wall_temperature_k=max(
            row.wall_temperature_coolant_side_k for row in station_solutions
        ),
        coolant_outlet_temperature_k=channel_result.outlet_temperature_k,
        coolant_outlet_pressure_pa=channel_result.outlet_pressure_pa,
        notes=tuple(notes),
    )


def _solve_coupled_station(
    *,
    bundle: ExportBundle,
    station: EngineStation,
    layout: ChannelLayout,
    coolant_temperature_k: float,
    coolant_pressure_pa: float,
    transport: ChannelTransportState,
    settings: CoupledThermalSettings,
    material_property_provider: MaterialProvider,
) -> CoupledThermalStation:
    gas = _gas_state(bundle, station)
    section = layout.section_at(station.s_m)
    equivalent_height = (
        section.single_channel_area_m2 / section.hot_wall_width_per_channel_m
    )
    if section.rib_width_m > 0.0:
        trial_material = material_property_provider(
            settings.wall_material_id,
            0.5 * (coolant_temperature_k + gas.recovery_temperature_k),
        )
        trial_conductivity = _material_conductivity(trial_material)
        fin_factor = channel_fin_area_factor(
            channel_width_m=section.hot_wall_width_per_channel_m,
            channel_height_m=equivalent_height,
            rib_width_m=section.rib_width_m,
            coolant_heat_transfer_coefficient_w_per_m2_k=(
                transport.heat_transfer_coefficient_w_per_m2_k
            ),
            wall_thermal_conductivity_w_per_m_k=trial_conductivity,
        )
    else:
        fin_factor = 1.0
    effective_h_c = transport.heat_transfer_coefficient_w_per_m2_k * fin_factor
    lower = coolant_temperature_k + 1.0e-6
    upper = max(gas.recovery_temperature_k, gas.gas_temperature_k) - 1.0e-6
    if upper <= lower:
        upper = lower + 1.0

    def balance(hot_wall_temperature_k: float):
        material = material_property_provider(
            settings.wall_material_id,
            0.5 * (hot_wall_temperature_k + coolant_temperature_k),
        )
        conductivity = _material_conductivity(material)
        h_g = _bartz_heat_transfer_coefficient(
            bundle,
            station,
            gas,
            hot_wall_temperature_k,
            settings.throat_curvature_mode,
        )
        q_conv = h_g * max(
            gas.recovery_temperature_k - hot_wall_temperature_k,
            0.0,
        )
        q_rad = _radiation_heat_flux(
            gas.gas_temperature_k,
            hot_wall_temperature_k,
            settings,
        )
        cold_conductance = 1.0 / (
            section.hot_wall_thickness_m / conductivity + 1.0 / effective_h_c
        )
        q_cold = cold_conductance * (
            hot_wall_temperature_k - coolant_temperature_k
        )
        return q_conv + q_rad - q_cold, q_conv, q_rad, q_cold, h_g, conductivity, material

    lower_balance = balance(lower)[0]
    upper_balance = balance(upper)[0]
    if lower_balance < 0.0:
        hot_wall = lower
    elif upper_balance > 0.0:
        hot_wall = upper
    else:
        for _ in range(70):
            midpoint = 0.5 * (lower + upper)
            midpoint_balance = balance(midpoint)[0]
            if midpoint_balance > 0.0:
                lower = midpoint
            else:
                upper = midpoint
        hot_wall = 0.5 * (lower + upper)
    _residual, q_conv, q_rad, q_total, h_g, wall_k, material = balance(hot_wall)
    coolant_wall = coolant_temperature_k + q_total / effective_h_c
    notes = list(transport.notes)
    if material.note:
        notes.extend(
            part.strip() for part in material.note.split(";") if part.strip()
        )
    return CoupledThermalStation(
        station=station,
        coolant_temperature_k=coolant_temperature_k,
        coolant_pressure_pa=coolant_pressure_pa,
        recovery_temperature_k=gas.recovery_temperature_k,
        gas_temperature_k=gas.gas_temperature_k,
        gas_heat_transfer_coefficient_w_per_m2_k=h_g,
        coolant_heat_transfer_coefficient_w_per_m2_k=(
            transport.heat_transfer_coefficient_w_per_m2_k
        ),
        effective_coolant_heat_transfer_coefficient_w_per_m2_k=effective_h_c,
        channel_fin_area_factor=fin_factor,
        convective_heat_flux_w_per_m2=q_conv,
        radiation_heat_flux_w_per_m2=q_rad,
        total_heat_flux_w_per_m2=q_total,
        wall_temperature_hot_gas_side_k=hot_wall,
        wall_temperature_coolant_side_k=coolant_wall,
        wall_thermal_conductivity_w_per_m_k=wall_k,
        transport=transport,
        notes=tuple(dict.fromkeys(notes)),
    )


def _gas_state(bundle: ExportBundle, station: EngineStation) -> _GasState:
    profile_point = _nearest_profile_point(bundle, station)
    state = profile_point.state if profile_point is not None else None
    thermo = bundle.thermochemistry
    gas_temperature = _positive_or(
        getattr(state, "temperature_k", None),
        thermo.chamber_temperature_k,
    )
    cp = _positive_or(getattr(state, "cp_j_per_kg_k", None), thermo.cp_j_per_kg_k, 3_200.0)
    viscosity = _positive_or(getattr(state, "viscosity_pa_s", None), thermo.viscosity_pa_s, 8.0e-5)
    prandtl = _positive_or(getattr(state, "prandtl_number", None), thermo.prandtl_number, 0.70)
    gamma = _positive_or(getattr(state, "gamma", None), thermo.gamma, 1.20)
    mach = max(getattr(state, "mach_number", None) or 0.0, 0.0)
    recovery = getattr(state, "adiabatic_wall_temperature_k", None)
    if recovery is None or recovery <= 0.0:
        recovery_factor = prandtl ** (1.0 / 3.0)
        recovery = gas_temperature * (
            1.0 + recovery_factor * 0.5 * (gamma - 1.0) * mach**2
        )
    return _GasState(
        gas_temperature_k=gas_temperature,
        recovery_temperature_k=recovery,
        cp_j_per_kg_k=cp,
        viscosity_pa_s=viscosity,
        prandtl_number=prandtl,
        gamma=gamma,
        mach_number=mach,
    )


def _nearest_profile_point(
    bundle: ExportBundle,
    station: EngineStation,
) -> ThermochemistryProfilePoint | None:
    if not bundle.thermochemistry_profile:
        return None
    return min(
        bundle.thermochemistry_profile,
        key=lambda point: abs(point.x_m - station.x_m),
    )


def _bartz_heat_transfer_coefficient(
    bundle: ExportBundle,
    station: EngineStation,
    gas: _GasState,
    wall_temperature_k: float,
    curvature_mode: str,
) -> float:
    throat_diameter = 2.0 * bundle.geometry.throat_radius_m
    throat_curvature = _throat_curvature_radius(bundle, curvature_mode)
    local_area_ratio = max(
        station.area_m2 / bundle.geometry.throat_area_m2,
        1.0,
    )
    mach_term = 1.0 + 0.5 * (gas.gamma - 1.0) * gas.mach_number**2
    sigma_term = (
        0.5
        * wall_temperature_k
        / bundle.thermochemistry.chamber_temperature_k
        * mach_term
        + 0.5
    )
    sigma = sigma_term**-0.68 * mach_term**-0.12
    return (
        0.026
        * gas.viscosity_pa_s**0.2
        * gas.cp_j_per_kg_k
        / gas.prandtl_number**0.6
        * (bundle.inputs.chamber_pressure_pa / bundle.thermochemistry.c_star_m_s) ** 0.8
        * throat_diameter**-0.2
        * (throat_diameter / throat_curvature) ** 0.1
        * local_area_ratio**-0.9
        * sigma
    )


def _throat_curvature_radius(bundle: ExportBundle, mode: str) -> float:
    throat_radius = bundle.geometry.throat_radius_m
    upstream = bundle.inputs.throat_upstream_radius_m or 1.5 * throat_radius
    downstream = bundle.inputs.throat_downstream_radius_m or 0.382 * throat_radius
    if mode == "downstream":
        return downstream
    if mode == "mean":
        return 0.5 * (upstream + downstream)
    return upstream


def _radiation_heat_flux(
    gas_temperature_k: float,
    wall_temperature_k: float,
    settings: CoupledThermalSettings,
) -> float:
    if not settings.radiation_enabled:
        return 0.0
    return max(
        settings.wall_emissivity
        * settings.gas_effective_emissivity
        * _STEFAN_BOLTZMANN_W_PER_M2_K4
        * (gas_temperature_k**4 - wall_temperature_k**4),
        0.0,
    )


def _material_conductivity(properties: MaterialProperties) -> float:
    value = properties.thermal_conductivity_w_per_m_k
    if value is None or not math.isfinite(value) or value <= 0.0:
        raise ValueError("Wall material thermal conductivity is unavailable.")
    return value


def _positive_or(*values: float | None) -> float:
    for value in values:
        if value is not None and math.isfinite(value) and value > 0.0:
            return value
    raise ValueError("No positive fallback value is available.")

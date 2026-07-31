"""Hydraulic and coolant-side heat-transfer model for variable channels.

The functions in this module operate only on the canonical station mesh and
``ChannelLayout``.  That keeps the engineering definition shared by the
thermal solver, future CAD and CFD exporters instead of maintaining separate
channel geometries in each feature.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Sequence

from engine.cooling.models import (
    ChannelCrossSection,
    ChannelLayout,
    ChannelSectionState,
    ChannelShape,
    CoolantCircuit,
)
from engine.properties import CoolantProperties, get_coolant_properties
from engine.station_mesh import EngineStation, EngineStationMesh


_LAMINAR_RE_MAX = 2_300.0
_TURBULENT_RE_MIN = 4_000.0


@dataclass(frozen=True, slots=True)
class ChannelTransportState:
    """Resolved local flow and heat-transfer state."""

    section: ChannelSectionState
    properties: CoolantProperties
    mass_flux_kg_per_m2_s: float
    velocity_m_per_s: float
    reynolds_number: float
    prandtl_number: float
    darcy_friction_factor: float
    nusselt_number: float
    heat_transfer_coefficient_w_per_m2_k: float
    flow_regime: str
    nusselt_method: str
    pressure_gradient_pa_per_m_channel: float
    dean_number: float
    circumferential_pitch_m: float | None
    ligament_margin_m: float | None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ChannelMarchStation:
    """Coolant state at one engine station, ordered in coolant-flow direction."""

    flow_index: int
    station: EngineStation
    transport: ChannelTransportState
    coolant_temperature_k: float
    coolant_pressure_pa: float
    heat_added_from_previous_w: float
    friction_pressure_drop_from_previous_pa: float
    acceleration_pressure_change_from_previous_pa: float
    minor_pressure_drop_from_previous_pa: float
    total_pressure_drop_from_previous_pa: float
    hot_wall_area_from_previous_m2: float
    coolant_wetted_area_from_previous_m2: float


@dataclass(frozen=True, slots=True)
class ChannelCircuitResult:
    """Complete one-dimensional channel-circuit march."""

    circuit_id: str
    stations: tuple[ChannelMarchStation, ...]
    inlet_temperature_k: float
    outlet_temperature_k: float
    inlet_pressure_pa: float
    outlet_pressure_pa: float
    total_heat_added_w: float
    total_friction_pressure_drop_pa: float
    total_acceleration_pressure_change_pa: float
    total_minor_pressure_drop_pa: float
    total_pressure_drop_pa: float
    coolant_flow_direction: str
    notes: tuple[str, ...] = ()


HeatFluxInput = float | Sequence[float] | Callable[[EngineStation], float]
MinorLossInput = float | Sequence[float] | Callable[[EngineStation, EngineStation], float]
PropertyProvider = Callable[[str, float, float | None], CoolantProperties]


def evaluate_channel_transport(
    section: ChannelSectionState,
    *,
    coolant_properties: CoolantProperties,
    mass_flow_kg_per_s: float,
    station_radius_m: float | None = None,
) -> ChannelTransportState:
    """Return local hydraulic and coolant-side heat-transfer quantities."""

    if not math.isfinite(mass_flow_kg_per_s) or mass_flow_kg_per_s <= 0.0:
        raise ValueError("Coolant mass flow must be finite and greater than zero.")
    _validate_properties(coolant_properties)
    area = section.total_flow_area_m2
    density = coolant_properties.density_kg_per_m3
    viscosity = coolant_properties.viscosity_pa_s
    conductivity = coolant_properties.thermal_conductivity_w_per_m_k
    mass_flux = mass_flow_kg_per_s / area
    velocity = mass_flux / density
    reynolds = mass_flux * section.hydraulic_diameter_m / viscosity
    prandtl = _prandtl_number(coolant_properties)
    friction, regime = darcy_friction_factor(
        reynolds,
        section.roughness_m / section.hydraulic_diameter_m,
        section.cross_section,
    )
    nusselt, nusselt_method, nusselt_notes = channel_nusselt_number(
        reynolds,
        prandtl,
        friction,
        section.cross_section,
    )
    heat_transfer_coefficient = (
        nusselt * conductivity / section.hydraulic_diameter_m
    )
    pressure_gradient = (
        friction
        / section.hydraulic_diameter_m
        * 0.5
        * density
        * velocity**2
    )
    pitch = None
    ligament_margin = None
    dean_number = 0.0
    notes = list(nusselt_notes)
    if station_radius_m is not None:
        if not math.isfinite(station_radius_m) or station_radius_m <= 0.0:
            raise ValueError("Station radius must be finite and greater than zero.")
        pitch = 2.0 * math.pi * (
            station_radius_m + section.hot_wall_thickness_m
        ) / section.channel_count
        ligament_margin = pitch - (
            section.hot_wall_width_per_channel_m + section.rib_width_m
        )
        if ligament_margin < 0.0:
            notes.append("channel width plus rib exceeds the available circumferential pitch")
        sine = math.sin(math.radians(section.helix_angle_deg))
        if abs(sine) > 1.0e-12:
            path_curvature = sine**2 / (
                station_radius_m + section.hot_wall_thickness_m
            )
            curvature_radius = 1.0 / path_curvature
            dean_number = reynolds * math.sqrt(
                section.hydraulic_diameter_m / (2.0 * curvature_radius)
            )
    if not coolant_properties.valid:
        notes.append("coolant property state is marked invalid")
    if coolant_properties.note:
        notes.extend(
            note.strip()
            for note in coolant_properties.note.split(";")
            if note.strip()
        )
    return ChannelTransportState(
        section=section,
        properties=coolant_properties,
        mass_flux_kg_per_m2_s=mass_flux,
        velocity_m_per_s=velocity,
        reynolds_number=reynolds,
        prandtl_number=prandtl,
        darcy_friction_factor=friction,
        nusselt_number=nusselt,
        heat_transfer_coefficient_w_per_m2_k=heat_transfer_coefficient,
        flow_regime=regime,
        nusselt_method=nusselt_method,
        pressure_gradient_pa_per_m_channel=pressure_gradient,
        dean_number=dean_number,
        circumferential_pitch_m=pitch,
        ligament_margin_m=ligament_margin,
        notes=tuple(dict.fromkeys(notes)),
    )


def march_channel_circuit(
    station_mesh: EngineStationMesh,
    layout: ChannelLayout,
    circuit: CoolantCircuit,
    *,
    hot_wall_heat_flux_w_per_m2: HeatFluxInput = 0.0,
    minor_loss_coefficient: MinorLossInput = 0.0,
    property_provider: PropertyProvider = get_coolant_properties,
) -> ChannelCircuitResult:
    """March coolant temperature and pressure through a variable channel path.

    Heat flux is defined on the hot-gas wall.  The coolant heat-transfer area
    is reported separately as the full channel wetted perimeter.  Pressure
    change includes Darcy friction, local minor losses and the signed change in
    dynamic pressure caused by variable area/density.
    """

    if len(station_mesh.stations) < 2:
        raise ValueError("At least two engine stations are required.")
    heat_flux_values = _resolve_heat_flux(
        hot_wall_heat_flux_w_per_m2,
        station_mesh.stations,
    )
    flow_pairs = list(zip(station_mesh.stations, heat_flux_values))
    direction = "exit-to-chamber" if circuit.opposite_hot_gas_flow else "chamber-to-exit"
    if circuit.opposite_hot_gas_flow:
        flow_pairs.reverse()

    temperature = circuit.inlet_temperature_k
    pressure = circuit.inlet_pressure_pa
    total_heat = 0.0
    total_friction = 0.0
    total_acceleration = 0.0
    total_minor = 0.0
    station_results: list[ChannelMarchStation] = []
    aggregate_notes: list[str] = []

    first_station, _first_flux = flow_pairs[0]
    first_section = layout.section_at(first_station.s_m)
    first_properties = property_provider(circuit.coolant_id, temperature, pressure)
    first_transport = evaluate_channel_transport(
        first_section,
        coolant_properties=first_properties,
        mass_flow_kg_per_s=circuit.mass_flow_kg_per_s,
        station_radius_m=first_station.inner_radius_m,
    )
    station_results.append(
        ChannelMarchStation(
            flow_index=0,
            station=first_station,
            transport=first_transport,
            coolant_temperature_k=temperature,
            coolant_pressure_pa=pressure,
            heat_added_from_previous_w=0.0,
            friction_pressure_drop_from_previous_pa=0.0,
            acceleration_pressure_change_from_previous_pa=0.0,
            minor_pressure_drop_from_previous_pa=0.0,
            total_pressure_drop_from_previous_pa=0.0,
            hot_wall_area_from_previous_m2=0.0,
            coolant_wetted_area_from_previous_m2=0.0,
        )
    )
    aggregate_notes.extend(first_transport.notes)

    for flow_index, ((upstream, flux_up), (downstream, flux_down)) in enumerate(
        zip(flow_pairs, flow_pairs[1:]),
        start=1,
    ):
        ds_wall = abs(downstream.s_m - upstream.s_m)
        if ds_wall <= 0.0:
            raise ValueError("Station arc lengths must be unique.")
        midpoint_s = 0.5 * (upstream.s_m + downstream.s_m)
        midpoint_radius = 0.5 * (upstream.inner_radius_m + downstream.inner_radius_m)
        midpoint_section = layout.section_at(midpoint_s)
        midpoint_properties = property_provider(circuit.coolant_id, temperature, pressure)
        midpoint_transport = evaluate_channel_transport(
            midpoint_section,
            coolant_properties=midpoint_properties,
            mass_flow_kg_per_s=circuit.mass_flow_kg_per_s,
            station_radius_m=midpoint_radius,
        )
        channel_length = ds_wall * midpoint_section.helical_length_multiplier
        friction_drop = (
            midpoint_transport.pressure_gradient_pa_per_m_channel
            * channel_length
        )
        loss_coefficient = _resolve_minor_loss(
            minor_loss_coefficient,
            flow_index - 1,
            len(flow_pairs) - 1,
            upstream,
            downstream,
        )
        dynamic_pressure_mid = (
            0.5
            * midpoint_properties.density_kg_per_m3
            * midpoint_transport.velocity_m_per_s**2
        )
        minor_drop = loss_coefficient * dynamic_pressure_mid

        mean_radius = midpoint_radius
        hot_wall_area = 2.0 * math.pi * mean_radius * ds_wall
        mean_heat_flux = 0.5 * (flux_up + flux_down)
        heat_added = mean_heat_flux * hot_wall_area
        coolant_wetted_area = (
            midpoint_section.total_wetted_perimeter_m * channel_length
        )
        cp = midpoint_properties.cp_j_per_kg_k
        downstream_temperature = temperature + (
            heat_added / (circuit.mass_flow_kg_per_s * cp)
        )
        downstream_section = layout.section_at(downstream.s_m)
        pressure_before_acceleration = pressure - friction_drop - minor_drop
        if pressure_before_acceleration <= 0.0:
            raise ValueError(
                f"Coolant pressure became non-positive before station {downstream.station_id}."
            )
        downstream_properties_estimate = property_provider(
            circuit.coolant_id,
            downstream_temperature,
            pressure_before_acceleration,
        )
        downstream_transport_estimate = evaluate_channel_transport(
            downstream_section,
            coolant_properties=downstream_properties_estimate,
            mass_flow_kg_per_s=circuit.mass_flow_kg_per_s,
            station_radius_m=downstream.inner_radius_m,
        )
        upstream_dynamic_pressure = (
            0.5
            * station_results[-1].transport.properties.density_kg_per_m3
            * station_results[-1].transport.velocity_m_per_s**2
        )
        downstream_dynamic_pressure = (
            0.5
            * downstream_properties_estimate.density_kg_per_m3
            * downstream_transport_estimate.velocity_m_per_s**2
        )
        acceleration_change = downstream_dynamic_pressure - upstream_dynamic_pressure

        temperature = downstream_temperature
        total_segment_drop = friction_drop + minor_drop + acceleration_change
        pressure -= total_segment_drop
        if pressure <= 0.0:
            raise ValueError(
                f"Coolant pressure became non-positive before station {downstream.station_id}."
            )

        properties = property_provider(circuit.coolant_id, temperature, pressure)
        transport = evaluate_channel_transport(
            downstream_section,
            coolant_properties=properties,
            mass_flow_kg_per_s=circuit.mass_flow_kg_per_s,
            station_radius_m=downstream.inner_radius_m,
        )
        station_results.append(
            ChannelMarchStation(
                flow_index=flow_index,
                station=downstream,
                transport=transport,
                coolant_temperature_k=temperature,
                coolant_pressure_pa=pressure,
                heat_added_from_previous_w=heat_added,
                friction_pressure_drop_from_previous_pa=friction_drop,
                acceleration_pressure_change_from_previous_pa=acceleration_change,
                minor_pressure_drop_from_previous_pa=minor_drop,
                total_pressure_drop_from_previous_pa=total_segment_drop,
                hot_wall_area_from_previous_m2=hot_wall_area,
                coolant_wetted_area_from_previous_m2=coolant_wetted_area,
            )
        )
        total_heat += heat_added
        total_friction += friction_drop
        total_acceleration += acceleration_change
        total_minor += minor_drop
        aggregate_notes.extend(midpoint_transport.notes)
        aggregate_notes.extend(transport.notes)

    total_pressure_drop = circuit.inlet_pressure_pa - pressure
    return ChannelCircuitResult(
        circuit_id=circuit.circuit_id,
        stations=tuple(station_results),
        inlet_temperature_k=circuit.inlet_temperature_k,
        outlet_temperature_k=temperature,
        inlet_pressure_pa=circuit.inlet_pressure_pa,
        outlet_pressure_pa=pressure,
        total_heat_added_w=total_heat,
        total_friction_pressure_drop_pa=total_friction,
        total_acceleration_pressure_change_pa=total_acceleration,
        total_minor_pressure_drop_pa=total_minor,
        total_pressure_drop_pa=total_pressure_drop,
        coolant_flow_direction=direction,
        notes=tuple(dict.fromkeys(aggregate_notes)),
    )


def darcy_friction_factor(
    reynolds_number: float,
    relative_roughness: float,
    cross_section: ChannelCrossSection,
) -> tuple[float, str]:
    """Return Darcy friction factor with a continuous transition blend."""

    if not math.isfinite(reynolds_number) or reynolds_number <= 0.0:
        raise ValueError("Reynolds number must be finite and greater than zero.")
    if not math.isfinite(relative_roughness) or relative_roughness < 0.0:
        raise ValueError("Relative roughness must be finite and non-negative.")
    laminar = _laminar_poiseuille_number(cross_section) / reynolds_number
    if reynolds_number <= _LAMINAR_RE_MAX:
        return laminar, "laminar"
    turbulent = (
        -1.8
        * math.log10(
            (relative_roughness / 3.7) ** 1.11
            + 6.9 / reynolds_number
        )
    ) ** -2
    if reynolds_number < _TURBULENT_RE_MIN:
        fraction = (
            (reynolds_number - _LAMINAR_RE_MAX)
            / (_TURBULENT_RE_MIN - _LAMINAR_RE_MAX)
        )
        return laminar + fraction * (turbulent - laminar), "transitional"
    return turbulent, "turbulent"


def channel_nusselt_number(
    reynolds_number: float,
    prandtl_number: float,
    darcy_factor: float,
    cross_section: ChannelCrossSection,
) -> tuple[float, str, tuple[str, ...]]:
    """Return a shape-aware fully developed or Gnielinski Nusselt number."""

    if reynolds_number <= 0.0 or prandtl_number <= 0.0 or darcy_factor <= 0.0:
        raise ValueError("Reynolds, Prandtl and Darcy factor must be positive.")
    laminar = _laminar_constant_heat_flux_nusselt(cross_section)
    if reynolds_number <= _LAMINAR_RE_MAX:
        return laminar, "fully-developed-laminar-constant-heat-flux", ()
    denominator = (
        1.0
        + 12.7
        * math.sqrt(darcy_factor / 8.0)
        * (prandtl_number ** (2.0 / 3.0) - 1.0)
    )
    turbulent = (
        (darcy_factor / 8.0)
        * (reynolds_number - 1_000.0)
        * prandtl_number
        / denominator
    )
    notes: list[str] = []
    if not (3_000.0 <= reynolds_number <= 5.0e6 and 0.5 <= prandtl_number <= 2_000.0):
        notes.append("Gnielinski correlation is outside its recommended range")
    if reynolds_number < _TURBULENT_RE_MIN:
        fraction = (
            (reynolds_number - _LAMINAR_RE_MAX)
            / (_TURBULENT_RE_MIN - _LAMINAR_RE_MAX)
        )
        return (
            laminar + fraction * (turbulent - laminar),
            "laminar-to-gnielinski-transition",
            tuple(notes + ["transition-regime heat transfer is correlation-sensitive"]),
        )
    return turbulent, "gnielinski", tuple(notes)


def rpa_regenerative_nusselt_number(
    reynolds_number: float,
    prandtl_number: float,
    *,
    coolant_id: str,
    coolant_temperature_k: float,
    coolant_wall_temperature_k: float,
) -> float:
    """Return the coolant-specific correlation documented by RPA 2.3.

    This is kept as an explicit comparison model.  The default channel solver
    uses Gnielinski because it incorporates the local roughness-dependent
    Darcy factor and reports its validity range.
    """

    if reynolds_number <= 0.0 or prandtl_number <= 0.0:
        raise ValueError("Reynolds and Prandtl numbers must be positive.")
    if coolant_temperature_k <= 0.0 or coolant_wall_temperature_k <= 0.0:
        raise ValueError("Coolant temperatures must be positive.")
    key = coolant_id.strip().lower().replace("-", "").replace(" ", "")
    base = reynolds_number**0.8 * prandtl_number**0.4
    temperature_ratio = coolant_temperature_k / coolant_wall_temperature_k
    if key in {"rp1", "rpn1", "kerosene", "rg1"}:
        return 0.021 * base * (0.64 + 0.36 * temperature_ratio)
    if key in {"lh2", "h2", "hydrogen"}:
        return 0.033 * base * temperature_ratio**0.57
    if key in {"ch4", "lch4", "methane"}:
        return 0.0185 * base * temperature_ratio**0.1
    return 0.023 * base


def channel_fin_area_factor(
    *,
    channel_width_m: float,
    channel_height_m: float,
    rib_width_m: float,
    coolant_heat_transfer_coefficient_w_per_m2_k: float,
    wall_thermal_conductivity_w_per_m_k: float,
) -> float:
    """Return the RPA channel-wall rib/fin surface-area factor."""

    values = (
        channel_width_m,
        channel_height_m,
        rib_width_m,
        coolant_heat_transfer_coefficient_w_per_m2_k,
        wall_thermal_conductivity_w_per_m_k,
    )
    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise ValueError("Fin-factor inputs must be finite and greater than zero.")
    xi = math.sqrt(
        2.0
        * coolant_heat_transfer_coefficient_w_per_m2_k
        * channel_height_m
        / wall_thermal_conductivity_w_per_m_k
    )
    fin_efficiency = math.tanh(xi) / xi if xi > 1.0e-12 else 1.0
    pitch = channel_width_m + rib_width_m
    return (
        channel_width_m / pitch
        + 2.0 * channel_height_m / pitch * fin_efficiency
    )


def _laminar_poiseuille_number(cross_section: ChannelCrossSection) -> float:
    if cross_section.shape in {
        ChannelShape.RECTANGULAR,
        ChannelShape.ROUNDED_RECTANGULAR,
    }:
        width, height = cross_section._width_height()
        aspect = min(width, height) / max(width, height)
        return 96.0 * (
            1.0
            - 1.3553 * aspect
            + 1.9467 * aspect**2
            - 1.7012 * aspect**3
            + 0.9564 * aspect**4
            - 0.2537 * aspect**5
        )
    return 64.0


def _laminar_constant_heat_flux_nusselt(
    cross_section: ChannelCrossSection,
) -> float:
    if cross_section.shape in {
        ChannelShape.RECTANGULAR,
        ChannelShape.ROUNDED_RECTANGULAR,
    }:
        width, height = cross_section._width_height()
        aspect = min(width, height) / max(width, height)
        return 8.235 * (
            1.0
            - 2.0421 * aspect
            + 3.0853 * aspect**2
            - 2.4765 * aspect**3
            + 1.0578 * aspect**4
            - 0.1861 * aspect**5
        )
    return 4.36


def _prandtl_number(properties: CoolantProperties) -> float:
    if properties.prandtl_number is not None and properties.prandtl_number > 0.0:
        return properties.prandtl_number
    return (
        properties.cp_j_per_kg_k
        * properties.viscosity_pa_s
        / properties.thermal_conductivity_w_per_m_k
    )


def _validate_properties(properties: CoolantProperties) -> None:
    named_values = {
        "density": properties.density_kg_per_m3,
        "specific heat": properties.cp_j_per_kg_k,
        "viscosity": properties.viscosity_pa_s,
        "thermal conductivity": properties.thermal_conductivity_w_per_m_k,
    }
    for label, value in named_values.items():
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"Coolant {label} must be finite and greater than zero.")


def _resolve_heat_flux(
    source: HeatFluxInput,
    stations: tuple[EngineStation, ...],
) -> list[float]:
    if callable(source):
        values = [float(source(station)) for station in stations]
    elif isinstance(source, (int, float)):
        values = [float(source)] * len(stations)
    else:
        values = [float(value) for value in source]
        if len(values) != len(stations):
            raise ValueError("Heat-flux sequence length must equal the station count.")
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("Hot-wall heat flux values must be finite and non-negative.")
    return values


def _resolve_minor_loss(
    source: MinorLossInput,
    segment_index: int,
    segment_count: int,
    upstream: EngineStation,
    downstream: EngineStation,
) -> float:
    if callable(source):
        value = float(source(upstream, downstream))
    elif isinstance(source, (int, float)):
        value = float(source)
    else:
        values = [float(item) for item in source]
        if len(values) != segment_count:
            raise ValueError(
                "Minor-loss sequence length must equal the number of station intervals."
            )
        value = values[segment_index]
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("Minor-loss coefficients must be finite and non-negative.")
    return value

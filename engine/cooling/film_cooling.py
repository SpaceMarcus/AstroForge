"""Gaseous and liquid film-cooling marching models.

The gaseous mixing law and liquid heating/vaporisation balances follow the
model documented in the RPA thermal-analysis report. The scalar heat-flux
effectiveness remains explicitly screening-level until the surface-layer
composition is coupled to stationwise chemical-equilibrium states.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Callable, Sequence

from engine.cooling.models import FilmCoolingSlot
from engine.station_mesh import EngineStation, EngineStationMesh


class FilmPhase(str, Enum):
    GASEOUS_MIXING = "gaseous-mixing"
    LIQUID_HEATING = "liquid-heating"
    LIQUID_VAPORIZING = "liquid-vaporizing"
    DEPLETED = "depleted"


@dataclass(frozen=True, slots=True)
class FilmCoolingInputs:
    """Physical and empirical inputs for one film slot."""

    slot: FilmCoolingSlot
    injection_temperature_k: float
    coolant_cp_j_per_kg_k: float
    coolant_viscosity_pa_s: float
    surface_layer_mass_flow_kg_per_s: float
    surface_layer_thickness_m: float
    turbulent_mixing_coefficient: float = 1.0e-3
    film_stability_factor: float = 1.0
    vaporization_temperature_k: float | None = None
    latent_heat_j_per_kg: float | None = None

    def __post_init__(self) -> None:
        positive_values = {
            "injection temperature": self.injection_temperature_k,
            "coolant specific heat": self.coolant_cp_j_per_kg_k,
            "coolant viscosity": self.coolant_viscosity_pa_s,
            "surface-layer mass flow": self.surface_layer_mass_flow_kg_per_s,
            "surface-layer thickness": self.surface_layer_thickness_m,
            "turbulent mixing coefficient": self.turbulent_mixing_coefficient,
        }
        for label, value in positive_values.items():
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"Film {label} must be finite and greater than zero.")
        if (
            not math.isfinite(self.film_stability_factor)
            or not 0.0 < self.film_stability_factor <= 1.0
        ):
            raise ValueError("Film stability factor must be in the range (0, 1].")
        if self.slot.liquid:
            if (
                self.vaporization_temperature_k is None
                or self.vaporization_temperature_k <= self.injection_temperature_k
            ):
                raise ValueError(
                    "Liquid film requires a vaporization temperature above injection temperature."
                )
            if self.latent_heat_j_per_kg is None or self.latent_heat_j_per_kg <= 0.0:
                raise ValueError("Liquid film requires positive latent heat.")


@dataclass(frozen=True, slots=True)
class FilmMixingWeights:
    mixing_fraction: float
    k_surface_from_surface: float
    k_surface_from_film: float
    k_film_from_surface: float
    k_film_from_film: float


@dataclass(frozen=True, slots=True)
class FilmStationResult:
    station: EngineStation
    distance_from_injection_m: float
    phase: FilmPhase
    film_temperature_k: float
    liquid_mass_flow_kg_per_s: float
    gaseous_film_mass_flow_kg_per_s: float
    film_reynolds_number: float
    mixing_fraction: float
    convective_effectiveness: float
    unshielded_convective_heat_flux_w_per_m2: float
    radiation_heat_flux_w_per_m2: float
    wall_heat_flux_w_per_m2: float
    absorbed_by_film_from_previous_w: float
    mixing_weights: FilmMixingWeights | None


@dataclass(frozen=True, slots=True)
class FilmCoolingResult:
    slot_id: str
    stations: tuple[FilmStationResult, ...]
    total_heat_absorbed_by_film_w: float
    liquid_depletion_s_m: float | None
    notes: tuple[str, ...]


FluxInput = float | Sequence[float] | Callable[[EngineStation], float]


def gaseous_film_mixing_fraction(
    distance_from_injection_m: float,
    *,
    turbulent_mixing_coefficient: float,
    surface_layer_mass_flow_kg_per_s: float,
    film_mass_flow_kg_per_s: float,
    surface_layer_thickness_m: float,
) -> float:
    """Return RPA's ``xi = 1-exp(-M*(x/Hs)^2)`` mixing coordinate."""

    values = (
        distance_from_injection_m,
        turbulent_mixing_coefficient,
        surface_layer_mass_flow_kg_per_s,
        film_mass_flow_kg_per_s,
        surface_layer_thickness_m,
    )
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Film mixing inputs must be finite.")
    if distance_from_injection_m < 0.0:
        raise ValueError("Distance from film injection must be non-negative.")
    if any(value <= 0.0 for value in values[1:]):
        raise ValueError("Film mixing coefficients, flows and thickness must be positive.")
    mixing_number = (
        turbulent_mixing_coefficient
        * surface_layer_mass_flow_kg_per_s
        / film_mass_flow_kg_per_s
    )
    normalized_distance = distance_from_injection_m / surface_layer_thickness_m
    return 1.0 - math.exp(-mixing_number * normalized_distance**2)


def gaseous_film_mixing_weights(
    mixing_fraction: float,
    *,
    surface_layer_mass_flow_kg_per_s: float,
    film_mass_flow_kg_per_s: float,
) -> FilmMixingWeights:
    """Return the RPA surface-layer/film two-zone mixing coefficients."""

    if not math.isfinite(mixing_fraction) or not 0.0 <= mixing_fraction <= 1.0:
        raise ValueError("Film mixing fraction must lie in [0, 1].")
    if surface_layer_mass_flow_kg_per_s <= 0.0 or film_mass_flow_kg_per_s <= 0.0:
        raise ValueError("Film and surface-layer mass flows must be positive.")
    half_mixed = 0.5 * mixing_fraction
    surface_after = (
        surface_layer_mass_flow_kg_per_s * (1.0 - half_mixed)
        + film_mass_flow_kg_per_s * half_mixed
    )
    film_after = (
        surface_layer_mass_flow_kg_per_s * half_mixed
        + film_mass_flow_kg_per_s * (1.0 - half_mixed)
    )
    return FilmMixingWeights(
        mixing_fraction=mixing_fraction,
        k_surface_from_surface=(
            surface_layer_mass_flow_kg_per_s / surface_after * (1.0 - half_mixed)
        ),
        k_surface_from_film=film_mass_flow_kg_per_s / surface_after * half_mixed,
        k_film_from_surface=surface_layer_mass_flow_kg_per_s / film_after * half_mixed,
        k_film_from_film=(
            film_mass_flow_kg_per_s / film_after * (1.0 - half_mixed)
        ),
    )


def march_film_cooling(
    station_mesh: EngineStationMesh,
    inputs: FilmCoolingInputs,
    *,
    convective_heat_flux_w_per_m2: FluxInput,
    radiation_heat_flux_w_per_m2: FluxInput = 0.0,
) -> FilmCoolingResult:
    """March a film downstream from its injection station."""

    slot = inputs.slot
    stations = tuple(
        station for station in station_mesh.stations if station.s_m >= slot.s_m
    )
    if not stations:
        raise ValueError("Film injection lies downstream of the station mesh.")
    convective = _resolve_flux(convective_heat_flux_w_per_m2, station_mesh.stations)
    radiation = _resolve_flux(radiation_heat_flux_w_per_m2, station_mesh.stations)
    flux_by_id = {
        station.station_id: (convective[index], radiation[index])
        for index, station in enumerate(station_mesh.stations)
    }

    temperature = inputs.injection_temperature_k
    liquid_flow = slot.mass_flow_kg_per_s if slot.liquid else 0.0
    gaseous_flow = 0.0 if slot.liquid else slot.mass_flow_kg_per_s
    total_absorbed = 0.0
    depletion_s = None
    vaporization_start_s = None
    results: list[FilmStationResult] = []
    previous_s = slot.s_m

    for station in stations:
        ds = max(station.s_m - previous_s, 0.0)
        q_conv, q_rad = flux_by_id[station.station_id]
        covered_hot_area = (
            2.0
            * math.pi
            * station.inner_radius_m
            * ds
            * slot.circumference_fraction
        )
        available_convective_heat = q_conv * covered_hot_area
        absorbed = 0.0

        if liquid_flow > 0.0 and ds > 0.0:
            if temperature < (inputs.vaporization_temperature_k or temperature):
                sensible_capacity = (
                    inputs.film_stability_factor
                    * liquid_flow
                    * inputs.coolant_cp_j_per_kg_k
                    * ((inputs.vaporization_temperature_k or temperature) - temperature)
                )
                sensible_heat = min(available_convective_heat, sensible_capacity)
                temperature += sensible_heat / (
                    inputs.film_stability_factor
                    * liquid_flow
                    * inputs.coolant_cp_j_per_kg_k
                )
                absorbed += sensible_heat
                available_convective_heat -= sensible_heat
            if (
                temperature >= (inputs.vaporization_temperature_k or math.inf)
                and available_convective_heat > 0.0
            ):
                if vaporization_start_s is None:
                    vaporization_start_s = station.s_m
                vaporized = min(
                    liquid_flow,
                    available_convective_heat / (inputs.latent_heat_j_per_kg or math.inf),
                )
                latent_heat = vaporized * (inputs.latent_heat_j_per_kg or 0.0)
                liquid_flow -= vaporized
                gaseous_flow += vaporized
                absorbed += latent_heat
                if liquid_flow <= 1.0e-12:
                    liquid_flow = 0.0
                    depletion_s = station.s_m

        if liquid_flow > 0.0:
            phase = (
                FilmPhase.LIQUID_VAPORIZING
                if temperature >= (inputs.vaporization_temperature_k or math.inf)
                else FilmPhase.LIQUID_HEATING
            )
            mixing_fraction = 0.0
            effectiveness = 1.0
            wall_heat_flux = q_rad
            weights = None
        else:
            phase = FilmPhase.GASEOUS_MIXING if gaseous_flow > 0.0 else FilmPhase.DEPLETED
            gas_start_s = depletion_s or vaporization_start_s or slot.s_m
            gas_distance = max(station.s_m - gas_start_s, 0.0)
            if gaseous_flow > 0.0:
                mixing_fraction = gaseous_film_mixing_fraction(
                    gas_distance,
                    turbulent_mixing_coefficient=inputs.turbulent_mixing_coefficient,
                    surface_layer_mass_flow_kg_per_s=inputs.surface_layer_mass_flow_kg_per_s,
                    film_mass_flow_kg_per_s=gaseous_flow,
                    surface_layer_thickness_m=inputs.surface_layer_thickness_m,
                )
                weights = gaseous_film_mixing_weights(
                    mixing_fraction,
                    surface_layer_mass_flow_kg_per_s=inputs.surface_layer_mass_flow_kg_per_s,
                    film_mass_flow_kg_per_s=gaseous_flow,
                )
            else:
                mixing_fraction = 1.0
                weights = None
            effectiveness = 1.0 - mixing_fraction
            wall_heat_flux = q_rad + mixing_fraction * q_conv

        total_absorbed += absorbed
        film_reynolds = (
            max(liquid_flow, gaseous_flow)
            / (
                2.0
                * math.pi
                * station.inner_radius_m
                * inputs.coolant_viscosity_pa_s
            )
        )
        results.append(
            FilmStationResult(
                station=station,
                distance_from_injection_m=station.s_m - slot.s_m,
                phase=phase,
                film_temperature_k=temperature,
                liquid_mass_flow_kg_per_s=liquid_flow,
                gaseous_film_mass_flow_kg_per_s=gaseous_flow,
                film_reynolds_number=film_reynolds,
                mixing_fraction=mixing_fraction,
                convective_effectiveness=effectiveness,
                unshielded_convective_heat_flux_w_per_m2=q_conv,
                radiation_heat_flux_w_per_m2=q_rad,
                wall_heat_flux_w_per_m2=wall_heat_flux,
                absorbed_by_film_from_previous_w=absorbed,
                mixing_weights=weights,
            )
        )
        previous_s = station.s_m

    notes = (
        "gaseous mixing follows the RPA two-zone turbulent-mixing law",
        "liquid heating and vaporization follow the RPA space-marching energy balance",
        "scalar convective effectiveness is screening-level until station composition coupling is active",
    )
    return FilmCoolingResult(
        slot_id=slot.slot_id,
        stations=tuple(results),
        total_heat_absorbed_by_film_w=total_absorbed,
        liquid_depletion_s_m=depletion_s,
        notes=notes,
    )


def _resolve_flux(
    source: FluxInput,
    stations: tuple[EngineStation, ...],
) -> list[float]:
    if callable(source):
        values = [float(source(station)) for station in stations]
    elif isinstance(source, (int, float)):
        values = [float(source)] * len(stations)
    else:
        values = [float(value) for value in source]
        if len(values) != len(stations):
            raise ValueError("Film heat-flux sequence length must equal station count.")
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("Film heat flux must be finite and non-negative.")
    return values

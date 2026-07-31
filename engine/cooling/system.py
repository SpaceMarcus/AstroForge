"""Multiple-circuit and axial-segment orchestration for cooling analyses."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from engine.cooling.channel_flow import (
    ChannelCircuitResult,
    HeatFluxInput,
    march_channel_circuit,
)
from engine.cooling.models import (
    ChannelLayout,
    CoolantCircuit,
    CoolingMechanism,
    CoolingSegment,
)
from engine.station_mesh import EngineStation, EngineStationMesh


@dataclass(frozen=True, slots=True)
class RegenerativeCircuitPath:
    """One coolant circuit routed through one regenerative axial segment."""

    path_id: str
    circuit: CoolantCircuit
    segment: CoolingSegment
    layout: ChannelLayout
    heat_load_fraction: float = 1.0
    minor_loss_coefficient: float = 0.0

    def __post_init__(self) -> None:
        if not self.path_id.strip():
            raise ValueError("Cooling path ID must not be empty.")
        if self.segment.circuit_id != self.circuit.circuit_id:
            raise ValueError("Cooling segment and circuit IDs must match.")
        if CoolingMechanism.REGENERATIVE_CHANNELS not in self.segment.mechanisms:
            raise ValueError("A regenerative circuit path requires channel cooling.")
        if (
            not math.isfinite(self.heat_load_fraction)
            or not 0.0 < self.heat_load_fraction <= 1.0
        ):
            raise ValueError("Path heat-load fraction must be in the range (0, 1].")
        if (
            not math.isfinite(self.minor_loss_coefficient)
            or self.minor_loss_coefficient < 0.0
        ):
            raise ValueError("Path minor-loss coefficient must be non-negative.")


@dataclass(frozen=True, slots=True)
class CoolingSystemResult:
    path_results: tuple[tuple[str, ChannelCircuitResult], ...]
    total_coolant_mass_flow_kg_per_s: float
    total_heat_added_w: float
    maximum_pressure_drop_pa: float
    notes: tuple[str, ...] = ()

    def result_for_path(self, path_id: str) -> ChannelCircuitResult:
        for candidate_id, result in self.path_results:
            if candidate_id == path_id:
                return result
        raise KeyError(path_id)


def march_cooling_system(
    station_mesh: EngineStationMesh,
    paths: tuple[RegenerativeCircuitPath, ...],
    *,
    hot_wall_heat_flux_w_per_m2: HeatFluxInput,
) -> CoolingSystemResult:
    """Run independent circuits over named, possibly parallel axial segments."""

    if not paths:
        raise ValueError("A cooling system requires at least one regenerative path.")
    path_ids = [path.path_id for path in paths]
    if len(path_ids) != len(set(path_ids)):
        raise ValueError("Cooling path IDs must be unique.")
    _validate_heat_load_coverage(paths)
    results: list[tuple[str, ChannelCircuitResult]] = []
    notes: list[str] = []
    for path in paths:
        submesh = _station_submesh(
            station_mesh,
            path.segment.s_start_m,
            path.segment.s_end_m,
            path.path_id,
        )
        local_heat_flux = _scaled_heat_flux(
            hot_wall_heat_flux_w_per_m2,
            path.heat_load_fraction,
            station_mesh,
        )
        result = march_channel_circuit(
            submesh,
            path.layout,
            path.circuit,
            hot_wall_heat_flux_w_per_m2=local_heat_flux,
            minor_loss_coefficient=path.minor_loss_coefficient,
        )
        results.append((path.path_id, result))
        notes.extend(result.notes)
    return CoolingSystemResult(
        path_results=tuple(results),
        total_coolant_mass_flow_kg_per_s=sum(
            path.circuit.mass_flow_kg_per_s for path in paths
        ),
        total_heat_added_w=sum(result.total_heat_added_w for _path_id, result in results),
        maximum_pressure_drop_pa=max(
            result.total_pressure_drop_pa for _path_id, result in results
        ),
        notes=tuple(dict.fromkeys(notes)),
    )


def _station_submesh(
    mesh: EngineStationMesh,
    s_start_m: float,
    s_end_m: float,
    path_id: str,
) -> EngineStationMesh:
    if s_start_m < 0.0 or s_end_m > mesh.contour_length_m or s_end_m <= s_start_m:
        raise ValueError("Cooling path range lies outside the engine contour.")
    selected: list[EngineStation] = []
    start = _interpolate_station(mesh, s_start_m, f"{path_id}-START")
    end = _interpolate_station(mesh, s_end_m, f"{path_id}-END")
    selected.append(start)
    selected.extend(
        station
        for station in mesh.stations
        if s_start_m < station.s_m < s_end_m
    )
    if not math.isclose(end.s_m, selected[-1].s_m, abs_tol=1.0e-12):
        selected.append(end)
    if len(selected) < 2:
        raise ValueError("Cooling path range must contain at least two stations.")
    return EngineStationMesh(
        stations=tuple(selected),
        contour_length_m=s_end_m - s_start_m,
    )


def _interpolate_station(
    mesh: EngineStationMesh,
    target_s_m: float,
    boundary_id: str,
) -> EngineStation:
    for station in mesh.stations:
        if math.isclose(station.s_m, target_s_m, abs_tol=1.0e-12):
            return station
    for left, right in zip(mesh.stations, mesh.stations[1:]):
        if left.s_m < target_s_m < right.s_m:
            fraction = (target_s_m - left.s_m) / (right.s_m - left.s_m)
            radius = _lerp(left.inner_radius_m, right.inner_radius_m, fraction)
            return EngineStation(
                station_id=f"SEG-{boundary_id}",
                index=-1,
                x_m=_lerp(left.x_m, right.x_m, fraction),
                s_m=target_s_m,
                inner_radius_m=radius,
                area_m2=math.pi * radius**2,
                tangent_angle_deg=_lerp(
                    left.tangent_angle_deg,
                    right.tangent_angle_deg,
                    fraction,
                ),
                curvature_1_per_m=_lerp(
                    left.curvature_1_per_m,
                    right.curvature_1_per_m,
                    fraction,
                ),
                region=left.region if fraction < 0.5 else right.region,
            )
    raise ValueError("Cooling boundary cannot be interpolated on the station mesh.")


def _validate_heat_load_coverage(paths: tuple[RegenerativeCircuitPath, ...]) -> None:
    boundaries = sorted(
        {
            coordinate
            for path in paths
            for coordinate in (path.segment.s_start_m, path.segment.s_end_m)
        }
    )
    for left, right in zip(boundaries, boundaries[1:]):
        midpoint = 0.5 * (left + right)
        fraction_sum = sum(
            path.heat_load_fraction
            for path in paths
            if path.segment.s_start_m <= midpoint < path.segment.s_end_m
        )
        if fraction_sum > 1.0 + 1.0e-12:
            raise ValueError(
                "Parallel cooling paths assign more than 100% of the local hot-wall heat load."
            )


def _scaled_heat_flux(
    source: HeatFluxInput,
    fraction: float,
    full_mesh: EngineStationMesh,
) -> float | Callable[[EngineStation], float]:
    if isinstance(source, (int, float)):
        return float(source) * fraction
    if callable(source):
        return lambda station: fraction * float(source(station))
    values = [float(value) for value in source]
    if len(values) != len(full_mesh.stations):
        raise ValueError("System heat-flux sequence length must equal full station count.")
    by_id = {
        station.station_id: values[index]
        for index, station in enumerate(full_mesh.stations)
    }

    def lookup(station: EngineStation) -> float:
        if station.station_id in by_id:
            return fraction * by_id[station.station_id]
        nearest = min(
            full_mesh.stations,
            key=lambda candidate: abs(candidate.s_m - station.s_m),
        )
        return fraction * by_id[nearest.station_id]

    return lookup


def _lerp(first: float, second: float, fraction: float) -> float:
    return first + fraction * (second - first)

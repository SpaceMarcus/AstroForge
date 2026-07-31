"""Stable engine-wall stations shared by analysis, CAD and mesh exporters."""

from __future__ import annotations

from dataclasses import dataclass
import math

from engine.models import NozzlePoint


@dataclass(frozen=True, slots=True)
class EngineStation:
    """One stable point on the committed hot-gas wall contour."""

    station_id: str
    index: int
    x_m: float
    s_m: float
    inner_radius_m: float
    area_m2: float
    tangent_angle_deg: float
    curvature_1_per_m: float
    region: str


@dataclass(frozen=True, slots=True)
class EngineStationMesh:
    """Ordered immutable station mesh and its design fingerprint input."""

    stations: tuple[EngineStation, ...]
    contour_length_m: float

    def nearest_to_s(self, s_m: float) -> EngineStation:
        if not self.stations:
            raise ValueError("Station mesh is empty.")
        return min(self.stations, key=lambda station: abs(station.s_m - s_m))


def build_engine_station_mesh(contour: list[NozzlePoint]) -> EngineStationMesh:
    """Convert a committed contour to stable stations with local geometry."""

    if len(contour) < 2:
        raise ValueError("At least two contour points are required for a station mesh.")
    arc_lengths = [0.0]
    for left, right in zip(contour, contour[1:]):
        if right.x_m < left.x_m:
            raise ValueError("Contour x coordinates must be non-decreasing.")
        distance = math.hypot(
            right.x_m - left.x_m,
            right.radius_m - left.radius_m,
        )
        if distance <= 0.0:
            raise ValueError("Consecutive contour points must not coincide.")
        arc_lengths.append(arc_lengths[-1] + distance)

    throat_index = min(range(len(contour)), key=lambda index: contour[index].area_m2)
    stations: list[EngineStation] = []
    for index, point in enumerate(contour):
        left = contour[max(0, index - 1)]
        right = contour[min(len(contour) - 1, index + 1)]
        dx = right.x_m - left.x_m
        dr = right.radius_m - left.radius_m
        tangent_angle_deg = math.degrees(math.atan2(dr, dx))
        curvature = _local_curvature(contour, index)
        if index < throat_index:
            region = "chamber" if tangent_angle_deg == 0.0 else "converging"
        elif index == throat_index:
            region = "throat"
        else:
            region = "diverging"
        stations.append(
            EngineStation(
                station_id=f"STA-{index:05d}",
                index=index,
                x_m=point.x_m,
                s_m=arc_lengths[index],
                inner_radius_m=point.radius_m,
                area_m2=point.area_m2,
                tangent_angle_deg=tangent_angle_deg,
                curvature_1_per_m=curvature,
                region=region,
            )
        )
    return EngineStationMesh(
        stations=tuple(stations),
        contour_length_m=arc_lengths[-1],
    )


def _local_curvature(contour: list[NozzlePoint], index: int) -> float:
    if index == 0 or index == len(contour) - 1:
        return 0.0
    first = contour[index - 1]
    middle = contour[index]
    last = contour[index + 1]
    a = math.hypot(middle.x_m - first.x_m, middle.radius_m - first.radius_m)
    b = math.hypot(last.x_m - middle.x_m, last.radius_m - middle.radius_m)
    c = math.hypot(last.x_m - first.x_m, last.radius_m - first.radius_m)
    denominator = a * b * c
    if denominator <= 0.0:
        return 0.0
    twice_area = abs(
        (middle.x_m - first.x_m) * (last.radius_m - first.radius_m)
        - (middle.radius_m - first.radius_m) * (last.x_m - first.x_m)
    )
    return 2.0 * twice_area / denominator

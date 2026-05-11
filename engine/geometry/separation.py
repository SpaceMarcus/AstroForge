"""Separation helpers kept separate from plotting and GUI code."""

from __future__ import annotations

from engine.models import (
    ContourMarker,
    ExportBundle,
    PredictedSeparationPoint,
    SeparationCriterion,
    ThermochemistryProfilePoint,
)


def default_separation_criterion() -> SeparationCriterion:
    """Return the currently used first-order separation rule."""

    return SeparationCriterion(
        name="Summerfield-style wall-pressure criterion",
        wall_to_ambient_pressure_ratio_limit=0.40,
    )


def predict_separation_point(
    bundle: ExportBundle,
    criterion: SeparationCriterion | None = None,
) -> PredictedSeparationPoint | None:
    """Predict a first separation point using local wall-pressure estimates."""

    criterion = criterion or default_separation_criterion()
    ambient_pressure = bundle.inputs.ambient_pressure_pa
    if ambient_pressure <= 0.0:
        return None

    for point in bundle.thermochemistry_profile:
        if point.region != "diverging":
            continue
        static_pressure = estimate_local_static_pressure_pa(bundle.inputs.chamber_pressure_pa, point)
        if static_pressure is None:
            continue
        ratio = static_pressure / ambient_pressure
        if ratio <= criterion.wall_to_ambient_pressure_ratio_limit:
            return PredictedSeparationPoint(
                station_index=point.station_index or 0,
                x_m=point.x_m,
                radius_m=point.radius_m,
                area_ratio=point.state.area_ratio or point.area_m2 / bundle.geometry.throat_area_m2,
                static_pressure_pa=static_pressure,
                criterion_name=criterion.name,
                reason=(
                    f"Predicted where local wall/static pressure ratio falls to {ratio:.3f} "
                    f"against the {criterion.wall_to_ambient_pressure_ratio_limit:.2f} limit."
                ),
            )
    return None


def estimate_local_static_pressure_pa(
    chamber_pressure_pa: float,
    point: ThermochemistryProfilePoint,
) -> float | None:
    """Estimate local static pressure from chamber pressure and interpolated Mach."""

    gamma = point.state.gamma
    mach = point.state.mach_number
    if gamma is None or mach is None or gamma <= 1.0 or mach < 0.0:
        return None
    pressure_ratio = (1.0 + 0.5 * (gamma - 1.0) * mach * mach) ** (gamma / (gamma - 1.0))
    return chamber_pressure_pa / pressure_ratio


def build_contour_markers(
    bundle: ExportBundle,
    separation_point: PredictedSeparationPoint | None,
) -> list[ContourMarker]:
    """Build plot markers for throat, exit, optimal expansion and separation."""

    markers: list[ContourMarker] = []
    profile = bundle.thermochemistry_profile
    if not profile:
        return markers

    throat_point = min(profile, key=lambda point: abs(point.x_m))
    exit_point = profile[-1]
    has_diverging_section = any(point.region == "diverging" for point in profile)
    markers.append(
        ContourMarker(
            label="throat",
            x_m=throat_point.x_m,
            radius_m=throat_point.radius_m,
            color="#1f4f7a",
            station_index=throat_point.station_index,
        )
    )
    if has_diverging_section:
        markers.append(
            ContourMarker(
                label="exit",
                x_m=exit_point.x_m,
                radius_m=exit_point.radius_m,
                color="#c25b2a",
                station_index=exit_point.station_index,
            )
        )

    optimal_eps = bundle.geometry.optimal_expansion_ratio
    current_eps = bundle.geometry.current_expansion_ratio
    if has_diverging_section and optimal_eps is not None and current_eps is not None and current_eps > 1.0:
        if current_eps is not None and optimal_eps <= current_eps:
            optimal_point = min(
                profile,
                key=lambda point: abs((point.state.area_ratio or 0.0) - optimal_eps),
            )
            markers.append(
                ContourMarker(
                    label="optimal eps",
                    x_m=optimal_point.x_m,
                    radius_m=optimal_point.radius_m,
                    color="#2d7d46",
                    station_index=optimal_point.station_index,
                )
            )
        else:
            markers.append(
                ContourMarker(
                    label="optimal eps > exit",
                    x_m=exit_point.x_m,
                    radius_m=exit_point.radius_m,
                    color="#2d7d46",
                    station_index=exit_point.station_index,
                )
            )

    if has_diverging_section and separation_point is not None:
        markers.append(
            ContourMarker(
                label="separation",
                x_m=separation_point.x_m,
                radius_m=separation_point.radius_m,
                color="#b03060",
                station_index=separation_point.station_index,
            )
        )

    return markers

"""Nozzle contour generation and thermochemistry mapping utilities."""

from __future__ import annotations

from dataclasses import replace
import math

from engine.geometry.sizing import circle_area_from_radius
from engine.models import (
    BellContourVariant,
    GeometryResult,
    NozzleContourMethod,
    NozzlePoint,
    ThermochemistryProfilePoint,
    ThermochemistryResult,
    ThermochemistryState,
)
from engine.nozzle_geometry import (
    TOP_NOZZLE_SOURCE,
    get_top_nozzle_angles,
    normalize_top_length_fraction,
)

UNIVERSAL_GAS_CONSTANT_J_PER_MOL_K = 8.31446261815324


def generate_nozzle_contour(
    geometry: GeometryResult,
    *,
    method: NozzleContourMethod = NozzleContourMethod.BELL,
    bell_variant: BellContourVariant = BellContourVariant.PARABOLA,
    bell_length_fraction_percent: float | None = None,
    manual_nozzle_length_m: float | None = None,
    chamber_length_m: float | None = None,
    chamber_radius_m: float | None = None,
    convergent_half_angle_deg: float = 45.0,
    throat_upstream_radius_m: float | None = None,
    throat_downstream_radius_m: float | None = None,
    chamber_corner_radius_m: float | None = None,
    reference_conical_half_angle_deg: float = 15.0,
    points_per_segment: int = 40,
    include_diverging_section: bool = True,
) -> list[NozzlePoint]:
    """Generate a chamber-throat-exit contour for plotting and export."""

    throat_radius = geometry.throat_radius_m
    exit_radius = geometry.exit_radius_m
    chamber_radius = chamber_radius_m or geometry.chamber_radius_m
    chamber_length = chamber_length_m or geometry.chamber_length_m
    # The Geometry tab can override the default throat-blend radii and chamber
    # corner radius. When no explicit override is present we keep the historical
    # MVP defaults so older saved states still render sensibly.
    upstream_throat_radius = (
        throat_upstream_radius_m
        if throat_upstream_radius_m is not None and throat_upstream_radius_m > 0.0
        else 1.5 * throat_radius
    )
    downstream_throat_radius = (
        throat_downstream_radius_m
        if throat_downstream_radius_m is not None and throat_downstream_radius_m > 0.0
        else 0.382 * throat_radius
    )
    chamber_corner_radius = max(chamber_corner_radius_m or 0.0, 0.0)
    geometry.current_expansion_ratio = geometry.exit_area_m2 / geometry.throat_area_m2
    geometry.bell_start_angle_deg = None
    geometry.bell_exit_angle_deg = None
    geometry.top_nozzle_length_fraction_percent = None
    geometry.top_nozzle_angle_source = None

    if not include_diverging_section:
        geometry.current_expansion_ratio = 1.0
        geometry.optimal_expansion_ratio = None
        geometry.reference_conical_length_m = 0.0
        geometry.current_nozzle_length_m = 0.0
        geometry.notes = [
            "Subsonic / unchoked plausibility case: divergent nozzle geometry is disabled.",
        ]
        points: list[NozzlePoint] = []
        if chamber_radius is not None and chamber_length is not None and chamber_length > 0.0:
            # Even in a throat-only subsonic case we still render the chamber-side
            # blends so the preview matches the selected chamber and throat inputs.
            points.extend(
                _converging_section_with_blends(
                    chamber_radius=chamber_radius,
                    throat_radius=throat_radius,
                    chamber_length_m=chamber_length,
                    half_angle_deg=convergent_half_angle_deg,
                    chamber_corner_radius_m=chamber_corner_radius,
                    throat_entry_radius_m=upstream_throat_radius,
                    points_count=points_per_segment,
                )
            )
        else:
            points.append(
                NozzlePoint(
                    x_m=0.0,
                    radius_m=throat_radius,
                    area_m2=circle_area_from_radius(throat_radius),
                )
            )

        geometry.contour_length_m = _streamwise_distances(points)[-1] if points else None
        return points

    reference_conical_length = max(
        (exit_radius - throat_radius) / math.tan(math.radians(reference_conical_half_angle_deg)),
        throat_radius,
    )
    geometry.reference_conical_length_m = reference_conical_length

    if method is NozzleContourMethod.CONICAL:
        current_nozzle_length = manual_nozzle_length_m or reference_conical_length
        geometry.notes = (
            ["Manual nozzle length applied to the conical divergent contour."]
            if manual_nozzle_length_m is not None
            else []
        )
    elif method is NozzleContourMethod.BELL:
        if manual_nozzle_length_m is not None:
            current_nozzle_length = manual_nozzle_length_m
        else:
            resolved_length_fraction_percent = (
                normalize_top_length_fraction(bell_length_fraction_percent)
                if bell_length_fraction_percent is not None
                else 80.0
            )
            current_nozzle_length = (resolved_length_fraction_percent / 100.0) * reference_conical_length
        geometry.notes = [
            "Bell parabola uses Rao / Huzel & Huang TOP chart interpolation via pygasflow.",
        ]
        if manual_nozzle_length_m is not None:
            geometry.notes.append("Manual nozzle length applied to the bell-parabola contour.")
        else:
            geometry.notes.append(
                f"Bell length fraction Lf = {resolved_length_fraction_percent:.1f}% drives the TOP contour length."
            )
    else:
        raise ValueError("Aerospike contours are reserved for a future implementation.")

    geometry.current_nozzle_length_m = current_nozzle_length

    points: list[NozzlePoint] = []

    if chamber_radius is not None and chamber_length is not None and chamber_length > 0.0:
        # Use one converging builder for both conical and bell nozzles so chamber
        # and throat edits are reflected consistently across all contour families.
        converging = _converging_section_with_blends(
            chamber_radius=chamber_radius,
            throat_radius=throat_radius,
            chamber_length_m=chamber_length,
            half_angle_deg=convergent_half_angle_deg,
            chamber_corner_radius_m=chamber_corner_radius,
            throat_entry_radius_m=upstream_throat_radius,
            points_count=points_per_segment,
        )
        points.extend(converging)
    else:
        points.append(
            NozzlePoint(
                x_m=0.0,
                radius_m=throat_radius,
                area_m2=circle_area_from_radius(throat_radius),
            )
        )

    if method is NozzleContourMethod.CONICAL:
        diverging = _conic_section(
            throat_radius=throat_radius,
            exit_radius=exit_radius,
            length_m=current_nozzle_length,
            points_count=points_per_segment,
        )
    elif bell_variant is BellContourVariant.PARABOLA:
        diverging, theta_n_deg, theta_e_deg, length_fraction_percent = _parabolic_bell_section(
            throat_radius=throat_radius,
            exit_radius=exit_radius,
            length_m=current_nozzle_length,
            reference_conical_length_m=reference_conical_length,
            downstream_throat_radius_m=downstream_throat_radius,
            points_count=points_per_segment,
        )
        geometry.bell_start_angle_deg = theta_n_deg
        geometry.bell_exit_angle_deg = theta_e_deg
        geometry.top_nozzle_length_fraction_percent = length_fraction_percent
        geometry.top_nozzle_angle_source = TOP_NOZZLE_SOURCE
    else:
        raise ValueError(
            "Bell subtypes TIC and TOC are visible in the UI but are not numerically implemented yet."
        )

    if points and math.isclose(points[-1].x_m, diverging[0].x_m, abs_tol=1.0e-12):
        points.extend(diverging[1:])
    else:
        points.extend(diverging)

    geometry.contour_length_m = _streamwise_distances(points)[-1] if points else None
    return points


def build_thermochemistry_profile(
    contour: list[NozzlePoint],
    geometry: GeometryResult,
    thermochemistry: ThermochemistryResult,
) -> list[ThermochemistryProfilePoint]:
    """Map chamber, throat and exit RocketCEA states onto the contour."""

    chamber_state = thermochemistry.station_states.get("chamber")
    throat_state = thermochemistry.station_states.get("throat")
    exit_state = thermochemistry.station_states.get("exit")
    if chamber_state is None or throat_state is None or exit_state is None or not contour:
        return []

    streamwise_distances = _streamwise_distances(contour)
    has_chamber_section = contour[0].x_m < 0.0
    first_radius = contour[0].radius_m
    convergent_start_x = next(
        (
            point.x_m
            for point in contour
            if point.x_m < 0.0 and not math.isclose(point.radius_m, first_radius, abs_tol=1.0e-9)
        ),
        contour[0].x_m,
    )
    chamber_area_ratio = (
        geometry.chamber_area_m2 / geometry.throat_area_m2
        if geometry.chamber_area_m2 is not None and geometry.throat_area_m2 > 0.0
        else chamber_state.area_ratio
    )
    exit_area_ratio = geometry.exit_area_m2 / max(geometry.throat_area_m2, 1.0e-12)
    profile: list[ThermochemistryProfilePoint] = []

    for index, point in enumerate(contour):
        area_ratio = point.area_m2 / geometry.throat_area_m2
        if has_chamber_section and point.x_m <= convergent_start_x:
            region = "chamber"
            state = replace(chamber_state, area_ratio=area_ratio, source="rocketcea-station")
        elif has_chamber_section and point.x_m < 0.0:
            region = "converging"
            if chamber_area_ratio is None or chamber_area_ratio <= 1.0:
                fraction = (point.x_m - convergent_start_x) / (0.0 - convergent_start_x)
            else:
                fraction = (chamber_area_ratio - area_ratio) / max(chamber_area_ratio - 1.0, 1.0e-12)
            state = _interpolate_state(
                chamber_state,
                throat_state,
                fraction,
                label=region,
                source="area-ratio interpolated chamber-to-throat",
                area_ratio=area_ratio,
            )
        elif math.isclose(point.x_m, 0.0, abs_tol=1.0e-12):
            region = "throat"
            state = replace(throat_state, area_ratio=area_ratio, source="rocketcea-station")
        else:
            region = "diverging"
            if math.isclose(area_ratio, exit_area_ratio, rel_tol=1.0e-6, abs_tol=1.0e-9) or index == len(contour) - 1:
                state = replace(exit_state, area_ratio=area_ratio, source="rocketcea-station")
                state = _augment_with_boundary_metrics(state, streamwise_distances[index])
                profile.append(
                    ThermochemistryProfilePoint(
                        x_m=point.x_m,
                        radius_m=point.radius_m,
                        area_m2=point.area_m2,
                        region=region,
                        state=state,
                        station_index=index,
                    )
                )
                continue
            fraction = (area_ratio - 1.0) / max(exit_area_ratio - 1.0, 1.0e-12)
            state = _interpolate_state(
                throat_state,
                exit_state,
                fraction,
                label=region,
                source="area-ratio interpolated throat-to-exit",
                area_ratio=area_ratio,
            )

        state = _augment_with_boundary_metrics(state, streamwise_distances[index])
        profile.append(
            ThermochemistryProfilePoint(
                x_m=point.x_m,
                radius_m=point.radius_m,
                area_m2=point.area_m2,
                region=region,
                state=state,
                station_index=index,
            )
        )

    return profile


def _converging_section_with_blends(
    *,
    chamber_radius: float,
    throat_radius: float,
    chamber_length_m: float,
    half_angle_deg: float,
    chamber_corner_radius_m: float,
    throat_entry_radius_m: float,
    points_count: int,
) -> list[NozzlePoint]:
    """Build the chamber-side contour with cylinder, rounded corner and throat arc."""

    half_angle = math.radians(half_angle_deg)
    chamber_corner_axial = chamber_corner_radius_m * math.sin(half_angle)
    throat_arc_x_extent = throat_entry_radius_m * math.sin(half_angle)
    chamber_tangent_radius = chamber_radius - chamber_corner_radius_m * (1.0 - math.cos(half_angle))
    throat_tangent_radius = throat_radius + throat_entry_radius_m * (1.0 - math.cos(half_angle))
    straight_length = max((chamber_tangent_radius - throat_tangent_radius) / math.tan(half_angle), 0.0)

    chamber_start_x = -(chamber_length_m + chamber_corner_axial + straight_length + throat_arc_x_extent)
    line_end_x = -throat_arc_x_extent

    points = _cylindrical_section(
        x_start=chamber_start_x,
        x_end=-(straight_length + throat_arc_x_extent + chamber_corner_axial),
        radius_m=chamber_radius,
        points_count=max(points_count // 2, 2),
    )
    if chamber_corner_radius_m > 0.0:
        # The chamber corner arc rounds the cylinder-to-convergent junction before
        # the straight conical run toward the throat-entry blend.
        arc_start_x = -(straight_length + throat_arc_x_extent + chamber_corner_axial)
        points.extend(
            _chamber_corner_arc(
                chamber_radius=chamber_radius,
                corner_radius_m=chamber_corner_radius_m,
                arc_start_x=arc_start_x,
                half_angle_deg=half_angle_deg,
                points_count=max(points_count // 3, 5),
            )[1:]
        )
    points.extend(
        _linear_transition(
            x_start=-(straight_length + throat_arc_x_extent),
            x_end=line_end_x,
            radius_start=chamber_tangent_radius,
            radius_end=throat_tangent_radius,
            points_count=max(points_count // 2, 3),
        )[1:]
    )
    points.extend(
        _throat_entry_arc(
            throat_radius=throat_radius,
            arc_radius_m=throat_entry_radius_m,
            half_angle_deg=half_angle_deg,
            points_count=max(points_count // 2, 4),
        )[1:]
    )
    return points


def _chamber_corner_arc(
    *,
    chamber_radius: float,
    corner_radius_m: float,
    arc_start_x: float,
    half_angle_deg: float,
    points_count: int,
) -> list[NozzlePoint]:
    """Round the cylinder-to-convergent corner before the straight convergent line."""

    half_angle = math.radians(half_angle_deg)
    points: list[NozzlePoint] = []
    for index in range(points_count):
        fraction = index / (points_count - 1)
        angle = math.pi / 2.0 - half_angle * fraction
        x = arc_start_x + corner_radius_m * math.cos(angle)
        radius = chamber_radius - corner_radius_m + corner_radius_m * math.sin(angle)
        points.append(NozzlePoint(x_m=x, radius_m=radius, area_m2=circle_area_from_radius(radius)))
    return points


def _cylindrical_section(
    *,
    x_start: float,
    x_end: float,
    radius_m: float,
    points_count: int,
) -> list[NozzlePoint]:
    if points_count < 2:
        points_count = 2
    points: list[NozzlePoint] = []
    for index in range(points_count):
        fraction = index / (points_count - 1)
        x = x_start + fraction * (x_end - x_start)
        points.append(
            NozzlePoint(
                x_m=x,
                radius_m=radius_m,
                area_m2=circle_area_from_radius(radius_m),
            )
        )
    return points


def _linear_transition(
    *,
    x_start: float,
    x_end: float,
    radius_start: float,
    radius_end: float,
    points_count: int,
) -> list[NozzlePoint]:
    points: list[NozzlePoint] = []
    for index in range(points_count):
        fraction = index / (points_count - 1)
        x = x_start + fraction * (x_end - x_start)
        radius = radius_start + fraction * (radius_end - radius_start)
        points.append(NozzlePoint(x_m=x, radius_m=radius, area_m2=circle_area_from_radius(radius)))
    return points


def _throat_entry_arc(
    *,
    throat_radius: float,
    arc_radius_m: float,
    half_angle_deg: float,
    points_count: int,
) -> list[NozzlePoint]:
    half_angle = math.radians(half_angle_deg)
    points: list[NozzlePoint] = []
    for index in range(points_count):
        fraction = index / (points_count - 1)
        angle = half_angle * (1.0 - fraction)
        x = -arc_radius_m * math.sin(angle)
        radius = throat_radius + arc_radius_m * (1.0 - math.cos(angle))
        points.append(NozzlePoint(x_m=x, radius_m=radius, area_m2=circle_area_from_radius(radius)))
    return points


def _cosine_transition(
    *,
    x_start: float,
    x_end: float,
    radius_start: float,
    radius_end: float,
    points_count: int,
) -> list[NozzlePoint]:
    points: list[NozzlePoint] = []
    for index in range(points_count):
        fraction = index / (points_count - 1)
        blend = 0.5 * (1.0 - math.cos(math.pi * fraction))
        radius = radius_start + blend * (radius_end - radius_start)
        x = x_start + fraction * (x_end - x_start)
        points.append(NozzlePoint(x_m=x, radius_m=radius, area_m2=circle_area_from_radius(radius)))
    return points


def _parabolic_bell_section(
    *,
    throat_radius: float,
    exit_radius: float,
    length_m: float,
    reference_conical_length_m: float,
    downstream_throat_radius_m: float,
    points_count: int,
) -> tuple[list[NozzlePoint], float, float, float]:
    """Build the TOP bell from the throat arc tangency point to the exit."""

    length_ratio = length_m / max(reference_conical_length_m, 1.0e-9)
    expansion_ratio = (exit_radius / max(throat_radius, 1.0e-9)) ** 2
    length_fraction_percent = normalize_top_length_fraction(length_ratio)
    theta_n_deg, theta_e_deg = get_top_nozzle_angles(expansion_ratio, length_fraction_percent)
    theta_n = math.radians(theta_n_deg)
    theta_e = math.radians(theta_e_deg)

    # N is the tangency point where the downstream throat arc hands over to the
    # bell parabola. The Geometry tab uses the same construction for its previews.
    x_join = downstream_throat_radius_m * math.sin(theta_n)
    r_join = throat_radius + downstream_throat_radius_m * (1.0 - math.cos(theta_n))
    if length_m <= x_join:
        raise ValueError("Manual nozzle length is shorter than the downstream throat-arc requirement.")

    control_x, control_r = _line_intersection(
        point_a=(x_join, r_join),
        slope_a=math.tan(theta_n),
        point_b=(length_m, exit_radius),
        slope_b=math.tan(theta_e),
    )

    arc_points = _throat_divergent_arc(
        throat_radius=throat_radius,
        arc_radius_m=downstream_throat_radius_m,
        end_angle_rad=theta_n,
        points_count=max(points_count // 3, 6),
    )
    parabola_points = _quadratic_bezier_section(
        start_point=(x_join, r_join),
        control_point=(control_x, control_r),
        end_point=(length_m, exit_radius),
        points_count=max(points_count, 20),
    )
    return arc_points + parabola_points[1:], theta_n_deg, theta_e_deg, length_fraction_percent


def _throat_divergent_arc(
    *,
    throat_radius: float,
    arc_radius_m: float,
    end_angle_rad: float,
    points_count: int,
) -> list[NozzlePoint]:
    points: list[NozzlePoint] = []
    for index in range(points_count):
        fraction = index / (points_count - 1)
        angle = end_angle_rad * fraction
        x = arc_radius_m * math.sin(angle)
        radius = throat_radius + arc_radius_m * (1.0 - math.cos(angle))
        points.append(NozzlePoint(x_m=x, radius_m=radius, area_m2=circle_area_from_radius(radius)))
    return points


def _quadratic_bezier_section(
    *,
    start_point: tuple[float, float],
    control_point: tuple[float, float],
    end_point: tuple[float, float],
    points_count: int,
) -> list[NozzlePoint]:
    points: list[NozzlePoint] = []
    for index in range(points_count):
        fraction = index / (points_count - 1)
        one_minus = 1.0 - fraction
        x = (
            one_minus * one_minus * start_point[0]
            + 2.0 * one_minus * fraction * control_point[0]
            + fraction * fraction * end_point[0]
        )
        radius = (
            one_minus * one_minus * start_point[1]
            + 2.0 * one_minus * fraction * control_point[1]
            + fraction * fraction * end_point[1]
        )
        points.append(NozzlePoint(x_m=x, radius_m=radius, area_m2=circle_area_from_radius(radius)))
    return points


def _line_intersection(
    *,
    point_a: tuple[float, float],
    slope_a: float,
    point_b: tuple[float, float],
    slope_b: float,
) -> tuple[float, float]:
    if math.isclose(slope_a, slope_b, rel_tol=1.0e-9, abs_tol=1.0e-9):
        x = 0.5 * (point_a[0] + point_b[0])
        y = point_a[1] + slope_a * (x - point_a[0])
        return x, y
    x = (
        (point_b[1] - point_a[1])
        + slope_a * point_a[0]
        - slope_b * point_b[0]
    ) / (slope_a - slope_b)
    y = point_a[1] + slope_a * (x - point_a[0])
    return x, y


def _conic_section(
    *,
    throat_radius: float,
    exit_radius: float,
    length_m: float,
    points_count: int,
) -> list[NozzlePoint]:
    points: list[NozzlePoint] = []
    for index in range(points_count):
        fraction = index / (points_count - 1)
        radius = throat_radius + fraction * (exit_radius - throat_radius)
        x = fraction * length_m
        points.append(NozzlePoint(x_m=x, radius_m=radius, area_m2=circle_area_from_radius(radius)))
    return points


def _interpolate_state(
    start: ThermochemistryState,
    end: ThermochemistryState,
    fraction: float,
    *,
    label: str,
    source: str,
    area_ratio: float | None,
) -> ThermochemistryState:
    clamped_fraction = min(max(fraction, 0.0), 1.0)
    return ThermochemistryState(
        label=label,
        area_ratio=area_ratio,
        temperature_k=_lerp_optional(start.temperature_k, end.temperature_k, clamped_fraction),
        density_kg_per_m3=_lerp_optional(
            start.density_kg_per_m3,
            end.density_kg_per_m3,
            clamped_fraction,
        ),
        enthalpy_j_per_kg=_lerp_optional(
            start.enthalpy_j_per_kg,
            end.enthalpy_j_per_kg,
            clamped_fraction,
        ),
        cp_j_per_kg_k=_lerp_optional(start.cp_j_per_kg_k, end.cp_j_per_kg_k, clamped_fraction),
        viscosity_pa_s=_lerp_optional(start.viscosity_pa_s, end.viscosity_pa_s, clamped_fraction),
        thermal_conductivity_w_per_m_k=_lerp_optional(
            start.thermal_conductivity_w_per_m_k,
            end.thermal_conductivity_w_per_m_k,
            clamped_fraction,
        ),
        prandtl_number=_lerp_optional(start.prandtl_number, end.prandtl_number, clamped_fraction),
        gamma=_lerp_optional(start.gamma, end.gamma, clamped_fraction),
        molecular_weight_kg_per_mol=_lerp_optional(
            start.molecular_weight_kg_per_mol,
            end.molecular_weight_kg_per_mol,
            clamped_fraction,
        ),
        mach_number=_lerp_optional(start.mach_number, end.mach_number, clamped_fraction),
        species_mass_fractions=_interpolate_species(
            start.species_mass_fractions,
            end.species_mass_fractions,
            clamped_fraction,
        ),
        species_mole_fractions=_interpolate_species(
            start.species_mole_fractions,
            end.species_mole_fractions,
            clamped_fraction,
        ),
        source=source,
    )


def _interpolate_species(
    start: dict[str, float],
    end: dict[str, float],
    fraction: float,
) -> dict[str, float]:
    interpolated: dict[str, float] = {}
    for species in sorted(set(start) | set(end)):
        value = _lerp_optional(start.get(species, 0.0), end.get(species, 0.0), fraction)
        if value is not None and value > 1.0e-7:
            interpolated[species] = value
    return dict(sorted(interpolated.items(), key=lambda item: item[1], reverse=True))


def _augment_with_boundary_metrics(
    state: ThermochemistryState,
    streamwise_distance_m: float,
) -> ThermochemistryState:
    if (
        state.temperature_k is None
        or state.gamma is None
        or state.molecular_weight_kg_per_mol is None
        or state.mach_number is None
        or state.density_kg_per_m3 is None
        or state.viscosity_pa_s is None
        or state.prandtl_number is None
        or state.temperature_k <= 0.0
        or state.gamma <= 0.0
        or state.molecular_weight_kg_per_mol <= 0.0
        or state.viscosity_pa_s <= 0.0
        or state.density_kg_per_m3 <= 0.0
        or streamwise_distance_m <= 0.0
    ):
        return state

    specific_gas_constant = UNIVERSAL_GAS_CONSTANT_J_PER_MOL_K / state.molecular_weight_kg_per_mol
    speed_of_sound = math.sqrt(state.gamma * specific_gas_constant * state.temperature_k)
    velocity = state.mach_number * speed_of_sound
    reynolds_number = (
        state.density_kg_per_m3 * max(velocity, 1.0e-6) * streamwise_distance_m / state.viscosity_pa_s
    )

    if reynolds_number <= 0.0:
        return replace(state, velocity_m_per_s=velocity)

    prandtl = max(state.prandtl_number, 1.0e-9)
    recovery_factor = prandtl ** (1.0 / 3.0)
    adiabatic_wall_temperature = state.temperature_k * (
        1.0 + recovery_factor * (state.gamma - 1.0) * 0.5 * state.mach_number**2
    )
    velocity_boundary_layer = 0.37 * streamwise_distance_m / reynolds_number**0.2
    thermal_boundary_layer = velocity_boundary_layer * prandtl ** (-1.0 / 3.0)

    return replace(
        state,
        velocity_m_per_s=velocity,
        reynolds_number=reynolds_number,
        adiabatic_wall_temperature_k=adiabatic_wall_temperature,
        thermal_boundary_layer_thickness_m=thermal_boundary_layer,
        velocity_boundary_layer_thickness_m=velocity_boundary_layer,
    )


def _streamwise_distances(contour: list[NozzlePoint]) -> list[float]:
    distances: list[float] = []
    cumulative_distance = 0.0
    previous_point: NozzlePoint | None = None
    for point in contour:
        if previous_point is not None:
            cumulative_distance += math.hypot(
                point.x_m - previous_point.x_m,
                point.radius_m - previous_point.radius_m,
            )
        distances.append(cumulative_distance)
        previous_point = point
    return distances


def _lerp_optional(start: float | None, end: float | None, fraction: float) -> float | None:
    if start is None and end is None:
        return None
    if start is None:
        return end
    if end is None:
        return start
    return start + fraction * (end - start)

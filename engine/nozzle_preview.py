"""Lightweight nozzle-preview guidance used by the Geometry tab."""

from __future__ import annotations

from dataclasses import dataclass
import math

from engine.models import BellContourVariant, NozzleContourMethod
from engine.nozzle_geometry import TOP_NOZZLE_SOURCE, get_top_nozzle_angles, normalize_top_length_fraction


@dataclass(slots=True)
class NozzlePreviewResult:
    """Preview-only approximation of a nozzle section starting at the throat."""

    throat_radius_m: float
    exit_radius_m: float
    expansion_ratio: float
    downstream_radius_m: float
    downstream_radius_ratio: float
    inflow_angle_deg: float
    outflow_angle_deg: float
    angle_source: str | None
    length_fraction_percent: float | None
    start_x_m: float
    start_radius_m: float
    length_m: float
    uses_manual_length: bool
    uses_normalized_throat: bool
    points: list[tuple[float, float]]


def build_nozzle_preview(
    *,
    throat_radius_m: float | None,
    expansion_ratio: float,
    downstream_radius_ratio: float,
    contour_method: NozzleContourMethod,
    bell_variant: BellContourVariant,
    manual_length_m: float | None,
    length_fraction_input: float | None = None,
) -> NozzlePreviewResult:
    """Build a preview-only nozzle approximation from x = 0 to x = L."""

    throat_radius_value = throat_radius_m if throat_radius_m is not None and throat_radius_m > 0.0 else 1.0
    uses_normalized_throat = throat_radius_m is None or throat_radius_m <= 0.0
    expansion_ratio_value = max(expansion_ratio, 1.0)
    re_rt = math.sqrt(expansion_ratio_value)
    exit_radius_m = throat_radius_value * re_rt
    downstream_ratio_value = max(downstream_radius_ratio, 0.05)
    downstream_radius_m = downstream_ratio_value * throat_radius_value
    reference_conical_length_m = max(
        (exit_radius_m - throat_radius_value) / math.tan(math.radians(15.0)),
        throat_radius_value,
    )

    uses_manual_length = manual_length_m is not None and manual_length_m > 0.0
    if contour_method is NozzleContourMethod.BELL and bell_variant is BellContourVariant.PARABOLA:
        if uses_manual_length:
            length_m = manual_length_m
            length_fraction_input = length_m / max(reference_conical_length_m, 1.0e-9)
        elif length_fraction_input is not None:
            length_fraction_percent = normalize_top_length_fraction(length_fraction_input)
            length_m = (length_fraction_percent / 100.0) * reference_conical_length_m
        else:
            length_fraction_input = 0.80
            length_m = 0.80 * reference_conical_length_m
            length_fraction_percent = normalize_top_length_fraction(length_fraction_input)
        if uses_manual_length:
            length_fraction_percent = normalize_top_length_fraction(length_fraction_input)
        chart_theta_n_deg, outflow_angle_deg = get_top_nozzle_angles(
            expansion_ratio_value,
            length_fraction_percent,
        )
        inflow_angle_deg, _preview_exit_angle_deg = estimate_placeholder_nozzle_angles(
            re_rt=re_rt,
            downstream_radius_ratio=downstream_ratio_value,
            contour_method=contour_method,
            bell_variant=bell_variant,
        )
        inflow_angle_deg = max(chart_theta_n_deg - 8.0, min(inflow_angle_deg, chart_theta_n_deg + 8.0))
        angle_source = TOP_NOZZLE_SOURCE
    else:
        inflow_angle_deg, outflow_angle_deg = estimate_placeholder_nozzle_angles(
            re_rt=re_rt,
            downstream_radius_ratio=downstream_ratio_value,
            contour_method=contour_method,
            bell_variant=bell_variant,
        )
        angle_source = None
        length_fraction_percent = None
        inflow_angle_rad = math.radians(inflow_angle_deg)
        outflow_angle_rad = math.radians(outflow_angle_deg)
        start_x_m = downstream_radius_m * math.sin(inflow_angle_rad)
        start_radius_m = throat_radius_value + downstream_radius_m * (1.0 - math.cos(inflow_angle_rad))
        if uses_manual_length and manual_length_m is not None:
            length_m = manual_length_m
        else:
            average_angle_rad = max(0.5 * (inflow_angle_rad + outflow_angle_rad), math.radians(1.0))
            body_length_m = max((exit_radius_m - start_radius_m) / math.tan(average_angle_rad), 0.0)
            length_m = start_x_m + body_length_m
        length_m = max(length_m, start_x_m + throat_radius_value * 0.25)

    inflow_angle_rad = math.radians(inflow_angle_deg)
    outflow_angle_rad = math.radians(outflow_angle_deg)

    # Standard tangency-point approximation for the start of the nozzle body after the throat arc.
    start_x_m = downstream_radius_m * math.sin(inflow_angle_rad)
    start_radius_m = throat_radius_value + downstream_radius_m * (1.0 - math.cos(inflow_angle_rad))
    if (
        contour_method is NozzleContourMethod.BELL
        and bell_variant is BellContourVariant.PARABOLA
        and length_m <= start_x_m
    ):
        raise ValueError("Manual nozzle length is shorter than the downstream throat-arc requirement.")
    length_m = max(length_m, start_x_m + throat_radius_value * 0.25)

    points = _build_preview_points(
        throat_radius_m=throat_radius_value,
        exit_radius_m=exit_radius_m,
        start_x_m=start_x_m,
        start_radius_m=start_radius_m,
        length_m=length_m,
        inflow_angle_rad=inflow_angle_rad,
        outflow_angle_rad=outflow_angle_rad,
        downstream_radius_m=downstream_radius_m,
        contour_method=contour_method,
    )
    return NozzlePreviewResult(
        throat_radius_m=throat_radius_value,
        exit_radius_m=exit_radius_m,
        expansion_ratio=expansion_ratio_value,
        downstream_radius_m=downstream_radius_m,
        downstream_radius_ratio=downstream_ratio_value,
        inflow_angle_deg=inflow_angle_deg,
        outflow_angle_deg=outflow_angle_deg,
        angle_source=angle_source,
        length_fraction_percent=length_fraction_percent,
        start_x_m=start_x_m,
        start_radius_m=start_radius_m,
        length_m=length_m,
        uses_manual_length=uses_manual_length,
        uses_normalized_throat=uses_normalized_throat,
        points=points,
    )


def estimate_placeholder_nozzle_angles(
    *,
    re_rt: float,
    downstream_radius_ratio: float,
    contour_method: NozzleContourMethod,
    bell_variant: BellContourVariant,
) -> tuple[float, float]:
    """Return placeholder inflow/outflow angles until the diagram-based method is added."""

    re_factor = min(max((re_rt - 1.0) / 4.5, 0.0), 1.0)
    radius_factor = min(max((downstream_radius_ratio - 0.382) / 1.2, -0.2), 0.5)

    inflow_angle = 27.0 + 10.0 * re_factor + 6.0 * radius_factor
    outflow_angle = 14.0 - 5.0 * re_factor

    if contour_method is NozzleContourMethod.CONICAL:
        inflow_angle += 2.0
        outflow_angle += 2.0
    elif bell_variant is BellContourVariant.TIC:
        outflow_angle -= 1.0
    elif bell_variant is BellContourVariant.TOC:
        outflow_angle += 1.0

    return max(15.0, min(inflow_angle, 50.0)), max(4.0, min(outflow_angle, 20.0))


def _build_preview_points(
    *,
    throat_radius_m: float,
    exit_radius_m: float,
    start_x_m: float,
    start_radius_m: float,
    length_m: float,
    inflow_angle_rad: float,
    outflow_angle_rad: float,
    downstream_radius_m: float,
    contour_method: NozzleContourMethod,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = [(0.0, throat_radius_m)]
    arc_steps = 16
    for step in range(1, arc_steps + 1):
        fraction = step / arc_steps
        angle = inflow_angle_rad * fraction
        points.append(
            (
                downstream_radius_m * math.sin(angle),
                throat_radius_m + downstream_radius_m * (1.0 - math.cos(angle)),
            )
        )

    if length_m <= start_x_m:
        points.append((length_m, start_radius_m))
        return points

    if contour_method is NozzleContourMethod.CONICAL:
        points.append((length_m, exit_radius_m))
        return points

    body_steps = 28
    end_slope = math.tan(outflow_angle_rad)
    start_slope = math.tan(inflow_angle_rad)
    body_length = length_m - start_x_m
    for step in range(1, body_steps + 1):
        fraction = step / body_steps
        h00 = 2.0 * fraction**3 - 3.0 * fraction**2 + 1.0
        h10 = fraction**3 - 2.0 * fraction**2 + fraction
        h01 = -2.0 * fraction**3 + 3.0 * fraction**2
        h11 = fraction**3 - fraction**2
        radius_value = (
            h00 * start_radius_m
            + h10 * body_length * start_slope
            + h01 * exit_radius_m
            + h11 * body_length * end_slope
        )
        x_value = start_x_m + body_length * fraction
        points.append((x_value, radius_value))
    return points

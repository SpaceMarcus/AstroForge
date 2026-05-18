"""Shared preview-bundle helpers for geometry sandbox plots and exports.

These helpers intentionally reuse the existing geometry and contour builders so the
Geometry tab can preview committed-design changes without silently rerunning the
thermochemistry backend. This module owns only the temporary preview bundle; the
authoritative committed design still lives in the main solver / ExportBundle path.
"""

from __future__ import annotations

from dataclasses import replace
import math

from engine.flow import FlowCase, adapt_inputs_for_flow_case, classify_input_flow_case
from engine.geometry import build_thermochemistry_profile, generate_nozzle_contour, size_engine_geometry
from engine.models import ExportBundle, InputParameters, ThermochemistryProfilePoint, WallThicknessMode

_LINER_DENSITY_KG_PER_M3 = {
    "cucrzr": 8_900.0,
    "grcop-42": 8_760.0,
    "inconel 718": 8_190.0,
    "316l stainless steel": 8_000.0,
}


def build_geometry_preview_bundle(
    base_bundle: ExportBundle,
    preview_inputs: InputParameters,
) -> ExportBundle:
    """Return a geometry-only preview bundle for sandbox plotting and export.

    The preview keeps the last calculated thermochemistry result and remaps it onto
    the updated contour. This makes Geometry-tab edits visible immediately while
    keeping the main solver path explicit and user-driven.
    """

    # The preview follows the same flow-case gate as the main solver so a subsonic
    # sandbox edit cannot accidentally show a divergent contour that the committed
    # design path would suppress.
    preview_gamma = base_bundle.thermochemistry.gamma
    if preview_gamma is not None and (not math.isfinite(preview_gamma) or preview_gamma <= 1.0):
        preview_gamma = None
    flow_case = classify_input_flow_case(
        preview_inputs,
        gamma=preview_gamma,
    )
    effective_inputs = adapt_inputs_for_flow_case(preview_inputs, flow_case)
    # Reuse the last calculated thermochemistry and only rebuild the geometry side.
    geometry = size_engine_geometry(effective_inputs, base_bundle.thermochemistry)
    contour = generate_nozzle_contour(
        geometry,
        method=effective_inputs.contour_method,
        bell_variant=effective_inputs.bell_variant,
        manual_nozzle_length_m=effective_inputs.manual_nozzle_length_m,
        chamber_length_m=geometry.chamber_length_m,
        chamber_radius_m=geometry.chamber_radius_m,
        convergent_half_angle_deg=effective_inputs.convergent_half_angle_deg,
        throat_upstream_radius_m=effective_inputs.throat_upstream_radius_m,
        throat_downstream_radius_m=effective_inputs.throat_downstream_radius_m,
        chamber_corner_radius_m=effective_inputs.chamber_corner_radius_m,
        include_diverging_section=flow_case.flow_case is FlowCase.CHOKED_SUPERSONIC,
    )
    # The thermochemistry profile is remapped onto the new contour so every contour
    # plot and geometry export reads the same preview state.
    thermochemistry_profile = build_thermochemistry_profile(contour, geometry, base_bundle.thermochemistry)
    return ExportBundle(
        inputs=effective_inputs,
        thermochemistry=base_bundle.thermochemistry,
        geometry=geometry,
        contour=contour,
        thermochemistry_profile=thermochemistry_profile,
        of_sweep=base_bundle.of_sweep,
        generated_at_utc=base_bundle.generated_at_utc,
    )


def estimate_liner_mass_kg(
    inputs: InputParameters,
    contour: list,
) -> float | None:
    """Estimate liner mass from contour surface area, wall thickness and material.

    This is a first-order shell estimate for the hot-gas-side liner wall only. It is
    suitable for sandbox tradeoffs and summary readouts, not for detailed structural
    sign-off.
    """

    if inputs.wall_thickness_mode is not WallThicknessMode.CONSTANT:
        return None
    if inputs.wall_thickness_m is None or inputs.wall_thickness_m <= 0.0:
        return None
    density = _material_density_kg_per_m3(inputs.liner_material)
    if density is None or len(contour) < 2:
        return None

    # Treat the liner as a thin shell wrapped around the hot-gas contour.
    surface_area_m2 = 0.0
    for start, end in zip(contour, contour[1:]):
        ds = math.hypot(end.x_m - start.x_m, end.radius_m - start.radius_m)
        radius_mean = 0.5 * (start.radius_m + end.radius_m)
        surface_area_m2 += 2.0 * math.pi * radius_mean * ds
    return surface_area_m2 * inputs.wall_thickness_m * density


def with_liner_mass(bundle: ExportBundle) -> ExportBundle:
    """Return a bundle copy whose geometry includes the current liner-mass estimate."""

    liner_mass_kg = estimate_liner_mass_kg(bundle.inputs, bundle.contour)
    return replace(
        bundle,
        geometry=replace(bundle.geometry, estimated_liner_mass_kg=liner_mass_kg),
    )


def is_current_design_bundle_stale(
    current_inputs: InputParameters | None,
    bundle: ExportBundle | None,
) -> bool:
    """Return whether the committed bundle no longer matches the visible inputs.

    The GUI deliberately allows draft edits and preview-only geometry updates.
    Downstream modules such as Thermal Analysis, Report and Export must therefore
    gate themselves against the committed Current Design bundle instead of
    assuming that the currently visible form fields have already been committed.
    """

    if current_inputs is None or bundle is None:
        return True
    return current_inputs != bundle.inputs


def validate_bundle_geometry_synchronization(bundle: ExportBundle) -> list[str]:
    """Return synchronization issues for one committed/export-ready bundle.

    This helper is intentionally stricter than the geometry preview path. It is
    meant for committed-design guards before Thermal Analysis or export so stale
    contours and stale thermochemistry profiles do not slip through silently.
    """

    issues: list[str] = []
    contour = bundle.contour
    profile = bundle.thermochemistry_profile
    geometry = bundle.geometry

    if contour is None or len(contour) < 2:
        return ["Committed contour is missing or has fewer than two points."]

    contour_x_values = [point.x_m for point in contour]
    contour_radius_values = [point.radius_m for point in contour]
    contour_area_values = [point.area_m2 for point in contour]
    if not _all_finite(contour_x_values + contour_radius_values + contour_area_values):
        issues.append("Committed contour contains non-finite x, radius or area values.")
    if any(radius <= 0.0 for radius in contour_radius_values):
        issues.append("Committed contour contains non-positive radii.")
    if any(area <= 0.0 for area in contour_area_values):
        issues.append("Committed contour contains non-positive areas.")
    for point in contour:
        expected_area_m2 = math.pi * point.radius_m**2
        if not math.isclose(point.area_m2, expected_area_m2, rel_tol=2.0e-3, abs_tol=1.0e-9):
            issues.append("Committed contour contains radius/area pairs that are not self-consistent.")
            break

    contour_x_span_m = contour[-1].x_m - contour[0].x_m
    if not math.isfinite(contour_x_span_m) or contour_x_span_m <= 0.0:
        issues.append("Committed contour x-span is not positive.")

    contour_min_radius_m = min(contour_radius_values)
    contour_max_radius_m = max(contour_radius_values)
    throat_radius_m = geometry.throat_radius_m
    exit_radius_m = geometry.exit_radius_m
    if not math.isclose(contour_min_radius_m, throat_radius_m, rel_tol=0.03, abs_tol=1.0e-6):
        issues.append("Committed contour throat radius does not match committed geometry throat radius.")
    if not math.isclose(contour[-1].radius_m, exit_radius_m, rel_tol=0.03, abs_tol=1.0e-6):
        issues.append("Committed contour exit radius does not match committed geometry exit radius.")

    if not profile:
        issues.append("Committed thermochemistry profile is missing.")
        return issues

    profile_x_values = [point.x_m for point in profile]
    profile_radius_values = [point.radius_m for point in profile]
    profile_area_values = [point.area_m2 for point in profile]
    if not _all_finite(profile_x_values + profile_radius_values + profile_area_values):
        issues.append("Committed thermochemistry profile contains non-finite x, radius or area values.")
    if any(radius <= 0.0 for radius in profile_radius_values):
        issues.append("Committed thermochemistry profile contains non-positive radii.")
    if any(area <= 0.0 for area in profile_area_values):
        issues.append("Committed thermochemistry profile contains non-positive areas.")

    x_tolerance_m = max(1.0e-6, 0.02 * max(contour_x_span_m, 1.0e-6))
    if (
        abs(profile[0].x_m - contour[0].x_m) > x_tolerance_m
        or abs(profile[-1].x_m - contour[-1].x_m) > x_tolerance_m
    ):
        issues.append("Committed thermochemistry profile x-range does not match the committed contour closely.")

    radius_scale_m = max(contour_max_radius_m - contour_min_radius_m, contour_max_radius_m, 1.0e-9)
    if (
        abs(min(profile_radius_values) - contour_min_radius_m) > 0.05 * radius_scale_m
        or abs(max(profile_radius_values) - contour_max_radius_m) > 0.05 * radius_scale_m
    ):
        issues.append("Committed thermochemistry profile radius range differs noticeably from the committed contour.")

    return issues


def format_bundle_geometry_summary(bundle: ExportBundle | None) -> str:
    """Return a compact human-readable contour/profile summary."""

    if bundle is None or not bundle.contour:
        return "No committed contour available."

    contour = bundle.contour
    profile = bundle.thermochemistry_profile
    contour_min_radius_m = min(point.radius_m for point in contour)
    contour_max_radius_m = max(point.radius_m for point in contour)
    issue_count = len(validate_bundle_geometry_synchronization(bundle))
    alignment_text = "aligned" if issue_count == 0 else "needs attention"
    return (
        f"Committed contour: {len(contour)} points, "
        f"x=[{contour[0].x_m:.4f}, {contour[-1].x_m:.4f}] m, "
        f"r=[{contour_min_radius_m:.4f}, {contour_max_radius_m:.4f}] m, "
        f"throat={bundle.geometry.throat_radius_m:.4f} m, "
        f"exit={bundle.geometry.exit_radius_m:.4f} m, "
        f"profile pts={len(profile)}, profile {alignment_text}."
    )


def _material_density_kg_per_m3(material_name: str | None) -> float | None:
    """Return a simple density lookup for the MVP liner-mass estimate."""

    if material_name is None:
        return None
    normalized = material_name.strip().lower()
    if not normalized:
        return None
    if normalized in _LINER_DENSITY_KG_PER_M3:
        return _LINER_DENSITY_KG_PER_M3[normalized]
    for key, density in _LINER_DENSITY_KG_PER_M3.items():
        if normalized.startswith(key):
            return density
    return None


def _all_finite(values: list[float]) -> bool:
    return all(math.isfinite(value) for value in values)

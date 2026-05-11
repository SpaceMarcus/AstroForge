"""Shared preview helpers for geometry sandbox plots and exports.

These helpers intentionally reuse the existing geometry and contour builders so the
Geometry tab can preview committed-design changes without silently rerunning the
thermochemistry backend.
"""

from __future__ import annotations

from dataclasses import replace
import math

from engine.flow import FlowCase, adapt_inputs_for_flow_case, classify_input_flow_case
from engine.geometry import build_thermochemistry_profile, generate_nozzle_contour, size_engine_geometry
from engine.models import ExportBundle, InputParameters, WallThicknessMode

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
    flow_case = classify_input_flow_case(preview_inputs)
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

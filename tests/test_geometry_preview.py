"""Tests for geometry-sandbox preview helpers."""

from dataclasses import replace

from engine.geometry_preview import (
    build_geometry_preview_bundle,
    estimate_liner_mass_kg,
    format_bundle_geometry_summary,
    is_current_design_bundle_stale,
    validate_bundle_geometry_synchronization,
    with_liner_mass,
)
from engine.models import (
    ChemistryMode,
    ExportBundle,
    GeometryResult,
    InputParameters,
    ThermochemistryResult,
    ThermochemistryState,
)


def _make_base_bundle() -> ExportBundle:
    inputs = InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=7.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=18.0,
        ambient_pressure_pa=101_325.0,
        contraction_ratio=3.0,
        characteristic_length_m=1.1,
    )
    thermo = ThermochemistryResult(
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        propellant_description="LOX / RP-1",
        chamber_temperature_k=3500.0,
        c_star_m_s=1750.0,
        isp_vac_s=320.0,
        isp_amb_s=285.0,
        cf_vac=1.79,
        cf_amb=1.60,
        gamma=1.2,
        chamber_density_kg_per_m3=4.5,
        station_states={
            "chamber": ThermochemistryState(
                label="chamber",
                area_ratio=3.0,
                temperature_k=3500.0,
                density_kg_per_m3=4.5,
                gamma=1.2,
                mach_number=0.1,
                velocity_m_per_s=80.0,
            ),
            "throat": ThermochemistryState(
                label="throat",
                area_ratio=1.0,
                temperature_k=3300.0,
                density_kg_per_m3=3.2,
                gamma=1.19,
                mach_number=1.0,
                velocity_m_per_s=1100.0,
            ),
            "exit": ThermochemistryState(
                label="exit",
                area_ratio=18.0,
                temperature_k=2200.0,
                density_kg_per_m3=0.5,
                gamma=1.17,
                mach_number=3.0,
                velocity_m_per_s=2500.0,
            ),
        },
    )
    return ExportBundle(
        inputs=inputs,
        thermochemistry=thermo,
        geometry=GeometryResult(
            throat_area_m2=0.01,
            throat_radius_m=0.0564,
            exit_area_m2=0.18,
            exit_radius_m=0.2394,
            mass_flow_kg_per_s=35.0,
        ),
        contour=[],
    )


def test_build_geometry_preview_bundle_uses_preview_inputs() -> None:
    base_bundle = _make_base_bundle()
    preview_inputs = InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=7.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=24.0,
        ambient_pressure_pa=101_325.0,
        contraction_ratio=3.4,
        characteristic_length_m=1.2,
        bell_length_fraction_percent=90.0,
        throat_upstream_radius_m=0.08,
        throat_downstream_radius_m=0.02,
        convergent_half_angle_deg=38.0,
        chamber_corner_radius_m=0.01,
    )

    preview_bundle = build_geometry_preview_bundle(base_bundle, preview_inputs)

    assert preview_bundle.inputs.expansion_ratio == 24.0
    assert preview_bundle.geometry.current_expansion_ratio == 24.0
    assert preview_bundle.inputs.bell_length_fraction_percent == 90.0
    assert preview_bundle.inputs.manual_nozzle_length_m is None
    assert preview_bundle.geometry.top_nozzle_length_fraction_percent == 90.0
    assert preview_bundle.geometry.chamber_radius_m is not None
    assert preview_bundle.contour[0].x_m < 0.0
    assert preview_bundle.contour[-1].x_m > 0.0


def test_build_geometry_preview_bundle_marks_preview_profile_as_area_ratio_remap() -> None:
    base_bundle = _make_base_bundle()
    preview_bundle = build_geometry_preview_bundle(
        base_bundle,
        replace(base_bundle.inputs, chamber_corner_radius_m=0.005),
    )

    assert any(
        "preview area-ratio remapped from previous CEA" in point.state.source
        for point in preview_bundle.thermochemistry_profile
        if point.region != "chamber"
    )


def test_build_geometry_preview_bundle_uses_last_thermochemistry_gamma_for_flow_case_gate() -> None:
    base_bundle = _make_base_bundle()
    base_bundle.thermochemistry.gamma = 1.67
    preview_inputs = InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=1.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=24.0,
        ambient_pressure_pa=5.2e5,
        contraction_ratio=3.4,
        characteristic_length_m=1.2,
    )

    preview_bundle = build_geometry_preview_bundle(base_bundle, preview_inputs)

    assert preview_bundle.inputs.expansion_ratio == 1.0
    assert preview_bundle.geometry.current_expansion_ratio == 1.0
    assert preview_bundle.contour[-1].x_m == 0.0


def test_with_liner_mass_adds_estimate_for_constant_wall() -> None:
    base_bundle = _make_base_bundle()
    preview_bundle = build_geometry_preview_bundle(base_bundle, base_bundle.inputs)
    updated_bundle = with_liner_mass(preview_bundle)

    assert updated_bundle.geometry.estimated_liner_mass_kg is not None
    assert updated_bundle.geometry.estimated_liner_mass_kg > 0.0


def test_estimate_liner_mass_returns_none_without_contour() -> None:
    base_bundle = _make_base_bundle()
    assert estimate_liner_mass_kg(base_bundle.inputs, []) is None


def test_current_design_bundle_stale_detection_tracks_visible_input_changes() -> None:
    base_bundle = _make_base_bundle()
    committed_bundle = build_geometry_preview_bundle(base_bundle, base_bundle.inputs)

    assert is_current_design_bundle_stale(base_bundle.inputs, committed_bundle) is False
    assert (
        is_current_design_bundle_stale(
            replace(base_bundle.inputs, characteristic_length_m=1.25),
            committed_bundle,
        )
        is True
    )


def test_validate_bundle_geometry_synchronization_accepts_aligned_preview_bundle() -> None:
    base_bundle = _make_base_bundle()
    committed_bundle = build_geometry_preview_bundle(base_bundle, base_bundle.inputs)

    issues = validate_bundle_geometry_synchronization(committed_bundle)

    assert issues == []
    assert "profile aligned" in format_bundle_geometry_summary(committed_bundle)


def test_validate_bundle_geometry_synchronization_reports_stale_profile_range() -> None:
    base_bundle = _make_base_bundle()
    committed_bundle = build_geometry_preview_bundle(base_bundle, base_bundle.inputs)
    for profile_point in committed_bundle.thermochemistry_profile:
        profile_point.x_m += 0.12

    issues = validate_bundle_geometry_synchronization(committed_bundle)

    assert any("x-range" in issue for issue in issues)

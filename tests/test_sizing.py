"""Tests for simple geometry helper functions."""

import math

import pytest

from engine.geometry.contour import generate_nozzle_contour
from engine.geometry.contour import build_thermochemistry_profile
from engine.geometry.separation import build_contour_markers, predict_separation_point
from engine.geometry.sizing import (
    area_ratio_from_radii,
    circle_area_from_radius,
    mass_flow_from_throat_area,
    radius_from_circle_area,
    size_engine_geometry,
    throat_area_from_thrust,
)
from engine.models import (
    BellContourVariant,
    ChemistryMode,
    InputParameters,
    NozzleContourMethod,
    ThermochemistryResult,
    ThermochemistryState,
)


def test_circle_area_from_radius() -> None:
    assert circle_area_from_radius(0.01) == pytest.approx(math.pi * 1.0e-4)


def test_radius_from_circle_area() -> None:
    assert radius_from_circle_area(math.pi * 4.0e-4) == pytest.approx(0.02)


def test_area_ratio_from_radii() -> None:
    assert area_ratio_from_radii(0.03, 0.01) == pytest.approx(9.0)


def test_circle_area_from_radius_rejects_non_positive_radius() -> None:
    with pytest.raises(ValueError):
        circle_area_from_radius(0.0)


def make_inputs(
    contour_method: NozzleContourMethod = NozzleContourMethod.BELL,
) -> InputParameters:
    return InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=8.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=20.0,
        ambient_pressure_pa=101_325.0,
        contraction_ratio=3.0,
        characteristic_length_m=1.2,
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        contour_method=contour_method,
        bell_variant=BellContourVariant.PARABOLA,
    )


def make_thermo() -> ThermochemistryResult:
    return ThermochemistryResult(
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        propellant_description="LOX / RP-1",
        chamber_temperature_k=3500.0,
        c_star_m_s=1750.0,
        isp_vac_s=320.0,
        isp_amb_s=285.0,
        cf_vac=1.79,
        cf_amb=1.60,
        gamma=1.2,
        molecular_weight_kg_per_mol=0.022,
        cp_j_per_kg_k=3200.0,
        viscosity_pa_s=8.0e-5,
        thermal_conductivity_w_per_m_k=0.2,
        prandtl_number=0.7,
        station_states={
            "chamber": ThermochemistryState(
                label="chamber",
                area_ratio=3.0,
                temperature_k=3500.0,
                density_kg_per_m3=5.0,
                enthalpy_j_per_kg=1.0e6,
                cp_j_per_kg_k=3200.0,
                viscosity_pa_s=8.0e-5,
                thermal_conductivity_w_per_m_k=0.2,
                prandtl_number=0.7,
                gamma=1.2,
                molecular_weight_kg_per_mol=0.022,
                mach_number=0.2,
                species_mass_fractions={"CO": 0.35, "H2O": 0.30},
                species_mole_fractions={"CO": 0.34, "H2O": 0.29},
            ),
            "throat": ThermochemistryState(
                label="throat",
                area_ratio=1.0,
                temperature_k=3300.0,
                density_kg_per_m3=4.2,
                enthalpy_j_per_kg=9.0e5,
                cp_j_per_kg_k=3000.0,
                viscosity_pa_s=7.5e-5,
                thermal_conductivity_w_per_m_k=0.18,
                prandtl_number=0.72,
                gamma=1.19,
                molecular_weight_kg_per_mol=0.0215,
                mach_number=1.0,
                species_mass_fractions={"CO": 0.33, "H2O": 0.28},
                species_mole_fractions={"CO": 0.32, "H2O": 0.27},
            ),
            "exit": ThermochemistryState(
                label="exit",
                area_ratio=20.0,
                temperature_k=2100.0,
                density_kg_per_m3=1.6,
                enthalpy_j_per_kg=7.0e5,
                cp_j_per_kg_k=2500.0,
                viscosity_pa_s=6.0e-5,
                thermal_conductivity_w_per_m_k=0.12,
                prandtl_number=0.78,
                gamma=1.16,
                molecular_weight_kg_per_mol=0.0208,
                mach_number=3.2,
                species_mass_fractions={"CO": 0.25, "H2O": 0.20},
                species_mole_fractions={"CO": 0.24, "H2O": 0.19},
            ),
        },
    )


def test_throat_area_from_thrust() -> None:
    assert throat_area_from_thrust(100_000.0, 8.0e6, 1.6) == pytest.approx(0.0078125)


def test_mass_flow_from_throat_area() -> None:
    assert mass_flow_from_throat_area(0.0078125, 8.0e6, 1750.0) == pytest.approx(35.7142857)


def test_size_engine_geometry_computes_optional_chamber_values() -> None:
    geometry = size_engine_geometry(make_inputs(), make_thermo())

    assert geometry.throat_area_m2 == pytest.approx(0.0078125)
    assert geometry.exit_area_m2 == pytest.approx(0.15625)
    assert geometry.chamber_area_m2 == pytest.approx(0.0234375)
    assert geometry.chamber_volume_m3 == pytest.approx(0.009375)
    assert geometry.chamber_length_m == pytest.approx(0.4)


def test_generate_nozzle_contour_creates_exportable_points() -> None:
    geometry = size_engine_geometry(make_inputs(), make_thermo())

    contour = generate_nozzle_contour(
        geometry,
        method=NozzleContourMethod.BELL,
        bell_variant=BellContourVariant.PARABOLA,
        points_per_segment=12,
    )

    assert len(contour) > 12
    assert contour[0].x_m < 0.0
    assert contour[-1].x_m > 0.0
    assert contour[-1].area_m2 == pytest.approx(geometry.exit_area_m2)
    assert geometry.reference_conical_length_m is not None
    assert geometry.current_nozzle_length_m is not None
    assert geometry.current_nozzle_length_m < geometry.reference_conical_length_m


def test_generate_nozzle_contour_supports_conic_option() -> None:
    geometry = size_engine_geometry(make_inputs(NozzleContourMethod.CONIC), make_thermo())

    contour = generate_nozzle_contour(
        geometry,
        method=NozzleContourMethod.CONIC,
        points_per_segment=12,
    )

    assert contour[-1].area_m2 == pytest.approx(geometry.exit_area_m2)
    assert contour[-1].x_m > 0.0


def test_build_thermochemistry_profile_maps_station_data_to_contour() -> None:
    geometry = size_engine_geometry(make_inputs(), make_thermo())
    contour = generate_nozzle_contour(
        geometry,
        method=NozzleContourMethod.BELL,
        bell_variant=BellContourVariant.PARABOLA,
        points_per_segment=12,
    )

    profile = build_thermochemistry_profile(contour, geometry, make_thermo())

    assert len(profile) == len(contour)
    assert profile[0].state.temperature_k == pytest.approx(3500.0)
    assert profile[-1].state.temperature_k == pytest.approx(2100.0)
    assert any(point.region == "diverging" for point in profile)
    assert profile[-1].state.adiabatic_wall_temperature_k is not None
    assert profile[-1].state.velocity_boundary_layer_thickness_m is not None
    assert profile[-1].state.thermal_boundary_layer_thickness_m is not None
    assert profile[-1].station_index == len(profile) - 1


def test_predict_separation_point_and_markers() -> None:
    inputs = make_inputs()
    inputs.ambient_pressure_pa = 4.5e5
    thermo = make_thermo()
    thermo.optimal_expansion_ratio = 12.0
    geometry = size_engine_geometry(inputs, thermo)
    contour = generate_nozzle_contour(
        geometry,
        method=NozzleContourMethod.BELL,
        bell_variant=BellContourVariant.PARABOLA,
        points_per_segment=16,
    )
    profile = build_thermochemistry_profile(contour, geometry, thermo)

    from engine.models import ExportBundle

    bundle = ExportBundle(
        inputs=inputs,
        thermochemistry=thermo,
        geometry=geometry,
        contour=contour,
        thermochemistry_profile=profile,
    )
    separation = predict_separation_point(bundle)
    markers = build_contour_markers(bundle, separation)

    assert separation is not None
    assert any(marker.label == "throat" for marker in markers)
    assert any(marker.label == "exit" for marker in markers)
    assert any("optimal" in marker.label for marker in markers)
    assert any(marker.label == "separation" for marker in markers)

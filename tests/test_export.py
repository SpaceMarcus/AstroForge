"""Tests for export helpers."""

from pathlib import Path

from engine.io import export_engine_preset, load_engine_preset
from engine.io.export import bundle_to_dict, export_bundle, export_geometry_to_csv, export_geometry_to_json
from engine.models import (
    BellContourVariant,
    ChemistryMode,
    ExportBundle,
    GeometryResult,
    InputParameters,
    ManufacturingMode,
    ManufacturingRoute,
    NozzleContourMethod,
    NozzlePoint,
    OFSweepMetric,
    OFSweepPoint,
    OFSweepResult,
    ThermochemistryResult,
    ThermochemistryProfilePoint,
    ThermochemistryState,
    WallThicknessMode,
)
from engine.project_state import ProjectManagementData, ProjectMode
from engine.unit_system import UnitPreset


def make_bundle() -> ExportBundle:
    inputs = InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=7.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=20.0,
        ambient_pressure_pa=101_325.0,
        contraction_ratio=3.0,
        characteristic_length_m=1.1,
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
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
        molecular_weight_kg_per_mol=0.022,
        cp_j_per_kg_k=3200.0,
        viscosity_pa_s=8.0e-5,
        thermal_conductivity_w_per_m_k=0.2,
        prandtl_number=0.7,
    )
    geometry = GeometryResult(
        throat_area_m2=0.0078,
        throat_radius_m=0.0498,
        exit_area_m2=0.156,
        exit_radius_m=0.223,
        mass_flow_kg_per_s=35.7,
    )
    contour = [
        NozzlePoint(x_m=0.0, radius_m=0.05, area_m2=0.00785),
        NozzlePoint(x_m=0.4, radius_m=0.22, area_m2=0.15205),
    ]
    thermo_profile = [
        ThermochemistryProfilePoint(
            x_m=0.0,
            radius_m=0.05,
            area_m2=0.00785,
            region="throat",
            state=ThermochemistryState(
                label="throat",
                area_ratio=1.0,
                temperature_k=3200.0,
                adiabatic_wall_temperature_k=3400.0,
                thermal_boundary_layer_thickness_m=0.0012,
                velocity_boundary_layer_thickness_m=0.0015,
                species_mass_fractions={"CO": 0.3},
                species_mole_fractions={"CO": 0.29},
            ),
        )
    ]
    return ExportBundle(
        inputs=inputs,
        thermochemistry=thermo,
        geometry=geometry,
        contour=contour,
        thermochemistry_profile=thermo_profile,
        of_sweep=OFSweepResult(
            fuel="RP-1",
            oxidizer="LOX",
            chemistry_mode=ChemistryMode.EQUILIBRIUM,
            chamber_pressure_pa=7.0e6,
            expansion_ratio=20.0,
            stoichiometric_mixture_ratio=3.4,
            peak_isp_vac_mixture_ratio=2.7,
            peak_c_star_mixture_ratio=2.8,
            points=[
                OFSweepPoint(
                    mixture_ratio=2.6,
                    equivalence_ratio=1.3,
                    c_star_m_s=1750.0,
                    isp_vac_s=320.0,
                    chamber_temperature_k=3500.0,
                    is_fuel_rich=True,
                    is_oxidizer_rich=False,
                )
            ],
        ),
    )


def test_bundle_to_dict_contains_serializable_nested_data() -> None:
    bundle_dict = bundle_to_dict(make_bundle())

    assert bundle_dict["inputs"]["chemistry_mode"] == "equilibrium"
    assert bundle_dict["geometry"]["throat_area_m2"] == 0.0078
    assert isinstance(bundle_dict["contour"], list)
    assert isinstance(bundle_dict["thermochemistry_profile"], list)


def test_export_bundle_writes_json_and_csv_files(tmp_path: Path) -> None:
    written_files = export_bundle(make_bundle(), tmp_path / "case")

    assert written_files["json"].exists()
    assert written_files["summary_csv"].exists()
    assert written_files["contour_csv"].exists()
    assert written_files["thermo_profile_csv"].exists()


def test_geometry_only_exports_write_requested_files(tmp_path: Path) -> None:
    bundle = make_bundle()

    geometry_json = export_geometry_to_json(bundle, tmp_path / "geometry.json")
    geometry_csv = export_geometry_to_csv(bundle, tmp_path / "geometry.csv")

    assert geometry_json.exists()
    assert geometry_csv.exists()


def test_engine_preset_roundtrip_preserves_inputs_and_ui_state(tmp_path: Path) -> None:
    inputs = InputParameters(
        fuel="CH4",
        oxidizer="LOX",
        chamber_pressure_pa=9.5e6,
        thrust_n=150_000.0,
        mixture_ratio=3.25,
        expansion_ratio=28.0,
        ambient_pressure_pa=45_000.0,
        contraction_ratio=2.8,
        characteristic_length_m=0.95,
        chemistry_mode=ChemistryMode.FROZEN_AT_THROAT,
        contour_method=NozzleContourMethod.BELL,
        bell_variant=BellContourVariant.PARABOLA,
        manual_nozzle_length_m=0.72,
        throat_upstream_radius_m=0.012,
        throat_downstream_radius_m=0.008,
        convergent_half_angle_deg=38.0,
        manufacturing_mode=ManufacturingMode.TRADITIONAL,
        manufacturing_route=ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT,
        liner_material="GRCop-42",
        liner_coating_enabled=True,
        liner_coating="Ceramic TBC",
        wall_thickness_mode=WallThicknessMode.CONSTANT,
        wall_thickness_m=0.0018,
    )

    project_management = ProjectManagementData(
        allow_initial_design_editing_after_run=True,
        mission_objectives="Reusable booster demonstrator",
        requirements="Sea-level ignition and rapid turnaround",
        constraints="Manufacturing by conventional milling",
        budgets="Development budget capped in phase A",
        thrust_requirement=">= 150 kN at sea level",
        pressure_requirement="Operate from sea level to altitude tests",
        throttling_requirement="Target 60-100% throttle window",
        max_length="Nozzle package should stay below 900 mm",
        wall_temperature_constraint="Keep wall temperatures below test article limits",
        manufacturing_constraint="Prefer CuCrZr-compatible processes",
        mass_budget="Stay within vehicle aft-bay mass margin",
    )

    preset_path = export_engine_preset(
        inputs,
        tmp_path / "engine_preset.astraforge.json",
        of_sweep_metric=OFSweepMetric.C_STAR,
        selected_mixture_ratio=3.10,
        unit_preset=UnitPreset.US,
        project_mode=ProjectMode.GUIDED,
        system_engineering_enabled=True,
        project_management=project_management,
    )
    loaded_inputs, ui_state = load_engine_preset(preset_path)

    assert preset_path.exists()
    assert loaded_inputs == inputs
    assert ui_state["of_sweep_metric"] is OFSweepMetric.C_STAR
    assert ui_state["selected_mixture_ratio"] == 3.10
    assert ui_state["unit_preset"] is UnitPreset.US
    assert ui_state["project_mode"] is ProjectMode.GUIDED
    assert ui_state["system_engineering_enabled"] is True
    assert ui_state["project_management"] == project_management

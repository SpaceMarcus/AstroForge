"""Tests for the annulus-cooling thermal-analysis reference model."""

from engine.gui.thermal_analysis_page import (
    _THERMAL_PLOT_FIELDS,
    _build_plot_export_rows,
    _build_plot_payload,
)
from engine.models import (
    ChemistryMode,
    ExportBundle,
    GeometryResult,
    InputParameters,
    NozzlePoint,
    ThermochemistryProfilePoint,
    ThermochemistryResult,
    ThermochemistryState,
)
from engine.thermal_analysis import (
    _compute_station_mechanical_screening,
    BartzThroatCurvatureMode,
    CoolingFlowDirection,
    ParticipatingSpeciesMode,
    PressureCalculationMode,
    RadiationModelType,
    RadiationSettings,
    StationDistributionMode,
    ThermalAnalysisInputs,
    ThermalModelType,
    ThermalSolverType,
    default_thermal_analysis_inputs,
    run_thermal_analysis,
)
from engine.unit_system import UnitPreset
from engine.utils.validation import InputValidationError


def _make_bundle() -> ExportBundle:
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
        liner_material="CuCrZr",
        wall_thickness_m=0.0015,
    )
    contour = [
        NozzlePoint(x_m=-0.22, radius_m=0.090, area_m2=0.025447),
        NozzlePoint(x_m=-0.12, radius_m=0.090, area_m2=0.025447),
        NozzlePoint(x_m=-0.02, radius_m=0.070, area_m2=0.015394),
        NozzlePoint(x_m=0.00, radius_m=0.050, area_m2=0.007854),
        NozzlePoint(x_m=0.18, radius_m=0.110, area_m2=0.038013),
        NozzlePoint(x_m=0.42, radius_m=0.190, area_m2=0.113411),
    ]
    profile = [
        ThermochemistryProfilePoint(
            x_m=point.x_m,
            radius_m=point.radius_m,
            area_m2=point.area_m2,
            region="chamber" if point.x_m < 0.0 else "diverging",
            station_index=index,
            state=ThermochemistryState(
                label=f"station-{index}",
                temperature_k=3400.0 - 180.0 * index,
                adiabatic_wall_temperature_k=3520.0 - 160.0 * index,
                cp_j_per_kg_k=3250.0 - 30.0 * index,
                viscosity_pa_s=8.0e-5 + 1.0e-6 * index,
                thermal_conductivity_w_per_m_k=0.16,
                prandtl_number=0.72,
                gamma=1.20,
                molecular_weight_kg_per_mol=0.022,
                mach_number=0.05 + 0.45 * index,
                thermal_boundary_layer_thickness_m=0.0012 + 0.0001 * index,
                species_mass_fractions={"CO2": 0.18 - 0.01 * index, "H2O": 0.22 - 0.015 * index, "CO": 0.03 + 0.002 * index},
                species_mole_fractions={"CO2": 0.16 - 0.01 * index, "H2O": 0.20 - 0.015 * index, "CO": 0.025 + 0.002 * index},
            ),
        )
        for index, point in enumerate(contour)
    ]
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
        thermal_conductivity_w_per_m_k=0.2,
    )
    geometry = GeometryResult(
        throat_area_m2=0.007854,
        throat_radius_m=0.05,
        exit_area_m2=0.113411,
        exit_radius_m=0.19,
        mass_flow_kg_per_s=35.0,
        chamber_area_m2=0.025447,
        chamber_radius_m=0.09,
        chamber_volume_m3=0.009,
        chamber_length_m=0.12,
        contour_length_m=0.64,
        current_expansion_ratio=18.0,
    )
    return ExportBundle(
        inputs=inputs,
        thermochemistry=thermo,
        geometry=geometry,
        contour=contour,
        thermochemistry_profile=profile,
    )


def test_default_thermal_inputs_seed_from_fuel_flow() -> None:
    bundle = _make_bundle()

    thermal_inputs = default_thermal_analysis_inputs(bundle, fuel_name=bundle.inputs.fuel)

    assert thermal_inputs.coolant_type == "RP-1"
    assert thermal_inputs.coolant_mass_flow_kg_per_s is not None
    assert thermal_inputs.coolant_mass_flow_kg_per_s > 0.0
    assert thermal_inputs.coolant_inlet_temperature_k == 293.15
    assert thermal_inputs.solver_settings.station_tolerance == 0.1


def test_run_thermal_analysis_returns_station_results_and_summary() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert len(result.stations) == thermal_inputs.solver_settings.station_count
    assert result.summary.total_heat_into_coolant_w is not None
    assert result.summary.total_heat_into_coolant_w > 0.0
    assert result.summary.total_coolant_pressure_drop_pa is not None
    assert result.summary.total_coolant_pressure_drop_pa > 0.0
    assert result.summary.estimated_isp_gain_s is None
    assert result.stations[0].iterations is not None
    assert result.stations[0].converged is True
    assert result.stations[0].residual_k is not None
    assert "coolant properties from table" in result.stations[0].status
    assert "material properties from screening table" in result.stations[0].status
    assert "coolant properties from table" in result.stations[0].status_summary
    assert result.stations[0].warning_summary != ""
    assert result.stations[0].coolant_cp_j_per_kg_k is not None
    assert result.stations[0].coolant_viscosity_pa_s is not None
    assert result.stations[0].wall_mean_temperature_k is not None
    assert result.stations[0].hoop_stress_pa is not None
    assert result.stations[0].equivalent_von_mises_stress_pa is not None
    assert result.stations[0].material_margin_status is not None
    assert result.stations[0].total_screening_strain is not None
    assert result.summary.coolant_property_source == "table"
    assert result.summary.material_property_source == "screening-table"
    assert result.summary.max_von_mises_stress_pa is not None
    assert result.summary.max_total_screening_strain is not None


def test_run_thermal_analysis_computes_closeout_screening_when_enabled() -> None:
    bundle = _make_bundle()
    bundle.inputs.closeout_enabled = True
    bundle.inputs.closeout_thickness_m = 0.003
    bundle.inputs.closeout_material = "Inconel 718"
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert result.stations[0].closeout_thickness_m == 0.003
    assert result.stations[0].closeout_material == "Inconel 718"
    assert result.stations[0].closeout_hoop_stress_pa is not None
    assert result.stations[0].closeout_material_strength_margin is not None
    assert "closeout stress is screening-level shell estimate" in result.stations[0].status


def test_mechanical_screening_matches_pressure_only_shell_case_when_wall_delta_t_is_zero() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )
    station = run_thermal_analysis(bundle, thermal_inputs).stations[0]
    station.wall_temperature_hot_gas_side_k = 650.0
    station.wall_temperature_coolant_side_k = 650.0

    screening = _compute_station_mechanical_screening(
        station=station,
        gas_pressure_pa=5.0e6,
        coolant_pressure_pa=8.0e6,
        wall_thickness_m=bundle.inputs.wall_thickness_m or 0.0015,
        wall_material_id="Inconel 718",
        reference_temperature_k=293.15,
        closeout_enabled=False,
        closeout_thickness_m=None,
        closeout_material_id=None,
    )

    pressure_only_vm = (
        screening.pressure_longitudinal_stress_pa ** 2
        + screening.pressure_hoop_stress_pa ** 2
        - screening.pressure_longitudinal_stress_pa * screening.pressure_hoop_stress_pa
    ) ** 0.5
    assert screening.thermal_gradient_stress_upper_bound_pa == 0.0
    assert screening.von_mises_hot_side_pa is not None
    assert abs(screening.von_mises_hot_side_pa - pressure_only_vm) < 1.0
    assert abs(screening.equivalent_von_mises_stress_pa - pressure_only_vm) < 1.0


def test_mechanical_screening_uses_symmetric_gradient_indicator_without_pressure() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )
    station = run_thermal_analysis(bundle, thermal_inputs).stations[0]
    station.wall_temperature_hot_gas_side_k = 900.0
    station.wall_temperature_coolant_side_k = 500.0

    screening = _compute_station_mechanical_screening(
        station=station,
        gas_pressure_pa=7.0e6,
        coolant_pressure_pa=7.0e6,
        wall_thickness_m=bundle.inputs.wall_thickness_m or 0.0015,
        wall_material_id="Inconel 718",
        reference_temperature_k=293.15,
        closeout_enabled=False,
        closeout_thickness_m=None,
        closeout_material_id=None,
    )

    assert screening.pressure_hoop_stress_pa == 0.0
    assert screening.von_mises_hot_side_pa is not None
    assert screening.von_mises_cold_side_pa is not None
    assert abs(screening.von_mises_hot_side_pa - screening.von_mises_cold_side_pa) < 1.0


def test_mechanical_screening_uses_hot_side_yield_for_governing_margin_when_hot_wall_is_weaker() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )
    station = run_thermal_analysis(bundle, thermal_inputs).stations[0]
    station.wall_temperature_hot_gas_side_k = 1088.71
    station.wall_temperature_coolant_side_k = 588.71

    screening = _compute_station_mechanical_screening(
        station=station,
        gas_pressure_pa=6.2e6,
        coolant_pressure_pa=8.5e6,
        wall_thickness_m=bundle.inputs.wall_thickness_m or 0.0015,
        wall_material_id="Inconel 718",
        reference_temperature_k=293.15,
        closeout_enabled=False,
        closeout_thickness_m=None,
        closeout_material_id=None,
    )

    assert screening.yield_strength_hot_side_pa is not None
    assert screening.yield_strength_cold_side_pa is not None
    assert screening.yield_strength_hot_side_pa < screening.yield_strength_cold_side_pa
    assert screening.material_yield_strength_pa == screening.yield_strength_hot_side_pa


def test_mechanical_screening_flags_expected_local_plasticity_when_elastic_vm_exceeds_yield() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )
    station = run_thermal_analysis(bundle, thermal_inputs).stations[0]
    station.wall_temperature_hot_gas_side_k = 1088.71
    station.wall_temperature_coolant_side_k = 500.0

    screening = _compute_station_mechanical_screening(
        station=station,
        gas_pressure_pa=2.0e6,
        coolant_pressure_pa=15.0e6,
        wall_thickness_m=bundle.inputs.wall_thickness_m or 0.0015,
        wall_material_id="GRCop-42",
        reference_temperature_k=293.15,
        closeout_enabled=False,
        closeout_thickness_m=None,
        closeout_material_id=None,
    )

    assert screening.material_margin_status == "exceeded"
    assert screening.plasticity_expected_hot_side or screening.plasticity_expected_cold_side
    assert any("plasticity expected" in note for note in screening.status_notes)


def test_run_thermal_analysis_supports_reverse_flow_direction() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        flow_direction=CoolingFlowDirection.INJECTOR_TO_NOZZLE,
    )
    thermal_inputs.solver_settings.solver_type = ThermalSolverType.CRANK_NICOLSON
    thermal_inputs.solver_settings.station_count = 8

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert len(result.stations) == 8
    assert result.stations[0].x_mid_m < result.stations[-1].x_mid_m


def test_run_thermal_analysis_reverses_station_order_for_nozzle_to_injector() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        flow_direction=CoolingFlowDirection.NOZZLE_TO_INJECTOR,
    )
    thermal_inputs.solver_settings.station_count = 8

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert result.stations[0].x_mid_m > result.stations[-1].x_mid_m


def test_run_thermal_analysis_can_use_cea_profile_station_grid() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )
    thermal_inputs.solver_settings.station_distribution_mode = StationDistributionMode.CEA_PROFILE

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert len(result.stations) == len(bundle.thermochemistry_profile) - 1


def test_run_thermal_analysis_manual_station_mode_uses_nearest_profile_point_by_x() -> None:
    bundle = _make_bundle()
    bundle.thermochemistry_profile = [
        bundle.thermochemistry_profile[0],
        bundle.thermochemistry_profile[-1],
    ]
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        flow_direction=CoolingFlowDirection.INJECTOR_TO_NOZZLE,
    )
    thermal_inputs.solver_settings.station_count = 4

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert "gas-side recovery placeholder" not in result.stations[0].status


def test_run_thermal_analysis_warns_when_cea_profile_looks_stale_against_contour() -> None:
    bundle = _make_bundle()
    for profile_point in bundle.thermochemistry_profile:
        profile_point.x_m += 0.05
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )
    thermal_inputs.solver_settings.station_distribution_mode = StationDistributionMode.CEA_PROFILE

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert "CEA-profile alignment warning" in result.stations[0].status
    assert "bundle debug:" in result.stations[0].status
    assert "CEA-profile alignment warning" in result.stations[0].warning_summary
    assert "bundle debug:" in result.stations[0].status_summary


def test_run_thermal_analysis_uses_requested_coolant_inlet_temperature() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        coolant_inlet_temperature_k=305.0,
    )
    thermal_inputs.solver_settings.station_count = 6

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert result.stations[0].coolant_temperature_in_k == 305.0


def test_run_thermal_analysis_marks_laminar_coolant_flow() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=0.01,
        coolant_type="RP-1",
    )
    thermal_inputs.solver_settings.station_count = 5

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert result.stations[0].nusselt_coolant == 3.66
    assert "laminar" in result.stations[0].status


def test_run_thermal_analysis_marks_transitional_coolant_regime_as_uncertain() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=3.0,
        coolant_type="RP-1",
    )
    thermal_inputs.solver_settings.station_count = 5

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert result.stations[0].reynolds_coolant is not None
    assert 2_300.0 <= result.stations[0].reynolds_coolant < 10_000.0
    assert result.stations[0].nusselt_coolant is not None
    assert result.stations[0].nusselt_coolant > 3.66
    assert "transitional" in result.stations[0].status
    assert "coolant Nu correlation uncertain" in result.stations[0].status
    assert "transitional" in result.stations[0].status_summary
    assert "coolant Nu correlation uncertain" in result.stations[0].warning_summary


def test_run_thermal_analysis_uses_turbulent_correlations_above_re_10000() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=10.0,
        coolant_type="RP-1",
    )
    thermal_inputs.solver_settings.station_count = 5

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert result.stations[0].reynolds_coolant is not None
    assert result.stations[0].reynolds_coolant >= 10_000.0
    assert result.stations[0].nusselt_coolant is not None
    assert result.stations[0].nusselt_coolant > 3.66
    assert "turbulent" in result.stations[0].status


def test_run_thermal_analysis_uses_bartz_gas_side_heat_transfer() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )
    thermal_inputs.solver_settings.station_count = 6

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert result.stations[0].h_g_w_per_m2_k is not None
    assert result.stations[0].h_g_w_per_m2_k > 0.0
    assert "Bartz" in result.stations[0].status


def test_run_thermal_analysis_keeps_convection_only_behavior_when_radiation_disabled() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        radiation_settings=RadiationSettings(enabled=False),
    )
    thermal_inputs.solver_settings.station_count = 6

    result = run_thermal_analysis(bundle, thermal_inputs)

    first_station = result.stations[0]
    assert first_station.q_rad_w_per_m2 == 0.0
    assert first_station.q_radiation_station_w == 0.0
    assert first_station.q_total_w_per_m2 == first_station.q_hot_w_per_m2
    assert first_station.q_conv_w_per_m2 == first_station.q_hot_w_per_m2
    assert "radiation disabled" in first_station.status
    assert result.summary.radiation_enabled is False
    assert result.summary.total_radiation_heat_w == 0.0


def test_run_thermal_analysis_can_add_grey_gas_radiation() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        radiation_settings=RadiationSettings(
            enabled=True,
            model=RadiationModelType.GREY_GAS,
            wall_emissivity=0.8,
            gas_effective_emissivity=0.2,
        ),
    )
    thermal_inputs.solver_settings.station_count = 6

    result = run_thermal_analysis(bundle, thermal_inputs)

    first_station = result.stations[0]
    assert first_station.q_rad_w_per_m2 is not None
    assert first_station.q_rad_w_per_m2 > 0.0
    assert first_station.q_conv_w_per_m2 is not None
    assert first_station.q_total_w_per_m2 is not None
    assert first_station.q_total_w_per_m2 > first_station.q_conv_w_per_m2
    assert "radiation: grey gas" in first_station.status
    assert result.summary.radiation_enabled is True
    assert result.summary.total_radiation_heat_w is not None
    assert result.summary.total_radiation_heat_w > 0.0


def test_run_thermal_analysis_uses_local_cea_species_for_participating_media() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        radiation_settings=RadiationSettings(
            enabled=True,
            model=RadiationModelType.PARTICIPATING_MEDIA_EFFECTIVE_EMISSIVITY,
            participating_media_enabled=True,
            participating_species_mode=ParticipatingSpeciesMode.CO2_H2O_ONLY,
        ),
    )
    thermal_inputs.solver_settings.station_count = 6

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert "species source: local CEA mole fractions" in result.stations[0].status
    assert "participating species:" in result.stations[0].status
    assert "CO2=" in result.stations[0].status
    assert result.stations[0].participating_species_mode == ParticipatingSpeciesMode.CO2_H2O_ONLY.value


def test_run_thermal_analysis_participating_media_falls_back_to_fixed_emissivity_without_mole_fractions() -> None:
    bundle = _make_bundle()
    for profile_point in bundle.thermochemistry_profile:
        profile_point.state.species_mole_fractions = {}
        profile_point.state.species_mass_fractions = {}
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        radiation_settings=RadiationSettings(
            enabled=True,
            model=RadiationModelType.PARTICIPATING_MEDIA_EFFECTIVE_EMISSIVITY,
            participating_media_enabled=True,
        ),
    )
    thermal_inputs.solver_settings.station_count = 6

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert "participating media fallback: fixed effective gas emissivity" in result.stations[0].status
    assert "no local CEA species mole fractions available" in result.stations[0].status


def test_run_thermal_analysis_all_polyatomic_mode_includes_co_species() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        radiation_settings=RadiationSettings(
            enabled=True,
            model=RadiationModelType.PARTICIPATING_MEDIA_EFFECTIVE_EMISSIVITY,
            participating_media_enabled=True,
            participating_species_mode=ParticipatingSpeciesMode.ALL_RADIATING_POLYATOMIC,
        ),
    )
    thermal_inputs.solver_settings.station_count = 6

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert "species source: local CEA mole fractions" in result.stations[0].status
    assert "participating species:" in result.stations[0].status
    assert "CO=" in result.stations[0].status


def test_run_thermal_analysis_supports_user_fixed_radiation_heat_flux() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        radiation_settings=RadiationSettings(
            enabled=True,
            model=RadiationModelType.USER_FIXED_HEAT_FLUX,
            fixed_radiation_heat_flux_w_per_m2=25_000.0,
        ),
    )
    thermal_inputs.solver_settings.station_count = 6

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert result.stations[0].q_rad_w_per_m2 == 25_000.0
    assert "user fixed heat flux" in result.stations[0].status


def test_run_thermal_analysis_validates_radiation_emissivity_range() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        radiation_settings=RadiationSettings(enabled=True, wall_emissivity=1.2),
    )

    try:
        run_thermal_analysis(bundle, thermal_inputs)
    except InputValidationError as exc:
        assert "Wall emissivity must be between 0 and 1." in str(exc)
    else:  # pragma: no cover - defensive guard
        raise AssertionError("Expected InputValidationError for invalid wall emissivity")


def test_bartz_curvature_selection_changes_heat_transfer_level() -> None:
    bundle = _make_bundle()
    upstream_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        bartz_throat_curvature_mode=BartzThroatCurvatureMode.UPSTREAM,
    )
    downstream_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        bartz_throat_curvature_mode=BartzThroatCurvatureMode.DOWNSTREAM,
    )
    upstream_inputs.solver_settings.station_count = 6
    downstream_inputs.solver_settings.station_count = 6

    upstream_result = run_thermal_analysis(bundle, upstream_inputs)
    downstream_result = run_thermal_analysis(bundle, downstream_inputs)

    assert upstream_result.stations[0].h_g_w_per_m2_k is not None
    assert downstream_result.stations[0].h_g_w_per_m2_k is not None
    assert upstream_result.stations[0].h_g_w_per_m2_k != downstream_result.stations[0].h_g_w_per_m2_k


def test_run_thermal_analysis_rejects_future_model_selection() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        model_type=ThermalModelType.CHANNELS_FUTURE,
    )

    try:
        run_thermal_analysis(bundle, thermal_inputs)
    except InputValidationError as exc:
        assert "annulus reference model" in str(exc)
    else:  # pragma: no cover - defensive guard
        raise AssertionError("Expected InputValidationError for future model selection")


def test_backward_pressure_mode_reconstructs_required_pump_pressure() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        injector_pressure_drop_pa=800_000.0,
        pressure_margin_pa=150_000.0,
        external_feed_pressure_drop_pa=120_000.0,
    )
    thermal_inputs.solver_settings.station_count = 6
    thermal_inputs.solver_settings.pressure_mode = PressureCalculationMode.BACKWARD_REQUIRED_PUMP

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert result.summary.required_cooling_inlet_pressure_pa is not None
    assert result.summary.required_pump_discharge_pressure_pa is not None
    assert result.summary.total_coolant_pressure_drop_pa is not None
    assert result.summary.required_cooling_inlet_pressure_pa > (
        bundle.inputs.chamber_pressure_pa + thermal_inputs.injector_pressure_drop_pa + thermal_inputs.pressure_margin_pa
    )
    assert result.summary.required_pump_discharge_pressure_pa == (
        result.summary.required_cooling_inlet_pressure_pa + thermal_inputs.external_feed_pressure_drop_pa
    )
    assert result.stations[0].required_pressure_in_pa is not None
    assert result.stations[-1].required_pressure_out_pa == (
        bundle.inputs.chamber_pressure_pa + thermal_inputs.injector_pressure_drop_pa + thermal_inputs.pressure_margin_pa
    )


def test_forward_pressure_check_uses_given_pump_discharge_pressure() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        injector_pressure_drop_pa=800_000.0,
        pressure_margin_pa=150_000.0,
        external_feed_pressure_drop_pa=120_000.0,
        pump_discharge_pressure_pa=8_500_000.0,
    )
    thermal_inputs.solver_settings.station_count = 6
    thermal_inputs.solver_settings.pressure_mode = PressureCalculationMode.FORWARD_PUMP_CHECK

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert result.summary.required_pump_discharge_pressure_pa == 8_500_000.0
    assert result.summary.required_cooling_inlet_pressure_pa == 8_380_000.0
    assert result.stations[0].required_pressure_in_pa == 8_380_000.0


def test_plot_payload_supports_r_of_x_and_heat_flux_over_x() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )

    result = run_thermal_analysis(bundle, thermal_inputs)
    payload = _build_plot_payload(result, "x_mid", ["r_inner", "q_hot"], UnitPreset.SI)

    assert payload.x_label.startswith("x ")
    assert payload.series[0].label.startswith("r(x)")
    assert payload.series[1].label.startswith("Heat flux q''")
    assert len(payload.x_values) == len(result.stations)
    assert len(payload.series[0].values) == len(result.stations)
    assert any(value is not None for value in payload.series[1].values)


def test_plot_payload_supports_radiation_quantities() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
        radiation_settings=RadiationSettings(enabled=True),
    )

    result = run_thermal_analysis(bundle, thermal_inputs)
    payload = _build_plot_payload(result, "x_mid", ["q_conv", "q_rad", "gas_emissivity"], UnitPreset.SI)

    assert payload.series[0].label.startswith("Convective heat flux")
    assert payload.series[1].label.startswith("Radiative heat flux")
    assert payload.series[2].label.startswith("Gas effective emissivity")


def test_plot_payload_supports_coolant_cp_and_viscosity() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )

    result = run_thermal_analysis(bundle, thermal_inputs)
    payload = _build_plot_payload(result, "x_mid", ["coolant_cp", "coolant_viscosity"], UnitPreset.SI)

    assert payload.series[0].label.startswith("Coolant cp")
    assert payload.series[1].label.startswith("Coolant viscosity µ")
    assert any(value is not None for value in payload.series[0].values)
    assert any(value is not None for value in payload.series[1].values)


def test_plot_export_rows_include_current_x_and_y_headers() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )

    result = run_thermal_analysis(bundle, thermal_inputs)
    payload = _build_plot_payload(result, "x_mid", ["r_inner"], UnitPreset.SI)
    rows = _build_plot_export_rows(payload)

    assert rows[0][0].startswith("x ")
    assert rows[0][1].startswith("r(x)")
    assert len(rows) == len(result.stations) + 1
    assert rows[1][0] != ""


def test_plot_payload_supports_mechanical_screening_quantities() -> None:
    bundle = _make_bundle()
    bundle.inputs.closeout_enabled = True
    bundle.inputs.closeout_thickness_m = 0.003
    bundle.inputs.closeout_material = "Inconel 718"
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=9.5,
        coolant_type="RP-1",
    )

    result = run_thermal_analysis(bundle, thermal_inputs)
    payload = _build_plot_payload(
        result,
        "x_mid",
        ["hoop_stress", "thermal_stress", "von_mises_stress", "closeout_hoop_stress"],
        UnitPreset.SI,
    )

    assert payload.series[0].label.startswith("Hoop stress")
    assert payload.series[1].label.startswith("Elastic thermal-stress indicator")
    assert payload.series[2].label.startswith("Von Mises stress")
    assert payload.series[3].label.startswith("Closeout hoop stress")
    assert payload.series[0].label.endswith("[MPa]")
    assert payload.series[2].label.endswith("[MPa]")
    assert any(value is not None for value in payload.series[0].values)


def test_plot_field_labels_are_human_readable() -> None:
    assert _THERMAL_PLOT_FIELDS["r_inner"].label == "r(x)"
    assert _THERMAL_PLOT_FIELDS["q_hot"].label == "Heat flux q''"
    assert _THERMAL_PLOT_FIELDS["q_rad"].label.startswith("Radiative heat flux")
    assert _THERMAL_PLOT_FIELDS["coolant_cp"].label == "Coolant cp"
    assert _THERMAL_PLOT_FIELDS["coolant_viscosity"].label == "Coolant viscosity µ"

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
    CoolingFlowDirection,
    PressureCalculationMode,
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
                thermal_conductivity_w_per_m_k=0.16,
                thermal_boundary_layer_thickness_m=0.0012 + 0.0001 * index,
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


def test_run_thermal_analysis_uses_turbulent_annulus_threshold_from_re_1664() -> None:
    bundle = _make_bundle()
    thermal_inputs = ThermalAnalysisInputs(
        coolant_mass_flow_kg_per_s=2.0,
        coolant_type="RP-1",
    )
    thermal_inputs.solver_settings.station_count = 5

    result = run_thermal_analysis(bundle, thermal_inputs)

    assert result.stations[0].reynolds_coolant is not None
    assert result.stations[0].reynolds_coolant > 1_664.0
    assert result.stations[0].nusselt_coolant is not None
    assert result.stations[0].nusselt_coolant > 3.66
    assert "turbulent" in result.stations[0].status


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


def test_plot_field_labels_are_human_readable() -> None:
    assert _THERMAL_PLOT_FIELDS["r_inner"].label == "r(x)"
    assert _THERMAL_PLOT_FIELDS["q_hot"].label == "Heat flux q''"

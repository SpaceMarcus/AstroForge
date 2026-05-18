"""Thermal Analysis page widgets for AstraForge."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from engine.gui.project_panels import ScrollableContentFrame
from engine.models import ExportBundle, InputParameters
from engine.thermal_analysis import (
    BartzThroatCurvatureMode,
    CoolingFlowDirection,
    OpticalPathLengthMode,
    ParticipatingMediaModelType,
    ParticipatingSpeciesMode,
    PressureCalculationMode,
    RadiationModelType,
    RadiationSettings,
    RadiationTemperatureSource,
    SolverSettings,
    StationDistributionMode,
    ThermalAnalysisInputs,
    ThermalModelType,
    ThermalAnalysisResult,
    ThermalSolverType,
    ThermalStationResult,
)
from engine.unit_system import UnitPreset, convert_to_display, format_quantity, get_unit_symbol
from engine.utils.validation import InputValidationError

try:  # pragma: no cover - depends on local matplotlib installation
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except Exception:  # pragma: no cover - depends on local matplotlib installation
    FigureCanvasTkAgg = None
    Figure = None

_FLOW_DIRECTION_LABELS = {
    CoolingFlowDirection.NOZZLE_TO_INJECTOR: "nozzle-to-injector",
    CoolingFlowDirection.INJECTOR_TO_NOZZLE: "injector-to-nozzle",
}
_FLOW_DIRECTION_VALUES = {label: value for value, label in _FLOW_DIRECTION_LABELS.items()}

_MODEL_TYPE_LABELS = {
    ThermalModelType.ANNULUS: "Annulus cooling reference",
    ThermalModelType.ANNULUS_WITH_FILM_FUTURE: "Annulus + film cooling (planned)",
    ThermalModelType.CHANNELS_FUTURE: "Channels (planned)",
    ThermalModelType.CHANNELS_WITH_FILM_FUTURE: "Channels + film cooling (planned)",
}
_MODEL_TYPE_VALUES = {label: value for value, label in _MODEL_TYPE_LABELS.items()}

_SOLVER_TYPE_LABELS = {
    ThermalSolverType.FORWARD_EULER: "Forward Euler",
    ThermalSolverType.BACKWARD_EULER: "Backward Euler",
    ThermalSolverType.CRANK_NICOLSON: "Crank-Nicolson",
    ThermalSolverType.NTU_EXPONENTIAL: "NTU / exponential station model",
}
_SOLVER_TYPE_VALUES = {label: value for value, label in _SOLVER_TYPE_LABELS.items()}

_STATION_MODE_LABELS = {
    StationDistributionMode.MANUAL: "Manual station count",
    StationDistributionMode.CEA_PROFILE: "Use CEA/profile stations",
}
_STATION_MODE_VALUES = {label: value for value, label in _STATION_MODE_LABELS.items()}

_PRESSURE_MODE_LABELS = {
    PressureCalculationMode.BACKWARD_REQUIRED_PUMP: "Backward required pump pressure",
    PressureCalculationMode.FORWARD_PUMP_CHECK: "Forward pressure check from given pump discharge pressure",
}
_PRESSURE_MODE_VALUES = {label: value for value, label in _PRESSURE_MODE_LABELS.items()}

_BARTZ_CURVATURE_MODE_LABELS = {
    BartzThroatCurvatureMode.UPSTREAM: "Upstream Rc,t",
    BartzThroatCurvatureMode.MEAN: "Mean Rc,t",
    BartzThroatCurvatureMode.DOWNSTREAM: "Downstream Rc,t",
}
_BARTZ_CURVATURE_MODE_VALUES = {
    label: value for value, label in _BARTZ_CURVATURE_MODE_LABELS.items()
}

_RADIATION_MODEL_LABELS = {
    RadiationModelType.GREY_GAS: "Grey gas",
    RadiationModelType.USER_FIXED_HEAT_FLUX: "User fixed heat flux",
    RadiationModelType.PARTICIPATING_MEDIA_EFFECTIVE_EMISSIVITY: "Participating-media effective emissivity",
}
_RADIATION_MODEL_VALUES = {label: value for value, label in _RADIATION_MODEL_LABELS.items()}

_RADIATION_TEMPERATURE_SOURCE_LABELS = {
    RadiationTemperatureSource.LOCAL_GAS_TEMPERATURE: "Local gas temperature",
    RadiationTemperatureSource.ADIABATIC_WALL_TEMPERATURE: "Adiabatic wall temperature",
    RadiationTemperatureSource.CHAMBER_TEMPERATURE: "Chamber temperature",
}
_RADIATION_TEMPERATURE_SOURCE_VALUES = {
    label: value for value, label in _RADIATION_TEMPERATURE_SOURCE_LABELS.items()
}

_PARTICIPATING_MEDIA_MODEL_LABELS = {
    ParticipatingMediaModelType.EFFECTIVE_EMISSIVITY: "Effective emissivity",
    ParticipatingMediaModelType.SIMPLE_CO2_H2O_PLACEHOLDER: "Simple CO2/H2O placeholder",
}
_PARTICIPATING_MEDIA_MODEL_VALUES = {
    label: value for value, label in _PARTICIPATING_MEDIA_MODEL_LABELS.items()
}

_PARTICIPATING_SPECIES_MODE_LABELS = {
    ParticipatingSpeciesMode.CO2_H2O_ONLY: "CO2 + H2O only",
    ParticipatingSpeciesMode.ALL_RADIATING_POLYATOMIC: "All radiating polyatomic species",
}
_PARTICIPATING_SPECIES_MODE_VALUES = {
    label: value for value, label in _PARTICIPATING_SPECIES_MODE_LABELS.items()
}

_OPTICAL_PATH_LENGTH_MODE_LABELS = {
    OpticalPathLengthMode.LOCAL_DIAMETER: "Local diameter",
    OpticalPathLengthMode.USER_FIXED: "User fixed",
    OpticalPathLengthMode.MEAN_BEAM_LENGTH_PLACEHOLDER: "Mean beam length (placeholder)",
}
_OPTICAL_PATH_LENGTH_MODE_VALUES = {
    label: value for value, label in _OPTICAL_PATH_LENGTH_MODE_LABELS.items()
}


@dataclass(frozen=True, slots=True)
class _ThermalPlotField:
    label: str
    quantity: str | None
    extractor: Callable[[ThermalStationResult], float | None]


@dataclass(frozen=True, slots=True)
class _ThermalPlotSeries:
    """One selected Y-series in display units, kept reusable for export and redraw."""

    key: str
    label: str
    values: list[float | None]


@dataclass(frozen=True, slots=True)
class _ThermalPlotPayload:
    """Current plot selection in display units.

    The window redraw and the export buttons both use the same payload so the
    user always exports exactly what is currently shown.
    """

    x_key: str
    x_label: str
    x_values: list[float | None]
    series: list[_ThermalPlotSeries]


_THERMAL_PLOT_FIELDS: dict[str, _ThermalPlotField] = {
    "station_index": _ThermalPlotField("Station index i", None, lambda station: float(station.station_index)),
    "x_start": _ThermalPlotField("x_start", "length", lambda station: station.x_start_m),
    "x_end": _ThermalPlotField("x_end", "length", lambda station: station.x_end_m),
    "x_mid": _ThermalPlotField("x", "length", lambda station: station.x_mid_m),
    "r_inner": _ThermalPlotField("r(x)", "length", lambda station: station.r_inner_m),
    "r_outer": _ThermalPlotField("r_outer", "length", lambda station: station.r_outer_m),
    "r_mean": _ThermalPlotField("r_mean", "length", lambda station: station.r_mean_m),
    "a_gas": _ThermalPlotField("A_gas", "area", lambda station: station.area_gas_m2),
    "a_hot": _ThermalPlotField("A_hot", "area", lambda station: station.area_hot_m2),
    "a_annulus": _ThermalPlotField("A_annulus", "area", lambda station: station.area_annulus_m2),
    "d_h": _ThermalPlotField("D_h", "length", lambda station: station.hydraulic_diameter_m),
    "t_recovery": _ThermalPlotField("T_recovery", "temperature", lambda station: station.recovery_temperature_k),
    "h_g": _ThermalPlotField("h_g", "heat_transfer_coefficient", lambda station: station.h_g_w_per_m2_k),
    "h_c": _ThermalPlotField("h_c", "heat_transfer_coefficient", lambda station: station.h_c_w_per_m2_k),
    "q_station": _ThermalPlotField("Q_station", None, lambda station: station.q_station_w),
    "q_hot": _ThermalPlotField("Heat flux q''", "heat_flux", lambda station: station.q_hot_w_per_m2),
    "q_conv": _ThermalPlotField("Convective heat flux q''_conv", "heat_flux", lambda station: station.q_conv_w_per_m2),
    "q_rad": _ThermalPlotField("Radiative heat flux q''_rad", "heat_flux", lambda station: station.q_rad_w_per_m2),
    "q_total": _ThermalPlotField("Total heat flux q''_total", "heat_flux", lambda station: station.q_total_w_per_m2),
    "t_c_in": _ThermalPlotField("T_c_in", "temperature", lambda station: station.coolant_temperature_in_k),
    "t_c_bulk": _ThermalPlotField("T_c_bulk", "temperature", lambda station: station.coolant_temperature_bulk_k),
    "t_c_out": _ThermalPlotField("T_c_out", "temperature", lambda station: station.coolant_temperature_out_k),
    "t_wg": _ThermalPlotField("T_wg", "temperature", lambda station: station.wall_temperature_hot_gas_side_k),
    "t_wc": _ThermalPlotField("T_wc", "temperature", lambda station: station.wall_temperature_coolant_side_k),
    "delta_t_wall": _ThermalPlotField("Delta_T_wall", "temperature", lambda station: station.wall_delta_t_k),
    "t_rad": _ThermalPlotField("T_rad", "temperature", lambda station: station.radiation_temperature_k),
    "p_required_in": _ThermalPlotField("p_required_in", "pressure", lambda station: station.required_pressure_in_pa),
    "p_required_out": _ThermalPlotField("p_required_out", "pressure", lambda station: station.required_pressure_out_pa),
    "delta_p_station": _ThermalPlotField("Delta_p_station", "pressure", lambda station: station.pressure_drop_station_pa),
    "re_coolant": _ThermalPlotField("Re_coolant", None, lambda station: station.reynolds_coolant),
    "coolant_cp": _ThermalPlotField("Coolant cp", "specific_heat", lambda station: station.coolant_cp_j_per_kg_k),
    "coolant_viscosity": _ThermalPlotField("Coolant viscosity µ", "viscosity", lambda station: station.coolant_viscosity_pa_s),
    "nu_coolant": _ThermalPlotField("Nu_coolant", None, lambda station: station.nusselt_coolant),
    "friction_factor": _ThermalPlotField("friction_factor", None, lambda station: station.friction_factor),
    "gas_emissivity": _ThermalPlotField("Gas effective emissivity", None, lambda station: station.gas_effective_emissivity),
    "radiation_fraction": _ThermalPlotField(
        "Radiation fraction",
        None,
        lambda station: (
            None
            if station.q_total_w_per_m2 in {None, 0.0} or station.q_rad_w_per_m2 is None
            else station.q_rad_w_per_m2 / station.q_total_w_per_m2
        ),
    ),
    "thermal_margin": _ThermalPlotField("thermal_margin", "temperature", lambda station: station.thermal_margin_k),
    "wall_mean_temperature": _ThermalPlotField(
        "Wall mean temperature",
        "temperature",
        lambda station: station.wall_mean_temperature_k,
    ),
    "pressure_delta": _ThermalPlotField(
        "Pressure delta",
        "pressure",
        lambda station: station.pressure_delta_pa,
    ),
    "hoop_stress": _ThermalPlotField("Hoop stress", "stress", lambda station: station.hoop_stress_pa),
    "longitudinal_stress": _ThermalPlotField(
        "Longitudinal stress",
        "stress",
        lambda station: station.longitudinal_stress_pa,
    ),
    "thermal_strain": _ThermalPlotField("Thermal strain", None, lambda station: station.thermal_strain),
    "thermal_stress": _ThermalPlotField(
        "Elastic thermal-stress indicator",
        "stress",
        lambda station: station.thermal_stress_pa,
    ),
    "von_mises_stress": _ThermalPlotField(
        "Von Mises stress",
        "stress",
        lambda station: station.equivalent_von_mises_stress_pa,
    ),
    "material_strength_margin": _ThermalPlotField(
        "Material screening margin (Rp0.2(T))",
        None,
        lambda station: station.material_strength_margin,
    ),
    "total_screening_strain": _ThermalPlotField(
        "Total screening strain",
        None,
        lambda station: station.total_screening_strain,
    ),
    "closeout_hoop_stress": _ThermalPlotField(
        "Closeout hoop stress",
        "stress",
        lambda station: station.closeout_hoop_stress_pa,
    ),
    "closeout_material_strength_margin": _ThermalPlotField(
        "Closeout material strength margin",
        None,
        lambda station: station.closeout_material_strength_margin,
    ),
}

_THERMAL_PLOT_X_KEYS = (
    "station_index",
    "x_start",
    "x_mid",
    "x_end",
    "r_inner",
    "r_outer",
    "r_mean",
)
_THERMAL_PLOT_DEFAULT_Y_KEYS = ("t_wg", "t_wc", "t_c_bulk")
_THERMAL_PLOT_Y_DISABLED_KEYS = {"station_index", "x_start", "x_mid", "x_end"}


class ExistingDesignContextCard(ttk.LabelFrame):
    """Compact read-only summary of the committed design used by Thermal Analysis."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset) -> None:
        super().__init__(master, text="Existing Design Context", padding=12)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(3, weight=1)
        self._unit_preset = unit_preset
        self._value_vars = {
            "design_status": tk.StringVar(value="not yet committed"),
            "pc": tk.StringVar(value="not yet computed"),
            "of": tk.StringVar(value="not yet set"),
            "mdot_total": tk.StringVar(value="not yet computed"),
            "mdot_coolant": tk.StringVar(value="not yet set"),
            "coolant_type": tk.StringVar(value="not yet set"),
            "wall_material": tk.StringVar(value="not yet set"),
            "wall_thickness": tk.StringVar(value="not yet set"),
            "geometry_source": tk.StringVar(value="Committed Current Design"),
            "contour_status": tk.StringVar(value="No committed contour available."),
        }
        fields = [
            ("design_status", "design status"),
            ("geometry_source", "geometry source"),
            ("pc", "pc"),
            ("of", "O/F"),
            ("mdot_total", "mdot_total"),
            ("mdot_coolant", "mdot_coolant"),
            ("coolant_type", "coolant type"),
            ("wall_material", "wall material"),
            ("wall_thickness", "wall thickness"),
        ]
        for index, (key, label) in enumerate(fields):
            row = index // 2
            column = (index % 2) * 2
            ttk.Label(self, text=label).grid(row=row, column=column, sticky="w", padx=(0, 8), pady=3)
            ttk.Label(self, textvariable=self._value_vars[key]).grid(row=row, column=column + 1, sticky="w", pady=3)

        ttk.Label(
            self,
            textvariable=self._value_vars["contour_status"],
            wraplength=980,
            justify="left",
        ).grid(row=5, column=0, columnspan=4, sticky="ew", pady=(10, 0))

        ttk.Label(
            self,
            text=(
                "This card shows the committed design data currently consumed by the annulus reference model. "
                "Coolant type follows the current reference setup, while coolant mass flow comes from the Thermal Analysis inputs."
            ),
            wraplength=980,
            justify="left",
        ).grid(row=6, column=0, columnspan=4, sticky="ew", pady=(10, 0))

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        self._unit_preset = unit_preset

    def update_context(
        self,
        *,
        current_inputs: InputParameters | None,
        current_bundle: ExportBundle | None,
        thermal_inputs: ThermalAnalysisInputs,
        design_status_label: str,
        geometry_source_label: str,
        contour_status_label: str,
    ) -> None:
        self._value_vars["design_status"].set(design_status_label)
        self._value_vars["pc"].set(
            format_quantity(
                current_inputs.chamber_pressure_pa if current_inputs is not None else None,
                "pressure",
                self._unit_preset,
                include_unit=True,
            )
        )
        self._value_vars["of"].set("--" if current_inputs is None else f"{current_inputs.mixture_ratio:.4f}")
        self._value_vars["mdot_total"].set(
            format_quantity(
                current_bundle.geometry.mass_flow_kg_per_s if current_bundle is not None else None,
                "mass_flow",
                self._unit_preset,
                include_unit=True,
            )
        )
        self._value_vars["mdot_coolant"].set(
            format_quantity(
                thermal_inputs.coolant_mass_flow_kg_per_s,
                "mass_flow",
                self._unit_preset,
                include_unit=True,
            )
        )
        self._value_vars["coolant_type"].set(thermal_inputs.coolant_type or "not yet set")
        self._value_vars["wall_material"].set(
            current_inputs.liner_material if current_inputs is not None else "not yet set"
        )
        self._value_vars["wall_thickness"].set(
            format_quantity(
                current_inputs.wall_thickness_m if current_inputs is not None else None,
                "length",
                self._unit_preset,
                include_unit=True,
            )
        )
        self._value_vars["geometry_source"].set(geometry_source_label)
        self._value_vars["contour_status"].set(contour_status_label)


class AnnulusCoolingCard(ttk.LabelFrame):
    """Editable thermal-model inputs for the MVP thermal page."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset) -> None:
        super().__init__(master, text="Thermal Model Setup", padding=12)
        self.columnconfigure(1, weight=1)
        self._unit_preset = unit_preset
        self._field_labels: dict[str, ttk.Label] = {}
        self._model_note_var = tk.StringVar(value="")
        self._variables = {
            "model_type": tk.StringVar(value=_MODEL_TYPE_LABELS[ThermalModelType.ANNULUS]),
            "coolant_mass_flow": tk.StringVar(value=""),
            "coolant_inlet_temperature": tk.StringVar(value=""),
            "annulus_gap": tk.StringVar(value=""),
            "roughness": tk.StringVar(value=""),
            "bartz_curvature_mode": tk.StringVar(
                value=_BARTZ_CURVATURE_MODE_LABELS[BartzThroatCurvatureMode.UPSTREAM]
            ),
            "pressure_mode": tk.StringVar(value=_PRESSURE_MODE_LABELS[PressureCalculationMode.BACKWARD_REQUIRED_PUMP]),
            "injector_pressure_drop": tk.StringVar(value=""),
            "pressure_margin": tk.StringVar(value=""),
            "external_feed_pressure_drop": tk.StringVar(value=""),
            "pump_discharge_pressure": tk.StringVar(value=""),
            "flow_direction": tk.StringVar(value=_FLOW_DIRECTION_LABELS[CoolingFlowDirection.NOZZLE_TO_INJECTOR]),
        }
        self._variables["model_type"].trace_add("write", self._handle_model_changed)
        self._variables["pressure_mode"].trace_add("write", self._handle_pressure_mode_changed)
        self._pump_pressure_entry: ttk.Entry | None = None
        self._build_widgets()

    def _build_widgets(self) -> None:
        ttk.Label(self, text="Thermal model").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Combobox(
            self,
            state="readonly",
            textvariable=self._variables["model_type"],
            values=list(_MODEL_TYPE_VALUES),
        ).grid(row=0, column=1, sticky="ew", pady=4)

        self._field_labels["coolant_mass_flow"] = ttk.Label(self)
        self._field_labels["coolant_mass_flow"].grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self, textvariable=self._variables["coolant_mass_flow"]).grid(row=1, column=1, sticky="ew", pady=4)

        self._field_labels["coolant_inlet_temperature"] = ttk.Label(self)
        self._field_labels["coolant_inlet_temperature"].grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self, textvariable=self._variables["coolant_inlet_temperature"]).grid(row=2, column=1, sticky="ew", pady=4)

        self._field_labels["annulus_gap"] = ttk.Label(self)
        self._field_labels["annulus_gap"].grid(row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self, textvariable=self._variables["annulus_gap"]).grid(row=3, column=1, sticky="ew", pady=4)

        self._field_labels["roughness"] = ttk.Label(self)
        self._field_labels["roughness"].grid(row=4, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self, textvariable=self._variables["roughness"]).grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(self, text="Bartz throat curvature Rc,t").grid(row=5, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Combobox(
            self,
            state="readonly",
            textvariable=self._variables["bartz_curvature_mode"],
            values=list(_BARTZ_CURVATURE_MODE_VALUES),
        ).grid(row=5, column=1, sticky="ew", pady=4)

        ttk.Label(self, text="Cooling flow direction").grid(row=6, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Combobox(
            self,
            state="readonly",
            textvariable=self._variables["flow_direction"],
            values=list(_FLOW_DIRECTION_VALUES),
        ).grid(row=6, column=1, sticky="ew", pady=4)

        ttk.Label(self, text="Pressure mode").grid(row=7, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Combobox(
            self,
            state="readonly",
            textvariable=self._variables["pressure_mode"],
            values=list(_PRESSURE_MODE_VALUES),
        ).grid(row=7, column=1, sticky="ew", pady=4)

        self._field_labels["injector_pressure_drop"] = ttk.Label(self)
        self._field_labels["injector_pressure_drop"].grid(row=8, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self, textvariable=self._variables["injector_pressure_drop"]).grid(row=8, column=1, sticky="ew", pady=4)

        self._field_labels["pressure_margin"] = ttk.Label(self)
        self._field_labels["pressure_margin"].grid(row=9, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self, textvariable=self._variables["pressure_margin"]).grid(row=9, column=1, sticky="ew", pady=4)

        self._field_labels["external_feed_pressure_drop"] = ttk.Label(self)
        self._field_labels["external_feed_pressure_drop"].grid(row=10, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self, textvariable=self._variables["external_feed_pressure_drop"]).grid(row=10, column=1, sticky="ew", pady=4)

        self._field_labels["pump_discharge_pressure"] = ttk.Label(self)
        self._field_labels["pump_discharge_pressure"].grid(row=11, column=0, sticky="w", padx=(0, 10), pady=4)
        self._pump_pressure_entry = ttk.Entry(self, textvariable=self._variables["pump_discharge_pressure"])
        self._pump_pressure_entry.grid(row=11, column=1, sticky="ew", pady=4)

        ttk.Label(self, text="Fixed mechanical assumption").grid(row=12, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Label(self, text="3 spacer ribs").grid(row=12, column=1, sticky="w", pady=4)

        ttk.Label(
            self,
            textvariable=self._model_note_var,
            wraplength=460,
            justify="left",
            foreground="#667381",
        ).grid(row=13, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        ttk.Label(
            self,
            text=(
                "Spacer ribs are shown as a mechanical support assumption only and are not included in the MVP annulus "
                "thermal-hydraulic calculation."
            ),
            wraplength=460,
            justify="left",
            foreground="#7d4d1b",
        ).grid(row=14, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self._apply_unit_labels()
        self._refresh_model_note()
        self._refresh_pressure_mode()

    def _apply_unit_labels(self) -> None:
        self._field_labels["coolant_mass_flow"].configure(
            text=f"Coolant mass flow [{get_unit_symbol('mass_flow', self._unit_preset)}]"
        )
        self._field_labels["coolant_inlet_temperature"].configure(
            text=f"Coolant inlet temperature [{get_unit_symbol('temperature', self._unit_preset)}]"
        )
        self._field_labels["annulus_gap"].configure(
            text=f"Annulus gap height g_annulus [{get_unit_symbol('length', self._unit_preset)}]"
        )
        self._field_labels["roughness"].configure(
            text=f"Coolant roughness epsilon_roughness [{get_unit_symbol('length', self._unit_preset)}]"
        )
        self._field_labels["injector_pressure_drop"].configure(
            text=f"Injector pressure drop Delta_p_injector [{get_unit_symbol('pressure', self._unit_preset)}]"
        )
        self._field_labels["pressure_margin"].configure(
            text=f"Pressure margin Delta_p_margin [{get_unit_symbol('pressure', self._unit_preset)}]"
        )
        self._field_labels["external_feed_pressure_drop"].configure(
            text=f"External feed pressure drop Delta_p_feed_external [{get_unit_symbol('pressure', self._unit_preset)}]"
        )
        self._field_labels["pump_discharge_pressure"].configure(
            text=f"Pump discharge pressure [{get_unit_symbol('pressure', self._unit_preset)}]"
        )

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        self._unit_preset = unit_preset
        self._apply_unit_labels()

    def set_inputs(self, inputs: ThermalAnalysisInputs) -> None:
        self._variables["model_type"].set(_MODEL_TYPE_LABELS[inputs.model_type])
        self._variables["coolant_mass_flow"].set(
            "" if inputs.coolant_mass_flow_kg_per_s is None else format_quantity(inputs.coolant_mass_flow_kg_per_s, "mass_flow", self._unit_preset)
        )
        self._variables["coolant_inlet_temperature"].set(
            format_quantity(inputs.coolant_inlet_temperature_k, "temperature", self._unit_preset)
        )
        self._variables["annulus_gap"].set(format_quantity(inputs.annulus_gap_m, "length", self._unit_preset))
        self._variables["roughness"].set(format_quantity(inputs.coolant_roughness_m, "length", self._unit_preset))
        self._variables["bartz_curvature_mode"].set(
            _BARTZ_CURVATURE_MODE_LABELS[inputs.bartz_throat_curvature_mode]
        )
        self._variables["pressure_mode"].set(_PRESSURE_MODE_LABELS[inputs.solver_settings.pressure_mode])
        self._variables["injector_pressure_drop"].set(
            format_quantity(inputs.injector_pressure_drop_pa, "pressure", self._unit_preset)
        )
        self._variables["pressure_margin"].set(
            format_quantity(inputs.pressure_margin_pa, "pressure", self._unit_preset)
        )
        self._variables["external_feed_pressure_drop"].set(
            format_quantity(inputs.external_feed_pressure_drop_pa, "pressure", self._unit_preset)
        )
        self._variables["pump_discharge_pressure"].set(
            "" if inputs.pump_discharge_pressure_pa is None else format_quantity(inputs.pump_discharge_pressure_pa, "pressure", self._unit_preset)
        )
        self._variables["flow_direction"].set(_FLOW_DIRECTION_LABELS[inputs.flow_direction])
        self._refresh_model_note()
        self._refresh_pressure_mode()

    def get_partial_inputs(self) -> dict[str, object]:
        errors: list[str] = []
        model_type = _MODEL_TYPE_VALUES.get(self._variables["model_type"].get())
        coolant_mass_flow = _parse_optional_float(self._variables["coolant_mass_flow"].get(), "Coolant mass flow", errors)
        coolant_inlet_temperature = _parse_required_float(
            self._variables["coolant_inlet_temperature"].get(),
            "Coolant inlet temperature",
            errors,
        )
        annulus_gap = _parse_required_float(self._variables["annulus_gap"].get(), "Annulus gap height", errors)
        roughness = _parse_required_float(self._variables["roughness"].get(), "Coolant roughness", errors)
        bartz_curvature_mode = _BARTZ_CURVATURE_MODE_VALUES.get(self._variables["bartz_curvature_mode"].get())
        pressure_mode = _PRESSURE_MODE_VALUES.get(self._variables["pressure_mode"].get())
        injector_pressure_drop = _parse_required_float(
            self._variables["injector_pressure_drop"].get(),
            "Injector pressure drop",
            errors,
        )
        pressure_margin = _parse_required_float(
            self._variables["pressure_margin"].get(),
            "Pressure margin",
            errors,
        )
        external_feed_pressure_drop = _parse_required_float(
            self._variables["external_feed_pressure_drop"].get(),
            "External feed pressure drop",
            errors,
        )
        pump_discharge_pressure = _parse_optional_float(
            self._variables["pump_discharge_pressure"].get(),
            "Pump discharge pressure",
            errors,
        )
        flow_direction = _FLOW_DIRECTION_VALUES.get(self._variables["flow_direction"].get())
        if model_type is None:
            errors.append("Thermal model is invalid.")
            model_type = ThermalModelType.ANNULUS
        if pressure_mode is None:
            errors.append("Pressure mode is invalid.")
            pressure_mode = PressureCalculationMode.BACKWARD_REQUIRED_PUMP
        if bartz_curvature_mode is None:
            errors.append("Bartz throat curvature selection is invalid.")
            bartz_curvature_mode = BartzThroatCurvatureMode.UPSTREAM
        if flow_direction is None:
            errors.append("Cooling flow direction is invalid.")
            flow_direction = CoolingFlowDirection.NOZZLE_TO_INJECTOR
        if errors:
            raise InputValidationError(errors)
        return {
            "model_type": model_type,
            "coolant_mass_flow_kg_per_s": _convert_lengthless_quantity(coolant_mass_flow, "mass_flow", self._unit_preset),
            "coolant_inlet_temperature_k": _convert_lengthless_quantity(
                coolant_inlet_temperature,
                "temperature",
                self._unit_preset,
            ),
            "annulus_gap_m": _convert_lengthless_quantity(annulus_gap, "length", self._unit_preset),
            "coolant_roughness_m": _convert_lengthless_quantity(roughness, "length", self._unit_preset),
            "bartz_throat_curvature_mode": bartz_curvature_mode,
            "pressure_mode": pressure_mode,
            "injector_pressure_drop_pa": _convert_lengthless_quantity(
                injector_pressure_drop,
                "pressure",
                self._unit_preset,
            ),
            "pressure_margin_pa": _convert_lengthless_quantity(
                pressure_margin,
                "pressure",
                self._unit_preset,
            ),
            "external_feed_pressure_drop_pa": _convert_lengthless_quantity(
                external_feed_pressure_drop,
                "pressure",
                self._unit_preset,
            ),
            "pump_discharge_pressure_pa": _convert_lengthless_quantity(
                pump_discharge_pressure,
                "pressure",
                self._unit_preset,
            ),
            "flow_direction": flow_direction,
        }

    def _handle_model_changed(self, *_args: object) -> None:
        self._refresh_model_note()

    def _refresh_model_note(self) -> None:
        model_type = _MODEL_TYPE_VALUES.get(self._variables["model_type"].get(), ThermalModelType.ANNULUS)
        if model_type is ThermalModelType.ANNULUS:
            self._model_note_var.set(
                "Annulus cooling is the active MVP reference model. It uses the current inner contour r(x), a uniform annulus gap and a separate post-processed pressure reconstruction. The gas-side heat transfer now uses a steady-state Bartz-style correlation based on the existing CEA/profile properties and the selected throat-curvature reference. The coolant-side correlations assume fully developed annular flow everywhere. That is conservative for wall heat transfer because real inlet regions often have stronger eddies and therefore higher local h-values than this baseline."
            )
            return
        self._model_note_var.set(
            "This option is shown so later channel and film-cooling models already have a clear place in the workflow. The current MVP still calculates annulus cooling only."
        )

    def _handle_pressure_mode_changed(self, *_args: object) -> None:
        self._refresh_pressure_mode()

    def _refresh_pressure_mode(self) -> None:
        pressure_mode = _PRESSURE_MODE_VALUES.get(
            self._variables["pressure_mode"].get(),
            PressureCalculationMode.BACKWARD_REQUIRED_PUMP,
        )
        if self._pump_pressure_entry is not None:
            self._pump_pressure_entry.configure(
                state="normal" if pressure_mode is PressureCalculationMode.FORWARD_PUMP_CHECK else "disabled"
            )


class RadiationCard(ttk.LabelFrame):
    """Optional advanced radiation settings for the Thermal Analysis MVP."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset) -> None:
        super().__init__(master, text="Radiation", padding=12)
        self._unit_preset = unit_preset
        self._expanded = False
        self.columnconfigure(0, weight=1)
        self._field_labels: dict[str, ttk.Label] = {}
        self._variables = {
            "enabled": tk.BooleanVar(value=False),
            "model": tk.StringVar(value=_RADIATION_MODEL_LABELS[RadiationModelType.GREY_GAS]),
            "wall_emissivity": tk.StringVar(value="0.8"),
            "gas_effective_emissivity": tk.StringVar(value="0.15"),
            "temperature_source": tk.StringVar(
                value=_RADIATION_TEMPERATURE_SOURCE_LABELS[RadiationTemperatureSource.LOCAL_GAS_TEMPERATURE]
            ),
            "participating_media_enabled": tk.BooleanVar(value=False),
            "participating_media_model": tk.StringVar(
                value=_PARTICIPATING_MEDIA_MODEL_LABELS[ParticipatingMediaModelType.EFFECTIVE_EMISSIVITY]
            ),
            "participating_species_mode": tk.StringVar(
                value=_PARTICIPATING_SPECIES_MODE_LABELS[ParticipatingSpeciesMode.CO2_H2O_ONLY]
            ),
            "optical_path_length_mode": tk.StringVar(
                value=_OPTICAL_PATH_LENGTH_MODE_LABELS[OpticalPathLengthMode.LOCAL_DIAMETER]
            ),
            "user_optical_path_length": tk.StringVar(value=""),
            "co2_mole_fraction": tk.StringVar(value=""),
            "h2o_mole_fraction": tk.StringVar(value=""),
            "soot_factor": tk.StringVar(value="0.0"),
            "fixed_heat_flux": tk.StringVar(value=""),
        }
        self._details_frame = ttk.Frame(self)
        self._details_frame.columnconfigure(1, weight=1)
        self._interactive_widgets: list[tk.Widget] = []
        self._participating_widgets: list[tk.Widget] = []
        self._fixed_flux_widgets: list[tk.Widget] = []
        self._user_optical_widgets: list[tk.Widget] = []
        self._variables["enabled"].trace_add("write", self._handle_state_changed)
        self._variables["participating_media_enabled"].trace_add("write", self._handle_state_changed)
        self._variables["model"].trace_add("write", self._handle_state_changed)
        self._variables["optical_path_length_mode"].trace_add("write", self._handle_state_changed)
        self._build_widgets()

    def _build_widgets(self) -> None:
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            header,
            text="Enable radiation heat transfer",
            variable=self._variables["enabled"],
        ).grid(row=0, column=0, sticky="w")
        self._toggle_button = ttk.Button(header, text="Show radiation settings", command=self._toggle_details)
        self._toggle_button.grid(row=0, column=2, sticky="e")

        ttk.Label(
            self,
            text=(
                "Optional advanced screening feature. Radiation is OFF by default so the standard annulus result stays "
                "identical to the convection-only baseline unless you explicitly enable it."
            ),
            wraplength=980,
            justify="left",
            foreground="#667381",
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))

        details = self._details_frame
        details.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        ttk.Label(details, text="Radiation model").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        model_combo = ttk.Combobox(
            details,
            state="readonly",
            textvariable=self._variables["model"],
            values=list(_RADIATION_MODEL_VALUES),
        )
        model_combo.grid(row=0, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(model_combo)

        self._field_labels["wall_emissivity"] = ttk.Label(details)
        self._field_labels["wall_emissivity"].grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        wall_entry = ttk.Entry(details, textvariable=self._variables["wall_emissivity"])
        wall_entry.grid(row=1, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(wall_entry)

        self._field_labels["gas_effective_emissivity"] = ttk.Label(details)
        self._field_labels["gas_effective_emissivity"].grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        gas_entry = ttk.Entry(details, textvariable=self._variables["gas_effective_emissivity"])
        gas_entry.grid(row=2, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(gas_entry)

        ttk.Label(details, text="Radiation temperature source").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        temp_combo = ttk.Combobox(
            details,
            state="readonly",
            textvariable=self._variables["temperature_source"],
            values=list(_RADIATION_TEMPERATURE_SOURCE_VALUES),
        )
        temp_combo.grid(row=3, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(temp_combo)

        participating_toggle = ttk.Checkbutton(
            details,
            text="Participating media",
            variable=self._variables["participating_media_enabled"],
        )
        participating_toggle.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 4))
        self._interactive_widgets.append(participating_toggle)

        ttk.Label(details, text="Participating media model").grid(row=5, column=0, sticky="w", padx=(0, 10), pady=4)
        participating_combo = ttk.Combobox(
            details,
            state="readonly",
            textvariable=self._variables["participating_media_model"],
            values=list(_PARTICIPATING_MEDIA_MODEL_VALUES),
        )
        participating_combo.grid(row=5, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(participating_combo)
        self._participating_widgets.append(participating_combo)

        ttk.Label(details, text="Participating species mode").grid(row=6, column=0, sticky="w", padx=(0, 10), pady=4)
        species_mode_combo = ttk.Combobox(
            details,
            state="readonly",
            textvariable=self._variables["participating_species_mode"],
            values=list(_PARTICIPATING_SPECIES_MODE_VALUES),
        )
        species_mode_combo.grid(row=6, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(species_mode_combo)
        self._participating_widgets.append(species_mode_combo)

        ttk.Label(details, text="Optical path length mode").grid(row=7, column=0, sticky="w", padx=(0, 10), pady=4)
        optical_combo = ttk.Combobox(
            details,
            state="readonly",
            textvariable=self._variables["optical_path_length_mode"],
            values=list(_OPTICAL_PATH_LENGTH_MODE_VALUES),
        )
        optical_combo.grid(row=7, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(optical_combo)
        self._participating_widgets.append(optical_combo)

        self._field_labels["user_optical_path_length"] = ttk.Label(details)
        self._field_labels["user_optical_path_length"].grid(row=8, column=0, sticky="w", padx=(0, 10), pady=4)
        user_optical_entry = ttk.Entry(details, textvariable=self._variables["user_optical_path_length"])
        user_optical_entry.grid(row=8, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(user_optical_entry)
        self._participating_widgets.append(user_optical_entry)
        self._user_optical_widgets.append(user_optical_entry)

        self._field_labels["co2_mole_fraction"] = ttk.Label(details)
        self._field_labels["co2_mole_fraction"].grid(row=9, column=0, sticky="w", padx=(0, 10), pady=4)
        co2_entry = ttk.Entry(details, textvariable=self._variables["co2_mole_fraction"])
        co2_entry.grid(row=9, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(co2_entry)
        self._participating_widgets.append(co2_entry)

        self._field_labels["h2o_mole_fraction"] = ttk.Label(details)
        self._field_labels["h2o_mole_fraction"].grid(row=10, column=0, sticky="w", padx=(0, 10), pady=4)
        h2o_entry = ttk.Entry(details, textvariable=self._variables["h2o_mole_fraction"])
        h2o_entry.grid(row=10, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(h2o_entry)
        self._participating_widgets.append(h2o_entry)

        self._field_labels["soot_factor"] = ttk.Label(details)
        self._field_labels["soot_factor"].grid(row=11, column=0, sticky="w", padx=(0, 10), pady=4)
        soot_entry = ttk.Entry(details, textvariable=self._variables["soot_factor"])
        soot_entry.grid(row=11, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(soot_entry)
        self._participating_widgets.append(soot_entry)

        self._field_labels["fixed_heat_flux"] = ttk.Label(details)
        self._field_labels["fixed_heat_flux"].grid(row=12, column=0, sticky="w", padx=(0, 10), pady=4)
        fixed_heat_flux_entry = ttk.Entry(details, textvariable=self._variables["fixed_heat_flux"])
        fixed_heat_flux_entry.grid(row=12, column=1, sticky="ew", pady=4)
        self._interactive_widgets.append(fixed_heat_flux_entry)
        self._fixed_flux_widgets.append(fixed_heat_flux_entry)

        ttk.Label(
            details,
            text=(
                "This is a screening-level model only. It adds a separate radiative heat-flux term on top of Bartz "
                "convection and prefers local CEA station mole fractions when participating media is enabled. It does not represent a spectral radiation solution."
            ),
            wraplength=960,
            justify="left",
            foreground="#7d4d1b",
        ).grid(row=13, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self._apply_unit_labels()
        self._details_frame.grid_remove()
        self._refresh_widget_states()

    def _toggle_details(self) -> None:
        self._expanded = not self._expanded
        if self._expanded:
            self._details_frame.grid()
            self._toggle_button.configure(text="Hide radiation settings")
        else:
            self._details_frame.grid_remove()
            self._toggle_button.configure(text="Show radiation settings")

    def _handle_state_changed(self, *_args: object) -> None:
        self._refresh_widget_states()

    def _refresh_widget_states(self) -> None:
        enabled = self._variables["enabled"].get()
        use_participating = enabled and (
            self._variables["participating_media_enabled"].get()
            or _RADIATION_MODEL_VALUES.get(self._variables["model"].get())
            is RadiationModelType.PARTICIPATING_MEDIA_EFFECTIVE_EMISSIVITY
        )
        use_fixed_heat_flux = enabled and (
            _RADIATION_MODEL_VALUES.get(self._variables["model"].get())
            is RadiationModelType.USER_FIXED_HEAT_FLUX
        )
        user_optical = use_participating and (
            _OPTICAL_PATH_LENGTH_MODE_VALUES.get(self._variables["optical_path_length_mode"].get())
            is OpticalPathLengthMode.USER_FIXED
        )

        for widget in self._interactive_widgets:
            self._set_widget_state(widget, enabled)
        for widget in self._participating_widgets:
            self._set_widget_state(widget, use_participating)
        for widget in self._fixed_flux_widgets:
            self._set_widget_state(widget, use_fixed_heat_flux)
        for widget in self._user_optical_widgets:
            self._set_widget_state(widget, user_optical)

    @staticmethod
    def _set_widget_state(widget: tk.Widget, enabled: bool) -> None:
        if isinstance(widget, ttk.Combobox):
            widget.configure(state="readonly" if enabled else "disabled")
            return
        widget.configure(state="normal" if enabled else "disabled")

    def _apply_unit_labels(self) -> None:
        self._field_labels["wall_emissivity"].configure(text="Wall emissivity [-]")
        self._field_labels["gas_effective_emissivity"].configure(text="Gas effective emissivity fallback [-]")
        self._field_labels["user_optical_path_length"].configure(
            text=f"User optical path length [{get_unit_symbol('length', self._unit_preset)}]"
        )
        self._field_labels["co2_mole_fraction"].configure(text="Fallback CO2 mole fraction [-]")
        self._field_labels["h2o_mole_fraction"].configure(text="Fallback H2O mole fraction [-]")
        self._field_labels["soot_factor"].configure(text="Soot factor [-]")
        self._field_labels["fixed_heat_flux"].configure(
            text=f"Fixed radiation heat flux [{get_unit_symbol('heat_flux', self._unit_preset)}]"
        )

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        self._unit_preset = unit_preset
        self._apply_unit_labels()

    def set_inputs(self, inputs: ThermalAnalysisInputs) -> None:
        settings = inputs.radiation_settings
        self._variables["enabled"].set(settings.enabled)
        self._variables["model"].set(_RADIATION_MODEL_LABELS[settings.model])
        self._variables["wall_emissivity"].set(f"{settings.wall_emissivity:.4g}")
        self._variables["gas_effective_emissivity"].set(f"{settings.gas_effective_emissivity:.4g}")
        self._variables["temperature_source"].set(
            _RADIATION_TEMPERATURE_SOURCE_LABELS[settings.radiation_temperature_source]
        )
        self._variables["participating_media_enabled"].set(settings.participating_media_enabled)
        self._variables["participating_media_model"].set(
            _PARTICIPATING_MEDIA_MODEL_LABELS[settings.participating_media_model]
        )
        self._variables["participating_species_mode"].set(
            _PARTICIPATING_SPECIES_MODE_LABELS[settings.participating_species_mode]
        )
        self._variables["optical_path_length_mode"].set(
            _OPTICAL_PATH_LENGTH_MODE_LABELS[settings.optical_path_length_mode]
        )
        self._variables["user_optical_path_length"].set(
            "" if settings.user_optical_path_length_m is None else format_quantity(settings.user_optical_path_length_m, "length", self._unit_preset)
        )
        self._variables["co2_mole_fraction"].set(
            "" if settings.co2_mole_fraction is None else f"{settings.co2_mole_fraction:.4g}"
        )
        self._variables["h2o_mole_fraction"].set(
            "" if settings.h2o_mole_fraction is None else f"{settings.h2o_mole_fraction:.4g}"
        )
        self._variables["soot_factor"].set(f"{settings.soot_factor:.4g}")
        self._variables["fixed_heat_flux"].set(
            "" if settings.fixed_radiation_heat_flux_w_per_m2 is None else format_quantity(settings.fixed_radiation_heat_flux_w_per_m2, "heat_flux", self._unit_preset)
        )
        if settings.enabled and not self._expanded:
            self._toggle_details()
        self._refresh_widget_states()

    def get_settings(self) -> RadiationSettings:
        errors: list[str] = []
        enabled = self._variables["enabled"].get()
        model = _RADIATION_MODEL_VALUES.get(self._variables["model"].get())
        temperature_source = _RADIATION_TEMPERATURE_SOURCE_VALUES.get(self._variables["temperature_source"].get())
        participating_media_model = _PARTICIPATING_MEDIA_MODEL_VALUES.get(
            self._variables["participating_media_model"].get()
        )
        participating_species_mode = _PARTICIPATING_SPECIES_MODE_VALUES.get(
            self._variables["participating_species_mode"].get()
        )
        optical_path_length_mode = _OPTICAL_PATH_LENGTH_MODE_VALUES.get(
            self._variables["optical_path_length_mode"].get()
        )
        wall_emissivity = _parse_required_float(self._variables["wall_emissivity"].get(), "Wall emissivity", errors)
        gas_effective_emissivity = _parse_required_float(
            self._variables["gas_effective_emissivity"].get(),
            "Gas effective emissivity",
            errors,
        )
        soot_factor = _parse_required_float(self._variables["soot_factor"].get(), "Soot factor", errors)
        user_optical_path_length = _parse_optional_float(
            self._variables["user_optical_path_length"].get(),
            "User optical path length",
            errors,
        )
        fixed_heat_flux = _parse_optional_float(
            self._variables["fixed_heat_flux"].get(),
            "Fixed radiation heat flux",
            errors,
        )
        co2_mole_fraction = _parse_optional_float(self._variables["co2_mole_fraction"].get(), "CO2 mole fraction", errors)
        h2o_mole_fraction = _parse_optional_float(self._variables["h2o_mole_fraction"].get(), "H2O mole fraction", errors)
        if model is None:
            errors.append("Radiation model is invalid.")
            model = RadiationModelType.GREY_GAS
        if temperature_source is None:
            errors.append("Radiation temperature source is invalid.")
            temperature_source = RadiationTemperatureSource.LOCAL_GAS_TEMPERATURE
        if participating_media_model is None:
            errors.append("Participating media model is invalid.")
            participating_media_model = ParticipatingMediaModelType.EFFECTIVE_EMISSIVITY
        if participating_species_mode is None:
            errors.append("Participating species mode is invalid.")
            participating_species_mode = ParticipatingSpeciesMode.CO2_H2O_ONLY
        if optical_path_length_mode is None:
            errors.append("Optical path length mode is invalid.")
            optical_path_length_mode = OpticalPathLengthMode.LOCAL_DIAMETER
        if errors:
            raise InputValidationError(errors)
        return RadiationSettings(
            enabled=enabled,
            model=model,
            wall_emissivity=wall_emissivity,
            gas_effective_emissivity=gas_effective_emissivity,
            radiation_temperature_source=temperature_source,
            participating_media_enabled=self._variables["participating_media_enabled"].get(),
            participating_media_model=participating_media_model,
            participating_species_mode=participating_species_mode,
            co2_mole_fraction=co2_mole_fraction,
            h2o_mole_fraction=h2o_mole_fraction,
            optical_path_length_mode=optical_path_length_mode,
            user_optical_path_length_m=_convert_lengthless_quantity(
                user_optical_path_length,
                "length",
                self._unit_preset,
            ),
            soot_factor=soot_factor,
            fixed_radiation_heat_flux_w_per_m2=_convert_lengthless_quantity(
                fixed_heat_flux,
                "heat_flux",
                self._unit_preset,
            ),
        )


class SolverSettingsCard(ttk.LabelFrame):
    """Editable station-solver settings for the MVP annulus model."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Solver Settings", padding=12)
        self.columnconfigure(1, weight=1)
        self._variables = {
            "solver_type": tk.StringVar(value=_SOLVER_TYPE_LABELS[ThermalSolverType.NTU_EXPONENTIAL]),
            "station_distribution_mode": tk.StringVar(value=_STATION_MODE_LABELS[StationDistributionMode.MANUAL]),
            "station_count": tk.StringVar(value="32"),
            "station_tolerance": tk.StringVar(value="0.1"),
            "max_iterations": tk.StringVar(value="25"),
            "relaxation_factor": tk.StringVar(value="0.6"),
        }
        self._station_mode_note_var = tk.StringVar(value="")
        self._station_count_entry: ttk.Entry | None = None
        self._variables["station_distribution_mode"].trace_add("write", self._handle_station_mode_changed)
        self._build_widgets()

    def _build_widgets(self) -> None:
        ttk.Label(self, text="Solver type").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Combobox(
            self,
            state="readonly",
            textvariable=self._variables["solver_type"],
            values=list(_SOLVER_TYPE_VALUES),
        ).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(self, text="Station distribution").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Combobox(
            self,
            state="readonly",
            textvariable=self._variables["station_distribution_mode"],
            values=list(_STATION_MODE_VALUES),
        ).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(self, text="Number of stations N").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        self._station_count_entry = ttk.Entry(self, textvariable=self._variables["station_count"])
        self._station_count_entry.grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(
            self,
            textvariable=self._station_mode_note_var,
            wraplength=420,
            justify="left",
            foreground="#667381",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 4))

        ttk.Label(self, text="Station tolerance").grid(row=4, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self, textvariable=self._variables["station_tolerance"]).grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(self, text="Maximum iterations per station").grid(row=5, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self, textvariable=self._variables["max_iterations"]).grid(row=5, column=1, sticky="ew", pady=4)

        ttk.Label(self, text="Relaxation factor").grid(row=6, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self, textvariable=self._variables["relaxation_factor"]).grid(row=6, column=1, sticky="ew", pady=4)
        self._refresh_station_mode()

    def set_inputs(self, settings: SolverSettings) -> None:
        self._variables["solver_type"].set(_SOLVER_TYPE_LABELS[settings.solver_type])
        self._variables["station_distribution_mode"].set(_STATION_MODE_LABELS[settings.station_distribution_mode])
        self._variables["station_count"].set(str(settings.station_count))
        self._variables["station_tolerance"].set(f"{settings.station_tolerance:.5g}")
        self._variables["max_iterations"].set(str(settings.max_iterations_per_station))
        self._variables["relaxation_factor"].set(f"{settings.relaxation_factor:.3f}")
        self._refresh_station_mode()

    def get_settings(self) -> SolverSettings:
        errors: list[str] = []
        solver_type = _SOLVER_TYPE_VALUES.get(self._variables["solver_type"].get())
        station_distribution_mode = _STATION_MODE_VALUES.get(self._variables["station_distribution_mode"].get())
        if solver_type is None:
            errors.append("Solver type is invalid.")
            solver_type = ThermalSolverType.NTU_EXPONENTIAL
        if station_distribution_mode is None:
            errors.append("Station distribution is invalid.")
            station_distribution_mode = StationDistributionMode.MANUAL
        if station_distribution_mode is StationDistributionMode.MANUAL:
            station_count = _parse_required_int(self._variables["station_count"].get(), "Number of stations", errors)
        else:
            station_count = max(_parse_fallback_int(self._variables["station_count"].get(), default=32), 2)
        station_tolerance = _parse_required_float(self._variables["station_tolerance"].get(), "Station tolerance", errors)
        max_iterations = _parse_required_int(self._variables["max_iterations"].get(), "Maximum iterations per station", errors)
        relaxation_factor = _parse_required_float(self._variables["relaxation_factor"].get(), "Relaxation factor", errors)
        if errors:
            raise InputValidationError(errors)
        return SolverSettings(
            solver_type=solver_type,
            station_distribution_mode=station_distribution_mode,
            station_count=station_count,
            station_tolerance=station_tolerance,
            max_iterations_per_station=max_iterations,
            relaxation_factor=relaxation_factor,
        )

    def set_profile_station_count(self, station_count: int | None) -> None:
        if _STATION_MODE_VALUES.get(self._variables["station_distribution_mode"].get()) is StationDistributionMode.CEA_PROFILE:
            if station_count is None:
                self._station_mode_note_var.set(
                    "Uses the currently available CEA/profile stations. Calculate Current Design first if this count is not ready yet."
                )
            else:
                self._station_mode_note_var.set(
                    f"Uses {station_count} stations from the current CEA/profile sampling."
                )
        else:
            self._station_mode_note_var.set(
                "Manual mode redistributes the current geometry into the requested station count."
            )

    def _handle_station_mode_changed(self, *_args: object) -> None:
        self._refresh_station_mode()

    def _refresh_station_mode(self) -> None:
        mode = _STATION_MODE_VALUES.get(self._variables["station_distribution_mode"].get(), StationDistributionMode.MANUAL)
        if self._station_count_entry is not None:
            self._station_count_entry.configure(state="normal" if mode is StationDistributionMode.MANUAL else "disabled")
        if mode is StationDistributionMode.MANUAL:
            self._station_mode_note_var.set(
                "Manual mode redistributes the current geometry into the requested station count."
            )
        else:
            self._station_mode_note_var.set(
                "Uses the currently available CEA/profile stations. Calculate Current Design first if this count is not ready yet."
            )


class FutureChannelDefinitionPanel(ttk.LabelFrame):
    """Disabled placeholder for later detailed channel-cooling work."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Channel Definition - planned", padding=12)
        self.columnconfigure(1, weight=1)
        entries = [
            ("Channel type", "rectangular / trapezoidal / triangular / custom"),
            ("Number of channels", ""),
            ("Channel width", ""),
            ("Channel height", ""),
            ("Rib thickness", ""),
            ("Helix angle", ""),
            ("Variable twist", ""),
            ("Dimples / turbulators", ""),
            ("AM roughness model", ""),
        ]
        for row, (label, value) in enumerate(entries):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            widget = ttk.Entry(self)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            widget.insert(0, value)
            widget.configure(state="disabled")
        ttk.Label(
            self,
            text=(
                "Detailed channel cooling is planned for a later version. MVP uses annulus cooling as a reference model."
            ),
            wraplength=980,
            justify="left",
            foreground="#667381",
        ).grid(row=len(entries), column=0, columnspan=2, sticky="ew", pady=(8, 0))


class ThermalActionRow(ttk.LabelFrame):
    """Button row for thermal-analysis actions."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Actions", padding=12)
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=0)
        self.columnconfigure(2, weight=0)
        self.columnconfigure(3, weight=1)
        self._calculate_button = ttk.Button(self, text="Calculate Thermal Analysis")
        self._calculate_button.grid(row=0, column=0, sticky="w")
        self._reset_button = ttk.Button(self, text="Reset Thermal Inputs")
        self._reset_button.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self._plot_button = ttk.Button(self, text="Open Plot Window")
        self._plot_button.grid(row=0, column=2, sticky="w", padx=(10, 0))
        ttk.Label(
            self,
            text="Runs a station-wise annulus thermal-hydraulic reference calculation.",
            wraplength=760,
            justify="left",
        ).grid(row=0, column=3, sticky="w", padx=(16, 0))

    def bind_calculate(self, callback: Callable[[], None]) -> None:
        self._calculate_button.configure(command=callback)

    def bind_reset(self, callback: Callable[[], None]) -> None:
        self._reset_button.configure(command=callback)

    def bind_open_plot(self, callback: Callable[[], None]) -> None:
        self._plot_button.configure(command=callback)


class ThermalSummaryTiles(ttk.LabelFrame):
    """Compact summary tiles for the current thermal-analysis result."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset) -> None:
        super().__init__(master, text="Summary Results", padding=12)
        self._unit_preset = unit_preset
        self._tile_vars = {
            "twg": tk.StringVar(value="not available"),
            "twc": tk.StringVar(value="not available"),
            "tc_out": tk.StringVar(value="not available"),
            "q_total": tk.StringVar(value="not available"),
            "dp_total": tk.StringVar(value="not available"),
            "p_cooling_in": tk.StringVar(value="not available"),
            "p_pump_out": tk.StringVar(value="not available"),
            "dp_injector": tk.StringVar(value="not available"),
            "dp_external": tk.StringVar(value="not available"),
            "dp_margin": tk.StringVar(value="not available"),
            "margin": tk.StringVar(value="not available"),
            "delta_h": tk.StringVar(value="not available"),
            "isp_gain": tk.StringVar(value="preliminary placeholder"),
        }
        definitions = [
            ("Max hot-gas-side wall temperature T_wg,max", "twg"),
            ("Max coolant-side wall temperature T_wc,max", "twc"),
            ("Coolant outlet temperature T_c,out", "tc_out"),
            ("Total heat picked up by coolant Q_total", "q_total"),
            ("Required cooling inlet pressure", "p_cooling_in"),
            ("Required pump discharge pressure", "p_pump_out"),
            ("Total coolant pressure drop Delta_p_total", "dp_total"),
            ("Injector pressure drop", "dp_injector"),
            ("External feed pressure drop", "dp_external"),
            ("Pressure margin", "dp_margin"),
            ("Minimum thermal margin", "margin"),
            ("Estimated propellant enthalpy gain Delta_h_regen", "delta_h"),
            ("Estimated Isp gain (preliminary)", "isp_gain"),
        ]
        for index, (label, key) in enumerate(definitions):
            card = ttk.LabelFrame(self, text=label, padding=10)
            card.grid(row=index // 4, column=index % 4, sticky="nsew", padx=4, pady=4)
            self.columnconfigure(index % 4, weight=1)
            ttk.Label(card, textvariable=self._tile_vars[key], wraplength=220, justify="left").grid(row=0, column=0, sticky="w")

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        self._unit_preset = unit_preset

    def clear(self) -> None:
        for key in (
            "twg",
            "twc",
            "tc_out",
            "q_total",
            "dp_total",
            "p_cooling_in",
            "p_pump_out",
            "dp_injector",
            "dp_external",
            "dp_margin",
            "margin",
            "delta_h",
        ):
            self._tile_vars[key].set("not available")
        self._tile_vars["isp_gain"].set("preliminary placeholder")

    def update_result(self, result: ThermalAnalysisResult) -> None:
        summary = result.summary
        self._tile_vars["twg"].set(format_quantity(summary.max_wall_temperature_hot_gas_side_k, "temperature", self._unit_preset, include_unit=True))
        self._tile_vars["twc"].set(format_quantity(summary.max_wall_temperature_coolant_side_k, "temperature", self._unit_preset, include_unit=True))
        self._tile_vars["tc_out"].set(format_quantity(summary.coolant_outlet_temperature_k, "temperature", self._unit_preset, include_unit=True))
        self._tile_vars["q_total"].set(_format_power(summary.total_heat_into_coolant_w))
        self._tile_vars["p_cooling_in"].set(format_quantity(summary.required_cooling_inlet_pressure_pa, "pressure", self._unit_preset, include_unit=True))
        self._tile_vars["p_pump_out"].set(format_quantity(summary.required_pump_discharge_pressure_pa, "pressure", self._unit_preset, include_unit=True))
        self._tile_vars["dp_total"].set(format_quantity(summary.total_coolant_pressure_drop_pa, "pressure", self._unit_preset, include_unit=True))
        self._tile_vars["dp_injector"].set(format_quantity(summary.injector_pressure_drop_pa, "pressure", self._unit_preset, include_unit=True))
        self._tile_vars["dp_external"].set(format_quantity(summary.external_feed_pressure_drop_pa, "pressure", self._unit_preset, include_unit=True))
        self._tile_vars["dp_margin"].set(format_quantity(summary.pressure_margin_pa, "pressure", self._unit_preset, include_unit=True))
        self._tile_vars["margin"].set(format_quantity(summary.minimum_thermal_margin_k, "temperature", self._unit_preset, include_unit=True))
        self._tile_vars["delta_h"].set(format_quantity(summary.propellant_enthalpy_gain_j_per_kg, "specific_energy", self._unit_preset, include_unit=True))
        if summary.estimated_isp_gain_s is None:
            self._tile_vars["isp_gain"].set(f"{summary.estimated_isp_gain_note} {summary.pressure_mode_note}")
        else:
            self._tile_vars["isp_gain"].set(
                f"{format_quantity(summary.estimated_isp_gain_s, 'isp', self._unit_preset, include_unit=True)} ({summary.estimated_isp_gain_note})"
            )


class ThermalStationResultsTable(ttk.LabelFrame):
    """Wide horizontally scrollable station result table."""

    _COLUMNS = (
        "station_index",
        "x_start",
        "x_end",
        "x_mid",
        "r_inner",
        "r_outer",
        "r_mean",
        "a_gas",
        "a_hot",
        "a_annulus",
        "d_h",
        "t_recovery",
        "h_g",
        "h_c",
        "q_station",
        "q_hot",
        "t_c_in",
        "t_c_bulk",
        "t_c_out",
        "t_wg",
        "t_wc",
        "delta_t_wall",
        "p_required_in",
        "p_required_out",
        "delta_p_station",
        "re_coolant",
        "nu_coolant",
        "friction_factor",
        "thermal_margin",
        "wall_mean_temperature",
        "pressure_delta",
        "hoop_stress",
        "longitudinal_stress",
        "thermal_strain",
        "thermal_stress",
        "von_mises_stress",
        "material_yield_strength",
        "material_strength_margin",
        "total_screening_strain",
        "material_margin_status",
        "closeout_thickness",
        "closeout_hoop_stress",
        "closeout_material_strength_margin",
        "status_summary",
        "warning_summary",
    )

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset) -> None:
        super().__init__(master, text="Station Results", padding=12)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._unit_preset = unit_preset
        self._result: ThermalAnalysisResult | None = None
        self._tree = ttk.Treeview(self, columns=self._COLUMNS, show="headings", height=16)
        self._tree.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(self, orient="horizontal", command=self._tree.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self._tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self._configure_columns()

    def _configure_columns(self) -> None:
        stress_unit = get_unit_symbol("stress", self._unit_preset)

        def stress_heading(base_label: str) -> str:
            return f"{base_label} [{stress_unit}]" if stress_unit else base_label

        headings = {
            "station_index": "Station index i",
            "x_start": "x_start",
            "x_end": "x_end",
            "x_mid": "x_mid",
            "r_inner": "r_inner",
            "r_outer": "r_outer",
            "r_mean": "r_mean",
            "a_gas": "A_gas",
            "a_hot": "A_hot",
            "a_annulus": "A_annulus",
            "d_h": "D_h",
            "t_recovery": "T_recovery",
            "h_g": "h_g",
            "h_c": "h_c",
            "q_station": "Q_station",
            "q_hot": "q_hot",
            "t_c_in": "T_c_in",
            "t_c_bulk": "T_c_bulk",
            "t_c_out": "T_c_out",
            "t_wg": "T_wg",
            "t_wc": "T_wc",
            "delta_t_wall": "Delta_T_wall",
            "p_required_in": "p_required_in",
            "p_required_out": "p_required_out",
            "delta_p_station": "Delta_p_station",
            "re_coolant": "Re_coolant",
            "nu_coolant": "Nu_coolant",
            "friction_factor": "friction_factor",
            "thermal_margin": "thermal_margin",
            "wall_mean_temperature": "T_wall_mean",
            "pressure_delta": "Delta_p_wall",
            "hoop_stress": stress_heading("sigma_hoop"),
            "longitudinal_stress": stress_heading("sigma_longitudinal"),
            "thermal_strain": "epsilon_thermal",
            "thermal_stress": stress_heading("sigma_thermal_indicator"),
            "von_mises_stress": stress_heading("sigma_vm"),
            "material_yield_strength": stress_heading("yield_strength"),
            "material_strength_margin": "screening_margin_Rp0.2(T)",
            "total_screening_strain": "epsilon_total",
            "material_margin_status": "material_margin_status",
            "closeout_thickness": "closeout_thickness",
            "closeout_hoop_stress": stress_heading("sigma_closeout"),
            "closeout_material_strength_margin": "closeout_margin",
            "status_summary": "status",
            "warning_summary": "warnings",
        }
        for key in self._COLUMNS:
            self._tree.heading(key, text=headings[key])
            if key == "status_summary":
                width = 220
            elif key == "warning_summary":
                width = 320
            elif key == "material_margin_status":
                width = 130
            else:
                width = 110
            self._tree.column(key, width=width, stretch=False, anchor="center")

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        self._unit_preset = unit_preset
        self._configure_columns()
        if self._result is not None:
            self.update_result(self._result)

    def clear(self) -> None:
        self._result = None
        for item in self._tree.get_children():
            self._tree.delete(item)

    def update_result(self, result: ThermalAnalysisResult) -> None:
        self._result = result
        self.clear()
        self._result = result
        for station in result.stations:
            self._tree.insert(
                "",
                "end",
                values=(
                    station.station_index,
                    _fmt_quantity(station.x_start_m, "length", self._unit_preset),
                    _fmt_quantity(station.x_end_m, "length", self._unit_preset),
                    _fmt_quantity(station.x_mid_m, "length", self._unit_preset),
                    _fmt_quantity(station.r_inner_m, "length", self._unit_preset),
                    _fmt_quantity(station.r_outer_m, "length", self._unit_preset),
                    _fmt_quantity(station.r_mean_m, "length", self._unit_preset),
                    _fmt_quantity(station.area_gas_m2, "area", self._unit_preset),
                    _fmt_quantity(station.area_hot_m2, "area", self._unit_preset),
                    _fmt_quantity(station.area_annulus_m2, "area", self._unit_preset),
                    _fmt_quantity(station.hydraulic_diameter_m, "length", self._unit_preset),
                    _fmt_quantity(station.recovery_temperature_k, "temperature", self._unit_preset),
                    _fmt_quantity(station.h_g_w_per_m2_k, "heat_transfer_coefficient", self._unit_preset),
                    _fmt_quantity(station.h_c_w_per_m2_k, "heat_transfer_coefficient", self._unit_preset),
                    _format_power(station.q_station_w),
                    _fmt_quantity(station.q_hot_w_per_m2, "heat_flux", self._unit_preset),
                    _fmt_quantity(station.coolant_temperature_in_k, "temperature", self._unit_preset),
                    _fmt_quantity(station.coolant_temperature_bulk_k, "temperature", self._unit_preset),
                    _fmt_quantity(station.coolant_temperature_out_k, "temperature", self._unit_preset),
                    _fmt_quantity(station.wall_temperature_hot_gas_side_k, "temperature", self._unit_preset),
                    _fmt_quantity(station.wall_temperature_coolant_side_k, "temperature", self._unit_preset),
                    _fmt_quantity(station.wall_delta_t_k, "temperature", self._unit_preset),
                    _fmt_quantity(station.required_pressure_in_pa, "pressure", self._unit_preset),
                    _fmt_quantity(station.required_pressure_out_pa, "pressure", self._unit_preset),
                    _fmt_quantity(station.pressure_drop_station_pa, "pressure", self._unit_preset),
                    _fmt_dimensionless(station.reynolds_coolant),
                    _fmt_dimensionless(station.nusselt_coolant),
                    _fmt_dimensionless(station.friction_factor),
                    _fmt_quantity(station.thermal_margin_k, "temperature", self._unit_preset),
                    _fmt_quantity(station.wall_mean_temperature_k, "temperature", self._unit_preset),
                    _fmt_quantity(station.pressure_delta_pa, "pressure", self._unit_preset),
                    _fmt_quantity(station.hoop_stress_pa, "stress", self._unit_preset),
                    _fmt_quantity(station.longitudinal_stress_pa, "stress", self._unit_preset),
                    _fmt_dimensionless(station.thermal_strain),
                    _fmt_quantity(station.thermal_stress_pa, "stress", self._unit_preset),
                    _fmt_quantity(station.equivalent_von_mises_stress_pa, "stress", self._unit_preset),
                    _fmt_quantity(station.material_yield_strength_pa, "stress", self._unit_preset),
                    _fmt_dimensionless(station.material_strength_margin),
                    _fmt_dimensionless(station.total_screening_strain),
                    station.material_margin_status or "--",
                    _fmt_quantity(station.closeout_thickness_m, "length", self._unit_preset),
                    _fmt_quantity(station.closeout_hoop_stress_pa, "stress", self._unit_preset),
                    _fmt_dimensionless(station.closeout_material_strength_margin),
                    station.status_summary,
                    station.warning_summary,
                ),
            )


class ThermalPlotWindow(tk.Toplevel):
    """Separate plotting window for Thermal Analysis station results."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset) -> None:
        super().__init__(master)
        self.title("Thermal Analysis Plots")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self._unit_preset = unit_preset
        self._result: ThermalAnalysisResult | None = None
        self._last_plot_payload: _ThermalPlotPayload | None = None
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        controls = ttk.LabelFrame(self, text="Plot Selection", padding=12)
        controls.grid(row=0, column=0, sticky="nsw", padx=(12, 8), pady=12)
        controls.columnconfigure(0, weight=1)

        ttk.Label(controls, text="X quantity").grid(row=0, column=0, sticky="w")
        self._x_var = tk.StringVar(value=_THERMAL_PLOT_FIELDS[_THERMAL_PLOT_X_KEYS[2]].label)
        ttk.Combobox(
            controls,
            state="readonly",
            textvariable=self._x_var,
            values=[_THERMAL_PLOT_FIELDS[key].label for key in _THERMAL_PLOT_X_KEYS],
        ).grid(row=1, column=0, sticky="ew", pady=(4, 10))

        ttk.Label(controls, text="Y quantities").grid(row=2, column=0, sticky="w")
        self._y_listbox = tk.Listbox(controls, selectmode="extended", exportselection=False, height=14)
        self._y_listbox.grid(row=3, column=0, sticky="nsew", pady=(4, 10))
        for key, field in _THERMAL_PLOT_FIELDS.items():
            if key in _THERMAL_PLOT_Y_DISABLED_KEYS:
                continue
            self._y_listbox.insert("end", field.label)
        controls.rowconfigure(3, weight=1)

        self._label_to_key = {
            _THERMAL_PLOT_FIELDS[key].label: key
            for key in _THERMAL_PLOT_FIELDS
            if key not in _THERMAL_PLOT_Y_DISABLED_KEYS
        }
        for default_key in _THERMAL_PLOT_DEFAULT_Y_KEYS:
            if default_key in _THERMAL_PLOT_Y_DISABLED_KEYS:
                continue
            label = _THERMAL_PLOT_FIELDS[default_key].label
            index = list(self._label_to_key).index(label)
            self._y_listbox.selection_set(index)

        ttk.Button(controls, text="Plot Selected Quantities", command=self._redraw).grid(
            row=4,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )

        export_frame = ttk.LabelFrame(controls, text="Download", padding=10)
        export_frame.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        export_frame.columnconfigure(0, weight=1)
        export_frame.columnconfigure(1, weight=1)
        ttk.Button(
            export_frame,
            text="Plot Data CSV",
            command=lambda: self._export_plot_data("csv"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        ttk.Button(
            export_frame,
            text="Plot Data TXT",
            command=lambda: self._export_plot_data("txt"),
        ).grid(row=0, column=1, sticky="ew", pady=(0, 6))
        ttk.Button(
            export_frame,
            text="Save PNG",
            command=lambda: self._save_plot_image("png"),
        ).grid(row=1, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(
            export_frame,
            text="Save SVG",
            command=lambda: self._save_plot_image("svg"),
        ).grid(row=1, column=1, sticky="ew")

        custom_frame = ttk.LabelFrame(controls, text="Custom Formula (planned)", padding=10)
        custom_frame.grid(row=6, column=0, sticky="ew")
        custom_entry = ttk.Entry(custom_frame)
        custom_entry.grid(row=0, column=0, sticky="ew")
        custom_entry.configure(state="disabled")
        custom_frame.columnconfigure(0, weight=1)
        ttk.Label(
            custom_frame,
            text="Custom expressions will be added later. For now you can combine multiple built-in station quantities in one plot.",
            wraplength=280,
            justify="left",
            foreground="#667381",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        plot_frame = ttk.LabelFrame(self, text="Thermal Plot", padding=12)
        plot_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 12), pady=12)
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(0, weight=1)

        if Figure is None or FigureCanvasTkAgg is None:
            ttk.Label(
                plot_frame,
                text="matplotlib is not installed. Thermal plots are not available in this environment.",
                wraplength=560,
                justify="left",
            ).grid(row=0, column=0, sticky="nsew")
            self._figure = None
            self._axis = None
            self._canvas = None
            return

        self._figure = Figure(figsize=(7.2, 5.2), dpi=100)
        self._axis = self._figure.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._figure, master=plot_frame)
        self._canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self._status_var = tk.StringVar(value="Select one or more Y quantities and calculate Thermal Analysis.")
        ttk.Label(plot_frame, textvariable=self._status_var, wraplength=720, justify="left").grid(
            row=1, column=0, sticky="ew", pady=(8, 0)
        )

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        self._unit_preset = unit_preset
        self._redraw()

    def set_result(self, result: ThermalAnalysisResult | None) -> None:
        self._result = result
        self._redraw()

    def _redraw(self) -> None:
        if self._axis is None or self._canvas is None:
            return
        self._last_plot_payload = None
        self._axis.clear()
        self._axis.grid(True, linestyle="--", linewidth=0.6, alpha=0.6)

        if self._result is None:
            self._axis.text(0.5, 0.5, "No Thermal Analysis result available yet.", ha="center", va="center", transform=self._axis.transAxes)
            self._status_var.set("Run Thermal Analysis first, then choose X and Y quantities here.")
            self._canvas.draw_idle()
            return

        x_label = self._x_var.get()
        x_key = _thermal_plot_key_from_label(x_label, allowed_keys=_THERMAL_PLOT_X_KEYS)
        if x_key is None:
            self._axis.text(0.5, 0.5, "Choose a valid X quantity.", ha="center", va="center", transform=self._axis.transAxes)
            self._status_var.set("The selected X quantity is not available.")
            self._canvas.draw_idle()
            return

        selected_labels = [self._y_listbox.get(index) for index in self._y_listbox.curselection()]
        selected_keys = [self._label_to_key[label] for label in selected_labels if label in self._label_to_key]
        if not selected_keys:
            self._axis.text(0.5, 0.5, "Select at least one Y quantity.", ha="center", va="center", transform=self._axis.transAxes)
            self._status_var.set("Select one or more Y quantities to draw a plot.")
            self._canvas.draw_idle()
            return

        payload = _build_plot_payload(self._result, x_key, selected_keys, self._unit_preset)
        self._last_plot_payload = payload
        series_count = 0
        for series in payload.series:
            paired = [
                (x_value, y_value)
                for x_value, y_value in zip(payload.x_values, series.values)
                if x_value is not None and y_value is not None
            ]
            if not paired:
                continue
            xs, ys = zip(*paired)
            self._axis.plot(xs, ys, linewidth=2.0, marker="o", markersize=3.5, label=series.label)
            series_count += 1

        self._axis.set_xlabel(_plot_axis_label(x_key, self._unit_preset))
        self._axis.set_ylabel("Selected thermal quantities")
        if series_count > 0:
            self._axis.legend(loc="best")
            self._status_var.set(
                "Plot uses the current Thermal Analysis result only. Change selections here freely without recalculating."
            )
        else:
            self._axis.text(0.5, 0.5, "The selected quantities do not contain plottable values.", ha="center", va="center", transform=self._axis.transAxes)
            self._status_var.set("The selected quantity combination does not currently produce valid plot points.")
        self._figure.tight_layout()
        self._canvas.draw_idle()

    def _export_plot_data(self, file_kind: str) -> None:
        """Write the currently visible plot data to a simple engineering table."""

        if self._last_plot_payload is None:
            messagebox.showinfo("No plot data available", "Create a plot first, then export the current data selection.")
            return
        target_path = filedialog.asksaveasfilename(
            parent=self,
            title="Save plot data",
            defaultextension=f".{file_kind}",
            filetypes=[
                ("CSV files", "*.csv"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not target_path:
            return
        rows = _build_plot_export_rows(self._last_plot_payload)
        if file_kind == "csv":
            with open(target_path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerows(rows)
        else:
            with open(target_path, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write("\t".join(row) + "\n")
        self._status_var.set(f"Saved plot data to {target_path}")

    def _save_plot_image(self, file_kind: str) -> None:
        """Save the visible figure as a raster or vector file."""

        if self._figure is None or self._canvas is None or self._last_plot_payload is None:
            messagebox.showinfo("No plot image available", "Create a plot first, then save the current figure.")
            return
        filetypes = [("PNG image", "*.png")] if file_kind == "png" else [("SVG vector", "*.svg")]
        target_path = filedialog.asksaveasfilename(
            parent=self,
            title="Save plot image",
            defaultextension=f".{file_kind}",
            filetypes=filetypes + [("All files", "*.*")],
        )
        if not target_path:
            return
        self._figure.tight_layout()
        self._figure.savefig(target_path, dpi=200 if file_kind == "png" else None)
        self._status_var.set(f"Saved plot image to {target_path}")


class ThermalAnalysisPage(ttk.Frame):
    """Full vertically scrollable Thermal Analysis page."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset) -> None:
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._unit_preset = unit_preset
        self._cached_inputs: ThermalAnalysisInputs | None = None
        self._current_result: ThermalAnalysisResult | None = None
        self._plot_window: ThermalPlotWindow | None = None
        self._scrollable = ScrollableContentFrame(self)
        self._scrollable.grid(row=0, column=0, sticky="nsew")
        content = self._scrollable.content
        content.columnconfigure(0, weight=1)

        header = ttk.Frame(content, padding=(0, 0, 0, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Thermal Analysis", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Annulus-cooling MVP reference model for thermal-hydraulic predesign",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(
            header,
            text="MVP Reference Model",
            background="#dfe9f5",
            foreground="#244a6d",
            padx=8,
            pady=3,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        self._context_card = ExistingDesignContextCard(content, unit_preset=unit_preset)
        self._context_card.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        input_row = ttk.Frame(content)
        input_row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        input_row.columnconfigure(0, weight=1)
        input_row.columnconfigure(1, weight=1)
        self._annulus_card = AnnulusCoolingCard(input_row, unit_preset=unit_preset)
        self._annulus_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._solver_card = SolverSettingsCard(input_row)
        self._solver_card.grid(row=0, column=1, sticky="nsew")

        self._radiation_card = RadiationCard(content, unit_preset=unit_preset)
        self._radiation_card.grid(row=3, column=0, sticky="ew", pady=(12, 0))

        self._future_channel_panel = FutureChannelDefinitionPanel(content)
        self._future_channel_panel.grid(row=4, column=0, sticky="ew", pady=(12, 0))

        self._action_row = ThermalActionRow(content)
        self._action_row.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        self._action_row.bind_open_plot(self.open_plot_window)

        self._summary_tiles = ThermalSummaryTiles(content, unit_preset=unit_preset)
        self._summary_tiles.grid(row=6, column=0, sticky="ew", pady=(12, 0))

        self._results_table = ThermalStationResultsTable(content, unit_preset=unit_preset)
        self._results_table.grid(row=7, column=0, sticky="nsew", pady=(12, 0))

    def bind_calculate(self, callback: Callable[[], None]) -> None:
        self._action_row.bind_calculate(callback)

    def bind_reset(self, callback: Callable[[], None]) -> None:
        self._action_row.bind_reset(callback)

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        self._unit_preset = unit_preset
        self._context_card.set_unit_preset(unit_preset)
        self._annulus_card.set_unit_preset(unit_preset)
        self._radiation_card.set_unit_preset(unit_preset)
        self._summary_tiles.set_unit_preset(unit_preset)
        self._results_table.set_unit_preset(unit_preset)
        if self._plot_window is not None and self._plot_window.winfo_exists():
            self._plot_window.set_unit_preset(unit_preset)
        if self._cached_inputs is not None:
            self.set_inputs(self._cached_inputs)

    def set_inputs(self, inputs: ThermalAnalysisInputs) -> None:
        self._cached_inputs = inputs
        self._annulus_card.set_inputs(inputs)
        self._radiation_card.set_inputs(inputs)
        self._solver_card.set_inputs(inputs.solver_settings)

    def get_inputs(self) -> ThermalAnalysisInputs:
        partial_inputs = self._annulus_card.get_partial_inputs()
        solver_settings = self._solver_card.get_settings()
        inputs = ThermalAnalysisInputs(
            coolant_mass_flow_kg_per_s=partial_inputs["coolant_mass_flow_kg_per_s"],
            coolant_type=self._cached_inputs.coolant_type if self._cached_inputs is not None else "RP-1",
            model_type=partial_inputs["model_type"],
            coolant_inlet_temperature_k=float(partial_inputs["coolant_inlet_temperature_k"]),
            annulus_gap_m=float(partial_inputs["annulus_gap_m"]),
            coolant_roughness_m=float(partial_inputs["coolant_roughness_m"]),
            injector_pressure_drop_pa=float(partial_inputs["injector_pressure_drop_pa"]),
            pressure_margin_pa=float(partial_inputs["pressure_margin_pa"]),
            external_feed_pressure_drop_pa=float(partial_inputs["external_feed_pressure_drop_pa"]),
            pump_discharge_pressure_pa=partial_inputs["pump_discharge_pressure_pa"],
            bartz_throat_curvature_mode=partial_inputs["bartz_throat_curvature_mode"],
            flow_direction=partial_inputs["flow_direction"],
            solver_settings=solver_settings,
            radiation_settings=self._radiation_card.get_settings(),
        )
        inputs.solver_settings.pressure_mode = partial_inputs["pressure_mode"]
        self._cached_inputs = inputs
        return inputs

    def update_design_context(
        self,
        *,
        current_inputs: InputParameters | None,
        current_bundle: ExportBundle | None,
        thermal_inputs: ThermalAnalysisInputs,
        design_status_label: str,
        geometry_source_label: str,
        contour_status_label: str,
        profile_station_count: int | None,
    ) -> None:
        self._context_card.update_context(
            current_inputs=current_inputs,
            current_bundle=current_bundle,
            thermal_inputs=thermal_inputs,
            design_status_label=design_status_label,
            geometry_source_label=geometry_source_label,
            contour_status_label=contour_status_label,
        )
        self._solver_card.set_profile_station_count(profile_station_count)

    def clear_result(self) -> None:
        self._current_result = None
        self._summary_tiles.clear()
        self._results_table.clear()
        if self._plot_window is not None and self._plot_window.winfo_exists():
            self._plot_window.set_result(None)

    def show_result(self, result: ThermalAnalysisResult) -> None:
        self._current_result = result
        self._summary_tiles.update_result(result)
        self._results_table.update_result(result)
        if self._plot_window is not None and self._plot_window.winfo_exists():
            self._plot_window.set_result(result)

    def open_plot_window(self) -> None:
        """Open or raise the separate thermal-plot window."""

        if self._plot_window is not None and self._plot_window.winfo_exists():
            self._plot_window.lift()
            self._plot_window.focus_force()
            return
        if Figure is None or FigureCanvasTkAgg is None:
            messagebox.showinfo(
                "Thermal plots not available",
                "matplotlib is not installed, so the thermal plot window cannot be opened in this environment.",
            )
            return
        self._plot_window = ThermalPlotWindow(self, unit_preset=self._unit_preset)
        self._plot_window.transient(self.winfo_toplevel())
        self._plot_window.set_result(self._current_result)


def _parse_required_float(raw_value: str, label: str, errors: list[str]) -> float:
    text = raw_value.strip().replace(",", ".")
    if not text:
        errors.append(f"{label} must not be empty.")
        return 0.0
    try:
        return float(text)
    except ValueError:
        errors.append(f"{label} must be a valid number.")
        return 0.0


def _parse_optional_float(raw_value: str, label: str, errors: list[str]) -> float | None:
    text = raw_value.strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        errors.append(f"{label} must be a valid number.")
        return None


def _parse_required_int(raw_value: str, label: str, errors: list[str]) -> int:
    text = raw_value.strip()
    if not text:
        errors.append(f"{label} must not be empty.")
        return 0
    try:
        return int(text)
    except ValueError:
        errors.append(f"{label} must be an integer.")
        return 0


def _parse_fallback_int(raw_value: str, *, default: int) -> int:
    text = raw_value.strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError:
        return default


def _convert_lengthless_quantity(value: float | None, quantity: str, unit_preset: UnitPreset) -> float | None:
    if value is None:
        return None
    from engine.unit_system import convert_from_display

    return convert_from_display(value, quantity, unit_preset)


def _format_power(value_w: float | None) -> str:
    if value_w is None:
        return "--"
    if abs(value_w) >= 1.0e6:
        return f"{value_w / 1.0e6:.3f} MW"
    if abs(value_w) >= 1.0e3:
        return f"{value_w / 1.0e3:.3f} kW"
    return f"{value_w:.2f} W"


def _fmt_quantity(value: float | None, quantity: str, unit_preset: UnitPreset) -> str:
    return format_quantity(value, quantity, unit_preset)


def _fmt_dimensionless(value: float | None) -> str:
    if value is None:
        return "--"
    if abs(value) >= 1.0e4:
        return f"{value:.3e}"
    return f"{value:.4f}"


def _plot_series_values(
    result: ThermalAnalysisResult,
    field_key: str,
    unit_preset: UnitPreset,
) -> list[float | None]:
    """Return one display-ready station series for the thermal plot window."""

    field = _THERMAL_PLOT_FIELDS[field_key]
    values: list[float | None] = []
    for station in result.stations:
        value = field.extractor(station)
        if value is None:
            values.append(None)
            continue
        if field.quantity is None:
            values.append(float(value))
        else:
            values.append(convert_to_display(value, field.quantity, unit_preset))
    return values


def _build_plot_payload(
    result: ThermalAnalysisResult,
    x_key: str,
    y_keys: list[str],
    unit_preset: UnitPreset,
) -> _ThermalPlotPayload:
    """Build one reusable payload for redraw and export.

    Keeping the display-unit series in one object avoids slight mismatches
    between the visible plot and the exported files.
    """

    return _ThermalPlotPayload(
        x_key=x_key,
        x_label=_plot_axis_label(x_key, unit_preset),
        x_values=_plot_series_values(result, x_key, unit_preset),
        series=[
            _ThermalPlotSeries(
                key=y_key,
                label=_plot_axis_label(y_key, unit_preset),
                values=_plot_series_values(result, y_key, unit_preset),
            )
            for y_key in y_keys
        ],
    )


def _build_plot_export_rows(payload: _ThermalPlotPayload) -> list[list[str]]:
    """Return a plain table for CSV/TXT export of the currently visible plot."""

    header = [payload.x_label] + [series.label for series in payload.series]
    rows = [header]
    row_count = len(payload.x_values)
    for row_index in range(row_count):
        row = [_format_plot_export_value(payload.x_values[row_index])]
        for series in payload.series:
            row.append(_format_plot_export_value(series.values[row_index]))
        rows.append(row)
    return rows


def _plot_axis_label(field_key: str, unit_preset: UnitPreset) -> str:
    field = _THERMAL_PLOT_FIELDS[field_key]
    if field.quantity is None:
        return f"{field.label} [-]"
    return f"{field.label} [{get_unit_symbol(field.quantity, unit_preset)}]"


def _thermal_plot_key_from_label(label: str, *, allowed_keys: tuple[str, ...] | None = None) -> str | None:
    keys = allowed_keys if allowed_keys is not None else tuple(_THERMAL_PLOT_FIELDS)
    for key in keys:
        if _THERMAL_PLOT_FIELDS[key].label == label:
            return key
    return None


def _format_plot_export_value(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.9g}"

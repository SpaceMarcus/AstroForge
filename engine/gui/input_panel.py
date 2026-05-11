"""Tkinter input panel for engine design parameters."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from engine.flow import FlowCase, FlowCaseAssessment
from engine.models import BellContourVariant, ChemistryMode, InputParameters, NozzleContourMethod
from engine.performance_preview import PerformancePreviewResult, eta_cstar_band
from engine.unit_system import UnitPreset, convert_from_display, format_quantity, get_unit_symbol
from engine.utils.validation import InputValidationError

FAMILY_LABELS = {
    NozzleContourMethod.CONICAL: "Conical",
    NozzleContourMethod.BELL: "Bell",
    NozzleContourMethod.AEROSPIKE: "Aerospike (future)",
}
FAMILY_VALUES = {label: method for method, label in FAMILY_LABELS.items()}
SUBTYPE_LABELS = {
    BellContourVariant.PARABOLA: "Parabola (TOP)",
    BellContourVariant.TIC: "TIC",
    BellContourVariant.TOC: "TOC",
}
SUBTYPE_VALUES = {label: variant for variant, label in SUBTYPE_LABELS.items()}


class InputPanel(ttk.LabelFrame):
    """Collect user inputs in display-friendly units and convert to SI."""

    _DERIVED_FLOW_UNAVAILABLE_TEXT = "requires thermochemistry/performance"
    _DERIVED_SPLIT_UNAVAILABLE_TEXT = "not yet computed"
    _PREVIEW_UNAVAILABLE_TEXT = "—"

    def __init__(
        self,
        master: tk.Misc,
        *,
        unit_preset: UnitPreset = UnitPreset.SI_CAD,
        show_current_design_features: bool = False,
    ) -> None:
        super().__init__(master, text="AstraForge Inputs", padding=12)
        self.columnconfigure(0, weight=1)
        self._unit_preset = unit_preset
        self._show_current_design_features = show_current_design_features
        self._chemistry_box: ttk.Combobox | None = None
        self._length_apply_callback: Callable[[], None] | None = None
        self._input_changed_callback: Callable[[], None] | None = None
        self._bell_subtype_widgets: list[tk.Widget] = []
        self._nozzle_control_widgets: list[tk.Widget] = []
        self._editable_widgets: list[tk.Widget] = []
        self._field_labels: dict[str, ttk.Label] = {}
        self._suspend_change_notifications = False
        self._nozzle_controls_enabled = True
        self._editable = True
        self._flow_case_notice_var = tk.StringVar(value="")
        self._performance_preview_result: PerformancePreviewResult | None = None
        self._changed_performance_preview_keys: set[str] = set()
        self._derived_flow_values = {
            "total_mass_flow": tk.StringVar(value=self._DERIVED_FLOW_UNAVAILABLE_TEXT),
            "fuel_mass_flow": tk.StringVar(value=self._DERIVED_SPLIT_UNAVAILABLE_TEXT),
            "oxidizer_mass_flow": tk.StringVar(value=self._DERIVED_SPLIT_UNAVAILABLE_TEXT),
        }
        self._performance_preview_values = {
            "c_star_theoretical": tk.StringVar(value=self._PREVIEW_UNAVAILABLE_TEXT),
            "c_star_design": tk.StringVar(value=self._PREVIEW_UNAVAILABLE_TEXT),
            "cf_design": tk.StringVar(value=self._PREVIEW_UNAVAILABLE_TEXT),
            "isp_vac": tk.StringVar(value=self._PREVIEW_UNAVAILABLE_TEXT),
            "isp_sl": tk.StringVar(value=self._PREVIEW_UNAVAILABLE_TEXT),
            "mass_flow": tk.StringVar(value=self._PREVIEW_UNAVAILABLE_TEXT),
            "thrust_estimate": tk.StringVar(value=self._PREVIEW_UNAVAILABLE_TEXT),
            "chamber_pressure": tk.StringVar(value=self._PREVIEW_UNAVAILABLE_TEXT),
            "thrust_deviation": tk.StringVar(value=self._PREVIEW_UNAVAILABLE_TEXT),
        }
        self._performance_preview_value_labels: dict[str, ttk.Label] = {}
        self._derived_total_mass_flow_kg_per_s: float | None = None
        self._derived_mixture_ratio: float | None = None
        self._combustion_eta_entry: ttk.Entry | None = None
        self._combustion_loss_label: ttk.Label | None = None
        self._combustion_warning_label: ttk.Label | None = None
        self._current_design_value_labels: list[ttk.Label] = []
        self._current_design_value_definitions = (
            (
                ("F_design", "thrust_estimate"),
                ("Isp_vac", "isp_vac"),
            ),
            (
                ("Isp_sl", "isp_sl"),
                ("pc", "chamber_pressure"),
            ),
            (
                ("mdot", "mass_flow"),
                ("c*_theoretical", "c_star_theoretical"),
            ),
            (
                ("c*_design", "c_star_design"),
                ("Cf_design", "cf_design"),
            ),
            (
                ("Deviation", "thrust_deviation"),
                None,
            ),
        )
        self._variables = {
            "fuel": tk.StringVar(),
            "oxidizer": tk.StringVar(),
            "chamber_pressure": tk.StringVar(),
            "thrust": tk.StringVar(),
            "mixture_ratio": tk.StringVar(),
            "expansion_ratio": tk.StringVar(),
            "ambient_pressure": tk.StringVar(),
            "contraction_ratio": tk.StringVar(),
            "characteristic_length": tk.StringVar(),
            "manual_nozzle_length": tk.StringVar(),
            "chemistry_mode": tk.StringVar(value=ChemistryMode.EQUILIBRIUM.value),
            "contour_family": tk.StringVar(value=FAMILY_LABELS[NozzleContourMethod.BELL]),
            "bell_subtype": tk.StringVar(value=SUBTYPE_LABELS[BellContourVariant.PARABOLA]),
            "current_expansion_ratio_display": tk.StringVar(value="--"),
            "optimal_expansion_ratio_display": tk.StringVar(value="pending calculation"),
        }
        self._use_combustion_efficiency_var = tk.BooleanVar(value=True)
        self._combustion_eta_var = tk.StringVar(value="0.95")
        self._combustion_loss_var = tk.StringVar(value="Assumed combustion loss: 5.0 %")
        self._combustion_warning_var = tk.StringVar(value="")
        self._variables["expansion_ratio"].trace_add("write", self._sync_current_expansion_ratio)
        self._variables["contour_family"].trace_add("write", self._sync_bell_subtype_visibility)
        for key in (
            "fuel",
            "oxidizer",
            "chamber_pressure",
            "thrust",
            "mixture_ratio",
            "expansion_ratio",
            "ambient_pressure",
            "contraction_ratio",
            "characteristic_length",
            "manual_nozzle_length",
            "chemistry_mode",
            "contour_family",
            "bell_subtype",
        ):
            self._variables[key].trace_add("write", self._handle_input_changed)
        self._use_combustion_efficiency_var.trace_add("write", self._handle_combustion_efficiency_changed)
        self._combustion_eta_var.trace_add("write", self._handle_combustion_efficiency_changed)
        self._ensure_styles()
        self._build_widgets()

    @property
    def unit_preset(self) -> UnitPreset:
        """Return the currently selected input/display unit preset."""

        return self._unit_preset

    def _build_widgets(self) -> None:
        ttk.Label(
            self,
            text="AstraForge keeps all internal calculations in SI units.",
            wraplength=360,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(
            self,
            textvariable=self._flow_case_notice_var,
            wraplength=360,
            justify="left",
            foreground="#7d4d1b",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 10))

        propellant_frame = ttk.LabelFrame(self, text="Propellant and Mixture", padding=10)
        propellant_frame.grid(row=2, column=0, sticky="ew")
        propellant_frame.columnconfigure(1, weight=1)

        ttk.Label(propellant_frame, text="Fuel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        fuel_entry = ttk.Entry(propellant_frame, textvariable=self._variables["fuel"])
        fuel_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            pady=4,
        )
        self._editable_widgets.append(fuel_entry)

        ttk.Label(propellant_frame, text="Oxidizer").grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        oxidizer_entry = ttk.Entry(propellant_frame, textvariable=self._variables["oxidizer"])
        oxidizer_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            pady=4,
        )
        self._editable_widgets.append(oxidizer_entry)

        self._field_labels["mixture_ratio"] = ttk.Label(propellant_frame, text="O/F ratio [-]")
        self._field_labels["mixture_ratio"].grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        mixture_ratio_entry = ttk.Entry(
            propellant_frame,
            textvariable=self._variables["mixture_ratio"],
            width=18,
            font=("Segoe UI", 12, "bold"),
        )
        mixture_ratio_entry.grid(
            row=2,
            column=1,
            sticky="ew",
            pady=4,
        )
        self._editable_widgets.append(mixture_ratio_entry)

        operating_frame = ttk.LabelFrame(self, text="Operating Point", padding=10)
        operating_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        operating_frame.columnconfigure(1, weight=1)

        self._field_labels["chamber_pressure"] = ttk.Label(operating_frame)
        self._field_labels["chamber_pressure"].grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        chamber_pressure_entry = ttk.Entry(operating_frame, textvariable=self._variables["chamber_pressure"])
        chamber_pressure_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            pady=4,
        )
        self._editable_widgets.append(chamber_pressure_entry)

        self._field_labels["thrust"] = ttk.Label(operating_frame)
        self._field_labels["thrust"].grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        thrust_entry = ttk.Entry(operating_frame, textvariable=self._variables["thrust"])
        thrust_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            pady=4,
        )
        self._editable_widgets.append(thrust_entry)

        self._field_labels["ambient_pressure"] = ttk.Label(operating_frame)
        self._field_labels["ambient_pressure"].grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        ambient_pressure_entry = ttk.Entry(operating_frame, textvariable=self._variables["ambient_pressure"])
        ambient_pressure_entry.grid(
            row=2,
            column=1,
            sticky="ew",
            pady=4,
        )
        self._editable_widgets.append(ambient_pressure_entry)

        ttk.Label(operating_frame, text="Chemistry mode").grid(
            row=3,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        chemistry_box = ttk.Combobox(
            operating_frame,
            state="readonly",
            textvariable=self._variables["chemistry_mode"],
            values=[mode.value for mode in ChemistryMode],
        )
        chemistry_box.grid(row=3, column=1, sticky="ew", pady=4)
        self._chemistry_box = chemistry_box
        self._editable_widgets.append(chemistry_box)

        next_row = 4

        if self._show_current_design_features:
            combustion_frame = ttk.LabelFrame(self, text="Combustion Efficiency", padding=10)
            combustion_frame.grid(row=next_row, column=0, sticky="ew", pady=(10, 0))
            combustion_frame.columnconfigure(1, weight=1)

            combustion_check = ttk.Checkbutton(
                combustion_frame,
                text="Use combustion efficiency assumption",
                variable=self._use_combustion_efficiency_var,
            )
            combustion_check.grid(row=0, column=0, columnspan=2, sticky="w")
            self._editable_widgets.append(combustion_check)

            ttk.Label(combustion_frame, text="eta_cstar_design [-]").grid(
                row=1,
                column=0,
                sticky="w",
                padx=(0, 10),
                pady=(8, 4),
            )
            self._combustion_eta_entry = ttk.Entry(
                combustion_frame,
                textvariable=self._combustion_eta_var,
            )
            self._combustion_eta_entry.grid(row=1, column=1, sticky="ew", pady=(8, 4))
            self._editable_widgets.append(self._combustion_eta_entry)

            self._combustion_loss_label = ttk.Label(
                combustion_frame,
                textvariable=self._combustion_loss_var,
                wraplength=320,
                justify="left",
            )
            self._combustion_loss_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

            ttk.Label(
                combustion_frame,
                text=(
                    "Combustion efficiency is a pre-design assumption. "
                    "Typical values: 0.95–0.99 for liquid rocket engines."
                ),
                wraplength=320,
                justify="left",
                style="Hint.TLabel",
            ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

            self._combustion_warning_label = ttk.Label(
                combustion_frame,
                textvariable=self._combustion_warning_var,
                wraplength=320,
                justify="left",
                style="Warning.TLabel",
            )
            self._combustion_warning_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
            next_row += 1

            performance_frame = ttk.LabelFrame(self, text="Performance Preview", padding=10)
            performance_frame.grid(row=next_row, column=0, sticky="ew", pady=(10, 0))
            for column in range(4):
                performance_frame.columnconfigure(column, weight=1)

            for row_index, pair in enumerate(self._current_design_value_definitions):
                left_item, right_item = pair
                left_label_text, left_key = left_item
                ttk.Label(performance_frame, text=left_label_text).grid(
                    row=row_index,
                    column=0,
                    sticky="w",
                    padx=(0, 6),
                    pady=2,
                )
                left_value_label = ttk.Label(
                    performance_frame,
                    textvariable=self._performance_preview_values[left_key],
                    style="PreviewValue.TLabel",
                )
                left_value_label.grid(row=row_index, column=1, sticky="w", pady=2)
                self._performance_preview_value_labels[left_key] = left_value_label

                if right_item is None:
                    continue
                right_label_text, right_key = right_item
                ttk.Label(performance_frame, text=right_label_text).grid(
                    row=row_index,
                    column=2,
                    sticky="w",
                    padx=(16, 6),
                    pady=2,
                )
                right_value_label = ttk.Label(
                    performance_frame,
                    textvariable=self._performance_preview_values[right_key],
                    style="PreviewValue.TLabel",
                )
                right_value_label.grid(row=row_index, column=3, sticky="w", pady=2)
                self._performance_preview_value_labels[right_key] = right_value_label
            next_row += 1

        geometry_frame = ttk.LabelFrame(self, text="Nozzle and Chamber Inputs", padding=10)
        geometry_frame.grid(row=next_row, column=0, sticky="ew", pady=(10, 0))
        geometry_frame.columnconfigure(1, weight=1)

        ttk.Label(geometry_frame, text="Nozzle family").grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        contour_box = ttk.Combobox(
            geometry_frame,
            state="readonly",
            textvariable=self._variables["contour_family"],
            values=list(FAMILY_VALUES),
        )
        contour_box.grid(row=0, column=1, sticky="ew", pady=4)
        self._nozzle_control_widgets.append(contour_box)
        self._editable_widgets.append(contour_box)

        bell_subtype_label = ttk.Label(geometry_frame, text="Bell subtype")
        bell_subtype_label.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        bell_subtype_box = ttk.Combobox(
            geometry_frame,
            state="readonly",
            textvariable=self._variables["bell_subtype"],
            values=list(SUBTYPE_VALUES),
        )
        bell_subtype_box.grid(row=1, column=1, sticky="ew", pady=4)
        self._bell_subtype_widgets.extend([bell_subtype_label, bell_subtype_box])
        self._nozzle_control_widgets.append(bell_subtype_box)
        self._editable_widgets.append(bell_subtype_box)

        self._field_labels["expansion_ratio"] = ttk.Label(geometry_frame, text="eps = Ae/At [-]")
        self._field_labels["expansion_ratio"].grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        expansion_entry = ttk.Entry(geometry_frame, textvariable=self._variables["expansion_ratio"])
        expansion_entry.grid(
            row=2,
            column=1,
            sticky="ew",
            pady=4,
        )
        self._nozzle_control_widgets.append(expansion_entry)
        self._editable_widgets.append(expansion_entry)

        ttk.Label(geometry_frame, text="Current eps [-]").grid(
            row=3,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=2,
        )
        ttk.Label(
            geometry_frame,
            textvariable=self._variables["current_expansion_ratio_display"],
        ).grid(row=3, column=1, sticky="w", pady=2)

        ttk.Label(geometry_frame, text="Optimal eps [-]").grid(
            row=4,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=2,
        )
        ttk.Label(
            geometry_frame,
            textvariable=self._variables["optimal_expansion_ratio_display"],
            wraplength=220,
            justify="left",
        ).grid(row=4, column=1, sticky="w", pady=2)

        self._field_labels["contraction_ratio"] = ttk.Label(geometry_frame, text="Ac/At [-] optional")
        self._field_labels["contraction_ratio"].grid(
            row=5,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        contraction_entry = ttk.Entry(geometry_frame, textvariable=self._variables["contraction_ratio"])
        contraction_entry.grid(
            row=5,
            column=1,
            sticky="ew",
            pady=4,
        )
        self._editable_widgets.append(contraction_entry)

        self._field_labels["characteristic_length"] = ttk.Label(geometry_frame)
        self._field_labels["characteristic_length"].grid(
            row=6,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        characteristic_length_entry = ttk.Entry(geometry_frame, textvariable=self._variables["characteristic_length"])
        characteristic_length_entry.grid(
            row=6,
            column=1,
            sticky="ew",
            pady=4,
        )
        self._editable_widgets.append(characteristic_length_entry)

        self._field_labels["manual_nozzle_length"] = ttk.Label(geometry_frame)
        self._field_labels["manual_nozzle_length"].grid(
            row=7,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        length_row = ttk.Frame(geometry_frame)
        length_row.grid(row=7, column=1, sticky="ew", pady=4)
        length_row.columnconfigure(0, weight=1)
        manual_length_entry = ttk.Entry(length_row, textvariable=self._variables["manual_nozzle_length"])
        manual_length_entry.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        self._nozzle_control_widgets.append(manual_length_entry)
        self._editable_widgets.append(manual_length_entry)
        manual_length_button = ttk.Button(
            length_row,
            text="Apply length",
            command=self._handle_length_apply,
        )
        manual_length_button.grid(row=0, column=1, padx=(8, 0))
        self._nozzle_control_widgets.append(manual_length_button)
        self._editable_widgets.append(manual_length_button)

        ttk.Label(
            geometry_frame,
            text=(
                "Aerospike is reserved for a future version. TIC and TOC stay visible in the "
                "Bell UI but are intentionally blocked until dedicated geometry logic is added."
            ),
            wraplength=300,
            justify="left",
        ).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        derived_flow_frame = ttk.LabelFrame(self, text="Derived Flow Quantities", padding=10)
        derived_flow_frame.grid(row=next_row + 1, column=0, sticky="ew", pady=(10, 0))
        derived_flow_frame.columnconfigure(1, weight=1)

        self._field_labels["total_mass_flow"] = ttk.Label(derived_flow_frame)
        self._field_labels["total_mass_flow"].grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        ttk.Label(
            derived_flow_frame,
            textvariable=self._derived_flow_values["total_mass_flow"],
        ).grid(row=0, column=1, sticky="w", pady=4)

        self._field_labels["fuel_mass_flow"] = ttk.Label(derived_flow_frame)
        self._field_labels["fuel_mass_flow"].grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        ttk.Label(
            derived_flow_frame,
            textvariable=self._derived_flow_values["fuel_mass_flow"],
        ).grid(row=1, column=1, sticky="w", pady=4)

        self._field_labels["oxidizer_mass_flow"] = ttk.Label(derived_flow_frame)
        self._field_labels["oxidizer_mass_flow"].grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        ttk.Label(
            derived_flow_frame,
            textvariable=self._derived_flow_values["oxidizer_mass_flow"],
        ).grid(row=2, column=1, sticky="w", pady=4)

        self._sync_bell_subtype_visibility()
        self._apply_unit_labels()
        self._refresh_combustion_efficiency_display()
        self._refresh_performance_preview_display()

    def bind_chemistry_mode_changed(self, callback: Callable[[object], None]) -> None:
        """Bind a callback to chemistry mode changes."""

        if self._chemistry_box is not None:
            self._chemistry_box.bind("<<ComboboxSelected>>", callback)

    def bind_length_apply(self, callback: Callable[[], None]) -> None:
        """Bind a callback to the manual nozzle-length button."""

        self._length_apply_callback = callback

    def bind_inputs_changed(self, callback: Callable[[], None]) -> None:
        """Bind a callback fired when user-editable inputs change."""

        self._input_changed_callback = callback

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update the panel display preset while preserving current SI meaning."""

        if unit_preset is self._unit_preset:
            return

        current_inputs: InputParameters | None
        try:
            current_inputs = self.get_input_parameters()
        except InputValidationError:
            current_inputs = None

        self._unit_preset = unit_preset
        self._apply_unit_labels()
        if current_inputs is not None:
            self.set_inputs(current_inputs)
        self._refresh_derived_flow_display()
        self._refresh_performance_preview_display()

    def set_inputs(self, inputs: InputParameters) -> None:
        """Populate the panel from SI-based input parameters."""

        self._suspend_change_notifications = True
        self._variables["fuel"].set(inputs.fuel)
        self._variables["oxidizer"].set(inputs.oxidizer)
        self._variables["chamber_pressure"].set(
            format_quantity(inputs.chamber_pressure_pa, "pressure", self._unit_preset)
        )
        self._variables["thrust"].set(format_quantity(inputs.thrust_n, "force", self._unit_preset))
        self._variables["mixture_ratio"].set(f"{inputs.mixture_ratio:.4f}")
        self._variables["expansion_ratio"].set(f"{inputs.expansion_ratio:.4f}")
        self._variables["ambient_pressure"].set(
            format_quantity(inputs.ambient_pressure_pa, "pressure", self._unit_preset)
        )
        self._variables["contraction_ratio"].set(
            "" if inputs.contraction_ratio is None else f"{inputs.contraction_ratio:.4f}"
        )
        self._variables["characteristic_length"].set(
            ""
            if inputs.characteristic_length_m is None
            else format_quantity(inputs.characteristic_length_m, "length", self._unit_preset)
        )
        self._variables["manual_nozzle_length"].set(
            ""
            if inputs.manual_nozzle_length_m is None
            else format_quantity(inputs.manual_nozzle_length_m, "length", self._unit_preset)
        )
        self._variables["chemistry_mode"].set(inputs.chemistry_mode.value)
        self._variables["contour_family"].set(FAMILY_LABELS[inputs.contour_method])
        self._variables["bell_subtype"].set(SUBTYPE_LABELS[inputs.bell_variant])
        self._variables["optimal_expansion_ratio_display"].set("pending calculation")
        self._sync_bell_subtype_visibility()
        self._suspend_change_notifications = False

    def set_editable(self, editable: bool) -> None:
        """Enable or disable editing across the baseline input form."""

        self._editable = editable
        for widget in self._editable_widgets:
            if widget in self._nozzle_control_widgets:
                continue
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="readonly" if editable else "disabled")
            elif isinstance(widget, ttk.Button):
                widget.configure(state="normal" if editable else "disabled")
            else:
                widget.configure(state="normal" if editable else "disabled")
        self._set_nozzle_controls_enabled(self._nozzle_controls_enabled)

    def set_mixture_ratio(self, mixture_ratio: float) -> None:
        """Update only the O/F ratio field, for example from the O/F sweep plot."""

        self._variables["mixture_ratio"].set(f"{mixture_ratio:.4f}")

    def get_combustion_efficiency_assumption(self) -> float:
        """Return the Current Design combustion-efficiency assumption."""

        if not self._show_current_design_features or not self._use_combustion_efficiency_var.get():
            return 1.0

        raw_value = self._combustion_eta_var.get().strip()
        errors: list[str] = []
        if not raw_value:
            errors.append("eta_cstar_design must not be empty when the assumption is enabled.")
        else:
            try:
                eta_cstar_design = float(raw_value.replace(",", "."))
            except ValueError:
                errors.append("eta_cstar_design must be a valid number.")
            else:
                if eta_cstar_design <= 0.0:
                    errors.append("eta_cstar_design must be greater than 0.0.")
                if eta_cstar_design > 1.0:
                    errors.append("eta_cstar_design must not exceed 1.0.")
        if errors:
            raise InputValidationError(errors)
        return float(raw_value.replace(",", "."))

    def set_performance_preview(self, preview_result: PerformancePreviewResult) -> None:
        """Store the last compact Current Design performance preview."""

        previous_result = self._performance_preview_result
        self._changed_performance_preview_keys = self._compute_changed_preview_keys(
            previous_result,
            preview_result,
        )
        self._performance_preview_result = preview_result
        self._refresh_performance_preview_display()

    def clear_performance_preview(self) -> None:
        """Reset the compact Current Design preview when no result is available."""

        self._performance_preview_result = None
        self._changed_performance_preview_keys = set()
        self._refresh_performance_preview_display()

    def set_derived_flow_quantities(
        self,
        total_mass_flow_kg_per_s: float | None,
        mixture_ratio: float | None,
    ) -> None:
        """Show read-only total, fuel and oxidizer mass flows from the current result."""

        self._derived_total_mass_flow_kg_per_s = total_mass_flow_kg_per_s
        self._derived_mixture_ratio = mixture_ratio
        self._refresh_derived_flow_display()

    def clear_derived_flow_quantities(self) -> None:
        """Reset the read-only flow block when no current result is available."""

        self._derived_total_mass_flow_kg_per_s = None
        self._derived_mixture_ratio = None
        self._refresh_derived_flow_display()

    def set_flow_case_assessment(self, assessment: FlowCaseAssessment | None) -> None:
        """Show the current flow-case notice and disable nozzle controls when needed."""

        if assessment is None:
            self._flow_case_notice_var.set("")
            self._set_nozzle_controls_enabled(True)
            return

        if assessment.flow_case is FlowCase.SUBSONIC:
            self._flow_case_notice_var.set(
                "Subsonic / unchoked case detected. Divergent nozzle inputs stay visible for reference "
                "but are disabled until Pc/Pa exceeds the critical ratio."
            )
            self._set_nozzle_controls_enabled(False)
            return

        self._flow_case_notice_var.set(
            "Choked / supersonic case detected. Divergent nozzle inputs remain active."
        )
        self._set_nozzle_controls_enabled(True)

    def set_calculated_expansion_ratios(
        self,
        *,
        current_expansion_ratio: float | None,
        optimal_expansion_ratio: float | None,
    ) -> None:
        """Update the read-only expansion-ratio tracking rows."""

        self._suspend_change_notifications = True
        self._variables["current_expansion_ratio_display"].set(
            "--" if current_expansion_ratio is None else f"{current_expansion_ratio:.4f}"
        )
        self._variables["optimal_expansion_ratio_display"].set(
            "--" if optimal_expansion_ratio is None else f"{optimal_expansion_ratio:.4f}"
        )
        self._suspend_change_notifications = False

    def get_manual_nozzle_length_m(self) -> float | None:
        """Return the optional manual nozzle length without changing the main inputs."""

        errors: list[str] = []
        value = self._parse_optional_float(
            f"Nozzle length L [{get_unit_symbol('length', self._unit_preset)}]",
            "manual_nozzle_length",
            errors,
        )
        if errors:
            raise InputValidationError(errors)
        return convert_from_display(value, "length", self._unit_preset)

    def get_input_parameters(self) -> InputParameters:
        """Read display values and convert them to SI domain inputs."""

        errors: list[str] = []
        fuel = self._variables["fuel"].get().strip()
        oxidizer = self._variables["oxidizer"].get().strip()
        chamber_pressure_value = self._parse_required_float(
            f"Pc [{get_unit_symbol('pressure', self._unit_preset)}]",
            "chamber_pressure",
            errors,
        )
        thrust_value = self._parse_required_float(
            f"Thrust [{get_unit_symbol('force', self._unit_preset)}]",
            "thrust",
            errors,
        )
        mixture_ratio = self._parse_required_float("O/F ratio", "mixture_ratio", errors)
        expansion_ratio = self._parse_required_float("eps", "expansion_ratio", errors)
        ambient_pressure_value = self._parse_required_float(
            f"Pa [{get_unit_symbol('pressure', self._unit_preset)}]",
            "ambient_pressure",
            errors,
        )
        contraction_ratio = self._parse_optional_float("Ac/At", "contraction_ratio", errors)
        characteristic_length_value = self._parse_optional_float(
            f"L* [{get_unit_symbol('length', self._unit_preset)}]",
            "characteristic_length",
            errors,
        )
        manual_nozzle_length_value = self._parse_optional_float(
            f"Nozzle length L [{get_unit_symbol('length', self._unit_preset)}]",
            "manual_nozzle_length",
            errors,
        )

        chemistry_mode_raw = self._variables["chemistry_mode"].get()
        try:
            chemistry_mode = ChemistryMode(chemistry_mode_raw)
        except ValueError:
            errors.append("Chemistry mode is invalid.")
            chemistry_mode = ChemistryMode.EQUILIBRIUM

        contour_family_raw = self._variables["contour_family"].get()
        contour_method = FAMILY_VALUES.get(contour_family_raw)
        if contour_method is None:
            errors.append("Nozzle family is invalid.")
            contour_method = NozzleContourMethod.BELL

        bell_subtype_raw = self._variables["bell_subtype"].get()
        bell_variant = SUBTYPE_VALUES.get(bell_subtype_raw)
        if bell_variant is None:
            errors.append("Bell contour subtype is invalid.")
            bell_variant = BellContourVariant.PARABOLA

        if errors:
            raise InputValidationError(errors)

        return InputParameters(
            fuel=fuel,
            oxidizer=oxidizer,
            chamber_pressure_pa=convert_from_display(chamber_pressure_value, "pressure", self._unit_preset) or 0.0,
            thrust_n=convert_from_display(thrust_value, "force", self._unit_preset) or 0.0,
            mixture_ratio=mixture_ratio,
            expansion_ratio=expansion_ratio,
            ambient_pressure_pa=convert_from_display(ambient_pressure_value, "pressure", self._unit_preset) or 0.0,
            contraction_ratio=contraction_ratio,
            characteristic_length_m=convert_from_display(
                characteristic_length_value,
                "length",
                self._unit_preset,
            ),
            chemistry_mode=chemistry_mode,
            contour_method=contour_method,
            bell_variant=bell_variant,
            manual_nozzle_length_m=convert_from_display(
                manual_nozzle_length_value,
                "length",
                self._unit_preset,
            ),
        )

    def _apply_unit_labels(self) -> None:
        self._field_labels["chamber_pressure"].configure(
            text=f"Pc [{get_unit_symbol('pressure', self._unit_preset)}]"
        )
        self._field_labels["thrust"].configure(
            text=f"Thrust [{get_unit_symbol('force', self._unit_preset)}]"
        )
        self._field_labels["ambient_pressure"].configure(
            text=f"Pa [{get_unit_symbol('pressure', self._unit_preset)}]"
        )
        self._field_labels["characteristic_length"].configure(
            text=f"L* [{get_unit_symbol('length', self._unit_preset)}] optional"
        )
        self._field_labels["manual_nozzle_length"].configure(
            text=f"Nozzle length L [{get_unit_symbol('length', self._unit_preset)}]"
        )
        self._field_labels["total_mass_flow"].configure(
            text=f"Total mass flow [{get_unit_symbol('mass_flow', self._unit_preset)}]"
        )
        self._field_labels["fuel_mass_flow"].configure(
            text=f"Fuel mass flow [{get_unit_symbol('mass_flow', self._unit_preset)}]"
        )
        self._field_labels["oxidizer_mass_flow"].configure(
            text=f"Oxidizer mass flow [{get_unit_symbol('mass_flow', self._unit_preset)}]"
        )

    def _sync_current_expansion_ratio(self, *_args: object) -> None:
        raw_value = self._variables["expansion_ratio"].get().strip()
        self._variables["current_expansion_ratio_display"].set(raw_value or "--")

    def _sync_bell_subtype_visibility(self, *_args: object) -> None:
        is_bell = FAMILY_VALUES.get(self._variables["contour_family"].get()) is NozzleContourMethod.BELL
        for widget in self._bell_subtype_widgets:
            if is_bell:
                widget.grid()
                if isinstance(widget, ttk.Combobox):
                    widget.configure(state="readonly" if self._nozzle_controls_enabled else "disabled")
            else:
                widget.grid_remove()

    def _handle_length_apply(self) -> None:
        if self._length_apply_callback is not None:
            self._length_apply_callback()

    def _handle_combustion_efficiency_changed(self, *_args: object) -> None:
        self._refresh_combustion_efficiency_display()
        self._handle_input_changed()

    def _set_nozzle_controls_enabled(self, enabled: bool) -> None:
        self._nozzle_controls_enabled = enabled
        state = "readonly" if enabled and self._editable else "disabled"
        for widget in self._nozzle_control_widgets:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state=state)
            elif isinstance(widget, ttk.Button):
                widget.configure(state="normal" if enabled and self._editable else "disabled")
            else:
                widget.configure(state="normal" if enabled and self._editable else "disabled")
        self._sync_bell_subtype_visibility()

    def _handle_input_changed(self, *_args: object) -> None:
        if self._suspend_change_notifications:
            return
        if self._input_changed_callback is not None:
            self._input_changed_callback()

    def _refresh_combustion_efficiency_display(self) -> None:
        if not self._show_current_design_features:
            return

        if self._combustion_eta_entry is not None:
            self._combustion_eta_entry.configure(
                state=(
                    "normal"
                    if self._editable and self._use_combustion_efficiency_var.get()
                    else "disabled"
                )
            )

        if not self._use_combustion_efficiency_var.get():
            if self._combustion_loss_label is not None:
                self._combustion_loss_label.configure(style="PreviewValue.TLabel")
            self._combustion_loss_var.set("Assumed combustion loss: 0.0 %")
            self._combustion_warning_var.set("")
            return

        raw_value = self._combustion_eta_var.get().strip()
        if not raw_value:
            if self._combustion_loss_label is not None:
                self._combustion_loss_label.configure(style="Warning.TLabel")
            self._combustion_loss_var.set("Assumed combustion loss: —")
            self._combustion_warning_var.set("Enter eta_cstar_design to use the assumption.")
            return

        try:
            eta_cstar_design = float(raw_value.replace(",", "."))
        except ValueError:
            if self._combustion_loss_label is not None:
                self._combustion_loss_label.configure(style="Warning.TLabel")
            self._combustion_loss_var.set("Assumed combustion loss: —")
            self._combustion_warning_var.set("eta_cstar_design must be a valid number.")
            return

        if self._combustion_loss_label is not None:
            self._combustion_loss_label.configure(
                style=self._style_for_eta_cstar_design(eta_cstar_design)
            )
        if eta_cstar_design > 1.0 or eta_cstar_design <= 0.0:
            self._combustion_loss_var.set("Assumed combustion loss: —")
            self._combustion_warning_var.set("eta_cstar_design must stay in the range (0, 1.0].")
            return

        self._combustion_loss_var.set(
            f"Assumed combustion loss: {(1.0 - eta_cstar_design) * 100.0:.1f} %"
        )
        if eta_cstar_design < 0.90:
            self._combustion_warning_var.set(
                "Warning: eta_cstar_design below 0.90 is unusually low for liquid rocket pre-design."
            )
        else:
            self._combustion_warning_var.set("")

    def _refresh_derived_flow_display(self) -> None:
        total_mass_flow_kg_per_s = self._derived_total_mass_flow_kg_per_s
        mixture_ratio = self._derived_mixture_ratio
        if total_mass_flow_kg_per_s is None or total_mass_flow_kg_per_s <= 0.0:
            self._derived_flow_values["total_mass_flow"].set(self._DERIVED_FLOW_UNAVAILABLE_TEXT)
            self._derived_flow_values["fuel_mass_flow"].set(self._DERIVED_SPLIT_UNAVAILABLE_TEXT)
            self._derived_flow_values["oxidizer_mass_flow"].set(self._DERIVED_SPLIT_UNAVAILABLE_TEXT)
            return

        self._derived_flow_values["total_mass_flow"].set(
            format_quantity(total_mass_flow_kg_per_s, "mass_flow", self._unit_preset)
        )

        if mixture_ratio is None or mixture_ratio < 0.0:
            self._derived_flow_values["fuel_mass_flow"].set(self._DERIVED_SPLIT_UNAVAILABLE_TEXT)
            self._derived_flow_values["oxidizer_mass_flow"].set(self._DERIVED_SPLIT_UNAVAILABLE_TEXT)
            return

        denominator = 1.0 + mixture_ratio
        if denominator <= 0.0:
            self._derived_flow_values["fuel_mass_flow"].set(self._DERIVED_SPLIT_UNAVAILABLE_TEXT)
            self._derived_flow_values["oxidizer_mass_flow"].set(self._DERIVED_SPLIT_UNAVAILABLE_TEXT)
            return

        fuel_mass_flow_kg_per_s = total_mass_flow_kg_per_s / denominator
        oxidizer_mass_flow_kg_per_s = mixture_ratio * total_mass_flow_kg_per_s / denominator
        self._derived_flow_values["fuel_mass_flow"].set(
            format_quantity(fuel_mass_flow_kg_per_s, "mass_flow", self._unit_preset)
        )
        self._derived_flow_values["oxidizer_mass_flow"].set(
            format_quantity(oxidizer_mass_flow_kg_per_s, "mass_flow", self._unit_preset)
        )

    def _refresh_performance_preview_display(self) -> None:
        for key, variable in self._performance_preview_values.items():
            variable.set(self._PREVIEW_UNAVAILABLE_TEXT)
            label = self._performance_preview_value_labels.get(key)
            if label is not None:
                label.configure(style="PreviewValue.TLabel")

        preview_result = self._performance_preview_result
        if preview_result is None:
            return

        self._performance_preview_values["c_star_theoretical"].set(
            self._format_preview_quantity(preview_result.c_star_theoretical_m_s, "velocity")
        )
        self._performance_preview_values["c_star_design"].set(
            self._format_preview_quantity(preview_result.c_star_design_m_s, "velocity")
        )
        self._performance_preview_values["cf_design"].set(
            self._format_preview_dimensionless(preview_result.cf_design, precision=4)
        )
        self._performance_preview_values["isp_vac"].set(
            self._format_preview_quantity(preview_result.isp_vac_s, "isp")
        )
        self._performance_preview_values["isp_sl"].set(
            self._format_preview_quantity(preview_result.isp_sl_s, "isp")
        )
        self._performance_preview_values["mass_flow"].set(
            self._format_preview_quantity(preview_result.mass_flow_kg_per_s, "mass_flow")
        )
        self._performance_preview_values["thrust_estimate"].set(
            self._format_preview_quantity(preview_result.thrust_estimate_n, "force")
        )
        self._performance_preview_values["chamber_pressure"].set(
            self._format_preview_quantity(preview_result.chamber_pressure_pa, "pressure")
        )
        self._performance_preview_values["thrust_deviation"].set(
            self._format_preview_percent(preview_result.thrust_deviation_percent)
        )

        deviation_label = self._performance_preview_value_labels.get("thrust_deviation")
        if deviation_label is not None and preview_result.thrust_deviation_exceeds_threshold:
            deviation_label.configure(style="Warning.TLabel")
        for key in self._changed_performance_preview_keys:
            label = self._performance_preview_value_labels.get(key)
            if label is not None:
                label.configure(style="Error.TLabel")

    def _format_preview_quantity(self, value: float | None, quantity: str) -> str:
        if value is None:
            return self._PREVIEW_UNAVAILABLE_TEXT
        return format_quantity(value, quantity, self._unit_preset)

    def _format_preview_dimensionless(self, value: float | None, *, precision: int) -> str:
        if value is None:
            return self._PREVIEW_UNAVAILABLE_TEXT
        return f"{value:.{precision}f}"

    def _format_preview_percent(self, value: float | None) -> str:
        if value is None:
            return self._PREVIEW_UNAVAILABLE_TEXT
        return f"{value:+.2f} %"

    def _style_for_eta_cstar_design(self, eta_cstar_design: float) -> str:
        band = eta_cstar_band(eta_cstar_design)
        if band == "success":
            return "Success.TLabel"
        if band == "warning":
            return "Warning.TLabel"
        if band == "invalid":
            return "Error.TLabel"
        return "PreviewValue.TLabel"

    def _ensure_styles(self) -> None:
        style = ttk.Style()
        style.configure("PreviewValue.TLabel")
        style.configure("Hint.TLabel", foreground="#4b5b6b")
        style.configure("Success.TLabel", foreground="#2f9d57")
        style.configure("Warning.TLabel", foreground="#b36b00")
        style.configure("Error.TLabel", foreground="#c73a3a")

    def _compute_changed_preview_keys(
        self,
        previous_result: PerformancePreviewResult | None,
        current_result: PerformancePreviewResult,
    ) -> set[str]:
        if previous_result is None:
            return set()

        attribute_map = {
            "thrust_estimate": "thrust_estimate_n",
            "isp_vac": "isp_vac_s",
            "isp_sl": "isp_sl_s",
            "chamber_pressure": "chamber_pressure_pa",
            "mass_flow": "mass_flow_kg_per_s",
            "c_star_theoretical": "c_star_theoretical_m_s",
            "c_star_design": "c_star_design_m_s",
            "cf_design": "cf_design",
            "thrust_deviation": "thrust_deviation_percent",
        }
        changed_keys: set[str] = set()
        for key, attribute_name in attribute_map.items():
            if getattr(previous_result, attribute_name) != getattr(current_result, attribute_name):
                changed_keys.add(key)
        return changed_keys

    def _parse_required_float(self, label: str, key: str, errors: list[str]) -> float:
        raw_value = self._variables[key].get().strip()
        if not raw_value:
            errors.append(f"{label} must not be empty.")
            return 0.0
        try:
            return float(raw_value.replace(",", "."))
        except ValueError:
            errors.append(f"{label} must be a valid number.")
            return 0.0

    def _parse_optional_float(self, label: str, key: str, errors: list[str]) -> float | None:
        raw_value = self._variables[key].get().strip()
        if not raw_value:
            return None
        try:
            return float(raw_value.replace(",", "."))
        except ValueError:
            errors.append(f"{label} must be a valid number when it is provided.")
            return None

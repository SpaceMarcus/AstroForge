"""Tkinter panels for geometry, materials, comparison and summary details."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from engine.flow import FlowCase, FlowCaseAssessment
from engine.models import (
    BellContourVariant,
    ExportBundle,
    InputParameters,
    ManufacturingMode,
    ManufacturingRoute,
    PredictedSeparationPoint,
    ThermochemistryProfilePoint,
    WallThicknessMode,
)
from engine.unit_system import (
    UnitPreset,
    convert_from_display,
    format_quantity,
    get_unit_symbol,
)
from engine.utils.validation import InputValidationError

DEFAULT_LINER_MATERIAL = "CuCrZr"
DEFAULT_COATING = "None"

SUBTYPE_LABELS = {
    BellContourVariant.PARABOLA: "Parabola (TOP)",
    BellContourVariant.TIC: "TIC",
    BellContourVariant.TOC: "TOC",
}
SUBTYPE_VALUES = {label: variant for variant, label in SUBTYPE_LABELS.items()}

MANUFACTURING_MODE_LABELS = {
    ManufacturingMode.TRADITIONAL: "Traditional",
    ManufacturingMode.ADDITIVE: "Additive Manufacturing (future-ready group)",
}
MANUFACTURING_MODE_VALUES = {label: mode for mode, label in MANUFACTURING_MODE_LABELS.items()}

ROUTE_LABELS = {
    ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT: "Milled channels + closeout",
    ManufacturingRoute.TUBE_WALL_BRAZED_TUBE: "Tube-wall / brazed tube",
    ManufacturingRoute.ELECTROFORMED_CLOSEOUT: "Electroformed closeout / electroformed jacket",
    ManufacturingRoute.LPBF: "LPBF / L-PBF",
    ManufacturingRoute.LPDED: "LP-DED / DED",
}
TRADITIONAL_ROUTES = (
    ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT,
    ManufacturingRoute.TUBE_WALL_BRAZED_TUBE,
    ManufacturingRoute.ELECTROFORMED_CLOSEOUT,
)
ADDITIVE_ROUTES = (
    ManufacturingRoute.LPBF,
    ManufacturingRoute.LPDED,
)

# The route-to-material grouping is intentionally simple for the MVP so we can add
# process-specific geometry and DfAM limits later without scattering that logic.
# Planned LPBF hooks: overhang/support logic, self-supporting channel angles, build-volume caps.
# Planned LP-DED hooks: larger feature floors, larger radii, coarse deposition envelopes.
ROUTE_MATERIALS = {
    ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT: ["CuCrZr", "GRCop-42", "Inconel 718", "316L stainless steel"],
    ManufacturingRoute.TUBE_WALL_BRAZED_TUBE: ["CuCrZr", "GRCop-42", "316L stainless steel"],
    ManufacturingRoute.ELECTROFORMED_CLOSEOUT: ["CuCrZr", "Inconel 718", "316L stainless steel"],
    ManufacturingRoute.LPBF: ["Inconel 718", "316L stainless steel", "GRCop-42 (future-ready)"],
    ManufacturingRoute.LPDED: ["Inconel 718", "316L stainless steel", "CuCrZr (future-ready)"],
}

WALL_THICKNESS_MODE_LABELS = {
    WallThicknessMode.CONSTANT: "Constant wall thickness",
    WallThicknessMode.VARIABLE_FUTURE: "Variable wall thickness (future)",
}
WALL_THICKNESS_MODE_VALUES = {
    label: mode for mode, label in WALL_THICKNESS_MODE_LABELS.items()
}


class GeometryMaterialEditorPanel(ttk.LabelFrame):
    """Structured geometry editor used by the Geometry and Material tab."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset = UnitPreset.SI_CAD) -> None:
        super().__init__(master, text="Geometry Editor", padding=12)
        self.columnconfigure(0, weight=1)
        self._unit_preset = unit_preset
        self._nozzle_controls_enabled = True
        self._current_contour_family_label = tk.StringVar(value="not yet set")
        self._current_is_bell = False
        self._flow_case_note_var = tk.StringVar(value="")
        self._field_labels: dict[str, ttk.Label] = {}
        self._bell_subtype_widgets: list[tk.Widget] = []
        self._nozzle_widgets: list[tk.Widget] = []
        self._variables = {
            "bell_subtype": tk.StringVar(value=SUBTYPE_LABELS[BellContourVariant.PARABOLA]),
            "expansion_ratio": tk.StringVar(),
            "manual_nozzle_length": tk.StringVar(),
            "throat_upstream_radius": tk.StringVar(),
            "throat_downstream_radius": tk.StringVar(),
        }
        self._build_widgets()

    def _build_widgets(self) -> None:
        general_frame = ttk.LabelFrame(self, text="General Geometry", padding=10)
        general_frame.grid(row=0, column=0, sticky="ew")
        general_frame.columnconfigure(1, weight=1)

        ttk.Label(general_frame, text="Contour family").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(
            general_frame,
            textvariable=self._current_contour_family_label,
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", pady=4)

        bell_label = ttk.Label(general_frame, text="Bell subtype")
        bell_label.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        bell_box = ttk.Combobox(
            general_frame,
            state="readonly",
            textvariable=self._variables["bell_subtype"],
            values=list(SUBTYPE_VALUES),
        )
        bell_box.grid(row=1, column=1, sticky="ew", pady=4)
        self._bell_subtype_widgets.extend([bell_label, bell_box])
        self._nozzle_widgets.append(bell_box)

        throat_frame = ttk.LabelFrame(self, text="Throat Geometry", padding=10)
        throat_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        throat_frame.columnconfigure(1, weight=1)
        self._field_labels["throat_upstream_radius"] = ttk.Label(throat_frame)
        self._field_labels["throat_upstream_radius"].grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(
            throat_frame,
            textvariable=self._variables["throat_upstream_radius"],
        ).grid(row=0, column=1, sticky="ew", pady=4)
        self._field_labels["throat_downstream_radius"] = ttk.Label(throat_frame)
        self._field_labels["throat_downstream_radius"].grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(
            throat_frame,
            textvariable=self._variables["throat_downstream_radius"],
        ).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(
            throat_frame,
            text=(
                "Upstream and downstream throat blend radii are relevant for all contour families. "
                "They are stored now so later contour-shaping, cooling-channel and curvature rules can use them."
            ),
            wraplength=440,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        nozzle_frame = ttk.LabelFrame(self, text="Nozzle Geometry", padding=10)
        nozzle_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        nozzle_frame.columnconfigure(1, weight=1)
        self._nozzle_frame = nozzle_frame

        self._field_labels["expansion_ratio"] = ttk.Label(nozzle_frame, text="eps = Ae/At [-]")
        self._field_labels["expansion_ratio"].grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        expansion_entry = ttk.Entry(nozzle_frame, textvariable=self._variables["expansion_ratio"])
        expansion_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self._nozzle_widgets.append(expansion_entry)

        self._field_labels["manual_nozzle_length"] = ttk.Label(nozzle_frame)
        self._field_labels["manual_nozzle_length"].grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        manual_entry = ttk.Entry(nozzle_frame, textvariable=self._variables["manual_nozzle_length"])
        manual_entry.grid(row=1, column=1, sticky="ew", pady=4)
        self._nozzle_widgets.append(manual_entry)

        ttk.Label(
            nozzle_frame,
            text=(
                "Bell -> Parabola (TOP) is split into chamber, throat and nozzle sections so we can add "
                "angles, radii and length rules cleanly in the next patch."
            ),
            wraplength=440,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        ttk.Label(
            self,
            textvariable=self._flow_case_note_var,
            wraplength=500,
            justify="left",
            foreground="#7d4d1b",
        ).grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self._apply_unit_labels()
        self._sync_bell_subtype_visibility()

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update displayed units for geometry editor fields."""

        if unit_preset is self._unit_preset:
            return
        self._unit_preset = unit_preset
        self._apply_unit_labels()

    def set_inputs(self, inputs: InputParameters) -> None:
        """Load geometry-related fields from the shared input model."""

        self._current_contour_family_label.set(inputs.contour_method.value.replace("-", " ").title())
        self._current_is_bell = inputs.contour_method.value == "bell"
        self._variables["bell_subtype"].set(SUBTYPE_LABELS[inputs.bell_variant])
        self._variables["expansion_ratio"].set(f"{inputs.expansion_ratio:.4f}")
        self._variables["manual_nozzle_length"].set(
            "" if inputs.manual_nozzle_length_m is None else format_quantity(inputs.manual_nozzle_length_m, "length", self._unit_preset)
        )
        self._variables["throat_upstream_radius"].set(
            ""
            if inputs.throat_upstream_radius_m is None
            else format_quantity(inputs.throat_upstream_radius_m, "length", self._unit_preset)
        )
        self._variables["throat_downstream_radius"].set(
            ""
            if inputs.throat_downstream_radius_m is None
            else format_quantity(inputs.throat_downstream_radius_m, "length", self._unit_preset)
        )
        self._sync_bell_subtype_visibility()

    def set_flow_case_assessment(self, assessment: FlowCaseAssessment | None) -> None:
        """Disable nozzle-edit controls for subsonic / unchoked cases."""

        if assessment is None:
            self._flow_case_note_var.set("")
            self._set_nozzle_controls_enabled(True)
            return
        if assessment.flow_case is FlowCase.SUBSONIC:
            self._flow_case_note_var.set(
                "Subsonic / unchoked case: the nozzle section is disabled because the MVP keeps the geometry throat-only."
            )
            self._set_nozzle_controls_enabled(False)
            return
        self._flow_case_note_var.set(
            "Choked / supersonic case: the nozzle section remains editable."
        )
        self._set_nozzle_controls_enabled(True)

    def get_geometry_updates(self) -> dict[str, object]:
        """Return geometry updates that can be applied back to the shared input model."""

        errors: list[str] = []
        bell_subtype_raw = self._variables["bell_subtype"].get()
        bell_variant = SUBTYPE_VALUES.get(bell_subtype_raw)
        if bell_variant is None:
            errors.append("Geometry bell subtype is invalid.")
            bell_variant = BellContourVariant.PARABOLA

        expansion_ratio = _parse_required_float(
            self._variables["expansion_ratio"].get(),
            "Geometry eps",
            errors,
        )
        manual_nozzle_length = _parse_optional_float(
            self._variables["manual_nozzle_length"].get(),
            "Manual nozzle length",
            errors,
        )
        throat_upstream_radius = _parse_optional_float(
            self._variables["throat_upstream_radius"].get(),
            "Upstream throat radius",
            errors,
        )
        throat_downstream_radius = _parse_optional_float(
            self._variables["throat_downstream_radius"].get(),
            "Downstream throat radius",
            errors,
        )

        if errors:
            raise InputValidationError(errors)

        return {
            "bell_variant": bell_variant,
            "expansion_ratio": expansion_ratio,
            "manual_nozzle_length_m": convert_from_display(manual_nozzle_length, "length", self._unit_preset),
            "throat_upstream_radius_m": convert_from_display(
                throat_upstream_radius, "length", self._unit_preset
            ),
            "throat_downstream_radius_m": convert_from_display(
                throat_downstream_radius, "length", self._unit_preset
            ),
        }

    def _apply_unit_labels(self) -> None:
        self._field_labels["throat_upstream_radius"].configure(
            text=f"Upstream throat radius [{get_unit_symbol('length', self._unit_preset)}]"
        )
        self._field_labels["throat_downstream_radius"].configure(
            text=f"Downstream throat radius [{get_unit_symbol('length', self._unit_preset)}]"
        )
        self._field_labels["manual_nozzle_length"].configure(
            text=f"Manual nozzle length [{get_unit_symbol('length', self._unit_preset)}]"
        )

    def _set_nozzle_controls_enabled(self, enabled: bool) -> None:
        self._nozzle_controls_enabled = enabled
        state = "readonly" if enabled else "disabled"
        for widget in self._nozzle_widgets:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state=state)
            else:
                widget.configure(state="normal" if enabled else "disabled")
        self._sync_bell_subtype_visibility()

    def _sync_bell_subtype_visibility(self, *_args: object) -> None:
        for widget in self._bell_subtype_widgets:
            if self._current_is_bell:
                widget.grid()
                if isinstance(widget, ttk.Combobox):
                    widget.configure(state="readonly" if self._nozzle_controls_enabled else "disabled")
            else:
                widget.grid_remove()


class SummaryPanel(ttk.LabelFrame):
    """Display the notes and local point details shown in the overview tab."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset = UnitPreset.SI_CAD) -> None:
        super().__init__(master, text="Species and Notes", padding=12)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._unit_preset = unit_preset

        self._summary_text = tk.Text(self, height=14, wrap="word", state="disabled")
        self._summary_text.grid(row=0, column=0, sticky="nsew")

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update the display preset used for future summaries."""

        self._unit_preset = unit_preset

    def clear(self) -> None:
        self._set_summary_text("")

    def show_default_summary(self, bundle: ExportBundle) -> None:
        """Show a default summary after a fresh calculation."""

        thermo = bundle.thermochemistry
        has_diverging_section = any(point.region == "diverging" for point in bundle.thermochemistry_profile)
        summary_lines = [
            f"Contour family: {bundle.inputs.contour_method.value}",
            (
                f"Bell subtype: {bundle.inputs.bell_variant.value}"
                if bundle.inputs.contour_method.value == "bell"
                else "Bell subtype: --"
            ),
            f"Active unit preset: {self._unit_preset.value}",
            "RocketCEA provides exact station values for the chamber, throat and exit.",
            "Click a contour plot to inspect local species, transport and wall quantities.",
            "The adiabatic wall temperature and boundary-layer thickness values are approximate.",
            "",
        ]
        if bundle.of_sweep is not None:
            stoich = bundle.of_sweep.stoichiometric_mixture_ratio
            summary_lines.append(
                "O/F sweep ready: "
                + (
                    f"stoichiometric O/F = {stoich:.3f}"
                    if stoich is not None
                    else "stoichiometric O/F unavailable"
                )
            )
            summary_lines.append("")
        if bundle.geometry.notes:
            summary_lines.append("Geometry notes:")
            summary_lines.extend(f"  - {note}" for note in bundle.geometry.notes)
            summary_lines.append("")
        if has_diverging_section:
            summary_lines.append(
                "Markers show throat, exit, optimal expansion and the predicted separation point."
            )
        else:
            summary_lines.append(
                "This case is currently throat-only in the contour view, so exit, optimal-expansion and separation markers stay hidden."
            )
        summary_lines.append("")
        if thermo.species_summary:
            summary_lines.append("Dominant exit mass fractions:")
            for species, fraction in thermo.species_summary.get("exit_mass", {}).items():
                summary_lines.append(f"  {species}: {fraction:.5f}")
            summary_lines.append("")
        if thermo.notes:
            summary_lines.append("Notes:")
            summary_lines.extend(f"  - {note}" for note in thermo.notes)
        self._set_summary_text("\n".join(summary_lines).strip())

    def show_profile_point(
        self,
        profile_point: ThermochemistryProfilePoint,
        bundle: ExportBundle,
    ) -> None:
        """Show local thermochemistry details for the selected contour point."""

        state = profile_point.state
        summary_lines = [
            f"Station index: {profile_point.station_index if profile_point.station_index is not None else '--'}",
            (
                "Selected point: "
                f"x = {format_quantity(profile_point.x_m, 'length', self._unit_preset, include_unit=True)}, "
                f"r = {format_quantity(profile_point.radius_m, 'length', self._unit_preset, include_unit=True)}, "
                f"region = {profile_point.region}"
            ),
            f"Source: {state.source}",
            f"A/At = {_fmt(state.area_ratio, '.4f')}",
            f"T = {format_quantity(state.temperature_k, 'temperature', self._unit_preset, include_unit=True)}",
            f"rho = {format_quantity(state.density_kg_per_m3, 'density', self._unit_preset, include_unit=True)}",
            f"h = {format_quantity(state.enthalpy_j_per_kg, 'specific_energy', self._unit_preset, include_unit=True)}",
            f"cp = {format_quantity(state.cp_j_per_kg_k, 'specific_heat', self._unit_preset, include_unit=True)}",
            f"mu = {format_quantity(state.viscosity_pa_s, 'viscosity', self._unit_preset, include_unit=True)}",
            (
                "k = "
                f"{format_quantity(state.thermal_conductivity_w_per_m_k, 'thermal_conductivity', self._unit_preset, include_unit=True)}"
            ),
            f"Pr = {_fmt(state.prandtl_number, '.4f')}",
            f"gamma = {_fmt(state.gamma, '.4f')}",
            (
                "MW = "
                f"{format_quantity(state.molecular_weight_kg_per_mol, 'molecular_weight', self._unit_preset, include_unit=True)}"
            ),
            f"Mach = {_fmt(state.mach_number, '.4f')}",
            (
                "Velocity = "
                f"{format_quantity(state.velocity_m_per_s, 'velocity', self._unit_preset, include_unit=True)}"
            ),
            f"Re_x = {_fmt(state.reynolds_number, '.4e')}",
            (
                "T_aw = "
                f"{format_quantity(state.adiabatic_wall_temperature_k, 'temperature', self._unit_preset, include_unit=True)}"
            ),
            (
                "Thermal BL thickness = "
                f"{format_quantity(state.thermal_boundary_layer_thickness_m, 'length', self._unit_preset, include_unit=True)}"
            ),
            (
                "Velocity BL thickness = "
                f"{format_quantity(state.velocity_boundary_layer_thickness_m, 'length', self._unit_preset, include_unit=True)}"
            ),
            "",
        ]

        if state.species_mass_fractions:
            summary_lines.append("Local mass fractions:")
            for species, fraction in list(state.species_mass_fractions.items())[:12]:
                summary_lines.append(f"  {species}: {fraction:.6f}")
            summary_lines.append("")

        if state.species_mole_fractions:
            summary_lines.append("Local mole fractions:")
            for species, fraction in list(state.species_mole_fractions.items())[:10]:
                summary_lines.append(f"  {species}: {fraction:.6f}")
            summary_lines.append("")

        if bundle.geometry.notes:
            summary_lines.append("Geometry notes:")
            summary_lines.extend(f"  - {note}" for note in bundle.geometry.notes)
            summary_lines.append("")

        if bundle.thermochemistry.notes:
            summary_lines.append("Notes:")
            summary_lines.extend(f"  - {note}" for note in bundle.thermochemistry.notes)

        self._set_summary_text("\n".join(summary_lines).strip())

    def _set_summary_text(self, text: str) -> None:
        self._summary_text.configure(state="normal")
        self._summary_text.delete("1.0", "end")
        self._summary_text.insert("1.0", text)
        self._summary_text.configure(state="disabled")


class GeometryDetailsPanel(ttk.LabelFrame):
    """Dedicated geometry display for the geometry and overview tabs."""

    _FIELD_DEFINITIONS = [
        ("Contour family", "contour_method", None),
        ("Bell subtype", "bell_variant", None),
        ("Current eps", "current_expansion_ratio", None),
        ("Optimal eps", "optimal_expansion_ratio", None),
        ("Reference conical L", "reference_conical_length_m", "length"),
        ("Current nozzle L", "current_nozzle_length_m", "length"),
        ("At", "throat_area_m2", "area"),
        ("rt", "throat_radius_m", "length"),
        ("Ae", "exit_area_m2", "area"),
        ("re", "exit_radius_m", "length"),
        ("Ac", "chamber_area_m2", "area"),
        ("rc", "chamber_radius_m", "length"),
        ("Vc", "chamber_volume_m3", "volume"),
        ("Chamber length", "chamber_length_m", "length"),
        ("Mass flow", "mass_flow_kg_per_s", "mass_flow"),
        ("Contour length", "contour_length_m", "length"),
    ]

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset = UnitPreset.SI_CAD) -> None:
        super().__init__(master, text="Geometry Summary", padding=12)
        self._unit_preset = unit_preset
        self._last_bundle: ExportBundle | None = None
        self._label_widgets: dict[str, ttk.Label] = {}
        self.variables: dict[str, tk.StringVar] = {}

        for row_index, (label_text, key, quantity) in enumerate(self._FIELD_DEFINITIONS):
            label = ttk.Label(self)
            label.grid(row=row_index, column=0, sticky="w", pady=2)
            self._label_widgets[key] = label
            variable = tk.StringVar(value="--")
            ttk.Label(self, textvariable=variable).grid(row=row_index, column=1, sticky="e", pady=2)
            self.variables[key] = variable
            self._configure_label(key, label_text, quantity)

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update units and rerender the last geometry bundle if available."""

        self._unit_preset = unit_preset
        for label_text, key, quantity in self._FIELD_DEFINITIONS:
            self._configure_label(key, label_text, quantity)
        if self._last_bundle is not None:
            self.update_results(self._last_bundle)

    def clear(self) -> None:
        self._last_bundle = None
        for variable in self.variables.values():
            variable.set("--")

    def update_results(self, bundle: ExportBundle) -> None:
        self._last_bundle = bundle
        geometry = bundle.geometry
        self.variables["contour_method"].set(bundle.inputs.contour_method.value)
        self.variables["bell_variant"].set(
            bundle.inputs.bell_variant.value if bundle.inputs.contour_method.value == "bell" else "--"
        )
        self.variables["current_expansion_ratio"].set(_fmt(geometry.current_expansion_ratio, ".4f"))
        self.variables["optimal_expansion_ratio"].set(_fmt(geometry.optimal_expansion_ratio, ".4f"))
        self.variables["reference_conical_length_m"].set(
            format_quantity(geometry.reference_conical_length_m, "length", self._unit_preset)
        )
        self.variables["current_nozzle_length_m"].set(
            format_quantity(geometry.current_nozzle_length_m, "length", self._unit_preset)
        )
        self.variables["throat_area_m2"].set(format_quantity(geometry.throat_area_m2, "area", self._unit_preset))
        self.variables["throat_radius_m"].set(format_quantity(geometry.throat_radius_m, "length", self._unit_preset))
        self.variables["exit_area_m2"].set(format_quantity(geometry.exit_area_m2, "area", self._unit_preset))
        self.variables["exit_radius_m"].set(format_quantity(geometry.exit_radius_m, "length", self._unit_preset))
        self.variables["chamber_area_m2"].set(format_quantity(geometry.chamber_area_m2, "area", self._unit_preset))
        self.variables["chamber_radius_m"].set(
            format_quantity(geometry.chamber_radius_m, "length", self._unit_preset)
        )
        self.variables["chamber_volume_m3"].set(
            format_quantity(geometry.chamber_volume_m3, "volume", self._unit_preset)
        )
        self.variables["chamber_length_m"].set(
            format_quantity(geometry.chamber_length_m, "length", self._unit_preset)
        )
        self.variables["mass_flow_kg_per_s"].set(
            format_quantity(geometry.mass_flow_kg_per_s, "mass_flow", self._unit_preset)
        )
        self.variables["contour_length_m"].set(
            format_quantity(geometry.contour_length_m, "length", self._unit_preset)
        )

    def _configure_label(self, key: str, label_text: str, quantity: str | None) -> None:
        label = self._label_widgets[key]
        if quantity is None:
            if "eps" in label_text:
                label.configure(text=f"{label_text} [-]")
            else:
                label.configure(text=label_text)
            return
        label.configure(text=f"{label_text} [{get_unit_symbol(quantity, self._unit_preset)}]")


class MaterialOptionsPanel(ttk.LabelFrame):
    """Material and manufacturing editor prepared for future process-specific rules."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset = UnitPreset.SI_CAD) -> None:
        super().__init__(master, text="Manufacturing and Materials", padding=12)
        self.columnconfigure(0, weight=1)
        self._change_callback: Callable[[], None] | None = None
        self._suspend_notifications = False
        self._unit_preset = unit_preset
        self._field_labels: dict[str, ttk.Label] = {}
        self._manufacturing_mode = tk.StringVar(value=MANUFACTURING_MODE_LABELS[ManufacturingMode.TRADITIONAL])
        self._manufacturing_route = tk.StringVar(value=ROUTE_LABELS[ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT])
        self._liner_material = tk.StringVar(value=DEFAULT_LINER_MATERIAL)
        self._coating_enabled = tk.BooleanVar(value=False)
        self._coating = tk.StringVar(value=DEFAULT_COATING)
        self._wall_thickness_mode = tk.StringVar(
            value=WALL_THICKNESS_MODE_LABELS[WallThicknessMode.CONSTANT]
        )
        self._wall_thickness = tk.StringVar(value="1.500")
        self._note_var = tk.StringVar(value="")
        self._route_box: ttk.Combobox | None = None
        self._material_box: ttk.Combobox | None = None
        self._wall_entry: ttk.Entry | None = None
        self._manufacturing_mode.trace_add("write", self._handle_mode_changed)
        self._manufacturing_route.trace_add("write", self._handle_route_changed)
        self._liner_material.trace_add("write", self._handle_changed)
        self._coating_enabled.trace_add("write", self._handle_changed)
        self._coating.trace_add("write", self._handle_changed)
        self._wall_thickness_mode.trace_add("write", self._handle_wall_mode_changed)
        self._wall_thickness.trace_add("write", self._handle_changed)
        self._build_widgets()
        self._sync_route_values()
        self._sync_material_values()
        self._sync_wall_mode()

    def _build_widgets(self) -> None:
        manufacturing_frame = ttk.LabelFrame(self, text="Manufacturing Mode", padding=10)
        manufacturing_frame.grid(row=0, column=0, sticky="ew")
        manufacturing_frame.columnconfigure(1, weight=1)

        ttk.Label(manufacturing_frame, text="Mode").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Combobox(
            manufacturing_frame,
            state="readonly",
            textvariable=self._manufacturing_mode,
            values=list(MANUFACTURING_MODE_VALUES),
        ).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(manufacturing_frame, text="Route").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        route_box = ttk.Combobox(
            manufacturing_frame,
            state="readonly",
            textvariable=self._manufacturing_route,
        )
        route_box.grid(row=1, column=1, sticky="ew", pady=4)
        self._route_box = route_box

        ttk.Label(
            manufacturing_frame,
            textvariable=self._note_var,
            wraplength=420,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        materials_frame = ttk.LabelFrame(self, text="Materials", padding=10)
        materials_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        materials_frame.columnconfigure(1, weight=1)

        ttk.Label(materials_frame, text="Liner material").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        material_box = ttk.Combobox(
            materials_frame,
            state="readonly",
            textvariable=self._liner_material,
        )
        material_box.grid(row=0, column=1, sticky="ew", pady=4)
        self._material_box = material_box

        ttk.Label(materials_frame, text="Coating enabled").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Checkbutton(materials_frame, variable=self._coating_enabled).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(materials_frame, text="Liner coating").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Combobox(
            materials_frame,
            state="readonly",
            textvariable=self._coating,
            values=["None", "NiCr bond coat", "Ceramic TBC", "Refractory washcoat"],
        ).grid(row=2, column=1, sticky="ew", pady=4)

        wall_frame = ttk.LabelFrame(self, text="Hot-Gas / Coolant Separating Wall", padding=10)
        wall_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        wall_frame.columnconfigure(1, weight=1)

        ttk.Label(wall_frame, text="Wall model").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Combobox(
            wall_frame,
            state="readonly",
            textvariable=self._wall_thickness_mode,
            values=list(WALL_THICKNESS_MODE_VALUES),
        ).grid(row=0, column=1, sticky="ew", pady=4)

        wall_label = ttk.Label(wall_frame)
        wall_label.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        self._field_labels["wall_thickness"] = wall_label
        wall_entry = ttk.Entry(wall_frame, textvariable=self._wall_thickness)
        wall_entry.grid(row=1, column=1, sticky="ew", pady=4)
        self._wall_entry = wall_entry

        ttk.Label(
            wall_frame,
            text=(
                "The wall thickness here refers specifically to the hot-gas-to-coolant separating wall. "
                "Variable wall thickness is structurally prepared but not yet solved in detail."
            ),
            wraplength=420,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        self._apply_unit_labels()

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update displayed wall-thickness units."""

        if unit_preset is self._unit_preset:
            return
        self._unit_preset = unit_preset
        self._apply_unit_labels()

    def reset_defaults(self) -> None:
        self._suspend_notifications = True
        self._manufacturing_mode.set(MANUFACTURING_MODE_LABELS[ManufacturingMode.TRADITIONAL])
        self._sync_route_values()
        self._manufacturing_route.set(ROUTE_LABELS[ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT])
        self._sync_material_values()
        self._liner_material.set(DEFAULT_LINER_MATERIAL)
        self._coating_enabled.set(False)
        self._coating.set(DEFAULT_COATING)
        self._wall_thickness_mode.set(WALL_THICKNESS_MODE_LABELS[WallThicknessMode.CONSTANT])
        self._wall_thickness.set("1.500")
        self._suspend_notifications = False
        self._sync_wall_mode()

    def set_inputs(self, inputs: InputParameters) -> None:
        """Populate the material/manufacturing controls from the shared input model."""

        self._suspend_notifications = True
        self._manufacturing_mode.set(MANUFACTURING_MODE_LABELS[inputs.manufacturing_mode])
        self._sync_route_values()
        self._manufacturing_route.set(ROUTE_LABELS[inputs.manufacturing_route])
        self._sync_material_values()
        self._liner_material.set(inputs.liner_material or DEFAULT_LINER_MATERIAL)
        self._coating_enabled.set(bool(inputs.liner_coating_enabled))
        self._coating.set(inputs.liner_coating or DEFAULT_COATING)
        self._wall_thickness_mode.set(WALL_THICKNESS_MODE_LABELS[inputs.wall_thickness_mode])
        self._wall_thickness.set(
            ""
            if inputs.wall_thickness_m is None
            else format_quantity(inputs.wall_thickness_m, "length", self._unit_preset)
        )
        self._suspend_notifications = False
        self._sync_wall_mode()

    def bind_inputs_changed(self, callback: Callable[[], None]) -> None:
        """Bind a callback fired when the draft material editor changes."""

        self._change_callback = callback

    def get_material_updates(self) -> dict[str, object]:
        """Return material/manufacturing updates to apply to the shared input model."""

        errors: list[str] = []
        manufacturing_mode = MANUFACTURING_MODE_VALUES.get(self._manufacturing_mode.get())
        if manufacturing_mode is None:
            errors.append("Manufacturing mode is invalid.")
            manufacturing_mode = ManufacturingMode.TRADITIONAL

        route = _route_from_label(self._manufacturing_route.get())
        if route is None:
            errors.append("Manufacturing route is invalid.")
            route = ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT

        wall_mode = WALL_THICKNESS_MODE_VALUES.get(self._wall_thickness_mode.get())
        if wall_mode is None:
            errors.append("Wall-thickness mode is invalid.")
            wall_mode = WallThicknessMode.CONSTANT

        wall_thickness = _parse_optional_float(
            self._wall_thickness.get(),
            "Hot-gas wall thickness",
            errors,
        )
        if wall_mode is WallThicknessMode.CONSTANT and wall_thickness is None:
            errors.append("Constant wall thickness requires a numeric value.")
        if errors:
            raise InputValidationError(errors)

        coating = self._coating.get().strip() or DEFAULT_COATING
        return {
            "manufacturing_mode": manufacturing_mode,
            "manufacturing_route": route,
            "liner_material": self._liner_material.get().strip() or DEFAULT_LINER_MATERIAL,
            "liner_coating_enabled": self._coating_enabled.get() and coating != DEFAULT_COATING,
            "liner_coating": None if not self._coating_enabled.get() or coating == DEFAULT_COATING else coating,
            "wall_thickness_mode": wall_mode,
            "wall_thickness_m": convert_from_display(wall_thickness, "length", self._unit_preset),
        }

    def _apply_unit_labels(self) -> None:
        self._field_labels["wall_thickness"].configure(
            text=f"Wall thickness [{get_unit_symbol('length', self._unit_preset)}]"
        )

    def _handle_mode_changed(self, *_args: object) -> None:
        if self._suspend_notifications:
            return
        self._sync_route_values()
        self._sync_material_values()
        self._update_note()
        self._handle_changed()

    def _handle_route_changed(self, *_args: object) -> None:
        if self._suspend_notifications:
            return
        self._sync_material_values()
        self._update_note()
        self._handle_changed()

    def _handle_wall_mode_changed(self, *_args: object) -> None:
        if self._suspend_notifications:
            return
        self._sync_wall_mode()
        self._handle_changed()

    def _sync_route_values(self) -> None:
        if self._route_box is None:
            return
        mode = MANUFACTURING_MODE_VALUES.get(self._manufacturing_mode.get(), ManufacturingMode.TRADITIONAL)
        routes = TRADITIONAL_ROUTES if mode is ManufacturingMode.TRADITIONAL else ADDITIVE_ROUTES
        labels = [ROUTE_LABELS[route] for route in routes]
        self._route_box.configure(values=labels)
        if self._manufacturing_route.get() not in labels:
            self._manufacturing_route.set(labels[0])
        self._update_note()

    def _sync_material_values(self) -> None:
        if self._material_box is None:
            return
        route = _route_from_label(self._manufacturing_route.get()) or ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT
        materials = ROUTE_MATERIALS[route]
        self._material_box.configure(values=materials)
        if self._liner_material.get() not in materials:
            self._liner_material.set(materials[0])

    def _sync_wall_mode(self) -> None:
        if self._wall_entry is None:
            return
        mode = WALL_THICKNESS_MODE_VALUES.get(
            self._wall_thickness_mode.get(),
            WallThicknessMode.CONSTANT,
        )
        self._wall_entry.configure(state="normal" if mode is WallThicknessMode.CONSTANT else "disabled")

    def _update_note(self) -> None:
        mode = MANUFACTURING_MODE_VALUES.get(self._manufacturing_mode.get(), ManufacturingMode.TRADITIONAL)
        route = _route_from_label(self._manufacturing_route.get())
        if mode is ManufacturingMode.TRADITIONAL:
            self._note_var.set(
                "Traditional routes are active in this MVP and already filter the material list to familiar liner/wall choices."
            )
            return
        if route is ManufacturingRoute.LPBF:
            self._note_var.set(
                "LPBF is future-ready here: material filtering is prepared, but overhang, support and self-supporting channel limits are not enforced yet."
            )
            return
        self._note_var.set(
            "LP-DED is future-ready here: larger-feature process logic and large-scale deposition envelopes are prepared conceptually, but not solved yet."
        )

    def _handle_changed(self, *_args: object) -> None:
        if self._suspend_notifications:
            return
        if self._change_callback is not None:
            self._change_callback()


class ComparisonPanel(ttk.LabelFrame):
    """Prepared comparison table for reference, best-known and current contours."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset = UnitPreset.SI_CAD) -> None:
        super().__init__(master, text="Comparison", padding=12)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._unit_preset = unit_preset
        self._last_bundle: ExportBundle | None = None
        self._last_separation_point: PredictedSeparationPoint | None = None
        self._tree = ttk.Treeview(
            self,
            columns=(
                "contour",
                "eps",
                "length",
                "l_ratio",
                "rt",
                "re",
                "isp",
                "cf",
                "separation",
            ),
            show="tree headings",
            height=8,
        )
        self._configure_headings()
        self._tree.column("#0", width=140, stretch=False)
        self._tree.column("contour", width=110, stretch=False)
        self._tree.column("eps", width=70, stretch=False)
        self._tree.column("length", width=90, stretch=False)
        self._tree.column("l_ratio", width=70, stretch=False)
        self._tree.column("rt", width=78, stretch=False)
        self._tree.column("re", width=78, stretch=False)
        self._tree.column("isp", width=90, stretch=False)
        self._tree.column("cf", width=70, stretch=False)
        self._tree.column("separation", width=240, stretch=True)
        self._tree.grid(row=0, column=0, sticky="nsew")

        self._note_var = tk.StringVar(
            value="Run a calculation to populate the comparison baseline."
        )
        ttk.Label(
            self,
            textvariable=self._note_var,
            wraplength=860,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(10, 0))

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update unit headings and rerender the last comparison state."""

        self._unit_preset = unit_preset
        self._configure_headings()
        if self._last_bundle is not None:
            self.update_results(self._last_bundle, self._last_separation_point)

    def clear(self) -> None:
        self._last_bundle = None
        self._last_separation_point = None
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._note_var.set("Run a calculation to populate the comparison baseline.")

    def update_results(
        self,
        bundle: ExportBundle,
        separation_point: PredictedSeparationPoint | None,
    ) -> None:
        self._last_bundle = bundle
        self._last_separation_point = separation_point
        for item in self._tree.get_children():
            self._tree.delete(item)

        geometry = bundle.geometry
        thermo = bundle.thermochemistry
        reference_length = geometry.reference_conical_length_m
        current_length = geometry.current_nozzle_length_m
        length_ratio = (
            None
            if reference_length in {None, 0.0} or current_length is None
            else current_length / reference_length
        )
        separation_text = "no separation predicted"
        if current_length in {None, 0.0}:
            separation_text = "subsonic / throat-only case"
        elif separation_point is not None:
            separation_text = (
                f"predicted at x={format_quantity(separation_point.x_m, 'length', self._unit_preset, include_unit=True)} "
                f"(A/At={separation_point.area_ratio:.2f})"
            )

        rows = [
            (
                "Reference conical",
                (
                    "conical",
                    _fmt(geometry.current_expansion_ratio, ".3f"),
                    format_quantity(reference_length, "length", self._unit_preset),
                    "1.0000",
                    format_quantity(geometry.throat_radius_m, "length", self._unit_preset),
                    format_quantity(geometry.exit_radius_m, "length", self._unit_preset),
                    format_quantity(thermo.isp_vac_s, "isp", self._unit_preset),
                    _fmt(thermo.cf_vac, ".4f"),
                    "same operating point baseline",
                ),
            ),
            (
                "Best variant yet",
                (
                    bundle.inputs.contour_method.value,
                    _fmt(geometry.current_expansion_ratio, ".3f"),
                    format_quantity(current_length, "length", self._unit_preset),
                    _fmt(length_ratio, ".4f"),
                    format_quantity(geometry.throat_radius_m, "length", self._unit_preset),
                    format_quantity(geometry.exit_radius_m, "length", self._unit_preset),
                    format_quantity(thermo.isp_vac_s, "isp", self._unit_preset),
                    _fmt(thermo.cf_vac, ".4f"),
                    "current design baseline; no multi-variant search yet",
                ),
            ),
            (
                "Current nozzle",
                (
                    (
                        f"{bundle.inputs.contour_method.value}/{bundle.inputs.bell_variant.value}"
                        if bundle.inputs.contour_method.value == "bell"
                        else bundle.inputs.contour_method.value
                    ),
                    _fmt(geometry.current_expansion_ratio, ".3f"),
                    format_quantity(current_length, "length", self._unit_preset),
                    _fmt(length_ratio, ".4f"),
                    format_quantity(geometry.throat_radius_m, "length", self._unit_preset),
                    format_quantity(geometry.exit_radius_m, "length", self._unit_preset),
                    format_quantity(thermo.isp_vac_s, "isp", self._unit_preset),
                    _fmt(thermo.cf_vac, ".4f"),
                    separation_text,
                ),
            ),
        ]

        for role, values in rows:
            self._tree.insert("", "end", text=role, values=values)

        self._note_var.set(
            "Comparison currently uses the same RocketCEA operating point across rows. "
            "Mass, TWR, surface-area and material-weight proxies are prepared for later additions."
        )

    def _configure_headings(self) -> None:
        self._tree.heading("#0", text="Role")
        self._tree.heading("contour", text="Contour")
        self._tree.heading("eps", text="Ae/At")
        self._tree.heading("length", text=f"Length [{get_unit_symbol('length', self._unit_preset)}]")
        self._tree.heading("l_ratio", text="L/Lcon")
        self._tree.heading("rt", text=f"rt [{get_unit_symbol('length', self._unit_preset)}]")
        self._tree.heading("re", text=f"re [{get_unit_symbol('length', self._unit_preset)}]")
        self._tree.heading("isp", text=f"Isp_vac [{get_unit_symbol('isp', self._unit_preset)}]")
        self._tree.heading("cf", text="Cf_vac")
        self._tree.heading("separation", text="Separation")


def _fmt(value: float | None, pattern: str) -> str:
    if value is None:
        return "--"
    return format(value, pattern)


def _route_from_label(label: str) -> ManufacturingRoute | None:
    for route, route_label in ROUTE_LABELS.items():
        if route_label == label:
            return route
    return None


def _parse_required_float(raw_value: str, label: str, errors: list[str]) -> float:
    cleaned = raw_value.strip().replace(",", ".")
    if not cleaned:
        errors.append(f"{label} must not be empty.")
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        errors.append(f"{label} must be a valid number.")
        return 0.0


def _parse_optional_float(raw_value: str, label: str, errors: list[str]) -> float | None:
    cleaned = raw_value.strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        errors.append(f"{label} must be a valid number when it is provided.")
        return None

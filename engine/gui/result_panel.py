"""Tkinter panels for geometry, materials, comparison and summary details."""

from __future__ import annotations

import math
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
    NozzleContourMethod,
    PredictedSeparationPoint,
    ThermochemistryProfilePoint,
    WallThicknessMode,
)
from engine.nozzle_geometry import compute_divergence_efficiency
from engine.nozzle_preview import build_nozzle_preview
from engine.unit_system import (
    UnitPreset,
    convert_from_display,
    convert_to_display,
    format_quantity,
    get_unit_symbol,
)
from engine.utils.validation import InputValidationError

DEFAULT_LINER_MATERIAL = "CuCrZr"
DEFAULT_COATING = "None"
DEFAULT_CLOSEOUT_THICKNESS_M = 0.003
CLOSEOUT_MATERIAL_OPTIONS = ["GRCop-42", "Inconel 718", "CuCrZr", "316 Stainless Steel"]

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


def _route_supports_closeout(route: ManufacturingRoute) -> bool:
    return route in {
        ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT,
        ManufacturingRoute.ELECTROFORMED_CLOSEOUT,
    }


def _normalize_closeout_material(material: str | None, *, fallback: str) -> str:
    candidate = (material or fallback or DEFAULT_LINER_MATERIAL).strip()
    normalized = candidate.lower()
    if normalized in {"316l stainless steel", "316l", "316"}:
        return "316 Stainless Steel"
    if candidate in CLOSEOUT_MATERIAL_OPTIONS:
        return candidate
    return fallback if fallback in CLOSEOUT_MATERIAL_OPTIONS else candidate


class GeometryMaterialEditorPanel(ttk.LabelFrame):
    """Structured geometry editor used by the Geometry and Material tab."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset = UnitPreset.SI_CAD) -> None:
        super().__init__(master, text="Nozzle Section", padding=12)
        self.columnconfigure(0, weight=1)
        self._unit_preset = unit_preset
        self._nozzle_controls_enabled = True
        self._suspend_notifications = False
        self._change_callback: Callable[[], None] | None = None
        self._apply_divergent_loss_callback: Callable[[], None] | None = None
        self._current_contour_family_label = tk.StringVar(value="not yet set")
        self._current_is_bell = False
        self._runtime_inputs: InputParameters | None = None
        self._runtime_bundle: ExportBundle | None = None
        self._preview_error_message = ""
        self._flow_case_note_var = tk.StringVar(value="")
        self._nozzle_calculation_var = tk.StringVar(value="No nozzle draft loaded yet.")
        self._divergent_loss_var = tk.StringVar(value="Divergent loss: not available yet.")
        self._inflow_angle_var = tk.StringVar(
            value="Bell start angle guidance will appear here once a valid TOP draft is available."
        )
        self._outflow_angle_var = tk.StringVar(
            value="Exit-angle guidance will appear here once a valid TOP draft is available."
        )
        self._field_labels: dict[str, ttk.Label] = {}
        self._bell_subtype_widgets: list[tk.Widget] = []
        self._nozzle_widgets: list[tk.Widget] = []
        self._preview_canvas: tk.Canvas | None = None
        self._apply_divergent_loss_button: ttk.Button | None = None
        self._runtime_default_expansion_ratio: float | None = None
        self._variables = {
            "bell_subtype": tk.StringVar(value=SUBTYPE_LABELS[BellContourVariant.PARABOLA]),
            "expansion_ratio": tk.StringVar(),
            "length_fraction_percent": tk.StringVar(),
            "manual_nozzle_length": tk.StringVar(),
        }
        for variable in self._variables.values():
            variable.trace_add("write", self._handle_changed)
        self._build_widgets()

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        nozzle_frame = ttk.LabelFrame(self, text="Nozzle Geometry", padding=10)
        nozzle_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        nozzle_frame.columnconfigure(1, weight=1)
        self._nozzle_frame = nozzle_frame

        ttk.Label(nozzle_frame, text="Current contour family").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(
            nozzle_frame,
            textvariable=self._current_contour_family_label,
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", pady=4)

        bell_label = ttk.Label(nozzle_frame, text="Bell subtype")
        bell_label.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        bell_box = ttk.Combobox(
            nozzle_frame,
            state="readonly",
            textvariable=self._variables["bell_subtype"],
            values=list(SUBTYPE_VALUES),
        )
        bell_box.grid(row=1, column=1, sticky="ew", pady=4)
        self._bell_subtype_widgets.extend([bell_label, bell_box])
        self._nozzle_widgets.append(bell_box)

        self._field_labels["expansion_ratio"] = ttk.Label(nozzle_frame, text="eps = Ae/At [-]")
        self._field_labels["expansion_ratio"].grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        expansion_entry = ttk.Entry(nozzle_frame, textvariable=self._variables["expansion_ratio"])
        expansion_entry.grid(row=2, column=1, sticky="ew", pady=4)
        self._nozzle_widgets.append(expansion_entry)

        ttk.Label(nozzle_frame, text="Bell length Lf [%]").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        length_fraction_entry = ttk.Entry(nozzle_frame, textvariable=self._variables["length_fraction_percent"])
        length_fraction_entry.grid(row=3, column=1, sticky="ew", pady=4)
        self._nozzle_widgets.append(length_fraction_entry)

        self._field_labels["manual_nozzle_length"] = ttk.Label(nozzle_frame)
        self._field_labels["manual_nozzle_length"].grid(row=4, column=0, sticky="w", padx=(0, 10), pady=4)
        manual_entry = ttk.Entry(nozzle_frame, textvariable=self._variables["manual_nozzle_length"])
        manual_entry.grid(row=4, column=1, sticky="ew", pady=4)
        self._nozzle_widgets.append(manual_entry)

        ttk.Label(
            nozzle_frame,
            text=(
                "Use either a manual nozzle length or a bell-length fraction Lf here. "
                "Parabola (TOP) is the active nozzle path. TIC and TOC remain future work."
            ),
            wraplength=440,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        inflow_frame = ttk.LabelFrame(self, text="Bell start angle θ_n", padding=10)
        inflow_frame.grid(row=0, column=1, sticky="nsew")
        inflow_frame.columnconfigure(0, weight=1)
        ttk.Label(
            inflow_frame,
            textvariable=self._inflow_angle_var,
            wraplength=260,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

        calculation_frame = ttk.LabelFrame(self, text="Nozzle Calculation", padding=10)
        calculation_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 12), pady=(12, 0))
        calculation_frame.columnconfigure(0, weight=1)
        ttk.Label(
            calculation_frame,
            textvariable=self._nozzle_calculation_var,
            wraplength=320,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            calculation_frame,
            textvariable=self._divergent_loss_var,
            wraplength=320,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._apply_divergent_loss_button = ttk.Button(
            calculation_frame,
            text="Apply Divergent Loss",
            command=self._apply_divergent_loss,
            width=20,
        )
        self._apply_divergent_loss_button.grid(row=2, column=0, sticky="w", pady=(10, 0))

        outflow_frame = ttk.LabelFrame(self, text="Exit angle θ_e", padding=10)
        outflow_frame.grid(row=1, column=1, sticky="nsew", pady=(12, 0))
        outflow_frame.columnconfigure(0, weight=1)
        ttk.Label(
            outflow_frame,
            textvariable=self._outflow_angle_var,
            wraplength=260,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

        preview_frame = ttk.LabelFrame(self, text="Nozzle Preview", padding=10)
        preview_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        preview_frame.columnconfigure(0, weight=1)
        preview_canvas = tk.Canvas(preview_frame, height=150, background="#f7f8fb", highlightthickness=0)
        preview_canvas.grid(row=0, column=0, sticky="ew")
        preview_canvas.bind("<Configure>", self._handle_preview_resize)
        self._preview_canvas = preview_canvas

        ttk.Label(
            self,
            textvariable=self._flow_case_note_var,
            wraplength=500,
            justify="left",
            foreground="#7d4d1b",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self._apply_unit_labels()
        self._sync_bell_subtype_visibility()
        self._refresh_tile_text()
        self._refresh_preview()

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update displayed units for geometry editor fields."""

        if unit_preset is self._unit_preset:
            return
        self._unit_preset = unit_preset
        self._apply_unit_labels()

    def set_inputs(
        self,
        inputs: InputParameters,
        *,
        current_bundle: ExportBundle | None = None,
    ) -> None:
        """Load geometry-related fields from the shared input model."""

        self._suspend_notifications = True
        self._runtime_inputs = inputs
        self._runtime_bundle = current_bundle
        self._current_contour_family_label.set(inputs.contour_method.value.replace("-", " ").title())
        self._current_is_bell = inputs.contour_method.value == "bell"
        self._variables["bell_subtype"].set(SUBTYPE_LABELS[inputs.bell_variant])
        if current_bundle is not None and current_bundle.geometry.current_expansion_ratio is not None:
            default_expansion_ratio = current_bundle.geometry.current_expansion_ratio
        else:
            default_expansion_ratio = inputs.expansion_ratio
        self._runtime_default_expansion_ratio = default_expansion_ratio
        self._variables["expansion_ratio"].set(f"{default_expansion_ratio:.4f}")
        self._variables["length_fraction_percent"].set(
            ""
            if current_bundle is None or current_bundle.geometry.top_nozzle_length_fraction_percent is None
            else f"{current_bundle.geometry.top_nozzle_length_fraction_percent:.1f}"
        )
        self._variables["manual_nozzle_length"].set(
            "" if inputs.manual_nozzle_length_m is None else format_quantity(inputs.manual_nozzle_length_m, "length", self._unit_preset)
        )
        self._suspend_notifications = False
        self._sync_bell_subtype_visibility()
        self._refresh_tile_text()
        self._refresh_preview()

    def set_runtime_context(
        self,
        inputs: InputParameters | None,
        *,
        current_bundle: ExportBundle | None = None,
    ) -> None:
        """Update preview context without overwriting draft edits."""

        self._runtime_inputs = inputs
        self._runtime_bundle = current_bundle
        if inputs is not None:
            if current_bundle is not None and current_bundle.geometry.current_expansion_ratio is not None:
                runtime_default_expansion_ratio = current_bundle.geometry.current_expansion_ratio
            else:
                runtime_default_expansion_ratio = inputs.expansion_ratio
            try:
                current_expansion_ratio = float(self._variables["expansion_ratio"].get().strip().replace(",", "."))
            except ValueError:
                current_expansion_ratio = None
            if (
                current_expansion_ratio is None
                or self._runtime_default_expansion_ratio is None
                or math.isclose(
                    current_expansion_ratio,
                    self._runtime_default_expansion_ratio,
                    rel_tol=1.0e-9,
                    abs_tol=1.0e-6,
                )
            ):
                self._suspend_notifications = True
                self._runtime_default_expansion_ratio = runtime_default_expansion_ratio
                self._variables["expansion_ratio"].set(f"{runtime_default_expansion_ratio:.4f}")
                self._suspend_notifications = False
        self._refresh_tile_text()
        self._refresh_preview()

    def get_preview_commit_metadata(self) -> dict[str, object]:
        """Return preview-only metadata that can be committed alongside nozzle inputs."""

        preview = self._build_preview_model()
        if preview is None:
            return {}
        # The preview already resolves the active exit angle and bell length, so we reuse
        # that nozzle-only snapshot when committing divergent-loss assumptions.
        divergent_loss_factor = compute_divergence_efficiency(preview.outflow_angle_deg)
        return {
            "divergent_loss_factor": divergent_loss_factor,
            "divergent_loss_percent": None
            if divergent_loss_factor is None
            else (1.0 - divergent_loss_factor) * 100.0,
            "nozzle_angle_source": preview.angle_source,
            "resolved_nozzle_length_m": preview.length_m,
            "resolved_length_fraction_percent": preview.length_fraction_percent,
        }

    def bind_inputs_changed(self, callback: Callable[[], None]) -> None:
        """Bind a callback fired when draft nozzle values change."""

        self._change_callback = callback

    def bind_apply_divergent_loss(self, callback: Callable[[], None]) -> None:
        """Bind a callback that commits the preview divergent loss to Current Design."""

        self._apply_divergent_loss_callback = callback

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
        length_fraction_percent = _parse_optional_float(
            self._variables["length_fraction_percent"].get(),
            "Bell length Lf",
            errors,
        )
        manual_nozzle_length = _parse_optional_float(
            self._variables["manual_nozzle_length"].get(),
            "Manual nozzle length",
            errors,
        )

        if errors:
            raise InputValidationError(errors)

        resolved_manual_length_m = convert_from_display(manual_nozzle_length, "length", self._unit_preset)
        if resolved_manual_length_m is None and length_fraction_percent is not None:
            preview = self._build_preview_model()
            if preview is None:
                raise InputValidationError(
                    ["Bell-length fraction could not be resolved into a nozzle length for the current preview."]
                )
            resolved_manual_length_m = preview.length_m

        return {
            "bell_variant": bell_variant,
            "expansion_ratio": expansion_ratio,
            "manual_nozzle_length_m": resolved_manual_length_m,
        }

    def _apply_unit_labels(self) -> None:
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
        if self._apply_divergent_loss_button is not None and not enabled:
            self._apply_divergent_loss_button.configure(state="disabled")
        self._sync_bell_subtype_visibility()

    def _sync_bell_subtype_visibility(self, *_args: object) -> None:
        for widget in self._bell_subtype_widgets:
            if self._current_is_bell:
                widget.grid()
                if isinstance(widget, ttk.Combobox):
                    widget.configure(state="readonly" if self._nozzle_controls_enabled else "disabled")
            else:
                widget.grid_remove()

    def _handle_changed(self, *_args: object) -> None:
        if self._suspend_notifications:
            return
        self._refresh_tile_text()
        self._refresh_preview()
        if self._change_callback is not None:
            self._change_callback()

    def _refresh_tile_text(self) -> None:
        preview = self._build_preview_model()
        manual_length_text = self._variables["manual_nozzle_length"].get().strip() or "not set"
        length_fraction_text = self._variables["length_fraction_percent"].get().strip() or "not set"
        bell_text = self._variables["bell_subtype"].get() if self._current_is_bell else "not applicable"
        re_rt_text = "--" if preview is None else f"{preview.exit_radius_m / max(preview.throat_radius_m, 1.0e-9):.3f}"
        eps_text = "--" if preview is None else f"{preview.expansion_ratio:.3f}"
        if preview is None:
            if self._preview_error_message:
                self._nozzle_calculation_var.set(
                    f"Current contour family: {self._current_contour_family_label.get()}\n"
                    f"Bell subtype: {bell_text}\n"
                    f"Bell length Lf: {length_fraction_text}\n"
                    f"Manual nozzle length: {manual_length_text}\n"
                    f"{self._preview_error_message}"
                )
                self._inflow_angle_var.set(self._preview_error_message)
                self._outflow_angle_var.set(self._preview_error_message)
                self._divergent_loss_var.set("Divergent loss: not available while the nozzle preview is invalid.")
                if self._apply_divergent_loss_button is not None:
                    self._apply_divergent_loss_button.configure(state="disabled")
                return
            self._nozzle_calculation_var.set(
                f"Current contour family: {self._current_contour_family_label.get()}\n"
                f"Bell subtype: {bell_text}\n"
                f"Expansion ratio eps = {eps_text}\n"
                f"Approx. re/rt = {re_rt_text}\n"
                f"Bell length Lf: {length_fraction_text}\n"
                f"Manual nozzle length: {manual_length_text}"
            )
            self._inflow_angle_var.set(
                "Bell start angle guidance appears once eps is valid and the TOP bell draft is within the Rao chart range."
            )
            self._outflow_angle_var.set(
                "Exit-angle guidance appears once eps is valid and the TOP bell draft is within the Rao chart range."
            )
            self._divergent_loss_var.set("Divergent loss: not available until a valid nozzle preview exists.")
            if self._apply_divergent_loss_button is not None:
                self._apply_divergent_loss_button.configure(state="disabled")
            return
        radius_source = "normalized Rt" if preview.uses_normalized_throat else "Current Design throat"
        self._inflow_angle_var.set(
            f"Bell start angle θ_n = {preview.inflow_angle_deg:.2f} deg\n"
            f"Based on downstream throat radius R_down/Rt = {preview.downstream_radius_ratio:.3f}\n"
            f"Radius source: {radius_source}"
        )
        self._outflow_angle_var.set(
            f"Exit angle θ_e = {preview.outflow_angle_deg:.2f} deg\n"
            f"Source: {preview.angle_source or 'Preview approximation'}"
        )
        if preview.uses_manual_length:
            length_source = "manual override"
        elif preview.angle_source is not None:
            length_source = "reference 80% bell"
        else:
            length_source = "preview approximation"
        lf_text = "--" if preview.length_fraction_percent is None else f"{preview.length_fraction_percent:.1f} %"
        self._nozzle_calculation_var.set(
            f"Current contour family: {self._current_contour_family_label.get()}\n"
            f"Bell subtype: {bell_text}\n"
            f"Expansion ratio eps = {preview.expansion_ratio:.3f}\n"
            f"re/rt = {preview.exit_radius_m / max(preview.throat_radius_m, 1.0e-9):.3f}\n"
            f"Lf = {lf_text}\n"
            f"N(x, r) = ({preview.start_x_m:.4f} m, {preview.start_radius_m:.4f} m)\n"
            f"L = {preview.length_m:.4f} m from {length_source}"
        )
        # Divergent loss is shown here because it depends only on the nozzle exit-angle draft
        # and can therefore be reviewed and committed independently from other geometry edits.
        divergent_loss_factor = compute_divergence_efficiency(preview.outflow_angle_deg)
        if divergent_loss_factor is None:
            self._divergent_loss_var.set("Divergent loss: not available.")
            if self._apply_divergent_loss_button is not None:
                self._apply_divergent_loss_button.configure(state="disabled")
        else:
            self._divergent_loss_var.set(
                f"Divergent loss factor = {divergent_loss_factor:.4f}\n"
                f"Divergent loss = {(1.0 - divergent_loss_factor) * 100.0:.2f} %"
            )
            if self._apply_divergent_loss_button is not None:
                self._apply_divergent_loss_button.configure(state="normal")

    def _handle_preview_resize(self, _event: object) -> None:
        self._refresh_preview()

    def _apply_divergent_loss(self) -> None:
        """Commit the current preview loss factor into Current Design."""

        if self._apply_divergent_loss_callback is not None:
            # The owning window decides how this preview-only loss is stored in Current Design.
            self._apply_divergent_loss_callback()

    def _refresh_preview(self) -> None:
        if self._preview_canvas is None:
            return
        canvas = self._preview_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 320)
        height = max(canvas.winfo_height(), 150)
        preview = self._build_preview_model()
        if preview is None:
            canvas.create_text(
                width / 2.0,
                height / 2.0,
                text="Enter a valid expansion ratio to preview the nozzle from x = 0 to x = L.",
                width=width - 30.0,
                justify="center",
                fill="#667381",
            )
            return

        center_y = height - 24.0
        x_margin = 26.0
        y_margin = 26.0
        x_scale = (width - 2.0 * x_margin) / max(preview.length_m, 1.0e-9)
        y_scale = (height - 2.0 * y_margin) / max(preview.exit_radius_m * 1.15, 1.0e-9)
        scale = min(x_scale, y_scale)
        top_points: list[float] = []
        for x_value, radius_value in preview.points:
            top_points.extend((x_margin + x_value * scale, center_y - radius_value * scale))
        bottom_points: list[float] = []
        for index in range(len(top_points) - 2, -1, -2):
            bottom_points.extend((top_points[index], 2.0 * center_y - top_points[index + 1]))

        canvas.create_polygon(
            top_points + bottom_points,
            fill="#dfe9f5",
            outline="#2c628f",
            width=2,
            smooth=self._current_is_bell,
        )
        throat_canvas_x = x_margin
        throat_canvas_radius = preview.throat_radius_m * scale
        n_canvas_x = x_margin + preview.start_x_m * scale
        n_canvas_radius = preview.start_radius_m * scale
        exit_canvas_x = x_margin + preview.length_m * scale
        exit_canvas_radius = preview.exit_radius_m * scale

        canvas.create_line(
            throat_canvas_x,
            center_y - throat_canvas_radius,
            throat_canvas_x,
            center_y + throat_canvas_radius,
            fill="#244a6d",
            width=2,
        )
        canvas.create_oval(
            n_canvas_x - 3.0,
            center_y - n_canvas_radius - 3.0,
            n_canvas_x + 3.0,
            center_y - n_canvas_radius + 3.0,
            fill="#c25b2a",
            outline="",
        )
        canvas.create_text(throat_canvas_x, 10, anchor="nw", text="x = 0", font=("Segoe UI", 8), fill="#364556")
        canvas.create_text(n_canvas_x + 6.0, 10, anchor="nw", text="N", font=("Segoe UI", 8, "bold"), fill="#364556")
        canvas.create_text(exit_canvas_x, 10, anchor="ne", text="x = L", font=("Segoe UI", 8), fill="#364556")
        canvas.create_text(
            width - 10,
            height - 8,
            anchor="se",
            text=f"L ≈ {preview.length_m:.4f} m",
            font=("Segoe UI", 8),
            fill="#506170",
        )

    def _build_preview_model(self) -> object | None:
        self._preview_error_message = ""
        try:
            expansion_ratio = float(self._variables["expansion_ratio"].get().strip().replace(",", "."))
        except ValueError:
            return None
        if not math.isfinite(expansion_ratio) or expansion_ratio <= 1.0:
            return None

        try:
            manual_length = float(self._variables["manual_nozzle_length"].get().strip().replace(",", "."))
        except ValueError:
            manual_length = None
        try:
            length_fraction_percent = float(self._variables["length_fraction_percent"].get().strip().replace(",", "."))
        except ValueError:
            length_fraction_percent = None

        runtime_inputs = self._runtime_inputs
        runtime_bundle = self._runtime_bundle
        contour_method = runtime_inputs.contour_method if runtime_inputs is not None else NozzleContourMethod.BELL
        bell_variant = (
            SUBTYPE_VALUES.get(self._variables["bell_subtype"].get(), BellContourVariant.PARABOLA)
            if contour_method is NozzleContourMethod.BELL
            else BellContourVariant.PARABOLA
        )
        downstream_radius_ratio = 0.382
        if runtime_inputs is not None and runtime_bundle is not None and runtime_bundle.geometry.throat_radius_m > 0.0:
            if runtime_inputs.throat_downstream_radius_m is not None and runtime_inputs.throat_downstream_radius_m > 0.0:
                downstream_radius_ratio = (
                    runtime_inputs.throat_downstream_radius_m / runtime_bundle.geometry.throat_radius_m
                )
        elif runtime_inputs is not None and runtime_inputs.throat_downstream_radius_m is not None:
            downstream_radius_ratio = max(runtime_inputs.throat_downstream_radius_m, 0.382)
        throat_radius = runtime_bundle.geometry.throat_radius_m if runtime_bundle is not None else None
        try:
            return build_nozzle_preview(
                throat_radius_m=throat_radius,
                expansion_ratio=expansion_ratio,
                downstream_radius_ratio=downstream_radius_ratio,
                contour_method=contour_method,
                bell_variant=bell_variant,
                manual_length_m=manual_length,
                length_fraction_input=length_fraction_percent,
            )
        except (RuntimeError, ValueError) as exc:
            self._preview_error_message = str(exc)
            return None


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
        ("Estimated liner mass", "estimated_liner_mass_kg", "mass"),
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
        self.variables["estimated_liner_mass_kg"].set(
            format_quantity(geometry.estimated_liner_mass_kg, "mass", self._unit_preset)
        )

    def set_estimated_liner_mass(self, liner_mass_kg: float | None) -> None:
        """Update the summary with the latest preview-level liner-mass estimate."""

        self.variables["estimated_liner_mass_kg"].set(
            format_quantity(liner_mass_kg, "mass", self._unit_preset)
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
        super().__init__(master, text="Material Section", padding=12)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self._change_callback: Callable[[], None] | None = None
        self._apply_callback: Callable[[], None] | None = None
        self._apply_wall_callback: Callable[[], None] | None = None
        self._commit_liner_callback: Callable[[], None] | None = None
        self._suspend_notifications = False
        self._unit_preset = unit_preset
        self._field_labels: dict[str, ttk.Label] = {}
        self._manufacturing_mode = tk.StringVar(value=MANUFACTURING_MODE_LABELS[ManufacturingMode.TRADITIONAL])
        self._manufacturing_route = tk.StringVar(value=ROUTE_LABELS[ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT])
        self._liner_material = tk.StringVar(value=DEFAULT_LINER_MATERIAL)
        self._coating_enabled = tk.BooleanVar(value=False)
        self._coating = tk.StringVar(value=DEFAULT_COATING)
        self._closeout_enabled = tk.BooleanVar(value=True)
        self._closeout_thickness = tk.StringVar(value="3.000")
        self._closeout_material = tk.StringVar(value=DEFAULT_LINER_MATERIAL)
        self._wall_thickness_mode = tk.StringVar(
            value=WALL_THICKNESS_MODE_LABELS[WallThicknessMode.CONSTANT]
        )
        self._wall_thickness = tk.StringVar(value="1.500")
        self._note_var = tk.StringVar(value="")
        self._route_box: ttk.Combobox | None = None
        self._material_box: ttk.Combobox | None = None
        self._closeout_check: ttk.Checkbutton | None = None
        self._closeout_material_label: ttk.Label | None = None
        self._closeout_material_box: ttk.Combobox | None = None
        self._closeout_thickness_entry: ttk.Entry | None = None
        self._wall_entry: ttk.Entry | None = None
        self._manufacturing_mode.trace_add("write", self._handle_mode_changed)
        self._manufacturing_route.trace_add("write", self._handle_route_changed)
        self._liner_material.trace_add("write", self._handle_changed)
        self._coating_enabled.trace_add("write", self._handle_changed)
        self._coating.trace_add("write", self._handle_changed)
        self._closeout_enabled.trace_add("write", self._handle_closeout_changed)
        self._closeout_thickness.trace_add("write", self._handle_changed)
        self._closeout_material.trace_add("write", self._handle_changed)
        self._wall_thickness_mode.trace_add("write", self._handle_wall_mode_changed)
        self._wall_thickness.trace_add("write", self._handle_changed)
        self._build_widgets()
        self._sync_route_values()
        self._sync_material_values()
        self._sync_wall_mode()
        self._sync_closeout_controls()

    def _build_widgets(self) -> None:
        manufacturing_frame = ttk.LabelFrame(self, text="Manufacturing", padding=10)
        manufacturing_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
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
        materials_frame.grid(row=0, column=1, sticky="nsew")
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

        ttk.Label(materials_frame, text="Closeout enabled").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        closeout_check = ttk.Checkbutton(materials_frame, variable=self._closeout_enabled)
        closeout_check.grid(row=3, column=1, sticky="w", pady=4)
        self._closeout_check = closeout_check

        closeout_thickness_label = ttk.Label(materials_frame)
        closeout_thickness_label.grid(row=4, column=0, sticky="w", padx=(0, 10), pady=4)
        self._field_labels["closeout_thickness"] = closeout_thickness_label
        closeout_thickness_entry = ttk.Entry(materials_frame, textvariable=self._closeout_thickness)
        closeout_thickness_entry.grid(row=4, column=1, sticky="ew", pady=4)
        self._closeout_thickness_entry = closeout_thickness_entry

        closeout_material_label = ttk.Label(materials_frame, text="Closeout material")
        closeout_material_label.grid(row=5, column=0, sticky="w", padx=(0, 10), pady=4)
        self._closeout_material_label = closeout_material_label
        closeout_material_box = ttk.Combobox(
            materials_frame,
            state="readonly",
            textvariable=self._closeout_material,
            values=CLOSEOUT_MATERIAL_OPTIONS,
        )
        closeout_material_box.grid(row=5, column=1, sticky="ew", pady=4)
        self._closeout_material_box = closeout_material_box

        wall_frame = ttk.LabelFrame(self, text="Liner Wall", padding=10)
        wall_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 12), pady=(12, 0))
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
        button_row = ttk.Frame(wall_frame)
        button_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(
            button_row,
            text="Apply Wall Thickness",
            command=self._apply_wall_updates,
            width=20,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            button_row,
            text="Commit Liner to Thermo Chemistry / Cooling",
            command=self._commit_liner_updates,
            width=34,
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        empty_tile = ttk.LabelFrame(self, text="", padding=10)
        empty_tile.grid(row=1, column=1, sticky="nsew", pady=(12, 0))
        ttk.Label(empty_tile, text="").grid(row=0, column=0, pady=42)

        self._apply_unit_labels()
        self._sync_closeout_controls()

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
        self._closeout_enabled.set(True)
        self._closeout_thickness.set(format_quantity(DEFAULT_CLOSEOUT_THICKNESS_M, "length", self._unit_preset))
        self._closeout_material.set(DEFAULT_LINER_MATERIAL)
        self._wall_thickness_mode.set(WALL_THICKNESS_MODE_LABELS[WallThicknessMode.CONSTANT])
        self._wall_thickness.set("1.500")
        self._suspend_notifications = False
        self._sync_wall_mode()
        self._sync_closeout_controls()

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
        resolved_closeout_enabled = bool(inputs.closeout_enabled)
        if (
            not resolved_closeout_enabled
            and inputs.closeout_thickness_m is None
            and inputs.closeout_material is None
            and _route_supports_closeout(inputs.manufacturing_route)
        ):
            resolved_closeout_enabled = True
        self._closeout_enabled.set(resolved_closeout_enabled)
        self._closeout_thickness.set(
            format_quantity(
                inputs.closeout_thickness_m if inputs.closeout_thickness_m is not None else DEFAULT_CLOSEOUT_THICKNESS_M,
                "length",
                self._unit_preset,
            )
        )
        self._closeout_material.set(
            _normalize_closeout_material(
                inputs.closeout_material,
                fallback=_normalize_closeout_material(inputs.liner_material, fallback=DEFAULT_LINER_MATERIAL),
            )
        )
        self._wall_thickness_mode.set(WALL_THICKNESS_MODE_LABELS[inputs.wall_thickness_mode])
        self._wall_thickness.set(
            ""
            if inputs.wall_thickness_m is None
            else format_quantity(inputs.wall_thickness_m, "length", self._unit_preset)
        )
        self._suspend_notifications = False
        self._sync_wall_mode()
        self._sync_closeout_controls()

    def bind_inputs_changed(self, callback: Callable[[], None]) -> None:
        """Bind a callback fired when the draft material editor changes."""

        self._change_callback = callback

    def bind_apply_requested(self, callback: Callable[[], None]) -> None:
        """Bind a callback to store the current nozzle/material draft state."""

        self._apply_callback = callback

    def bind_apply_wall_requested(self, callback: Callable[[], None]) -> None:
        """Bind a callback that stores wall-thickness changes for preview use."""

        self._apply_wall_callback = callback

    def bind_commit_liner_requested(self, callback: Callable[[], None]) -> None:
        """Bind a callback that commits liner assumptions to Current Design."""

        self._commit_liner_callback = callback

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
        closeout_enabled = bool(self._closeout_enabled.get()) and _route_supports_closeout(route)
        closeout_thickness = _parse_optional_float(
            self._closeout_thickness.get(),
            "Closeout thickness",
            errors,
        )
        if closeout_enabled and closeout_thickness is None:
            closeout_thickness = convert_to_display(DEFAULT_CLOSEOUT_THICKNESS_M, "length", self._unit_preset)
        closeout_material = _normalize_closeout_material(
            self._closeout_material.get(),
            fallback=_normalize_closeout_material(self._liner_material.get(), fallback=DEFAULT_LINER_MATERIAL),
        )
        if errors:
            raise InputValidationError(errors)

        coating = self._coating.get().strip() or DEFAULT_COATING
        return {
            "manufacturing_mode": manufacturing_mode,
            "manufacturing_route": route,
            "liner_material": self._liner_material.get().strip() or DEFAULT_LINER_MATERIAL,
            "liner_coating_enabled": self._coating_enabled.get() and coating != DEFAULT_COATING,
            "liner_coating": None if not self._coating_enabled.get() or coating == DEFAULT_COATING else coating,
            "closeout_enabled": closeout_enabled,
            "closeout_thickness_m": (
                convert_from_display(closeout_thickness, "length", self._unit_preset)
                if closeout_enabled
                else None
            ),
            "closeout_material": closeout_material if closeout_enabled else None,
            "wall_thickness_mode": wall_mode,
            "wall_thickness_m": convert_from_display(wall_thickness, "length", self._unit_preset),
        }

    def _apply_unit_labels(self) -> None:
        self._field_labels["wall_thickness"].configure(
            text=f"Wall thickness [{get_unit_symbol('length', self._unit_preset)}]"
        )
        self._field_labels["closeout_thickness"].configure(
            text=f"Closeout thickness [{get_unit_symbol('length', self._unit_preset)}]"
        )

    def _handle_mode_changed(self, *_args: object) -> None:
        if self._suspend_notifications:
            return
        self._sync_route_values()
        self._sync_material_values()
        self._sync_closeout_controls()
        self._update_note()
        self._handle_changed()

    def _handle_route_changed(self, *_args: object) -> None:
        if self._suspend_notifications:
            return
        self._sync_material_values()
        self._sync_closeout_controls()
        self._update_note()
        self._handle_changed()

    def _handle_wall_mode_changed(self, *_args: object) -> None:
        if self._suspend_notifications:
            return
        self._sync_wall_mode()
        self._handle_changed()

    def _handle_closeout_changed(self, *_args: object) -> None:
        if self._suspend_notifications:
            return
        self._sync_closeout_controls()
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

    def _sync_closeout_controls(self) -> None:
        route = _route_from_label(self._manufacturing_route.get()) or ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT
        route_supports_closeout = _route_supports_closeout(route)
        if not route_supports_closeout and self._closeout_enabled.get():
            self._suspend_notifications = True
            self._closeout_enabled.set(False)
            self._suspend_notifications = False
        if self._closeout_check is not None:
            self._closeout_check.configure(state="normal" if route_supports_closeout else "disabled")
        if self._closeout_material_box is not None:
            self._closeout_material_box.configure(values=CLOSEOUT_MATERIAL_OPTIONS)
        if not self._closeout_material.get().strip():
            self._closeout_material.set(_normalize_closeout_material(self._liner_material.get(), fallback=DEFAULT_LINER_MATERIAL))
        show_closeout_details = route_supports_closeout and self._closeout_enabled.get()
        closeout_thickness_label = self._field_labels.get("closeout_thickness")
        for widget in (
            closeout_thickness_label,
            self._closeout_material_label,
            self._closeout_thickness_entry,
            self._closeout_material_box,
        ):
            if widget is None:
                continue
            if show_closeout_details:
                widget.grid()
            else:
                widget.grid_remove()

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

    def _apply_wall_updates(self) -> None:
        """Store the current wall-thickness choice for liner-mass previewing."""

        if self._apply_wall_callback is not None:
            # Wall thickness affects preview mass and wall overlay first; the caller decides
            # when those assumptions become part of the committed Current Design state.
            self._apply_wall_callback()

    def _commit_liner_updates(self) -> None:
        """Commit current liner/material inputs for later thermochemistry/cooling use."""

        if self._commit_liner_callback is not None:
            # This separate commit keeps liner assumptions explicit because cooling work may
            # start later than the first chamber/nozzle geometry exploration.
            self._commit_liner_callback()


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

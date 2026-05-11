"""Tkinter chamber-geometry sandbox for preliminary rocket-engine sizing."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Callable

from engine.chamber_geometry import (
    ChamberGeometryInputs,
    ChamberGeometryModel,
    ChamberGeometryResult,
    DEFAULT_LSTAR_PROPELLANT,
    FIGURE_8_15_SOURCE,
    LStarSelectionMode,
    NASA_LSTAR_SOURCE,
    StoredChamberGeometryCalculation,
    WorkingChamberGeometryState,
    calculate_chamber_geometry,
    estimate_contraction_ratio_guidance,
    get_lstar_range,
    infer_lstar_mode,
    select_lstar_value,
    suggest_lstar_propellant,
    validate_chamber_justifications,
)
from engine.models import ExportBundle, InputParameters
from engine.utils.validation import InputValidationError

SELECTION_MODE_LABELS = {
    LStarSelectionMode.MIN: "min",
    LStarSelectionMode.NOMINAL: "nominal",
    LStarSelectionMode.MAX: "max",
    LStarSelectionMode.CUSTOM: "custom",
}
SELECTION_MODE_VALUES = {label: mode for mode, label in SELECTION_MODE_LABELS.items()}

CHAMBER_MODEL_LABELS = {
    ChamberGeometryModel.CYLINDRICAL: "Cylindrical",
    ChamberGeometryModel.NEAR_SPHERICAL_CONVERGENT: "Near Spherical / Convergent CC (future)",
    ChamberGeometryModel.SPHERICAL: "Spherical CC (future)",
}
CHAMBER_MODEL_VALUES = {label: mode for mode, label in CHAMBER_MODEL_LABELS.items()}


class ChamberGeometryPanel(ttk.LabelFrame):
    """Interactive chamber sandbox with staged L* and epsilon_c selection."""

    _NOTE_TEXT = (
        "L* is an empirical preliminary design parameter. It represents the chamber volume required "
        "per throat area and depends on propellant combination, injector design, atomization, mixing, "
        "combustion efficiency and chamber pressure. The selected value should be refined later using "
        "injector design and hot-fire test data."
    )
    _FIGURE_8_15_NOTE = (
        "Figure 8-15 guidance is used here as an approximate preliminary band for Dc/Dt and epsilon_c "
        "based on the required chamber volume on a log scale."
    )

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Chamber Geometry", padding=12)
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(0, weight=1)

        self._suspend_notifications = False
        self._apply_lstar_callback: Callable[[], None] | None = None
        self._apply_geometry_callback: Callable[[], None] | None = None
        self._stored_state_changed_callback: Callable[[], None] | None = None
        self._current_bundle: ExportBundle | None = None
        self._runtime_inputs: InputParameters | None = None
        self._stored_calculation: StoredChamberGeometryCalculation | None = None
        self._stored_lstar_update: dict[str, object] | None = None
        self._stored_geometry_update: dict[str, object] | None = None
        self._committed_lstar_m: float | None = None
        self._committed_lstar_mode: LStarSelectionMode | None = None
        self._committed_lstar_justification = ""
        self._committed_eps_c: float | None = None
        self._committed_eps_mode: LStarSelectionMode | None = None
        self._committed_eps_justification = ""
        self._last_preview_result: ChamberGeometryResult | None = None

        self._variables = {
            "chamber_model": tk.StringVar(value=CHAMBER_MODEL_LABELS[ChamberGeometryModel.CYLINDRICAL]),
            "throat_diameter_m": tk.StringVar(value="0.1000"),
            "selected_lstar_m": tk.StringVar(value="not yet applied"),
            "selected_epsilon_c": tk.StringVar(value="not yet applied"),
            "convergent_half_angle_deg": tk.StringVar(value="45.000"),
            "corner_radius_ratio": tk.StringVar(value="0.0000"),
            "lstar_mode": tk.StringVar(value=SELECTION_MODE_LABELS[LStarSelectionMode.NOMINAL]),
            "custom_lstar_m": tk.StringVar(value=""),
            "eps_mode": tk.StringVar(value=SELECTION_MODE_LABELS[LStarSelectionMode.NOMINAL]),
            "custom_epsilon_c": tk.StringVar(value=""),
        }
        for variable in self._variables.values():
            variable.trace_add("write", self._handle_inputs_changed)

        self._lstar_slider_var = tk.DoubleVar(value=0.0)
        self._eps_slider_var = tk.DoubleVar(value=0.0)
        self._status_var = tk.StringVar(
            value="Apply L* and epsilon_c selections, then store the chamber geometry calculation."
        )
        self._warnings_var = tk.StringVar(value="")
        self._stored_calc_var = tk.StringVar(value="Last Geometry Calculation: not stored yet.")
        self._shape_note_var = tk.StringVar(
            value="Near-spherical and spherical chamber concepts are visible here but reserved for a later patch."
        )
        self._current_propellant_var = tk.StringVar(value=DEFAULT_LSTAR_PROPELLANT)
        self._lstar_range_text_var = tk.StringVar(value="--")
        self._lstar_selection_text_var = tk.StringVar(value="selected: --")
        self._lstar_slider_min_var = tk.StringVar(value="--")
        self._lstar_slider_max_var = tk.StringVar(value="--")
        self._eps_hint_var = tk.StringVar(value="Apply L* Selection first to unlock epsilon_c guidance.")
        self._eps_band_var = tk.StringVar(value="Typical epsilon_c band: --")
        self._dc_dt_band_var = tk.StringVar(value="Typical Dc/Dt band: --")
        self._eps_selection_text_var = tk.StringVar(value="selected: --")
        self._eps_slider_min_var = tk.StringVar(value="--")
        self._eps_slider_max_var = tk.StringVar(value="--")
        self._figure_8_15_state_var = tk.StringVar(value=self._FIGURE_8_15_NOTE)

        self._result_vars = {
            "lstar_range": tk.StringVar(value="not yet computed"),
            "selected_lstar": tk.StringVar(value="not yet computed"),
            "throat_area": tk.StringVar(value="not yet computed"),
            "chamber_area": tk.StringVar(value="not yet computed"),
            "throat_diameter": tk.StringVar(value="not yet computed"),
            "chamber_diameter": tk.StringVar(value="not yet computed"),
            "contraction_ratio": tk.StringVar(value="not yet computed"),
            "convergent_half_angle": tk.StringVar(value="not yet computed"),
            "corner_radius_ratio": tk.StringVar(value="not yet computed"),
            "corner_radius": tk.StringVar(value="not yet computed"),
            "required_chamber_volume": tk.StringVar(value="not yet computed"),
            "cylindrical_section_length": tk.StringVar(value="not yet computed"),
            "rounded_corner_length": tk.StringVar(value="not yet computed"),
            "remaining_cone_length": tk.StringVar(value="not yet computed"),
            "convergent_section_length": tk.StringVar(value="not yet computed"),
            "total_chamber_length": tk.StringVar(value="not yet computed"),
            "hot_gas_wall_area": tk.StringVar(value="not yet computed"),
        }

        self._justification_text_widgets: dict[str, tk.Text] = {}
        self._custom_lstar_entry: ttk.Entry | None = None
        self._custom_eps_entry: ttk.Entry | None = None
        self._lstar_slider: ttk.Scale | None = None
        self._eps_slider: ttk.Scale | None = None
        self._apply_lstar_button: ttk.Button | None = None
        self._apply_eps_button: ttk.Button | None = None
        self._apply_geometry_button: ttk.Button | None = None
        self._eps_tile_widgets: list[tk.Widget] = []
        self._preview_canvas: tk.Canvas | None = None

        self._build_widgets()
        self._refresh_results()

    def _build_widgets(self) -> None:
        left_frame = ttk.Frame(self)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left_frame.columnconfigure(0, weight=1)

        input_frame = ttk.LabelFrame(left_frame, text="Chamber Geometry Inputs", padding=10)
        input_frame.grid(row=0, column=0, sticky="ew")
        input_frame.columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="Chamber model").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Combobox(
            input_frame,
            state="readonly",
            textvariable=self._variables["chamber_model"],
            values=list(CHAMBER_MODEL_VALUES),
        ).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(
            input_frame,
            textvariable=self._shape_note_var,
            wraplength=480,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))

        ttk.Label(input_frame, text="Throat diameter Dt [m]").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(input_frame, textvariable=self._variables["throat_diameter_m"]).grid(
            row=2,
            column=1,
            sticky="ew",
            pady=4,
        )

        ttk.Label(input_frame, text="Selected L* [m]").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(
            input_frame,
            textvariable=self._variables["selected_lstar_m"],
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Label(input_frame, text="Selected epsilon_c [-]").grid(row=4, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(
            input_frame,
            textvariable=self._variables["selected_epsilon_c"],
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(input_frame, text="Convergent half angle theta [deg]").grid(
            row=5, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(input_frame, textvariable=self._variables["convergent_half_angle_deg"]).grid(
            row=5, column=1, sticky="ew", pady=4
        )

        ttk.Label(input_frame, text="r_corner / r_t [-]").grid(row=6, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(input_frame, textvariable=self._variables["corner_radius_ratio"]).grid(
            row=6, column=1, sticky="ew", pady=4
        )

        ttk.Label(
            input_frame,
            text="Use the L* and epsilon_c tiles on the right to commit preliminary selections into these chamber inputs.",
            wraplength=500,
            justify="left",
        ).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        apply_frame = ttk.Frame(left_frame)
        apply_frame.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self._apply_geometry_button = ttk.Button(
            apply_frame,
            text="Apply Geometry Inputs",
            command=self._apply_geometry_inputs,
            width=22,
        )
        self._apply_geometry_button.grid(row=0, column=0, sticky="w")

        result_frame = ttk.LabelFrame(left_frame, text="Chamber Geometry Calculation", padding=10)
        result_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        result_frame.columnconfigure(1, weight=1)
        result_frame.columnconfigure(3, weight=1)

        result_rows = [
            (("L* range [m]", "lstar_range"), ("Selected L* [m]", "selected_lstar")),
            (("At [m^2]", "throat_area"), ("Ac [m^2]", "chamber_area")),
            (("Dt [m]", "throat_diameter"), ("Dc [m]", "chamber_diameter")),
            (("epsilon_c [-]", "contraction_ratio"), ("theta [deg]", "convergent_half_angle")),
            (("Corner radius r/rt [-]", "corner_radius_ratio"), ("Corner radius [m]", "corner_radius")),
            (("Vc_required [m^3]", "required_chamber_volume"), ("Lc cylindrical section [m]", "cylindrical_section_length")),
            (("Rounded corner length [m]", "rounded_corner_length"), ("Remaining cone length [m]", "remaining_cone_length")),
            (("L_conv total axial [m]", "convergent_section_length"), ("L_total to throat [m]", "total_chamber_length")),
            (("A_hot [m^2]", "hot_gas_wall_area"), None),
        ]
        for row_index, row_definition in enumerate(result_rows):
            left_entry, right_entry = row_definition
            left_label, left_key = left_entry
            ttk.Label(result_frame, text=left_label).grid(
                row=row_index,
                column=0,
                sticky="w",
                padx=(0, 10),
                pady=2,
            )
            ttk.Label(result_frame, textvariable=self._result_vars[left_key], justify="left").grid(
                row=row_index,
                column=1,
                sticky="w",
                pady=2,
            )
            if right_entry is None:
                continue
            right_label, right_key = right_entry
            ttk.Label(result_frame, text=right_label).grid(
                row=row_index,
                column=2,
                sticky="w",
                padx=(18, 10),
                pady=2,
            )
            ttk.Label(result_frame, textvariable=self._result_vars[right_key], justify="left").grid(
                row=row_index,
                column=3,
                sticky="w",
                pady=2,
            )

        ttk.Label(
            result_frame,
            textvariable=self._stored_calc_var,
            wraplength=520,
            justify="left",
        ).grid(row=len(result_rows), column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Label(
            result_frame,
            textvariable=self._status_var,
            wraplength=520,
            justify="left",
        ).grid(row=len(result_rows) + 1, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        ttk.Label(
            result_frame,
            textvariable=self._warnings_var,
            wraplength=520,
            justify="left",
            foreground="#8b5a12",
        ).grid(row=len(result_rows) + 2, column=0, columnspan=4, sticky="ew", pady=(6, 0))

        ttk.Label(left_frame, text=self._NOTE_TEXT, wraplength=560, justify="left").grid(
            row=3, column=0, sticky="ew", pady=(10, 0)
        )

        preview_frame = ttk.LabelFrame(left_frame, text="Chamber Liner Geometry Preview", padding=10)
        preview_frame.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        preview_frame.columnconfigure(0, weight=1)
        preview_canvas = tk.Canvas(preview_frame, height=220, background="#f7f8fb", highlightthickness=0)
        preview_canvas.grid(row=0, column=0, sticky="ew")
        preview_canvas.bind("<Configure>", self._handle_preview_resize)
        self._preview_canvas = preview_canvas

        right_frame = ttk.Frame(self)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)

        lstar_frame = ttk.LabelFrame(right_frame, text="L* Selection", padding=10)
        lstar_frame.grid(row=0, column=0, sticky="ew")
        lstar_frame.columnconfigure(0, weight=1)

        ttk.Label(
            lstar_frame,
            textvariable=self._current_propellant_var,
            wraplength=420,
            justify="left",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            lstar_frame,
            textvariable=self._lstar_range_text_var,
            wraplength=420,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))

        mode_row = ttk.Frame(lstar_frame)
        mode_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        mode_row.columnconfigure(1, weight=1)
        ttk.Label(mode_row, text="Mode").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Combobox(
            mode_row,
            state="readonly",
            textvariable=self._variables["lstar_mode"],
            values=list(SELECTION_MODE_VALUES),
        ).grid(row=0, column=1, sticky="ew")

        custom_row = ttk.Frame(lstar_frame)
        custom_row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        custom_row.columnconfigure(1, weight=1)
        ttk.Label(custom_row, text="Custom L* [m]").grid(row=0, column=0, sticky="w", padx=(0, 10))
        custom_lstar_entry = ttk.Entry(custom_row, textvariable=self._variables["custom_lstar_m"])
        custom_lstar_entry.grid(row=0, column=1, sticky="ew")
        self._custom_lstar_entry = custom_lstar_entry

        lstar_slider = ttk.Scale(
            lstar_frame,
            variable=self._lstar_slider_var,
            command=self._handle_lstar_slider_changed,
        )
        lstar_slider.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self._lstar_slider = lstar_slider

        slider_row = ttk.Frame(lstar_frame)
        slider_row.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        slider_row.columnconfigure(0, weight=1)
        slider_row.columnconfigure(1, weight=1)
        ttk.Label(slider_row, textvariable=self._lstar_slider_min_var).grid(row=0, column=0, sticky="w")
        ttk.Label(slider_row, textvariable=self._lstar_slider_max_var).grid(row=0, column=1, sticky="e")
        ttk.Label(
            lstar_frame,
            textvariable=self._lstar_selection_text_var,
            justify="left",
        ).grid(row=6, column=0, sticky="w", pady=(6, 0))

        ttk.Label(lstar_frame, text="Justification for Selected L*").grid(row=7, column=0, sticky="w", pady=(10, 0))
        lstar_text = tk.Text(lstar_frame, height=3, wrap="word")
        lstar_text.grid(row=8, column=0, sticky="ew", pady=(4, 0))
        lstar_text.bind("<KeyRelease>", self._handle_text_changed)
        lstar_text.bind("<FocusOut>", self._handle_text_changed)
        self._justification_text_widgets["lstar"] = lstar_text

        apply_lstar_row = ttk.Frame(lstar_frame)
        apply_lstar_row.grid(row=9, column=0, sticky="w", pady=(8, 0))
        apply_lstar_button = ttk.Button(
            apply_lstar_row,
            text="Apply L* Selection",
            command=self._apply_lstar_selection,
            width=18,
        )
        apply_lstar_button.grid(row=0, column=0, sticky="w")
        self._apply_lstar_button = apply_lstar_button

        ttk.Label(
            lstar_frame,
            text=NASA_LSTAR_SOURCE,
            wraplength=420,
            justify="left",
        ).grid(row=10, column=0, sticky="ew", pady=(8, 0))

        eps_frame = ttk.LabelFrame(
            right_frame,
            text="Distribution of combustion chamber contraction ratio eps_c",
            padding=10,
        )
        eps_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        eps_frame.columnconfigure(0, weight=1)

        ttk.Label(
            eps_frame,
            textvariable=self._eps_hint_var,
            wraplength=420,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

        ttk.Label(
            eps_frame,
            textvariable=self._dc_dt_band_var,
            wraplength=420,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(
            eps_frame,
            textvariable=self._eps_band_var,
            wraplength=420,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(4, 0))

        eps_mode_row = ttk.Frame(eps_frame)
        eps_mode_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        eps_mode_row.columnconfigure(1, weight=1)
        ttk.Label(eps_mode_row, text="Mode").grid(row=0, column=0, sticky="w", padx=(0, 10))
        eps_mode_box = ttk.Combobox(
            eps_mode_row,
            state="readonly",
            textvariable=self._variables["eps_mode"],
            values=list(SELECTION_MODE_VALUES),
        )
        eps_mode_box.grid(row=0, column=1, sticky="ew")
        self._eps_tile_widgets.append(eps_mode_box)

        eps_custom_row = ttk.Frame(eps_frame)
        eps_custom_row.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        eps_custom_row.columnconfigure(1, weight=1)
        ttk.Label(eps_custom_row, text="Custom epsilon_c [-]").grid(row=0, column=0, sticky="w", padx=(0, 10))
        custom_eps_entry = ttk.Entry(eps_custom_row, textvariable=self._variables["custom_epsilon_c"])
        custom_eps_entry.grid(row=0, column=1, sticky="ew")
        self._custom_eps_entry = custom_eps_entry
        self._eps_tile_widgets.append(custom_eps_entry)

        eps_slider = ttk.Scale(
            eps_frame,
            variable=self._eps_slider_var,
            command=self._handle_eps_slider_changed,
        )
        eps_slider.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self._eps_slider = eps_slider
        self._eps_tile_widgets.append(eps_slider)

        eps_slider_row = ttk.Frame(eps_frame)
        eps_slider_row.grid(row=6, column=0, sticky="ew", pady=(4, 0))
        eps_slider_row.columnconfigure(0, weight=1)
        eps_slider_row.columnconfigure(1, weight=1)
        ttk.Label(eps_slider_row, textvariable=self._eps_slider_min_var).grid(row=0, column=0, sticky="w")
        ttk.Label(eps_slider_row, textvariable=self._eps_slider_max_var).grid(row=0, column=1, sticky="e")
        ttk.Label(
            eps_frame,
            textvariable=self._eps_selection_text_var,
            justify="left",
        ).grid(row=7, column=0, sticky="w", pady=(6, 0))

        ttk.Label(eps_frame, text="Justification for Contraction Ratio epsilon_c").grid(
            row=8, column=0, sticky="w", pady=(10, 0)
        )
        eps_text = tk.Text(eps_frame, height=3, wrap="word")
        eps_text.grid(row=9, column=0, sticky="ew", pady=(4, 0))
        eps_text.bind("<KeyRelease>", self._handle_text_changed)
        eps_text.bind("<FocusOut>", self._handle_text_changed)
        self._justification_text_widgets["contraction_ratio"] = eps_text
        self._eps_tile_widgets.append(eps_text)

        apply_eps_row = ttk.Frame(eps_frame)
        apply_eps_row.grid(row=10, column=0, sticky="w", pady=(8, 0))
        apply_eps_button = ttk.Button(
            apply_eps_row,
            text="Apply epsilon_c",
            command=self._apply_eps_selection,
            width=18,
        )
        apply_eps_button.grid(row=0, column=0, sticky="w")
        self._apply_eps_button = apply_eps_button
        self._eps_tile_widgets.append(apply_eps_button)

        ttk.Label(
            eps_frame,
            textvariable=self._figure_8_15_state_var,
            wraplength=420,
            justify="left",
        ).grid(row=11, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            eps_frame,
            text=FIGURE_8_15_SOURCE,
            wraplength=420,
            justify="left",
        ).grid(row=12, column=0, sticky="ew", pady=(8, 0))

    def bind_apply_selected_lstar(self, callback: Callable[[], None]) -> None:
        """Bind a callback after L* is stored for explicit Current Design transfer."""

        self._apply_lstar_callback = callback

    def bind_apply_geometry_inputs(self, callback: Callable[[], None]) -> None:
        """Bind a callback after chamber geometry is stored for explicit transfer."""

        self._apply_geometry_callback = callback

    def bind_stored_state_changed(self, callback: Callable[[], None]) -> None:
        """Bind a callback whenever a stored chamber state changes."""

        self._stored_state_changed_callback = callback

    def seed_from_design(
        self,
        inputs: InputParameters,
        *,
        current_bundle: ExportBundle | None = None,
    ) -> None:
        """Reset the sandbox from the current design baseline."""

        self._runtime_inputs = inputs
        self._current_bundle = current_bundle
        self._stored_calculation = None
        self._stored_lstar_update = None
        self._stored_geometry_update = None
        self._stored_calc_var.set("Last Geometry Calculation: not stored yet.")
        self._warnings_var.set("")
        self._status_var.set("Apply L* and epsilon_c selections, then store the chamber geometry calculation.")

        propellant_name = self._current_propellant_name(inputs)
        throat_diameter_m = 0.1000
        if current_bundle is not None:
            throat_diameter_m = 2.0 * current_bundle.geometry.throat_radius_m
        lstar_value = inputs.characteristic_length_m
        if lstar_value is None:
            lstar_value = select_lstar_value(propellant_name, LStarSelectionMode.NOMINAL)
        lstar_mode, custom_lstar = infer_lstar_mode(propellant_name, lstar_value)

        guidance = estimate_contraction_ratio_guidance(
            lstar_value * (math.pi / 4.0) * throat_diameter_m**2
        )
        eps_value = (
            inputs.contraction_ratio
            if inputs.contraction_ratio is not None and inputs.contraction_ratio > 1.0
            else 0.5 * (guidance.contraction_ratio_min + guidance.contraction_ratio_max)
        )
        eps_mode, custom_eps = _infer_selection_mode(
            eps_value,
            guidance.contraction_ratio_min,
            guidance.contraction_ratio_max,
        )

        self._suspend_notifications = True
        self._variables["throat_diameter_m"].set(f"{throat_diameter_m:.5f}")
        self._variables["convergent_half_angle_deg"].set(f"{inputs.convergent_half_angle_deg:.3f}")
        self._variables["corner_radius_ratio"].set("0.0000")
        self._variables["lstar_mode"].set(SELECTION_MODE_LABELS[lstar_mode])
        self._variables["custom_lstar_m"].set("" if custom_lstar is None else f"{custom_lstar:.4f}")
        self._variables["eps_mode"].set(SELECTION_MODE_LABELS[eps_mode])
        self._variables["custom_epsilon_c"].set("" if custom_eps is None else f"{custom_eps:.4f}")
        for widget in self._justification_text_widgets.values():
            widget.delete("1.0", "end")
        self._suspend_notifications = False

        self._committed_lstar_m = None
        self._committed_lstar_mode = None
        self._committed_lstar_justification = ""
        self._committed_eps_c = None
        self._committed_eps_mode = None
        self._committed_eps_justification = ""
        self._variables["selected_lstar_m"].set("not yet applied")
        self._variables["selected_epsilon_c"].set("not yet applied")
        self._refresh_results()

    def set_runtime_context(
        self,
        inputs: InputParameters | None,
        *,
        current_bundle: ExportBundle | None = None,
    ) -> None:
        """Update the Current Design context without overwriting sandbox selections."""

        self._runtime_inputs = inputs
        self._current_bundle = current_bundle
        self._refresh_results()

    def set_unit_preset(self, _unit_preset: object) -> None:
        """Keep a stable interface with the rest of the GUI.

        The chamber sandbox intentionally stays in SI units because the empirical
        source data are curated in meters for preliminary sizing.
        """

    def get_stored_lstar_update(self) -> dict[str, object]:
        """Return the stored L* update for explicit transfer into Current Design."""

        if self._stored_lstar_update is None:
            raise InputValidationError(
                ["No stored L* selection is available yet. Use Apply L* Selection first."]
            )
        return dict(self._stored_lstar_update)

    def get_stored_geometry_updates(self) -> dict[str, object]:
        """Return the stored chamber geometry update for explicit transfer."""

        if self._stored_geometry_update is None:
            raise InputValidationError(
                ["No stored chamber geometry inputs are available yet. Use Apply Geometry Inputs first."]
            )
        return dict(self._stored_geometry_update)

    def has_stored_geometry_updates(self) -> bool:
        return self._stored_geometry_update is not None

    def has_stored_lstar_update(self) -> bool:
        return self._stored_lstar_update is not None

    def has_stored_calculation(self) -> bool:
        return self._stored_calculation is not None

    def _handle_inputs_changed(self, *_args: object) -> None:
        if self._suspend_notifications:
            return
        self._refresh_results()

    def _handle_text_changed(self, _event: object) -> None:
        if self._suspend_notifications:
            return
        self._refresh_results()

    def _handle_lstar_slider_changed(self, raw_value: str) -> None:
        if self._suspend_notifications:
            return
        self._suspend_notifications = True
        self._variables["lstar_mode"].set(SELECTION_MODE_LABELS[LStarSelectionMode.CUSTOM])
        self._variables["custom_lstar_m"].set(f"{float(raw_value):.4f}")
        self._suspend_notifications = False
        self._refresh_results()

    def _handle_eps_slider_changed(self, raw_value: str) -> None:
        if self._suspend_notifications:
            return
        self._suspend_notifications = True
        self._variables["eps_mode"].set(SELECTION_MODE_LABELS[LStarSelectionMode.CUSTOM])
        self._variables["custom_epsilon_c"].set(f"{float(raw_value):.4f}")
        self._suspend_notifications = False
        self._refresh_results()

    def _apply_lstar_selection(self) -> None:
        propellant_name = self._current_propellant_name()
        justification = self._get_text_value("lstar")
        if not justification:
            self._status_var.set("Write a short L* justification before applying the L* selection.")
            return
        selected_lstar_m = self._resolve_live_lstar(propellant_name)
        if selected_lstar_m is None:
            self._status_var.set("Current L* selection is invalid.")
            return
        mode = SELECTION_MODE_VALUES.get(self._variables["lstar_mode"].get(), LStarSelectionMode.NOMINAL)
        self._commit_lstar_selection(selected_lstar_m, mode, justification, clear_geometry=True)
        self._stored_lstar_update = {"characteristic_length_m": selected_lstar_m}
        self._stored_calc_var.set(
            f"Last Geometry Calculation: L* selection stored at {selected_lstar_m:.4f} m. Re-apply epsilon_c and geometry inputs next."
        )
        self._status_var.set(
            "L* selection was applied into Chamber Geometry Inputs. The epsilon_c tile is now unlocked."
        )
        self._refresh_results()
        if self._apply_lstar_callback is not None:
            self._apply_lstar_callback()
        if self._stored_state_changed_callback is not None:
            self._stored_state_changed_callback()

    def _apply_eps_selection(self) -> None:
        if self._committed_lstar_m is None:
            self._status_var.set("Apply L* Selection first.")
            return
        justification = self._get_text_value("contraction_ratio")
        if not justification:
            self._status_var.set("Write a short epsilon_c justification before applying the epsilon_c selection.")
            return
        guidance = self._current_eps_guidance()
        if guidance is None:
            self._status_var.set("epsilon_c guidance is not available yet. Check Dt and the selected L*.")
            return
        selected_eps = self._resolve_live_epsilon(guidance.contraction_ratio_min, guidance.contraction_ratio_max)
        if selected_eps is None:
            self._status_var.set("Current epsilon_c selection is invalid.")
            return
        mode = SELECTION_MODE_VALUES.get(self._variables["eps_mode"].get(), LStarSelectionMode.NOMINAL)
        self._commit_eps_selection(selected_eps, mode, justification)
        self._status_var.set(
            "epsilon_c selection was applied into Chamber Geometry Inputs. Store Geometry Inputs when you are ready."
        )
        self._refresh_results()
        if self._stored_state_changed_callback is not None:
            self._stored_state_changed_callback()

    def _apply_geometry_inputs(self) -> None:
        try:
            state, result = self._build_live_working_state()
            errors = validate_chamber_justifications(
                state.inputs,
                lstar_justification=state.lstar_justification,
                contraction_ratio_justification=state.contraction_ratio_justification,
            )
            if errors:
                raise InputValidationError(errors)
        except InputValidationError as exc:
            self._status_var.set(str(exc))
            return

        self._stored_geometry_update = {
            "contraction_ratio": result.contraction_ratio,
            "convergent_half_angle_deg": result.convergent_half_angle_deg,
        }
        self._stored_calculation = StoredChamberGeometryCalculation(
            working_state=state,
            result=result,
            notes=["Stored from Apply Geometry Inputs."],
        )
        self._stored_calc_var.set(
            "Last Geometry Calculation: stored from Apply Geometry Inputs "
            f"with L* = {result.selected_lstar_m:.4f} m and epsilon_c = {result.contraction_ratio:.4f}."
        )
        self._status_var.set(
            "Chamber geometry inputs were stored. Transfer them explicitly into Current Design when you want to commit them."
        )
        self._refresh_results()
        if self._apply_geometry_callback is not None:
            self._apply_geometry_callback()
        if self._stored_state_changed_callback is not None:
            self._stored_state_changed_callback()

    def _build_live_working_state(self) -> tuple[WorkingChamberGeometryState, ChamberGeometryResult]:
        chamber_model = CHAMBER_MODEL_VALUES.get(
            self._variables["chamber_model"].get(),
            ChamberGeometryModel.CYLINDRICAL,
        )
        if chamber_model is not ChamberGeometryModel.CYLINDRICAL:
            raise InputValidationError(
                [
                    "Near-spherical and spherical chamber models are prepared in the UI but not implemented yet. "
                    "Switch Chamber Geometry back to Cylindrical before storing geometry inputs."
                ]
            )

        errors: list[str] = []
        throat_diameter_m = _parse_required_float(
            self._variables["throat_diameter_m"].get(),
            "Throat diameter Dt",
            errors,
        )
        convergent_half_angle_deg = _parse_required_float(
            self._variables["convergent_half_angle_deg"].get(),
            "Convergent half angle theta",
            errors,
        )
        corner_radius_ratio = _parse_required_float(
            self._variables["corner_radius_ratio"].get(),
            "r_corner / r_t",
            errors,
        )

        if self._committed_lstar_m is None:
            errors.append("Apply the L* Selection tile first.")
        if self._committed_eps_c is None:
            errors.append("Apply the epsilon_c tile first.")
        if errors:
            raise InputValidationError(errors)

        throat_radius_m = 0.5 * throat_diameter_m
        inputs = ChamberGeometryInputs(
            propellant_name=self._current_propellant_name(),
            throat_diameter_m=throat_diameter_m,
            contraction_ratio=self._committed_eps_c or 0.0,
            convergent_half_angle_deg=convergent_half_angle_deg,
            lstar_mode=LStarSelectionMode.CUSTOM,
            custom_lstar_m=self._committed_lstar_m,
            chamber_model=chamber_model,
            corner_radius_m=corner_radius_ratio * throat_radius_m,
        )
        state = WorkingChamberGeometryState(
            inputs=inputs,
            lstar_justification=self._committed_lstar_justification,
            contraction_ratio_justification=self._committed_eps_justification,
        )
        result = calculate_chamber_geometry(inputs)
        return state, result

    def _refresh_results(self) -> None:
        propellant_name = self._current_propellant_name()
        self._current_propellant_var.set(propellant_name)
        self._refresh_lstar_tile(propellant_name)
        self._refresh_eps_tile()
        self._sync_custom_states()
        self._update_button_states()

        try:
            _state, result = self._build_live_working_state()
        except InputValidationError as exc:
            self._set_placeholder_results(str(exc), propellant_name)
            return
        except ValueError as exc:
            self._set_placeholder_results(str(exc), propellant_name)
            return

        warnings = list(result.warnings)
        if result.selected_lstar_m < result.lstar_min_m or result.selected_lstar_m > result.lstar_max_m:
            warnings.append("Selected L* lies outside the empirical SP-125 band for the current propellant pair.")

        guidance = self._current_eps_guidance()
        if guidance is not None and result.contraction_ratio > guidance.contraction_ratio_max:
            warnings.append("Selected epsilon_c lies above the approximate Fig. 8-15 preliminary band.")
        if guidance is not None and result.contraction_ratio < guidance.contraction_ratio_min:
            warnings.append("Selected epsilon_c lies below the approximate Fig. 8-15 preliminary band.")

        self._result_vars["lstar_range"].set(f"{result.lstar_min_m:.2f} to {result.lstar_max_m:.2f}")
        self._result_vars["selected_lstar"].set(f"{result.selected_lstar_m:.4f}")
        self._result_vars["throat_area"].set(f"{result.throat_area_m2:.6f}")
        self._result_vars["chamber_area"].set(f"{result.chamber_area_m2:.6f}")
        self._result_vars["throat_diameter"].set(f"{result.throat_diameter_m:.5f}")
        self._result_vars["chamber_diameter"].set(f"{result.chamber_diameter_m:.5f}")
        self._result_vars["contraction_ratio"].set(f"{result.contraction_ratio:.4f}")
        self._result_vars["convergent_half_angle"].set(f"{result.convergent_half_angle_deg:.3f}")
        self._result_vars["corner_radius_ratio"].set(
            f"{result.corner_radius_m / max(0.5 * result.throat_diameter_m, 1.0e-9):.4f}"
        )
        self._result_vars["corner_radius"].set(f"{result.corner_radius_m:.5f}")
        self._result_vars["required_chamber_volume"].set(f"{result.required_chamber_volume_m3:.6f}")
        self._result_vars["cylindrical_section_length"].set(f"{result.cylindrical_section_length_m:.5f}")
        self._result_vars["rounded_corner_length"].set(f"{result.rounded_corner_arc_length_m:.5f}")
        self._result_vars["remaining_cone_length"].set(f"{result.remaining_straight_cone_length_m:.5f}")
        self._result_vars["convergent_section_length"].set(f"{result.convergent_section_length_m:.5f}")
        self._result_vars["total_chamber_length"].set(f"{result.total_chamber_length_to_throat_m:.5f}")
        self._result_vars["hot_gas_wall_area"].set(f"{result.hot_gas_wall_area_m2:.5f}")
        self._warnings_var.set("\n".join(warnings) if warnings else "No preliminary warnings.")
        if self._stored_calculation is None:
            self._status_var.set(
                "Selections are visible in Chamber Geometry Inputs. Use Apply Geometry Inputs to store the chamber calculation."
            )
        self._draw_liner_preview(result)

    def _refresh_lstar_tile(self, propellant_name: str) -> None:
        min_m, max_m = get_lstar_range(propellant_name)
        selected_lstar_m = self._resolve_live_lstar(propellant_name)
        self._lstar_range_text_var.set(f"Empirical L* range: {min_m:.2f} to {max_m:.2f} m")
        self._lstar_slider_min_var.set(f"{min_m:.2f} m")
        self._lstar_slider_max_var.set(f"{max_m:.2f} m")
        self._lstar_selection_text_var.set(
            "selected: --" if selected_lstar_m is None else f"selected: {selected_lstar_m:.4f} m"
        )
        if self._lstar_slider is not None:
            self._lstar_slider.configure(from_=min_m, to=max_m)
            self._suspend_notifications = True
            self._lstar_slider_var.set(
                min_m if selected_lstar_m is None else min(max(selected_lstar_m, min_m), max_m)
            )
            self._suspend_notifications = False

    def _refresh_eps_tile(self) -> None:
        guidance = self._current_eps_guidance()
        if guidance is None:
            self._eps_hint_var.set("Apply L* Selection first to unlock epsilon_c guidance.")
            self._dc_dt_band_var.set("Typical Dc/Dt band: --")
            self._eps_band_var.set("Typical epsilon_c band: --")
            self._eps_slider_min_var.set("--")
            self._eps_slider_max_var.set("--")
            self._eps_selection_text_var.set("selected: --")
            self._set_eps_tile_enabled(False)
            return

        self._eps_hint_var.set("Use the Fig. 8-15 band to select a preliminary contraction ratio, then apply it.")
        self._dc_dt_band_var.set(
            f"Typical Dc/Dt band: {guidance.dc_dt_min:.2f} to {guidance.dc_dt_max:.2f}"
        )
        self._eps_band_var.set(
            f"Typical epsilon_c band: {guidance.contraction_ratio_min:.2f} to {guidance.contraction_ratio_max:.2f}"
        )
        self._eps_slider_min_var.set(f"{guidance.contraction_ratio_min:.2f}")
        self._eps_slider_max_var.set(f"{guidance.contraction_ratio_max:.2f}")
        selected_eps = self._resolve_live_epsilon(guidance.contraction_ratio_min, guidance.contraction_ratio_max)
        self._eps_selection_text_var.set(
            "selected: --" if selected_eps is None else f"selected: {selected_eps:.4f}"
        )
        if self._eps_slider is not None:
            self._eps_slider.configure(from_=guidance.contraction_ratio_min, to=guidance.contraction_ratio_max)
            self._suspend_notifications = True
            self._eps_slider_var.set(
                guidance.contraction_ratio_min
                if selected_eps is None
                else min(max(selected_eps, guidance.contraction_ratio_min), guidance.contraction_ratio_max)
            )
            self._suspend_notifications = False
        self._set_eps_tile_enabled(True)

    def _sync_custom_states(self) -> None:
        if self._custom_lstar_entry is not None:
            lstar_mode = SELECTION_MODE_VALUES.get(self._variables["lstar_mode"].get(), LStarSelectionMode.NOMINAL)
            self._custom_lstar_entry.configure(
                state="normal" if lstar_mode is LStarSelectionMode.CUSTOM else "disabled"
            )
        if self._custom_eps_entry is not None:
            eps_mode = SELECTION_MODE_VALUES.get(self._variables["eps_mode"].get(), LStarSelectionMode.NOMINAL)
            self._custom_eps_entry.configure(
                state="normal" if eps_mode is LStarSelectionMode.CUSTOM and self._committed_lstar_m is not None else "disabled"
            )

    def _update_button_states(self) -> None:
        propellant_name = self._current_propellant_name()
        lstar_ready = (
            self._resolve_live_lstar(propellant_name) is not None
            and bool(self._get_text_value("lstar"))
        )
        if self._apply_lstar_button is not None:
            self._apply_lstar_button.configure(state="normal" if lstar_ready else "disabled")

        guidance = self._current_eps_guidance()
        eps_ready = (
            guidance is not None
            and self._resolve_live_epsilon(guidance.contraction_ratio_min, guidance.contraction_ratio_max) is not None
            and bool(self._get_text_value("contraction_ratio"))
        )
        if self._apply_eps_button is not None:
            self._apply_eps_button.configure(state="normal" if eps_ready else "disabled")

        geometry_ready = self._committed_lstar_m is not None and self._committed_eps_c is not None
        if geometry_ready:
            try:
                self._build_live_working_state()
            except InputValidationError:
                geometry_ready = False
        if self._apply_geometry_button is not None:
            self._apply_geometry_button.configure(state="normal" if geometry_ready else "disabled")

    def _current_eps_guidance(self) -> object | None:
        if self._committed_lstar_m is None:
            return None
        throat_diameter = _parse_optional_float(self._variables["throat_diameter_m"].get(), "Dt", [])
        if throat_diameter is None or throat_diameter <= 0.0:
            return None
        throat_area = (math.pi / 4.0) * throat_diameter**2
        try:
            return estimate_contraction_ratio_guidance(self._committed_lstar_m * throat_area)
        except ValueError:
            return None

    def _set_eps_tile_enabled(self, enabled: bool) -> None:
        combobox_state = "readonly" if enabled else "disabled"
        entry_state = "normal" if enabled else "disabled"
        for widget in self._eps_tile_widgets:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state=combobox_state)
            elif isinstance(widget, tk.Text):
                widget.configure(state="normal" if enabled else "disabled")
            elif isinstance(widget, ttk.Scale):
                widget.configure(state="normal" if enabled else "disabled")
            elif isinstance(widget, ttk.Button):
                continue
            else:
                widget.configure(state=entry_state)

    def _commit_lstar_selection(
        self,
        selected_lstar_m: float,
        mode: LStarSelectionMode,
        justification: str,
        *,
        clear_geometry: bool,
    ) -> None:
        self._suspend_notifications = True
        self._committed_lstar_m = selected_lstar_m
        self._committed_lstar_mode = mode
        self._committed_lstar_justification = justification.strip()
        self._variables["selected_lstar_m"].set(f"{selected_lstar_m:.4f}")
        if clear_geometry:
            self._committed_eps_c = None
            self._committed_eps_mode = None
            self._committed_eps_justification = ""
            self._variables["selected_epsilon_c"].set("not yet applied")
            self._stored_geometry_update = None
            self._stored_calculation = None
            self._stored_calc_var.set("Last Geometry Calculation: not stored yet.")
        self._suspend_notifications = False

    def _commit_eps_selection(
        self,
        selected_eps_c: float,
        mode: LStarSelectionMode,
        justification: str,
    ) -> None:
        self._suspend_notifications = True
        self._committed_eps_c = selected_eps_c
        self._committed_eps_mode = mode
        self._committed_eps_justification = justification.strip()
        self._variables["selected_epsilon_c"].set(f"{selected_eps_c:.4f}")
        self._stored_geometry_update = None
        self._stored_calculation = None
        self._stored_calc_var.set("Last Geometry Calculation: not stored yet.")
        self._suspend_notifications = False

    def _resolve_live_lstar(self, propellant_name: str) -> float | None:
        mode = SELECTION_MODE_VALUES.get(self._variables["lstar_mode"].get(), LStarSelectionMode.NOMINAL)
        custom_lstar_m = _parse_optional_float(self._variables["custom_lstar_m"].get(), "Custom L*", [])
        try:
            return select_lstar_value(propellant_name, mode, custom_lstar_m=custom_lstar_m)
        except ValueError:
            return None

    def _resolve_live_epsilon(self, min_eps: float, max_eps: float) -> float | None:
        mode = SELECTION_MODE_VALUES.get(self._variables["eps_mode"].get(), LStarSelectionMode.NOMINAL)
        custom_eps = _parse_optional_float(self._variables["custom_epsilon_c"].get(), "Custom epsilon_c", [])
        if mode is LStarSelectionMode.MIN:
            return min_eps
        if mode is LStarSelectionMode.NOMINAL:
            return 0.5 * (min_eps + max_eps)
        if mode is LStarSelectionMode.MAX:
            return max_eps
        if custom_eps is None or not math.isfinite(custom_eps) or custom_eps <= 1.0:
            return None
        return custom_eps

    def _set_placeholder_results(self, status: str, propellant_name: str) -> None:
        min_m, max_m = get_lstar_range(propellant_name)
        self._result_vars["lstar_range"].set(f"{min_m:.2f} to {max_m:.2f}")
        self._result_vars["selected_lstar"].set(
            "--" if self._committed_lstar_m is None else f"{self._committed_lstar_m:.4f}"
        )
        self._result_vars["contraction_ratio"].set(
            "--" if self._committed_eps_c is None else f"{self._committed_eps_c:.4f}"
        )
        for key in (
            "throat_area",
            "chamber_area",
            "throat_diameter",
            "chamber_diameter",
            "convergent_half_angle",
            "corner_radius_ratio",
            "corner_radius",
            "required_chamber_volume",
            "cylindrical_section_length",
            "rounded_corner_length",
            "remaining_cone_length",
            "convergent_section_length",
            "total_chamber_length",
            "hot_gas_wall_area",
        ):
            self._result_vars[key].set("not yet computed")
        self._warnings_var.set("")
        if self._stored_calculation is None:
            self._status_var.set(status)
        self._draw_preview_placeholder(status)

    def _draw_liner_preview(self, result: ChamberGeometryResult) -> None:
        if self._preview_canvas is None:
            return
        self._last_preview_result = result
        canvas = self._preview_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 520)
        height = max(canvas.winfo_height(), 220)
        chamber_radius = 0.5 * result.chamber_diameter_m
        throat_radius = 0.5 * result.throat_diameter_m
        theta_rad = math.radians(result.convergent_half_angle_deg)
        arc_axial_length = result.corner_radius_m * math.sin(theta_rad)
        straight_cone_axial = max(result.convergent_section_length_m - arc_axial_length, 0.0)
        total_length = max(result.total_chamber_length_to_throat_m, 1.0e-9)
        max_radius = max(chamber_radius, throat_radius, 1.0e-9)

        x_margin = 30.0
        y_margin = 22.0
        x_scale = (width - 2.0 * x_margin) / total_length
        y_scale = (height - 2.0 * y_margin) / (2.2 * max_radius)
        scale = min(x_scale, y_scale)
        center_y = height / 2.0

        x0 = x_margin
        x1 = x0 + result.cylindrical_section_length_m * scale
        x2 = x1 + arc_axial_length * scale
        x3 = x2 + straight_cone_axial * scale
        chamber_r = chamber_radius * scale
        throat_r = throat_radius * scale
        corner_r = result.corner_radius_m * scale

        top_points: list[tuple[float, float]] = [(x0, center_y - chamber_r), (x1, center_y - chamber_r)]
        if result.corner_radius_m > 0.0 and corner_r > 0.0:
            arc_center_x = x1
            arc_center_y = center_y - chamber_r + corner_r
            arc_steps = 16
            for step in range(1, arc_steps + 1):
                angle = math.pi / 2.0 - theta_rad * (step / arc_steps)
                top_points.append(
                    (
                        arc_center_x + corner_r * math.cos(angle),
                        arc_center_y - corner_r * math.sin(angle),
                    )
                )
        top_points.append((x3, center_y - throat_r))

        bottom_points = [(x, 2.0 * center_y - y) for x, y in reversed(top_points)]
        polygon_points = [coordinate for point in (top_points + bottom_points) for coordinate in point]

        canvas.create_polygon(
            polygon_points,
            fill="#f2d2c2",
            outline="#c25b2a",
            width=2,
            smooth=False,
        )
        canvas.create_line(x3, center_y - throat_r, x3, center_y + throat_r, fill="#1f4f7a", width=2)
        canvas.create_text(x0, 10, anchor="nw", text="Cylinder", font=("Segoe UI", 8), fill="#364556")
        if result.corner_radius_m > 0.0:
            canvas.create_text(x1 + 10, 10, anchor="nw", text="Rounded corner", font=("Segoe UI", 8), fill="#364556")
        canvas.create_text(x3 - 10, 10, anchor="ne", text="Throat", font=("Segoe UI", 8), fill="#364556")

    def _draw_preview_placeholder(self, message: str) -> None:
        if self._preview_canvas is None:
            return
        self._last_preview_result = None
        canvas = self._preview_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 520)
        height = max(canvas.winfo_height(), 220)
        canvas.create_text(
            width / 2.0,
            height / 2.0,
            text=message,
            width=width - 40,
            justify="center",
            fill="#667381",
        )

    def _handle_preview_resize(self, _event: object) -> None:
        if self._last_preview_result is not None:
            self._draw_liner_preview(self._last_preview_result)
        else:
            self._draw_preview_placeholder("Apply L* and epsilon_c selections to preview the liner shape.")

    def _get_text_value(self, key: str) -> str:
        widget = self._justification_text_widgets[key]
        return widget.get("1.0", "end").strip()

    def _current_propellant_name(self, inputs: InputParameters | None = None) -> str:
        active_inputs = inputs if inputs is not None else self._runtime_inputs
        if active_inputs is None:
            return DEFAULT_LSTAR_PROPELLANT
        return suggest_lstar_propellant(active_inputs.oxidizer, active_inputs.fuel) or DEFAULT_LSTAR_PROPELLANT


def _parse_required_float(raw_value: str, label: str, errors: list[str]) -> float:
    before_count = len(errors)
    value = _parse_optional_float(raw_value, label, errors)
    if value is None:
        if len(errors) == before_count:
            errors.append(f"{label} must be a valid number.")
        return 0.0
    return value


def _parse_optional_float(raw_value: str, label: str, errors: list[str]) -> float | None:
    cleaned = raw_value.strip()
    if not cleaned:
        return None
    try:
        return float(cleaned.replace(",", "."))
    except ValueError:
        errors.append(f"{label} must be a valid number.")
        return None


def _infer_selection_mode(
    value: float,
    min_value: float,
    max_value: float,
) -> tuple[LStarSelectionMode, float | None]:
    nominal_value = 0.5 * (min_value + max_value)
    if math.isclose(value, min_value, rel_tol=0.0, abs_tol=1.0e-6):
        return LStarSelectionMode.MIN, value
    if math.isclose(value, nominal_value, rel_tol=0.0, abs_tol=1.0e-6):
        return LStarSelectionMode.NOMINAL, value
    if math.isclose(value, max_value, rel_tol=0.0, abs_tol=1.0e-6):
        return LStarSelectionMode.MAX, value
    return LStarSelectionMode.CUSTOM, value

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
    apply_chamber_geometry_result_to_inputs,
    calculate_chamber_geometry,
    chamber_geometry_result_input_updates,
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

DEFAULT_THROAT_UPSTREAM_RATIO = 1.5
DEFAULT_THROAT_DOWNSTREAM_RATIO = 0.382


class ChamberGeometryPanel(ttk.LabelFrame):
    """Interactive chamber workspace for chamber/throat draft sizing.

    ``sandbox`` keeps the earlier staged educational workflow with local Apply
    steps. ``workspace`` exposes the same values as live draft inputs that are
    committed only by the main Current Design action.
    """

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

    def __init__(self, master: tk.Misc, *, workflow_mode: str = "sandbox") -> None:
        super().__init__(master, text="Chamber and Throat Workspace", padding=12)
        self.columnconfigure(0, weight=1)
        normalized_mode = workflow_mode.strip().lower()
        self._workflow_mode = normalized_mode if normalized_mode in {"sandbox", "workspace"} else "sandbox"

        self._suspend_notifications = False
        self._apply_lstar_callback: Callable[[], None] | None = None
        self._apply_eps_callback: Callable[[], None] | None = None
        self._apply_geometry_callback: Callable[[], None] | None = None
        self._stored_state_changed_callback: Callable[[], None] | None = None
        self._inputs_changed_callback: Callable[[], None] | None = None
        self._current_bundle: ExportBundle | None = None
        self._runtime_inputs: InputParameters | None = None
        self._stored_calculation: StoredChamberGeometryCalculation | None = None
        self._stored_lstar_update: dict[str, object] | None = None
        self._stored_eps_update: dict[str, object] | None = None
        self._stored_geometry_update: dict[str, object] | None = None
        self._committed_lstar_m: float | None = None
        self._committed_lstar_mode: LStarSelectionMode | None = None
        self._committed_lstar_justification = ""
        self._committed_eps_c: float | None = None
        self._committed_eps_mode: LStarSelectionMode | None = None
        self._committed_eps_justification = ""
        self._committed_throat_upstream_ratio: float | None = None
        self._committed_throat_downstream_ratio: float | None = None
        self._last_preview_result: ChamberGeometryResult | None = None

        self._variables = {
            "chamber_model": tk.StringVar(value=CHAMBER_MODEL_LABELS[ChamberGeometryModel.CYLINDRICAL]),
            "selected_lstar_m": tk.StringVar(value="not yet applied"),
            "selected_epsilon_c": tk.StringVar(value="not yet applied"),
            "convergent_half_angle_deg": tk.StringVar(value="45.000"),
            "corner_radius_ratio": tk.StringVar(value="0.0000"),
            "throat_upstream_ratio": tk.StringVar(value=f"{DEFAULT_THROAT_UPSTREAM_RATIO:.4f}"),
            "throat_downstream_ratio": tk.StringVar(value=f"{DEFAULT_THROAT_DOWNSTREAM_RATIO:.4f}"),
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
            value="Near-spherical and spherical chamber concepts remain visible here as future work while the current predesign flow focuses on the cylindrical chamber."
        )
        self._workspace_mode_note_var = tk.StringVar(
            value=(
                "Live chamber and throat draft values are committed only by the global "
                "Commit Draft & Recalculate Current Design action."
            )
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
        self._throat_selection_text_var = tk.StringVar(value="selected: upstream -- / downstream --")

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
        self._apply_throat_button: ttk.Button | None = None
        self._apply_geometry_button: ttk.Button | None = None
        self._eps_tile_widgets: list[tk.Widget] = []
        self._preview_canvas: tk.Canvas | None = None
        self._throat_preview_canvas: tk.Canvas | None = None
        self._preview_frame: ttk.LabelFrame | None = None
        self._throat_preview_frame: ttk.LabelFrame | None = None

        self._build_widgets()
        self._refresh_results()

    def _build_widgets(self) -> None:
        chamber_section_frame = ttk.LabelFrame(self, text="Chamber Section", padding=10)
        chamber_section_frame.grid(row=0, column=0, sticky="ew")
        chamber_section_frame.columnconfigure(0, weight=3)
        chamber_section_frame.columnconfigure(1, weight=2)

        left_frame = ttk.Frame(chamber_section_frame)
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

        ttk.Label(input_frame, text="Selected L* [m]").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(
            input_frame,
            textvariable=self._variables["selected_lstar_m"],
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(input_frame, text="Selected epsilon_c [-]").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(
            input_frame,
            textvariable=self._variables["selected_epsilon_c"],
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Label(input_frame, text="Convergent half angle theta [deg]").grid(
            row=4, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(input_frame, textvariable=self._variables["convergent_half_angle_deg"]).grid(
            row=4, column=1, sticky="ew", pady=4
        )

        ttk.Label(input_frame, text="r_corner / r_t [-]").grid(row=5, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(input_frame, textvariable=self._variables["corner_radius_ratio"]).grid(
            row=5, column=1, sticky="ew", pady=4
        )

        ttk.Label(
            input_frame,
            text=(
                "Dt is taken from the last calculated Current Design throat sizing. "
                "Use the L*, epsilon_c and throat tiles on the right to commit preliminary selections into these chamber inputs."
            ),
            wraplength=500,
            justify="left",
        ).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        if self._workflow_mode == "workspace":
            ttk.Label(
                input_frame,
                textvariable=self._workspace_mode_note_var,
                wraplength=500,
                justify="left",
                foreground="#53606d",
            ).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        else:
            apply_frame = ttk.Frame(input_frame)
            apply_frame.grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))
            self._apply_geometry_button = ttk.Button(
                apply_frame,
                text="Apply Chamber Geometry",
                command=self._apply_geometry_inputs,
                width=22,
            )
            self._apply_geometry_button.grid(row=0, column=0, sticky="w")

        result_frame = ttk.LabelFrame(left_frame, text="Chamber Geometry Calculation", padding=10)
        result_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
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

        preview_frame = ttk.LabelFrame(left_frame, text="Chamber Geometry Preview", padding=10)
        preview_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        preview_frame.columnconfigure(0, weight=1)
        self._preview_frame = preview_frame
        preview_canvas = tk.Canvas(preview_frame, height=220, background="#f7f8fb", highlightthickness=0)
        preview_canvas.grid(row=0, column=0, sticky="ew")
        preview_canvas.bind("<Configure>", self._handle_preview_resize)
        self._preview_canvas = preview_canvas

        right_frame = ttk.Frame(chamber_section_frame)
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

        if self._workflow_mode == "workspace":
            ttk.Label(
                lstar_frame,
                text="Live draft value. The global Current Design commit will use this L* directly.",
                wraplength=420,
                justify="left",
                foreground="#53606d",
            ).grid(row=9, column=0, sticky="ew", pady=(8, 0))
        else:
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

        if self._workflow_mode == "workspace":
            ttk.Label(
                eps_frame,
                text="Live draft value. The global Current Design commit will use this contraction ratio directly.",
                wraplength=420,
                justify="left",
                foreground="#53606d",
            ).grid(row=10, column=0, sticky="ew", pady=(8, 0))
        else:
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

        chamber_empty_tile = ttk.LabelFrame(right_frame, text="", padding=10)
        chamber_empty_tile.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        ttk.Label(chamber_empty_tile, text="").grid(row=0, column=0, pady=70)

        throat_section_frame = ttk.LabelFrame(self, text="Throat Section", padding=10)
        throat_section_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        throat_section_frame.columnconfigure(0, weight=1)
        throat_section_frame.columnconfigure(1, weight=1)

        throat_frame = ttk.LabelFrame(throat_section_frame, text="Throat Section", padding=10)
        throat_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        throat_frame.columnconfigure(1, weight=1)

        ttk.Label(throat_frame, text="Upstream radius R_up / Rt [-]").grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(throat_frame, textvariable=self._variables["throat_upstream_ratio"]).grid(
            row=0, column=1, sticky="ew", pady=4
        )
        ttk.Label(throat_frame, text="Downstream radius R_down / Rt [-]").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(throat_frame, textvariable=self._variables["throat_downstream_ratio"]).grid(
            row=1, column=1, sticky="ew", pady=4
        )
        ttk.Label(
            throat_frame,
            text=(
                "Nominal preliminary throat-blend radii: upstream 1.500 Rt, downstream 0.382 Rt. "
                "The closeup below focuses on the downstream throat blend from x/Rt = 0.2 to 0.6."
            ),
            wraplength=420,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(
            throat_frame,
            textvariable=self._throat_selection_text_var,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        if self._workflow_mode == "workspace":
            ttk.Label(
                throat_frame,
                text="Live draft value. The global Current Design commit will use the current throat blend directly.",
                wraplength=420,
                justify="left",
                foreground="#53606d",
            ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        else:
            apply_throat_row = ttk.Frame(throat_frame)
            apply_throat_row.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
            apply_throat_button = ttk.Button(
                apply_throat_row,
                text="Apply Throat Radii",
                command=self._apply_throat_selection,
                width=18,
            )
            apply_throat_button.grid(row=0, column=0, sticky="w")
            self._apply_throat_button = apply_throat_button

        throat_preview_frame = ttk.LabelFrame(throat_section_frame, text="Throat Geometry Closeup", padding=10)
        throat_preview_frame.grid(row=0, column=1, sticky="nsew")
        throat_preview_frame.columnconfigure(0, weight=1)
        self._throat_preview_frame = throat_preview_frame
        throat_preview_canvas = tk.Canvas(
            throat_preview_frame,
            height=220,
            background="#f7f8fb",
            highlightthickness=0,
        )
        throat_preview_canvas.grid(row=0, column=0, sticky="ew")
        throat_preview_canvas.bind("<Configure>", self._handle_throat_preview_resize)
        self._throat_preview_canvas = throat_preview_canvas
        if self._workflow_mode == "workspace":
            preview_frame.grid_remove()
            throat_preview_frame.grid_remove()

    def bind_apply_selected_lstar(self, callback: Callable[[], None]) -> None:
        """Bind a callback after L* is stored for explicit Current Design transfer."""

        self._apply_lstar_callback = callback

    def bind_apply_selected_eps(self, callback: Callable[[], None]) -> None:
        """Bind a callback after epsilon_c is stored for explicit Current Design transfer."""

        self._apply_eps_callback = callback

    def bind_apply_geometry_inputs(self, callback: Callable[[], None]) -> None:
        """Bind a callback after chamber geometry is stored for explicit transfer."""

        self._apply_geometry_callback = callback

    def bind_stored_state_changed(self, callback: Callable[[], None]) -> None:
        """Bind a callback whenever a stored chamber state changes."""

        self._stored_state_changed_callback = callback

    def bind_inputs_changed(self, callback: Callable[[], None]) -> None:
        """Bind a callback fired when live chamber/throat draft values change."""

        self._inputs_changed_callback = callback

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
        self._stored_eps_update = None
        self._stored_geometry_update = None
        self._stored_calc_var.set("Last Geometry Calculation: not stored yet.")
        self._warnings_var.set("")
        self._status_var.set(
            "Apply L* and epsilon_c selections, then store the chamber geometry calculation."
            if self._workflow_mode != "workspace"
            else "Live chamber/throat draft is ready. Commit it through Current Design when you want to refresh the authoritative contour."
        )

        propellant_name = self._current_propellant_name(inputs)
        throat_diameter_m = self._current_throat_diameter_m(current_bundle)
        lstar_value = inputs.characteristic_length_m
        if lstar_value is None:
            lstar_value = select_lstar_value(propellant_name, LStarSelectionMode.NOMINAL)
        lstar_mode, custom_lstar = infer_lstar_mode(propellant_name, lstar_value)

        guidance = None
        if throat_diameter_m is not None and throat_diameter_m > 0.0:
            guidance = estimate_contraction_ratio_guidance(
                lstar_value * (math.pi / 4.0) * throat_diameter_m**2
            )

        if guidance is not None:
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
        else:
            eps_value = inputs.contraction_ratio if inputs.contraction_ratio is not None and inputs.contraction_ratio > 1.0 else None
            eps_mode = LStarSelectionMode.CUSTOM if eps_value is not None else LStarSelectionMode.NOMINAL
            custom_eps = eps_value

        throat_radius_m = None if throat_diameter_m is None else 0.5 * throat_diameter_m
        upstream_ratio = DEFAULT_THROAT_UPSTREAM_RATIO
        downstream_ratio = DEFAULT_THROAT_DOWNSTREAM_RATIO
        if (
            throat_radius_m is not None
            and throat_radius_m > 0.0
            and inputs.throat_upstream_radius_m is not None
            and inputs.throat_upstream_radius_m > 0.0
        ):
            upstream_ratio = inputs.throat_upstream_radius_m / throat_radius_m
        if (
            throat_radius_m is not None
            and throat_radius_m > 0.0
            and inputs.throat_downstream_radius_m is not None
            and inputs.throat_downstream_radius_m > 0.0
        ):
            downstream_ratio = inputs.throat_downstream_radius_m / throat_radius_m

        self._suspend_notifications = True
        self._variables["convergent_half_angle_deg"].set(f"{inputs.convergent_half_angle_deg:.3f}")
        if (
            throat_radius_m is not None
            and throat_radius_m > 0.0
            and inputs.chamber_corner_radius_m is not None
            and inputs.chamber_corner_radius_m >= 0.0
        ):
            corner_radius_ratio = inputs.chamber_corner_radius_m / throat_radius_m
        else:
            corner_radius_ratio = 0.0
        self._variables["corner_radius_ratio"].set(f"{corner_radius_ratio:.4f}")
        self._variables["throat_upstream_ratio"].set(f"{upstream_ratio:.4f}")
        self._variables["throat_downstream_ratio"].set(f"{downstream_ratio:.4f}")
        self._variables["lstar_mode"].set(SELECTION_MODE_LABELS[lstar_mode])
        self._variables["custom_lstar_m"].set("" if custom_lstar is None else f"{custom_lstar:.4f}")
        self._variables["eps_mode"].set(SELECTION_MODE_LABELS[eps_mode])
        self._variables["custom_epsilon_c"].set("" if custom_eps is None else f"{custom_eps:.4f}")
        for widget in self._justification_text_widgets.values():
            widget.delete("1.0", "end")
        self._suspend_notifications = False

        if self._workflow_mode == "workspace":
            self._committed_lstar_m = lstar_value
            self._committed_lstar_mode = lstar_mode
            self._committed_lstar_justification = ""
            self._committed_eps_c = eps_value
            self._committed_eps_mode = eps_mode if eps_value is not None else None
            self._committed_eps_justification = ""
            self._committed_throat_upstream_ratio = upstream_ratio
            self._committed_throat_downstream_ratio = downstream_ratio
            self._variables["selected_lstar_m"].set(f"{lstar_value:.4f}")
            self._variables["selected_epsilon_c"].set(
                "not yet applied" if eps_value is None else f"{eps_value:.4f}"
            )
        else:
            self._committed_lstar_m = None
            self._committed_lstar_mode = None
            self._committed_lstar_justification = ""
            self._committed_eps_c = None
            self._committed_eps_mode = None
            self._committed_eps_justification = ""
            self._committed_throat_upstream_ratio = None
            self._committed_throat_downstream_ratio = None
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

    def get_stored_eps_update(self) -> dict[str, object]:
        """Return the stored epsilon_c update for explicit transfer into Current Design."""

        if self._stored_eps_update is None:
            raise InputValidationError(
                ["No stored epsilon_c selection is available yet. Use Apply epsilon_c first."]
            )
        return dict(self._stored_eps_update)

    def get_stored_geometry_updates(self) -> dict[str, object]:
        """Return the stored chamber geometry update for explicit transfer."""

        if self._stored_geometry_update is None:
            raise InputValidationError(
                ["No stored chamber geometry inputs are available yet. Use Apply Chamber Geometry first."]
            )
        return dict(self._stored_geometry_update)

    def get_live_preview_updates(self) -> dict[str, object]:
        """Return valid draft chamber and throat values for live contour previewing."""

        throat_diameter_m = self._current_throat_diameter_m()
        if throat_diameter_m is None or throat_diameter_m <= 0.0:
            return {}

        preview_updates: dict[str, object] = {}
        throat_radius_m = 0.5 * throat_diameter_m
        upstream_ratio, downstream_ratio = self._resolve_live_throat_ratios()
        propellant_name = self._current_propellant_name()
        if upstream_ratio is not None:
            preview_updates["throat_upstream_radius_m"] = upstream_ratio * throat_radius_m
        if downstream_ratio is not None:
            preview_updates["throat_downstream_radius_m"] = downstream_ratio * throat_radius_m
        live_lstar_m = self._resolve_live_lstar(propellant_name)
        if live_lstar_m is not None:
            preview_updates["characteristic_length_m"] = live_lstar_m
        guidance = self._current_eps_guidance()
        if guidance is not None:
            live_eps = self._resolve_live_epsilon(guidance.contraction_ratio_min, guidance.contraction_ratio_max)
            if live_eps is not None:
                preview_updates["contraction_ratio"] = live_eps
        errors: list[str] = []
        convergent_half_angle_deg = _parse_required_float(
            self._variables["convergent_half_angle_deg"].get(),
            "Convergent half angle theta",
            errors,
        )
        corner_radius_ratio = _parse_optional_float(
            self._variables["corner_radius_ratio"].get(),
            "r_corner / r_t",
            errors,
        )
        if not errors:
            preview_updates["convergent_half_angle_deg"] = convergent_half_angle_deg
            if corner_radius_ratio is not None and corner_radius_ratio >= 0.0:
                preview_updates["chamber_corner_radius_m"] = corner_radius_ratio * throat_radius_m
        return preview_updates

    def get_live_commit_updates(self) -> dict[str, object]:
        """Return strict chamber/throat draft values for Current Design commits."""

        throat_diameter_m = self._current_throat_diameter_m()
        errors: list[str] = []
        if throat_diameter_m is None or throat_diameter_m <= 0.0:
            raise InputValidationError(
                ["Current throat sizing is unavailable. Calculate the baseline Current Design first."]
            )

        throat_radius_m = 0.5 * throat_diameter_m
        propellant_name = self._current_propellant_name()
        selected_lstar_m = self._resolve_live_lstar(propellant_name)
        if selected_lstar_m is None:
            errors.append("L* selection is invalid.")

        guidance = self._current_eps_guidance(lstar_value=selected_lstar_m)
        selected_eps = None
        if guidance is not None:
            selected_eps = self._resolve_live_epsilon(
                guidance.contraction_ratio_min,
                guidance.contraction_ratio_max,
            )
        if selected_eps is None:
            errors.append("epsilon_c selection is invalid or unavailable.")

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
        if corner_radius_ratio < 0.0:
            errors.append("r_corner / r_t must be zero or positive.")

        upstream_ratio, downstream_ratio = self._resolve_live_throat_ratios()
        if upstream_ratio is None or upstream_ratio <= 0.0:
            errors.append("Upstream throat radius ratio is invalid.")
        if downstream_ratio is None or downstream_ratio <= 0.0:
            errors.append("Downstream throat radius ratio is invalid.")

        if errors:
            raise InputValidationError(errors)

        return {
            "characteristic_length_m": selected_lstar_m,
            "contraction_ratio": selected_eps,
            "convergent_half_angle_deg": convergent_half_angle_deg,
            "chamber_corner_radius_m": corner_radius_ratio * throat_radius_m,
            "throat_upstream_radius_m": upstream_ratio * throat_radius_m,
            "throat_downstream_radius_m": downstream_ratio * throat_radius_m,
        }

    def has_stored_geometry_updates(self) -> bool:
        return self._stored_geometry_update is not None

    def has_stored_eps_update(self) -> bool:
        return self._stored_eps_update is not None

    def has_stored_lstar_update(self) -> bool:
        return self._stored_lstar_update is not None

    def has_stored_calculation(self) -> bool:
        return self._stored_calculation is not None

    def _handle_inputs_changed(self, *_args: object) -> None:
        if self._suspend_notifications:
            return
        self._refresh_results()
        if self._inputs_changed_callback is not None:
            self._inputs_changed_callback()

    def _handle_text_changed(self, _event: object) -> None:
        if self._suspend_notifications:
            return
        self._refresh_results()
        if self._inputs_changed_callback is not None:
            self._inputs_changed_callback()

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
            self._status_var.set(
                "epsilon_c guidance is not available yet. Calculate Current Design first so the throat sizing can be reused here."
            )
            return
        selected_eps = self._resolve_live_epsilon(guidance.contraction_ratio_min, guidance.contraction_ratio_max)
        if selected_eps is None:
            self._status_var.set("Current epsilon_c selection is invalid.")
            return
        mode = SELECTION_MODE_VALUES.get(self._variables["eps_mode"].get(), LStarSelectionMode.NOMINAL)
        self._commit_eps_selection(selected_eps, mode, justification)
        self._stored_eps_update = {"contraction_ratio": selected_eps}
        self._status_var.set(
            "epsilon_c selection was applied into Chamber Geometry Inputs. Store Geometry Inputs when you are ready."
        )
        self._refresh_results()
        if self._apply_eps_callback is not None:
            self._apply_eps_callback()
        if self._stored_state_changed_callback is not None:
            self._stored_state_changed_callback()

    def _apply_throat_selection(self) -> None:
        upstream_ratio, downstream_ratio = self._resolve_live_throat_ratios()
        if upstream_ratio is None or downstream_ratio is None:
            self._status_var.set("Current throat-radius selection is invalid.")
            return
        self._commit_throat_selection(upstream_ratio, downstream_ratio)
        self._status_var.set(
            "Throat blend radii were applied into the chamber sandbox. Store Geometry Inputs when you are ready."
        )
        self._refresh_results()
        if self._stored_state_changed_callback is not None:
            self._stored_state_changed_callback()

    def _apply_geometry_inputs(self) -> None:
        if self._committed_throat_upstream_ratio is None or self._committed_throat_downstream_ratio is None:
            self._status_var.set("Apply the Throat Geometry tile first.")
            return
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

        base_inputs = self._runtime_inputs
        if base_inputs is None:
            self._status_var.set("Current Design inputs are not available for chamber-geometry handoff.")
            return
        mapped_inputs = apply_chamber_geometry_result_to_inputs(base_inputs, result)
        mapped_updates, handoff_notes = chamber_geometry_result_input_updates(base_inputs, result)
        self._stored_geometry_update = {
            **mapped_updates,
            "throat_upstream_radius_m": (self._committed_throat_upstream_ratio or 0.0) * (0.5 * result.throat_diameter_m),
            "throat_downstream_radius_m": (self._committed_throat_downstream_ratio or 0.0) * (0.5 * result.throat_diameter_m),
        }
        self._stored_calculation = StoredChamberGeometryCalculation(
            working_state=state,
            result=result,
            notes=[
                "Stored from Apply Chamber Geometry.",
                f"Explicit InputParameters handoff uses L*={mapped_inputs.characteristic_length_m:.4f} m, "
                f"epsilon_c={mapped_inputs.contraction_ratio:.4f}, "
                f"theta={mapped_inputs.convergent_half_angle_deg:.2f} deg and corner radius={mapped_inputs.chamber_corner_radius_m:.5f} m.",
                *handoff_notes,
            ],
        )
        self._stored_calc_var.set(
            "Last Geometry Calculation: stored from Apply Chamber Geometry "
            f"with L* = {result.selected_lstar_m:.4f} m, epsilon_c = {result.contraction_ratio:.4f}, "
            f"R_up/Rt = {self._committed_throat_upstream_ratio:.4f} and R_down/Rt = {self._committed_throat_downstream_ratio:.4f}."
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

        active_lstar_m = (
            self._resolve_live_lstar(self._current_propellant_name())
            if self._workflow_mode == "workspace"
            else self._committed_lstar_m
        )
        active_eps_c: float | None
        if self._workflow_mode == "workspace":
            guidance = self._current_eps_guidance(lstar_value=active_lstar_m)
            active_eps_c = (
                None
                if guidance is None
                else self._resolve_live_epsilon(
                    guidance.contraction_ratio_min,
                    guidance.contraction_ratio_max,
                )
            )
        else:
            active_eps_c = self._committed_eps_c
        if active_lstar_m is None:
            errors.append(
                "L* draft is invalid." if self._workflow_mode == "workspace" else "Apply the L* Selection tile first."
            )
        if active_eps_c is None:
            errors.append(
                "epsilon_c draft is invalid or unavailable."
                if self._workflow_mode == "workspace"
                else "Apply the epsilon_c tile first."
            )
        throat_diameter_m = self._current_throat_diameter_m()
        if throat_diameter_m is None:
            errors.append(
                "Calculate Current Design first to provide throat sizing for Chamber Geometry."
            )
        if errors:
            raise InputValidationError(errors)

        throat_radius_m = 0.5 * throat_diameter_m
        inputs = ChamberGeometryInputs(
            propellant_name=self._current_propellant_name(),
            throat_diameter_m=throat_diameter_m,
            contraction_ratio=active_eps_c or 0.0,
            convergent_half_angle_deg=convergent_half_angle_deg,
            lstar_mode=LStarSelectionMode.CUSTOM,
            custom_lstar_m=active_lstar_m,
            chamber_model=chamber_model,
            corner_radius_m=corner_radius_ratio * throat_radius_m,
        )
        state = WorkingChamberGeometryState(
            inputs=inputs,
            lstar_justification=self._committed_lstar_justification if self._workflow_mode != "workspace" else "",
            contraction_ratio_justification=self._committed_eps_justification if self._workflow_mode != "workspace" else "",
        )
        result = calculate_chamber_geometry(inputs)
        return state, result

    def _refresh_results(self) -> None:
        propellant_name = self._current_propellant_name()
        self._current_propellant_var.set(propellant_name)
        self._refresh_lstar_tile(propellant_name)
        self._refresh_eps_tile()
        self._refresh_throat_tile()
        self._sync_custom_states()
        self._update_button_states()
        if self._workflow_mode == "workspace":
            live_lstar_m = self._resolve_live_lstar(propellant_name)
            self._variables["selected_lstar_m"].set(
                "not yet applied" if live_lstar_m is None else f"{live_lstar_m:.4f}"
            )

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
        if self._workflow_mode == "workspace":
            self._variables["selected_epsilon_c"].set(f"{result.contraction_ratio:.4f}")
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
                "Selections are visible in Chamber Geometry Inputs. Use Apply Chamber Geometry to store the chamber calculation."
                if self._workflow_mode != "workspace"
                else "Selections are visible in the live draft preview. Use Commit Draft & Recalculate Current Design to refresh the committed contour."
            )
        self._draw_liner_preview(result)
        self._refresh_throat_preview()

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
            if self._workflow_mode == "workspace":
                self._eps_hint_var.set(
                    "Use the current live L* draft and committed throat sizing to unlock epsilon_c guidance."
                )
            elif self._committed_lstar_m is None:
                self._eps_hint_var.set("Apply L* Selection first to unlock epsilon_c guidance.")
            elif self._current_throat_diameter_m() is None:
                self._eps_hint_var.set(
                    "Calculate Current Design first to provide Dt and unlock epsilon_c guidance."
                )
            else:
                self._eps_hint_var.set("epsilon_c guidance is not available yet.")
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

    def _refresh_throat_tile(self) -> None:
        upstream_ratio, downstream_ratio = self._resolve_live_throat_ratios()
        if upstream_ratio is None or downstream_ratio is None:
            self._throat_selection_text_var.set("Live: --")
            return
        selection_text = f"Live: upstream {upstream_ratio:.4f} Rt, downstream {downstream_ratio:.4f} Rt"
        if (
            self._committed_throat_upstream_ratio is not None
            and self._committed_throat_downstream_ratio is not None
        ):
            selection_text += (
                f"\nApplied: upstream {self._committed_throat_upstream_ratio:.4f} Rt, "
                f"downstream {self._committed_throat_downstream_ratio:.4f} Rt"
            )
        self._throat_selection_text_var.set(selection_text)

    def _sync_custom_states(self) -> None:
        if self._custom_lstar_entry is not None:
            lstar_mode = SELECTION_MODE_VALUES.get(self._variables["lstar_mode"].get(), LStarSelectionMode.NOMINAL)
            self._custom_lstar_entry.configure(
                state="normal" if lstar_mode is LStarSelectionMode.CUSTOM else "disabled"
            )
        if self._custom_eps_entry is not None:
            eps_mode = SELECTION_MODE_VALUES.get(self._variables["eps_mode"].get(), LStarSelectionMode.NOMINAL)
            self._custom_eps_entry.configure(
                state="normal" if eps_mode is LStarSelectionMode.CUSTOM and self._current_eps_guidance() is not None else "disabled"
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

        throat_upstream_ratio, throat_downstream_ratio = self._resolve_live_throat_ratios()
        if self._apply_throat_button is not None:
            self._apply_throat_button.configure(
                state="normal"
                if throat_upstream_ratio is not None and throat_downstream_ratio is not None
                else "disabled"
            )

        geometry_ready = (
            self._committed_lstar_m is not None
            and self._committed_eps_c is not None
            and self._committed_throat_upstream_ratio is not None
            and self._committed_throat_downstream_ratio is not None
        )
        if geometry_ready:
            try:
                self._build_live_working_state()
            except InputValidationError:
                geometry_ready = False
        if self._apply_geometry_button is not None:
            self._apply_geometry_button.configure(state="normal" if geometry_ready else "disabled")

    def _current_eps_guidance(self, *, lstar_value: float | None = None) -> object | None:
        active_lstar_m = lstar_value
        if active_lstar_m is None:
            active_lstar_m = (
                self._resolve_live_lstar(self._current_propellant_name())
                if self._workflow_mode == "workspace"
                else self._committed_lstar_m
            )
        if active_lstar_m is None:
            return None
        throat_diameter = self._current_throat_diameter_m()
        if throat_diameter is None or throat_diameter <= 0.0:
            return None
        throat_area = (math.pi / 4.0) * throat_diameter**2
        try:
            return estimate_contraction_ratio_guidance(active_lstar_m * throat_area)
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
            self._stored_eps_update = None
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
        self._stored_eps_update = None
        self._stored_geometry_update = None
        self._stored_calculation = None
        self._stored_calc_var.set("Last Geometry Calculation: not stored yet.")
        self._suspend_notifications = False

    def _commit_throat_selection(
        self,
        upstream_ratio: float,
        downstream_ratio: float,
    ) -> None:
        self._suspend_notifications = True
        self._committed_throat_upstream_ratio = upstream_ratio
        self._committed_throat_downstream_ratio = downstream_ratio
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

    def _resolve_live_throat_ratios(self) -> tuple[float | None, float | None]:
        errors: list[str] = []
        upstream_ratio = _parse_required_float(
            self._variables["throat_upstream_ratio"].get(),
            "Upstream throat radius ratio",
            errors,
        )
        downstream_ratio = _parse_required_float(
            self._variables["throat_downstream_ratio"].get(),
            "Downstream throat radius ratio",
            errors,
        )
        if errors:
            return None, None
        if upstream_ratio <= 0.0 or downstream_ratio <= 0.0:
            return None, None
        return upstream_ratio, downstream_ratio

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
        self._refresh_throat_preview()

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
        inner_polygon_points = [coordinate for point in (top_points + bottom_points) for coordinate in point]
        canvas.create_polygon(
            inner_polygon_points,
            fill="#f2d2c2",
            outline="#c25b2a",
            width=2,
            smooth=False,
        )
        canvas.create_line(
            x3,
            center_y - throat_r,
            x3,
            center_y + throat_r,
            fill="#1f4f7a",
            width=2,
        )
        label_color = "#364556"
        canvas.create_text(x0, 10, anchor="nw", text="Cylinder", font=("Segoe UI", 8), fill=label_color)
        if result.corner_radius_m > 0.0:
            canvas.create_text(
                x1 + 10,
                10,
                anchor="nw",
                text="Rounded corner",
                font=("Segoe UI", 8),
                fill=label_color,
            )
        canvas.create_text(x3 - 10, 10, anchor="ne", text="Throat", font=("Segoe UI", 8, "bold"), fill=label_color)

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
            self._draw_preview_placeholder(
                "Apply L* and epsilon_c selections and use a calculated Current Design throat size to preview the chamber geometry."
            )

    def _refresh_throat_preview(self) -> None:
        if self._throat_preview_canvas is None:
            return
        upstream_ratio, downstream_ratio = self._resolve_live_throat_ratios()
        if upstream_ratio is None or downstream_ratio is None:
            self._draw_throat_preview_placeholder(
                "Enter valid upstream and downstream throat radii to preview the local throat shape."
            )
            return

        canvas = self._throat_preview_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 520)
        height = max(canvas.winfo_height(), 220)
        x_margin = 34.0
        y_margin = 20.0
        plot_left = x_margin
        plot_right = width - x_margin
        plot_top = y_margin + 18.0
        plot_bottom = height - y_margin - 18.0
        center_y = 0.5 * (plot_top + plot_bottom)
        x_min_norm = 0.2
        x_max_norm = 0.6
        radial_min = 0.98
        radial_max = 1.0 + max(downstream_ratio, 0.35) + 0.10

        def map_x(x_norm: float) -> float:
            return plot_left + (
                (x_norm - x_min_norm) / max(x_max_norm - x_min_norm, 1.0e-9)
            ) * (plot_right - plot_left)

        def radial_to_offset(radius_norm: float) -> float:
            normalized = (radius_norm - radial_min) / max(radial_max - radial_min, 1.0e-9)
            return normalized * (center_y - plot_top)

        def map_y_top(radius_norm: float) -> float:
            return center_y - radial_to_offset(radius_norm)

        def map_y_bottom(radius_norm: float) -> float:
            return center_y + radial_to_offset(radius_norm)

        canvas.create_rectangle(0, 0, width, height, fill="#f7f8fb", outline="")
        canvas.create_rectangle(
            plot_left,
            plot_top,
            plot_right,
            plot_bottom,
            fill="#fcfdff",
            outline="#d5dde6",
            width=1,
        )

        for x_norm, label in ((0.2, "0.2 Rt"), (0.4, "0.4 Rt"), (0.6, "0.6 Rt")):
            x_pos = map_x(x_norm)
            dash = (3, 3)
            color = "#d7dee6"
            width_px = 1
            canvas.create_line(x_pos, plot_top, x_pos, plot_bottom, fill=color, dash=dash, width=width_px)
            canvas.create_text(x_pos, plot_bottom + 10, text=label, fill="#5d6977", font=("Segoe UI", 8))

        canvas.create_line(plot_left, center_y, plot_right, center_y, fill="#d3dce5", dash=(4, 3))
        throat_top_y = map_y_top(1.0)
        throat_bottom_y = map_y_bottom(1.0)
        canvas.create_line(plot_left, throat_top_y, plot_right, throat_top_y, fill="#e3e8ee", dash=(2, 4))
        canvas.create_line(plot_left, throat_bottom_y, plot_right, throat_bottom_y, fill="#e3e8ee", dash=(2, 4))
        canvas.create_text(plot_left + 6, throat_top_y - 8, anchor="w", text="Rt", fill="#647180", font=("Segoe UI", 8))

        def build_arc_xy(start_x: float, end_x: float, ratio: float, samples: int = 48) -> list[tuple[float, float, float]]:
            points: list[tuple[float, float, float]] = []
            for step in range(samples + 1):
                x_norm = start_x + (end_x - start_x) * (step / samples)
                radial_offset = max(ratio**2 - x_norm**2, 0.0)
                radius_norm = 1.0 + ratio - math.sqrt(radial_offset)
                points.append((x_norm, map_x(x_norm), radius_norm))
            return points

        downstream_extent = min(x_max_norm, max(downstream_ratio, 0.0))
        downstream_start = x_min_norm
        downstream_points = (
            build_arc_xy(downstream_start, downstream_extent, downstream_ratio)
            if downstream_extent > downstream_start
            else []
        )

        def draw_region(
            points: list[tuple[float, float, float]],
            *,
            fill: str,
            outline: str,
            accent: str,
        ) -> None:
            if len(points) < 2:
                return
            polygon_points: list[float] = []
            for _x_norm, x_pos, radius_norm in points:
                polygon_points.extend((x_pos, map_y_top(radius_norm)))
            for _x_norm, x_pos, radius_norm in reversed(points):
                polygon_points.extend((x_pos, map_y_bottom(radius_norm)))
            canvas.create_polygon(
                polygon_points,
                fill=fill,
                outline="",
            )
            top_line = [coordinate for _x_norm, x_pos, radius_norm in points for coordinate in (x_pos, map_y_top(radius_norm))]
            bottom_line = [
                coordinate
                for _x_norm, x_pos, radius_norm in points
                for coordinate in (x_pos, map_y_bottom(radius_norm))
            ]
            canvas.create_line(*top_line, fill=outline, width=2.5, smooth=True)
            canvas.create_line(*bottom_line, fill=outline, width=2.5, smooth=True)
            start_x = points[0][1]
            end_x = points[-1][1]
            canvas.create_line(start_x, map_y_top(points[0][2]), start_x, map_y_bottom(points[0][2]), fill=accent, width=1)
            canvas.create_line(end_x, map_y_top(points[-1][2]), end_x, map_y_bottom(points[-1][2]), fill=accent, width=1)

        draw_region(
            downstream_points,
            fill="#dfe9f5",
            outline="#2c628f",
            accent="#c1d4e7",
        )

        canvas.create_text(
            width / 2.0,
            8,
            anchor="n",
            text="Downstream throat closeup, scaled by Rt",
            fill="#334250",
            font=("Segoe UI", 8, "bold"),
        )
        canvas.create_text(
            plot_left + 8,
            plot_top + 8,
            anchor="nw",
            text=f"R_down = {downstream_ratio:.4f} Rt",
            fill="#25557e",
            font=("Segoe UI", 8, "bold"),
        )

        if downstream_points:
            end_x_norm, end_x, end_radius = downstream_points[-1]
            end_angle = math.asin(min(max(end_x_norm / max(downstream_ratio, 1.0e-9), -1.0), 1.0))
            tangent_slope = math.tan(end_angle)
            if x_max_norm > end_x_norm and tangent_slope > 0.0:
                end_top_y = map_y_top(end_radius)
                end_bottom_y = map_y_bottom(end_radius)
                continuation_end_x = map_x(x_max_norm)
                continuation_dx = x_max_norm - end_x_norm
                continuation_radius = end_radius + tangent_slope * continuation_dx
                continuation_top_y = map_y_top(continuation_radius)
                continuation_bottom_y = map_y_bottom(continuation_radius)
                canvas.create_line(
                    end_x,
                    end_top_y,
                    continuation_end_x,
                    continuation_top_y,
                    fill="#6e7d8a",
                    dash=(4, 3),
                    width=2,
                )
                canvas.create_line(
                    end_x,
                    end_bottom_y,
                    continuation_end_x,
                    continuation_bottom_y,
                    fill="#6e7d8a",
                    dash=(4, 3),
                    width=2,
                )
        if downstream_extent < x_max_norm:
            continuation_x = map_x(max(downstream_extent, x_min_norm))
            canvas.create_text(
                continuation_x + 12,
                center_y - 18,
                anchor="w",
                text="nozzle contour continues",
                fill="#6e7d8a",
                font=("Segoe UI", 8),
            )

    def _draw_throat_preview_placeholder(self, message: str) -> None:
        if self._throat_preview_canvas is None:
            return
        canvas = self._throat_preview_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 520)
        height = max(canvas.winfo_height(), 220)
        canvas.create_rectangle(0, 0, width, height, fill="#f7f8fb", outline="")
        canvas.create_rectangle(34, 38, width - 34, height - 38, fill="#fcfdff", outline="#d5dde6", width=1)
        canvas.create_text(
            width / 2.0,
            height / 2.0,
            text=message,
            width=width - 40,
            justify="center",
            fill="#667381",
        )

    def _handle_throat_preview_resize(self, _event: object) -> None:
        self._refresh_throat_preview()

    def _get_text_value(self, key: str) -> str:
        widget = self._justification_text_widgets[key]
        return widget.get("1.0", "end").strip()

    def _current_propellant_name(self, inputs: InputParameters | None = None) -> str:
        active_inputs = inputs if inputs is not None else self._runtime_inputs
        if active_inputs is None:
            return DEFAULT_LSTAR_PROPELLANT
        return suggest_lstar_propellant(active_inputs.oxidizer, active_inputs.fuel) or DEFAULT_LSTAR_PROPELLANT

    def _current_throat_diameter_m(self, bundle: ExportBundle | None = None) -> float | None:
        active_bundle = bundle if bundle is not None else self._current_bundle
        if active_bundle is None:
            return None
        throat_radius_m = active_bundle.geometry.throat_radius_m
        if throat_radius_m is None or not math.isfinite(throat_radius_m) or throat_radius_m <= 0.0:
            return None
        return 2.0 * throat_radius_m


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

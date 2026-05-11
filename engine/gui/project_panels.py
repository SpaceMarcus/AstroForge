"""Project-management and dashboard panels for AstraForge."""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable

from engine.flow import FlowCase, FlowCaseAssessment
from engine.models import ExportBundle, InputParameters
from engine.project_state import (
    MODULE_LABELS,
    MODULE_ORDER,
    PROJECT_MODE_LABELS,
    STATUS_COLORS,
    ModuleStatus,
    ProjectManagementData,
    ProjectMode,
    ProjectState,
)
from engine.unit_system import UnitPreset, format_quantity


class ScrollableContentFrame(ttk.Frame):
    """Reusable scrollable content area with a fixed outer container."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(self, highlightthickness=0, background="#f7f8fb")
        self._scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar.grid(row=0, column=1, sticky="ns")

        self.content = ttk.Frame(self._canvas, padding=(0, 0, 0, 0))
        self.content.columnconfigure(0, weight=1)
        self._window_id = self._canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.content.bind("<Configure>", self._handle_content_configure)
        self._canvas.bind("<Configure>", self._handle_canvas_configure)
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)

    def _handle_content_configure(self, _event: object) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _handle_canvas_configure(self, event: object) -> None:
        width = getattr(event, "width", None)
        if width is not None:
            self._canvas.itemconfigure(self._window_id, width=width)

    def _bind_mousewheel(self, _event: object) -> None:
        self._canvas.bind_all("<MouseWheel>", self._handle_mousewheel)

    def _unbind_mousewheel(self, _event: object) -> None:
        self._canvas.unbind_all("<MouseWheel>")

    def _handle_mousewheel(self, event: object) -> None:
        delta = getattr(event, "delta", 0)
        if delta:
            self._canvas.yview_scroll(int(-delta / 120), "units")


class FlowCasePanel(ttk.LabelFrame):
    """Compact plausibility-check panel for design input tabs."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Plausibility Check", padding=12)
        self.columnconfigure(0, weight=1)
        self._title_var = tk.StringVar(value="Awaiting valid operating conditions.")
        self._detail_var = tk.StringVar(
            value="Enter Pc and Pa to classify the case as subsonic/unchoked or choked/supersonic."
        )
        self._ratio_var = tk.StringVar(value="")

        ttk.Label(
            self,
            textvariable=self._title_var,
            font=("Segoe UI", 11, "bold"),
            wraplength=420,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            self,
            textvariable=self._detail_var,
            wraplength=420,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(
            self,
            textvariable=self._ratio_var,
            wraplength=420,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(6, 0))

    def set_assessment(self, assessment: FlowCaseAssessment | None) -> None:
        """Show the current flow-case result or a neutral placeholder."""

        if assessment is None:
            self._title_var.set("Awaiting valid operating conditions.")
            self._detail_var.set(
                "Enter Pc and Pa to classify the case as subsonic/unchoked or choked/supersonic."
            )
            self._ratio_var.set("")
            return

        self._title_var.set(assessment.title)
        self._detail_var.set(assessment.message)
        self._ratio_var.set(
            "Current pa/pc = "
            f"{assessment.current_back_pressure_ratio:.4f}, critical pa/pc = "
            f"{assessment.critical_back_pressure_ratio:.4f} "
            f"(gamma = {assessment.gamma_used:.3f}, source = {assessment.gamma_source})."
        )


class ProjectManagementPanel(ttk.LabelFrame):
    """Optional project-management and requirement inputs for guided workflows."""

    _TEXT_FIELD_DEFINITIONS = [
        ("mission_objectives", "Mission objectives"),
        ("requirements", "Requirements"),
        ("constraints", "Constraints"),
        ("budgets", "Budgets"),
    ]

    _ENTRY_FIELD_DEFINITIONS = [
        ("thrust_requirement", "Thrust requirement"),
        ("pressure_requirement", "Vacuum / ambient requirement"),
        ("throttling_requirement", "Throttling requirement"),
        ("max_length", "Max length"),
        ("wall_temperature_constraint", "Wall temperature constraint"),
        ("manufacturing_constraint", "Manufacturing / material constraint"),
        ("mass_budget", "Mass budget"),
    ]

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Project Management", padding=12)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        self._change_callback: Callable[[], None] | None = None
        self._suspend_notifications = False
        self._project_mode = ProjectMode.SANDBOX
        self._system_engineering_enabled = tk.BooleanVar(value=False)
        self._allow_initial_design_editing_after_run = tk.BooleanVar(value=False)
        self._mode_note_var = tk.StringVar(value="")
        self._setup_status_var = tk.StringVar(value="")
        self._se_toggle: ttk.Checkbutton | None = None
        self._entry_variables = {
            key: tk.StringVar()
            for key, _label in self._ENTRY_FIELD_DEFINITIONS
        }
        self._text_widgets: dict[str, tk.Text] = {}
        self._build_widgets()

    def _build_widgets(self) -> None:
        context_frame = ttk.LabelFrame(self, text="Workflow Context", padding=10)
        context_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        context_frame.columnconfigure(0, weight=1)

        ttk.Label(
            context_frame,
            textvariable=self._mode_note_var,
            wraplength=980,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

        self._se_toggle = ttk.Checkbutton(
            context_frame,
            text="Enable system-engineering requirement overlays",
            variable=self._system_engineering_enabled,
            command=self._notify_changed,
        )
        self._se_toggle.grid(row=1, column=0, sticky="w", pady=(8, 0))

        ttk.Checkbutton(
            context_frame,
            text="Allow further editing in Initial Design after the baseline run",
            variable=self._allow_initial_design_editing_after_run,
            command=self._notify_changed,
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))

        mission_frame = ttk.LabelFrame(self, text="Mission and Scope", padding=10)
        mission_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(10, 0))
        mission_frame.columnconfigure(0, weight=1)
        mission_frame.rowconfigure(1, weight=1)
        mission_frame.rowconfigure(3, weight=1)
        mission_frame.rowconfigure(5, weight=1)
        mission_frame.rowconfigure(7, weight=1)

        for index, (key, label) in enumerate(self._TEXT_FIELD_DEFINITIONS):
            row = index * 2
            ttk.Label(mission_frame, text=label).grid(row=row, column=0, sticky="w")
            text_widget = tk.Text(mission_frame, height=4, wrap="word")
            text_widget.grid(row=row + 1, column=0, sticky="nsew", pady=(4, 8))
            text_widget.bind("<KeyRelease>", self._handle_text_edited)
            text_widget.bind("<FocusOut>", self._handle_text_edited)
            self._text_widgets[key] = text_widget

        requirements_frame = ttk.LabelFrame(self, text="Requirement Drivers", padding=10)
        requirements_frame.grid(row=1, column=1, sticky="nsew", pady=(10, 0))
        requirements_frame.columnconfigure(1, weight=1)

        for row, (key, label) in enumerate(self._ENTRY_FIELD_DEFINITIONS):
            ttk.Label(requirements_frame, text=label).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 10),
                pady=4,
            )
            ttk.Entry(
                requirements_frame,
                textvariable=self._entry_variables[key],
            ).grid(row=row, column=1, sticky="ew", pady=4)
            self._entry_variables[key].trace_add("write", self._handle_entry_edited)

        ttk.Label(
            self,
            textvariable=self._setup_status_var,
            wraplength=1000,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        self.set_project_context(ProjectMode.SANDBOX, system_engineering_enabled=False)

    def bind_project_changed(self, callback: Callable[[], None]) -> None:
        """Bind a callback for edits to project-management content."""

        self._change_callback = callback

    def set_project_context(
        self,
        project_mode: ProjectMode,
        *,
        system_engineering_enabled: bool,
    ) -> None:
        """Update the workflow mode note and SE toggle behavior."""

        self._suspend_notifications = True
        self._project_mode = project_mode
        if project_mode is ProjectMode.SANDBOX:
            self._system_engineering_enabled.set(False)
            self._mode_note_var.set(
                "Sandbox / Learn keeps project-management content optional. "
                "You can leave mission, requirements, constraints and budgets empty and still work freely."
            )
            if self._se_toggle is not None:
                self._se_toggle.configure(state="disabled")
        else:
            self._system_engineering_enabled.set(bool(system_engineering_enabled))
            self._mode_note_var.set(
                "Guided Project activates project context, requirement overlays and completeness hints "
                "without touching the core solver."
            )
            if self._se_toggle is not None:
                self._se_toggle.configure(state="normal")
        self._suspend_notifications = False

    def set_project_data(self, project_management: ProjectManagementData) -> None:
        """Populate the project-management fields from central state."""

        self._suspend_notifications = True
        self._allow_initial_design_editing_after_run.set(
            bool(project_management.allow_initial_design_editing_after_run)
        )
        for key, widget in self._text_widgets.items():
            widget.delete("1.0", "end")
            widget.insert("1.0", getattr(project_management, key))
        for key, variable in self._entry_variables.items():
            variable.set(getattr(project_management, key))
        self._suspend_notifications = False

    def set_project_setup_status(self, status: ModuleStatus, message: str) -> None:
        """Show the current guided/sandbox project-setup interpretation."""

        self._setup_status_var.set(f"{MODULE_LABELS['project_setup']}: {message}")

    def get_project_management_data(self) -> ProjectManagementData:
        """Return the current project-management content as a dataclass."""

        return ProjectManagementData(
            allow_initial_design_editing_after_run=self._allow_initial_design_editing_after_run.get(),
            mission_objectives=self._get_text_value("mission_objectives"),
            requirements=self._get_text_value("requirements"),
            constraints=self._get_text_value("constraints"),
            budgets=self._get_text_value("budgets"),
            thrust_requirement=self._entry_variables["thrust_requirement"].get().strip(),
            pressure_requirement=self._entry_variables["pressure_requirement"].get().strip(),
            throttling_requirement=self._entry_variables["throttling_requirement"].get().strip(),
            max_length=self._entry_variables["max_length"].get().strip(),
            wall_temperature_constraint=self._entry_variables["wall_temperature_constraint"].get().strip(),
            manufacturing_constraint=self._entry_variables["manufacturing_constraint"].get().strip(),
            mass_budget=self._entry_variables["mass_budget"].get().strip(),
        )

    def is_system_engineering_enabled(self) -> bool:
        """Return whether system-engineering overlays are enabled."""

        return self._system_engineering_enabled.get() and self._project_mode is ProjectMode.GUIDED

    def is_initial_design_editing_allowed(self) -> bool:
        """Return whether the user explicitly allows editing Initial Design after the baseline run."""

        return self._allow_initial_design_editing_after_run.get()

    def _get_text_value(self, key: str) -> str:
        return self._text_widgets[key].get("1.0", "end").strip()

    def _handle_entry_edited(self, *_args: object) -> None:
        self._notify_changed()

    def _handle_text_edited(self, _event: object) -> None:
        self._notify_changed()

    def _notify_changed(self) -> None:
        if self._suspend_notifications:
            return
        if self._change_callback is not None:
            self._change_callback()


class DashboardSummaryPanel(ttk.LabelFrame):
    """Compact textual dashboard summary for the overview tab."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset = UnitPreset.SI_CAD) -> None:
        super().__init__(master, text="Dashboard Summary", padding=12)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._unit_preset = unit_preset
        self._text = tk.Text(self, height=18, wrap="word", state="disabled")
        self._text.grid(row=0, column=0, sticky="nsew")

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update the display preset used by the dashboard summary."""

        self._unit_preset = unit_preset

    def update_dashboard(
        self,
        project_state: ProjectState,
        *,
        bundle: ExportBundle | None,
        current_inputs: InputParameters | None,
    ) -> None:
        """Refresh the textual project summary shown next to the dashboard."""

        lines = [
            f"Project mode: {PROJECT_MODE_LABELS[project_state.project_mode]}",
            (
                "System engineering: active"
                if project_state.system_engineering_enabled
                else "System engineering: reduced / skipped"
            ),
            f"{MODULE_LABELS['project_setup']}: {project_state.module_messages.get('project_setup', '--')}",
            "",
        ]
        if project_state.flow_case_assessment is not None:
            lines.extend(
                [
                    f"Flow case: {project_state.flow_case_assessment.title}",
                    project_state.flow_case_assessment.message,
                    "",
                ]
            )

        if project_state.project_management.mission_objectives.strip():
            lines.append(
                "Mission objectives: "
                + _short_text(project_state.project_management.mission_objectives)
            )
        if project_state.project_management.requirements.strip():
            lines.append(
                "Requirements: "
                + _short_text(project_state.project_management.requirements)
            )
        if project_state.project_management.constraints.strip():
            lines.append(
                "Constraints: "
                + _short_text(project_state.project_management.constraints)
            )
        if project_state.project_management.budgets.strip():
            lines.append(
                "Budgets: "
                + _short_text(project_state.project_management.budgets)
            )
        if len(lines) > 4:
            lines.append("")

        if current_inputs is not None:
            lines.append(
                f"Current setup: {current_inputs.oxidizer} / {current_inputs.fuel}, "
                f"Thrust {format_quantity(current_inputs.thrust_n, 'force', self._unit_preset, include_unit=True)}, "
                f"Pc {format_quantity(current_inputs.chamber_pressure_pa, 'pressure', self._unit_preset, include_unit=True)}"
            )
            lines.append(
                f"Baseline contour: {current_inputs.contour_method.value}"
                + (
                    f" / {current_inputs.bell_variant.value}"
                    if current_inputs.contour_method.value == "bell"
                    else ""
                )
            )
            lines.append(
                f"Mixture ratio {current_inputs.mixture_ratio:.4f}, eps {current_inputs.expansion_ratio:.4f}"
            )
            lines.append(
                f"Material baseline: {current_inputs.liner_material}"
                + (
                    f" with {current_inputs.liner_coating}"
                    if current_inputs.liner_coating_enabled and current_inputs.liner_coating
                    else ""
                )
            )
            lines.append(
                "Manufacturing: "
                f"{current_inputs.manufacturing_mode.value} / {current_inputs.manufacturing_route.value}"
            )
            lines.append(
                "Wall thickness: "
                + (
                    format_quantity(current_inputs.wall_thickness_m, "length", self._unit_preset, include_unit=True)
                    if current_inputs.wall_thickness_mode.value == "constant"
                    else "variable (future-ready)"
                )
            )
            lines.append("")

        if bundle is not None:
            lines.append(
                f"Latest result: Isp_vac {format_quantity(bundle.thermochemistry.isp_vac_s, 'isp', self._unit_preset, include_unit=True)}, "
                f"c* {format_quantity(bundle.thermochemistry.c_star_m_s, 'velocity', self._unit_preset, include_unit=True)}"
            )
            lines.append(
                f"Nozzle length {format_quantity(bundle.geometry.current_nozzle_length_m, 'length', self._unit_preset, include_unit=True)}, "
                f"Mass flow {format_quantity(bundle.geometry.mass_flow_kg_per_s, 'mass_flow', self._unit_preset, include_unit=True)}"
            )
            lines.append(
                f"Thermochemistry: {project_state.module_messages.get('thermochemistry', '--')}"
            )
        else:
            lines.append(
                "No current calculation bundle is active. Use Initial Design to seed Current Design, then calculate in Current Design."
            )

        self._set_text("\n".join(lines).strip())

    def _set_text(self, text: str) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text)
        self._text.configure(state="disabled")


class ProjectDashboardPanel(ttk.LabelFrame):
    """Status lamps plus MBSE-style 2D engine silhouette for the overview tab."""

    _COMPONENT_TARGETS = {
        "requirements": (0.15, 0.17),
        "injector": (0.12, 0.52),
        "chamber": (0.28, 0.52),
        "throat": (0.42, 0.52),
        "nozzle": (0.62, 0.52),
        "liner": (0.33, 0.70),
        "wall": (0.45, 0.76),
        "cooling": (0.52, 0.28),
        "performance": (0.83, 0.52),
    }

    _COMPONENT_MODULES = {
        "requirements": "project_setup",
        "injector": "thermochemistry",
        "chamber": "geometry",
        "throat": "contour",
        "nozzle": "contour",
        "liner": "material",
        "wall": "material",
        "cooling": "cooling",
        "performance": "performance",
    }

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset = UnitPreset.SI_CAD) -> None:
        super().__init__(master, text="Overview Dashboard", padding=12)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._unit_preset = unit_preset
        self._project_state: ProjectState | None = None
        self._bundle: ExportBundle | None = None
        self._current_inputs: InputParameters | None = None

        self._indicator_vars: dict[str, tk.StringVar] = {}
        indicator_frame = ttk.Frame(self)
        indicator_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for column in range(4):
            indicator_frame.columnconfigure(column, weight=1)

        self._indicator_canvases: dict[str, tk.Canvas] = {}
        for index, module_key in enumerate(MODULE_ORDER):
            card = ttk.Frame(indicator_frame, padding=6)
            card.grid(row=index // 4, column=index % 4, sticky="nsew", padx=4, pady=4)
            status_canvas = tk.Canvas(card, width=18, height=18, highlightthickness=0, bg="#f7f8fb")
            status_canvas.grid(row=0, column=0, sticky="w")
            status_canvas.create_oval(2, 2, 16, 16, fill=STATUS_COLORS[ModuleStatus.IDLE], outline="")
            ttk.Label(card, text=MODULE_LABELS[module_key], font=("Segoe UI", 9, "bold")).grid(
                row=0,
                column=1,
                sticky="w",
                padx=(6, 0),
            )
            message_var = tk.StringVar(value="")
            ttk.Label(
                card,
                textvariable=message_var,
                wraplength=180,
                justify="left",
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
            self._indicator_canvases[module_key] = status_canvas
            self._indicator_vars[module_key] = message_var

        self._canvas = tk.Canvas(self, background="#f7f8fb", highlightthickness=0)
        self._canvas.grid(row=1, column=0, sticky="nsew")
        self._canvas.bind("<Configure>", self._handle_canvas_configure)

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update display units for current-value callouts."""

        self._unit_preset = unit_preset
        self._redraw_canvas()

    def update_dashboard(
        self,
        project_state: ProjectState,
        *,
        bundle: ExportBundle | None,
        current_inputs: InputParameters | None,
    ) -> None:
        """Refresh status lamps and the MBSE-style engine dashboard."""

        self._project_state = project_state
        self._bundle = bundle
        self._current_inputs = current_inputs
        self._refresh_indicators()
        self._redraw_canvas()

    def _refresh_indicators(self) -> None:
        if self._project_state is None:
            return
        for module_key in MODULE_ORDER:
            status = self._project_state.module_statuses.get(module_key, ModuleStatus.IDLE)
            message = self._project_state.module_messages.get(module_key, "")
            canvas = self._indicator_canvases[module_key]
            canvas.delete("all")
            canvas.create_oval(2, 2, 16, 16, fill=STATUS_COLORS[status], outline="")
            self._indicator_vars[module_key].set(message)

    def _handle_canvas_configure(self, _event: object) -> None:
        self._redraw_canvas()

    def _redraw_canvas(self) -> None:
        self._canvas.delete("all")
        if self._project_state is None:
            return

        width = max(self._canvas.winfo_width(), 860)
        height = max(self._canvas.winfo_height(), 420)
        center_y = height * 0.58

        injector = (width * 0.10, center_y - 34, width * 0.16, center_y + 34)
        chamber = (width * 0.16, center_y - 58, width * 0.37, center_y + 58)
        throat = (width * 0.37, center_y - 22, width * 0.42, center_y + 22)
        performance = (width * 0.77, center_y - 40, width * 0.92, center_y + 40)
        requirements_box = (width * 0.06, height * 0.10, width * 0.24, height * 0.20)

        outer_nozzle = [
            width * 0.42,
            center_y - 26,
            width * 0.72,
            center_y - 72,
            width * 0.72,
            center_y + 72,
            width * 0.42,
            center_y + 26,
        ]
        inner_liner = [
            width * 0.18,
            center_y - 42,
            width * 0.36,
            center_y - 42,
            width * 0.42,
            center_y - 18,
            width * 0.69,
            center_y - 58,
            width * 0.69,
            center_y + 58,
            width * 0.42,
            center_y + 18,
            width * 0.36,
            center_y + 42,
            width * 0.18,
            center_y + 42,
        ]
        cooling_outline = [
            width * 0.15,
            center_y - 80,
            width * 0.38,
            center_y - 80,
            width * 0.74,
            center_y - 102,
            width * 0.74,
            center_y - 80,
            width * 0.45,
            center_y - 32,
            width * 0.38,
            center_y - 70,
            width * 0.15,
            center_y - 70,
        ]

        self._canvas.create_text(
            width * 0.03,
            height * 0.04,
            anchor="nw",
            text="MBSE-style engine context",
            font=("Segoe UI", 12, "bold"),
            fill="#22303d",
        )

        self._draw_box(requirements_box, "requirements", "Requirements\n/ Interfaces")
        self._draw_box(injector, "injector", "Injector")
        self._draw_box(chamber, "chamber", "Chamber")
        self._draw_box(throat, "throat", "Throat")
        self._draw_box(performance, "performance", "Performance")

        nozzle_color = self._component_color("nozzle")
        self._canvas.create_polygon(
            outer_nozzle,
            fill=nozzle_color,
            outline="#243444",
            width=2,
            smooth=True,
        )
        self._canvas.create_text(
            width * 0.58,
            center_y,
            text="Nozzle",
            font=("Segoe UI", 10, "bold"),
            fill="#101010",
        )

        liner_color = self._component_color("liner")
        self._canvas.create_polygon(
            inner_liner,
            outline=liner_color,
            fill="",
            width=3,
            smooth=True,
        )
        self._canvas.create_text(
            width * 0.27,
            center_y + 92,
            text="Liner",
            font=("Segoe UI", 9),
            fill="#364556",
        )

        wall_color = self._component_color("wall")
        self._canvas.create_polygon(
            [
                width * 0.16,
                center_y - 56,
                width * 0.37,
                center_y - 56,
                width * 0.42,
                center_y - 24,
                width * 0.72,
                center_y - 70,
                width * 0.72,
                center_y + 70,
                width * 0.42,
                center_y + 24,
                width * 0.37,
                center_y + 56,
                width * 0.16,
                center_y + 56,
            ],
            outline=wall_color,
            fill="",
            width=2,
            smooth=True,
        )
        self._canvas.create_text(
            width * 0.40,
            center_y + 118,
            text="Wall / material",
            font=("Segoe UI", 9),
            fill="#364556",
        )

        cooling_color = self._component_color("cooling")
        self._canvas.create_line(cooling_outline, fill=cooling_color, width=10, smooth=True)
        self._canvas.create_text(
            width * 0.53,
            center_y - 118,
            text="Cooling",
            font=("Segoe UI", 9),
            fill="#364556",
        )

        if self._project_state.system_engineering_enabled:
            self._draw_requirement_overlays(width, height)
        else:
            self._canvas.create_text(
                width * 0.64,
                height * 0.16,
                anchor="nw",
                text="Requirement overlays stay hidden while system engineering is reduced.",
                width=250,
                font=("Segoe UI", 9),
                fill="#667381",
            )

    def _draw_box(self, bounds: tuple[float, float, float, float], component_key: str, label: str) -> None:
        fill_color = self._component_color(component_key)
        self._canvas.create_rectangle(
            *bounds,
            fill=fill_color,
            outline="#243444",
            width=2,
        )
        self._canvas.create_text(
            (bounds[0] + bounds[2]) / 2.0,
            (bounds[1] + bounds[3]) / 2.0,
            text=label,
            font=("Segoe UI", 10, "bold"),
            justify="center",
            fill="#101010",
        )

    def _draw_requirement_overlays(self, width: float, height: float) -> None:
        if self._project_state is None:
            return

        overlay_positions = {
            "requirements": (width * 0.04, height * 0.02),
            "injector": (width * 0.03, height * 0.30),
            "nozzle": (width * 0.42, height * 0.03),
            "wall": (width * 0.18, height * 0.82),
            "liner": (width * 0.05, height * 0.70),
            "performance": (width * 0.72, height * 0.16),
        }

        for overlay in self._project_state.requirement_overlays[:7]:
            x, y = overlay_positions.get(overlay.target, (width * 0.08, height * 0.08))
            current_value = self._current_value_hint(overlay.title)
            text = overlay.text if not current_value else f"{overlay.text}\nCurrent: {current_value}"
            text_id = self._canvas.create_text(
                x + 8,
                y + 8,
                anchor="nw",
                width=220,
                text=f"{overlay.title}\n{text}",
                font=("Segoe UI", 9),
                fill="#1f2b37",
            )
            bbox = self._canvas.bbox(text_id)
            if bbox is None:
                continue
            outline_color = self._component_color(overlay.target)
            rect_id = self._canvas.create_rectangle(
                bbox[0] - 6,
                bbox[1] - 6,
                bbox[2] + 6,
                bbox[3] + 6,
                fill="#fffdf8",
                outline=outline_color,
                width=2,
            )
            self._canvas.tag_lower(rect_id, text_id)

            target_x, target_y = self._target_coordinates(overlay.target, width, height)
            self._canvas.create_line(
                bbox[2] + 6,
                (bbox[1] + bbox[3]) / 2.0,
                target_x,
                target_y,
                fill=outline_color,
                width=2,
                arrow="last",
            )

    def _target_coordinates(self, component_key: str, width: float, height: float) -> tuple[float, float]:
        normalized_x, normalized_y = self._COMPONENT_TARGETS.get(component_key, (0.20, 0.20))
        return width * normalized_x, height * normalized_y

    def _component_color(self, component_key: str) -> str:
        if self._project_state is None:
            return STATUS_COLORS[ModuleStatus.IDLE]
        module_key = self._COMPONENT_MODULES.get(component_key, "project_setup")
        status = self._project_state.module_statuses.get(module_key, ModuleStatus.IDLE)
        return STATUS_COLORS[status]

    def _current_value_hint(self, overlay_title: str) -> str:
        bundle = self._bundle
        current_inputs = self._current_inputs

        if overlay_title == "Thrust requirement" and current_inputs is not None:
            return format_quantity(current_inputs.thrust_n, "force", self._unit_preset, include_unit=True)

        if overlay_title == "Vacuum / ambient requirement":
            if bundle is not None:
                return (
                    f"Pa {format_quantity(bundle.inputs.ambient_pressure_pa, 'pressure', self._unit_preset, include_unit=True)}, "
                    f"Isp_vac {format_quantity(bundle.thermochemistry.isp_vac_s, 'isp', self._unit_preset, include_unit=True)}"
                )
            if current_inputs is not None:
                return format_quantity(current_inputs.ambient_pressure_pa, "pressure", self._unit_preset, include_unit=True)

        if overlay_title == "Max length" and bundle is not None:
            return format_quantity(bundle.geometry.current_nozzle_length_m, "length", self._unit_preset, include_unit=True)

        if overlay_title == "Wall temperature constraint" and bundle is not None:
            wall_temperatures = [
                point.state.adiabatic_wall_temperature_k
                for point in bundle.thermochemistry_profile
                if point.state.adiabatic_wall_temperature_k is not None
            ]
            if wall_temperatures:
                return format_quantity(max(wall_temperatures), "temperature", self._unit_preset, include_unit=True)

        if overlay_title == "Manufacturing / material" and current_inputs is not None:
            return current_inputs.liner_material

        if overlay_title == "Mass budget" and bundle is not None:
            return (
                "engine mass model pending; "
                f"m_dot {format_quantity(bundle.geometry.mass_flow_kg_per_s, 'mass_flow', self._unit_preset, include_unit=True)}"
            )

        return ""


def _short_text(text: str, *, limit: int = 120) -> str:
    cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."

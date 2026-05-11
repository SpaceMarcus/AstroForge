"""Main Tkinter window for the AstraForge rocket-engine predesign tool."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Protocol

from engine.chemistry.base import ThermochemistryBackendError
from engine.flow import classify_input_flow_case
from engine.geometry import build_contour_markers, predict_separation_point
from engine.gui.chamber_geometry_panel import ChamberGeometryPanel
from engine.gui.input_panel import InputPanel
from engine.gui.plotting import ContourPlotFrame, OFSweepPlotFrame, SpeciesProfilePlotFrame
from engine.gui.project_panels import (
    DashboardSummaryPanel,
    FlowCasePanel,
    ProjectDashboardPanel,
    ProjectManagementPanel,
    ScrollableContentFrame,
)
from engine.gui.result_panel import (
    ComparisonPanel,
    GeometryDetailsPanel,
    GeometryMaterialEditorPanel,
    MaterialOptionsPanel,
    SummaryPanel,
)
from engine.io import export_engine_preset, load_engine_preset
from engine.models import ExportBundle, InputParameters, OFSweepMetric, OFSweepPoint, ThermochemistryProfilePoint
from engine.performance_preview import compute_performance_preview
from engine.project_state import (
    PROJECT_MODE_LABELS,
    ProjectMode,
    ProjectState,
    apply_project_management_settings,
    clear_calculation_results,
    create_project_state,
    mark_calculation_failed,
    mark_calculation_running,
    mark_calculation_success,
    mark_design_inputs_changed,
    set_project_mode,
    set_flow_case_assessment,
)
from engine.unit_system import UnitPreset, UNIT_PRESET_LABELS, format_quantity
from engine.utils.validation import InputValidationError


class ApplicationController(Protocol):
    """Minimal controller contract consumed by the GUI."""

    def run_case(self, inputs: InputParameters) -> ExportBundle: ...

    def export_case(
        self,
        bundle: ExportBundle,
        output_stem: str | Path,
        unit_preset: UnitPreset = UnitPreset.SI,
    ) -> dict[str, Path]: ...

    def export_geometry_json(
        self,
        bundle: ExportBundle,
        target_path: str | Path,
        unit_preset: UnitPreset = UnitPreset.SI,
    ) -> Path: ...

    def export_geometry_csv(
        self,
        bundle: ExportBundle,
        target_path: str | Path,
        unit_preset: UnitPreset = UnitPreset.SI,
    ) -> Path: ...


class MainWindow(tk.Tk):
    """Desktop GUI with dashboard, project setup and engineering tabs."""

    def __init__(
        self,
        controller: ApplicationController,
        example_input_factory: Callable[[], InputParameters],
    ) -> None:
        super().__init__()
        self.title("AstraForge")
        self.geometry("1460x980")
        self.minsize(1200, 860)

        self._controller = controller
        self._example_input_factory = example_input_factory
        self._current_bundle: ExportBundle | None = None
        self._current_separation_point = None
        self._selected_profile_point: ThermochemistryProfilePoint | None = None
        self._selected_sweep_mixture_ratio: float | None = None
        self._last_preset_path: Path | None = None
        self._unit_preset = UnitPreset.SI_CAD
        self._project_state: ProjectState = create_project_state()
        self._applied_detail_overrides: dict[str, object] = {}
        self._current_design_linked_to_initial = True
        self._initial_design_locked = False
        self._initial_design_snapshot: InputParameters | None = None
        self._pending_initial_design_lock_inputs: InputParameters | None = None
        self._working_geometry_updates: dict[str, object] | None = None
        self._working_material_updates: dict[str, object] | None = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._error_var = tk.StringVar(value="")
        self._status_var = tk.StringVar(value="AstraForge ready.")
        self._of_metric_var = tk.StringVar(value=OFSweepMetric.ISP_VAC.value)
        self._selected_of_var = tk.StringVar(value="")
        self._of_summary_var = tk.StringVar(value="Run a calculation to populate the O/F sweep.")
        self._unit_preset_var = tk.StringVar(value=self._unit_preset.value)
        self._project_mode_var = tk.StringVar(value=self._project_state.project_mode.value)

        self._build_menu()
        self._build_layout()
        self._apply_project_state_to_ui(reset_project_data=True)
        self.load_example_values(clear_results=True)

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="New", command=self.new_case)
        file_menu.add_command(label="New Window", command=self.open_new_window)
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self.save_engine_preset)
        file_menu.add_command(label="Save As...", command=self.save_engine_preset_as)
        file_menu.add_command(label="Load...", command=self.load_engine_preset_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu_bar.add_cascade(label="File", menu=file_menu)

        unit_menu = tk.Menu(menu_bar, tearoff=False)
        for preset in UnitPreset:
            unit_menu.add_radiobutton(
                label=UNIT_PRESET_LABELS[preset],
                value=preset.value,
                variable=self._unit_preset_var,
                command=self._on_unit_preset_selected,
            )
        menu_bar.add_cascade(label="Unit", menu=unit_menu)

        self.config(menu=menu_bar)

    def _build_layout(self) -> None:
        header_frame = ttk.Frame(self, padding=(16, 10, 16, 8))
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.columnconfigure(0, weight=1)

        ttk.Label(
            header_frame,
            text="AstraForge",
            font=("Segoe UI", 20, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header_frame,
            text="Rocket-engine predesign with RocketCEA-backed thermochemistry and geometry previews.",
        ).grid(row=1, column=0, sticky="w", pady=(2, 6))

        mode_frame = ttk.Frame(header_frame)
        mode_frame.grid(row=2, column=0, sticky="w")
        ttk.Label(mode_frame, text="Project mode").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Radiobutton(
            mode_frame,
            text=PROJECT_MODE_LABELS[ProjectMode.GUIDED],
            value=ProjectMode.GUIDED.value,
            variable=self._project_mode_var,
            command=self._on_project_mode_selected,
        ).grid(row=0, column=1, sticky="w", padx=(0, 10))
        ttk.Radiobutton(
            mode_frame,
            text=PROJECT_MODE_LABELS[ProjectMode.SANDBOX],
            value=ProjectMode.SANDBOX.value,
            variable=self._project_mode_var,
            command=self._on_project_mode_selected,
        ).grid(row=0, column=2, sticky="w")

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self._notebook = notebook

        project_management_tab = ttk.Frame(notebook, padding=8)
        project_management_tab.columnconfigure(0, weight=1)
        project_management_tab.rowconfigure(0, weight=1)
        notebook.add(project_management_tab, text="Project Management")

        overview_tab = ttk.Frame(notebook, padding=8)
        overview_tab.columnconfigure(0, weight=0)
        overview_tab.columnconfigure(1, weight=1)
        overview_tab.rowconfigure(0, weight=1)
        notebook.add(overview_tab, text="Overview")

        initial_design_tab = ttk.Frame(notebook, padding=8)
        initial_design_tab.columnconfigure(0, weight=1)
        initial_design_tab.rowconfigure(0, weight=1)
        notebook.add(initial_design_tab, text="Initial Design")
        self._initial_design_tab = initial_design_tab

        current_design_tab = ttk.Frame(notebook, padding=8)
        current_design_tab.columnconfigure(0, weight=1)
        current_design_tab.rowconfigure(0, weight=1)
        notebook.add(current_design_tab, text="Current Design")
        self._current_design_tab = current_design_tab

        geometry_tab = ttk.Frame(notebook, padding=8)
        geometry_tab.columnconfigure(0, weight=1)
        geometry_tab.rowconfigure(0, weight=1)
        notebook.add(geometry_tab, text="Geometry and Material")

        thermo_tab = ttk.Frame(notebook, padding=8)
        thermo_tab.columnconfigure(0, weight=1)
        thermo_tab.rowconfigure(0, weight=1)
        notebook.add(thermo_tab, text="Thermo Chemistry")

        comparison_tab = ttk.Frame(notebook, padding=8)
        comparison_tab.columnconfigure(0, weight=1)
        comparison_tab.rowconfigure(0, weight=1)
        notebook.add(comparison_tab, text="Comparison")

        report_tab = ttk.Frame(notebook, padding=8)
        report_tab.columnconfigure(0, weight=1)
        report_tab.rowconfigure(0, weight=1)
        notebook.add(report_tab, text="Report")

        self._build_project_management_tab(project_management_tab)
        self._build_overview_tab(overview_tab)
        self._build_initial_design_tab(initial_design_tab)
        self._build_current_design_tab(current_design_tab)
        self._build_geometry_tab(geometry_tab)
        self._build_thermo_tab(thermo_tab)
        self._build_comparison_tab(comparison_tab)
        self._build_report_tab(report_tab)

        status_frame = ttk.LabelFrame(self, text="Status and Errors", padding=12)
        status_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        status_frame.columnconfigure(0, weight=1)
        ttk.Label(
            status_frame,
            textvariable=self._error_var,
            wraplength=1180,
            justify="left",
            foreground="#9a2f2f",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            status_frame,
            textvariable=self._status_var,
            wraplength=1180,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _build_project_management_tab(self, master: ttk.Frame) -> None:
        self._project_management_panel = ProjectManagementPanel(master)
        self._project_management_panel.grid(row=0, column=0, sticky="nsew")
        self._project_management_panel.bind_project_changed(self._on_project_management_changed)

    def _build_overview_tab(self, master: ttk.Frame) -> None:
        self._dashboard_summary_panel = DashboardSummaryPanel(master, unit_preset=self._unit_preset)
        self._dashboard_summary_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        self._project_dashboard_panel = ProjectDashboardPanel(master, unit_preset=self._unit_preset)
        self._project_dashboard_panel.grid(row=0, column=1, sticky="nsew")

    def _build_initial_design_tab(self, master: ttk.Frame) -> None:
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        scrollable = ScrollableContentFrame(master)
        scrollable.grid(row=0, column=0, sticky="nsew")
        content = scrollable.content
        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)
        
        self._initial_input_panel = InputPanel(content, unit_preset=self._unit_preset)
        self._initial_input_panel.grid(row=0, column=0, sticky="new", padx=(0, 12))

        right_frame = ttk.Frame(content)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        self._initial_flow_case_panel = FlowCasePanel(right_frame)
        self._initial_flow_case_panel.grid(row=0, column=0, sticky="ew")

        seed_panel = ttk.LabelFrame(right_frame, text="Workflow", padding=12)
        seed_panel.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        seed_panel.columnconfigure(0, weight=1)
        ttk.Label(
            seed_panel,
            text=(
                "Initial Design is the baseline workspace. "
                "The first calculation copies these inputs into Current Design and runs the working design there."
            ),
            wraplength=460,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            seed_panel,
            text=(
                "After that, Geometry and Material applies into Current Design only, "
                "so the Initial Design baseline stays unchanged."
            ),
            wraplength=460,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self._initial_design_lock_var = tk.StringVar(
            value="Initial Design remains editable until the baseline is executed."
        )
        ttk.Label(
            seed_panel,
            textvariable=self._initial_design_lock_var,
            wraplength=460,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(10, 0))

        action_bar = ttk.Frame(master, padding=(0, 10, 0, 0))
        action_bar.grid(row=1, column=0, sticky="ew")
        for column in range(4):
            action_bar.columnconfigure(column, weight=1)
        self._initial_calculate_button = ttk.Button(
            action_bar,
            text="Calculate -> Current Design",
            command=self.calculate_from_initial_design,
        )
        self._initial_calculate_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._initial_load_example_button = ttk.Button(
            action_bar,
            text="Load Example",
            command=self.load_example_values,
        )
        self._initial_load_example_button.grid(row=0, column=1, sticky="ew", padx=6)
        self._initial_copy_button = ttk.Button(
            action_bar,
            text="Copy To Current Design",
            command=self.copy_initial_design_to_current_design,
        )
        self._initial_copy_button.grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(
            action_bar,
            text="Clear Errors",
            command=self.reset_error,
        ).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        self._initial_input_panel.bind_inputs_changed(self._on_initial_design_inputs_changed)
        self._initial_input_panel.bind_chemistry_mode_changed(self._on_initial_design_chemistry_mode_changed)
        self._initial_input_panel.bind_length_apply(self._on_initial_design_length_apply_requested)

    def _build_current_design_tab(self, master: ttk.Frame) -> None:
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        scrollable = ScrollableContentFrame(master)
        scrollable.grid(row=0, column=0, sticky="nsew")
        content = scrollable.content
        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)

        self._input_panel = InputPanel(
            content,
            unit_preset=self._unit_preset,
            show_current_design_features=True,
        )
        self._input_panel.grid(row=0, column=0, sticky="new", padx=(0, 12))

        right_frame = ttk.Frame(content)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.columnconfigure(1, weight=1)
        right_frame.rowconfigure(2, weight=1)

        transfer_frame = ttk.LabelFrame(right_frame, text="Sandbox Transfers", padding=12)
        transfer_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        for column in range(2):
            transfer_frame.columnconfigure(column, weight=1)
        self._load_lstar_to_current_button = ttk.Button(
            transfer_frame,
            text="Load L* into Current Design",
            command=self.load_working_lstar_into_current_design,
        )
        self._load_lstar_to_current_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        self._load_geometry_to_current_button = ttk.Button(
            transfer_frame,
            text="Load Geometry Inputs into Current Design",
            command=self.load_working_geometry_inputs_into_current_design,
        )
        self._load_geometry_to_current_button.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 6))
        self._apply_geometry_material_to_current_button = ttk.Button(
            transfer_frame,
            text="Apply Geometry + Material to Current Design",
            command=self.apply_working_geometry_material_to_current_design,
        )
        self._apply_geometry_material_to_current_button.grid(
            row=1, column=0, columnspan=2, sticky="ew"
        )

        self._build_sweep_section(right_frame, row_index=1, column_index=0)

        self._flow_case_panel = FlowCasePanel(right_frame)
        self._flow_case_panel.grid(row=1, column=1, sticky="new", padx=(10, 0))

        self._summary_panel = SummaryPanel(right_frame, unit_preset=self._unit_preset)
        self._summary_panel.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(10, 0))

        self._initial_conditions_plot_frame = ContourPlotFrame(
            content,
            on_point_selected=self._on_profile_point_selected,
            unit_preset=self._unit_preset,
        )
        self._initial_conditions_plot_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(12, 0))

        action_bar = ttk.Frame(master, padding=(0, 10, 0, 0))
        action_bar.grid(row=1, column=0, sticky="ew")
        for column in range(4):
            action_bar.columnconfigure(column, weight=1)
        ttk.Button(action_bar, text="Calculate Current Design", command=self.calculate).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(action_bar, text="Sync From Initial", command=self.copy_initial_design_to_current_design).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(action_bar, text="Export All", command=self.export_results).grid(
            row=0, column=2, sticky="ew", padx=6
        )
        ttk.Button(action_bar, text="Clear Errors", command=self.reset_error).grid(
            row=0, column=3, sticky="ew", padx=(6, 0)
        )

        self._input_panel.bind_chemistry_mode_changed(self._on_chemistry_mode_changed)
        self._input_panel.bind_length_apply(self._on_length_apply_requested)
        self._input_panel.bind_inputs_changed(self._on_design_inputs_changed)

    def _build_geometry_tab(self, master: ttk.Frame) -> None:
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        scrollable = ScrollableContentFrame(master)
        scrollable.grid(row=0, column=0, sticky="nsew")
        content = scrollable.content
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)

        self._chamber_geometry_panel = ChamberGeometryPanel(content)
        self._chamber_geometry_panel.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._chamber_geometry_panel.bind_apply_selected_lstar(self._on_working_lstar_stored)
        self._chamber_geometry_panel.bind_apply_geometry_inputs(self._on_working_geometry_inputs_stored)
        self._chamber_geometry_panel.bind_stored_state_changed(self._refresh_current_design_transfer_states)

        self._geometry_editor_panel = GeometryMaterialEditorPanel(content, unit_preset=self._unit_preset)
        self._geometry_editor_panel.grid(row=1, column=0, sticky="new", padx=(0, 12), pady=(12, 0))

        self._material_panel = MaterialOptionsPanel(content, unit_preset=self._unit_preset)
        self._material_panel.grid(row=1, column=1, sticky="new", pady=(12, 0))

        self._geometry_hint_var = tk.StringVar(
            value=(
                "Apply geometry/material edits to update the shared model. "
                "Then recalculate so the contour and thermochemistry plots become current again."
            )
        )
        ttk.Label(
            content,
            textvariable=self._geometry_hint_var,
            wraplength=980,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        self._geometry_plot_frame = ContourPlotFrame(
            content,
            on_point_selected=self._on_profile_point_selected,
            unit_preset=self._unit_preset,
        )
        self._geometry_plot_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(12, 0))

        self._geometry_panel = GeometryDetailsPanel(content, unit_preset=self._unit_preset)
        self._geometry_panel.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        action_bar = ttk.Frame(master, padding=(0, 10, 0, 0))
        action_bar.grid(row=1, column=0, sticky="ew")
        for column in range(4):
            action_bar.columnconfigure(column, weight=1)
        self._apply_material_geometry_button = ttk.Button(
            action_bar,
            text="Apply Material/Geometry",
            command=self.store_working_material_geometry,
        )
        self._apply_material_geometry_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(
            action_bar,
            text="Export Geometry JSON",
            command=self.export_geometry_json,
        ).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(
            action_bar,
            text="Export Geometry CSV",
            command=self.export_geometry_csv,
        ).grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(
            action_bar,
            text="Clear Errors",
            command=self.reset_error,
        ).grid(row=0, column=3, sticky="ew", padx=(6, 0))

    def _build_sweep_section(
        self,
        master: ttk.Frame,
        *,
        row_index: int,
        column_index: int,
    ) -> None:
        sweep_frame = ttk.LabelFrame(master, text="Mixture Ratio", padding=12)
        sweep_frame.grid(row=row_index, column=column_index, sticky="nsew")
        sweep_frame.columnconfigure(0, weight=1)
        sweep_frame.rowconfigure(2, weight=1)

        controls_frame = ttk.Frame(sweep_frame)
        controls_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        controls_frame.columnconfigure(1, weight=1)

        ttk.Label(controls_frame, text="Metric").grid(row=0, column=0, sticky="w", padx=(0, 6))
        metric_box = ttk.Combobox(
            controls_frame,
            state="readonly",
            textvariable=self._of_metric_var,
            values=[metric.value for metric in OFSweepMetric],
            width=10,
        )
        metric_box.grid(row=0, column=1, sticky="w")
        metric_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_of_sweep_plot())

        ttk.Label(controls_frame, text="Selected MR").grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 6),
            pady=(8, 0),
        )
        ttk.Entry(controls_frame, textvariable=self._selected_of_var, width=14).grid(
            row=1,
            column=1,
            sticky="w",
            pady=(8, 0),
        )
        ttk.Button(
            controls_frame,
            text="Apply",
            command=self.apply_selected_of_to_inputs,
        ).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(8, 0))

        ttk.Label(
            sweep_frame,
            textvariable=self._of_summary_var,
            wraplength=420,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 6))

        self._of_sweep_plot = OFSweepPlotFrame(
            sweep_frame,
            on_point_selected=self._on_of_sweep_point_selected,
            unit_preset=self._unit_preset,
        )
        self._of_sweep_plot.grid(row=2, column=0, sticky="nsew")

    def _build_thermo_tab(self, master: ttk.Frame) -> None:
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        master.rowconfigure(1, weight=1)

        self._species_plot_frame = SpeciesProfilePlotFrame(master, unit_preset=self._unit_preset)
        self._species_plot_frame.grid(row=0, column=0, sticky="nsew")

        self._thermo_contour_plot_frame = ContourPlotFrame(
            master,
            on_point_selected=self._on_profile_point_selected,
            unit_preset=self._unit_preset,
        )
        self._thermo_contour_plot_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))

    def _build_comparison_tab(self, master: ttk.Frame) -> None:
        self._comparison_panel = ComparisonPanel(master, unit_preset=self._unit_preset)
        self._comparison_panel.grid(row=0, column=0, sticky="nsew")

    def _build_report_tab(self, master: ttk.Frame) -> None:
        frame = ttk.LabelFrame(master, text="Report Preparation", padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(
            frame,
            text="AstraForge report generation is prepared here for later structured summaries and exports.",
            wraplength=760,
            justify="left",
        ).grid(row=0, column=0, sticky="nw")
        ttk.Label(
            frame,
            text=(
                "Planned sections: project context, operating point, geometry, thermochemistry, "
                "contour comparison, dashboard status and export packaging."
            ),
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="nw", pady=(10, 0))

    def new_case(self) -> None:
        """Reset the current window to a fresh default state."""

        if not self._confirm_discard_changes():
            return
        self._last_preset_path = None
        self.reset_error()
        self._project_state = create_project_state()
        self._reset_initial_design_lock_state()
        self._reset_working_geometry_states()
        self._project_mode_var.set(self._project_state.project_mode.value)
        self._apply_project_state_to_ui(reset_project_data=True)
        self.load_example_values(clear_results=True)
        self._status_var.set("Started a new AstraForge case.")

    def open_new_window(self) -> None:
        """Open a second independent AstraForge window as a separate process."""

        try:
            if getattr(sys, "frozen", False):
                project_root = Path(sys.executable).resolve().parent
                subprocess.Popen([sys.executable], cwd=str(project_root))
            else:
                project_root = Path(__file__).resolve().parents[2]
                python_executable = Path(sys.executable)
                pythonw_executable = python_executable.with_name("pythonw.exe")
                executable = pythonw_executable if pythonw_executable.exists() else python_executable
                subprocess.Popen([str(executable), str(project_root / "gui_launcher.py")], cwd=str(project_root))
        except Exception as exc:
            self._error_var.set(f"Could not open a new window: {exc}")
            self._status_var.set("New window failed.")
            return

        self._status_var.set("Opened a new independent AstraForge window.")

    def load_example_values(self, *, clear_results: bool = False) -> None:
        """Load the built-in LOX/RP-1 example values into the form."""

        example = self._example_input_factory()
        self._reset_initial_design_lock_state()
        self._reset_working_geometry_states()
        self._initial_input_panel.set_inputs(example)
        self._initial_input_panel.set_editable(True)
        self._refresh_initial_flow_case_assessment(example)
        self._current_design_linked_to_initial = True
        self._applied_detail_overrides = self._detail_overrides_from_inputs(example)
        self._input_panel.set_inputs(example)
        self._seed_geometry_sandbox_from_inputs(example)
        self._refresh_flow_case_assessment(example)
        self._selected_of_var.set(f"{example.mixture_ratio:.4f}")
        self._selected_sweep_mixture_ratio = example.mixture_ratio
        if clear_results:
            self._clear_loaded_results()
        else:
            mark_design_inputs_changed(self._project_state)
            self._refresh_of_sweep_plot()
            self._refresh_dashboard_views()
        self._status_var.set("Example values loaded.")

    def copy_initial_design_to_current_design(self) -> None:
        """Copy the baseline Initial Design into the Current Design workspace."""

        self.reset_error()
        inputs = self._copy_initial_design_to_current_design(
            select_current_tab=True,
        )
        if inputs is None:
            return
        self._status_var.set(
            "Initial Design was copied into Current Design. Existing results stay visible until you recalculate the committed design."
        )

    def calculate_from_initial_design(self) -> None:
        """Seed Current Design from Initial Design and run the working-design calculation."""

        inputs = self._copy_initial_design_to_current_design(select_current_tab=True)
        if inputs is None:
            return
        self._pending_initial_design_lock_inputs = inputs
        self.calculate()

    def calculate(self) -> None:
        """Read inputs, run the application controller and update the GUI."""

        self.reset_error()
        try:
            eta_cstar_design = self._input_panel.get_combustion_efficiency_assumption()
        except InputValidationError as exc:
            self._error_var.set(str(exc))
            self._status_var.set("Calculation failed.")
            return
        mark_calculation_running(self._project_state)
        self._refresh_dashboard_views()
        try:
            inputs = self._read_current_inputs()
            self._refresh_flow_case_assessment(inputs)
            bundle = self._controller.run_case(inputs)
        except (InputValidationError, ThermochemistryBackendError) as exc:
            self._pending_initial_design_lock_inputs = None
            mark_calculation_failed(self._project_state, str(exc))
            self._error_var.set(str(exc))
            self._refresh_dashboard_views()
            self._status_var.set("Calculation failed.")
            return
        except Exception as exc:  # pragma: no cover - GUI integration safeguard
            self._pending_initial_design_lock_inputs = None
            mark_calculation_failed(self._project_state, str(exc))
            self._error_var.set(f"Unexpected error: {exc}")
            self._refresh_dashboard_views()
            self._status_var.set("Calculation failed.")
            return

        self._current_bundle = bundle
        self._current_design_linked_to_initial = False
        self._selected_profile_point = None
        self._selected_sweep_mixture_ratio = bundle.inputs.mixture_ratio
        self._selected_of_var.set(f"{bundle.inputs.mixture_ratio:.4f}")
        self._update_geometry_sandbox_runtime_context(bundle.inputs)
        self._input_panel.set_calculated_expansion_ratios(
            current_expansion_ratio=bundle.geometry.current_expansion_ratio,
            optimal_expansion_ratio=bundle.geometry.optimal_expansion_ratio,
        )
        self._input_panel.set_derived_flow_quantities(
            bundle.geometry.mass_flow_kg_per_s,
            bundle.inputs.mixture_ratio,
        )
        self._input_panel.set_performance_preview(
            compute_performance_preview(inputs, bundle, eta_cstar_design)
        )
        self._current_separation_point = predict_separation_point(bundle)
        contour_markers = build_contour_markers(bundle, self._current_separation_point)

        self._geometry_panel.update_results(bundle)
        self._comparison_panel.update_results(bundle, self._current_separation_point)
        self._summary_panel.show_default_summary(bundle)
        self._initial_conditions_plot_frame.update_contour(
            bundle.contour,
            bundle.thermochemistry_profile,
            contour_markers,
        )
        self._geometry_plot_frame.update_contour(
            bundle.contour,
            bundle.thermochemistry_profile,
            contour_markers,
        )
        self._thermo_contour_plot_frame.update_contour(
            bundle.contour,
            bundle.thermochemistry_profile,
            contour_markers,
        )
        self._species_plot_frame.update_profile(bundle.thermochemistry_profile)
        mark_calculation_success(self._project_state)
        self._refresh_flow_case_assessment(inputs, gamma=bundle.thermochemistry.gamma)
        self._refresh_of_sweep_plot()
        self._refresh_dashboard_views()
        if self._pending_initial_design_lock_inputs is not None:
            self._mark_initial_design_executed(self._pending_initial_design_lock_inputs)
            self._pending_initial_design_lock_inputs = None
        self._status_var.set("Calculation completed successfully.")

    def export_results(self) -> None:
        """Export the currently displayed result bundle to JSON and CSV."""

        self.reset_error()
        if self._current_bundle is None:
            self._error_var.set("No results are available for export yet.")
            self._status_var.set("Export not possible.")
            return

        output_dir = Path.cwd() / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        selected = filedialog.asksaveasfilename(
            title="Choose the export base filename",
            initialdir=str(output_dir),
            initialfile="rocket_engine_case.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not selected:
            self._status_var.set("Export cancelled.")
            return

        output_stem = Path(selected).with_suffix("")
        try:
            written_files = self._controller.export_case(
                self._current_bundle,
                output_stem,
                unit_preset=self._unit_preset,
            )
        except Exception as exc:  # pragma: no cover - depends on filesystem interaction
            self._error_var.set(f"Export failed: {exc}")
            self._status_var.set("Export failed.")
            return

        self._status_var.set(
            "Export completed: "
            + ", ".join(f"{label} -> {path.name}" for label, path in written_files.items())
        )

    def save_engine_preset(self) -> None:
        """Save the current engine inputs to the last preset path."""

        if self._last_preset_path is None:
            self.save_engine_preset_as()
            return

        self._write_engine_preset(self._last_preset_path)

    def save_engine_preset_as(self) -> None:
        """Save the current engine inputs as an AstraForge preset file."""

        selected = self._ask_output_path(
            title="Save engine preset as",
            initial_name="engine_preset.astraforge.json",
            defaultextension=".json",
            filetypes=[
                ("AstraForge engine preset", "*.astraforge.json"),
                ("JSON", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if selected is None:
            self._status_var.set("Preset save cancelled.")
            return

        self._write_engine_preset(selected)

    def load_engine_preset_file(self) -> None:
        """Load engine inputs from an AstraForge preset file."""

        self.reset_error()
        output_dir = Path.cwd() / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        selected = filedialog.askopenfilename(
            title="Load engine preset",
            initialdir=str(output_dir),
            filetypes=[
                ("AstraForge engine preset", "*.astraforge.json"),
                ("JSON", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            self._status_var.set("Preset load cancelled.")
            return

        try:
            inputs, ui_state = load_engine_preset(selected)
        except Exception as exc:
            self._error_var.set(f"Preset load failed: {exc}")
            self._status_var.set("Preset load failed.")
            return

        loaded_mode = ui_state.get("project_mode", ProjectMode.SANDBOX)
        self._project_state = create_project_state(loaded_mode)
        self._reset_initial_design_lock_state()
        self._reset_working_geometry_states()
        apply_project_management_settings(
            self._project_state,
            ui_state.get("project_management", self._project_state.project_management),
            system_engineering_enabled=ui_state.get("system_engineering_enabled", False),
        )
        self._project_mode_var.set(self._project_state.project_mode.value)
        self._apply_project_state_to_ui(reset_project_data=True)

        self._apply_unit_preset(ui_state.get("unit_preset", self._unit_preset))
        self._initial_input_panel.set_inputs(inputs)
        self._initial_input_panel.set_editable(True)
        self._refresh_initial_flow_case_assessment(inputs)
        self._current_design_linked_to_initial = True
        self._applied_detail_overrides = self._detail_overrides_from_inputs(inputs)
        self._current_design_linked_to_initial = True
        self._input_panel.set_inputs(inputs)
        self._seed_geometry_sandbox_from_inputs(inputs)
        self._refresh_flow_case_assessment(inputs)
        self._last_preset_path = Path(selected)
        self._of_metric_var.set(ui_state["of_sweep_metric"].value)
        self._selected_sweep_mixture_ratio = ui_state["selected_mixture_ratio"] or inputs.mixture_ratio
        self._selected_of_var.set(f"{self._selected_sweep_mixture_ratio:.4f}")
        self._clear_loaded_results()
        self._status_var.set(
            f"Engine preset loaded from {Path(selected).name}. Click Calculate to refresh results."
        )

    def export_geometry_json(self) -> None:
        """Export geometry-only data to JSON from the geometry tab."""

        self.reset_error()
        if self._current_bundle is None:
            self._error_var.set("Run a calculation before exporting geometry.")
            self._status_var.set("Geometry export not possible.")
            return

        selected = self._ask_output_path(
            title="Export geometry JSON",
            initial_name="rocket_engine_geometry.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if selected is None:
            self._status_var.set("Geometry export cancelled.")
            return

        try:
            path = self._controller.export_geometry_json(
                self._current_bundle,
                selected,
                unit_preset=self._unit_preset,
            )
        except Exception as exc:  # pragma: no cover - depends on filesystem interaction
            self._error_var.set(f"Geometry JSON export failed: {exc}")
            self._status_var.set("Geometry export failed.")
            return

        self._status_var.set(f"Geometry JSON exported to {path.name}.")

    def export_geometry_csv(self) -> None:
        """Export the contour geometry to CSV from the geometry tab."""

        self.reset_error()
        if self._current_bundle is None:
            self._error_var.set("Run a calculation before exporting geometry.")
            self._status_var.set("Geometry export not possible.")
            return

        selected = self._ask_output_path(
            title="Export geometry CSV",
            initial_name="rocket_engine_geometry.csv",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if selected is None:
            self._status_var.set("Geometry export cancelled.")
            return

        try:
            path = self._controller.export_geometry_csv(
                self._current_bundle,
                selected,
                unit_preset=self._unit_preset,
            )
        except Exception as exc:  # pragma: no cover - depends on filesystem interaction
            self._error_var.set(f"Geometry CSV export failed: {exc}")
            self._status_var.set("Geometry export failed.")
            return

        self._status_var.set(f"Geometry CSV exported to {path.name}.")

    def apply_selected_of_to_inputs(self) -> None:
        """Apply the selected O/F ratio to the main input form."""

        raw_value = self._selected_of_var.get().strip()
        if not raw_value:
            self._error_var.set("Enter or click a mixture ratio first.")
            self._status_var.set("Mixture-ratio selection incomplete.")
            return
        try:
            mixture_ratio = float(raw_value.replace(",", "."))
        except ValueError:
            self._error_var.set("Selected mixture ratio must be a valid number.")
            self._status_var.set("Mixture-ratio selection invalid.")
            return

        self._input_panel.set_mixture_ratio(mixture_ratio)
        self._selected_sweep_mixture_ratio = mixture_ratio
        self._refresh_of_sweep_plot()
        self._status_var.set(
            "The mixture-ratio field was updated. Recalculate to evaluate the new operating point."
        )

    def reset_error(self) -> None:
        """Clear the visible error state."""

        self._error_var.set("")

    def _on_project_mode_selected(self) -> None:
        new_mode = ProjectMode(self._project_mode_var.get())
        set_project_mode(self._project_state, new_mode)
        self._apply_project_state_to_ui(reset_project_data=False)
        self._status_var.set(f"Project mode set to {PROJECT_MODE_LABELS[new_mode]}.")

    def _on_project_management_changed(self) -> None:
        apply_project_management_settings(
            self._project_state,
            self._project_management_panel.get_project_management_data(),
            system_engineering_enabled=self._project_management_panel.is_system_engineering_enabled(),
        )
        self._update_initial_design_lock_state()
        self._refresh_dashboard_views()
        self._status_var.set("Project-management context updated.")

    def _on_initial_design_inputs_changed(self) -> None:
        initial_inputs = self._try_read_initial_inputs()
        self._refresh_initial_flow_case_assessment(initial_inputs)
        if initial_inputs is not None and self._current_design_linked_to_initial:
            self._applied_detail_overrides = self._detail_overrides_from_inputs(initial_inputs)
            self._input_panel.set_inputs(initial_inputs)
            self._update_geometry_sandbox_runtime_context(initial_inputs)
            self._refresh_flow_case_assessment(initial_inputs)
            self._selected_of_var.set(f"{initial_inputs.mixture_ratio:.4f}")
            self._selected_sweep_mixture_ratio = initial_inputs.mixture_ratio

    def _on_initial_design_chemistry_mode_changed(self, _event: object) -> None:
        self._status_var.set(
            "Initial Design updated. Use Calculate -> Current Design to propagate the new baseline."
        )
        self._on_initial_design_inputs_changed()

    def _on_initial_design_length_apply_requested(self) -> None:
        self._status_var.set(
            "Initial Design nozzle length updated. Use Calculate -> Current Design to propagate the new baseline."
        )
        self._on_initial_design_inputs_changed()

    def _on_design_inputs_changed(self) -> None:
        self._current_design_linked_to_initial = False
        current_inputs = self._try_read_current_inputs()
        mark_design_inputs_changed(self._project_state)
        self._refresh_flow_case_assessment(current_inputs)
        self._update_geometry_sandbox_runtime_context(current_inputs)
        self._refresh_dashboard_views()

    def store_working_material_geometry(self) -> None:
        """Store geometry/material sandbox edits without touching Current Design."""

        self.reset_error()
        try:
            geometry_updates = self._geometry_editor_panel.get_geometry_updates()
            material_updates = self._material_panel.get_material_updates()
        except InputValidationError as exc:
            self._error_var.set(str(exc))
            self._status_var.set("Storing geometry/material sandbox state failed.")
            return

        self._working_geometry_updates = geometry_updates
        self._working_material_updates = material_updates
        self._refresh_current_design_transfer_states()
        self._status_var.set(
            "Geometry/material sandbox state was stored. Transfer it explicitly in Current Design when you are ready."
        )

    def load_working_lstar_into_current_design(self) -> None:
        """Load only the stored sandbox L* into Current Design without recalculating."""

        self.reset_error()
        try:
            base_inputs = self._read_current_inputs()
            lstar_update = self._chamber_geometry_panel.get_stored_lstar_update()
        except InputValidationError as exc:
            self._error_var.set(str(exc))
            self._status_var.set("Loading L* into Current Design failed.")
            return

        updated_inputs = replace(base_inputs, **lstar_update)
        self._apply_current_design_inputs_without_recalculation(
            updated_inputs,
            status_message=(
                f"Stored sandbox L* = {updated_inputs.characteristic_length_m:.4f} m was loaded into Current Design. "
                "Existing results remain visible until you calculate again."
            ),
        )

    def load_working_geometry_inputs_into_current_design(self) -> None:
        """Load stored sandbox chamber/nozzle geometry inputs into Current Design without recalculating."""

        self.reset_error()
        try:
            base_inputs = self._read_current_inputs()
            chamber_updates = self._chamber_geometry_panel.get_stored_geometry_updates()
        except InputValidationError as exc:
            self._error_var.set(str(exc))
            self._status_var.set("Loading geometry inputs into Current Design failed.")
            return

        geometry_updates = self._working_geometry_updates or {}
        updated_inputs = replace(base_inputs, **chamber_updates, **geometry_updates)
        self._apply_current_design_inputs_without_recalculation(
            updated_inputs,
            status_message=(
                "Stored sandbox geometry inputs were loaded into Current Design. "
                "Existing results remain visible until you calculate again."
            ),
        )

    def apply_working_geometry_material_to_current_design(self) -> None:
        """Load stored sandbox geometry and material updates into Current Design without recalculating."""

        self.reset_error()
        try:
            base_inputs = self._read_current_inputs()
            chamber_updates = self._chamber_geometry_panel.get_stored_geometry_updates()
        except InputValidationError as exc:
            self._error_var.set(str(exc))
            self._status_var.set("Applying geometry/material to Current Design failed.")
            return

        geometry_updates = self._working_geometry_updates or {}
        material_updates = self._working_material_updates or {}
        updated_inputs = replace(base_inputs, **chamber_updates, **geometry_updates, **material_updates)
        self._apply_current_design_inputs_without_recalculation(
            updated_inputs,
            status_message=(
                "Stored sandbox geometry and material values were applied to Current Design. "
                "Existing results remain visible until you calculate again."
            ),
        )

    def _on_working_lstar_stored(self) -> None:
        self._refresh_current_design_transfer_states()
        self._status_var.set(
            "Sandbox L* selection was stored. Load it explicitly into Current Design when you want to commit it."
        )

    def _on_working_geometry_inputs_stored(self) -> None:
        self._refresh_current_design_transfer_states()
        self._status_var.set(
            "Sandbox chamber geometry inputs were stored. Load them explicitly into Current Design when you want to commit them."
        )

    def _apply_current_design_inputs_without_recalculation(
        self,
        updated_inputs: InputParameters,
        *,
        status_message: str,
    ) -> None:
        self._current_design_linked_to_initial = False
        self._applied_detail_overrides = self._detail_overrides_from_inputs(updated_inputs)
        self._input_panel.set_inputs(updated_inputs)
        self._refresh_flow_case_assessment(updated_inputs)
        self._update_geometry_sandbox_runtime_context(updated_inputs)
        self._selected_of_var.set(f"{updated_inputs.mixture_ratio:.4f}")
        self._selected_sweep_mixture_ratio = updated_inputs.mixture_ratio
        mark_design_inputs_changed(self._project_state)
        self._refresh_of_sweep_plot()
        self._refresh_dashboard_views()
        self._status_var.set(status_message)

    def _on_profile_point_selected(self, profile_point: ThermochemistryProfilePoint) -> None:
        if self._current_bundle is None:
            return
        self._selected_profile_point = profile_point
        self._summary_panel.show_profile_point(profile_point, self._current_bundle)

    def _on_of_sweep_point_selected(self, point: OFSweepPoint) -> None:
        self._selected_of_var.set(f"{point.mixture_ratio:.4f}")
        self.apply_selected_of_to_inputs()

    def _refresh_of_sweep_plot(self) -> None:
        metric = OFSweepMetric(self._of_metric_var.get())
        if self._current_bundle is None:
            self._of_sweep_plot.update_sweep(
                None,
                metric=metric,
                current_mixture_ratio=self._selected_sweep_mixture_ratio,
            )
            self._update_of_summary()
            return

        self._of_sweep_plot.update_sweep(
            self._current_bundle.of_sweep,
            metric=metric,
            current_mixture_ratio=self._selected_sweep_mixture_ratio,
        )
        self._update_of_summary()

    def _update_of_summary(self) -> None:
        if self._current_bundle is None or self._current_bundle.of_sweep is None:
            self._of_summary_var.set("Run a calculation to populate the O/F sweep.")
            return

        sweep = self._current_bundle.of_sweep
        reference_mixture_ratio = self._selected_sweep_mixture_ratio or self._current_bundle.inputs.mixture_ratio
        point = min(
            sweep.points,
            key=lambda sweep_point: abs(sweep_point.mixture_ratio - reference_mixture_ratio),
        )
        displayed_metric = (
            f"Vacuum Isp = {format_quantity(point.isp_vac_s, 'isp', self._unit_preset, include_unit=True)}"
            if OFSweepMetric(self._of_metric_var.get()) is OFSweepMetric.ISP_VAC
            else f"c* = {format_quantity(point.c_star_m_s, 'velocity', self._unit_preset, include_unit=True)}"
        )
        stoich = (
            f"{sweep.stoichiometric_mixture_ratio:.3f}"
            if sweep.stoichiometric_mixture_ratio is not None
            else "unavailable"
        )
        max_isp_mr = f"{sweep.peak_isp_vac_mixture_ratio:.3f}"
        max_cstar_mr = f"{sweep.peak_c_star_mixture_ratio:.3f}"
        self._of_summary_var.set(
            f"MR {point.mixture_ratio:.4f} | Isp {format_quantity(point.isp_vac_s, 'isp', self._unit_preset, include_unit=True)} | "
            f"c* {format_quantity(point.c_star_m_s, 'velocity', self._unit_preset, include_unit=True)}\n"
            f"Stoich {stoich} | Max Isp MR {max_isp_mr} | Max c* MR {max_cstar_mr} | {displayed_metric}"
        )

    def _on_chemistry_mode_changed(self, _event: object) -> None:
        self._status_var.set("Chemistry mode changed. Recalculating current case...")
        self.calculate()

    def _on_length_apply_requested(self) -> None:
        try:
            manual_length = self._input_panel.get_manual_nozzle_length_m()
        except InputValidationError as exc:
            self._error_var.set(str(exc))
            self._status_var.set("Manual nozzle-length entry is invalid.")
            return

        if manual_length is None:
            self._status_var.set("Enter a manual nozzle length before applying it.")
            return

        self._status_var.set("Manual nozzle length accepted. Recalculating current geometry...")
        self.calculate()

    def _on_unit_preset_selected(self) -> None:
        self._apply_unit_preset(UnitPreset(self._unit_preset_var.get()))
        self._status_var.set(f"Unit preset set to {UNIT_PRESET_LABELS[self._unit_preset]}.")

    def _apply_unit_preset(self, unit_preset: UnitPreset) -> None:
        self._unit_preset = unit_preset
        self._unit_preset_var.set(unit_preset.value)
        self._initial_input_panel.set_unit_preset(unit_preset)
        self._input_panel.set_unit_preset(unit_preset)
        self._summary_panel.set_unit_preset(unit_preset)
        self._dashboard_summary_panel.set_unit_preset(unit_preset)
        self._project_dashboard_panel.set_unit_preset(unit_preset)
        self._flow_case_panel.set_assessment(self._project_state.flow_case_assessment)
        self._chamber_geometry_panel.set_unit_preset(unit_preset)
        self._geometry_editor_panel.set_unit_preset(unit_preset)
        self._geometry_panel.set_unit_preset(unit_preset)
        self._material_panel.set_unit_preset(unit_preset)
        self._comparison_panel.set_unit_preset(unit_preset)
        self._initial_conditions_plot_frame.set_unit_preset(unit_preset)
        self._geometry_plot_frame.set_unit_preset(unit_preset)
        self._species_plot_frame.set_unit_preset(unit_preset)
        self._thermo_contour_plot_frame.set_unit_preset(unit_preset)
        self._of_sweep_plot.set_unit_preset(unit_preset)
        self._update_of_summary()
        if self._current_bundle is not None:
            if self._selected_profile_point is not None:
                self._summary_panel.show_profile_point(self._selected_profile_point, self._current_bundle)
            else:
                self._summary_panel.show_default_summary(self._current_bundle)
        initial_inputs = self._try_read_initial_inputs()
        self._refresh_initial_flow_case_assessment(initial_inputs)
        current_inputs = self._try_read_current_inputs()
        if current_inputs is not None:
            self._update_geometry_sandbox_runtime_context(current_inputs)
        self._refresh_dashboard_views()

    def _apply_project_state_to_ui(self, *, reset_project_data: bool) -> None:
        self._project_mode_var.set(self._project_state.project_mode.value)
        self._project_management_panel.set_project_context(
            self._project_state.project_mode,
            system_engineering_enabled=self._project_state.system_engineering_enabled,
        )
        if reset_project_data:
            self._project_management_panel.set_project_data(self._project_state.project_management)
        self._project_management_panel.set_project_setup_status(
            self._project_state.module_statuses["project_setup"],
            self._project_state.module_messages.get("project_setup", ""),
        )
        self._update_initial_design_lock_state()
        self._refresh_current_design_transfer_states()
        self._refresh_dashboard_views()

    def _refresh_dashboard_views(self) -> None:
        current_inputs = self._try_read_current_inputs()
        current_bundle = self._current_bundle if self._project_state.has_results else None
        self._project_management_panel.set_project_setup_status(
            self._project_state.module_statuses["project_setup"],
            self._project_state.module_messages.get("project_setup", ""),
        )
        self._dashboard_summary_panel.update_dashboard(
            self._project_state,
            bundle=current_bundle,
            current_inputs=current_inputs,
        )
        self._project_dashboard_panel.update_dashboard(
            self._project_state,
            bundle=current_bundle,
            current_inputs=current_inputs,
        )

    def _refresh_flow_case_assessment(
        self,
        inputs: InputParameters | None,
        *,
        gamma: float | None = None,
    ) -> None:
        if inputs is None:
            set_flow_case_assessment(self._project_state, None)
            self._input_panel.set_flow_case_assessment(None)
            self._geometry_editor_panel.set_flow_case_assessment(None)
            self._flow_case_panel.set_assessment(None)
            return

        assessment = classify_input_flow_case(inputs, gamma=gamma)
        set_flow_case_assessment(self._project_state, assessment)
        self._input_panel.set_flow_case_assessment(assessment)
        self._geometry_editor_panel.set_flow_case_assessment(assessment)
        self._flow_case_panel.set_assessment(assessment)

    def _refresh_initial_flow_case_assessment(
        self,
        inputs: InputParameters | None,
        *,
        gamma: float | None = None,
    ) -> None:
        if inputs is None:
            self._initial_input_panel.set_flow_case_assessment(None)
            self._initial_flow_case_panel.set_assessment(None)
            return

        assessment = classify_input_flow_case(inputs, gamma=gamma)
        self._initial_input_panel.set_flow_case_assessment(assessment)
        self._initial_flow_case_panel.set_assessment(assessment)

    def _copy_initial_design_to_current_design(
        self,
        *,
        select_current_tab: bool,
    ) -> InputParameters | None:
        try:
            inputs = self._read_initial_inputs()
        except InputValidationError as exc:
            self._error_var.set(str(exc))
            self._status_var.set("Initial Design could not be propagated to Current Design.")
            return None

        self._applied_detail_overrides = self._detail_overrides_from_inputs(inputs)
        self._current_design_linked_to_initial = True
        self._input_panel.set_inputs(inputs)
        self._refresh_flow_case_assessment(inputs)
        self._update_geometry_sandbox_runtime_context(inputs)
        self._selected_of_var.set(f"{inputs.mixture_ratio:.4f}")
        self._selected_sweep_mixture_ratio = inputs.mixture_ratio
        mark_design_inputs_changed(self._project_state)
        self._refresh_of_sweep_plot()
        self._refresh_dashboard_views()
        if select_current_tab:
            self._notebook.select(self._current_design_tab)
        return inputs

    @staticmethod
    def _detail_overrides_from_inputs(inputs: InputParameters) -> dict[str, object]:
        return {
            "convergent_half_angle_deg": inputs.convergent_half_angle_deg,
            "throat_upstream_radius_m": inputs.throat_upstream_radius_m,
            "throat_downstream_radius_m": inputs.throat_downstream_radius_m,
            "manufacturing_mode": inputs.manufacturing_mode,
            "manufacturing_route": inputs.manufacturing_route,
            "liner_material": inputs.liner_material,
            "liner_coating_enabled": inputs.liner_coating_enabled,
            "liner_coating": inputs.liner_coating,
            "wall_thickness_mode": inputs.wall_thickness_mode,
            "wall_thickness_m": inputs.wall_thickness_m,
        }

    def _seed_geometry_sandbox_from_inputs(self, inputs: InputParameters) -> None:
        current_bundle = (
            self._current_bundle
            if self._current_bundle is not None and self._current_bundle.inputs == inputs
            else None
        )
        self._chamber_geometry_panel.seed_from_design(inputs, current_bundle=current_bundle)
        self._geometry_editor_panel.set_inputs(inputs)
        self._material_panel.set_inputs(inputs)
        self._refresh_current_design_transfer_states()

    def _update_geometry_sandbox_runtime_context(self, inputs: InputParameters | None) -> None:
        current_bundle = (
            self._current_bundle
            if self._current_bundle is not None and inputs is not None and self._current_bundle.inputs == inputs
            else self._current_bundle
        )
        self._chamber_geometry_panel.set_runtime_context(inputs, current_bundle=current_bundle)

    def _try_read_initial_inputs(self) -> InputParameters | None:
        try:
            return self._read_initial_inputs()
        except InputValidationError:
            return None

    def _try_read_current_inputs(self) -> InputParameters | None:
        try:
            return self._read_current_inputs()
        except InputValidationError:
            return None

    def _confirm_discard_changes(self) -> bool:
        if self._current_bundle is None and self._last_preset_path is None:
            return True
        return messagebox.askyesno(
            title="Discard current case?",
            message=(
                "Start a new case and discard the current workspace in this window?\n"
                "Use Save first if you want to keep the current setup."
            ),
            parent=self,
        )

    def _ask_output_path(
        self,
        *,
        title: str,
        initial_name: str,
        defaultextension: str,
        filetypes: list[tuple[str, str]],
    ) -> Path | None:
        output_dir = Path.cwd() / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        selected = filedialog.asksaveasfilename(
            title=title,
            initialdir=str(output_dir),
            initialfile=initial_name,
            defaultextension=defaultextension,
            filetypes=filetypes,
        )
        if not selected:
            return None
        return Path(selected)

    def _read_current_inputs(self) -> InputParameters:
        base_inputs = self._input_panel.get_input_parameters()
        return replace(base_inputs, **self._applied_detail_overrides)

    def _read_initial_inputs(self) -> InputParameters:
        return self._initial_input_panel.get_input_parameters()

    def _clear_loaded_results(self) -> None:
        """Clear derived outputs after loading or resetting a case."""

        clear_calculation_results(self._project_state)
        self._current_bundle = None
        self._current_separation_point = None
        self._selected_profile_point = None
        self._summary_panel.clear()
        self._geometry_panel.clear()
        self._comparison_panel.clear()
        self._input_panel.clear_derived_flow_quantities()
        self._input_panel.clear_performance_preview()
        self._initial_conditions_plot_frame.update_contour([], [], [])
        self._geometry_plot_frame.update_contour([], [], [])
        self._species_plot_frame.update_profile([])
        self._thermo_contour_plot_frame.update_contour([], [], [])
        self._of_sweep_plot.update_sweep(
            None,
            metric=OFSweepMetric(self._of_metric_var.get()),
            current_mixture_ratio=self._selected_sweep_mixture_ratio,
        )
        self._of_summary_var.set(
            "Current setup changed. Click Calculate to recompute the O/F sweep and all results."
        )
        current_inputs = self._try_read_current_inputs()
        if current_inputs is not None:
            self._update_geometry_sandbox_runtime_context(current_inputs)
        self._refresh_dashboard_views()

    def _reset_working_geometry_states(self) -> None:
        self._working_geometry_updates = None
        self._working_material_updates = None

    def _reset_initial_design_lock_state(self) -> None:
        self._initial_design_locked = False
        self._initial_design_snapshot = None
        self._pending_initial_design_lock_inputs = None

    def _mark_initial_design_executed(self, inputs: InputParameters) -> None:
        self._initial_design_locked = True
        self._initial_design_snapshot = inputs
        self._update_initial_design_lock_state()

    def _update_initial_design_lock_state(self) -> None:
        if not hasattr(self, "_initial_input_panel"):
            return
        allow_editing = self._project_management_panel.is_initial_design_editing_allowed()
        is_editable = (not self._initial_design_locked) or allow_editing
        self._initial_input_panel.set_editable(is_editable)
        self._initial_calculate_button.configure(state="normal" if is_editable else "disabled")
        self._initial_copy_button.configure(state="normal" if is_editable else "disabled")
        self._initial_load_example_button.configure(state="normal" if is_editable else "disabled")
        tab_state = "normal" if is_editable else "disabled"
        self._notebook.tab(self._initial_design_tab, state=tab_state)
        if not is_editable and self._notebook.select() == str(self._initial_design_tab):
            self._notebook.select(self._current_design_tab)
        if self._initial_design_locked and not allow_editing:
            self._initial_design_lock_var.set(
                "Initial Design is locked after the baseline run. Enable the Project Management override to edit it again."
            )
        elif self._initial_design_locked and allow_editing:
            self._initial_design_lock_var.set(
                "Initial Design baseline is saved, but Project Management currently allows you to keep editing it."
            )
        else:
            self._initial_design_lock_var.set(
                "Initial Design remains editable until the baseline is executed."
            )

    def _refresh_current_design_transfer_states(self) -> None:
        if not hasattr(self, "_load_lstar_to_current_button"):
            return
        has_lstar = self._chamber_geometry_panel.has_stored_lstar_update()
        has_geometry = self._chamber_geometry_panel.has_stored_geometry_updates()
        has_material_geometry = has_geometry and (
            self._working_geometry_updates is not None or self._working_material_updates is not None
        )
        self._load_lstar_to_current_button.configure(state="normal" if has_lstar else "disabled")
        self._load_geometry_to_current_button.configure(state="normal" if has_geometry else "disabled")
        self._apply_geometry_material_to_current_button.configure(
            state="normal" if has_material_geometry else "disabled"
        )
        if hasattr(self, "_apply_material_geometry_button"):
            self._apply_material_geometry_button.configure(state="normal")

    def _write_engine_preset(self, target_path: str | Path) -> None:
        """Persist the current UI state as an AstraForge preset."""

        self.reset_error()
        try:
            inputs = self._read_current_inputs()
        except InputValidationError as exc:
            self._error_var.set(str(exc))
            self._status_var.set("Engine preset could not be saved.")
            return

        try:
            path = export_engine_preset(
                inputs,
                target_path,
                of_sweep_metric=OFSweepMetric(self._of_metric_var.get()),
                selected_mixture_ratio=self._selected_sweep_mixture_ratio,
                unit_preset=self._unit_preset,
                project_mode=self._project_state.project_mode,
                system_engineering_enabled=self._project_state.system_engineering_enabled,
                project_management=self._project_state.project_management,
            )
        except Exception as exc:  # pragma: no cover - depends on filesystem interaction
            self._error_var.set(f"Preset save failed: {exc}")
            self._status_var.set("Preset save failed.")
            return

        self._last_preset_path = Path(path)
        self._status_var.set(f"Engine preset saved to {path.name}.")

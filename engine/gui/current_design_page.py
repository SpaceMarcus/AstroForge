"""Dedicated Current Design workspace layout for AstraForge.

This page owns only the Tk layout and local widget plumbing. The controller,
committed bundle state and explicit recalculation path still live in MainWindow.
"""

from __future__ import annotations

from dataclasses import replace
import tkinter as tk
from tkinter import ttk
from typing import Callable

from engine.geometry import build_contour_markers
from engine.gui.chamber_geometry_panel import ChamberGeometryPanel
from engine.gui.input_panel import InputPanel
from engine.gui.plotting import ContourPlotFrame, OFSweepPlotFrame
from engine.gui.project_panels import FlowCasePanel, ScrollableContentFrame
from engine.gui.result_panel import GeometryDetailsPanel, GeometryMaterialEditorPanel, MaterialOptionsPanel, SummaryPanel
from engine.models import ExportBundle, InputParameters, OFSweepMetric, OFSweepPoint, PredictedSeparationPoint, ThermochemistryProfilePoint
from engine.performance_preview import PerformancePreviewResult
from engine.unit_system import UnitPreset, format_quantity
from engine.utils.validation import InputValidationError


class CurrentDesignPage(ttk.Frame):
    """One engineering workspace with scrollable draft tiles and a fixed geometry view."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        unit_preset: UnitPreset,
        status_var: tk.StringVar,
        last_committed_var: tk.StringVar,
        geometry_source_var: tk.StringVar,
        thermal_status_var: tk.StringVar,
        contour_status_var: tk.StringVar,
        preview_status_var: tk.StringVar,
        of_metric_var: tk.StringVar,
        selected_of_var: tk.StringVar,
        of_summary_var: tk.StringVar,
    ) -> None:
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0, minsize=300)
        self.rowconfigure(0, weight=1)

        self._unit_preset = unit_preset
        self._status_var = status_var
        self._last_committed_var = last_committed_var
        self._geometry_source_var = geometry_source_var
        self._thermal_status_var = thermal_status_var
        self._contour_status_var = contour_status_var
        self._preview_status_var = preview_status_var
        self._of_metric_var = of_metric_var
        self._selected_of_var = selected_of_var
        self._of_summary_var = of_summary_var
        self._geometry_view_note_var = tk.StringVar(
            value="Committed Current Design will appear here after the first full recalculation."
        )

        self._point_selected_callback: Callable[[ThermochemistryProfilePoint], None] | None = None
        self._commit_callback: Callable[[], None] | None = None
        self._sync_callback: Callable[[], None] | None = None
        self._export_callback: Callable[[], None] | None = None
        self._clear_errors_callback: Callable[[], None] | None = None
        self._apply_selected_of_callback: Callable[[], None] | None = None
        self._metric_changed_callback: Callable[[], None] | None = None
        self._of_point_selected_callback: Callable[[OFSweepPoint], None] | None = None
        self._preview_update_callback: Callable[[], None] | None = None

        self._committed_bundle: ExportBundle | None = None
        self._preview_bundle: ExportBundle | None = None
        self._committed_separation_point: PredictedSeparationPoint | None = None
        self._preview_separation_point: PredictedSeparationPoint | None = None
        self._visible_bundle: ExportBundle | None = None
        self._committed_wall_thickness_m: float | None = None
        self._preview_wall_thickness_m: float | None = None
        self._selected_profile_point: ThermochemistryProfilePoint | None = None
        self._selected_station_var = tk.StringVar(value="Selected station: none")
        self._suspend_geometry_redraw = False
        self._pending_geometry_redraw = False
        self._species_popup: tk.Toplevel | None = None
        self._species_summary_panel: SummaryPanel | None = None
        self._of_sweep_popup: tk.Toplevel | None = None
        self._popup_of_sweep_plot: OFSweepPlotFrame | None = None
        self._open_species_button: ttk.Button | None = None

        self._build_layout()

    @property
    def input_panel(self) -> InputPanel:
        return self._input_panel

    @property
    def chamber_panel(self) -> ChamberGeometryPanel:
        return self._chamber_geometry_panel

    @property
    def geometry_editor_panel(self) -> GeometryMaterialEditorPanel:
        return self._geometry_editor_panel

    @property
    def material_panel(self) -> MaterialOptionsPanel:
        return self._material_panel

    @property
    def flow_case_panel(self) -> FlowCasePanel:
        return self._flow_case_panel

    @property
    def summary_panel(self) -> SummaryPanel:
        return self._ensure_species_popup_panel()

    @property
    def geometry_details_panel(self) -> GeometryDetailsPanel:
        return self._geometry_panel

    @property
    def contour_plot_frame(self) -> ContourPlotFrame:
        return self._contour_plot_frame

    @property
    def of_sweep_plot(self) -> OFSweepPlotFrame:
        return self._ensure_of_sweep_popup_plot()

    def _build_layout(self) -> None:
        left_scroll = ScrollableContentFrame(self)
        left_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left_content = left_scroll.content
        left_content.columnconfigure(0, weight=1)

        right_frame = ttk.Frame(self)
        right_frame.grid(row=0, column=1, sticky="ns")
        right_frame.configure(width=300)
        right_frame.grid_propagate(False)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        status_frame = ttk.LabelFrame(left_content, text="Current Design Status", padding=12)
        status_frame.grid(row=0, column=0, sticky="ew")
        status_frame.columnconfigure(1, weight=1)
        status_frame.columnconfigure(3, weight=1)
        ttk.Label(status_frame, text="status").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Label(status_frame, textvariable=self._status_var).grid(row=0, column=1, sticky="w", pady=3)
        ttk.Label(status_frame, text="last committed").grid(row=0, column=2, sticky="w", padx=(18, 8), pady=3)
        ttk.Label(status_frame, textvariable=self._last_committed_var).grid(row=0, column=3, sticky="w", pady=3)
        ttk.Label(status_frame, text="geometry source").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Label(status_frame, textvariable=self._geometry_source_var).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(status_frame, text="thermal status").grid(row=1, column=2, sticky="w", padx=(18, 8), pady=3)
        ttk.Label(status_frame, textvariable=self._thermal_status_var).grid(row=1, column=3, sticky="w", pady=3)
        ttk.Label(
            status_frame,
            textvariable=self._contour_status_var,
            wraplength=620,
            justify="left",
        ).grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Label(
            status_frame,
            textvariable=self._preview_status_var,
            wraplength=620,
            justify="left",
        ).grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        workflow_frame = ttk.LabelFrame(left_content, text="Draft Workflow", padding=12)
        workflow_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(
            workflow_frame,
            text=(
                "Edit chamber, throat, nozzle and material values directly here. "
                "Use Update Geometry Preview when you want to inspect the draft contour. "
                "Thermal Analysis, Report and Export keep using the last committed contour until "
                "you commit and recalculate."
            ),
            wraplength=620,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

        self._input_panel = InputPanel(
            left_content,
            unit_preset=self._unit_preset,
            show_current_design_features=True,
        )
        self._input_panel.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        self._build_sweep_section(left_content, row_index=3)

        self._flow_case_panel = FlowCasePanel(left_content)
        self._flow_case_panel.grid(row=4, column=0, sticky="ew", pady=(10, 0))

        self._chamber_geometry_panel = ChamberGeometryPanel(left_content, workflow_mode="workspace")
        self._chamber_geometry_panel.grid(row=5, column=0, sticky="ew", pady=(10, 0))

        self._geometry_editor_panel = GeometryMaterialEditorPanel(
            left_content,
            unit_preset=self._unit_preset,
            workflow_mode="workspace",
        )
        self._geometry_editor_panel.grid(row=6, column=0, sticky="ew", pady=(10, 0))

        self._material_panel = MaterialOptionsPanel(left_content, unit_preset=self._unit_preset)
        self._material_panel.grid(row=7, column=0, sticky="ew", pady=(10, 0))

        self._geometry_panel = GeometryDetailsPanel(left_content, unit_preset=self._unit_preset)
        self._geometry_panel.grid(row=8, column=0, sticky="ew", pady=(10, 0))

        station_frame = ttk.LabelFrame(right_frame, text="Selected Station", padding=10)
        station_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        station_frame.columnconfigure(0, weight=1)
        ttk.Label(
            station_frame,
            textvariable=self._selected_station_var,
            wraplength=240,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        self._open_species_button = ttk.Button(
            station_frame,
            text="Open Species & Notes",
            command=self._open_species_notes_popup,
            state="disabled",
        )
        self._open_species_button.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        geometry_view_frame = ttk.LabelFrame(right_frame, text="Geometry Viewer", padding=12)
        geometry_view_frame.grid(row=1, column=0, sticky="nsew")
        geometry_view_frame.configure(width=280, height=620)
        geometry_view_frame.grid_propagate(False)
        geometry_view_frame.columnconfigure(0, weight=1)
        geometry_view_frame.rowconfigure(0, weight=1)

        self._contour_plot_frame = ContourPlotFrame(
            geometry_view_frame,
            on_point_selected=self._handle_point_selected,
            unit_preset=self._unit_preset,
            orientation="vertical_clockwise",
        )
        self._contour_plot_frame.configure(text="Committed / Draft Geometry")
        self._contour_plot_frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            geometry_view_frame,
            textvariable=self._geometry_view_note_var,
            wraplength=340,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(10, 0))

        action_bar = ttk.Frame(self, padding=(0, 10, 0, 0))
        action_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        for column in range(5):
            action_bar.columnconfigure(column, weight=1)
        self._commit_button = ttk.Button(
            action_bar,
            text="Commit Draft & Recalculate Current Design",
            command=self._handle_commit_recalculate,
        )
        self._commit_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._preview_button = ttk.Button(
            action_bar,
            text="Update Geometry Preview",
            command=self._handle_preview_update,
        )
        self._preview_button.grid(row=0, column=1, sticky="ew", padx=6)
        self._sync_button = ttk.Button(
            action_bar,
            text="Sync From Initial",
            command=self._handle_sync_from_initial,
        )
        self._sync_button.grid(row=0, column=2, sticky="ew", padx=6)
        self._export_button = ttk.Button(
            action_bar,
            text="Export All",
            command=self._handle_export,
        )
        self._export_button.grid(row=0, column=3, sticky="ew", padx=6)
        self._clear_errors_button = ttk.Button(
            action_bar,
            text="Clear Errors",
            command=self._handle_clear_errors,
        )
        self._clear_errors_button.grid(row=0, column=4, sticky="ew", padx=(6, 0))

    def _build_sweep_section(self, master: ttk.Frame, *, row_index: int) -> None:
        sweep_frame = ttk.LabelFrame(master, text="Mixture Ratio", padding=12)
        sweep_frame.grid(row=row_index, column=0, sticky="ew", pady=(10, 0))
        sweep_frame.columnconfigure(0, weight=1)

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
        metric_box.bind("<<ComboboxSelected>>", self._handle_metric_changed)

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
            command=self._handle_apply_selected_of,
        ).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(8, 0))

        ttk.Label(
            sweep_frame,
            textvariable=self._of_summary_var,
            wraplength=620,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(
            sweep_frame,
            text="Open O/F Sweep",
            command=self._open_of_sweep_popup,
        ).grid(row=2, column=0, sticky="w")

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        self._unit_preset = unit_preset
        self._input_panel.set_unit_preset(unit_preset)
        self._chamber_geometry_panel.set_unit_preset(unit_preset)
        self._geometry_editor_panel.set_unit_preset(unit_preset)
        self._material_panel.set_unit_preset(unit_preset)
        self._geometry_panel.set_unit_preset(unit_preset)
        if self._species_summary_panel is not None:
            self._species_summary_panel.set_unit_preset(unit_preset)
        self._contour_plot_frame.set_unit_preset(unit_preset)
        if self._popup_of_sweep_plot is not None:
            self._popup_of_sweep_plot.set_unit_preset(unit_preset)
        if self._selected_profile_point is not None:
            self._selected_station_var.set(
                "Selected station: "
                f"x = {format_quantity(self._selected_profile_point.x_m, 'length', self._unit_preset, include_unit=True)}, "
                f"r = {format_quantity(self._selected_profile_point.radius_m, 'length', self._unit_preset, include_unit=True)}"
            )
        self._request_geometry_redraw()

    def set_inputs(self, inputs: InputParameters, current_bundle: ExportBundle | None = None) -> None:
        self._input_panel.set_inputs(inputs)
        self._chamber_geometry_panel.seed_from_design(inputs, current_bundle=current_bundle)
        self._geometry_editor_panel.set_inputs(inputs, current_bundle=current_bundle)
        self._material_panel.set_inputs(inputs)

    def set_runtime_context(
        self,
        inputs: InputParameters | None,
        *,
        current_bundle: ExportBundle | None = None,
        preview_bundle: ExportBundle | None = None,
    ) -> None:
        self._chamber_geometry_panel.set_runtime_context(inputs, current_bundle=preview_bundle or current_bundle)
        self._geometry_editor_panel.set_runtime_context(inputs, current_bundle=preview_bundle or current_bundle)
        self._preview_bundle = preview_bundle
        self._request_geometry_redraw()

    def set_flow_case_assessment(self, assessment) -> None:
        self._input_panel.set_flow_case_assessment(assessment)
        self._geometry_editor_panel.set_flow_case_assessment(assessment)
        self._flow_case_panel.set_assessment(assessment)

    def set_current_design_status(
        self,
        *,
        status_text: str,
        last_committed: str,
        geometry_source: str,
        thermal_status: str,
        contour_status: str,
        preview_status: str,
    ) -> None:
        self._status_var.set(status_text)
        self._last_committed_var.set(last_committed)
        self._geometry_source_var.set(geometry_source)
        self._thermal_status_var.set(thermal_status)
        self._contour_status_var.set(contour_status)
        self._preview_status_var.set(preview_status)

    def set_performance_preview(self, preview: PerformancePreviewResult) -> None:
        self._input_panel.set_performance_preview(preview)

    def clear_performance_preview(self) -> None:
        self._input_panel.clear_performance_preview()

    def set_derived_flow_quantities(self, total_mass_flow_kg_per_s: float | None, mixture_ratio: float | None) -> None:
        self._input_panel.set_derived_flow_quantities(total_mass_flow_kg_per_s, mixture_ratio)

    def clear_derived_flow_quantities(self) -> None:
        self._input_panel.clear_derived_flow_quantities()

    def set_calculated_expansion_ratios(
        self,
        *,
        current_expansion_ratio: float | None,
        optimal_expansion_ratio: float | None,
    ) -> None:
        self._input_panel.set_calculated_expansion_ratios(
            current_expansion_ratio=current_expansion_ratio,
            optimal_expansion_ratio=optimal_expansion_ratio,
        )

    def update_committed_contour(
        self,
        bundle: ExportBundle | None,
        *,
        separation_point: PredictedSeparationPoint | None = None,
        wall_thickness_m: float | None = None,
    ) -> None:
        self._committed_bundle = bundle
        self._committed_separation_point = separation_point
        self._committed_wall_thickness_m = wall_thickness_m
        self._selected_profile_point = None
        self._selected_station_var.set("Selected station: none")
        if self._open_species_button is not None:
            self._open_species_button.configure(state="normal" if bundle is not None else "disabled")
        self._request_geometry_redraw()

    def update_preview_contour(
        self,
        bundle: ExportBundle | None,
        *,
        separation_point: PredictedSeparationPoint | None = None,
        wall_thickness_m: float | None = None,
    ) -> None:
        self._preview_bundle = bundle
        self._preview_separation_point = separation_point
        self._preview_wall_thickness_m = wall_thickness_m
        self._selected_profile_point = None
        self._selected_station_var.set("Selected station: none")
        if self._open_species_button is not None:
            self._open_species_button.configure(state="normal" if bundle is not None or self._committed_bundle is not None else "disabled")
        self._request_geometry_redraw()

    def clear_preview_contour(self) -> None:
        self._preview_bundle = None
        self._preview_separation_point = None
        self._preview_wall_thickness_m = None
        self._selected_profile_point = None
        self._selected_station_var.set("Selected station: none")
        self._request_geometry_redraw()

    def update_geometry_summary(self, bundle: ExportBundle) -> None:
        self._geometry_panel.update_results(bundle)

    def clear_results(self) -> None:
        self._committed_bundle = None
        self._preview_bundle = None
        self._committed_separation_point = None
        self._preview_separation_point = None
        self._visible_bundle = None
        self._committed_wall_thickness_m = None
        self._preview_wall_thickness_m = None
        self._selected_profile_point = None
        self._selected_station_var.set("Selected station: none")
        self._geometry_view_note_var.set("Committed Current Design will appear here after the first full recalculation.")
        if self._species_summary_panel is not None:
            self._species_summary_panel.clear()
        self._geometry_panel.clear()
        self._contour_plot_frame.update_contour([], [], [])
        if self._open_species_button is not None:
            self._open_species_button.configure(state="disabled")

    def get_base_inputs(self) -> InputParameters:
        return self._input_panel.get_input_parameters()

    def get_chamber_commit_updates(self) -> dict[str, object]:
        return self._chamber_geometry_panel.get_live_commit_updates()

    def get_nozzle_commit_updates(self) -> dict[str, object]:
        return self._geometry_editor_panel.get_geometry_updates()

    def get_material_commit_updates(self) -> dict[str, object]:
        return self._material_panel.get_material_updates()

    def collect_draft_inputs(self) -> InputParameters:
        base_inputs = self.get_base_inputs()
        updates: dict[str, object] = {}
        try:
            updates.update(self.get_chamber_commit_updates())
        except InputValidationError:
            if getattr(self._chamber_geometry_panel, "_current_bundle", None) is not None:
                raise
        updates.update(self.get_nozzle_commit_updates())
        updates.update(self.get_material_commit_updates())
        return replace(base_inputs, **updates)

    def get_combustion_efficiency_assumption(self) -> float:
        return self._input_panel.get_combustion_efficiency_assumption()

    def get_divergent_loss_enabled(self) -> bool:
        return self._input_panel.get_divergent_loss_enabled()

    def set_current_design_field_locks(self, locked_fields: set[str]) -> None:
        self._input_panel.set_current_design_field_locks(locked_fields)

    def set_committed_divergent_loss(
        self,
        *,
        divergent_loss_factor: float | None,
        source_text: str | None,
    ) -> None:
        self._input_panel.set_committed_divergent_loss(
            divergent_loss_factor=divergent_loss_factor,
            source_text=source_text,
        )

    def clear_committed_divergent_loss(self) -> None:
        self._input_panel.clear_committed_divergent_loss()

    def get_visible_contour_bundle(self) -> ExportBundle | None:
        return self._visible_bundle

    def bind_inputs_changed(self, callback: Callable[[], None]) -> None:
        self._input_panel.bind_inputs_changed(callback)
        self._chamber_geometry_panel.bind_inputs_changed(callback)
        self._geometry_editor_panel.bind_inputs_changed(callback)
        self._material_panel.bind_inputs_changed(callback)

    def bind_commit_recalculate(self, callback: Callable[[], None]) -> None:
        self._commit_callback = callback

    def bind_sync_from_initial(self, callback: Callable[[], None]) -> None:
        self._sync_callback = callback

    def bind_export_all(self, callback: Callable[[], None]) -> None:
        self._export_callback = callback

    def bind_clear_errors(self, callback: Callable[[], None]) -> None:
        self._clear_errors_callback = callback

    def bind_point_selected(self, callback: Callable[[ThermochemistryProfilePoint], None]) -> None:
        self._point_selected_callback = callback

    def bind_apply_selected_of(self, callback: Callable[[], None]) -> None:
        self._apply_selected_of_callback = callback

    def bind_of_selected(self, callback: Callable[[OFSweepPoint], None]) -> None:
        self._of_point_selected_callback = callback

    def bind_metric_changed(self, callback: Callable[[], None]) -> None:
        self._metric_changed_callback = callback

    def bind_preview_update(self, callback: Callable[[], None]) -> None:
        self._preview_update_callback = callback

    def begin_geometry_update(self) -> None:
        self._suspend_geometry_redraw = True
        self._pending_geometry_redraw = False

    def end_geometry_update(self) -> None:
        self._suspend_geometry_redraw = False
        if self._pending_geometry_redraw:
            self._pending_geometry_redraw = False
            self._refresh_geometry_view()

    def _request_geometry_redraw(self) -> None:
        if self._suspend_geometry_redraw:
            self._pending_geometry_redraw = True
            return
        self._refresh_geometry_view()

    def _refresh_geometry_view(self) -> None:
        active_bundle = self._preview_bundle or self._committed_bundle
        active_separation = self._preview_separation_point if self._preview_bundle is not None else self._committed_separation_point
        active_wall_thickness = getattr(self, "_preview_wall_thickness_m", None) if self._preview_bundle is not None else getattr(self, "_committed_wall_thickness_m", None)
        self._visible_bundle = active_bundle
        if active_bundle is None:
            self._geometry_view_note_var.set("Committed Current Design will appear here after the first full recalculation.")
            self._contour_plot_frame.update_contour([], [], [])
            if self._species_summary_panel is not None and self._species_popup is not None and self._species_popup.winfo_exists() and self._species_popup.state() != "withdrawn":
                self._species_summary_panel.clear()
            return
        if self._preview_bundle is not None and self._committed_bundle is not None:
            self._geometry_view_note_var.set(
                "Showing the live draft preview. Thermochemistry was remapped from the last committed CEA result; downstream modules still use the committed contour until you recommit."
            )
        elif self._preview_bundle is not None:
            self._geometry_view_note_var.set(
                "Showing a preview-only geometry state. Downstream modules remain blocked until the first committed recalculation exists."
            )
        else:
            self._geometry_view_note_var.set("Showing the committed Current Design contour.")
        self._contour_plot_frame.update_contour(
            active_bundle.contour,
            active_bundle.thermochemistry_profile,
            build_contour_markers(active_bundle, active_separation),
            wall_thickness_m=active_wall_thickness,
        )
        if self._species_summary_panel is not None and self._species_popup is not None and self._species_popup.winfo_exists() and self._species_popup.state() != "withdrawn":
            self._refresh_species_popup_content()

    def _handle_commit_recalculate(self) -> None:
        if self._commit_callback is not None:
            self._commit_callback()

    def _handle_preview_update(self) -> None:
        if self._preview_update_callback is not None:
            self._preview_update_callback()

    def _handle_sync_from_initial(self) -> None:
        if self._sync_callback is not None:
            self._sync_callback()

    def _handle_export(self) -> None:
        if self._export_callback is not None:
            self._export_callback()

    def _handle_clear_errors(self) -> None:
        if self._clear_errors_callback is not None:
            self._clear_errors_callback()

    def _handle_point_selected(self, profile_point: ThermochemistryProfilePoint) -> None:
        self._selected_profile_point = profile_point
        self._selected_station_var.set(
            "Selected station: "
            f"x = {format_quantity(profile_point.x_m, 'length', self._unit_preset, include_unit=True)}, "
            f"r = {format_quantity(profile_point.radius_m, 'length', self._unit_preset, include_unit=True)}"
        )
        if self._open_species_button is not None:
            self._open_species_button.configure(state="normal")
        if self._species_popup is not None and self._species_popup.winfo_exists() and self._species_popup.state() != "withdrawn":
            self._open_species_notes_popup()
        if self._point_selected_callback is not None:
            self._point_selected_callback(profile_point)

    def _handle_apply_selected_of(self) -> None:
        if self._apply_selected_of_callback is not None:
            self._apply_selected_of_callback()

    def _handle_of_point_selected(self, point: OFSweepPoint) -> None:
        if self._of_point_selected_callback is not None:
            self._of_point_selected_callback(point)

    def _handle_metric_changed(self, _event: object) -> None:
        if self._metric_changed_callback is not None:
            self._metric_changed_callback()

    def _ensure_species_popup_panel(self) -> SummaryPanel:
        if self._species_summary_panel is not None and self._species_popup is not None and self._species_popup.winfo_exists():
            return self._species_summary_panel
        popup = tk.Toplevel(self)
        popup.title("Species and Notes")
        popup.geometry("720x760")
        popup.withdraw()
        popup.protocol("WM_DELETE_WINDOW", popup.withdraw)
        panel = SummaryPanel(popup, unit_preset=self._unit_preset)
        panel.pack(fill="both", expand=True)
        self._species_popup = popup
        self._species_summary_panel = panel
        return panel

    def _ensure_of_sweep_popup_plot(self) -> OFSweepPlotFrame:
        if self._popup_of_sweep_plot is not None and self._of_sweep_popup is not None and self._of_sweep_popup.winfo_exists():
            return self._popup_of_sweep_plot
        popup = tk.Toplevel(self)
        popup.title("O/F Sweep")
        popup.geometry("860x620")
        popup.withdraw()
        popup.protocol("WM_DELETE_WINDOW", popup.withdraw)
        plot = OFSweepPlotFrame(
            popup,
            on_point_selected=self._handle_of_point_selected,
            unit_preset=self._unit_preset,
        )
        plot.pack(fill="both", expand=True)
        self._of_sweep_popup = popup
        self._popup_of_sweep_plot = plot
        return plot

    def _refresh_species_popup_content(self) -> None:
        panel = self._ensure_species_popup_panel()
        if self._selected_profile_point is not None and self._visible_bundle is not None:
            panel.show_profile_point(self._selected_profile_point, self._visible_bundle)
        elif self._visible_bundle is not None:
            panel.show_default_summary(self._visible_bundle)
        else:
            panel.clear()

    def _open_species_notes_popup(self) -> None:
        popup = self._ensure_species_popup_panel().master
        self._refresh_species_popup_content()
        popup.deiconify()
        popup.lift()
        popup.focus_force()

    def _open_of_sweep_popup(self) -> None:
        popup = self._ensure_of_sweep_popup_plot().master
        popup.deiconify()
        popup.lift()
        popup.focus_force()

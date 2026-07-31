"""Design-side R-Network Builder page for AstraForge."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from engine.gui.project_panels import ScrollableContentFrame
from engine.gui.r_network_preview import NetworkPreviewPanel
from engine.models import ExportBundle, InputParameters
from engine.thermal_analysis import (
    CommittedThermalNetwork,
    ThermalAnalysisInputs,
    ThermalNetworkBuildResult,
)
from engine.unit_system import UnitPreset, format_quantity


class _DesignContextStrip(ttk.LabelFrame):
    """Compact committed-design status for the builder workflow."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset) -> None:
        super().__init__(master, text="Design Context", padding=12)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(3, weight=1)
        self._unit_preset = unit_preset
        self._vars = {
            "design_status": tk.StringVar(value="No committed result"),
            "geometry_source": tk.StringVar(value="No committed contour"),
            "station_count": tk.StringVar(value="--"),
            "wall_material": tk.StringVar(value="--"),
            "wall_thickness": tk.StringVar(value="--"),
            "contour_status": tk.StringVar(value="No committed contour available."),
        }
        fields = [
            ("design_status", "Geometry status"),
            ("geometry_source", "Geometry source"),
            ("station_count", "Station count"),
            ("wall_material", "Wall material"),
            ("wall_thickness", "Wall thickness"),
        ]
        for index, (key, label) in enumerate(fields):
            row = index // 2
            column = (index % 2) * 2
            ttk.Label(self, text=label).grid(row=row, column=column, sticky="w", padx=(0, 8), pady=3)
            ttk.Label(self, textvariable=self._vars[key]).grid(row=row, column=column + 1, sticky="w", pady=3)
        ttk.Label(
            self,
            textvariable=self._vars["contour_status"],
            wraplength=980,
            justify="left",
        ).grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 0))

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        self._unit_preset = unit_preset

    def update_context(
        self,
        *,
        current_inputs: InputParameters | None,
        current_bundle: ExportBundle | None,
        design_status_label: str,
        geometry_source_label: str,
        contour_status_label: str,
        profile_station_count: int | None,
    ) -> None:
        self._vars["design_status"].set(design_status_label)
        self._vars["geometry_source"].set(geometry_source_label)
        self._vars["station_count"].set("--" if profile_station_count is None else str(profile_station_count))
        self._vars["wall_material"].set(
            current_inputs.liner_material if current_inputs is not None else "--"
        )
        self._vars["wall_thickness"].set(
            format_quantity(
                current_inputs.wall_thickness_m if current_inputs is not None else None,
                "length",
                self._unit_preset,
                include_unit=True,
            )
        )
        self._vars["contour_status"].set(contour_status_label)


class _RNetworkStateStrip(ttk.LabelFrame):
    """Compact draft/committed state summary for the R-Network workflow."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Workflow Status", padding=12)
        for column in range(4):
            self.columnconfigure(column, weight=1)
        self._draft_var = tk.StringVar(value="Draft R-Network: not built")
        self._committed_var = tk.StringVar(value="Committed R-Network: none")
        self._build_var = tk.StringVar(value="Active solved model: Annulus baseline")
        self._note_var = tk.StringVar(
            value="Geometry -> R-Network Builder -> Thermal Analysis. Build a draft network, inspect it, then commit it."
        )
        ttk.Label(self, textvariable=self._build_var, foreground="#244a6d").grid(row=0, column=0, sticky="w")
        ttk.Label(self, textvariable=self._draft_var).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(self, textvariable=self._committed_var).grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Label(self, text="Cooling layout: stationwise matrix placeholder").grid(
            row=0, column=3, sticky="w", padx=(8, 0)
        )
        ttk.Label(self, textvariable=self._note_var, wraplength=980, justify="left").grid(
            row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0)
        )

    def set_active_model(self, thermal_inputs: ThermalAnalysisInputs | None) -> None:
        if thermal_inputs is None:
            self._build_var.set("Active solved model: Annulus baseline")
            return
        self._build_var.set(
            f"Layout preset: Annulus baseline | Flow direction: {thermal_inputs.flow_direction.value}"
        )

    def update_state(
        self,
        *,
        draft_network: ThermalNetworkBuildResult | None,
        committed_network: CommittedThermalNetwork | None,
        stale_notes: tuple[str, ...] = (),
    ) -> None:
        if draft_network is None:
            self._draft_var.set("Draft R-Network: not built")
        else:
            self._draft_var.set(
                f"Draft R-Network: {draft_network.status.upper()} | {draft_network.build_id} | "
                f"{len(draft_network.station_networks)} station network(s)"
            )
        if committed_network is None:
            self._committed_var.set("Committed R-Network: none")
        else:
            self._committed_var.set(
                f"Committed R-Network: {committed_network.status.upper()} | {committed_network.build_id}"
            )
        if stale_notes:
            self._note_var.set("\n".join(f"- {note}" for note in stale_notes))
        elif committed_network is not None and committed_network.notes:
            self._note_var.set("\n".join(f"- {note}" for note in committed_network.notes))
        else:
            self._note_var.set(
                "Thermal Analysis uses only the committed R-Network. Draft networks stay builder-only until committed."
            )


class _CoolingLayoutMatrixPlaceholderCard(ttk.LabelFrame):
    """Large placeholder visual area for the future matrix editor."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Cooling Layout Matrix", padding=12)
        self.columnconfigure(0, weight=1)
        ttk.Label(
            self,
            text=(
                "This is the dedicated layout/topology area. The current MVP keeps an annulus baseline over the full contour "
                "and reserves the matrix for future stationwise segment editing."
            ),
            wraplength=980,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        matrix = ttk.Frame(self, padding=(10, 12, 10, 12), style="")
        matrix.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        matrix.columnconfigure(1, weight=1)
        lane_labels = (
            "Outside / ambient",
            "Outer hull / closeout",
            "Coolant circuit",
            "Wall / liner",
            "Film / transpiration / ablative (future)",
            "Hot-gas boundary T_aw",
            "Radiation",
        )
        for row, label in enumerate(lane_labels):
            ttk.Label(matrix, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            bar = ttk.Label(
                matrix,
                text="Annulus baseline over full contour" if label == "Coolant circuit" else "Placeholder lane",
                anchor="w",
                background="#e7eef6" if label == "Coolant circuit" else "#f3f5f7",
                foreground="#244a6d" if label == "Coolant circuit" else "#667381",
                padding=(8, 4),
            )
            bar.grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Label(
            self,
            text="Future segment types will appear here as stationwise bars and keyframes instead of a long disabled input form.",
            wraplength=980,
            justify="left",
            foreground="#667381",
        ).grid(row=2, column=0, sticky="ew", pady=(10, 0))


class _SelectedSegmentDefinitionPanel(ttk.LabelFrame):
    """Read-only station/segment definition summary for the current baseline layout."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset) -> None:
        super().__init__(master, text="Selected Segment / Station Definition", padding=12)
        self.columnconfigure(1, weight=1)
        self._unit_preset = unit_preset
        self._summary_var = tk.StringVar(value="Annulus baseline | Range: full contour")
        self._mechanisms_var = tk.StringVar(value="Mechanisms: hot-gas convection, wall conduction, coolant convection")
        ttk.Label(self, text="Selection").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Label(self, textvariable=self._summary_var).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(self, text="Mechanisms").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Label(self, textvariable=self._mechanisms_var, wraplength=900, justify="left").grid(
            row=1, column=1, sticky="ew", pady=4
        )

    def set_inputs(self, thermal_inputs: ThermalAnalysisInputs | None) -> None:
        if thermal_inputs is None:
            self._summary_var.set("Annulus baseline | Range: full contour")
            self._mechanisms_var.set(
                "Mechanisms: hot-gas convection, wall conduction, coolant convection"
            )
            return
        self._summary_var.set(
            "Annulus baseline | Range: full contour | "
            f"Flow direction: {thermal_inputs.flow_direction.value} | "
            f"Gap: {format_quantity(thermal_inputs.annulus_gap_m, 'length', self._unit_preset, include_unit=True)}"
        )
        mechanisms = ["hot-gas convection", "wall conduction", "coolant convection"]
        if thermal_inputs.radiation_settings.enabled:
            mechanisms.append("radiation")
        self._mechanisms_var.set("Mechanisms: " + ", ".join(mechanisms))


class _LayoutPresetCard(ttk.LabelFrame):
    """Compact preset summary instead of a full solver-input stack."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Layout Preset", padding=12)
        self.columnconfigure(0, weight=1)
        self._active_var = tk.StringVar(value="Annulus baseline")
        ttk.Label(self, textvariable=self._active_var, foreground="#244a6d").grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text=(
                "Future presets: tube bundle, milled channels, additive channels, custom. "
                "These stay placeholders here instead of long disabled thermal-input forms."
            ),
            wraplength=980,
            justify="left",
            foreground="#667381",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def set_inputs(self, thermal_inputs: ThermalAnalysisInputs | None) -> None:
        if thermal_inputs is None:
            self._active_var.set("Annulus baseline")
            return
        self._active_var.set(
            f"Annulus baseline | Active solved model: {thermal_inputs.model_type.value}"
        )


class _RNetworkBuilderActionRow(ttk.LabelFrame):
    """Builder-side actions before Thermal Analysis consumes a committed network."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Build Controls", padding=12)
        for column in range(5):
            self.columnconfigure(column, weight=1)
        self._validate_button = ttk.Button(self, text="Validate Layout")
        self._validate_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._build_button = ttk.Button(self, text="Build R-Network")
        self._build_button.grid(row=0, column=1, sticky="ew", padx=6)
        self._commit_button = ttk.Button(self, text="Commit R-Network")
        self._commit_button.grid(row=0, column=2, sticky="ew", padx=6)
        self._reset_button = ttk.Button(self, text="Reset to Annulus Baseline")
        self._reset_button.grid(row=0, column=3, sticky="ew", padx=6)
        self._go_button = ttk.Button(self, text="Go to Thermal Analysis")
        self._go_button.grid(row=0, column=4, sticky="ew", padx=(6, 0))
        self._helper_var = tk.StringVar(
            value="Validate the layout, build a draft R-Network, inspect the preview and commit it before Thermal Analysis."
        )
        ttk.Label(self, textvariable=self._helper_var, wraplength=980, justify="left").grid(
            row=1, column=0, columnspan=5, sticky="ew", pady=(8, 0)
        )
        self.set_commit_enabled(False)

    def bind_validate(self, callback: Callable[[], None]) -> None:
        self._validate_button.configure(command=callback)

    def bind_build(self, callback: Callable[[], None]) -> None:
        self._build_button.configure(command=callback)

    def bind_commit(self, callback: Callable[[], None]) -> None:
        self._commit_button.configure(command=callback)

    def bind_reset(self, callback: Callable[[], None]) -> None:
        self._reset_button.configure(command=callback)

    def bind_go_to_thermal(self, callback: Callable[[], None]) -> None:
        self._go_button.configure(command=callback)

    def set_commit_enabled(self, enabled: bool) -> None:
        self._commit_button.configure(state="normal" if enabled else "disabled")

    def set_validation_message(self, message: str) -> None:
        self._helper_var.set(message)


class RNetworkBuilderPage(ttk.Frame):
    """Design-side workflow page that builds and commits the thermal R-Network."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset) -> None:
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._unit_preset = unit_preset
        self._cached_inputs: ThermalAnalysisInputs | None = None
        self._draft_network: ThermalNetworkBuildResult | None = None
        self._committed_network: CommittedThermalNetwork | None = None

        scrollable = ScrollableContentFrame(self)
        scrollable.grid(row=0, column=0, sticky="nsew")
        content = scrollable.content
        content.columnconfigure(0, weight=1)

        header = ttk.Frame(content, padding=(0, 0, 0, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="R-Network Builder", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text="Build thermal R-network from committed geometry and cooling layout.",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        self._context_strip = _DesignContextStrip(content, unit_preset=unit_preset)
        self._context_strip.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        self._state_strip = _RNetworkStateStrip(content)
        self._state_strip.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        self._matrix_placeholder = _CoolingLayoutMatrixPlaceholderCard(content)
        self._matrix_placeholder.grid(row=3, column=0, sticky="ew", pady=(12, 0))

        self._selected_segment_panel = _SelectedSegmentDefinitionPanel(content, unit_preset=unit_preset)
        self._selected_segment_panel.grid(row=4, column=0, sticky="ew", pady=(12, 0))

        self._layout_preset_card = _LayoutPresetCard(content)
        self._layout_preset_card.grid(row=5, column=0, sticky="ew", pady=(12, 0))

        self._action_row = _RNetworkBuilderActionRow(content)
        self._action_row.grid(row=6, column=0, sticky="ew", pady=(12, 0))

        self._network_preview = NetworkPreviewPanel(content, unit_preset=unit_preset)
        self._network_preview.grid(row=7, column=0, sticky="ew", pady=(12, 0))

    def bind_validate_layout(self, callback: Callable[[], None]) -> None:
        self._action_row.bind_validate(callback)

    def bind_build_network(self, callback: Callable[[], None]) -> None:
        self._action_row.bind_build(callback)

    def bind_commit_network(self, callback: Callable[[], None]) -> None:
        self._action_row.bind_commit(callback)

    def bind_reset(self, callback: Callable[[], None]) -> None:
        self._action_row.bind_reset(callback)

    def bind_go_to_thermal(self, callback: Callable[[], None]) -> None:
        self._action_row.bind_go_to_thermal(callback)

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        self._unit_preset = unit_preset
        self._context_strip.set_unit_preset(unit_preset)
        self._selected_segment_panel._unit_preset = unit_preset
        self._network_preview._unit_preset = unit_preset
        if self._cached_inputs is not None:
            self.set_inputs(self._cached_inputs)

    def set_inputs(self, inputs: ThermalAnalysisInputs) -> None:
        self._cached_inputs = inputs
        self._state_strip.set_active_model(inputs)
        self._selected_segment_panel.set_inputs(inputs)
        self._layout_preset_card.set_inputs(inputs)

    def get_inputs(self) -> ThermalAnalysisInputs:
        if self._cached_inputs is None:
            raise RuntimeError("R-Network Builder has no thermal setup cached yet.")
        return self._cached_inputs

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
        self._context_strip.update_context(
            current_inputs=current_inputs,
            current_bundle=current_bundle,
            design_status_label=design_status_label,
            geometry_source_label=geometry_source_label,
            contour_status_label=contour_status_label,
            profile_station_count=profile_station_count,
        )
        self.set_inputs(thermal_inputs)

    def set_layout_validation_result(self, message: str) -> None:
        self._action_row.set_validation_message(message)

    def set_draft_network_build_result(self, result: ThermalNetworkBuildResult) -> None:
        self._draft_network = result
        self._network_preview.set_build_result(result)
        self._action_row.set_commit_enabled(result.status != "error")
        self._state_strip.update_state(
            draft_network=self._draft_network,
            committed_network=self._committed_network,
        )

    def get_draft_network_build_result(self) -> ThermalNetworkBuildResult | None:
        return self._draft_network

    def clear_draft_network_build_result(self) -> None:
        self._draft_network = None
        self._network_preview.clear()
        self._action_row.set_commit_enabled(False)
        self._state_strip.update_state(
            draft_network=self._draft_network,
            committed_network=self._committed_network,
        )

    def mark_draft_network_stale(self, messages: tuple[str, ...]) -> None:
        self._action_row.set_commit_enabled(False)
        self._network_preview.mark_stale(messages)
        self._state_strip.update_state(
            draft_network=self._draft_network,
            committed_network=self._committed_network,
            stale_notes=messages,
        )

    def set_committed_network(
        self,
        committed_network: CommittedThermalNetwork | None,
        *,
        stale_notes: tuple[str, ...] = (),
    ) -> None:
        self._committed_network = committed_network
        self._state_strip.update_state(
            draft_network=self._draft_network,
            committed_network=self._committed_network,
            stale_notes=stale_notes,
        )
        if self._draft_network is None:
            if committed_network is None:
                self._network_preview.clear()
                self._action_row.set_commit_enabled(False)
            else:
                self._network_preview.set_build_result(committed_network.network_build_result)

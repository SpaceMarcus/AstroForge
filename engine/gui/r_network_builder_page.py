"""Design-side R-Network Builder page for AstraForge."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from engine.gui.project_panels import ScrollableContentFrame
from engine.gui.thermal_analysis_page import (
    AnnulusCoolingCard,
    ExistingDesignContextCard,
    FutureChannelDefinitionPanel,
    NetworkPreviewPanel,
    RadiationCard,
    SolverSettingsCard,
)
from engine.models import ExportBundle, InputParameters
from engine.thermal_analysis import (
    CommittedThermalNetwork,
    ThermalAnalysisInputs,
    ThermalNetworkBuildResult,
)
from engine.unit_system import UnitPreset


class _RNetworkStateCard(ttk.LabelFrame):
    """Compact draft/committed state summary for the R-Network workflow."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="R-Network State", padding=12)
        self.columnconfigure(0, weight=1)
        self._draft_var = tk.StringVar(value="Draft: not built")
        self._committed_var = tk.StringVar(value="Committed: none")
        self._notes_var = tk.StringVar(
            value="Build a draft R-Network, inspect the preview, then commit it before running Thermal Analysis."
        )
        ttk.Label(self, textvariable=self._draft_var, foreground="#244a6d").grid(row=0, column=0, sticky="w")
        ttk.Label(self, textvariable=self._committed_var).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(self, textvariable=self._notes_var, wraplength=980, justify="left").grid(
            row=2, column=0, sticky="ew", pady=(8, 0)
        )

    def update_state(
        self,
        *,
        draft_network: ThermalNetworkBuildResult | None,
        committed_network: CommittedThermalNetwork | None,
        stale_notes: tuple[str, ...] = (),
    ) -> None:
        if draft_network is None:
            self._draft_var.set("Draft: not built")
        else:
            self._draft_var.set(
                f"Draft: {draft_network.status.upper()} | {draft_network.build_id} | "
                f"{len(draft_network.station_networks)} station networks"
            )
        if committed_network is None:
            self._committed_var.set("Committed: none")
        else:
            self._committed_var.set(
                f"Committed: {committed_network.status.upper()} | {committed_network.build_id}"
            )
        if stale_notes:
            self._notes_var.set("\n".join(f"- {note}" for note in stale_notes))
        elif committed_network is not None and committed_network.notes:
            self._notes_var.set("\n".join(f"- {note}" for note in committed_network.notes))
        else:
            self._notes_var.set(
                "Draft R-Networks are editable previews. Thermal Analysis uses only the committed R-Network."
            )


class _CoolingMatrixPlaceholderCard(ttk.LabelFrame):
    """Placeholder for the future stationwise cooling matrix editor."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Cooling Layout / Matrix Editor", padding=12)
        self.columnconfigure(0, weight=1)
        ttk.Label(
            self,
            text=(
                "Stationwise keyframe-based cooling layout editing is planned here. "
                "The current MVP still builds an annulus baseline network over the full committed contour."
            ),
            wraplength=980,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            self,
            text=(
                "Planned lanes: outside boundary, closeout/hull, coolant circuit, wall/liner, "
                "film/transpiration placeholders, hot-gas boundary T_aw and radiation."
            ),
            wraplength=980,
            justify="left",
            foreground="#667381",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))


class _RNetworkBuilderActionRow(ttk.LabelFrame):
    """Builder-side actions before Thermal Analysis consumes a committed network."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="R-Network Build Controls", padding=12)
        self.columnconfigure(0, weight=1)
        for column in range(4):
            self.columnconfigure(column, weight=1)
        self._build_button = ttk.Button(self, text="Build R-Network")
        self._build_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._commit_button = ttk.Button(self, text="Commit R-Network")
        self._commit_button.grid(row=0, column=1, sticky="ew", padx=6)
        self._reset_button = ttk.Button(self, text="Reset to Annulus Baseline")
        self._reset_button.grid(row=0, column=2, sticky="ew", padx=6)
        self._go_button = ttk.Button(self, text="Go to Thermal Analysis")
        self._go_button.grid(row=0, column=3, sticky="ew", padx=(6, 0))
        self._helper_var = tk.StringVar(
            value="Build a draft R-Network, inspect the preview, then commit it for Thermal Analysis."
        )
        ttk.Label(self, textvariable=self._helper_var, wraplength=980, justify="left").grid(
            row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0)
        )
        self.set_commit_enabled(False)

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
            text="Build and commit the thermal resistance/conductance network before Thermal Analysis runs.",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        self._context_card = ExistingDesignContextCard(content, unit_preset=unit_preset)
        self._context_card.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        self._state_card = _RNetworkStateCard(content)
        self._state_card.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        self._matrix_placeholder = _CoolingMatrixPlaceholderCard(content)
        self._matrix_placeholder.grid(row=3, column=0, sticky="ew", pady=(12, 0))

        input_row = ttk.Frame(content)
        input_row.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        input_row.columnconfigure(0, weight=1)
        input_row.columnconfigure(1, weight=1)
        self._annulus_card = AnnulusCoolingCard(input_row, unit_preset=unit_preset)
        self._annulus_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._solver_card = SolverSettingsCard(input_row)
        self._solver_card.grid(row=0, column=1, sticky="nsew")

        self._radiation_card = RadiationCard(content, unit_preset=unit_preset)
        self._radiation_card.grid(row=5, column=0, sticky="ew", pady=(12, 0))

        self._future_channel_panel = FutureChannelDefinitionPanel(content)
        self._future_channel_panel.grid(row=6, column=0, sticky="ew", pady=(12, 0))

        self._action_row = _RNetworkBuilderActionRow(content)
        self._action_row.grid(row=7, column=0, sticky="ew", pady=(12, 0))

        self._network_preview = NetworkPreviewPanel(content, unit_preset=unit_preset)
        self._network_preview.grid(row=8, column=0, sticky="ew", pady=(12, 0))

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
        self._context_card.set_unit_preset(unit_preset)
        self._annulus_card.set_unit_preset(unit_preset)
        self._radiation_card.set_unit_preset(unit_preset)
        self._network_preview._unit_preset = unit_preset
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
            primary_coolant_nusselt_method=partial_inputs["primary_coolant_nusselt_method"],
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

    def set_draft_network_build_result(self, result: ThermalNetworkBuildResult) -> None:
        self._draft_network = result
        self._network_preview.set_build_result(result)
        self._action_row.set_commit_enabled(result.status != "error")
        self._state_card.update_state(
            draft_network=self._draft_network,
            committed_network=self._committed_network,
        )

    def get_draft_network_build_result(self) -> ThermalNetworkBuildResult | None:
        return self._draft_network

    def clear_draft_network_build_result(self) -> None:
        self._draft_network = None
        self._network_preview.clear()
        self._action_row.set_commit_enabled(False)
        self._state_card.update_state(
            draft_network=self._draft_network,
            committed_network=self._committed_network,
        )

    def mark_draft_network_stale(self, messages: tuple[str, ...]) -> None:
        self._action_row.set_commit_enabled(False)
        self._network_preview.mark_stale(messages)
        self._state_card.update_state(
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
        self._state_card.update_state(
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

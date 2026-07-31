"""Shared R-network preview widgets used by the design-side builder workflow."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from engine.thermal_analysis import StationThermalNetwork, ThermalNetworkBuildResult
from engine.unit_system import UnitPreset, format_quantity


def _fmt_quantity(value: float | None, quantity: str, unit_preset: UnitPreset) -> str:
    return format_quantity(value, quantity, unit_preset)


class NetworkPreviewPanel(ttk.LabelFrame):
    """Preview of the built thermal R-network before solving.

    The builder owns the full mapping preview so the Thermal Analysis tab can
    stay focused on solving and results instead of repeating the same network
    inspection UI.
    """

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset) -> None:
        super().__init__(master, text="R-Network Preview", padding=12)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._unit_preset = unit_preset
        self._result: ThermalNetworkBuildResult | None = None
        self._status_var = tk.StringVar(value="Not built")
        self._summary_var = tk.StringVar(
            value="Build the R-network to preview the segment-to-station mapping and station network sketch."
        )
        self._warnings_var = tk.StringVar(value="--")
        self._station_selector_var = tk.StringVar(value="")
        self._station_sketch_var = tk.StringVar(value="No R-network selected yet.")
        ttk.Label(self, textvariable=self._status_var, foreground="#244a6d").grid(row=0, column=0, sticky="w")
        ttk.Label(self, textvariable=self._summary_var, wraplength=980, justify="left").grid(
            row=1, column=0, sticky="ew", pady=(6, 0)
        )
        mapping_frame = ttk.Frame(self)
        mapping_frame.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        mapping_frame.columnconfigure(0, weight=1)
        mapping_frame.rowconfigure(1, weight=1)
        ttk.Label(mapping_frame, text="Segment-to-station mapping").grid(row=0, column=0, sticky="w")
        self._mapping_tree = ttk.Treeview(
            mapping_frame,
            columns=("segment", "model", "range", "station_count", "flow_direction", "mechanisms", "status"),
            show="headings",
            height=6,
        )
        self._mapping_tree.grid(row=1, column=0, sticky="nsew")
        for key, label, width in (
            ("segment", "Segment", 180),
            ("model", "Model", 160),
            ("range", "Range", 160),
            ("station_count", "Station count", 100),
            ("flow_direction", "Flow direction", 130),
            ("mechanisms", "Mechanisms", 220),
            ("status", "Status", 180),
        ):
            self._mapping_tree.heading(key, text=label)
            self._mapping_tree.column(key, width=width, stretch=False, anchor="center")
        station_frame = ttk.LabelFrame(self, text="Selected station R-network", padding=8)
        station_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        station_frame.columnconfigure(1, weight=1)
        ttk.Label(station_frame, text="Station").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._station_selector = ttk.Combobox(
            station_frame,
            state="readonly",
            textvariable=self._station_selector_var,
        )
        self._station_selector.grid(row=0, column=1, sticky="ew")
        self._station_selector.bind("<<ComboboxSelected>>", self._handle_station_selected)
        ttk.Label(station_frame, textvariable=self._station_sketch_var, wraplength=980, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        ttk.Label(self, textvariable=self._warnings_var, wraplength=980, justify="left", foreground="#7d4d1b").grid(
            row=4, column=0, sticky="ew", pady=(12, 0)
        )

    def clear(self) -> None:
        self._result = None
        self._status_var.set("Not built")
        self._summary_var.set(
            "Build the R-network to preview the segment-to-station mapping and station network sketch."
        )
        self._warnings_var.set("--")
        self._station_selector.configure(values=())
        self._station_selector_var.set("")
        self._station_sketch_var.set("No R-network selected yet.")
        for item in self._mapping_tree.get_children():
            self._mapping_tree.delete(item)

    def set_build_result(self, result: ThermalNetworkBuildResult) -> None:
        self.clear()
        self._result = result
        self._status_var.set(
            f"{result.status.upper()} | Builder: {result.active_station_network_builder} | Build ID: {result.build_id}"
        )
        self._summary_var.set(f"{result.summary}\n{result.setup_summary}")
        warning_lines = list(result.warnings) + list(result.errors)
        self._warnings_var.set("--" if not warning_lines else "\n".join(f"- {line}" for line in warning_lines))
        mapping_counts: dict[str, int] = {}
        for station_network in result.station_networks:
            mapping_counts[station_network.segment_node_id] = mapping_counts.get(station_network.segment_node_id, 0) + 1
        for assignment in result.segment_assignments:
            mechanisms = ", ".join(mechanism.value for mechanism in assignment.active_mechanisms) or "--"
            self._mapping_tree.insert(
                "",
                "end",
                values=(
                    assignment.segment_label,
                    assignment.segment_model_type.value,
                    assignment.range_label,
                    mapping_counts.get(assignment.segment_node_id, 0),
                    assignment.flow_direction.value,
                    mechanisms,
                    "mapped",
                ),
            )
        selector_values = [
            f"{network.station_id}: {network.segment_label} @ {network.region_label}"
            for network in result.station_networks
        ]
        self._station_selector.configure(values=selector_values)
        if selector_values:
            self._station_selector_var.set(selector_values[0])
            self._update_station_preview(result.station_networks[0])

    def mark_stale(self, messages: tuple[str, ...]) -> None:
        if self._result is None:
            self._status_var.set("STALE | R-Network changed before the first solve.")
            self._warnings_var.set("\n".join(f"- {message}" for message in messages))
            return
        self._status_var.set(f"STALE | Last build {self._result.build_id}")
        self._warnings_var.set("\n".join(f"- {message}" for message in messages))

    def _handle_station_selected(self, _event: object) -> None:
        if self._result is None:
            return
        selection = self._station_selector_var.get()
        prefix = selection.split(":", 1)[0].strip()
        try:
            station_id = int(prefix)
        except ValueError:
            return
        for network in self._result.station_networks:
            if network.station_id == station_id:
                self._update_station_preview(network)
                break

    def _update_station_preview(self, network: StationThermalNetwork) -> None:
        lines = [
            network.network_sketch
            + (" + Q_rad" if any(element.element_type == "radiation_heat_source" for element in network.elements) else ""),
            f"Segment: {network.segment_label} ({network.segment_model_type.value})",
            f"Flow direction: {network.flow_direction.value}",
            f"Integration rule: {network.integration_rule_label}",
            f"A_flow: {_fmt_quantity(network.flow_area_m2, 'area', self._unit_preset)}",
            f"A_hot: {_fmt_quantity(network.hot_wall_area_m2, 'area', self._unit_preset)}",
            f"A_cool: {_fmt_quantity(network.coolant_wall_area_m2, 'area', self._unit_preset)}",
            f"D_h: {_fmt_quantity(network.hydraulic_diameter_m, 'length', self._unit_preset)}",
        ]
        if network.notes:
            lines.append("Notes:")
            lines.extend(f"- {note}" for note in network.notes)
        if network.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in network.warnings)
        self._station_sketch_var.set("\n".join(lines))

"""Interactive engine-cycle pump, turbine and shaft-power workspace."""

from __future__ import annotations

import csv
import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from engine.cycle import (
    CycleDefinition,
    CycleType,
    PumpDefinition,
    RpaCycleSeed,
    ShaftDefinition,
    TurbineDefinition,
    cycle_seed_from_rpa_config,
    solve_cycle,
)
from engine.models import ExportBundle
from engine.properties import get_coolant_properties


_CYCLE_LABELS = {
    "Gas generator": CycleType.GAS_GENERATOR,
    "Staged combustion": CycleType.STAGED_COMBUSTION,
    "Full-flow staged combustion": CycleType.FULL_FLOW_STAGED_COMBUSTION,
    "Expander": CycleType.EXPANDER,
}
_CYCLE_LABEL_BY_TYPE = {value: key for key, value in _CYCLE_LABELS.items()}
_SHAFT_LABELS = ("Single combined shaft", "Two independent shafts")


class EngineCyclePage(ttk.Frame):
    """Preliminary cycle design with explicit component and shaft balances."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._bundle: ExportBundle | None = None
        self._result = None
        self._rpa_seed: RpaCycleSeed | None = None
        self._pending_rpa_seed = False
        self._status = tk.StringVar(
            value="Commit and recalculate Current Design to activate Engine Cycle."
        )
        self._kpis = {
            "pump_power": tk.StringVar(value="--"),
            "turbine_flow": tk.StringVar(value="--"),
            "flow_fraction": tk.StringVar(value="--"),
            "turbine_outlet": tk.StringVar(value="--"),
            "engine_flow": tk.StringVar(value="--"),
            "balance": tk.StringVar(value="--"),
        }
        self._vars = self._default_variables()
        self._build_header()
        self._build_workspace()

    def _default_variables(self) -> dict[str, tk.Variable]:
        return {
            "cycle": tk.StringVar(value="Gas generator"),
            "shafts": tk.StringVar(value=_SHAFT_LABELS[0]),
            "oxidizer_temperature_k": tk.StringVar(value="90.0"),
            "oxidizer_density": tk.StringVar(value="1140.0"),
            "oxidizer_inlet_bar": tk.StringVar(value="5.0"),
            "oxidizer_outlet_bar": tk.StringVar(value="120.0"),
            "oxidizer_efficiency": tk.StringVar(value="0.75"),
            "fuel_temperature_k": tk.StringVar(value="293.15"),
            "fuel_density": tk.StringVar(value="810.0"),
            "fuel_inlet_bar": tk.StringVar(value="4.0"),
            "fuel_outlet_bar": tk.StringVar(value="135.0"),
            "fuel_efficiency": tk.StringVar(value="0.70"),
            "turbine_temperature_k": tk.StringVar(value="900.0"),
            "turbine_inlet_bar": tk.StringVar(value="160.0"),
            "oxidizer_turbine_pr": tk.StringVar(value="2.0"),
            "oxidizer_turbine_efficiency": tk.StringVar(value="0.75"),
            "fuel_turbine_pr": tk.StringVar(value="2.0"),
            "fuel_turbine_efficiency": tk.StringVar(value="0.75"),
            "turbine_mechanical_efficiency": tk.StringVar(value="0.98"),
            "turbine_cp": tk.StringVar(value="3000.0"),
            "turbine_gamma": tk.StringVar(value="1.25"),
            "accessory_power_kw": tk.StringVar(value="0.0"),
        }

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(14, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Engine Cycle", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text=(
                "Pump pressure work, turbine expansion, independent shafts and "
                "closed power balances using the committed engine mass flow."
            ),
            foreground="#526579",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        buttons = ttk.Frame(header)
        buttons.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(buttons, text="Calculate Cycle", command=self.recalculate).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="Export Cycle CSV", command=self._export_csv).pack(
            side="left"
        )
        ttk.Label(
            header,
            textvariable=self._status,
            wraplength=1180,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _build_workspace(self) -> None:
        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        controls_host = ttk.Frame(pane, width=380)
        results = ttk.Frame(pane)
        results.columnconfigure(0, weight=1)
        results.rowconfigure(1, weight=1)
        pane.add(controls_host, weight=1)
        pane.add(results, weight=3)
        self._build_controls(controls_host)
        self._build_kpis(results)
        self._build_results(results)

    def _build_controls(self, master: ttk.Frame) -> None:
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        canvas = tk.Canvas(master, highlightthickness=0, width=380)
        scrollbar = ttk.Scrollbar(master, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=(4, 2, 10, 8))
        content.columnconfigure(0, weight=1)
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window, width=event.width),
        )

        topology = ttk.LabelFrame(content, text="Cycle Topology", padding=9)
        topology.grid(row=0, column=0, sticky="ew")
        topology.columnconfigure(1, weight=1)
        ttk.Label(topology, text="Cycle").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(
            topology,
            textvariable=self._vars["cycle"],
            values=tuple(_CYCLE_LABELS),
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=3)
        ttk.Label(topology, text="Shaft architecture").grid(
            row=1, column=0, sticky="w", pady=3
        )
        ttk.Combobox(
            topology,
            textvariable=self._vars["shafts"],
            values=_SHAFT_LABELS,
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=3)
        self._entry(topology, 2, "Accessory load [kW]", "accessory_power_kw")

        oxidizer = ttk.LabelFrame(content, text="Oxidizer Main Pump", padding=9)
        oxidizer.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        oxidizer.columnconfigure(1, weight=1)
        self._pump_entries(oxidizer, "oxidizer")

        fuel = ttk.LabelFrame(content, text="Fuel Main Pump", padding=9)
        fuel.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        fuel.columnconfigure(1, weight=1)
        self._pump_entries(fuel, "fuel")

        turbine = ttk.LabelFrame(content, text="Turbine Working Gas", padding=9)
        turbine.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        turbine.columnconfigure(1, weight=1)
        rows = (
            ("Inlet temperature [K]", "turbine_temperature_k"),
            ("Inlet pressure [bar]", "turbine_inlet_bar"),
            ("Main / oxidizer turbine PR", "oxidizer_turbine_pr"),
            ("Main / oxidizer turbine efficiency", "oxidizer_turbine_efficiency"),
            ("Fuel turbine PR", "fuel_turbine_pr"),
            ("Fuel turbine efficiency", "fuel_turbine_efficiency"),
            ("Mechanical efficiency", "turbine_mechanical_efficiency"),
            ("Gas cp [J/kgK]", "turbine_cp"),
            ("Gas gamma", "turbine_gamma"),
        )
        for row, (label, key) in enumerate(rows):
            self._entry(turbine, row, label, key)

    def _pump_entries(self, frame: ttk.Frame, prefix: str) -> None:
        rows = (
            ("Inlet temperature [K]", f"{prefix}_temperature_k"),
            ("Density [kg/m3]", f"{prefix}_density"),
            ("Inlet pressure [bar]", f"{prefix}_inlet_bar"),
            ("Discharge pressure [bar]", f"{prefix}_outlet_bar"),
            ("Pump efficiency", f"{prefix}_efficiency"),
        )
        for row, (label, key) in enumerate(rows):
            self._entry(frame, row, label, key)

    def _entry(self, frame: ttk.Frame, row: int, label: str, key: str) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self._vars[key]).grid(
            row=row, column=1, sticky="ew", padx=(6, 0), pady=3
        )

    def _build_kpis(self, master: ttk.Frame) -> None:
        cards = ttk.Frame(master, padding=(0, 0, 0, 8))
        cards.grid(row=0, column=0, sticky="ew")
        definitions = (
            ("Pump power", "pump_power"),
            ("Turbine flow", "turbine_flow"),
            ("Working-flow fraction", "flow_fraction"),
            ("Turbine outlet", "turbine_outlet"),
            ("Engine inlet flow", "engine_flow"),
            ("Shaft closure", "balance"),
        )
        for column, (label, key) in enumerate(definitions):
            cards.columnconfigure(column, weight=1)
            card = tk.Frame(
                cards,
                background="#f7f9fc",
                highlightbackground="#d8e0ea",
                highlightthickness=1,
                padx=9,
                pady=7,
            )
            card.grid(row=0, column=column, sticky="nsew", padx=(0, 5))
            tk.Label(
                card,
                text=label,
                background="#f7f9fc",
                foreground="#526579",
                font=("Segoe UI", 8),
            ).pack(anchor="w")
            tk.Label(
                card,
                textvariable=self._kpis[key],
                background="#f7f9fc",
                foreground="#16283d",
                font=("Segoe UI", 11, "bold"),
            ).pack(anchor="w", pady=(2, 0))

    def _build_results(self, master: ttk.Frame) -> None:
        notebook = ttk.Notebook(master)
        notebook.grid(row=1, column=0, sticky="nsew")
        chart_frame = ttk.Frame(notebook)
        table_frame = ttk.Frame(notebook)
        notebook.add(chart_frame, text="Power Balance")
        notebook.add(table_frame, text="Component Output")

        self._figure = Figure(figsize=(9.2, 5.8), dpi=100, facecolor="#ffffff")
        self._power_axis = self._figure.add_subplot(121)
        self._flow_axis = self._figure.add_subplot(122)
        self._figure.subplots_adjust(
            left=0.10, right=0.97, top=0.91, bottom=0.19, wspace=0.32
        )
        self._canvas = FigureCanvasTkAgg(self._figure, master=chart_frame)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._draw_empty_chart()

        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("kind", "component", "shaft", "flow", "pin", "pout", "eff", "power", "tout")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = (
            ("kind", "Type", 80),
            ("component", "Component", 125),
            ("shaft", "Shaft", 125),
            ("flow", "m [kg/s]", 90),
            ("pin", "pin [bar]", 90),
            ("pout", "pout [bar]", 90),
            ("eff", "Efficiency", 85),
            ("power", "Shaft power [MW]", 120),
            ("tout", "Tout [K]", 90),
        )
        for key, label, width in headings:
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=55, anchor="center")
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self._tree = tree

    def update_bundle(self, bundle: ExportBundle) -> None:
        first_committed_bundle = self._bundle is None
        self._bundle = bundle
        if first_committed_bundle:
            self._seed_from_bundle(bundle)
        if self._pending_rpa_seed and self._rpa_seed is not None:
            self._apply_rpa_seed(self._rpa_seed, bundle)
            self._pending_rpa_seed = False
        self.recalculate()

    def load_rpa_cycle_config(self, raw_config: dict[str, Any]) -> bool:
        seed = cycle_seed_from_rpa_config(raw_config)
        self._rpa_seed = seed
        self._pending_rpa_seed = seed is not None
        if seed is None:
            return False
        self._apply_rpa_seed(seed, self._bundle)
        if self._bundle is not None:
            self._pending_rpa_seed = False
            self.recalculate()
        return True

    def clear(self) -> None:
        self._bundle = None
        self._result = None
        self._rpa_seed = None
        self._pending_rpa_seed = False
        for variable in self._kpis.values():
            variable.set("--")
        self._tree.delete(*self._tree.get_children())
        self._status.set(
            "Commit and recalculate Current Design to activate Engine Cycle."
        )
        self._draw_empty_chart()

    def recalculate(self) -> None:
        if self._bundle is None:
            return
        try:
            definition = self._build_definition()
            self._result = solve_cycle(definition)
        except (KeyError, TypeError, ValueError) as exc:
            self._status.set(f"Cycle input error: {exc}")
            return
        self._refresh_kpis()
        self._refresh_table()
        self._refresh_chart()
        architecture = self._vars["shafts"].get()
        status = (
            f"{self._vars['cycle'].get()} calculation complete with {architecture.lower()}. "
            "All pump and turbine values are explicit preliminary component balances."
        )
        if self._rpa_seed is not None:
            status += " RPA feed-system values were applied where directly mappable."
            if self._rpa_seed.warnings:
                status += " " + " ".join(self._rpa_seed.warnings)
        self._status.set(status)

    def _build_definition(self) -> CycleDefinition:
        bundle = self._bundle
        if bundle is None:
            raise ValueError("No committed design is available.")
        total_flow = bundle.geometry.mass_flow_kg_per_s
        fuel_flow = total_flow / (1.0 + bundle.inputs.mixture_ratio)
        oxidizer_flow = total_flow - fuel_flow
        oxidizer_properties = get_coolant_properties(
            bundle.inputs.oxidizer,
            self._number("oxidizer_temperature_k"),
            self._number("oxidizer_inlet_bar") * 1.0e5,
        )
        fuel_properties = get_coolant_properties(
            bundle.inputs.fuel,
            self._number("fuel_temperature_k"),
            self._number("fuel_inlet_bar") * 1.0e5,
        )
        pumps = (
            PumpDefinition(
                pump_id="oxidizer-main-pump",
                fluid_id=bundle.inputs.oxidizer,
                mass_flow_kg_per_s=oxidizer_flow,
                density_kg_per_m3=self._number("oxidizer_density"),
                inlet_pressure_pa=self._number("oxidizer_inlet_bar") * 1.0e5,
                discharge_pressure_pa=self._number("oxidizer_outlet_bar") * 1.0e5,
                efficiency=self._number("oxidizer_efficiency"),
                inlet_temperature_k=self._number("oxidizer_temperature_k"),
                specific_heat_j_per_kg_k=oxidizer_properties.cp_j_per_kg_k,
            ),
            PumpDefinition(
                pump_id="fuel-main-pump",
                fluid_id=bundle.inputs.fuel,
                mass_flow_kg_per_s=fuel_flow,
                density_kg_per_m3=self._number("fuel_density"),
                inlet_pressure_pa=self._number("fuel_inlet_bar") * 1.0e5,
                discharge_pressure_pa=self._number("fuel_outlet_bar") * 1.0e5,
                efficiency=self._number("fuel_efficiency"),
                inlet_temperature_k=self._number("fuel_temperature_k"),
                specific_heat_j_per_kg_k=fuel_properties.cp_j_per_kg_k,
            ),
        )
        common_turbine = {
            "mass_flow_kg_per_s": None,
            "inlet_temperature_k": self._number("turbine_temperature_k"),
            "inlet_pressure_pa": self._number("turbine_inlet_bar") * 1.0e5,
            "specific_heat_j_per_kg_k": self._number("turbine_cp"),
            "gamma": self._number("turbine_gamma"),
            "mechanical_efficiency": self._number("turbine_mechanical_efficiency"),
        }
        accessory = self._number("accessory_power_kw") * 1.0e3
        if self._vars["shafts"].get() == _SHAFT_LABELS[0]:
            turbines = (
                TurbineDefinition(
                    turbine_id="main-turbine",
                    pressure_ratio=self._number("oxidizer_turbine_pr"),
                    isentropic_efficiency=self._number(
                        "oxidizer_turbine_efficiency"
                    ),
                    **common_turbine,
                ),
            )
            shafts = (
                ShaftDefinition(
                    shaft_id="combined-shaft",
                    pump_ids=("oxidizer-main-pump", "fuel-main-pump"),
                    turbine_ids=("main-turbine",),
                    accessory_power_w=accessory,
                ),
            )
        else:
            turbines = (
                TurbineDefinition(
                    turbine_id="oxidizer-turbine",
                    pressure_ratio=self._number("oxidizer_turbine_pr"),
                    isentropic_efficiency=self._number(
                        "oxidizer_turbine_efficiency"
                    ),
                    **common_turbine,
                ),
                TurbineDefinition(
                    turbine_id="fuel-turbine",
                    pressure_ratio=self._number("fuel_turbine_pr"),
                    isentropic_efficiency=self._number("fuel_turbine_efficiency"),
                    **common_turbine,
                ),
            )
            shafts = (
                ShaftDefinition(
                    "oxidizer-shaft",
                    ("oxidizer-main-pump",),
                    ("oxidizer-turbine",),
                    0.5 * accessory,
                ),
                ShaftDefinition(
                    "fuel-shaft",
                    ("fuel-main-pump",),
                    ("fuel-turbine",),
                    0.5 * accessory,
                ),
            )
        return CycleDefinition(
            cycle_type=_CYCLE_LABELS[self._vars["cycle"].get()],
            primary_propellant_mass_flow_kg_per_s=total_flow,
            pumps=pumps,
            turbines=turbines,
            shafts=shafts,
            label=f"{bundle.inputs.oxidizer}/{bundle.inputs.fuel} cycle",
        )

    def _seed_from_bundle(self, bundle: ExportBundle) -> None:
        chamber_bar = bundle.inputs.chamber_pressure_pa / 1.0e5
        self._vars["oxidizer_outlet_bar"].set(f"{1.20 * chamber_bar:.6g}")
        self._vars["fuel_outlet_bar"].set(f"{1.35 * chamber_bar:.6g}")
        self._vars["turbine_inlet_bar"].set(f"{2.0 * chamber_bar:.6g}")
        for side, fluid in (
            ("oxidizer", bundle.inputs.oxidizer),
            ("fuel", bundle.inputs.fuel),
        ):
            temperature = _default_inlet_temperature_k(fluid)
            pressure = self._number(f"{side}_inlet_bar") * 1.0e5
            properties = get_coolant_properties(fluid, temperature, pressure)
            self._vars[f"{side}_temperature_k"].set(f"{temperature:.6g}")
            self._vars[f"{side}_density"].set(
                f"{properties.density_kg_per_m3:.6g}"
            )

    def _apply_rpa_seed(
        self,
        seed: RpaCycleSeed,
        bundle: ExportBundle | None,
    ) -> None:
        self._vars["cycle"].set(_CYCLE_LABEL_BY_TYPE[seed.cycle_type])
        self._vars["shafts"].set(
            _SHAFT_LABELS[1] if len(seed.turbines) >= 2 else _SHAFT_LABELS[0]
        )
        for side, pump in (
            ("oxidizer", seed.oxidizer_pump),
            ("fuel", seed.fuel_pump),
        ):
            if pump.inlet_pressure_pa is not None:
                self._vars[f"{side}_inlet_bar"].set(
                    f"{pump.inlet_pressure_pa / 1.0e5:.8g}"
                )
            if pump.efficiency is not None:
                self._vars[f"{side}_efficiency"].set(f"{pump.efficiency:.8g}")
            if bundle is not None:
                target = (
                    bundle.inputs.chamber_pressure_pa
                    + pump.known_main_path_pressure_drop_pa
                )
                self._vars[f"{side}_outlet_bar"].set(f"{target / 1.0e5:.8g}")
        if seed.combustion_devices:
            device = seed.combustion_devices[0]
            if device.maximum_temperature_k is not None:
                self._vars["turbine_temperature_k"].set(
                    f"{device.maximum_temperature_k:.8g}"
                )
            if device.pressure_pa is not None and device.pressure_pa > 0.0:
                self._vars["turbine_inlet_bar"].set(
                    f"{device.pressure_pa / 1.0e5:.8g}"
                )
        for index, turbine in enumerate(seed.turbines[:2]):
            side = "oxidizer" if index == 0 else "fuel"
            self._vars[f"{side}_turbine_pr"].set(f"{turbine.pressure_ratio:.8g}")
            self._vars[f"{side}_turbine_efficiency"].set(
                f"{turbine.efficiency:.8g}"
            )

    def _refresh_kpis(self) -> None:
        result = self._result
        self._kpis["pump_power"].set(
            f"{result.total_pump_power_required_w / 1.0e6:.3f} MW"
        )
        self._kpis["turbine_flow"].set(
            f"{result.turbine_working_mass_flow_kg_per_s:.3f} kg/s"
        )
        self._kpis["flow_fraction"].set(
            f"{100.0 * result.turbine_working_mass_flow_fraction:.2f}%"
        )
        self._kpis["turbine_outlet"].set(
            f"{min(row.outlet_temperature_k for row in result.turbines):.1f} K"
        )
        self._kpis["engine_flow"].set(
            f"{result.estimated_total_engine_inlet_mass_flow_kg_per_s:.3f} kg/s"
        )
        max_closure = max(row.closure_relative for row in result.shafts)
        self._kpis["balance"].set(
            "closed" if result.all_shafts_balanced else f"{100.0 * max_closure:.3f}%"
        )

    def _refresh_table(self) -> None:
        self._tree.delete(*self._tree.get_children())
        shaft_by_pump = {
            pump_id: shaft.shaft_id
            for shaft in self._result.definition.shafts
            for pump_id in shaft.pump_ids
        }
        shaft_by_turbine = {
            turbine_id: shaft.shaft_id
            for shaft in self._result.definition.shafts
            for turbine_id in shaft.turbine_ids
        }
        for row in self._result.pumps:
            definition = row.definition
            outlet_temperature = (
                definition.inlet_temperature_k + row.estimated_temperature_rise_k
                if definition.inlet_temperature_k is not None
                and row.estimated_temperature_rise_k is not None
                else None
            )
            self._tree.insert(
                "",
                "end",
                values=(
                    "Pump",
                    definition.pump_id,
                    shaft_by_pump[definition.pump_id],
                    f"{definition.mass_flow_kg_per_s:.4f}",
                    f"{definition.inlet_pressure_pa / 1.0e5:.3f}",
                    f"{definition.discharge_pressure_pa / 1.0e5:.3f}",
                    f"{definition.efficiency:.4f}",
                    f"{-row.shaft_power_required_w / 1.0e6:.5f}",
                    "--" if outlet_temperature is None else f"{outlet_temperature:.2f}",
                ),
            )
        for row in self._result.turbines:
            definition = row.definition
            self._tree.insert(
                "",
                "end",
                values=(
                    "Turbine",
                    definition.turbine_id,
                    shaft_by_turbine[definition.turbine_id],
                    f"{row.mass_flow_kg_per_s:.4f}",
                    f"{definition.inlet_pressure_pa / 1.0e5:.3f}",
                    f"{row.outlet_pressure_pa / 1.0e5:.3f}",
                    f"{definition.isentropic_efficiency:.4f}",
                    f"{row.shaft_power_delivered_w / 1.0e6:.5f}",
                    f"{row.outlet_temperature_k:.2f}",
                ),
            )

    def _refresh_chart(self) -> None:
        self._power_axis.clear()
        self._flow_axis.clear()
        component_names = [row.definition.pump_id for row in self._result.pumps]
        component_power = [
            -row.shaft_power_required_w / 1.0e6 for row in self._result.pumps
        ]
        colors = ["#c34a36"] * len(component_names)
        component_names.extend(row.definition.turbine_id for row in self._result.turbines)
        component_power.extend(
            row.shaft_power_delivered_w / 1.0e6 for row in self._result.turbines
        )
        colors.extend(["#0f7b6c"] * len(self._result.turbines))
        self._power_axis.barh(component_names, component_power, color=colors)
        self._power_axis.axvline(0.0, color="#526579", linewidth=0.9)
        self._power_axis.set_xlabel("Shaft power [MW]")
        self._power_axis.set_title("Component power (+ turbine / - pump)")

        flow_names = [row.definition.turbine_id for row in self._result.turbines]
        flow_values = [row.mass_flow_kg_per_s for row in self._result.turbines]
        self._flow_axis.bar(flow_names, flow_values, color="#145da0")
        self._flow_axis.set_ylabel("Required turbine flow [kg/s]")
        self._flow_axis.set_title("Solved working-fluid allocation")
        self._flow_axis.tick_params(axis="x", rotation=15)
        for axis in (self._power_axis, self._flow_axis):
            axis.grid(True, axis="x" if axis is self._power_axis else "y", color="#dfe6ee")
            axis.spines["top"].set_visible(False)
            axis.spines["right"].set_visible(False)
            axis.tick_params(labelsize=8)
        self._canvas.draw_idle()

    def _draw_empty_chart(self) -> None:
        for axis in (self._power_axis, self._flow_axis):
            axis.clear()
            axis.grid(True, color="#dfe6ee")
            axis.text(
                0.5,
                0.5,
                "No committed design",
                transform=axis.transAxes,
                ha="center",
                va="center",
                color="#718096",
            )
        self._canvas.draw_idle()

    def _export_csv(self) -> None:
        if self._result is None:
            self._status.set("Calculate Engine Cycle before exporting.")
            return
        selected = filedialog.asksaveasfilename(
            title="Export Engine Cycle",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="engine_cycle_components.csv",
        )
        if not selected:
            return
        path = Path(selected)
        path.parent.mkdir(parents=True, exist_ok=True)
        shaft_by_pump = {
            component_id: shaft.shaft_id
            for shaft in self._result.definition.shafts
            for component_id in shaft.pump_ids
        }
        shaft_by_turbine = {
            component_id: shaft.shaft_id
            for shaft in self._result.definition.shafts
            for component_id in shaft.turbine_ids
        }
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "component_type",
                    "component_id",
                    "shaft_id",
                    "mass_flow_kg_per_s",
                    "inlet_pressure_pa",
                    "outlet_pressure_pa",
                    "efficiency",
                    "shaft_power_w",
                    "outlet_temperature_k",
                ]
            )
            for row in self._result.pumps:
                definition = row.definition
                outlet_temperature = (
                    definition.inlet_temperature_k + row.estimated_temperature_rise_k
                    if definition.inlet_temperature_k is not None
                    and row.estimated_temperature_rise_k is not None
                    else None
                )
                writer.writerow(
                    [
                        "pump",
                        definition.pump_id,
                        shaft_by_pump[definition.pump_id],
                        definition.mass_flow_kg_per_s,
                        definition.inlet_pressure_pa,
                        definition.discharge_pressure_pa,
                        definition.efficiency,
                        -row.shaft_power_required_w,
                        outlet_temperature,
                    ]
                )
            for row in self._result.turbines:
                definition = row.definition
                writer.writerow(
                    [
                        "turbine",
                        definition.turbine_id,
                        shaft_by_turbine[definition.turbine_id],
                        row.mass_flow_kg_per_s,
                        definition.inlet_pressure_pa,
                        row.outlet_pressure_pa,
                        definition.isentropic_efficiency,
                        row.shaft_power_delivered_w,
                        row.outlet_temperature_k,
                    ]
                )
        self._status.set(f"Engine-cycle component output exported to {path}.")

    def _number(self, key: str) -> float:
        raw = str(self._vars[key].get()).strip().replace(",", ".")
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(value):
            raise ValueError(f"{key} must be finite.")
        return value


def _default_inlet_temperature_k(fluid_id: str) -> float:
    normalized = "".join(character for character in fluid_id.upper() if character.isalnum())
    if normalized in {"LOX", "O2", "O2L"}:
        return 90.0
    if normalized in {"LH2", "H2", "H2L"}:
        return 20.0
    if normalized in {"CH4", "LCH4", "METHANE"}:
        return 111.0
    if normalized in {"N2O4", "NTO"}:
        return 293.15
    return 293.15

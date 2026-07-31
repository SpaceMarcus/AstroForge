"""Delivered-performance dashboard with altitude and throttle maps."""

from __future__ import annotations

import csv
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from engine.delivered_performance import (
    DeliveredPerformanceAssumptions,
    PerformanceMapPoint,
    build_performance_map,
    evaluate_delivered_performance,
)
from engine.models import ExportBundle


class DeliveredPerformancePage(ttk.Frame):
    """RPA-style delivered-performance view for a committed design."""

    _ALTITUDES_M = (0.0, 5_000.0, 10_000.0, 15_000.0, 20_000.0, 30_000.0, 40_000.0, 50_000.0)
    _THROTTLES = (0.40, 0.60, 0.80, 1.00)

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._bundle: ExportBundle | None = None
        self._map_points: list[PerformanceMapPoint] = []
        self._combustion_efficiency = tk.StringVar(value="0.9800")
        self._friction_efficiency = tk.StringVar(value="0.9900")
        self._status = tk.StringVar(
            value="Commit and recalculate Current Design to populate the map."
        )
        self._kpi_vars = {
            "isp": tk.StringVar(value="--"),
            "thrust": tk.StringVar(value="--"),
            "eta_total": tk.StringVar(value="--"),
            "separation": tk.StringVar(value="--"),
        }
        self._build_header()
        self._build_kpis()
        self._build_analysis_area()

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(16, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(
            header,
            text="Delivered Performance",
            font=("Segoe UI", 18, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=(
                "RPA-style correction factors, explicit pressure thrust, "
                "altitude performance and throttle screening."
            ),
            foreground="#526579",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        controls = ttk.Frame(header)
        controls.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Label(controls, text="ηc* [-]").grid(row=0, column=0, padx=(0, 6))
        ttk.Entry(
            controls,
            textvariable=self._combustion_efficiency,
            width=9,
        ).grid(row=0, column=1, padx=(0, 12))
        ttk.Label(controls, text="ζf [-]").grid(row=0, column=2, padx=(0, 6))
        ttk.Entry(
            controls,
            textvariable=self._friction_efficiency,
            width=9,
        ).grid(row=0, column=3, padx=(0, 12))
        ttk.Button(
            controls,
            text="Recalculate Map",
            command=self.recalculate,
        ).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(
            controls,
            text="Export CSV",
            command=self._export_csv,
        ).grid(row=0, column=5)

        ttk.Label(
            header,
            textvariable=self._status,
            wraplength=1100,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _build_kpis(self) -> None:
        cards = ttk.Frame(self, padding=(16, 0, 16, 10))
        cards.grid(row=1, column=0, sticky="ew")
        for index in range(4):
            cards.columnconfigure(index, weight=1)

        definitions = (
            ("Delivered Isp · sea level", "isp", "#145da0"),
            ("Delivered thrust · sea level", "thrust", "#0f7b6c"),
            ("Total Isp efficiency", "eta_total", "#7b4ba1"),
            ("Separation screen", "separation", "#b26016"),
        )
        for column, (title, key, accent) in enumerate(definitions):
            card = tk.Frame(
                cards,
                background="#f7f9fc",
                highlightbackground="#d8e0ea",
                highlightthickness=1,
                padx=14,
                pady=10,
            )
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 6, 0 if column == 3 else 6),
            )
            tk.Frame(card, background=accent, height=4).pack(fill="x", pady=(0, 8))
            tk.Label(
                card,
                text=title,
                background="#f7f9fc",
                foreground="#526579",
                font=("Segoe UI", 9),
            ).pack(anchor="w")
            tk.Label(
                card,
                textvariable=self._kpi_vars[key],
                background="#f7f9fc",
                foreground="#16283d",
                font=("Segoe UI", 16, "bold"),
            ).pack(anchor="w", pady=(3, 0))

    def _build_analysis_area(self) -> None:
        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 14))

        chart_frame = ttk.LabelFrame(
            pane,
            text="Altitude Envelope",
            padding=8,
        )
        table_frame = ttk.LabelFrame(
            pane,
            text="Operating Map",
            padding=8,
        )
        pane.add(chart_frame, weight=3)
        pane.add(table_frame, weight=2)

        self._figure = Figure(figsize=(8.2, 5.8), dpi=100, facecolor="#ffffff")
        self._isp_axis = self._figure.add_subplot(211)
        self._thrust_axis = self._figure.add_subplot(212, sharex=self._isp_axis)
        self._figure.subplots_adjust(left=0.10, right=0.97, top=0.95, bottom=0.10, hspace=0.28)
        self._canvas = FigureCanvasTkAgg(self._figure, master=chart_frame)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._draw_empty_plot()

        columns = (
            "altitude",
            "pressure",
            "throttle",
            "pc",
            "thrust",
            "isp",
            "separation",
        )
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=22)
        headings = (
            ("altitude", "Altitude [km]", 78),
            ("pressure", "pa [bar]", 70),
            ("throttle", "Throttle [%]", 78),
            ("pc", "pc [bar]", 68),
            ("thrust", "Fdel [kN]", 78),
            ("isp", "Isp,del [s]", 82),
            ("separation", "Separation", 80),
        )
        for key, label, width in headings:
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=65, anchor="center")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        tree.tag_configure("risk", foreground="#a33a2a")
        self._tree = tree

    def update_bundle(
        self,
        bundle: ExportBundle,
        *,
        combustion_efficiency: float | None = None,
    ) -> None:
        """Load a committed design and regenerate the performance map."""

        self._bundle = bundle
        if combustion_efficiency is not None:
            self._combustion_efficiency.set(f"{combustion_efficiency:.4f}")
        self.recalculate()

    def clear(self) -> None:
        self._bundle = None
        self._map_points = []
        for variable in self._kpi_vars.values():
            variable.set("--")
        self._tree.delete(*self._tree.get_children())
        self._status.set(
            "Commit and recalculate Current Design to populate the map."
        )
        self._draw_empty_plot()

    def recalculate(self) -> None:
        """Rebuild cards, plots and the table from the active assumptions."""

        if self._bundle is None:
            self.clear()
            return
        try:
            combustion_efficiency = float(
                self._combustion_efficiency.get().strip().replace(",", ".")
            )
            friction_efficiency = float(
                self._friction_efficiency.get().strip().replace(",", ".")
            )
            assumptions = DeliveredPerformanceAssumptions(
                combustion_efficiency=combustion_efficiency,
                friction_efficiency=friction_efficiency,
            )
            self._map_points = build_performance_map(
                self._bundle,
                altitudes_m=self._ALTITUDES_M,
                throttle_fractions=self._THROTTLES,
                assumptions=assumptions,
            )
            sea_level = evaluate_delivered_performance(
                self._bundle,
                ambient_pressure_pa=101_325.0,
                assumptions=assumptions,
            )
        except ValueError as exc:
            self._status.set(f"Performance-map input error: {exc}")
            return

        self._kpi_vars["isp"].set(f"{sea_level.delivered_isp_ambient_s:.1f} s")
        self._kpi_vars["thrust"].set(f"{sea_level.delivered_thrust_n / 1000.0:.1f} kN")
        self._kpi_vars["eta_total"].set(
            f"{100.0 * sea_level.losses.total_isp_efficiency:.2f} %"
        )
        risks = sum(point.result.separation_risk for point in self._map_points)
        self._kpi_vars["separation"].set(
            f"{risks} / {len(self._map_points)} points"
        )
        self._status.set(
            f"{sea_level.losses.combustion_source}. "
            f"{sea_level.losses.friction_source}. "
            f"{sea_level.losses.divergence_source}. "
            "Throttle maps scale chamber pressure and retain the committed "
            "thermochemical state for fast preliminary screening."
        )
        self._refresh_table()
        self._refresh_plot()

    def _refresh_table(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for point in sorted(
            self._map_points,
            key=lambda item: (item.throttle_fraction, item.altitude_m),
            reverse=True,
        ):
            result = point.result
            self._tree.insert(
                "",
                "end",
                values=(
                    f"{point.altitude_m / 1000.0:.1f}",
                    f"{point.ambient_pressure_pa / 1.0e5:.4f}",
                    f"{100.0 * point.throttle_fraction:.0f}",
                    f"{result.chamber_pressure_pa / 1.0e5:.2f}",
                    f"{result.delivered_thrust_n / 1000.0:.2f}",
                    f"{result.delivered_isp_ambient_s:.2f}",
                    "risk" if result.separation_risk else "clear",
                ),
                tags=("risk",) if result.separation_risk else (),
            )

    def _refresh_plot(self) -> None:
        self._isp_axis.clear()
        self._thrust_axis.clear()
        colors = ("#7b4ba1", "#d97706", "#0f7b6c", "#145da0")
        for color, throttle in zip(colors, self._THROTTLES):
            points = [
                point
                for point in self._map_points
                if point.throttle_fraction == throttle
            ]
            altitudes_km = [point.altitude_m / 1000.0 for point in points]
            isp_s = [point.result.delivered_isp_ambient_s for point in points]
            thrust_kn = [point.result.delivered_thrust_n / 1000.0 for point in points]
            label = f"{100.0 * throttle:.0f}% throttle"
            self._isp_axis.plot(
                altitudes_km,
                isp_s,
                color=color,
                linewidth=2.0,
                marker="o",
                markersize=4,
                label=label,
            )
            self._thrust_axis.plot(
                altitudes_km,
                thrust_kn,
                color=color,
                linewidth=2.0,
                marker="o",
                markersize=4,
                label=label,
            )

        self._style_axis(self._isp_axis, "Delivered specific impulse [s]")
        self._style_axis(self._thrust_axis, "Delivered thrust [kN]")
        self._thrust_axis.set_xlabel("Geometric altitude [km]")
        self._isp_axis.legend(
            loc="lower right",
            frameon=False,
            ncol=2,
            fontsize=8,
        )
        self._canvas.draw_idle()

    def _draw_empty_plot(self) -> None:
        self._isp_axis.clear()
        self._thrust_axis.clear()
        self._style_axis(self._isp_axis, "Delivered specific impulse [s]")
        self._style_axis(self._thrust_axis, "Delivered thrust [kN]")
        self._thrust_axis.set_xlabel("Geometric altitude [km]")
        self._isp_axis.text(
            0.5,
            0.5,
            "No committed design",
            transform=self._isp_axis.transAxes,
            ha="center",
            va="center",
            color="#718096",
        )
        self._canvas.draw_idle()

    @staticmethod
    def _style_axis(axis, ylabel: str) -> None:
        axis.set_ylabel(ylabel)
        axis.grid(True, color="#dfe6ee", linewidth=0.8)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.tick_params(colors="#45576a", labelsize=8)

    def _export_csv(self) -> None:
        if not self._map_points:
            self._status.set("Calculate a performance map before exporting it.")
            return
        selected = filedialog.asksaveasfilename(
            title="Export Delivered Performance Map",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="delivered_performance_map.csv",
        )
        if not selected:
            return
        path = Path(selected)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "altitude_m",
                    "ambient_pressure_pa",
                    "throttle_fraction",
                    "chamber_pressure_pa",
                    "mass_flow_kg_per_s",
                    "ideal_thrust_n",
                    "delivered_thrust_n",
                    "ideal_isp_ambient_s",
                    "delivered_isp_ambient_s",
                    "combustion_efficiency",
                    "friction_efficiency",
                    "divergence_efficiency",
                    "multiphase_efficiency",
                    "nozzle_efficiency",
                    "separation_risk",
                ]
            )
            for point in self._map_points:
                result = point.result
                writer.writerow(
                    [
                        point.altitude_m,
                        point.ambient_pressure_pa,
                        point.throttle_fraction,
                        result.chamber_pressure_pa,
                        result.mass_flow_kg_per_s,
                        result.ideal_thrust_n,
                        result.delivered_thrust_n,
                        result.ideal_isp_ambient_s,
                        result.delivered_isp_ambient_s,
                        result.losses.combustion_efficiency,
                        result.losses.friction_efficiency,
                        result.losses.divergence_efficiency,
                        result.losses.multiphase_efficiency,
                        result.losses.nozzle_efficiency,
                        result.separation_risk,
                    ]
                )
        self._status.set(f"Exported delivered-performance map to {path}.")

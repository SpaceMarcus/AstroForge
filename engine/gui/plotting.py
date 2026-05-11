"""Matplotlib integration for contour, species and O/F sweep plots."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from engine.chamber_geometry import NASA_LSTAR_SOURCE, list_lstar_propellants, LSTAR_DATA
from engine.models import (
    ContourMarker,
    NozzlePoint,
    OFSweepMetric,
    OFSweepPoint,
    OFSweepResult,
    ThermochemistryProfilePoint,
)
from engine.unit_system import UnitPreset, convert_to_display, format_axis_label, get_unit_symbol

try:  # pragma: no cover - depends on local matplotlib installation
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except Exception:  # pragma: no cover - depends on local matplotlib installation
    FigureCanvasTkAgg = None
    Figure = None


class ContourPlotFrame(ttk.LabelFrame):
    """Display the axisymmetric contour as r(x)."""

    def __init__(
        self,
        master: tk.Misc,
        on_point_selected: Callable[[ThermochemistryProfilePoint], None] | None = None,
        *,
        unit_preset: UnitPreset = UnitPreset.SI_CAD,
    ) -> None:
        super().__init__(master, text="Geometry Contour", padding=12)
        self._on_point_selected = on_point_selected
        self._unit_preset = unit_preset
        self._contour: list[NozzlePoint] = []
        self._profile: list[ThermochemistryProfilePoint] = []
        self._markers: list[ContourMarker] = []
        self._wall_thickness_m: float | None = None
        self._selected_index: int | None = None

        if Figure is None or FigureCanvasTkAgg is None:
            ttk.Label(
                self,
                text=(
                    "matplotlib is not installed. "
                    "Please install the project requirements to display plots."
                ),
                wraplength=420,
                justify="left",
            ).pack(fill="both", expand=True)
            self._canvas = None
            self._axis = None
            return

        self._figure = Figure(figsize=(6, 4), dpi=100)
        self._axis = self._figure.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._figure, master=self)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._canvas.mpl_connect("button_press_event", self._handle_click)
        self._configure_axis()

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update axis units and redraw the contour."""

        self._unit_preset = unit_preset
        self._redraw()

    def update_contour(
        self,
        contour: list[NozzlePoint],
        profile: list[ThermochemistryProfilePoint],
        markers: list[ContourMarker] | None = None,
        wall_thickness_m: float | None = None,
    ) -> None:
        """Render the contour if matplotlib is available."""

        self._contour = contour
        self._profile = profile
        self._markers = markers or []
        self._wall_thickness_m = wall_thickness_m
        self._selected_index = None
        self._redraw()

    def _configure_axis(self) -> None:
        if self._axis is None:
            return
        self._axis.set_xlabel(format_axis_label("x", "length", self._unit_preset))
        self._axis.set_ylabel(format_axis_label("r", "length", self._unit_preset))
        self._axis.grid(True, linestyle="--", linewidth=0.6, alpha=0.6)

    def _redraw(self) -> None:
        if self._canvas is None or self._axis is None:
            return
        self._axis.clear()
        self._configure_axis()

        if self._contour:
            x_display = [convert_to_display(point.x_m, "length", self._unit_preset) for point in self._contour]
            r_display = [convert_to_display(point.radius_m, "length", self._unit_preset) for point in self._contour]
            self._axis.plot(x_display, r_display, color="#c25b2a", linewidth=2.2)
            self._axis.fill_between(x_display, r_display, color="#f2d2c2", alpha=0.7)
            if self._wall_thickness_m is not None and self._wall_thickness_m > 0.0:
                wall_display = [
                    convert_to_display(point.radius_m + self._wall_thickness_m, "length", self._unit_preset)
                    for point in self._contour
                ]
                self._axis.plot(
                    x_display,
                    wall_display,
                    color="#6e8598",
                    linewidth=1.8,
                    linestyle="--",
                )
            self._axis.axvline(0.0, color="#555555", linestyle="--", linewidth=1.0)
            if self._selected_index is not None:
                selected = self._contour[self._selected_index]
                self._axis.scatter(
                    [convert_to_display(selected.x_m, "length", self._unit_preset)],
                    [convert_to_display(selected.radius_m, "length", self._unit_preset)],
                    color="#1f4f7a",
                    s=48,
                    zorder=5,
                )
            for marker in self._markers:
                x_value = convert_to_display(marker.x_m, "length", self._unit_preset)
                r_value = convert_to_display(marker.radius_m, "length", self._unit_preset)
                self._axis.scatter(
                    [x_value],
                    [r_value],
                    color=marker.color,
                    s=52,
                    marker="o",
                    edgecolors="#ffffff",
                    linewidths=0.7,
                    zorder=6,
                )
                self._axis.annotate(
                    marker.label,
                    (x_value, r_value),
                    textcoords="offset points",
                    xytext=(6, 6),
                    fontsize=8,
                    color=marker.color,
                )

        self._figure.tight_layout()
        self._canvas.draw_idle()

    def _handle_click(self, event: object) -> None:
        if self._canvas is None or self._axis is None:
            return
        if getattr(event, "inaxes", None) is not self._axis:
            return
        if not self._contour or getattr(event, "xdata", None) is None or getattr(event, "ydata", None) is None:
            return

        x_clicked = float(event.xdata)
        y_clicked = float(event.ydata)
        distances = [
            (
                (convert_to_display(point.x_m, "length", self._unit_preset) - x_clicked) ** 2
                + (convert_to_display(point.radius_m, "length", self._unit_preset) - y_clicked) ** 2
            )
            for point in self._contour
        ]
        self._selected_index = min(range(len(distances)), key=distances.__getitem__)
        self._redraw()

        if self._on_point_selected is not None and self._selected_index < len(self._profile):
            self._on_point_selected(self._profile[self._selected_index])


class SpeciesProfilePlotFrame(ttk.LabelFrame):
    """Display interpolated mass fractions along the nozzle axis."""

    def __init__(self, master: tk.Misc, *, unit_preset: UnitPreset = UnitPreset.SI_CAD) -> None:
        super().__init__(master, text="Species Mass Fractions", padding=12)
        self._unit_preset = unit_preset
        self._profile: list[ThermochemistryProfilePoint] = []

        if Figure is None or FigureCanvasTkAgg is None:
            ttk.Label(
                self,
                text=(
                    "matplotlib is not installed. "
                    "Please install the project requirements to display plots."
                ),
                wraplength=420,
                justify="left",
            ).pack(fill="both", expand=True)
            self._canvas = None
            self._axis = None
            return

        self._figure = Figure(figsize=(7, 5), dpi=100)
        self._axis = self._figure.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._figure, master=self)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update axis units and redraw the last profile."""

        self._unit_preset = unit_preset
        self.update_profile(self._profile)

    def update_profile(self, profile: list[ThermochemistryProfilePoint]) -> None:
        self._profile = profile
        if self._canvas is None or self._axis is None:
            return
        self._axis.clear()
        self._axis.set_xlabel(format_axis_label("x", "length", self._unit_preset))
        self._axis.set_ylabel("Mass fraction [-]")
        self._axis.grid(True, linestyle="--", linewidth=0.6, alpha=0.6)

        if profile:
            x_values = [convert_to_display(point.x_m, "length", self._unit_preset) for point in profile]
            dominant_species = _select_dominant_species(profile, limit=8)
            for species in dominant_species:
                y_values = [
                    point.state.species_mass_fractions.get(species, 0.0)
                    for point in profile
                ]
                self._axis.plot(x_values, y_values, linewidth=1.8, label=species)
            self._axis.axvline(0.0, color="#555555", linestyle="--", linewidth=1.0)
            if dominant_species:
                self._axis.legend(loc="upper right", fontsize=8)
        else:
            self._axis.text(
                0.5,
                0.5,
                "No thermochemistry profile data available.",
                transform=self._axis.transAxes,
                ha="center",
                va="center",
            )

        self._figure.tight_layout()
        self._canvas.draw_idle()


class OFSweepPlotFrame(ttk.LabelFrame):
    """Display O/F ratio sweeps with clickable MR selection."""

    def __init__(
        self,
        master: tk.Misc,
        on_point_selected: Callable[[OFSweepPoint], None] | None = None,
        *,
        unit_preset: UnitPreset = UnitPreset.SI_CAD,
    ) -> None:
        super().__init__(master, text="Mixture Ratio", padding=12)
        self._on_point_selected = on_point_selected
        self._unit_preset = unit_preset
        self._selected_index: int | None = None
        self._sweep_result: OFSweepResult | None = None
        self._metric = OFSweepMetric.ISP_VAC
        self._current_mixture_ratio: float | None = None

        if Figure is None or FigureCanvasTkAgg is None:
            ttk.Label(
                self,
                text=(
                    "matplotlib is not installed. "
                    "Please install the project requirements to display plots."
                ),
                wraplength=420,
                justify="left",
            ).pack(fill="both", expand=True)
            self._canvas = None
            self._axis = None
            return

        self._figure = Figure(figsize=(4.15, 2.75), dpi=100)
        self._axis = self._figure.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._figure, master=self)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._canvas.mpl_connect("button_press_event", self._handle_click)

    def set_unit_preset(self, unit_preset: UnitPreset) -> None:
        """Update y-axis units and redraw the sweep."""

        self._unit_preset = unit_preset
        self._redraw()

    def update_sweep(
        self,
        sweep_result: OFSweepResult | None,
        *,
        metric: OFSweepMetric,
        current_mixture_ratio: float | None,
    ) -> None:
        self._sweep_result = sweep_result
        self._metric = metric
        self._current_mixture_ratio = current_mixture_ratio
        if sweep_result is None or not sweep_result.points:
            self._selected_index = None
        elif current_mixture_ratio is not None:
            self._selected_index = min(
                range(len(sweep_result.points)),
                key=lambda index: abs(sweep_result.points[index].mixture_ratio - current_mixture_ratio),
            )
        else:
            self._selected_index = None
        self._redraw()

    def _metric_value(self, point: OFSweepPoint) -> float:
        if self._metric is OFSweepMetric.ISP_VAC:
            return point.isp_vac_s
        converted = convert_to_display(point.c_star_m_s, "velocity", self._unit_preset)
        return converted if converted is not None else point.c_star_m_s

    def _metric_label(self) -> str:
        if self._metric is OFSweepMetric.ISP_VAC:
            return "Vacuum Isp [s]"
        return f"c* [{get_unit_symbol('velocity', self._unit_preset)}]"

    def _redraw(self) -> None:
        if self._canvas is None or self._axis is None:
            return

        self._axis.clear()
        self._axis.set_xlabel("Mixture ratio [-]")
        self._axis.grid(True, linestyle="--", linewidth=0.6, alpha=0.6)
        self._axis.margins(x=0.03)

        if self._sweep_result is None or not self._sweep_result.points:
            self._axis.text(
                0.5,
                0.5,
                "No O/F sweep data available.",
                transform=self._axis.transAxes,
                ha="center",
                va="center",
            )
            self._figure.tight_layout()
            self._canvas.draw_idle()
            return

        x_values = [point.mixture_ratio for point in self._sweep_result.points]
        y_values = [self._metric_value(point) for point in self._sweep_result.points]
        self._axis.set_ylabel(self._metric_label())
        y_min = min(y_values)
        y_max = max(y_values)
        y_span = max(y_max - y_min, 1.0)
        y_padding = max(y_span * 0.10, 4.0 if self._metric is OFSweepMetric.ISP_VAC else 12.0)
        self._axis.set_ylim(y_min - y_padding, y_max + y_padding)

        stoich = self._sweep_result.stoichiometric_mixture_ratio
        if stoich is not None:
            self._axis.axvspan(x_values[0], stoich, color="#f4ddc4", alpha=0.35)
            self._axis.axvspan(stoich, x_values[-1], color="#d8e8f6", alpha=0.35)
            self._axis.axvline(
                stoich,
                color="#a65b00",
                linestyle="--",
                linewidth=1.2,
                label="Stoich",
            )
            y_text = y_max + y_padding - 0.08 * (2.0 * y_padding + y_span)
            self._axis.text(
                0.5 * (x_values[0] + stoich),
                y_text,
                "fuel rich",
                ha="center",
                va="top",
                fontsize=8,
                color="#7d4d1b",
            )
            self._axis.text(
                0.5 * (stoich + x_values[-1]),
                y_text,
                "oxidizer rich",
                ha="center",
                va="top",
                fontsize=8,
                color="#1f4f7a",
            )

        self._axis.plot(x_values, y_values, color="#1f4f7a", linewidth=2.0)

        peak_isp_mr = self._sweep_result.peak_isp_vac_mixture_ratio
        self._axis.axvline(
            peak_isp_mr,
            color="#2d7d46",
            linestyle=":",
            linewidth=1.3,
            label="Max Isp",
        )
        if self._metric is OFSweepMetric.ISP_VAC:
            peak_isp_index = min(
                range(len(self._sweep_result.points)),
                key=lambda index: abs(self._sweep_result.points[index].mixture_ratio - peak_isp_mr),
            )
            self._axis.scatter(
                [self._sweep_result.points[peak_isp_index].mixture_ratio],
                [self._sweep_result.points[peak_isp_index].isp_vac_s],
                color="#2d7d46",
                marker="*",
                s=120,
                zorder=5,
            )
        else:
            peak_cstar_mr = self._sweep_result.peak_c_star_mixture_ratio
            peak_cstar_index = min(
                range(len(self._sweep_result.points)),
                key=lambda index: abs(self._sweep_result.points[index].mixture_ratio - peak_cstar_mr),
            )
            self._axis.scatter(
                [self._sweep_result.points[peak_cstar_index].mixture_ratio],
                [self._metric_value(self._sweep_result.points[peak_cstar_index])],
                color="#7b3fb3",
                marker="*",
                s=120,
                zorder=5,
                label="Max c*",
            )

        if self._current_mixture_ratio is not None:
            current_index = min(
                range(len(self._sweep_result.points)),
                key=lambda index: abs(
                    self._sweep_result.points[index].mixture_ratio - self._current_mixture_ratio
                ),
            )
            current_point = self._sweep_result.points[current_index]
            self._axis.scatter(
                [current_point.mixture_ratio],
                [self._metric_value(current_point)],
                color="#b03060",
                s=55,
                zorder=5,
                label="Current MR",
            )

        if self._selected_index is not None:
            selected = self._sweep_result.points[self._selected_index]
            self._axis.scatter(
                [selected.mixture_ratio],
                [self._metric_value(selected)],
                color="#101010",
                s=65,
                zorder=6,
                label="Selected MR",
            )

        self._axis.text(
            0.02,
            0.97,
            f"{self._sweep_result.oxidizer} / {self._sweep_result.fuel}",
            transform=self._axis.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            color="#444444",
        )
        handles, _labels = self._axis.get_legend_handles_labels()
        if handles:
            self._axis.legend(
                loc="lower right",
                fontsize=7,
                framealpha=0.9,
                borderpad=0.35,
                handlelength=1.4,
                labelspacing=0.3,
            )
        self._figure.tight_layout()
        self._canvas.draw_idle()

    def _handle_click(self, event: object) -> None:
        if self._canvas is None or self._axis is None:
            return
        if self._sweep_result is None or not self._sweep_result.points:
            return
        if getattr(event, "inaxes", None) is not self._axis or getattr(event, "xdata", None) is None:
            return

        x_clicked = float(event.xdata)
        self._selected_index = min(
            range(len(self._sweep_result.points)),
            key=lambda index: abs(self._sweep_result.points[index].mixture_ratio - x_clicked),
        )
        self._redraw()

        if self._on_point_selected is not None:
            self._on_point_selected(self._sweep_result.points[self._selected_index])


def _select_dominant_species(
    profile: list[ThermochemistryProfilePoint],
    limit: int,
) -> list[str]:
    maxima: dict[str, float] = {}
    for point in profile:
        for species, fraction in point.state.species_mass_fractions.items():
            maxima[species] = max(maxima.get(species, 0.0), fraction)
    ordered = sorted(maxima.items(), key=lambda item: item[1], reverse=True)
    return [species for species, _ in ordered[:limit]]


class LStarRangePlotFrame(ttk.LabelFrame):
    """Display empirical L* ranges and highlight the currently selected propellant."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Typical L* Ranges", padding=12)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._selected_propellant = list_lstar_propellants()[0]
        self._selected_lstar_m: float | None = None

        if Figure is None or FigureCanvasTkAgg is None:
            ttk.Label(
                self,
                text=(
                    "matplotlib is not installed. "
                    "Please install the project requirements to display plots."
                ),
                wraplength=420,
                justify="left",
            ).grid(row=0, column=0, sticky="nsew")
            self._canvas = None
            self._axis = None
        else:
            self._figure = Figure(figsize=(6.3, 4.9), dpi=100)
            self._axis = self._figure.add_subplot(111)
            self._canvas = FigureCanvasTkAgg(self._figure, master=self)
            self._canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            self,
            text=NASA_LSTAR_SOURCE,
            wraplength=440,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def update_ranges(
        self,
        *,
        selected_propellant: str,
        selected_lstar_m: float | None,
    ) -> None:
        """Redraw the empirical L* chart for the selected propellant and marker."""

        self._selected_propellant = selected_propellant
        self._selected_lstar_m = selected_lstar_m
        self._redraw()

    def _redraw(self) -> None:
        if self._canvas is None or self._axis is None:
            return

        propellants = list_lstar_propellants()
        self._axis.clear()
        self._axis.set_xlabel("L* [m]")
        self._axis.set_ylabel("Propellant combination")
        self._axis.grid(True, axis="x", linestyle="--", linewidth=0.6, alpha=0.6)

        y_positions = list(range(len(propellants)))
        min_limit = min(LSTAR_DATA[propellant]["min_m"] for propellant in propellants)
        max_limit = max(LSTAR_DATA[propellant]["max_m"] for propellant in propellants)

        for index, propellant in enumerate(propellants):
            bounds = LSTAR_DATA[propellant]
            is_selected = propellant == self._selected_propellant
            color = "#d06b2f" if is_selected else "#8fa9c7"
            line_width = 8 if is_selected else 5
            self._axis.hlines(
                index,
                bounds["min_m"],
                bounds["max_m"],
                color=color,
                linewidth=line_width,
                alpha=0.95 if is_selected else 0.7,
            )
            self._axis.plot(bounds["min_m"], index, marker="|", color="#304252", markersize=12)
            self._axis.plot(bounds["max_m"], index, marker="|", color="#304252", markersize=12)

            if is_selected and self._selected_lstar_m is not None:
                self._axis.scatter(
                    [self._selected_lstar_m],
                    [index],
                    color="#1f4f7a",
                    s=52,
                    zorder=5,
                )
                label_x = max(bounds["max_m"], self._selected_lstar_m) + 0.03
                self._axis.text(
                    label_x,
                    index,
                    f"selected: {self._selected_lstar_m:.2f} m",
                    va="center",
                    ha="left",
                    fontsize=8,
                    color="#1f4f7a",
                )

        self._axis.set_yticks(y_positions)
        self._axis.set_yticklabels(propellants, fontsize=8)
        self._axis.invert_yaxis()
        self._axis.set_xlim(min_limit - 0.08, max_limit + 0.42)
        self._figure.tight_layout()
        self._canvas.draw_idle()

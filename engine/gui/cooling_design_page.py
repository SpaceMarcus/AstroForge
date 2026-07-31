"""Interactive variable-channel and film-cooling design workspace."""

from __future__ import annotations

import csv
import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from engine.cad import export_step_geometry
from engine.cfd import export_cfd_meshes
from engine.cooling import (
    AxialKeyframe,
    AxialProfile,
    ChannelLayout,
    ChannelShape,
    CoolantCircuit,
    CoupledThermalSettings,
    FilmCoolingInputs,
    FilmCoolingSlot,
    InterpolationMode,
    march_film_cooling,
    run_coupled_regenerative_analysis,
)
from engine.models import ExportBundle
from engine.properties import get_coolant_properties
from engine.station_mesh import EngineStationMesh, build_engine_station_mesh


_SHAPE_LABELS = {
    "Rectangular": ChannelShape.RECTANGULAR,
    "Trapezoidal": ChannelShape.TRAPEZOIDAL,
    "Rounded rectangular": ChannelShape.ROUNDED_RECTANGULAR,
    "Semicircular": ChannelShape.SEMICIRCULAR,
    "Circular / tubular": ChannelShape.CIRCULAR,
    "Racetrack": ChannelShape.RACETRACK,
    "Custom polygon": ChannelShape.CUSTOM_POLYGON,
}


class CoolingDesignPage(ttk.Frame):
    """Variable regenerative-channel design and hydraulic result view."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._bundle: ExportBundle | None = None
        self._station_mesh: EngineStationMesh | None = None
        self._coupled_result = None
        self._channel_result = None
        self._film_result = None
        self._status = tk.StringVar(
            value="Commit and recalculate Current Design to activate Cooling Design."
        )
        self._kpi_vars = {
            "dp": tk.StringVar(value="--"),
            "tout": tk.StringVar(value="--"),
            "hmax": tk.StringVar(value="--"),
            "velocity": tk.StringVar(value="--"),
            "ligament": tk.StringVar(value="--"),
            "film": tk.StringVar(value="--"),
            "twg": tk.StringVar(value="--"),
        }
        self._vars = self._default_variables()
        self._build_header()
        self._build_workspace()

    def _default_variables(self) -> dict[str, tk.Variable]:
        return {
            "coolant": tk.StringVar(value="RP-1"),
            "mass_flow": tk.StringVar(value="2.0"),
            "tin": tk.StringVar(value="293.15"),
            "pin_bar": tk.StringVar(value="120.0"),
            "direction": tk.StringVar(value="exit-to-chamber"),
            "shape": tk.StringVar(value="Rounded rectangular"),
            "heat_flux_mw": tk.StringVar(value="5.0"),
            "wall_material": tk.StringVar(value="CuCrZr"),
            "radiation_enabled": tk.BooleanVar(value=True),
            "wall_emissivity": tk.StringVar(value="0.70"),
            "gas_emissivity": tk.StringVar(value="0.15"),
            "count_0": tk.StringVar(value="120"),
            "count_t": tk.StringVar(value="120"),
            "count_1": tk.StringVar(value="120"),
            "width_0_mm": tk.StringVar(value="1.8"),
            "width_t_mm": tk.StringVar(value="1.2"),
            "width_1_mm": tk.StringVar(value="2.0"),
            "height_0_mm": tk.StringVar(value="2.5"),
            "height_t_mm": tk.StringVar(value="3.0"),
            "height_1_mm": tk.StringVar(value="2.0"),
            "rib_0_mm": tk.StringVar(value="1.0"),
            "rib_t_mm": tk.StringVar(value="0.8"),
            "rib_1_mm": tk.StringVar(value="1.0"),
            "wall_0_mm": tk.StringVar(value="1.2"),
            "wall_t_mm": tk.StringVar(value="0.8"),
            "wall_1_mm": tk.StringVar(value="1.0"),
            "helix_0_deg": tk.StringVar(value="0.0"),
            "helix_t_deg": tk.StringVar(value="25.0"),
            "helix_1_deg": tk.StringVar(value="10.0"),
            "roughness_um": tk.StringVar(value="10.0"),
            "corner_mm": tk.StringVar(value="0.2"),
            "polygon_mm": tk.StringVar(value="0,0; 1.8,0; 1.8,2.5; 0,2.5"),
            "film_enabled": tk.BooleanVar(value=False),
            "film_liquid": tk.BooleanVar(value=False),
            "film_location": tk.StringVar(value="0.15"),
            "film_mass_flow": tk.StringVar(value="0.05"),
            "film_slot_mm": tk.StringVar(value="0.5"),
            "film_angle": tk.StringVar(value="25.0"),
            "film_coverage": tk.StringVar(value="1.0"),
            "film_temperature": tk.StringVar(value="290.0"),
            "surface_flow": tk.StringVar(value="1.0"),
            "surface_thickness_mm": tk.StringVar(value="2.0"),
            "mixing_coefficient": tk.StringVar(value="0.001"),
            "vaporization_temperature": tk.StringVar(value="450.0"),
            "latent_heat_kj": tk.StringVar(value="250.0"),
        }

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(14, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="Cooling Design",
            font=("Segoe UI", 18, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=(
                "Stationwise channel geometry, helicity, hydraulic losses, "
                "coolant heating and gaseous/liquid film cooling."
            ),
            foreground="#526579",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        buttons = ttk.Frame(header)
        buttons.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(buttons, text="Calculate Cooling", command=self.recalculate).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="Export Station CSV", command=self._export_csv).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="Export STEP", command=self._export_step).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="Export CFD Mesh", command=self._export_cfd_mesh).pack(
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
        controls_host = ttk.Frame(pane, width=390)
        results = ttk.Frame(pane)
        results.columnconfigure(0, weight=1)
        results.rowconfigure(1, weight=1)
        pane.add(controls_host, weight=1)
        pane.add(results, weight=3)
        self._build_scrollable_controls(controls_host)
        self._build_kpis(results)
        self._build_results_notebook(results)

    def _build_scrollable_controls(self, master: ttk.Frame) -> None:
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        canvas = tk.Canvas(master, highlightthickness=0, width=390)
        scrollbar = ttk.Scrollbar(master, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=(4, 2, 10, 8))
        content.columnconfigure(1, weight=1)
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

        operating = ttk.LabelFrame(content, text="Coolant and Thermal Coupling", padding=9)
        operating.grid(row=0, column=0, columnspan=2, sticky="ew")
        operating.columnconfigure(1, weight=1)
        self._entry_row(operating, 0, "Coolant", "coolant")
        self._entry_row(operating, 1, "Mass flow [kg/s]", "mass_flow")
        self._entry_row(operating, 2, "Inlet temperature [K]", "tin")
        self._entry_row(operating, 3, "Inlet pressure [bar]", "pin_bar")
        ttk.Label(operating, text="Flow direction").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Combobox(
            operating,
            textvariable=self._vars["direction"],
            values=("exit-to-chamber", "chamber-to-exit"),
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", pady=3)
        self._entry_row(operating, 5, "Initial heat-flux guess [MW/m2]", "heat_flux_mw")
        self._entry_row(operating, 6, "Wall material", "wall_material")
        ttk.Checkbutton(
            operating,
            text="Include hot-gas radiation",
            variable=self._vars["radiation_enabled"],
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 2))
        self._entry_row(operating, 8, "Wall emissivity [0..1]", "wall_emissivity")
        self._entry_row(operating, 9, "Gas effective emissivity [0..1]", "gas_emissivity")

        geometry = ttk.LabelFrame(content, text="Variable Channel Geometry", padding=9)
        geometry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for column in range(4):
            geometry.columnconfigure(column, weight=1 if column else 0)
        ttk.Label(geometry, text="Shape").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(
            geometry,
            textvariable=self._vars["shape"],
            values=tuple(_SHAPE_LABELS),
            state="readonly",
        ).grid(row=0, column=1, columnspan=3, sticky="ew", pady=3)
        ttk.Label(geometry, text="Profile").grid(row=1, column=0, sticky="w", pady=(6, 2))
        for column, label in enumerate(("Injector", "Throat", "Exit"), start=1):
            ttk.Label(geometry, text=label).grid(row=1, column=column, pady=(6, 2))
        profile_rows = (
            ("Channels", "count", ""),
            ("Width / diameter", "width", "mm"),
            ("Height", "height", "mm"),
            ("Rib width", "rib", "mm"),
            ("Hot wall", "wall", "mm"),
            ("Helix angle", "helix", "deg"),
        )
        suffixes = ("0", "t", "1")
        for row, (label, key, unit) in enumerate(profile_rows, start=2):
            ttk.Label(
                geometry,
                text=f"{label}{f' [{unit}]' if unit else ''}",
            ).grid(row=row, column=0, sticky="w", pady=2)
            for column, suffix in enumerate(suffixes, start=1):
                variable_key = (
                    f"{key}_{suffix}"
                    if key == "count"
                    else f"{key}_{suffix}_{unit}"
                )
                ttk.Entry(
                    geometry,
                    textvariable=self._vars[variable_key],
                    width=8,
                ).grid(row=row, column=column, sticky="ew", padx=(4, 0), pady=2)
        self._entry_row(geometry, 8, "Roughness [um]", "roughness_um", columnspan=3)
        self._entry_row(geometry, 9, "Corner radius [mm]", "corner_mm", columnspan=3)
        ttk.Label(geometry, text="Custom polygon [mm]").grid(
            row=10, column=0, sticky="nw", pady=3
        )
        ttk.Entry(
            geometry,
            textvariable=self._vars["polygon_mm"],
        ).grid(row=10, column=1, columnspan=3, sticky="ew", padx=(4, 0), pady=3)

        film = ttk.LabelFrame(content, text="Film Cooling", padding=9)
        film.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        film.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            film,
            text="Enable film slot",
            variable=self._vars["film_enabled"],
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(
            film,
            text="Liquid film (heating + vaporization)",
            variable=self._vars["film_liquid"],
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 6))
        film_rows = (
            ("Axial position [0..1]", "film_location"),
            ("Film mass flow [kg/s]", "film_mass_flow"),
            ("Slot height [mm]", "film_slot_mm"),
            ("Injection angle [deg]", "film_angle"),
            ("Circumference coverage [0..1]", "film_coverage"),
            ("Injection temperature [K]", "film_temperature"),
            ("Surface-layer flow [kg/s]", "surface_flow"),
            ("Surface-layer thickness [mm]", "surface_thickness_mm"),
            ("Mixing coefficient", "mixing_coefficient"),
            ("Vaporization temperature [K]", "vaporization_temperature"),
            ("Latent heat [kJ/kg]", "latent_heat_kj"),
        )
        for row, (label, key) in enumerate(film_rows, start=2):
            self._entry_row(film, row, label, key)

    def _entry_row(
        self,
        frame: ttk.Frame,
        row: int,
        label: str,
        key: str,
        *,
        columnspan: int = 1,
    ) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self._vars[key]).grid(
            row=row,
            column=1,
            columnspan=columnspan,
            sticky="ew",
            padx=(6, 0),
            pady=3,
        )

    def _build_kpis(self, master: ttk.Frame) -> None:
        cards = ttk.Frame(master, padding=(0, 0, 0, 8))
        cards.grid(row=0, column=0, sticky="ew")
        definitions = (
            ("Pressure loss", "dp"),
            ("Coolant outlet", "tout"),
            ("Max coolant h", "hmax"),
            ("Max velocity", "velocity"),
            ("Min ligament margin", "ligament"),
            ("Film at exit", "film"),
            ("Max hot wall", "twg"),
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
                textvariable=self._kpi_vars[key],
                background="#f7f9fc",
                foreground="#16283d",
                font=("Segoe UI", 11, "bold"),
            ).pack(anchor="w", pady=(2, 0))

    def _build_results_notebook(self, master: ttk.Frame) -> None:
        notebook = ttk.Notebook(master)
        notebook.grid(row=1, column=0, sticky="nsew")
        plot_frame = ttk.Frame(notebook)
        table_frame = ttk.Frame(notebook)
        notebook.add(plot_frame, text="Profiles and Results")
        notebook.add(table_frame, text="Station Output")
        self._figure = Figure(figsize=(9.2, 6.2), dpi=100, facecolor="#ffffff")
        self._geometry_axis = self._figure.add_subplot(221)
        self._helix_axis = self._figure.add_subplot(222)
        self._temperature_axis = self._figure.add_subplot(223)
        self._pressure_axis = self._figure.add_subplot(224)
        self._figure.subplots_adjust(
            left=0.09, right=0.97, top=0.94, bottom=0.10, hspace=0.32, wspace=0.28
        )
        self._canvas = FigureCanvasTkAgg(self._figure, master=plot_frame)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._draw_empty_plot()

        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = (
            "station", "x", "s", "count", "width", "height", "helix",
            "v", "re", "h", "q", "tc", "twc", "twg", "p",
        )
        tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = (
            ("station", "Station", 82),
            ("x", "x [m]", 72),
            ("s", "s [m]", 72),
            ("count", "N", 48),
            ("width", "w [mm]", 70),
            ("height", "h [mm]", 70),
            ("helix", "Helix [deg]", 76),
            ("v", "v [m/s]", 72),
            ("re", "Re", 86),
            ("h", "hc [kW/m2K]", 98),
            ("q", "q [MW/m2]", 90),
            ("tc", "Tc [K]", 72),
            ("twc", "Tw,c [K]", 82),
            ("twg", "Tw,g [K]", 82),
            ("p", "pc [bar]", 78),
        )
        for key, label, width in headings:
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=45, anchor="center")
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree.tag_configure("warning", foreground="#a33a2a")
        self._tree = tree

    def update_bundle(self, bundle: ExportBundle) -> None:
        self._bundle = bundle
        self._station_mesh = build_engine_station_mesh(bundle.contour)
        self._vars["wall_material"].set(bundle.inputs.liner_material or "CuCrZr")
        if self._vars["coolant"].get() == "RP-1":
            self._vars["coolant"].set(bundle.inputs.fuel)
        if bundle.geometry.mass_flow_kg_per_s > 0.0:
            fuel_flow = (
                bundle.geometry.mass_flow_kg_per_s
                / (1.0 + bundle.inputs.mixture_ratio)
            )
            self._vars["mass_flow"].set(f"{fuel_flow:.6g}")
        self.recalculate()

    def clear(self) -> None:
        self._bundle = None
        self._station_mesh = None
        self._coupled_result = None
        self._channel_result = None
        self._film_result = None
        for variable in self._kpi_vars.values():
            variable.set("--")
        self._tree.delete(*self._tree.get_children())
        self._status.set(
            "Commit and recalculate Current Design to activate Cooling Design."
        )
        self._draw_empty_plot()

    def recalculate(self) -> None:
        if self._bundle is None or self._station_mesh is None:
            self.clear()
            return
        try:
            layout = self._build_channel_layout()
            circuit = CoolantCircuit(
                circuit_id="main-regen",
                coolant_id=self._text("coolant"),
                mass_flow_kg_per_s=self._number("mass_flow"),
                inlet_temperature_k=self._number("tin"),
                inlet_pressure_pa=self._number("pin_bar") * 1.0e5,
                opposite_hot_gas_flow=(
                    self._vars["direction"].get() == "exit-to-chamber"
                ),
            )
            settings = CoupledThermalSettings(
                wall_material_id=self._text("wall_material"),
                radiation_enabled=bool(self._vars["radiation_enabled"].get()),
                wall_emissivity=self._number("wall_emissivity"),
                gas_effective_emissivity=self._number("gas_emissivity"),
                initial_heat_flux_w_per_m2=self._number("heat_flux_mw") * 1.0e6,
            )
            self._coupled_result = run_coupled_regenerative_analysis(
                self._bundle,
                layout,
                circuit,
                settings=settings,
                station_mesh=self._station_mesh,
            )
            self._channel_result = self._coupled_result.channel_result
            self._film_result = self._calculate_film(
                [row.convective_heat_flux_w_per_m2 for row in self._coupled_result.stations],
                [row.radiation_heat_flux_w_per_m2 for row in self._coupled_result.stations],
            )
        except (TypeError, ValueError) as exc:
            self._status.set(f"Cooling input error: {exc}")
            return

        self._refresh_kpis()
        self._refresh_table()
        self._refresh_plot()
        notes = list(self._channel_result.notes)
        invalid_pitch = any(
            station.transport.ligament_margin_m is not None
            and station.transport.ligament_margin_m < 0.0
            for station in self._channel_result.stations
        )
        status = (
            "Coupled Bartz, radiation, temperature-dependent wall, rib/fin and "
            f"variable-channel solution complete in {self._coupled_result.iterations} iteration(s)."
        )
        if not self._coupled_result.converged:
            status += " Warning: the wall-temperature iteration did not reach tolerance."
        if invalid_pitch:
            status += " Warning: at least one channel/rib definition exceeds local pitch."
        elif notes:
            status += f" {len(notes)} correlation/property note(s) are present."
        self._status.set(status)

    def _build_channel_layout(self) -> ChannelLayout:
        mesh = self._station_mesh
        if mesh is None:
            raise ValueError("No committed station mesh is available.")
        throat = min(mesh.stations, key=lambda station: station.area_m2)
        positions = (0.0, throat.s_m, mesh.contour_length_m)

        def profile(prefix: str, unit_scale: float = 1.0, *, step: bool = False) -> AxialProfile:
            suffix = "" if prefix == "count" else ("_mm" if unit_scale == 1.0e-3 else "_deg")
            keys = tuple(f"{prefix}_{station}{suffix}" for station in ("0", "t", "1"))
            values = tuple(self._number(key) * unit_scale for key in keys)
            return AxialProfile(
                tuple(
                    AxialKeyframe(position, value)
                    for position, value in zip(positions, values)
                ),
                interpolation=InterpolationMode.STEP if step else InterpolationMode.LINEAR,
            )

        shape = _SHAPE_LABELS[self._vars["shape"].get()]
        width = profile("width", 1.0e-3)
        height = profile("height", 1.0e-3)
        common = {
            "shape": shape,
            "channel_count": profile("count", step=True),
            "rib_width_m": profile("rib", 1.0e-3),
            "hot_wall_thickness_m": profile("wall", 1.0e-3),
            "roughness_m": AxialProfile.constant(
                self._number("roughness_um") * 1.0e-6,
                minimum_value=0.0,
            ),
            "helix_angle_deg": profile("helix"),
        }
        if shape is ChannelShape.TRAPEZOIDAL:
            return ChannelLayout(
                **common,
                top_width_m=AxialProfile(
                    tuple(
                        AxialKeyframe(keyframe.s_m, 0.80 * keyframe.value)
                        for keyframe in width.keyframes
                    )
                ),
                bottom_width_m=width,
                height_m=height,
            )
        if shape in {ChannelShape.CIRCULAR, ChannelShape.SEMICIRCULAR}:
            return ChannelLayout(**common, diameter_m=width)
        if shape is ChannelShape.CUSTOM_POLYGON:
            return ChannelLayout(
                **common,
                polygon_points_m=self._parse_polygon(),
            )
        return ChannelLayout(
            **common,
            width_m=width,
            height_m=height,
            corner_radius_m=AxialProfile.constant(
                self._number("corner_mm") * 1.0e-3,
                minimum_value=0.0,
            ),
        )

    def _parse_polygon(self) -> tuple[tuple[float, float], ...]:
        points = []
        for raw_point in self._text("polygon_mm").split(";"):
            coordinates = raw_point.strip().split(",")
            if len(coordinates) != 2:
                raise ValueError("Custom polygon points must use 'x,y; x,y' in millimetres.")
            points.append(
                (
                    float(coordinates[0].strip()) * 1.0e-3,
                    float(coordinates[1].strip()) * 1.0e-3,
                )
            )
        return tuple(points)

    def _calculate_film(
        self,
        convective_heat_flux: list[float],
        radiation_heat_flux: list[float],
    ):
        if not bool(self._vars["film_enabled"].get()):
            return None
        mesh = self._station_mesh
        if mesh is None:
            return None
        location_fraction = self._number("film_location")
        if not 0.0 <= location_fraction <= 1.0:
            raise ValueError("Film axial position must be between 0 and 1.")
        liquid = bool(self._vars["film_liquid"].get())
        temperature = self._number("film_temperature")
        pressure = self._number("pin_bar") * 1.0e5
        properties = get_coolant_properties(self._text("coolant"), temperature, pressure)
        slot = FilmCoolingSlot(
            slot_id="film-1",
            s_m=location_fraction * mesh.contour_length_m,
            circuit_id="film",
            mass_flow_kg_per_s=self._number("film_mass_flow"),
            slot_height_m=self._number("film_slot_mm") * 1.0e-3,
            injection_angle_deg=self._number("film_angle"),
            circumference_fraction=self._number("film_coverage"),
            liquid=liquid,
        )
        inputs = FilmCoolingInputs(
            slot=slot,
            injection_temperature_k=temperature,
            coolant_cp_j_per_kg_k=properties.cp_j_per_kg_k,
            coolant_viscosity_pa_s=properties.viscosity_pa_s,
            surface_layer_mass_flow_kg_per_s=self._number("surface_flow"),
            surface_layer_thickness_m=self._number("surface_thickness_mm") * 1.0e-3,
            turbulent_mixing_coefficient=self._number("mixing_coefficient"),
            vaporization_temperature_k=(
                self._number("vaporization_temperature") if liquid else None
            ),
            latent_heat_j_per_kg=(
                self._number("latent_heat_kj") * 1.0e3 if liquid else None
            ),
        )
        return march_film_cooling(
            mesh,
            inputs,
            convective_heat_flux_w_per_m2=convective_heat_flux,
            radiation_heat_flux_w_per_m2=radiation_heat_flux,
        )

    def _refresh_kpis(self) -> None:
        result = self._channel_result
        self._kpi_vars["dp"].set(f"{result.total_pressure_drop_pa / 1.0e5:.3f} bar")
        self._kpi_vars["tout"].set(f"{result.outlet_temperature_k:.1f} K")
        self._kpi_vars["hmax"].set(
            f"{max(row.transport.heat_transfer_coefficient_w_per_m2_k for row in result.stations) / 1000.0:.1f} kW/m2K"
        )
        self._kpi_vars["velocity"].set(
            f"{max(row.transport.velocity_m_per_s for row in result.stations):.2f} m/s"
        )
        margins = [
            row.transport.ligament_margin_m
            for row in result.stations
            if row.transport.ligament_margin_m is not None
        ]
        self._kpi_vars["ligament"].set(
            "--" if not margins else f"{min(margins) * 1000.0:.3f} mm"
        )
        if self._film_result is None:
            self._kpi_vars["film"].set("disabled")
        else:
            exit_row = self._film_result.stations[-1]
            self._kpi_vars["film"].set(
                f"{100.0 * exit_row.convective_effectiveness:.1f}% shield"
            )
        self._kpi_vars["twg"].set(
            f"{self._coupled_result.maximum_hot_wall_temperature_k:.1f} K"
        )

    def _refresh_table(self) -> None:
        self._tree.delete(*self._tree.get_children())
        thermal_by_station = {
            row.station.station_id: row for row in self._coupled_result.stations
        }
        for row in sorted(
            self._channel_result.stations,
            key=lambda item: item.station.s_m,
        ):
            section = row.transport.section
            cross = section.cross_section
            width = (
                cross.width_m
                or cross.bottom_width_m
                or cross.diameter_m
                or section.hot_wall_width_per_channel_m
            )
            height = cross.height_m or cross.diameter_m or 0.0
            warning = (
                row.transport.ligament_margin_m is not None
                and row.transport.ligament_margin_m < 0.0
            )
            thermal = thermal_by_station[row.station.station_id]
            self._tree.insert(
                "",
                "end",
                values=(
                    row.station.station_id,
                    f"{row.station.x_m:.5f}",
                    f"{row.station.s_m:.5f}",
                    section.channel_count,
                    f"{1000.0 * width:.4f}",
                    f"{1000.0 * height:.4f}",
                    f"{section.helix_angle_deg:.2f}",
                    f"{row.transport.velocity_m_per_s:.3f}",
                    f"{row.transport.reynolds_number:.0f}",
                    f"{row.transport.heat_transfer_coefficient_w_per_m2_k / 1000.0:.3f}",
                    f"{thermal.total_heat_flux_w_per_m2 / 1.0e6:.4f}",
                    f"{row.coolant_temperature_k:.2f}",
                    f"{thermal.wall_temperature_coolant_side_k:.2f}",
                    f"{thermal.wall_temperature_hot_gas_side_k:.2f}",
                    f"{row.coolant_pressure_pa / 1.0e5:.4f}",
                ),
                tags=("warning",) if warning else (),
            )

    def _refresh_plot(self) -> None:
        for axis in (
            self._geometry_axis,
            self._helix_axis,
            self._temperature_axis,
            self._pressure_axis,
        ):
            axis.clear()
        rows = sorted(self._channel_result.stations, key=lambda item: item.station.s_m)
        s_values = [row.station.s_m for row in rows]
        widths = [
            1000.0 * row.transport.section.hot_wall_width_per_channel_m
            for row in rows
        ]
        heights = [
            1000.0
            * (
                row.transport.section.cross_section.height_m
                or row.transport.section.cross_section.diameter_m
                or 0.0
            )
            for row in rows
        ]
        helix = [row.transport.section.helix_angle_deg for row in rows]
        temperatures = [row.coolant_temperature_k for row in rows]
        pressures = [row.coolant_pressure_pa / 1.0e5 for row in rows]
        self._geometry_axis.plot(s_values, widths, label="width / diameter", color="#145da0")
        self._geometry_axis.plot(s_values, heights, label="height", color="#0f7b6c")
        self._geometry_axis.set_ylabel("Dimension [mm]")
        self._geometry_axis.legend(frameon=False, fontsize=8)
        self._helix_axis.plot(s_values, helix, color="#7b4ba1")
        self._helix_axis.set_ylabel("Helix angle [deg]")
        thermal_rows = sorted(
            self._coupled_result.stations,
            key=lambda item: item.station.s_m,
        )
        self._temperature_axis.plot(
            s_values, temperatures, label="coolant", color="#145da0"
        )
        self._temperature_axis.plot(
            s_values,
            [row.wall_temperature_coolant_side_k for row in thermal_rows],
            label="coolant-side wall",
            color="#e18b25",
        )
        self._temperature_axis.plot(
            s_values,
            [row.wall_temperature_hot_gas_side_k for row in thermal_rows],
            label="hot-gas-side wall",
            color="#c34a36",
        )
        self._temperature_axis.set_ylabel("Temperature [K]")
        self._temperature_axis.legend(frameon=False, fontsize=7)
        self._pressure_axis.plot(s_values, pressures, color="#b26016")
        self._pressure_axis.set_ylabel("Coolant pressure [bar]")
        for axis in (
            self._geometry_axis,
            self._helix_axis,
            self._temperature_axis,
            self._pressure_axis,
        ):
            axis.set_xlabel("Hot-wall arc length s [m]")
            axis.grid(True, color="#dfe6ee", linewidth=0.8)
            axis.spines["top"].set_visible(False)
            axis.spines["right"].set_visible(False)
            axis.tick_params(labelsize=8)
        self._canvas.draw_idle()

    def _draw_empty_plot(self) -> None:
        for axis, ylabel in (
            (self._geometry_axis, "Dimension [mm]"),
            (self._helix_axis, "Helix angle [deg]"),
            (self._temperature_axis, "Coolant temperature [K]"),
            (self._pressure_axis, "Coolant pressure [bar]"),
        ):
            axis.clear()
            axis.set_xlabel("Hot-wall arc length s [m]")
            axis.set_ylabel(ylabel)
            axis.grid(True, color="#dfe6ee", linewidth=0.8)
        self._geometry_axis.text(
            0.5,
            0.5,
            "No committed design",
            transform=self._geometry_axis.transAxes,
            ha="center",
            va="center",
            color="#718096",
        )
        self._canvas.draw_idle()

    def _export_csv(self) -> None:
        if self._channel_result is None:
            self._status.set("Calculate Cooling before exporting station output.")
            return
        selected = filedialog.asksaveasfilename(
            title="Export Cooling Station Output",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="cooling_station_output.csv",
        )
        if not selected:
            return
        path = Path(selected)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "station_id",
                    "x_m",
                    "s_m",
                    "channel_count",
                    "flow_area_m2",
                    "hydraulic_diameter_m",
                    "helix_angle_deg",
                    "velocity_m_per_s",
                    "reynolds_number",
                    "prandtl_number",
                    "darcy_friction_factor",
                    "nusselt_number",
                    "h_c_w_per_m2_k",
                    "h_c_effective_w_per_m2_k",
                    "fin_area_factor",
                    "h_g_w_per_m2_k",
                    "q_convective_w_per_m2",
                    "q_radiation_w_per_m2",
                    "q_total_w_per_m2",
                    "coolant_temperature_k",
                    "wall_temperature_coolant_side_k",
                    "wall_temperature_hot_gas_side_k",
                    "wall_thermal_conductivity_w_per_m_k",
                    "coolant_pressure_pa",
                    "ligament_margin_m",
                    "dean_number",
                ]
            )
            thermal_by_station = {
                row.station.station_id: row for row in self._coupled_result.stations
            }
            for row in self._channel_result.stations:
                transport = row.transport
                section = transport.section
                thermal = thermal_by_station[row.station.station_id]
                writer.writerow(
                    [
                        row.station.station_id,
                        row.station.x_m,
                        row.station.s_m,
                        section.channel_count,
                        section.total_flow_area_m2,
                        section.hydraulic_diameter_m,
                        section.helix_angle_deg,
                        transport.velocity_m_per_s,
                        transport.reynolds_number,
                        transport.prandtl_number,
                        transport.darcy_friction_factor,
                        transport.nusselt_number,
                        transport.heat_transfer_coefficient_w_per_m2_k,
                        thermal.effective_coolant_heat_transfer_coefficient_w_per_m2_k,
                        thermal.channel_fin_area_factor,
                        thermal.gas_heat_transfer_coefficient_w_per_m2_k,
                        thermal.convective_heat_flux_w_per_m2,
                        thermal.radiation_heat_flux_w_per_m2,
                        thermal.total_heat_flux_w_per_m2,
                        row.coolant_temperature_k,
                        thermal.wall_temperature_coolant_side_k,
                        thermal.wall_temperature_hot_gas_side_k,
                        thermal.wall_thermal_conductivity_w_per_m_k,
                        row.coolant_pressure_pa,
                        transport.ligament_margin_m,
                        transport.dean_number,
                    ]
                )
        self._status.set(f"Cooling station output exported to {path}.")

    def _export_step(self) -> None:
        if self._bundle is None or self._station_mesh is None:
            self._status.set("Commit Current Design before exporting STEP.")
            return
        selected = filedialog.askdirectory(
            title="Select STEP Export Folder",
            initialdir=str(Path.cwd() / "outputs"),
        )
        if not selected:
            return
        try:
            result = export_step_geometry(
                self._bundle,
                selected,
                channel_layout=self._build_channel_layout(),
            )
        except (RuntimeError, ValueError) as exc:
            self._status.set(f"STEP export failed: {exc}")
            return
        self._status.set(
            f"STEP assembly exported to {result.assembly_step}. "
            f"Schema: {result.actual_step_schema}. "
            f"Channel representation: {result.channel_representation}."
        )

    def _export_cfd_mesh(self) -> None:
        if self._bundle is None or self._station_mesh is None:
            self._status.set("Commit Current Design before exporting CFD meshes.")
            return
        selected = filedialog.askdirectory(
            title="Select CFD Mesh Export Folder",
            initialdir=str(Path.cwd() / "outputs"),
        )
        if not selected:
            return
        try:
            result = export_cfd_meshes(
                self._bundle,
                selected,
                channel_layout=self._build_channel_layout(),
            )
        except (RuntimeError, ValueError) as exc:
            self._status.set(f"CFD mesh export failed: {exc}")
            return
        self._status.set(
            f"Tagged gas and channel meshes exported to {result.manifest_json.parent}. "
            "The JSON manifest lists all boundary IDs and mesh checks."
        )

    def _number(self, key: str) -> float:
        raw = str(self._vars[key].get()).strip().replace(",", ".")
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(value):
            raise ValueError(f"{key} must be finite.")
        return value

    def _text(self, key: str) -> str:
        value = str(self._vars[key].get()).strip()
        if not value:
            raise ValueError(f"{key} must not be empty.")
        return value

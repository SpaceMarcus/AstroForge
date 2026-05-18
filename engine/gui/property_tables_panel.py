"""Read-only property-table viewer for the last AstraForge tab."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from engine.properties import (
    get_coolant_property_table_rows,
    get_material_property_table_rows,
    list_available_coolant_tables,
    list_available_material_tables,
)


class PropertyTablesReportPanel(ttk.Frame):
    """Show editable coolant and material source tables in one report-style page."""

    _COOLANT_COLUMNS = (
        "T_K",
        "p_Pa",
        "phase",
        "rho_kg_m3",
        "cp_J_kgK",
        "mu_Pa_s",
        "k_W_mK",
        "h_J_kg",
        "Pr",
        "valid",
    )
    _MATERIAL_COLUMNS = (
        "T_K",
        "rho_kg_m3",
        "cp_J_kgK",
        "k_W_mK",
        "youngs_modulus_pa",
        "poisson_ratio",
        "cte_1_per_K",
        "yield_strength_pa",
        "ultimate_tensile_strength_pa",
    )

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.rowconfigure(3, weight=1)

        self._coolant_display_to_id: dict[str, str] = {}
        self._material_display_to_id: dict[str, str] = {}
        self._coolant_var = tk.StringVar()
        self._material_var = tk.StringVar()
        self._context_var = tk.StringVar(
            value="Current thermal coolant and liner material tables are shown here for inspection."
        )
        self._coolant_note_var = tk.StringVar(value="")
        self._material_note_var = tk.StringVar(value="")

        self._build_widgets()
        self._load_available_tables()

    def _build_widgets(self) -> None:
        header = ttk.LabelFrame(self, text="Property Table Viewer", padding=12)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text=(
                "This page shows the editable source tables that Thermal Analysis currently reads for "
                "coolant/propellant and wall-material properties."
            ),
            wraplength=1040,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            textvariable=self._context_var,
            wraplength=1040,
            justify="left",
            foreground="#667381",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        coolant_frame = ttk.LabelFrame(self, text="Stoffdaten / Coolant Property Table", padding=12)
        coolant_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        coolant_frame.columnconfigure(1, weight=1)
        coolant_frame.rowconfigure(2, weight=1)
        ttk.Label(coolant_frame, text="Table").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self._coolant_selector = ttk.Combobox(
            coolant_frame,
            state="readonly",
            textvariable=self._coolant_var,
        )
        self._coolant_selector.grid(row=0, column=1, sticky="ew")
        self._coolant_selector.bind("<<ComboboxSelected>>", lambda _event: self._refresh_coolant_table())
        ttk.Label(
            coolant_frame,
            textvariable=self._coolant_note_var,
            wraplength=1040,
            justify="left",
            foreground="#667381",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 8))
        self._coolant_tree = self._build_tree(
            coolant_frame,
            columns=self._COOLANT_COLUMNS,
            row=2,
            headings={
                "T_K": "T [K]",
                "p_Pa": "p [Pa]",
                "phase": "phase",
                "rho_kg_m3": "rho [kg/m3]",
                "cp_J_kgK": "cp [J/kg/K]",
                "mu_Pa_s": "mu [Pa*s]",
                "k_W_mK": "k [W/m/K]",
                "h_J_kg": "h [J/kg]",
                "Pr": "Pr [-]",
                "valid": "valid",
            },
        )

        material_frame = ttk.LabelFrame(self, text="Materialdaten / Screening Property Table", padding=12)
        material_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        material_frame.columnconfigure(1, weight=1)
        material_frame.rowconfigure(2, weight=1)
        ttk.Label(material_frame, text="Table").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self._material_selector = ttk.Combobox(
            material_frame,
            state="readonly",
            textvariable=self._material_var,
        )
        self._material_selector.grid(row=0, column=1, sticky="ew")
        self._material_selector.bind("<<ComboboxSelected>>", lambda _event: self._refresh_material_table())
        ttk.Label(
            material_frame,
            textvariable=self._material_note_var,
            wraplength=1040,
            justify="left",
            foreground="#667381",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 8))
        self._material_tree = self._build_tree(
            material_frame,
            columns=self._MATERIAL_COLUMNS,
            row=2,
            headings={
                "T_K": "T [K]",
                "rho_kg_m3": "rho [kg/m3]",
                "cp_J_kgK": "cp [J/kg/K]",
                "k_W_mK": "k [W/m/K]",
                "youngs_modulus_pa": "E [Pa]",
                "poisson_ratio": "nu [-]",
                "cte_1_per_K": "alpha [1/K]",
                "yield_strength_pa": "yield [Pa]",
                "ultimate_tensile_strength_pa": "UTS [Pa]",
            },
        )

    def _build_tree(
        self,
        master: ttk.LabelFrame,
        *,
        columns: tuple[str, ...],
        row: int,
        headings: dict[str, str],
    ) -> ttk.Treeview:
        table_frame = ttk.Frame(master)
        table_frame.grid(row=row, column=0, columnspan=2, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=10)
        tree.grid(row=0, column=0, sticky="nsew")
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=120, anchor="center", stretch=False)
        return tree

    def _load_available_tables(self) -> None:
        coolant_entries = list_available_coolant_tables()
        self._coolant_display_to_id = {display: fluid_id for fluid_id, display in coolant_entries}
        self._coolant_selector.configure(values=list(self._coolant_display_to_id))
        if coolant_entries:
            self._coolant_var.set(coolant_entries[0][1])
            self._refresh_coolant_table()

        material_entries = list_available_material_tables()
        self._material_display_to_id = {display: material_id for material_id, display in material_entries}
        self._material_selector.configure(values=list(self._material_display_to_id))
        if material_entries:
            self._material_var.set(material_entries[0][1])
            self._refresh_material_table()

    def update_context(
        self,
        *,
        coolant_type: str | None,
        material_id: str | None,
    ) -> None:
        coolant_text = coolant_type or "not set"
        material_text = material_id or "not set"
        self._context_var.set(
            f"Current Thermal Analysis coolant: {coolant_text}. Current liner material: {material_text}."
        )
        self._select_matching_table(self._coolant_display_to_id, self._coolant_var, coolant_type)
        self._select_matching_table(self._material_display_to_id, self._material_var, material_id)
        self._refresh_coolant_table()
        self._refresh_material_table()

    def _select_matching_table(
        self,
        display_to_id: dict[str, str],
        variable: tk.StringVar,
        preferred_id: str | None,
    ) -> None:
        if not preferred_id:
            return
        preferred_normalized = _normalize_for_match(preferred_id)
        for display, table_id in display_to_id.items():
            candidate = _normalize_for_match(table_id)
            if preferred_normalized in candidate or candidate in preferred_normalized:
                variable.set(display)
                return

    def _refresh_coolant_table(self) -> None:
        selected_display = self._coolant_var.get()
        fluid_id = self._coolant_display_to_id.get(selected_display, selected_display)
        canonical_id, display_name, rows, note = get_coolant_property_table_rows(fluid_id)
        self._coolant_note_var.set(f"{display_name} [{canonical_id}] - {note}")
        self._replace_rows(
            self._coolant_tree,
            [
                (
                    _fmt_number(row.get("T_K")),
                    _fmt_number(row.get("p_Pa")),
                    str(row.get("phase") or ""),
                    _fmt_number(row.get("rho_kg_m3")),
                    _fmt_number(row.get("cp_J_kgK")),
                    _fmt_number(row.get("mu_Pa_s")),
                    _fmt_number(row.get("k_W_mK")),
                    _fmt_number(row.get("h_J_kg")),
                    _fmt_number(row.get("Pr")),
                    str(row.get("valid") if row.get("valid") is not None else ""),
                )
                for row in rows
            ],
        )

    def _refresh_material_table(self) -> None:
        selected_display = self._material_var.get()
        material_id = self._material_display_to_id.get(selected_display, selected_display)
        canonical_id, display_name, rows, note = get_material_property_table_rows(material_id)
        self._material_note_var.set(f"{display_name} [{canonical_id}] - {note}")
        self._replace_rows(
            self._material_tree,
            [
                (
                    _fmt_number(row.get("T_K")),
                    _fmt_number(row.get("rho_kg_m3")),
                    _fmt_number(row.get("cp_J_kgK")),
                    _fmt_number(row.get("k_W_mK")),
                    _fmt_number(row.get("youngs_modulus_pa")),
                    _fmt_number(row.get("poisson_ratio")),
                    _fmt_number(row.get("cte_1_per_K")),
                    _fmt_number(row.get("yield_strength_pa")),
                    _fmt_number(row.get("ultimate_tensile_strength_pa")),
                )
                for row in rows
            ],
        )

    @staticmethod
    def _replace_rows(tree: ttk.Treeview, rows: list[tuple[str, ...]]) -> None:
        tree.delete(*tree.get_children())
        for row in rows:
            tree.insert("", "end", values=row)


def _fmt_number(value: object) -> str:
    if value is None:
        return "--"
    numeric = float(value)
    magnitude = abs(numeric)
    if magnitude >= 1.0e6 or (0.0 < magnitude < 1.0e-3):
        return f"{numeric:.4e}"
    if magnitude >= 1.0:
        return f"{numeric:.4f}"
    return f"{numeric:.6f}"


def _normalize_for_match(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())

"""Editable property-table lookup for AstraForge thermal analysis.

The current thermal-analysis MVP still uses simple annulus-cooling physics, but
it now evaluates coolant and wall properties from external tables instead of
hard-coding everything in the solver. The tables are intentionally plain JSON
or CSV files so they can be reviewed and replaced later with more traceable
REFPROP/NIST/CoolProp-derived datasets.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import json
import math
from pathlib import Path
import sys


_PROPELLANT_FILE_CANDIDATES = (
    "propellant_property_tables_nist_style.json",
    "propellant_property_tables_nist_style.csv",
)
_MATERIAL_FILE_CANDIDATES = (
    "solid_material_properties_screening_v1.json",
    "solid_material_properties_screening_v1.csv",
)
_PROPERTY_WARNING_OUTSIDE_RANGE = "property lookup outside table range; clamped to available data"
_MATERIAL_WARNING_OUTSIDE_RANGE = "outside material property table range; endpoint value used"
_OXYGEN_NOT_LIQUID_WARNING = "oxygen property state is not liquid at requested T,p"
_COOLANT_FALLBACK_WARNING = "fallback constant coolant properties used"
_MATERIAL_FALLBACK_WARNING = "fallback material properties used"
_COOLANT_TABLE_NOTE = "coolant properties from table"
_MATERIAL_TABLE_NOTE = "material properties from screening table"
_GRCOP_RT_ONLY_WARNING = "GRCop-42 high-temperature mechanical properties are process-dependent; RT-only screening value used"


@dataclass(slots=True)
class CoolantProperties:
    density_kg_per_m3: float
    cp_j_per_kg_k: float
    viscosity_pa_s: float
    thermal_conductivity_w_per_m_k: float
    enthalpy_j_per_kg: float | None = None
    prandtl_number: float | None = None
    phase: str | None = None
    source: str = "table"
    valid: bool = True
    note: str = ""


@dataclass(slots=True)
class MaterialProperties:
    density_kg_per_m3: float | None
    cp_j_per_kg_k: float | None
    thermal_conductivity_w_per_m_k: float | None
    youngs_modulus_pa: float | None
    poisson_ratio: float | None
    cte_1_per_k: float | None
    yield_strength_pa: float | None
    ultimate_tensile_strength_pa: float | None
    source: str = "table"
    valid: bool = True
    note: str = ""


_PROPELLANT_TABLE_CACHE: dict[str, list[dict[str, object]]] | None = None
_MATERIAL_TABLE_CACHE: dict[str, dict[str, object]] | None = None


def get_coolant_properties(
    fluid_id: str,
    temperature_k: float,
    pressure_pa: float | None = None,
) -> CoolantProperties:
    """Return coolant properties from editable tables with graceful fallback."""

    canonical_id = _canonical_coolant_id(fluid_id)
    table = _load_propellant_tables()
    rows = table.get(canonical_id) if table is not None else None
    if not rows:
        return _fallback_coolant_properties(fluid_id)

    temperatures = sorted({float(row["T_K"]) for row in rows})
    pressures = sorted({float(row["p_Pa"]) for row in rows})
    if not temperatures or not pressures:
        return _fallback_coolant_properties(fluid_id)

    lookup_index = {
        (float(row["T_K"]), float(row["p_Pa"])): row
        for row in rows
    }
    note_parts = [_COOLANT_TABLE_NOTE]

    temperature_note, t1, t2 = _resolve_bounds(temperature_k, temperatures)
    if temperature_note:
        note_parts.append(temperature_note)
    if pressure_pa is None:
        # When no pressure estimate is available yet, use the highest table
        # pressure so dense liquid/supercritical coolant data remain the default.
        p1 = p2 = pressures[-1]
        note_parts.append("pressure not provided; using highest available table pressure")
    else:
        pressure_note, p1, p2 = _resolve_bounds(pressure_pa, pressures)
        if pressure_note:
            note_parts.append(pressure_note)

    density = _bilinear_property(lookup_index, "rho_kg_m3", temperature_k, pressure_pa, t1, t2, p1, p2)
    cp = _bilinear_property(lookup_index, "cp_J_kgK", temperature_k, pressure_pa, t1, t2, p1, p2)
    viscosity = _bilinear_property(lookup_index, "mu_Pa_s", temperature_k, pressure_pa, t1, t2, p1, p2)
    conductivity = _bilinear_property(lookup_index, "k_W_mK", temperature_k, pressure_pa, t1, t2, p1, p2)
    enthalpy = _bilinear_property_optional(lookup_index, "h_J_kg", temperature_k, pressure_pa, t1, t2, p1, p2)
    prandtl = _bilinear_property_optional(lookup_index, "Pr", temperature_k, pressure_pa, t1, t2, p1, p2)
    if prandtl is None and cp is not None and viscosity is not None and conductivity not in {None, 0.0}:
        prandtl = cp * viscosity / conductivity

    nearest_row = _nearest_propellant_row(rows, temperature_k, pressure_pa if pressure_pa is not None else p1)
    phase = str(nearest_row.get("phase") or "") or None
    valid = bool(nearest_row.get("valid", True))
    if canonical_id == "LOX_OXYGEN" and phase is not None and phase.lower() in {"gas", "vapor", "supercritical_gas"}:
        valid = False
        note_parts.append(_OXYGEN_NOT_LIQUID_WARNING)

    if None in {density, cp, viscosity, conductivity}:
        fallback = _fallback_coolant_properties(fluid_id)
        fallback.note = _join_notes(note_parts + [_COOLANT_FALLBACK_WARNING])
        return fallback

    return CoolantProperties(
        density_kg_per_m3=density,
        cp_j_per_kg_k=cp,
        viscosity_pa_s=viscosity,
        thermal_conductivity_w_per_m_k=conductivity,
        enthalpy_j_per_kg=enthalpy,
        prandtl_number=prandtl,
        phase=phase,
        source="table",
        valid=valid,
        note=_join_notes(note_parts),
    )


def get_material_properties(
    material_id: str,
    temperature_k: float,
) -> MaterialProperties:
    """Return screening material properties from editable temperature tables."""

    canonical_id = _canonical_material_id(material_id)
    table = _load_material_tables()
    entry = table.get(canonical_id) if table is not None else None
    if entry is None:
        return _fallback_material_properties(material_id)

    rows = list(entry.get("rows", []))
    property_curves: dict[str, list[tuple[float, float]]] = entry.get("property_curves", {})
    if not rows or not property_curves:
        return _fallback_material_properties(material_id)

    note_parts = [_MATERIAL_TABLE_NOTE]
    source_note = _material_source_note(entry)
    if source_note:
        note_parts.append(source_note)
    density_kg_per_m3, density_note = _lookup_material_curve(
        property_curves.get("density_kg_per_m3", []),
        temperature_k,
    )
    cp_j_per_kg_k, cp_note = _lookup_material_curve(
        property_curves.get("cp_j_per_kg_k", []),
        temperature_k,
    )
    thermal_conductivity_w_per_m_k, conductivity_note = _lookup_material_curve(
        property_curves.get("thermal_conductivity_w_per_m_k", []),
        temperature_k,
    )
    youngs_modulus_pa, modulus_note = _lookup_material_curve(
        property_curves.get("youngs_modulus_pa", []),
        temperature_k,
    )
    poisson_ratio, poisson_note = _lookup_material_curve(
        property_curves.get("poisson_ratio", []),
        temperature_k,
    )
    cte_1_per_k, cte_note = _lookup_material_curve(
        property_curves.get("cte_1_per_k", []),
        temperature_k,
    )
    yield_strength_pa, yield_note = _lookup_material_curve(
        property_curves.get("yield_strength_pa", []),
        temperature_k,
    )
    ultimate_tensile_strength_pa, uts_note = _lookup_material_curve(
        property_curves.get("ultimate_tensile_strength_pa", []),
        temperature_k,
    )
    note_parts.extend(
        note
        for note in (
            density_note,
            cp_note,
            conductivity_note,
            modulus_note,
            poisson_note,
            cte_note,
            yield_note,
            uts_note,
        )
        if note
    )
    if canonical_id == "grcop42" and abs(temperature_k - 293.15) > 5.0:
        note_parts.append(_GRCOP_RT_ONLY_WARNING)

    return MaterialProperties(
        density_kg_per_m3=density_kg_per_m3,
        cp_j_per_kg_k=cp_j_per_kg_k,
        thermal_conductivity_w_per_m_k=thermal_conductivity_w_per_m_k,
        youngs_modulus_pa=youngs_modulus_pa,
        poisson_ratio=poisson_ratio,
        cte_1_per_k=cte_1_per_k,
        yield_strength_pa=yield_strength_pa,
        ultimate_tensile_strength_pa=ultimate_tensile_strength_pa,
        source="screening-table",
        valid=True,
        note=_join_notes(note_parts),
    )


def list_available_coolant_tables() -> list[tuple[str, str]]:
    """Return available coolant/propellant tables for UI selection."""

    table = _load_propellant_tables() or {}
    entries: list[tuple[str, str]] = []
    for fluid_id in sorted(table):
        rows = table[fluid_id]
        display_name = str(rows[0].get("display_name") or fluid_id) if rows else fluid_id
        entries.append((fluid_id, display_name))
    return entries


def list_available_material_tables() -> list[tuple[str, str]]:
    """Return available material tables for UI selection."""

    table = _load_material_tables() or {}
    seen_ids: set[int] = set()
    entries: list[tuple[str, str]] = []
    for alias, entry in sorted(table.items()):
        entry_id = id(entry)
        if entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)
        display_name = str(entry.get("display_name") or alias)
        entries.append((alias, display_name))
    entries.sort(key=lambda item: item[1].lower())
    return entries


def get_coolant_property_table_rows(fluid_id: str) -> tuple[str, str, list[dict[str, object]], str]:
    """Return one coolant table in a UI-friendly normalized form."""

    canonical_id = _canonical_coolant_id(fluid_id)
    table = _load_propellant_tables() or {}
    rows = list(table.get(canonical_id, []))
    if not rows:
        fallback = _fallback_coolant_properties(fluid_id)
        return canonical_id, canonical_id, [], fallback.note
    rows.sort(key=lambda row: (float(row["p_Pa"]), float(row["T_K"])))
    display_name = str(rows[0].get("display_name") or canonical_id)
    return canonical_id, display_name, rows, _COOLANT_TABLE_NOTE


def get_material_property_table_rows(material_id: str) -> tuple[str, str, list[dict[str, object]], str]:
    """Return one material table in a UI-friendly normalized form."""

    canonical_id = _canonical_material_id(material_id)
    table = _load_material_tables() or {}
    entry = table.get(canonical_id)
    if entry is None:
        fallback = _fallback_material_properties(material_id)
        return canonical_id, canonical_id, [], fallback.note
    rows = sorted(
        list(entry.get("rows", [])),
        key=lambda row: float(row.get("T_K") or 0.0),
    )
    display_name = str(entry.get("display_name") or canonical_id)
    return canonical_id, display_name, rows, _join_notes(
        [_MATERIAL_TABLE_NOTE, _material_source_note(entry)]
    )


def _clear_property_table_caches() -> None:
    """Test helper to force a fresh file read."""

    global _PROPELLANT_TABLE_CACHE, _MATERIAL_TABLE_CACHE
    _PROPELLANT_TABLE_CACHE = None
    _MATERIAL_TABLE_CACHE = None


def _project_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def _property_data_dir() -> Path:
    return _project_root() / "data" / "properties"


def _load_propellant_tables() -> dict[str, list[dict[str, object]]] | None:
    global _PROPELLANT_TABLE_CACHE
    if _PROPELLANT_TABLE_CACHE is not None:
        return _PROPELLANT_TABLE_CACHE

    path = _find_existing_data_file(_PROPELLANT_FILE_CANDIDATES)
    if path is None:
        _PROPELLANT_TABLE_CACHE = {}
        return _PROPELLANT_TABLE_CACHE

    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records", [])
    else:
        with path.open("r", encoding="utf-8", newline="") as handle:
            records = list(csv.DictReader(handle))

    grouped: dict[str, list[dict[str, object]]] = {}
    for raw_record in records:
        fluid_key = str(raw_record.get("fluid_id", "")).strip()
        if not fluid_key:
            continue
        normalized = {
            "fluid_id": fluid_key,
            "display_name": raw_record.get("display_name"),
            "T_K": _to_float(raw_record.get("T_K")),
            "p_Pa": _to_float(raw_record.get("p_Pa")),
            "phase": raw_record.get("phase"),
            "rho_kg_m3": _to_float(raw_record.get("rho_kg_m3")),
            "cp_J_kgK": _to_float(raw_record.get("cp_J_kgK")),
            "mu_Pa_s": _to_float(raw_record.get("mu_Pa_s")),
            "k_W_mK": _to_float(raw_record.get("k_W_mK")),
            "h_J_kg": _to_float(raw_record.get("h_J_kg")),
            "Pr": _to_float(raw_record.get("Pr")),
            "valid": _to_bool(raw_record.get("valid"), default=True),
            "note": raw_record.get("note"),
        }
        if normalized["T_K"] is None or normalized["p_Pa"] is None:
            continue
        grouped.setdefault(fluid_key, []).append(normalized)

    _PROPELLANT_TABLE_CACHE = grouped
    return _PROPELLANT_TABLE_CACHE


def _load_material_tables() -> dict[str, dict[str, object]] | None:
    global _MATERIAL_TABLE_CACHE
    if _MATERIAL_TABLE_CACHE is not None:
        return _MATERIAL_TABLE_CACHE

    path = _find_existing_data_file(_MATERIAL_FILE_CANDIDATES)
    if path is None:
        _MATERIAL_TABLE_CACHE = {}
        return _MATERIAL_TABLE_CACHE

    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        materials = payload.get("materials", [])
    else:
        materials = _load_materials_from_csv(path)

    grouped: dict[str, dict[str, object]] = {}
    for material in materials:
        material_id = _normalize_alias(
            str(
                material.get("material_id")
                or material.get("id")
                or material.get("display_name")
                or ""
            )
        )
        if not material_id:
            continue
        rows: list[dict[str, float | None]] = []
        for row in material.get("table", material.get("temperature_table", [])):
            normalized_row = _normalize_material_row(row)
            if normalized_row["T_K"] is not None:
                rows.append(normalized_row)
        aliases = {_normalize_alias(alias) for alias in material.get("aliases", [])}
        aliases.add(material_id)
        aliases.add(_normalize_alias(str(material.get("display_name", ""))))
        entry = {
            "display_name": material.get("display_name"),
            "source_label": material.get("source_label") or material.get("source_label_primary") or material.get("source_label_physical"),
            "source_url": material.get("source_url") or material.get("source_url_primary") or material.get("source_url_physical"),
            "source_notes": material.get("source_notes"),
            "rows": rows,
            "property_curves": _build_material_property_curves(rows),
        }
        for alias in aliases:
            if alias:
                grouped[alias] = entry

    _MATERIAL_TABLE_CACHE = grouped
    return _MATERIAL_TABLE_CACHE


def _load_materials_from_csv(path: Path) -> list[dict[str, object]]:
    """Load a simple flat CSV material table if one is provided later."""

    grouped: dict[str, dict[str, object]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            material_key = _normalize_alias(str(row.get("material_id") or row.get("display_name") or ""))
            if not material_key:
                continue
            entry = grouped.setdefault(
                material_key,
                {
                    "id": material_key,
                    "display_name": row.get("display_name") or row.get("material_id"),
                    "aliases": [],
                    "temperature_table": [],
                },
            )
            entry["temperature_table"].append(row)
    return list(grouped.values())


def _normalize_material_row(row: dict[str, object]) -> dict[str, float | None]:
    """Normalize one material row from either legacy or SI-first JSON tables."""

    return {
        "T_K": _to_float(row.get("T_K") or row.get("temperature_k")),
        "rho_kg_m3": _to_float(row.get("rho_kg_m3") or row.get("density_kg_per_m3")),
        "cp_J_kgK": _to_float(row.get("cp_J_kgK") or row.get("cp_j_per_kg_k")),
        "k_W_mK": _to_float(row.get("k_W_mK") or row.get("thermal_conductivity_w_per_m_k")),
        "youngs_modulus_pa": _first_float(
            _to_float(row.get("youngs_modulus_pa")),
            _mpa_or_gpa_to_pa(row.get("youngs_modulus_GPa"), scale=1.0e9),
        ),
        "poisson_ratio": _to_float(row.get("poisson_ratio")),
        "cte_1_per_K": _to_float(row.get("cte_1_per_K") or row.get("cte_1_per_k")),
        "yield_strength_pa": _first_float(
            _to_float(row.get("yield_strength_pa")),
            _mpa_or_gpa_to_pa(row.get("yield_strength_MPa"), scale=1.0e6),
        ),
        "ultimate_tensile_strength_pa": _first_float(
            _to_float(row.get("ultimate_tensile_strength_pa") or row.get("tensile_strength_pa")),
            _mpa_or_gpa_to_pa(row.get("ultimate_tensile_strength_MPa"), scale=1.0e6),
        ),
    }


def _build_material_property_curves(
    rows: list[dict[str, float | None]],
) -> dict[str, list[tuple[float, float]]]:
    """Split a sparse combined table into per-property temperature curves."""

    field_mapping = {
        "density_kg_per_m3": "rho_kg_m3",
        "cp_j_per_kg_k": "cp_J_kgK",
        "thermal_conductivity_w_per_m_k": "k_W_mK",
        "youngs_modulus_pa": "youngs_modulus_pa",
        "poisson_ratio": "poisson_ratio",
        "cte_1_per_k": "cte_1_per_K",
        "yield_strength_pa": "yield_strength_pa",
        "ultimate_tensile_strength_pa": "ultimate_tensile_strength_pa",
    }
    curves: dict[str, list[tuple[float, float]]] = {}
    for output_field, row_key in field_mapping.items():
        points = [
            (float(row["T_K"]), float(value))
            for row in rows
            if row.get("T_K") is not None and (value := row.get(row_key)) is not None
        ]
        points.sort(key=lambda point: point[0])
        curves[output_field] = points
    return curves


def _lookup_material_curve(
    curve: list[tuple[float, float]],
    temperature_k: float,
) -> tuple[float | None, str | None]:
    """Interpolate one material property on its own temperature grid."""

    if not curve:
        return None, None
    if len(curve) == 1:
        point_temperature_k, point_value = curve[0]
        if math.isclose(temperature_k, point_temperature_k, rel_tol=0.0, abs_tol=1.0e-9):
            return point_value, None
        return point_value, _MATERIAL_WARNING_OUTSIDE_RANGE
    if temperature_k <= curve[0][0]:
        note = None if math.isclose(temperature_k, curve[0][0], rel_tol=0.0, abs_tol=1.0e-9) else _MATERIAL_WARNING_OUTSIDE_RANGE
        return curve[0][1], note
    if temperature_k >= curve[-1][0]:
        note = None if math.isclose(temperature_k, curve[-1][0], rel_tol=0.0, abs_tol=1.0e-9) else _MATERIAL_WARNING_OUTSIDE_RANGE
        return curve[-1][1], note
    for (lower_temperature_k, lower_value), (upper_temperature_k, upper_value) in zip(curve, curve[1:]):
        if lower_temperature_k <= temperature_k <= upper_temperature_k:
            fraction = _fraction_between(lower_temperature_k, upper_temperature_k, temperature_k)
            return lower_value + (upper_value - lower_value) * fraction, None
    return curve[-1][1], _MATERIAL_WARNING_OUTSIDE_RANGE


def _material_source_note(entry: dict[str, object]) -> str | None:
    source_label = str(entry.get("source_label") or "").strip()
    return f"source: {source_label}" if source_label else None


def _find_existing_data_file(candidates: tuple[str, ...]) -> Path | None:
    for name in candidates:
        path = _property_data_dir() / name
        if path.exists():
            return path
    return None


def _canonical_coolant_id(fluid_id: str) -> str:
    key = _normalize_alias(fluid_id)
    mapping = {
        "rp1": "RP1_SURROGATE_N_DODECANE",
        "rp-1": "RP1_SURROGATE_N_DODECANE",
        "kerosene": "RP1_SURROGATE_N_DODECANE",
        "n-dodecane": "RP1_SURROGATE_N_DODECANE",
        "lox": "LOX_OXYGEN",
        "o2": "LOX_OXYGEN",
        "oxygen": "LOX_OXYGEN",
        "liquidoxygen": "LOX_OXYGEN",
    }
    return mapping.get(key, fluid_id.strip())


def _canonical_material_id(material_id: str) -> str:
    key = _normalize_alias(material_id)
    mapping = {
        "grcop42": "grcop42",
        "grcop-42": "grcop42",
        "cucrnb": "grcop42",
        "cu-4cr-2nb": "grcop42",
        "grcop42rt": "grcop42",
        "inconel718": "inconel718",
        "in718": "inconel718",
        "alloy718": "inconel718",
        "unsn07718": "inconel718",
        "cucrzr": "cucrzr",
        "c18150": "cucrzr",
        "copperchromiumzirconium": "cucrzr",
        "cucrzralloy": "cucrzr",
        "316": "316stainlesssteel",
        "316l": "316stainlesssteel",
        "stainless316l": "316stainlesssteel",
        "316lstainlesssteel": "316stainlesssteel",
        "316stainlesssteel": "316stainlesssteel",
    }
    return mapping.get(key, key)


def _normalize_alias(value: str) -> str:
    return "".join(character for character in value.strip().lower() if character.isalnum())


def _to_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _to_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"false", "0", "no"}


def _mpa_or_gpa_to_pa(value: object, *, scale: float) -> float | None:
    numeric_value = _to_float(value)
    if numeric_value is None:
        return None
    return numeric_value * scale


def _first_float(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _resolve_bounds(
    value: float,
    grid: list[float],
    *,
    outside_note: str = _PROPERTY_WARNING_OUTSIDE_RANGE,
) -> tuple[str | None, float, float]:
    if not grid:
        raise ValueError("Interpolation grid must not be empty.")
    if value <= grid[0]:
        note = outside_note if value < grid[0] else None
        return note, grid[0], grid[0]
    if value >= grid[-1]:
        note = outside_note if value > grid[-1] else None
        return note, grid[-1], grid[-1]
    for lower, upper in zip(grid, grid[1:]):
        if lower <= value <= upper:
            return None, lower, upper
    return outside_note, grid[-1], grid[-1]


def _bilinear_property(
    lookup_index: dict[tuple[float, float], dict[str, object]],
    field_name: str,
    temperature_k: float,
    pressure_pa: float | None,
    t1: float,
    t2: float,
    p1: float,
    p2: float,
) -> float | None:
    value = _bilinear_property_optional(
        lookup_index,
        field_name,
        temperature_k,
        pressure_pa,
        t1,
        t2,
        p1,
        p2,
    )
    return value


def _bilinear_property_optional(
    lookup_index: dict[tuple[float, float], dict[str, object]],
    field_name: str,
    temperature_k: float,
    pressure_pa: float | None,
    t1: float,
    t2: float,
    p1: float,
    p2: float,
) -> float | None:
    q11 = _to_float(lookup_index.get((t1, p1), {}).get(field_name))
    q21 = _to_float(lookup_index.get((t2, p1), {}).get(field_name))
    q12 = _to_float(lookup_index.get((t1, p2), {}).get(field_name))
    q22 = _to_float(lookup_index.get((t2, p2), {}).get(field_name))
    if None in {q11, q21, q12, q22}:
        nearest_row = _nearest_available_corner(lookup_index, field_name, t1, t2, p1, p2)
        return _to_float(nearest_row.get(field_name)) if nearest_row is not None else None

    t_value = min(max(temperature_k, min(t1, t2)), max(t1, t2))
    if pressure_pa is None:
        p_value = p1
    else:
        p_value = min(max(pressure_pa, min(p1, p2)), max(p1, p2))

    lower_pressure_value = _interpolate_optional(q11, q21, _fraction_between(t1, t2, t_value))
    upper_pressure_value = _interpolate_optional(q12, q22, _fraction_between(t1, t2, t_value))
    return _interpolate_optional(lower_pressure_value, upper_pressure_value, _fraction_between(p1, p2, p_value))


def _nearest_available_corner(
    lookup_index: dict[tuple[float, float], dict[str, object]],
    field_name: str,
    t1: float,
    t2: float,
    p1: float,
    p2: float,
) -> dict[str, object] | None:
    for key in ((t1, p1), (t2, p1), (t1, p2), (t2, p2)):
        row = lookup_index.get(key)
        if row is not None and _to_float(row.get(field_name)) is not None:
            return row
    return None


def _nearest_propellant_row(
    rows: list[dict[str, object]],
    temperature_k: float,
    pressure_pa: float,
) -> dict[str, object]:
    pressure_scale = max(abs(pressure_pa), 1.0)
    return min(
        rows,
        key=lambda row: (
            abs(float(row["T_K"]) - temperature_k) / max(abs(temperature_k), 1.0)
            + abs(float(row["p_Pa"]) - pressure_pa) / pressure_scale
        ),
    )


def _interpolate_optional(left_value: float | None, right_value: float | None, fraction: float) -> float | None:
    if left_value is None and right_value is None:
        return None
    if left_value is None:
        return right_value
    if right_value is None:
        return left_value
    return left_value + (right_value - left_value) * fraction


def _fraction_between(lower: float, upper: float, value: float) -> float:
    if math.isclose(lower, upper):
        return 0.0
    return (value - lower) / (upper - lower)


def _join_notes(parts: list[str]) -> str:
    unique_parts: list[str] = []
    for part in parts:
        if part and part not in unique_parts:
            unique_parts.append(part)
    return ", ".join(unique_parts)


def _fallback_coolant_properties(fluid_id: str) -> CoolantProperties:
    """Emergency fallback if no property table is available."""

    coolant_key = _normalize_alias(fluid_id)
    database = {
        "rp1": CoolantProperties(810.0, 2_200.0, 1.8e-3, 0.13, prandtl_number=30.46, source="fallback"),
        "rpn1": CoolantProperties(810.0, 2_200.0, 1.8e-3, 0.13, prandtl_number=30.46, source="fallback"),
        "kerosene": CoolantProperties(810.0, 2_200.0, 1.8e-3, 0.13, prandtl_number=30.46, source="fallback"),
        "lox": CoolantProperties(1140.0, 1_700.0, 2.0e-4, 0.15, prandtl_number=2.27, source="fallback", phase="liquid"),
        "o2": CoolantProperties(1140.0, 1_700.0, 2.0e-4, 0.15, prandtl_number=2.27, source="fallback", phase="liquid"),
        "oxygen": CoolantProperties(1140.0, 1_700.0, 2.0e-4, 0.15, prandtl_number=2.27, source="fallback", phase="liquid"),
        "ch4": CoolantProperties(420.0, 3_500.0, 1.2e-4, 0.19, prandtl_number=2.21, source="fallback"),
        "methane": CoolantProperties(420.0, 3_500.0, 1.2e-4, 0.19, prandtl_number=2.21, source="fallback"),
        "lh2": CoolantProperties(70.0, 9_600.0, 1.3e-5, 0.10, prandtl_number=1.25, source="fallback"),
        "h2": CoolantProperties(70.0, 9_600.0, 1.3e-5, 0.10, prandtl_number=1.25, source="fallback"),
        "water": CoolantProperties(997.0, 4_180.0, 1.0e-3, 0.60, prandtl_number=6.97, source="fallback"),
    }
    fallback = database.get(coolant_key, CoolantProperties(810.0, 2_200.0, 1.8e-3, 0.13, source="fallback"))
    return CoolantProperties(
        density_kg_per_m3=fallback.density_kg_per_m3,
        cp_j_per_kg_k=fallback.cp_j_per_kg_k,
        viscosity_pa_s=fallback.viscosity_pa_s,
        thermal_conductivity_w_per_m_k=fallback.thermal_conductivity_w_per_m_k,
        enthalpy_j_per_kg=fallback.enthalpy_j_per_kg,
        prandtl_number=fallback.prandtl_number,
        phase=fallback.phase,
        source="fallback",
        valid=True,
        note=_COOLANT_FALLBACK_WARNING,
    )


def _fallback_material_properties(material_id: str) -> MaterialProperties:
    """Emergency screening fallback if no material table is available."""

    material_key = _canonical_material_id(material_id)
    database = {
        "grcop42": MaterialProperties(8890.0, 385.0, 287.5, 129.7e9, 0.34, 1.7e-5, 186.0e6, 260.0e6, source="fallback"),
        "inconel718": MaterialProperties(8190.0, 435.0, 11.4, 200.0e9, 0.29, 1.3e-5, 1030.0e6, 1275.0e6, source="fallback"),
        "cucrzr": MaterialProperties(8960.0, 380.0, 320.0, 120.0e9, 0.34, 1.7e-5, 325.0e6, 395.0e6, source="fallback"),
        "316stainlesssteel": MaterialProperties(8000.0, 500.0, 16.0, 193.0e9, 0.29, 1.6e-5, 290.0e6, 580.0e6, source="fallback"),
    }
    fallback = database.get(material_key, MaterialProperties(None, None, 25.0, None, None, None, None, None, source="fallback"))
    return MaterialProperties(
        density_kg_per_m3=fallback.density_kg_per_m3,
        cp_j_per_kg_k=fallback.cp_j_per_kg_k,
        thermal_conductivity_w_per_m_k=fallback.thermal_conductivity_w_per_m_k,
        youngs_modulus_pa=fallback.youngs_modulus_pa,
        poisson_ratio=fallback.poisson_ratio,
        cte_1_per_k=fallback.cte_1_per_k,
        yield_strength_pa=fallback.yield_strength_pa,
        ultimate_tensile_strength_pa=fallback.ultimate_tensile_strength_pa,
        source="fallback",
        valid=True,
        note=_MATERIAL_FALLBACK_WARNING,
    )

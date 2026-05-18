"""Tests for editable coolant and material property tables."""

from engine.properties import (
    get_coolant_properties,
    get_coolant_property_table_rows,
    get_material_properties,
    get_material_property_table_rows,
    list_available_coolant_tables,
    list_available_material_tables,
)
from engine.properties import property_tables


def test_rp1_table_lookup_varies_with_temperature_and_pressure() -> None:
    cold_low_pressure = get_coolant_properties("RP-1", 293.15, 2.0e6)
    hot_high_pressure = get_coolant_properties("kerosene", 653.15, 2.0e7)

    assert cold_low_pressure.source == "table"
    assert hot_high_pressure.source == "table"
    assert cold_low_pressure.density_kg_per_m3 != hot_high_pressure.density_kg_per_m3
    assert cold_low_pressure.viscosity_pa_s != hot_high_pressure.viscosity_pa_s
    assert "coolant properties from table" in cold_low_pressure.note


def test_oxygen_lookup_flags_non_liquid_state() -> None:
    gas_state = get_coolant_properties("LOX", 200.0, 3.0e5)

    assert gas_state.source == "table"
    assert gas_state.valid is False
    assert "oxygen property state is not liquid" in gas_state.note


def test_coolant_lookup_clamps_outside_available_range() -> None:
    lookup = get_coolant_properties("RP1", 200.0, 3.0e7)

    assert lookup.source == "table"
    assert "outside table range" in lookup.note


def test_material_lookup_varies_with_temperature() -> None:
    cold = get_material_properties("CuCrZr", 293.15)
    hot = get_material_properties("C18150", 1100.0)

    assert cold.source == "screening-table"
    assert hot.source == "screening-table"
    assert cold.thermal_conductivity_w_per_m_k != hot.thermal_conductivity_w_per_m_k
    assert cold.youngs_modulus_pa != hot.youngs_modulus_pa


def test_material_lookup_clamps_outside_range() -> None:
    lookup = get_material_properties("IN718", 1500.0)

    assert lookup.source == "screening-table"
    assert "endpoint value used" in lookup.note


def test_material_aliases_resolve_to_same_screening_curve() -> None:
    assert get_material_properties("Cu-Cr-Zr", 600.0).youngs_modulus_pa == get_material_properties("CuCrZr", 600.0).youngs_modulus_pa
    assert get_material_properties("Alloy 718", 922.04).yield_strength_pa == get_material_properties("IN718", 922.04).yield_strength_pa
    assert get_material_properties("316L stainless steel", 773.15).yield_strength_pa == get_material_properties("316", 773.15).yield_strength_pa


def test_cucrzr_interpolation_uses_property_specific_temperature_grids() -> None:
    lookup = get_material_properties("CuCrZr", 600.0)

    assert lookup.youngs_modulus_pa is not None
    assert 87.0e9 < lookup.youngs_modulus_pa < 106.0e9
    assert lookup.cte_1_per_k is not None
    assert abs(lookup.cte_1_per_k - 17.9e-6) < 1.0e-10


def test_in718_lookup_matches_preferred_high_temperature_screening_values() -> None:
    lookup = get_material_properties("IN718", 922.04)

    assert lookup.youngs_modulus_pa is not None
    assert abs(lookup.youngs_modulus_pa - 163.40e9) < 1.0e8
    assert lookup.yield_strength_pa is not None
    assert abs(lookup.yield_strength_pa - 965.27e6) < 1.0e5


def test_316l_lookup_matches_screening_values_at_773k() -> None:
    lookup = get_material_properties("316L", 773.15)

    assert lookup.youngs_modulus_pa is not None
    assert abs(lookup.youngs_modulus_pa - 165.0e9) < 1.0e8
    assert lookup.yield_strength_pa is not None
    assert abs(lookup.yield_strength_pa - 180.0e6) < 1.0e5


def test_grcop42_warns_about_room_temperature_only_screening_values() -> None:
    lookup = get_material_properties("GRCop-42", 600.0)

    assert lookup.youngs_modulus_pa is not None
    assert "RT-only screening value used" in lookup.note


def test_property_lookup_falls_back_when_tables_are_missing(monkeypatch) -> None:
    property_tables._clear_property_table_caches()
    monkeypatch.setattr(property_tables, "_PROPELLANT_FILE_CANDIDATES", ("missing_propellant_table.json",))
    monkeypatch.setattr(property_tables, "_MATERIAL_FILE_CANDIDATES", ("missing_material_table.json",))

    coolant = get_coolant_properties("RP-1", 300.0, 5.0e6)
    material = get_material_properties("CuCrZr", 500.0)

    assert coolant.source == "fallback"
    assert "fallback constant coolant properties used" in coolant.note
    assert material.source == "fallback"
    assert "fallback material properties used" in material.note

    property_tables._clear_property_table_caches()


def test_property_table_listing_helpers_return_editable_rows() -> None:
    coolant_tables = list_available_coolant_tables()
    material_tables = list_available_material_tables()

    assert any(fluid_id == "RP1_SURROGATE_N_DODECANE" for fluid_id, _display in coolant_tables)
    assert any("CuCrZr" in display for _alias, display in material_tables)

    coolant_id, coolant_name, coolant_rows, coolant_note = get_coolant_property_table_rows("RP-1")
    material_id, material_name, material_rows, material_note = get_material_property_table_rows("CuCrZr")

    assert coolant_id == "RP1_SURROGATE_N_DODECANE"
    assert "RP-1" in coolant_name
    assert coolant_rows
    assert "coolant properties from table" in coolant_note

    assert "cucrzr" in material_id.lower()
    assert "CuCrZr" in material_name
    assert material_rows
    assert "material properties from screening table" in material_note

"""Tests for central unit conversion helpers."""

import pytest

from engine.unit_system import UnitPreset, convert_from_display, convert_to_display, format_quantity, get_unit_symbol


def test_pressure_roundtrip_for_si_cad_bar() -> None:
    pressure_pa = 7.0e6
    display_value = convert_to_display(pressure_pa, "pressure", UnitPreset.SI_CAD)

    assert display_value == 70.0
    assert convert_from_display(display_value, "pressure", UnitPreset.SI_CAD) == pytest.approx(pressure_pa)


def test_length_roundtrip_for_us_inches() -> None:
    length_m = 0.0254
    display_value = convert_to_display(length_m, "length", UnitPreset.US)

    assert display_value == 1.0
    assert convert_from_display(display_value, "length", UnitPreset.US) == pytest.approx(length_m)


def test_common_force_format_keeps_editable_primary_value_clean() -> None:
    thrust_n = 100_000.0

    assert format_quantity(thrust_n, "force", UnitPreset.COMMON) == "100.000"
    assert "tf" in format_quantity(
        thrust_n,
        "force",
        UnitPreset.COMMON,
        include_unit=True,
        include_secondary=True,
    )


def test_axis_unit_symbols_exist_for_all_presets() -> None:
    assert get_unit_symbol("pressure", UnitPreset.SI) == "Pa"
    assert get_unit_symbol("pressure", UnitPreset.SI_CAD) == "bar"
    assert get_unit_symbol("pressure", UnitPreset.US) == "psia"
    assert get_unit_symbol("pressure", UnitPreset.COMMON) == "bar"

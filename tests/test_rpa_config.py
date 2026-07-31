"""Tests for safe RPA/libconfig import and export."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.io.rpa_config import (
    export_rpa_config,
    import_rpa_config_text,
    parse_rpa_config,
)
from engine.models import (
    ChemistryMode,
    InputParameters,
    NozzleContourMethod,
)


RPA_CASE = r'''
// Representative RPA 2.3 liquid-engine case.
version = 1.2;
name = "Reference";
info = "round-trip test";
generalOptions : { multiphase = true; ions = true; };
combustionChamberConditions :
{
  pressure : { value = 70.0; unit = "bar"; };
};
nozzleFlow :
{
  calculateNozzleFlow = true;
  freezingConditions : { calculate = true; expansionRatio = 3.0; };
  nozzleInletConditions : { contractionAreaRatio = 3.4; };
  nozzleExitConditions : { areaRatio = 25.0; supersonic = true; };
  nozzleStations = ( );
};
propellant :
{
  components :
  {
    ratio : { value = 6.0; unit = "O/F"; };
    oxidizer = (
      { name = "O2(L)"; massFraction = 1.0; }
    );
    fuel = (
      { name = "H2(L)"; massFraction = 1.0; }
    );
  };
};
engineSize :
{
  thrust : { value = 100.0; unit = "kN"; };
  ambientConditions : { value = 1.0; unit = "atm"; };
  chambersNo = 1;
  chamberGeometry :
  {
    length : { value = 1.0; unit = "m"; };
    characteristicLength = true;
    contractionAngle = 35.0;
    R1_to_Rt_ratio = 1.5;
    Rn_to_Rt_ratio = 0.382;
    TOC = true;
  };
};
propelantFeedSystem : { };
'''


def test_parse_rpa_config_handles_blocks_sequences_and_comments() -> None:
    parsed = parse_rpa_config(RPA_CASE)

    assert parsed["name"] == "Reference"
    assert parsed["generalOptions"]["multiphase"] is True
    assert parsed["nozzleFlow"]["nozzleStations"] == []
    assert parsed["propellant"]["components"]["oxidizer"][0]["name"] == "O2(L)"


def test_import_rpa_config_maps_units_propellants_and_freezing() -> None:
    result = import_rpa_config_text(RPA_CASE)
    inputs = result.inputs

    assert inputs.chamber_pressure_pa == 7.0e6
    assert inputs.thrust_n == 100_000.0
    assert inputs.ambient_pressure_pa == 101_325.0
    assert inputs.oxidizer == "LOX"
    assert inputs.fuel == "LH2"
    assert inputs.chemistry_mode is ChemistryMode.FROZEN_AT_THROAT
    assert inputs.contraction_ratio == 3.4
    assert inputs.expansion_ratio == 25.0
    assert inputs.characteristic_length_m == 1.0
    assert any("A/At=3" in warning for warning in result.warnings)
    assert any("TOC" in warning for warning in result.warnings)


def test_import_uses_throat_diameter_sizing_fallback() -> None:
    text = RPA_CASE.replace(
        'thrust : { value = 100.0; unit = "kN"; };',
        'throatDiameter : { value = 100.0; unit = "mm"; };',
    )

    result = import_rpa_config_text(text)

    expected_area = pytest.approx(3.141592653589793 * 0.05**2)
    assert result.inputs.thrust_n / (1.5 * 7.0e6) == expected_area
    assert result.inputs.throat_upstream_radius_m == pytest.approx(1.5 * 0.05)
    assert result.inputs.throat_downstream_radius_m == pytest.approx(0.382 * 0.05)
    assert any("throat diameter" in warning for warning in result.warnings)


def test_exported_rpa_config_is_parseable_and_round_trips_core_inputs(
    tmp_path: Path,
) -> None:
    inputs = InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=9.0e6,
        thrust_n=150_000.0,
        mixture_ratio=2.7,
        expansion_ratio=30.0,
        ambient_pressure_pa=45_000.0,
        contraction_ratio=3.2,
        characteristic_length_m=1.15,
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        contour_method=NozzleContourMethod.BELL,
        bell_length_fraction_percent=80.0,
        convergent_half_angle_deg=37.0,
    )

    path = export_rpa_config(inputs, tmp_path / "case.cfg", case_name="Round Trip")
    imported = import_rpa_config_text(path.read_text(encoding="utf-8"))

    assert path.exists()
    assert imported.case_name == "Round Trip"
    assert imported.inputs.fuel == inputs.fuel
    assert imported.inputs.oxidizer == inputs.oxidizer
    assert imported.inputs.chamber_pressure_pa == pytest.approx(inputs.chamber_pressure_pa)
    assert imported.inputs.thrust_n == pytest.approx(inputs.thrust_n)
    assert imported.inputs.mixture_ratio == pytest.approx(inputs.mixture_ratio)
    assert imported.inputs.expansion_ratio == pytest.approx(inputs.expansion_ratio)
    assert imported.inputs.ambient_pressure_pa == pytest.approx(inputs.ambient_pressure_pa)
    assert imported.inputs.characteristic_length_m == pytest.approx(
        inputs.characteristic_length_m
    )


def test_parser_rejects_executable_or_unknown_syntax() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        parse_rpa_config('name = __import__("os").system("whoami");')


def test_import_reports_mixture_model_as_explicitly_unsupported() -> None:
    text = RPA_CASE.replace(
        """components :
  {
    ratio : { value = 6.0; unit = "O/F"; };
    oxidizer = (
      { name = "O2(L)"; massFraction = 1.0; }
    );
    fuel = (
      { name = "H2(L)"; massFraction = 1.0; }
    );
  };""",
        """mixture :
  {
    species = (
      { name = "H2O2(L)"; massFraction = 1.0; }
    );
  };""",
    )

    with pytest.raises(ValueError, match="monopropellant/solid-mixture"):
        import_rpa_config_text(text)

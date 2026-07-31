"""RPA propellant-feed-system mapping tests."""

from __future__ import annotations

import pytest

from engine.cycle import CycleType, cycle_seed_from_rpa_config
from engine.io.rpa_config import parse_rpa_config


RPA_CYCLE = r'''
propelantFeedSystem :
{
  turbopumpFeedSystem :
  {
    cycle = "gas generator";
    oxidizerFeedSystem :
    {
      inletPressure : { value = 0.7; unit = "MPa"; };
      inletVelocity : { value = 5.0; unit = "m/s"; };
      pumpEfficiency = 0.74;
      valvePressureDrop : { value = 0.5; unit = "MPa"; };
      injectorPressureDrop : { value = 0.6; unit = "MPa"; };
      branches = ( );
    };
    fuelFeedSystem :
    {
      inletPressure : { value = 0.3; unit = "MPa"; };
      inletVelocity : { value = 8.0; unit = "m/s"; };
      pumpEfficiency = 0.68;
      coolingPressureDrop : { value = 5.0; unit = "MPa"; };
      injectorPressureDrop : { value = 0.5; unit = "MPa"; };
      boosterPump :
      {
        inletPressure : { value = 0.2; unit = "MPa"; };
        dischargePressure : { value = 1.0; unit = "MPa"; };
        pumpEfficiency = 0.6;
        hydraulicTurbine = true;
        turbinePressureRatio = 1.2;
        turbineEfficiency = 0.65;
        rotationalSpeed : { value = 9000; unit = "rpm"; };
      };
      branches = ( { name = "bleed"; relativeMassFlow = 0.01; } );
    };
    gasGenerators = (
      {
        ggType = "fuel-rich";
        pressure : { value = 8.0; unit = "MPa"; };
        sigma = 0.9;
        maxTemperature : { value = 900.0; unit = "K"; };
      }
    );
    turbines = (
      {
        ggType = "serial";
        turbinePressureRatio = 12.0;
        turbineEfficiency = 0.7;
        rotationalSpeed : { value = 12600; unit = "rpm"; };
      }
    );
  };
  estimateDryMass = true;
};
'''


def test_rpa_cycle_seed_maps_topology_pumps_devices_and_turbines() -> None:
    seed = cycle_seed_from_rpa_config(parse_rpa_config(RPA_CYCLE))

    assert seed is not None
    assert seed.cycle_type is CycleType.GAS_GENERATOR
    assert seed.oxidizer_pump.inlet_pressure_pa == pytest.approx(0.7e6)
    assert seed.oxidizer_pump.known_main_path_pressure_drop_pa == pytest.approx(1.1e6)
    assert seed.fuel_pump.cooling_pressure_drop_pa == pytest.approx(5.0e6)
    assert seed.fuel_pump.booster_pump is not None
    assert seed.fuel_pump.booster_pump.hydraulic_turbine
    assert seed.fuel_pump.branch_count == 1
    assert seed.combustion_devices[0].maximum_temperature_k == 900.0
    assert seed.turbines[0].pressure_ratio == 12.0
    assert seed.turbines[0].rotational_speed_rpm == 12_600.0
    assert seed.estimate_dry_mass
    assert len(seed.warnings) == 2


def test_rpa_cycle_seed_returns_none_without_turbopump_block() -> None:
    assert cycle_seed_from_rpa_config({"propelantFeedSystem": {}}) is None

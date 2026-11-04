"""Generate bounded offline cooling transport data using real CEA and CoolProp.

Run from repo root:
    .venv/Scripts/python.exe -m pip install CoolProp==8.0.0
    .venv/Scripts/python.exe lite/tools/generate_cooling_data.py

This is n-dodecane, NOT actual RP-1. No fallback or extrapolation is used.
The existing property adapter is used only for comparison at its original knots;
its endpoint-clamping behavior is deliberately not used for this new grid.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import CoolProp.CoolProp as CP
from engine.chemistry.rocketcea_backend import RocketCEABackend
from engine.models import InputParameters, ChemistryMode
from engine.properties.property_tables import get_coolant_properties

FLUID = "HEOS::n-Dodecane"
GAS_COLUMNS = ["cpJkgK", "muPaS", "prandtl", "gamma", "kWmK", "tcK", "cpFrozenJkgK", "prandtlFrozen", "kFrozenWmK", "gammaFrozen"]
COOLANT_COLUMNS = ["rhoKgM3", "cpJkgK", "muPaS", "kWmK", "hJkg"]
T_AXIS = [288.0, 293.15] + list(range(300, 631, 10)) + [633.0]
P_AXIS = [1, 2, 5, 10, 15, 20, 30, 40, 50, 60, 80, 100, 125, 150, 200]
ALLOWED_PHASES = {"liquid", "supercritical_liquid"}


def coolant_row(temperature: float, pressure_bar: float):
    phase = CP.PhaseSI("T", temperature, "P", pressure_bar * 1e5, FLUID)
    if phase not in ALLOWED_PHASES:
        return None, phase
    row = [float(CP.PropsSI(key, "T", temperature, "P", pressure_bar * 1e5, FLUID))
           for key in ["Dmass", "Cpmass", "viscosity", "conductivity", "Hmass"]]
    if not all(math.isfinite(value) for value in row) or not all(value > 0 for value in row[:4]):
        raise RuntimeError(f"Nonphysical properties at {temperature} K, {pressure_bar} bar")
    return row, phase


def gas_row(backend, pc, of):
    state = backend.calculate(InputParameters(
        fuel="RP-1", oxidizer="LOX", chamber_pressure_pa=pc * 1e5,
        thrust_n=10000, mixture_ratio=of, expansion_ratio=20,
        ambient_pressure_pa=0,
    ))
    row = [state.cp_j_per_kg_k, state.viscosity_pa_s, state.prandtl_number,
           state.gamma, state.thermal_conductivity_w_per_m_k, state.chamber_temperature_k]
    frozen = backend.calculate(InputParameters(
        fuel="RP-1", oxidizer="LOX", chamber_pressure_pa=pc * 1e5,
        thrust_n=10000, mixture_ratio=of, expansion_ratio=20,
        ambient_pressure_pa=0, chemistry_mode=ChemistryMode.FROZEN,
    ))
    fixed_composition_gas_constant = 8.31446261815324 / frozen.molecular_weight_kg_per_mol
    gamma_frozen = frozen.cp_j_per_kg_k / (frozen.cp_j_per_kg_k - fixed_composition_gas_constant)
    row.extend([frozen.cp_j_per_kg_k, frozen.prandtl_number, frozen.thermal_conductivity_w_per_m_k, gamma_frozen])
    if not all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0 for value in row):
        raise RuntimeError(f"Missing CEA transport properties at pc={pc}, OF={of}")
    return row


def main():
    thermo = json.loads((ROOT / "lite/public/thermo.json").read_text(encoding="utf-8"))
    pc_axis, of_axis = thermo["axes"]["pcBar"], thermo["axes"]["of"]
    backend = RocketCEABackend()
    if not backend.is_available:
        raise RuntimeError("Real RocketCEA is required; no synthetic fallback.")
    gas_values = [[gas_row(backend, pc, of) for of in of_axis] for pc in pc_axis]
    gas_errors = [0.0] * len(GAS_COLUMNS)
    gas_midpoints = 0
    for i in range(len(pc_axis) - 1):
        for j in range(len(of_axis) - 1):
            truth = gas_row(backend, (pc_axis[i] + pc_axis[i + 1]) / 2, (of_axis[j] + of_axis[j + 1]) / 2)
            mean = [sum(gas_values[i+di][j+dj][field] for di in [0, 1] for dj in [0, 1]) / 4
                    for field in range(len(GAS_COLUMNS))]
            gas_errors = [max(old, abs(approx/exact - 1)) for old, approx, exact in zip(gas_errors, mean, truth)]
            gas_midpoints += 1

    coolant_values, phases = [], []
    for temperature in T_AXIS:
        row_values, row_phases = [], []
        for pressure in P_AXIS:
            row, phase = coolant_row(temperature, pressure)
            row_values.append(row)
            row_phases.append(phase)
        coolant_values.append(row_values)
        phases.append(row_phases)

    coolant_errors = [0.0] * 4
    enthalpy_absolute_error = 0.0
    enthalpy_cell_scaled_error = 0.0
    coolant_midpoints = 0
    for i in range(len(T_AXIS) - 1):
        for j in range(len(P_AXIS) - 1):
            corners = [coolant_values[i+di][j+dj] for di in [0, 1] for dj in [0, 1]]
            if any(row is None for row in corners):
                continue
            truth, phase = coolant_row((T_AXIS[i] + T_AXIS[i+1]) / 2, (P_AXIS[j] + P_AXIS[j+1]) / 2)
            if truth is None:
                raise RuntimeError("An accepted interpolation cell crosses the liquid boundary.")
            mean = [sum(row[field] for row in corners) / 4 for field in range(5)]
            coolant_errors = [max(old, abs(approx/exact - 1)) for old, approx, exact in zip(coolant_errors, mean[:4], truth[:4])]
            dh = abs(mean[4] - truth[4])
            enthalpy_absolute_error = max(enthalpy_absolute_error, dh)
            enthalpy_cell_scaled_error = max(enthalpy_cell_scaled_error, dh / (truth[1] * (T_AXIS[i+1] - T_AXIS[i])))
            coolant_midpoints += 1

    legacy_checks = []
    for temperature, pressure in [(293.15, 50), (373.15, 100), (573.15, 100)]:
        old = get_coolant_properties("RP1_SURROGATE_N_DODECANE", temperature, pressure * 1e5)
        if old.source != "table" or not old.valid or "clamped" in old.note or "fallback" in old.note:
            raise RuntimeError("Legacy comparison unexpectedly used a fallback or clamped lookup.")
        current, _ = coolant_row(temperature, pressure)
        previous = [old.density_kg_per_m3, old.cp_j_per_kg_k, old.viscosity_pa_s, old.thermal_conductivity_w_per_m_k, old.enthalpy_j_per_kg]
        legacy_checks.append({"temperatureK": temperature, "pressureBar": pressure,
                              "maxRelativeDifferenceFirstFourProperties": max(abs(a/b-1) for a, b in zip(current[:4], previous[:4]))})

    payload = {
        "format": "astroforge-cooling-data", "version": 1,
        "source": f"RocketCEA {importlib.metadata.version('rocketcea')} via repository backend; CoolProp {importlib.metadata.version('CoolProp')} HEOS n-dodecane",
        "generator": "lite/tools/generate_cooling_data.py",
        "gas": {
            "axes": {"pcBar": pc_axis, "of": of_axis}, "columns": GAS_COLUMNS, "values": gas_values,
            "units": ["J/(kg K)", "Pa s", "1", "1", "W/(m K)", "K", "J/(kg K)", "1", "W/(m K)", "1"],
            "chemistry": "equilibrium", "chamberModel": "infinite-area", "reactants": thermo["reactants"],
            "source": "Real LOX/RP-1 RocketCEA chamber transport; SI conversion in repository RocketCEABackend",
            "domain": {"pcBar": [min(pc_axis), max(pc_axis)], "of": [min(of_axis), max(of_axis)]},
            "validity": "Chamber transport is independent of expansion ratio. Not local nozzle transport; a thermal correlation using these properties remains an approximation.",
            "frozenTransport": "cpFrozenJkgK, prandtlFrozen and kFrozenWmK come from CEA get_Chamber_Transport(frozen=1) through the repository backend. muPaS is common to both modes. gammaFrozen is derived as cpFrozen/(cpFrozen-R), R=universal gas constant/chamber molecular weight, for a fixed-composition calorically-perfect local-flow approximation. Equilibrium chamber gamma and transport remain separately available; model selection must be explicit.",
            "validation": {"method": "direct CEA versus bilinear interpolation at every pc/OF cell midpoint", "sampleCount": gas_midpoints, "maxSampledRelativeError": dict(zip(GAS_COLUMNS, gas_errors)), "limitation": "Sampled interpolation errors, not a global bound or experimental validation."},
        },
        "coolant": {
            "id": "RP1_SURROGATE_N_DODECANE", "displayName": "RP-1 surrogate: n-dodecane (not actual RP-1)",
            "fluid": "n-Dodecane", "cas": "112-40-3", "surrogate": True,
            "axes": {"temperatureK": T_AXIS, "pressureBar": P_AXIS}, "columns": COOLANT_COLUMNS,
            "values": coolant_values, "phases": phases,
            "units": ["kg/m3", "J/(kg K)", "Pa s", "W/(m K)", "J/kg"],
            "domain": {"temperatureK": [min(T_AXIS), max(T_AXIS)], "pressureBar": [min(P_AXIS), max(P_AXIS)]},
            "criticalTemperatureK": CP.PropsSI("Tcrit", "n-Dodecane"), "criticalPressureBar": CP.PropsSI("pcrit", "n-Dodecane") / 1e5,
            "source": f"CoolProp {importlib.metadata.version('CoolProp')} HEOS::n-Dodecane; freshly evaluated, no reference-data clamping",
            "validity": {"allowedPhases": sorted(ALLOWED_PHASES), "invalidCells": "null", "interpolation": "bilinear T,p only when all nonzero-weight corner states are valid; no extrapolation", "phaseBoundary": "No interpolation across null/vapor states. Valid rectangular cells stay on the dense-liquid side of the saturation boundary.", "enthalpy": "Absolute values depend on reference state and can be negative; use differences. cp is the EOS derivative at constant pressure.", "limitations": ["Single-component n-dodecane is not an RP-1 mixture model or qualified RP-1 data.", "No pyrolysis, coking, boiling or two-phase transport model.", "Not an official NIST or REFPROP export."]},
            "validation": {"method": "direct CoolProp versus bilinear interpolation at each fully valid cell midpoint", "sampleCount": coolant_midpoints, "maxSampledRelativeError": dict(zip(COOLANT_COLUMNS[:4], coolant_errors)), "maxSampledEnthalpyAbsoluteErrorJkg": enthalpy_absolute_error, "maxSampledEnthalpyErrorOverCpDeltaT": enthalpy_cell_scaled_error, "legacyPropertyAdapterKnotComparisons": legacy_checks, "limitation": "Interpolation checks only; no evidence of RP-1 surrogate accuracy."},
        },
        "references": [
            {"title": "RocketCEA transport API", "url": "https://rocketcea.readthedocs.io/en/stable/functions.html"},
            {"title": "CoolProp n-dodecane EOS and transport references", "url": "https://coolprop.org/fluid_properties/fluids/n-Dodecane.html"},
            {"title": "Lemmon and Huber, Thermodynamic Properties of n-Dodecane (2004)", "url": "https://doi.org/10.1021/ef0341062"},
            {"title": "Huber, Laesecke and Perkins, Transport Properties of n-Dodecane (2004)", "url": "https://doi.org/10.1021/ef034109e"},
            {"title": "NIST RP-1 surrogate mixture research: distinct from this single-component proxy", "url": "https://www.nist.gov/publications/preliminary-surrogate-mixture-models-thermophysical-properties-rocket-propellants-rp-1"},
        ],
        "provenance": {
            "legacyPropertyTableSha256": hashlib.sha256((ROOT / "data/properties/propellant_property_tables_nist_style.json").read_bytes()).hexdigest(),
            "ceaBackendSha256": hashlib.sha256((ROOT / "engine/chemistry/rocketcea_backend.py").read_bytes()).hexdigest(),
        },
    }
    target = ROOT / "lite/public/cooling-data.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(json.dumps({"file": str(target), "gasStates": len(pc_axis) * len(of_axis), "coolantStates": sum(row is not None for rows in coolant_values for row in rows), "gasValidation": payload["gas"]["validation"], "coolantValidation": payload["coolant"]["validation"]}, indent=2))


if __name__ == "__main__":
    main()

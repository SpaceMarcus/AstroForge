"""Generate the browser's bounded ideal LOX/RP-1 thermochemistry table.

Run from the repository root with .venv/Scripts/python.exe lite/tools/generate_thermo.py.
No extrapolation is permitted by the browser solver. This table uses the existing
RocketCEA adapter with infinite-area chamber equilibrium chemistry; geometric
contraction ratio in Lite is not a finite-area chemistry correction.
"""
from __future__ import annotations

import importlib.metadata
import json
import math
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine.chemistry.rocketcea_backend import RocketCEABackend
from engine.models import InputParameters


def main():
    backend = RocketCEABackend()
    if not backend.is_available:
        raise RuntimeError("A real RocketCEA installation is required; no synthetic fallback.")
    from rocketcea.input_cards import fuelCards, oxCards
    reactants = {}
    for role, name, cards in [("fuel", "RP_1", fuelCards), ("oxidizer", "LOX", oxCards)]:
        card = " ".join(cards[name])
        match = re.search(r"t\(k\)\s*=\s*([\d.]+)", card, re.IGNORECASE)
        if not match:
            raise RuntimeError(f"Cannot identify reactant temperature for {name}")
        reactants[role] = {"cardName": name, "temperatureK": float(match.group(1)), "card": card.strip()}
    axes = {"pcBar": [10,20,30,40,50,60,70,80], "of": [2,2.2,2.4,2.6,2.8,3,3.2], "eps": [4,6,10,15,20,30,40]}
    values = []
    for pc in axes["pcBar"]:
        for mr in axes["of"]:
            for eps in axes["eps"]:
                result = backend.calculate(InputParameters(fuel="RP-1", oxidizer="LOX", chamber_pressure_pa=pc*1e5, thrust_n=10000, mixture_ratio=mr, expansion_ratio=eps, ambient_pressure_pa=0))
                values.append([result.c_star_m_s, result.cf_vac, result.chamber_temperature_k, result.exit_pressure_pa / 1e5])
    # Independent off-grid CEA calls quantify sampled interpolation error.
    # Midpoints are validation samples, not a rigorous global error bound.
    max_errors = [0.0] * 4
    midpoint_count = 0
    for i in range(len(axes["pcBar"])-1):
        for j in range(len(axes["of"])-1):
            for k in range(len(axes["eps"])-1):
                pc, mr, eps = [(axes[key][idx]+axes[key][idx+1])/2 for key, idx in [("pcBar", i), ("of", j), ("eps", k)]]
                ref = backend.calculate(InputParameters(fuel="RP-1", oxidizer="LOX", chamber_pressure_pa=pc*1e5, thrust_n=10000, mixture_ratio=mr, expansion_ratio=eps, ambient_pressure_pa=0))
                truth = [ref.c_star_m_s, ref.cf_vac, ref.chamber_temperature_k, ref.exit_pressure_pa/1e5]
                estimated = [0.0]*4
                log_ratio = 0.0
                ew = math.log(eps/axes["eps"][k])/math.log(axes["eps"][k+1]/axes["eps"][k])
                for di in [0,1]:
                    for dj in [0,1]:
                        for dk in [0,1]:
                            row = values[((i+di)*len(axes["of"])+j+dj)*len(axes["eps"])+k+dk]
                            for field in range(3):
                                estimated[field] += row[field]/8
                            log_ratio += math.log(row[3]/axes["pcBar"][i+di])*.25*(ew if dk else 1-ew)
                estimated[3] = pc*math.exp(log_ratio)
                max_errors = [max(old, abs(value/exact-1)) for old, value, exact in zip(max_errors, estimated, truth)]
                midpoint_count += 1
    payload = {
        "format": "astroforge-thermo-grid", "version": 1,
        "source": "RocketCEA " + importlib.metadata.version("rocketcea") + " via AstraForge RocketCEABackend",
        "propellants": "LOX/RP-1", "chemistry": "equilibrium", "chamberModel": "infinite-area",
        "reactants": reactants,
        "interpolation": "c*, Cf, Tc trilinear; log(pe/pc) linear in pc, O/F and log(eps); no extrapolation", "axes": axes,
        "fields": ["cstarMS", "cfVac", "tcK", "peBar"], "values": values,
        "validation": {"method": "direct CEA at every grid-cell midpoint", "sampleCount": midpoint_count, "maxSampledRelativeError": dict(zip(["cstarMS", "cfVac", "tcK", "peBar"], max_errors)), "limitation": "Sampled interpolation agreement only; not a rigorous global bound or experimental validation."},
        "notes": ["Ideal performance, no combustion/friction/divergence losses.", "Geometry contraction ratio does not modify the infinite-area chemistry table."]
    }
    out = ROOT / "lite/public/thermo.json"
    out.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"Generated {len(values)} real CEA states in {out.name}")


if __name__ == "__main__":
    main()

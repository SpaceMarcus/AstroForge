"""RocketCEA backend implementation.

All RocketCEA-specific API assumptions are intentionally localized in this
module so the rest of the project only depends on the abstract backend
interface and SI-based domain models.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from typing import Any

from engine.chemistry.base import (
    ThermochemistryBackend,
    ThermochemistryBackendError,
    ThermochemistryBackendUnavailableError,
)
from engine.models import (
    ChemistryMode,
    InputParameters,
    OFSweepPoint,
    OFSweepResult,
    ThermochemistryResult,
    ThermochemistryState,
)
from engine.utils.validation import ensure_valid_input

PSIA_TO_PA = 6_894.757293168
FT_TO_M = 0.3048
DEGR_TO_K = 5.0 / 9.0
LBM_PER_CUFT_TO_KG_PER_M3 = 16.01846337396014
BTU_PER_LBM_R_TO_J_PER_KG_K = 4_186.8
MILLIPOISE_TO_PA_S = 1.0e-4
MCAL_PER_CMKS_TO_W_PER_MK = 0.4184
LBM_PER_LBMOL_TO_KG_PER_MOL = 1.0e-3
BTU_PER_LBM_TO_J_PER_KG = 2_326.0
STANDARD_GRAVITY = 9.80665


@dataclass(frozen=True, slots=True)
class _ModeFlags:
    frozen: int
    frozen_at_throat: int


class RocketCEABackend(ThermochemistryBackend):
    """RocketCEA-backed thermochemistry provider."""

    def __init__(self) -> None:
        self._cea_cls: type[Any] | None = None
        self._import_error: Exception | None = None

        try:
            with contextlib.redirect_stdout(io.StringIO()):
                from rocketcea.cea_obj import CEA_Obj
        except Exception as exc:  # pragma: no cover - depends on local install
            self._import_error = exc
        else:
            self._cea_cls = CEA_Obj

    @property
    def is_available(self) -> bool:
        """Return whether RocketCEA could be imported successfully."""

        return self._cea_cls is not None

    def calculate(self, inputs: InputParameters) -> ThermochemistryResult:
        """Calculate thermochemistry for a validated input set."""

        ensure_valid_input(inputs)
        pc_psia = inputs.chamber_pressure_pa / PSIA_TO_PA
        pa_psia = inputs.ambient_pressure_pa / PSIA_TO_PA
        flags = self._mode_flags(inputs.chemistry_mode)
        cea = self._build_cea(inputs)

        try:
            isp_vac_s, c_star_m_s, chamber_temperature_k = self._core_performance(
                cea=cea,
                pc_psia=pc_psia,
                inputs=inputs,
                flags=flags,
            )

            chamber_molecular_weight, chamber_gamma = cea.get_Chamber_MolWt_gamma(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
            )
            chamber_density = cea.get_Chamber_Density(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
            )
            densities = cea.get_Densities(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozen=flags.frozen,
                frozenAtThroat=flags.frozen_at_throat,
            )
            enthalpies = cea.get_Enthalpies(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozen=flags.frozen,
                frozenAtThroat=flags.frozen_at_throat,
            )
            heat_capacities = cea.get_HeatCapacities(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozen=flags.frozen,
                frozenAtThroat=flags.frozen_at_throat,
            )
            chamber_cp, chamber_viscosity, chamber_conductivity, chamber_prandtl = (
                cea.get_Chamber_Transport(
                    Pc=pc_psia,
                    MR=inputs.mixture_ratio,
                    eps=inputs.expansion_ratio,
                    frozen=flags.frozen,
                )
            )
            throat_cp, throat_viscosity, throat_conductivity, throat_prandtl = (
                cea.get_Throat_Transport(
                    Pc=pc_psia,
                    MR=inputs.mixture_ratio,
                    eps=inputs.expansion_ratio,
                    frozen=flags.frozen,
                )
            )
            exit_cp, exit_viscosity, exit_conductivity, exit_prandtl = cea.get_Exit_Transport(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozen=flags.frozen,
                frozenAtThroat=flags.frozen_at_throat,
            )
            throat_molecular_weight, throat_gamma = cea.get_Throat_MolWt_gamma(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozen=flags.frozen,
            )
            exit_molecular_weight, exit_gamma = cea.get_exit_MolWt_gamma(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozen=flags.frozen,
                frozenAtThroat=flags.frozen_at_throat,
            )
            temperatures = cea.get_Temperatures(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozen=flags.frozen,
                frozenAtThroat=flags.frozen_at_throat,
            )
            pc_over_pe = cea.get_PcOvPe(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozen=flags.frozen,
                frozenAtThroat=flags.frozen_at_throat,
            )
            optimal_expansion_ratio = self._optimal_expansion_ratio(
                cea=cea,
                pc_psia=pc_psia,
                pa_psia=pa_psia,
                inputs=inputs,
                flags=flags,
            )
            isp_amb_s, cf_amb, ambient_mode = self._ambient_performance(
                cea=cea,
                pc_psia=pc_psia,
                pa_psia=pa_psia,
                c_star_m_s=c_star_m_s,
                inputs=inputs,
                flags=flags,
            )
            species_summary, species_notes = self._species_summary(
                cea=cea,
                pc_psia=pc_psia,
                inputs=inputs,
                flags=flags,
            )
            chamber_mach = self._chamber_mach_number(
                cea=cea,
                pc_psia=pc_psia,
                inputs=inputs,
            )
            station_states = self._build_station_states(
                inputs=inputs,
                temperatures=temperatures,
                densities=densities,
                enthalpies=enthalpies,
                heat_capacities=heat_capacities,
                chamber_transport=(
                    chamber_cp,
                    chamber_viscosity,
                    chamber_conductivity,
                    chamber_prandtl,
                ),
                throat_transport=(
                    throat_cp,
                    throat_viscosity,
                    throat_conductivity,
                    throat_prandtl,
                ),
                exit_transport=(
                    exit_cp,
                    exit_viscosity,
                    exit_conductivity,
                    exit_prandtl,
                ),
                chamber_gamma=chamber_gamma,
                chamber_molecular_weight=chamber_molecular_weight,
                throat_gamma=throat_gamma,
                throat_molecular_weight=throat_molecular_weight,
                exit_gamma=exit_gamma,
                exit_molecular_weight=exit_molecular_weight,
                chamber_mach=chamber_mach,
                exit_mach=cea.get_MachNumber(
                    Pc=pc_psia,
                    MR=inputs.mixture_ratio,
                    eps=inputs.expansion_ratio,
                    frozen=flags.frozen,
                    frozenAtThroat=flags.frozen_at_throat,
                ),
                species_summary=species_summary,
            )
        except ThermochemistryBackendError:
            raise
        except Exception as exc:  # pragma: no cover - depends on RocketCEA runtime
            raise ThermochemistryBackendError(
                f"RocketCEA could not evaluate the requested case: {exc}"
            ) from exc

        notes = [
            "Gamma, molecular weight and transport properties refer to chamber conditions.",
            "RocketCEA values are used directly and converted to SI units only inside this module.",
            (
                "Adiabatic wall temperature and boundary-layer thickness values are derived later "
                "from local profile states with a simple turbulent boundary-layer approximation."
            ),
        ]
        if ambient_mode is not None:
            notes.append(f"Ambient nozzle mode reported by RocketCEA: {ambient_mode}")
        notes.extend(species_notes)

        cf_vac = isp_vac_s * STANDARD_GRAVITY / c_star_m_s
        exit_pressure_pa = (
            inputs.chamber_pressure_pa / pc_over_pe if pc_over_pe and pc_over_pe > 0.0 else None
        )
        exit_temperature_k = temperatures[2] * DEGR_TO_K if len(temperatures) >= 3 else None

        return ThermochemistryResult(
            chemistry_mode=inputs.chemistry_mode,
            propellant_description=cea.get_description(),
            chamber_temperature_k=chamber_temperature_k,
            c_star_m_s=c_star_m_s,
            isp_vac_s=isp_vac_s,
            isp_amb_s=isp_amb_s,
            cf_vac=cf_vac,
            cf_amb=cf_amb,
            gamma=chamber_gamma,
            molecular_weight_kg_per_mol=(
                chamber_molecular_weight * LBM_PER_LBMOL_TO_KG_PER_MOL
            ),
            cp_j_per_kg_k=chamber_cp * BTU_PER_LBM_R_TO_J_PER_KG_K,
            viscosity_pa_s=chamber_viscosity * MILLIPOISE_TO_PA_S,
            thermal_conductivity_w_per_m_k=(
                chamber_conductivity * MCAL_PER_CMKS_TO_W_PER_MK
            ),
            prandtl_number=chamber_prandtl,
            chamber_density_kg_per_m3=chamber_density * LBM_PER_CUFT_TO_KG_PER_M3,
            exit_pressure_pa=exit_pressure_pa,
            exit_temperature_k=exit_temperature_k,
            optimal_expansion_ratio=optimal_expansion_ratio,
            species_mass_fractions=species_summary.get("exit_mass", {}),
            species_mole_fractions=species_summary.get("exit_mole", {}),
            species_summary=species_summary,
            station_states=station_states,
            notes=notes,
        )

    def estimate_ambient_matched_expansion_ratio(
        self,
        inputs: InputParameters,
    ) -> float | None:
        """Return a preliminary ambient-matched expansion ratio from RocketCEA when possible."""

        ensure_valid_input(inputs)
        pc_psia = inputs.chamber_pressure_pa / PSIA_TO_PA
        pa_psia = inputs.ambient_pressure_pa / PSIA_TO_PA
        flags = self._mode_flags(inputs.chemistry_mode)
        cea = self._build_cea(inputs)
        return self._optimal_expansion_ratio(
            cea=cea,
            pc_psia=pc_psia,
            pa_psia=pa_psia,
            inputs=inputs,
            flags=flags,
        )

    def build_of_sweep(
        self,
        inputs: InputParameters,
        *,
        sample_count: int = 41,
    ) -> OFSweepResult:
        """Return an O/F sweep for the selected propellant pair and chemistry mode."""

        ensure_valid_input(inputs)
        if sample_count < 5:
            raise ThermochemistryBackendError("The O/F sweep requires at least 5 sample points.")

        cea = self._build_cea(inputs)
        pc_psia = inputs.chamber_pressure_pa / PSIA_TO_PA
        flags = self._mode_flags(inputs.chemistry_mode)

        try:
            stoichiometric_mixture_ratio = float(cea.getMRforER(ERphi=1.0))
        except Exception:
            stoichiometric_mixture_ratio = None

        lower_mr, upper_mr = self._default_sweep_bounds(
            current_mixture_ratio=inputs.mixture_ratio,
            stoichiometric_mixture_ratio=stoichiometric_mixture_ratio,
        )

        points: list[OFSweepPoint] = []
        try:
            for index in range(sample_count):
                fraction = index / (sample_count - 1)
                mixture_ratio = lower_mr + fraction * (upper_mr - lower_mr)
                isp_vac_s, c_star_m_s, chamber_temperature_k = self._core_performance(
                    cea=cea,
                    pc_psia=pc_psia,
                    inputs=InputParameters(
                        fuel=inputs.fuel,
                        oxidizer=inputs.oxidizer,
                        chamber_pressure_pa=inputs.chamber_pressure_pa,
                        thrust_n=inputs.thrust_n,
                        mixture_ratio=mixture_ratio,
                        expansion_ratio=inputs.expansion_ratio,
                        ambient_pressure_pa=inputs.ambient_pressure_pa,
                        contraction_ratio=inputs.contraction_ratio,
                        characteristic_length_m=inputs.characteristic_length_m,
                        chemistry_mode=inputs.chemistry_mode,
                        contour_method=inputs.contour_method,
                    ),
                    flags=flags,
                )
                equivalence_ratio = (
                    stoichiometric_mixture_ratio / mixture_ratio
                    if stoichiometric_mixture_ratio is not None and mixture_ratio > 0.0
                    else None
                )
                points.append(
                    OFSweepPoint(
                        mixture_ratio=mixture_ratio,
                        equivalence_ratio=equivalence_ratio,
                        c_star_m_s=c_star_m_s,
                        isp_vac_s=isp_vac_s,
                        chamber_temperature_k=chamber_temperature_k,
                        is_fuel_rich=(
                            stoichiometric_mixture_ratio is not None
                            and mixture_ratio < stoichiometric_mixture_ratio
                        ),
                        is_oxidizer_rich=(
                            stoichiometric_mixture_ratio is not None
                            and mixture_ratio > stoichiometric_mixture_ratio
                        ),
                    )
                )
        except Exception as exc:  # pragma: no cover - depends on RocketCEA runtime
            raise ThermochemistryBackendError(
                f"RocketCEA could not build the requested O/F sweep: {exc}"
            ) from exc

        peak_isp_point = max(points, key=lambda point: point.isp_vac_s)
        peak_c_star_point = max(points, key=lambda point: point.c_star_m_s)

        return OFSweepResult(
            fuel=inputs.fuel,
            oxidizer=inputs.oxidizer,
            chemistry_mode=inputs.chemistry_mode,
            chamber_pressure_pa=inputs.chamber_pressure_pa,
            expansion_ratio=inputs.expansion_ratio,
            stoichiometric_mixture_ratio=stoichiometric_mixture_ratio,
            peak_isp_vac_mixture_ratio=peak_isp_point.mixture_ratio,
            peak_c_star_mixture_ratio=peak_c_star_point.mixture_ratio,
            points=points,
        )

    def _build_cea(self, inputs: InputParameters) -> Any:
        cea_cls = self._require_backend()
        with contextlib.redirect_stdout(io.StringIO()):
            return cea_cls(
                oxName=inputs.oxidizer,
                fuelName=inputs.fuel,
                fac_CR=inputs.contraction_ratio,
            )

    def _require_backend(self) -> type[Any]:
        if self._cea_cls is None:
            detail = ""
            if self._import_error is not None:
                detail = f" Original import error: {self._import_error}"
            raise ThermochemistryBackendUnavailableError(
                "RocketCEA is not installed or could not be imported. "
                "Please install RocketCEA locally to evaluate thermochemistry."
                f"{detail}"
            )
        return self._cea_cls

    @staticmethod
    def _mode_flags(mode: ChemistryMode) -> _ModeFlags:
        if mode is ChemistryMode.EQUILIBRIUM:
            return _ModeFlags(frozen=0, frozen_at_throat=0)
        if mode is ChemistryMode.FROZEN:
            return _ModeFlags(frozen=1, frozen_at_throat=0)
        if mode is ChemistryMode.FROZEN_AT_THROAT:
            return _ModeFlags(frozen=1, frozen_at_throat=1)
        raise ThermochemistryBackendError(f"Unsupported chemistry mode: {mode}")

    @staticmethod
    def _core_performance(
        cea: Any,
        pc_psia: float,
        inputs: InputParameters,
        flags: _ModeFlags,
    ) -> tuple[float, float, float]:
        """Return Isp_vac [s], c* [m/s], Tc [K]."""

        if inputs.chemistry_mode is ChemistryMode.EQUILIBRIUM:
            isp_vac_s, c_star_ft_s, chamber_temperature_deg_r = cea.get_IvacCstrTc(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozen=0,
                frozenAtThroat=0,
            )
        else:
            # RocketCEA documents getFrozen_IvacCstrTc specifically for frozen modes.
            isp_vac_s, c_star_ft_s, chamber_temperature_deg_r = cea.getFrozen_IvacCstrTc(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozenAtThroat=flags.frozen_at_throat,
            )

        return (
            float(isp_vac_s),
            float(c_star_ft_s) * FT_TO_M,
            float(chamber_temperature_deg_r) * DEGR_TO_K,
        )

    @staticmethod
    def _ambient_performance(
        cea: Any,
        pc_psia: float,
        pa_psia: float,
        c_star_m_s: float,
        inputs: InputParameters,
        flags: _ModeFlags,
    ) -> tuple[float | None, float | None, str | None]:
        """Return ambient Isp [s], ambient Cf [-] and RocketCEA nozzle mode."""

        ambient_mode: str | None = None
        isp_amb_s: float | None = None
        cf_amb: float | None = None

        if hasattr(cea, "estimate_Ambient_Isp"):
            isp_amb_candidate = cea.estimate_Ambient_Isp(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                Pamb=pa_psia,
                frozen=flags.frozen,
                frozenAtThroat=flags.frozen_at_throat,
            )
            if isinstance(isp_amb_candidate, tuple):
                isp_amb_s = float(isp_amb_candidate[0])
                if len(isp_amb_candidate) > 1:
                    ambient_mode = str(isp_amb_candidate[1])
            else:
                isp_amb_s = float(isp_amb_candidate)

        if flags.frozen:
            cf_result = cea.getFrozen_PambCf(
                Pamb=pa_psia,
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozenAtThroat=flags.frozen_at_throat,
            )
        else:
            cf_result = cea.get_PambCf(
                Pamb=pa_psia,
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
            )

        if isinstance(cf_result, tuple):
            if len(cf_result) >= 2:
                cf_amb = float(cf_result[1])
            elif len(cf_result) == 1:
                cf_amb = float(cf_result[0])
            if len(cf_result) >= 3:
                ambient_mode = str(cf_result[2])

        if isp_amb_s is None and cf_amb is not None:
            isp_amb_s = cf_amb * c_star_m_s / STANDARD_GRAVITY

        return isp_amb_s, cf_amb, ambient_mode

    @staticmethod
    def _optimal_expansion_ratio(
        *,
        cea: Any,
        pc_psia: float,
        pa_psia: float,
        inputs: InputParameters,
        flags: _ModeFlags,
    ) -> float | None:
        """Return the ambient-matched expansion ratio when RocketCEA can provide it."""

        if pa_psia <= 0.0:
            return None
        try:
            return float(
                cea.get_eps_at_PcOvPe(
                    Pc=pc_psia,
                    MR=inputs.mixture_ratio,
                    PcOvPe=pc_psia / pa_psia,
                    frozen=flags.frozen,
                    frozenAtThroat=flags.frozen_at_throat,
                )
            )
        except Exception:
            return None

    @staticmethod
    def _species_summary(
        cea: Any,
        pc_psia: float,
        inputs: InputParameters,
        flags: _ModeFlags,
    ) -> tuple[dict[str, dict[str, float]], list[str]]:
        """Return compact species summaries for GUI and export."""

        if not hasattr(cea, "get_SpeciesMassFractions") or not hasattr(
            cea, "get_SpeciesMoleFractions"
        ):
            return {}, ["This RocketCEA build does not expose a species summary."]

        try:
            _mass_mol_weights, mass_fractions = cea.get_SpeciesMassFractions(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozen=flags.frozen,
                frozenAtThroat=flags.frozen_at_throat,
            )
            _mole_mol_weights, mole_fractions = cea.get_SpeciesMoleFractions(
                Pc=pc_psia,
                MR=inputs.mixture_ratio,
                eps=inputs.expansion_ratio,
                frozen=flags.frozen,
                frozenAtThroat=flags.frozen_at_throat,
            )
        except Exception:
            return {}, ["Species data could not be read for this case."]

        summary = {
            "chamber_mass": RocketCEABackend._extract_station(mass_fractions, station_index=1),
            "throat_mass": RocketCEABackend._extract_station(mass_fractions, station_index=2),
            "exit_mass": RocketCEABackend._extract_station(mass_fractions, station_index=3),
            "chamber_mole": RocketCEABackend._extract_station(mole_fractions, station_index=1),
            "throat_mole": RocketCEABackend._extract_station(mole_fractions, station_index=2),
            "exit_mole": RocketCEABackend._extract_station(mole_fractions, station_index=3),
        }
        return summary, []

    @staticmethod
    def _build_station_states(
        *,
        inputs: InputParameters,
        temperatures: list[float],
        densities: list[float],
        enthalpies: list[float],
        heat_capacities: list[float],
        chamber_transport: tuple[float, float, float, float],
        throat_transport: tuple[float, float, float, float],
        exit_transport: tuple[float, float, float, float],
        chamber_gamma: float,
        chamber_molecular_weight: float,
        throat_gamma: float,
        throat_molecular_weight: float,
        exit_gamma: float,
        exit_molecular_weight: float,
        chamber_mach: float | None,
        exit_mach: float | None,
        species_summary: dict[str, dict[str, float]],
    ) -> dict[str, ThermochemistryState]:
        return {
            "chamber": RocketCEABackend._make_station_state(
                label="chamber",
                area_ratio=inputs.contraction_ratio,
                temperature_deg_r=temperatures[0] if len(temperatures) > 0 else None,
                density_lbm_cuft=densities[0] if len(densities) > 0 else None,
                enthalpy_btu_lbm=enthalpies[0] if len(enthalpies) > 0 else None,
                cp_btu_lbm_r=heat_capacities[0] if len(heat_capacities) > 0 else None,
                transport=chamber_transport,
                gamma=chamber_gamma,
                molecular_weight=chamber_molecular_weight,
                mach_number=chamber_mach,
                species_mass_fractions=species_summary.get("chamber_mass", {}),
                species_mole_fractions=species_summary.get("chamber_mole", {}),
            ),
            "throat": RocketCEABackend._make_station_state(
                label="throat",
                area_ratio=1.0,
                temperature_deg_r=temperatures[1] if len(temperatures) > 1 else None,
                density_lbm_cuft=densities[1] if len(densities) > 1 else None,
                enthalpy_btu_lbm=enthalpies[1] if len(enthalpies) > 1 else None,
                cp_btu_lbm_r=heat_capacities[1] if len(heat_capacities) > 1 else None,
                transport=throat_transport,
                gamma=throat_gamma,
                molecular_weight=throat_molecular_weight,
                mach_number=1.0,
                species_mass_fractions=species_summary.get("throat_mass", {}),
                species_mole_fractions=species_summary.get("throat_mole", {}),
            ),
            "exit": RocketCEABackend._make_station_state(
                label="exit",
                area_ratio=inputs.expansion_ratio,
                temperature_deg_r=temperatures[2] if len(temperatures) > 2 else None,
                density_lbm_cuft=densities[2] if len(densities) > 2 else None,
                enthalpy_btu_lbm=enthalpies[2] if len(enthalpies) > 2 else None,
                cp_btu_lbm_r=heat_capacities[2] if len(heat_capacities) > 2 else None,
                transport=exit_transport,
                gamma=exit_gamma,
                molecular_weight=exit_molecular_weight,
                mach_number=exit_mach,
                species_mass_fractions=species_summary.get("exit_mass", {}),
                species_mole_fractions=species_summary.get("exit_mole", {}),
            ),
        }

    @staticmethod
    def _make_station_state(
        *,
        label: str,
        area_ratio: float | None,
        temperature_deg_r: float | None,
        density_lbm_cuft: float | None,
        enthalpy_btu_lbm: float | None,
        cp_btu_lbm_r: float | None,
        transport: tuple[float, float, float, float],
        gamma: float | None,
        molecular_weight: float | None,
        mach_number: float | None,
        species_mass_fractions: dict[str, float],
        species_mole_fractions: dict[str, float],
    ) -> ThermochemistryState:
        cp_value, viscosity_value, conductivity_value, prandtl_value = transport
        return ThermochemistryState(
            label=label,
            area_ratio=area_ratio,
            temperature_k=(
                temperature_deg_r * DEGR_TO_K if temperature_deg_r is not None else None
            ),
            density_kg_per_m3=(
                density_lbm_cuft * LBM_PER_CUFT_TO_KG_PER_M3
                if density_lbm_cuft is not None
                else None
            ),
            enthalpy_j_per_kg=(
                enthalpy_btu_lbm * BTU_PER_LBM_TO_J_PER_KG
                if enthalpy_btu_lbm is not None
                else None
            ),
            cp_j_per_kg_k=(
                cp_btu_lbm_r * BTU_PER_LBM_R_TO_J_PER_KG_K
                if cp_btu_lbm_r is not None
                else None
            ),
            viscosity_pa_s=viscosity_value * MILLIPOISE_TO_PA_S,
            thermal_conductivity_w_per_m_k=conductivity_value * MCAL_PER_CMKS_TO_W_PER_MK,
            prandtl_number=prandtl_value,
            gamma=gamma,
            molecular_weight_kg_per_mol=(
                molecular_weight * LBM_PER_LBMOL_TO_KG_PER_MOL
                if molecular_weight is not None
                else None
            ),
            mach_number=mach_number,
            species_mass_fractions=species_mass_fractions,
            species_mole_fractions=species_mole_fractions,
            source="rocketcea-station",
        )

    @staticmethod
    def _chamber_mach_number(
        *,
        cea: Any,
        pc_psia: float,
        inputs: InputParameters,
    ) -> float | None:
        if inputs.contraction_ratio is None or not hasattr(cea, "get_Chamber_MachNumber"):
            return None
        try:
            return float(
                cea.get_Chamber_MachNumber(
                    Pc=pc_psia,
                    MR=inputs.mixture_ratio,
                    fac_CR=inputs.contraction_ratio,
                )
            )
        except Exception:
            return None

    @staticmethod
    def _extract_station(
        fractions: dict[str, list[float]],
        station_index: int,
        limit: int = 8,
    ) -> dict[str, float]:
        station_values = {
            species: float(values[station_index])
            for species, values in fractions.items()
            if len(values) > station_index and values[station_index] > 0.0
        }
        ordered = sorted(station_values.items(), key=lambda item: item[1], reverse=True)
        return dict(ordered[:limit])

    @staticmethod
    def _default_sweep_bounds(
        *,
        current_mixture_ratio: float,
        stoichiometric_mixture_ratio: float | None,
    ) -> tuple[float, float]:
        anchor = max(current_mixture_ratio, stoichiometric_mixture_ratio or 0.0, 1.0)
        lower = max(0.15, min(current_mixture_ratio * 0.55, anchor * 0.35))
        upper = max(current_mixture_ratio * 1.5, anchor * 1.85)
        if stoichiometric_mixture_ratio is not None:
            lower = min(lower, stoichiometric_mixture_ratio * 0.55)
            upper = max(upper, stoichiometric_mixture_ratio * 1.7)
        if upper <= lower:
            upper = lower + max(0.5, current_mixture_ratio)
        return lower, upper

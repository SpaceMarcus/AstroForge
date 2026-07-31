"""Import and export the libconfig-style files used by RPA 2.3."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Any

from engine.models import (
    BellContourVariant,
    ChemistryMode,
    InputParameters,
    NozzleContourMethod,
)

STANDARD_ATMOSPHERE_PA = 101_325.0
DEFAULT_THRUST_COEFFICIENT = 1.50


@dataclass(frozen=True, slots=True)
class RPAConfigImportResult:
    """Mapped AstraForge inputs plus information that could not map exactly."""

    inputs: InputParameters
    case_name: str
    case_info: str
    warnings: tuple[str, ...]
    raw_config: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    position: int


_TOKEN_PATTERN = re.compile(
    r"""
    (?P<whitespace>\s+)
  | (?P<line_comment>//[^\r\n]*|\#[^\r\n]*)
  | (?P<block_comment>/\*.*?\*/)
  | (?P<string>"(?:\\.|[^"\\])*")
  | (?P<number>[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
  | (?P<identifier>[A-Za-z_][A-Za-z0-9_.+\-/]*)
  | (?P<punctuation>[{}()\[\]=:;,])
    """,
    re.VERBOSE | re.DOTALL,
)


class _LibconfigParser:
    def __init__(self, text: str) -> None:
        self._tokens = self._tokenize(text)
        self._index = 0

    @staticmethod
    def _tokenize(text: str) -> list[_Token]:
        tokens: list[_Token] = []
        position = 0
        while position < len(text):
            match = _TOKEN_PATTERN.match(text, position)
            if match is None:
                excerpt = text[position : position + 30].splitlines()[0]
                raise ValueError(
                    f"Unsupported RPA configuration syntax near {excerpt!r}."
                )
            kind = match.lastgroup or ""
            value = match.group()
            if kind not in {"whitespace", "line_comment", "block_comment"}:
                tokens.append(_Token(kind, value, position))
            position = match.end()
        return tokens

    def parse(self) -> dict[str, Any]:
        result = self._parse_assignments(end_token=None)
        if self._index != len(self._tokens):
            token = self._tokens[self._index]
            raise ValueError(
                f"Unexpected token {token.value!r} at offset {token.position}."
            )
        return result

    def _parse_assignments(self, end_token: str | None) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while self._index < len(self._tokens):
            if end_token is not None and self._peek_value() == end_token:
                self._index += 1
                return result
            key_token = self._consume()
            if key_token.kind not in {"identifier", "string"}:
                raise ValueError(
                    f"Expected a configuration key at offset {key_token.position}."
                )
            key = self._decode_string(key_token.value) if key_token.kind == "string" else key_token.value
            separator = self._consume()
            if separator.value not in {"=", ":"}:
                raise ValueError(
                    f"Expected '=' or ':' after {key!r} at offset {separator.position}."
                )
            value = self._parse_value()
            if key in result:
                previous = result[key]
                result[key] = previous + [value] if isinstance(previous, list) else [previous, value]
            else:
                result[key] = value
            if self._peek_value() == ";":
                self._index += 1
        if end_token is not None:
            raise ValueError(f"Unterminated RPA configuration block; expected {end_token!r}.")
        return result

    def _parse_value(self) -> Any:
        token = self._consume()
        if token.value == "{":
            return self._parse_assignments(end_token="}")
        if token.value in {"(", "["}:
            return self._parse_sequence(")" if token.value == "(" else "]")
        if token.kind == "string":
            return self._decode_string(token.value)
        if token.kind == "number":
            value = float(token.value)
            return int(value) if value.is_integer() and "." not in token.value and "e" not in token.value.lower() else value
        if token.kind == "identifier":
            lowered = token.value.lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
            if lowered in {"null", "none"}:
                return None
            return token.value
        raise ValueError(f"Unsupported value {token.value!r} at offset {token.position}.")

    def _parse_sequence(self, end_token: str) -> list[Any]:
        values: list[Any] = []
        while self._index < len(self._tokens):
            if self._peek_value() == end_token:
                self._index += 1
                return values
            values.append(self._parse_value())
            if self._peek_value() == ",":
                self._index += 1
            elif self._peek_value() != end_token:
                token = self._tokens[self._index]
                raise ValueError(
                    f"Expected ',' or {end_token!r} at offset {token.position}."
                )
        raise ValueError(f"Unterminated RPA sequence; expected {end_token!r}.")

    def _consume(self) -> _Token:
        if self._index >= len(self._tokens):
            raise ValueError("Unexpected end of RPA configuration.")
        token = self._tokens[self._index]
        self._index += 1
        return token

    def _peek_value(self) -> str | None:
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index].value

    @staticmethod
    def _decode_string(value: str) -> str:
        body = value[1:-1]
        return bytes(body, "utf-8").decode("unicode_escape")


def parse_rpa_config(text: str) -> dict[str, Any]:
    """Parse an RPA/libconfig document without executing its contents."""

    return _LibconfigParser(text).parse()


def load_rpa_config(path: str | Path) -> RPAConfigImportResult:
    """Read an RPA ``.cfg`` file and map supported fields to AstraForge."""

    source = Path(path)
    return import_rpa_config_text(source.read_text(encoding="utf-8-sig"))


def import_rpa_config_text(text: str) -> RPAConfigImportResult:
    """Map RPA configuration text to validated-shape AstraForge inputs."""

    config = parse_rpa_config(text)
    warnings: list[str] = []
    case_name = str(config.get("name", "Imported RPA case")).strip() or "Imported RPA case"
    case_info = str(config.get("info", "")).strip()

    chamber_conditions = _mapping(config.get("combustionChamberConditions"))
    chamber_pressure_pa = _quantity_to_si(
        _mapping(chamber_conditions.get("pressure")),
        quantity="pressure",
    )

    nozzle_flow = _mapping(config.get("nozzleFlow"))
    nozzle_inlet = _mapping(nozzle_flow.get("nozzleInletConditions"))
    nozzle_exit = _mapping(nozzle_flow.get("nozzleExitConditions"))
    contraction_ratio = _optional_number(nozzle_inlet.get("contractionAreaRatio"))
    expansion_ratio = _optional_number(nozzle_exit.get("areaRatio")) or 1.0

    engine_size = _mapping(config.get("engineSize"))
    thrust_block = _mapping(engine_size.get("thrust"))
    throat_diameter_block = _mapping(engine_size.get("throatDiameter"))
    thrust_n: float
    throat_radius_m: float | None = None
    if thrust_block:
        thrust_n = _quantity_to_si(thrust_block, quantity="force")
    elif throat_diameter_block:
        throat_diameter_m = _quantity_to_si(throat_diameter_block, quantity="length")
        throat_radius_m = 0.5 * throat_diameter_m
        throat_area_m2 = math.pi * throat_radius_m**2
        thrust_n = (
            DEFAULT_THRUST_COEFFICIENT * chamber_pressure_pa * throat_area_m2
        )
        warnings.append(
            "RPA specifies throat diameter instead of thrust. AstraForge estimated "
            f"thrust with Cf={DEFAULT_THRUST_COEFFICIENT:.2f}; recalculate and review."
        )
    else:
        thrust_n = 100_000.0
        warnings.append(
            "RPA configuration contains no engine thrust or throat diameter. "
            "AstraForge uses a 100 kN sizing placeholder; review before calculation."
        )

    ambient_block = engine_size.get("ambientConditions")
    ambient_pressure_pa = (
        _quantity_to_si(_mapping(ambient_block), quantity="pressure")
        if isinstance(ambient_block, dict)
        else 0.0
    )

    propellant = _mapping(config.get("propellant"))
    mixture_definition = _mapping(propellant.get("mixture"))
    if mixture_definition:
        species = mixture_definition.get("species")
        species_count = len(species) if isinstance(species, list) else 1
        raise ValueError(
            "RPA monopropellant/solid-mixture definitions are not yet supported "
            f"by AstroForge's bipropellant input model ({species_count} species found)."
        )
    components = _mapping(propellant.get("components"))
    ratio_block = _mapping(components.get("ratio"))
    mixture_ratio = _required_number(ratio_block.get("value"), "propellant.components.ratio.value")
    oxidizer_name = _first_component_name(components.get("oxidizer"), "oxidizer")
    fuel_name = _first_component_name(components.get("fuel"), "fuel")
    oxidizer = _rpa_to_rocketcea_propellant(oxidizer_name)
    fuel = _rpa_to_rocketcea_propellant(fuel_name)
    _warn_for_multicomponent(components.get("oxidizer"), "oxidizer", warnings)
    _warn_for_multicomponent(components.get("fuel"), "fuel", warnings)

    chemistry_mode = ChemistryMode.EQUILIBRIUM
    freezing = _mapping(nozzle_flow.get("freezingConditions"))
    if bool(freezing.get("calculate", False)):
        chemistry_mode = ChemistryMode.FROZEN_AT_THROAT
        freeze_ratio = _optional_number(freezing.get("expansionRatio"))
        if freeze_ratio is not None and not math.isclose(freeze_ratio, 1.0):
            warnings.append(
                f"RPA freezes chemistry at A/At={freeze_ratio:g}; AstraForge currently "
                "maps this to frozen-at-throat."
            )

    chamber_geometry = _mapping(engine_size.get("chamberGeometry"))
    length_block = _mapping(chamber_geometry.get("length"))
    characteristic_length_m: float | None = None
    if length_block:
        configured_length_m = _quantity_to_si(length_block, quantity="length")
        if bool(chamber_geometry.get("characteristicLength", False)):
            characteristic_length_m = configured_length_m
        else:
            characteristic_length_m = 1.1
            warnings.append(
                "RPA specifies physical chamber length. AstraForge requires L* and "
                "uses the 1.1 m predesign default."
            )

    contour_method = NozzleContourMethod.BELL
    bell_variant = BellContourVariant.PARABOLA
    nozzle_half_angle = _optional_number(chamber_geometry.get("nozzleHalfAngle"))
    if nozzle_half_angle is not None:
        contour_method = NozzleContourMethod.CONICAL
    if bool(chamber_geometry.get("TOC", False)):
        warnings.append(
            "RPA TOC geometry is mapped to AstraForge's TOP/Rao parabola until "
            "the dedicated TOC method-of-characteristics solver is implemented."
        )

    convergent_half_angle_deg = (
        _optional_number(chamber_geometry.get("contractionAngle")) or 45.0
    )
    throat_upstream_radius_m = None
    throat_downstream_radius_m = None
    if throat_radius_m is not None:
        upstream_ratio = _optional_number(chamber_geometry.get("R1_to_Rt_ratio"))
        downstream_ratio = _optional_number(chamber_geometry.get("Rn_to_Rt_ratio"))
        if upstream_ratio is not None:
            throat_upstream_radius_m = upstream_ratio * throat_radius_m
        if downstream_ratio is not None:
            throat_downstream_radius_m = downstream_ratio * throat_radius_m

    inputs = InputParameters(
        fuel=fuel,
        oxidizer=oxidizer,
        chamber_pressure_pa=chamber_pressure_pa,
        thrust_n=thrust_n,
        mixture_ratio=mixture_ratio,
        expansion_ratio=expansion_ratio,
        ambient_pressure_pa=ambient_pressure_pa,
        contraction_ratio=contraction_ratio,
        characteristic_length_m=characteristic_length_m,
        chemistry_mode=chemistry_mode,
        contour_method=contour_method,
        bell_variant=bell_variant,
        bell_length_fraction_percent=80.0 if contour_method is NozzleContourMethod.BELL else None,
        throat_upstream_radius_m=throat_upstream_radius_m,
        throat_downstream_radius_m=throat_downstream_radius_m,
        convergent_half_angle_deg=convergent_half_angle_deg,
    )
    return RPAConfigImportResult(
        inputs=inputs,
        case_name=case_name,
        case_info=case_info,
        warnings=tuple(warnings),
        raw_config=config,
    )


def export_rpa_config(
    inputs: InputParameters,
    target_path: str | Path,
    *,
    case_name: str = "AstraForge Export",
    case_info: str = "Exported by AstraForge",
) -> Path:
    """Write the supported engine/performance subset as an RPA 2.3 config."""

    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        rpa_config_text(inputs, case_name=case_name, case_info=case_info),
        encoding="utf-8",
    )
    return path


def rpa_config_text(
    inputs: InputParameters,
    *,
    case_name: str = "AstraForge Export",
    case_info: str = "Exported by AstraForge",
) -> str:
    """Serialize AstraForge inputs into the RPA/libconfig subset."""

    freeze_enabled = inputs.chemistry_mode is not ChemistryMode.EQUILIBRIUM
    freeze_ratio = 1.0
    if inputs.chemistry_mode is ChemistryMode.FROZEN:
        freeze_ratio = inputs.expansion_ratio
    ambient_atm = inputs.ambient_pressure_pa / STANDARD_ATMOSPHERE_PA
    characteristic_length_m = inputs.characteristic_length_m or 1.1
    lines = [
        "version = 1.2;",
        f'name = "{_escape_config_string(case_name)}";',
        f'info = "{_escape_config_string(case_info)}";',
        "generalOptions :",
        "{",
        "  multiphase = true;",
        "  ions = true;",
        "  flowSeparation = true;",
        "};",
        "combustionChamberConditions :",
        "{",
        "  pressure :",
        "  {",
        f"    value = {_rpa_float(inputs.chamber_pressure_pa / 1.0e5)};",
        '    unit = "bar";',
        "  };",
        "};",
        "nozzleFlow :",
        "{",
        "  calculateNozzleFlow = true;",
    ]
    if freeze_enabled:
        lines.extend(
            [
                "  freezingConditions :",
                "  {",
                "    calculate = true;",
                f"    expansionRatio = {_rpa_float(freeze_ratio)};",
                "  };",
            ]
        )
    lines.extend(
        [
            "  nozzleInletConditions :",
            "  {",
            f"    contractionAreaRatio = {_rpa_float(inputs.contraction_ratio or 4.0)};",
            "  };",
            "  nozzleExitConditions :",
            "  {",
            f"    areaRatio = {_rpa_float(inputs.expansion_ratio)};",
            "    supersonic = true;",
            "  };",
            "  nozzleStations = ( );",
            "};",
            "propellant :",
            "{",
            "  components :",
            "  {",
            "    ratio :",
            "    {",
            f"      value = {_rpa_float(inputs.mixture_ratio)};",
            '      unit = "O/F";',
            "    };",
            "    oxidizer = (",
            "      {",
            f'        name = "{_rocketcea_to_rpa_propellant(inputs.oxidizer, oxidizer=True)}";',
            "        massFraction = 1.0;",
            "        p :",
            "        {",
            "          value = 0.0;",
            '          unit = "MPa";',
            "        };",
            "      }",
            "    );",
            "    fuel = (",
            "      {",
            f'        name = "{_rocketcea_to_rpa_propellant(inputs.fuel, oxidizer=False)}";',
            "        massFraction = 1.0;",
            "        p :",
            "        {",
            "          value = 0.0;",
            '          unit = "MPa";',
            "        };",
            "      }",
            "    );",
            "  };",
            "};",
            "engineSize :",
            "{",
            "  thrust :",
            "  {",
            f"    value = {_rpa_float(inputs.thrust_n / 1000.0)};",
            '    unit = "kN";',
            "  };",
            "  ambientConditions :",
            "  {",
            f"    value = {_rpa_float(ambient_atm)};",
            '    unit = "atm";',
            "  };",
            "  chambersNo = 1;",
            "  chamberGeometry :",
            "  {",
            "    length :",
            "    {",
            f"      value = {_rpa_float(characteristic_length_m)};",
            '      unit = "m";',
            "    };",
            "    characteristicLength = true;",
            f"    contractionAngle = {_rpa_float(inputs.convergent_half_angle_deg)};",
            "    R1_to_Rt_ratio = 1.5;",
            "    Rn_to_Rt_ratio = 0.382;",
            "    R2_to_R2max_ratio = 1.0;",
        ]
    )
    if inputs.contour_method is NozzleContourMethod.CONICAL:
        lines.append(
            f"    nozzleHalfAngle = {_rpa_float(inputs.convergent_half_angle_deg)};"
        )
    else:
        lines.append("    TOC = false;")
    lines.extend(
        [
            "  };",
            "};",
            "propelantFeedSystem :",
            "{",
            "};",
            "",
        ]
    )
    return "\n".join(lines)


def _quantity_to_si(block: dict[str, Any], *, quantity: str) -> float:
    value = _required_number(block.get("value"), f"{quantity}.value")
    unit = str(block.get("unit", "")).strip().lower().replace(" ", "")
    factors = {
        "pressure": {
            "pa": 1.0,
            "kpa": 1.0e3,
            "mpa": 1.0e6,
            "bar": 1.0e5,
            "atm": STANDARD_ATMOSPHERE_PA,
            "psi": 6_894.757293168,
            "psia": 6_894.757293168,
        },
        "force": {
            "n": 1.0,
            "kn": 1.0e3,
            "lbf": 4.4482216152605,
            # RPA example files use "kg" for legacy kilogram-force thrust.
            "kg": 9.80665,
            "kgf": 9.80665,
        },
        "length": {
            "m": 1.0,
            "cm": 1.0e-2,
            "mm": 1.0e-3,
            "in": 0.0254,
            "inch": 0.0254,
            "ft": 0.3048,
        },
    }
    factor = factors[quantity].get(unit)
    if factor is None:
        raise ValueError(f"Unsupported RPA {quantity} unit: {block.get('unit')!r}.")
    return value * factor


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _required_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"RPA field {label} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"RPA field {label} must be finite.")
    return result


def _optional_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _first_component_name(value: Any, label: str) -> str:
    components = value if isinstance(value, list) else [value]
    if not components or not isinstance(components[0], dict):
        raise ValueError(f"RPA configuration does not define a valid {label} component.")
    name = str(components[0].get("name", "")).strip()
    if not name:
        raise ValueError(f"RPA {label} component is missing its name.")
    return name


def _warn_for_multicomponent(value: Any, label: str, warnings: list[str]) -> None:
    if isinstance(value, list) and len(value) > 1:
        warnings.append(
            f"RPA defines {len(value)} {label} components. AstraForge currently "
            "imports only the first component."
        )


def _rpa_to_rocketcea_propellant(name: str) -> str:
    normalized = "".join(character for character in name.upper() if character.isalnum())
    aliases = {
        "O2L": "LOX",
        "O2": "LOX",
        "H2L": "LH2",
        "H2": "LH2",
        "CH4L": "CH4",
        "RG1": "RP-1",
        "N2O4L": "N2O4",
        "C2H8N2LUDMH": "UDMH",
        "CH6N2L": "MMH",
        "C2H5OHL": "Ethanol",
    }
    return aliases.get(normalized, name)


def _rocketcea_to_rpa_propellant(name: str, *, oxidizer: bool) -> str:
    normalized = "".join(character for character in name.upper() if character.isalnum())
    aliases = {
        "LOX": "O2(L)",
        "O2": "O2(L)",
        "LH2": "H2(L)",
        "H2": "H2(L)",
        "CH4": "CH4(L)",
        "METHANE": "CH4(L)",
        "RP1": "RP-1",
        "N2O4": "N2O4(L)",
        "NTO": "N2O4(L)",
        "UDMH": "C2H8N2(L),UDMH",
        "MMH": "CH6N2(L)",
        "ETHANOL": "C2H5OH(L)",
    }
    if normalized in aliases:
        return aliases[normalized]
    if oxidizer and normalized == "N2O":
        return "N2O(L),184.67K"
    return name


def _escape_config_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _rpa_float(value: float) -> str:
    """Format a libconfig floating-point value without changing its type to int."""

    text = f"{float(value):.12g}"
    if "." not in text and "e" not in text.lower():
        text += ".0"
    return text

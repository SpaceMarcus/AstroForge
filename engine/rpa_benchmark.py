"""Run the locally installed RPA console and parse reference performance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Any


@dataclass(frozen=True, slots=True)
class RPAPerformanceTable:
    characteristic_velocity_m_per_s: float
    isp_sea_level_s: float
    isp_optimum_s: float
    isp_vacuum_s: float
    cf_sea_level: float
    cf_optimum: float
    cf_vacuum: float


@dataclass(frozen=True, slots=True)
class RPABenchmarkResult:
    case_name: str
    input_file: str
    ideal: RPAPerformanceTable
    delivered: RPAPerformanceTable | None
    warnings: tuple[str, ...]


def discover_rpa_console() -> Path | None:
    """Return the first known local RPA console executable."""

    candidates = (
        Path.home() / "Desktop" / "RPA-2.3.2-standard-win64" / "rpac.exe",
        Path("C:/Program Files/RPA/rpac.exe"),
        Path("C:/Program Files (x86)/RPA/rpac.exe"),
    )
    return next((path for path in candidates if path.exists()), None)


def run_rpa_benchmark(
    input_file: str | Path,
    *,
    rpa_console: str | Path | None = None,
    timeout_seconds: float = 90.0,
) -> RPABenchmarkResult:
    """Run one RPA input file and return structured ideal/delivered values."""

    console = Path(rpa_console) if rpa_console is not None else discover_rpa_console()
    if console is None or not console.exists():
        raise FileNotFoundError("RPA console executable rpac.exe was not found.")
    source = Path(input_file)
    if not source.exists():
        raise FileNotFoundError(f"RPA input file was not found: {source}")

    completed = subprocess.run(
        [
            str(console),
            "-i",
            str(source.resolve()),
            "-pr",
            "-pt",
            "9",
        ],
        cwd=str(console.parent),
        capture_output=True,
        text=False,
        timeout=timeout_seconds,
        check=False,
    )
    output = _decode_console_output(completed.stdout + b"\n" + completed.stderr)
    if completed.returncode != 0:
        tail = "\n".join(output.splitlines()[-20:])
        raise RuntimeError(
            f"RPA console failed with exit code {completed.returncode}.\n{tail}"
        )
    return parse_rpa_console_output(output, input_file=str(source))


def parse_rpa_console_output(
    output: str,
    *,
    input_file: str = "",
) -> RPABenchmarkResult:
    """Parse RPA's theoretical and delivered performance tables."""

    case_match = re.search(r"(?m)^Case name:[ \t]*([^\r\n]+?)[ \t]*$", output)
    case_name = case_match.group(1).strip() if case_match else Path(input_file).stem
    delivered_marker = re.search(
        r"(?im)^\s*Estimated delivered performance\s*$",
        output,
    )
    if delivered_marker is None:
        ideal_text = output
        delivered_text = ""
    else:
        ideal_text = output[: delivered_marker.start()]
        delivered_text = output[delivered_marker.end() :]

    ideal = _last_performance_table(ideal_text, label="ideal")
    delivered = (
        _first_performance_table(delivered_text, label="delivered")
        if delivered_text
        else None
    )
    warning_lines = tuple(
        line.strip()
        for line in output.splitlines()
        if line.strip().upper().startswith("WARNING:")
    )
    return RPABenchmarkResult(
        case_name=case_name,
        input_file=input_file,
        ideal=ideal,
        delivered=delivered,
        warnings=warning_lines,
    )


def write_rpa_benchmark_json(
    results: list[RPABenchmarkResult],
    target_path: str | Path,
    *,
    rpa_version: str = "2.3.2 Standard",
) -> Path:
    """Write deterministic structured RPA reference results."""

    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "format": "astraforge-rpa-benchmark",
        "version": 1,
        "rpa_version": rpa_version,
        "cases": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _first_performance_table(text: str, *, label: str) -> RPAPerformanceTable:
    matches = _performance_table_matches(text)
    if not matches:
        raise ValueError(f"RPA {label} performance table was not found.")
    return _table_from_match(matches[0])


def _last_performance_table(text: str, *, label: str) -> RPAPerformanceTable:
    matches = _performance_table_matches(text)
    if not matches:
        raise ValueError(f"RPA {label} performance table was not found.")
    return _table_from_match(matches[-1])


def _performance_table_matches(text: str) -> list[tuple[re.Match[str], re.Match[str], re.Match[str]]]:
    characteristic_matches = list(
        re.finditer(
            r"(?im)^\s*Characteristic velocity\s+"
            r"(?P<values>(?:[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\s+){2,}"
            r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s+m/s\s*$",
            text,
        )
    )
    isp_matches = list(
        re.finditer(
            r"(?im)^\s*Specific impulse \(by weight\)\s+"
            r"(?P<values>(?:[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\s+){2,}"
            r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s+s\s*$",
            text,
        )
    )
    cf_matches = list(
        re.finditer(
            r"(?im)^\s*Thrust coefficient\s+"
            r"(?P<values>(?:[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\s+){2,}"
            r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*$",
            text,
        )
    )
    tables: list[tuple[re.Match[str], re.Match[str], re.Match[str]]] = []
    for characteristic in characteristic_matches:
        isp = next((match for match in isp_matches if match.start() > characteristic.start()), None)
        cf = next(
            (
                match
                for match in cf_matches
                if isp is not None and match.start() > isp.start()
            ),
            None,
        )
        if isp is not None and cf is not None:
            tables.append((characteristic, isp, cf))
    return tables


def _table_from_match(
    matches: tuple[re.Match[str], re.Match[str], re.Match[str]],
) -> RPAPerformanceTable:
    characteristic, isp, cf = matches
    characteristic_values = _matched_numbers(characteristic)
    isp_values = _matched_numbers(isp)
    cf_values = _matched_numbers(cf)
    return RPAPerformanceTable(
        characteristic_velocity_m_per_s=max(
            characteristic_values,
            key=abs,
        ),
        isp_sea_level_s=isp_values[0],
        isp_optimum_s=isp_values[-2],
        isp_vacuum_s=isp_values[-1],
        cf_sea_level=cf_values[0],
        cf_optimum=cf_values[-2],
        cf_vacuum=cf_values[-1],
    )


def _matched_numbers(match: re.Match[str]) -> list[float]:
    return [float(value) for value in match.group("values").split()]


def _decode_console_output(value: bytes) -> str:
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")

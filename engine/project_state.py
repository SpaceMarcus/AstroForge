"""Central project mode and dashboard state for AstraForge."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from engine.flow import FlowCaseAssessment


class ProjectMode(str, Enum):
    """High-level workflow mode for the current AstraForge project."""

    GUIDED = "guided-project"
    SANDBOX = "sandbox-learn"


PROJECT_MODE_LABELS: dict[ProjectMode, str] = {
    ProjectMode.GUIDED: "Guided Project",
    ProjectMode.SANDBOX: "Sandbox / Learn",
}


class ModuleStatus(str, Enum):
    """Shared dashboard state for high-level project modules."""

    IDLE = "idle"
    RUNNING = "running"
    READY = "ready"
    STALE = "stale"
    ERROR = "error"


STATUS_COLORS: dict[ModuleStatus, str] = {
    ModuleStatus.IDLE: "#b7bcc4",
    ModuleStatus.RUNNING: "#2f78c4",
    ModuleStatus.READY: "#2f9d57",
    ModuleStatus.STALE: "#d4a62a",
    ModuleStatus.ERROR: "#c73a3a",
}


MODULE_LABELS: dict[str, str] = {
    "project_setup": "Project setup",
    "thermochemistry": "Thermochemistry",
    "geometry": "Geometry",
    "contour": "Contour",
    "material": "Material",
    "cooling": "Cooling",
    "performance": "Performance",
    "report": "Report",
}

MODULE_ORDER: tuple[str, ...] = tuple(MODULE_LABELS)


@dataclass(slots=True)
class ProjectManagementData:
    """Optional project-management and system-engineering text inputs."""

    allow_initial_design_editing_after_run: bool = False
    mission_objectives: str = ""
    requirements: str = ""
    constraints: str = ""
    budgets: str = ""
    thrust_requirement: str = ""
    pressure_requirement: str = ""
    throttling_requirement: str = ""
    max_length: str = ""
    wall_temperature_constraint: str = ""
    manufacturing_constraint: str = ""
    mass_budget: str = ""


@dataclass(slots=True)
class RequirementOverlay:
    """Requirement note to be attached to the overview MBSE silhouette."""

    title: str
    text: str
    target: str


@dataclass(slots=True)
class ProjectState:
    """Central GUI-readable state for project mode and dashboard module colors."""

    project_mode: ProjectMode = ProjectMode.SANDBOX
    system_engineering_enabled: bool = False
    project_management: ProjectManagementData = field(default_factory=ProjectManagementData)
    module_statuses: dict[str, ModuleStatus] = field(default_factory=lambda: default_module_statuses())
    module_messages: dict[str, str] = field(default_factory=dict)
    requirement_overlays: list[RequirementOverlay] = field(default_factory=list)
    flow_case_assessment: FlowCaseAssessment | None = None
    has_results: bool = False


def default_module_statuses() -> dict[str, ModuleStatus]:
    """Return the default module-status map."""

    return {key: ModuleStatus.IDLE for key in MODULE_ORDER}


def create_project_state(project_mode: ProjectMode = ProjectMode.SANDBOX) -> ProjectState:
    """Create a fresh project state with sensible defaults for the chosen mode."""

    state = ProjectState(
        project_mode=project_mode,
        system_engineering_enabled=project_mode is ProjectMode.GUIDED,
    )
    clear_calculation_results(state)
    refresh_project_setup_status(state)
    refresh_requirement_overlays(state)
    return state


def set_project_mode(state: ProjectState, project_mode: ProjectMode) -> None:
    """Switch the current project mode and update dependent state."""

    state.project_mode = project_mode
    state.system_engineering_enabled = project_mode is ProjectMode.GUIDED
    refresh_project_setup_status(state)
    refresh_requirement_overlays(state)


def set_flow_case_assessment(
    state: ProjectState,
    assessment: FlowCaseAssessment | None,
) -> None:
    """Persist the current flow-case assessment for GUI consumers."""

    state.flow_case_assessment = assessment


def apply_project_management_settings(
    state: ProjectState,
    project_management: ProjectManagementData,
    *,
    system_engineering_enabled: bool,
) -> None:
    """Update project-management text and requirement-tracking toggles."""

    state.project_management = project_management
    state.system_engineering_enabled = bool(system_engineering_enabled) and state.project_mode is ProjectMode.GUIDED
    refresh_project_setup_status(state)
    refresh_requirement_overlays(state)

    if state.has_results and state.system_engineering_enabled:
        state.module_statuses["performance"] = ModuleStatus.STALE
        state.module_messages["performance"] = (
            "Project requirements changed. Re-check the current operating point against them."
        )
        state.module_statuses["report"] = ModuleStatus.STALE
        state.module_messages["report"] = (
            "Project-management context changed. Refresh the dashboard and report summary."
        )


def clear_calculation_results(state: ProjectState) -> None:
    """Reset calculation-driven module states while keeping project setup intact."""

    state.has_results = False
    state.module_statuses["thermochemistry"] = ModuleStatus.IDLE
    state.module_messages["thermochemistry"] = "No thermochemistry result has been generated yet."
    state.module_statuses["geometry"] = ModuleStatus.IDLE
    state.module_messages["geometry"] = "No geometry sizing result has been generated yet."
    state.module_statuses["contour"] = ModuleStatus.IDLE
    state.module_messages["contour"] = "No nozzle contour has been generated yet."
    state.module_statuses["material"] = ModuleStatus.READY
    state.module_messages["material"] = "Material selections are available and can be refined."
    state.module_statuses["cooling"] = ModuleStatus.IDLE
    state.module_messages["cooling"] = "Cooling is prepared structurally but not modeled yet."
    state.module_statuses["performance"] = ModuleStatus.IDLE
    state.module_messages["performance"] = "No current performance snapshot is available."
    state.module_statuses["report"] = ModuleStatus.IDLE
    state.module_messages["report"] = "The report view is prepared but not yet populated from a current run."
    refresh_project_setup_status(state)
    refresh_requirement_overlays(state)


def mark_calculation_running(state: ProjectState) -> None:
    """Mark the main solver-driven modules as currently running."""

    for key in ("thermochemistry", "geometry", "contour", "performance"):
        state.module_statuses[key] = ModuleStatus.RUNNING
        state.module_messages[key] = "Calculation is currently running."
    state.module_statuses["material"] = ModuleStatus.READY
    state.module_messages["material"] = "Material selections remain available during the run."
    state.module_statuses["cooling"] = ModuleStatus.IDLE
    state.module_messages["cooling"] = "Cooling is prepared structurally but not modeled yet."
    state.module_statuses["report"] = ModuleStatus.STALE
    state.module_messages["report"] = "A new report context will be available after the run."
    refresh_project_setup_status(state)


def mark_calculation_success(state: ProjectState) -> None:
    """Mark the current project as having an up-to-date design result."""

    state.has_results = True
    state.module_statuses["thermochemistry"] = ModuleStatus.READY
    state.module_messages["thermochemistry"] = "RocketCEA-backed thermochemistry is current."
    state.module_statuses["geometry"] = ModuleStatus.READY
    state.module_messages["geometry"] = "Geometry sizing is current."
    state.module_statuses["contour"] = ModuleStatus.READY
    state.module_messages["contour"] = "The current contour is synchronized with the latest inputs."
    state.module_statuses["material"] = ModuleStatus.READY
    state.module_messages["material"] = "Material selections are synchronized with the current case."
    state.module_statuses["cooling"] = ModuleStatus.IDLE
    state.module_messages["cooling"] = "Cooling remains prepared for a later detailed model."
    state.module_statuses["performance"] = ModuleStatus.READY
    state.module_messages["performance"] = "Performance values are current for the latest operating point."
    state.module_statuses["report"] = ModuleStatus.STALE
    state.module_messages["report"] = "A report snapshot can now be refreshed from the current results."
    refresh_project_setup_status(state)


def mark_calculation_failed(state: ProjectState, message: str) -> None:
    """Mark the solver-driven modules as failed without blocking sandbox use."""

    state.has_results = False
    for key in ("thermochemistry", "geometry", "contour", "performance"):
        state.module_statuses[key] = ModuleStatus.ERROR
        state.module_messages[key] = message
    state.module_statuses["report"] = ModuleStatus.STALE
    state.module_messages["report"] = "The report context is outdated because the latest calculation failed."
    refresh_project_setup_status(state)


def mark_design_inputs_changed(state: ProjectState) -> None:
    """Mark calculation-dependent modules as stale after design-input edits."""

    if not state.has_results:
        return

    stale_messages = {
        "thermochemistry": "Design inputs changed. Re-run thermochemistry.",
        "geometry": "Design inputs changed. Re-run geometry sizing.",
        "contour": "Design inputs changed. Rebuild the contour.",
        "performance": "Design inputs changed. Refresh the performance snapshot.",
        "report": "Design inputs changed. The dashboard/report context is outdated.",
    }
    for key, message in stale_messages.items():
        state.module_statuses[key] = ModuleStatus.STALE
        state.module_messages[key] = message


def mark_material_inputs_changed(state: ProjectState) -> None:
    """Mark material-sensitive modules as stale after liner/material edits."""

    if state.has_results:
        state.module_statuses["material"] = ModuleStatus.STALE
        state.module_messages["material"] = "Material inputs changed. Review wall/liner assumptions."
        state.module_statuses["report"] = ModuleStatus.STALE
        state.module_messages["report"] = "Material inputs changed. Refresh the dashboard/report summary."
    else:
        state.module_statuses["material"] = ModuleStatus.READY
        state.module_messages["material"] = "Material selections are available and can be refined."


def refresh_project_setup_status(state: ProjectState) -> None:
    """Update the project-setup module based on mode and PM completeness."""

    entry_count = _project_entry_count(state.project_management)
    if state.project_mode is ProjectMode.SANDBOX:
        if entry_count == 0:
            state.module_statuses["project_setup"] = ModuleStatus.IDLE
            state.module_messages["project_setup"] = (
                "Project-management context is optional in Sandbox / Learn."
            )
        else:
            state.module_statuses["project_setup"] = ModuleStatus.READY
            state.module_messages["project_setup"] = (
                "Optional project notes are available without blocking sandbox exploration."
            )
        return

    if entry_count == 0:
        state.module_statuses["project_setup"] = ModuleStatus.STALE
        state.module_messages["project_setup"] = (
            "Guided Project expects mission goals, requirements or constraints."
        )
    elif entry_count < 3:
        state.module_statuses["project_setup"] = ModuleStatus.STALE
        state.module_messages["project_setup"] = (
            "Guided Project context is partial. Add more project drivers for fuller traceability."
        )
    else:
        state.module_statuses["project_setup"] = ModuleStatus.READY
        state.module_messages["project_setup"] = (
            "Guided Project context is active and available for dashboard overlays."
        )


def refresh_requirement_overlays(state: ProjectState) -> None:
    """Rebuild system-level requirement overlays from project-management text."""

    if not state.system_engineering_enabled:
        state.requirement_overlays = []
        return

    overlays: list[RequirementOverlay] = []
    data = state.project_management
    _append_overlay(overlays, "Thrust requirement", data.thrust_requirement, "performance")
    _append_overlay(overlays, "Vacuum / ambient requirement", data.pressure_requirement, "injector")
    _append_overlay(overlays, "Throttling requirement", data.throttling_requirement, "injector")
    _append_overlay(overlays, "Max length", data.max_length, "nozzle")
    _append_overlay(overlays, "Wall temperature constraint", data.wall_temperature_constraint, "wall")
    _append_overlay(overlays, "Manufacturing / material", data.manufacturing_constraint, "liner")
    _append_overlay(overlays, "Mass budget", data.mass_budget, "performance")

    if overlays:
        state.requirement_overlays = overlays
        return

    fallback_text = "Guided project is active. Add structured requirements to show callouts here."
    state.requirement_overlays = [
        RequirementOverlay(
            title="Requirements / interfaces",
            text=fallback_text,
            target="requirements",
        )
    ]


def _append_overlay(
    overlays: list[RequirementOverlay],
    title: str,
    text: str,
    target: str,
) -> None:
    cleaned = text.strip()
    if not cleaned:
        return
    overlays.append(RequirementOverlay(title=title, text=cleaned, target=target))


def _project_entry_count(project_management: ProjectManagementData) -> int:
    return sum(
        1
        for value in (
            project_management.mission_objectives,
            project_management.requirements,
            project_management.constraints,
            project_management.budgets,
            project_management.thrust_requirement,
            project_management.pressure_requirement,
            project_management.throttling_requirement,
            project_management.max_length,
            project_management.wall_temperature_constraint,
            project_management.manufacturing_constraint,
            project_management.mass_budget,
        )
        if value.strip()
    )

"""Tests for central project-mode and dashboard state helpers."""

from engine.project_state import (
    ModuleStatus,
    ProjectManagementData,
    ProjectMode,
    apply_project_management_settings,
    create_project_state,
    mark_calculation_success,
    mark_design_inputs_changed,
    set_project_mode,
)


def test_sandbox_defaults_keep_project_setup_optional() -> None:
    state = create_project_state()

    assert state.project_mode is ProjectMode.SANDBOX
    assert state.module_statuses["project_setup"] is ModuleStatus.IDLE
    assert state.requirement_overlays == []


def test_guided_mode_uses_project_management_to_activate_overlays() -> None:
    state = create_project_state()
    set_project_mode(state, ProjectMode.GUIDED)
    apply_project_management_settings(
        state,
        ProjectManagementData(
            mission_objectives="Reusable demonstrator",
            requirements="Sea-level ignition",
            constraints="Keep packaging compact",
            thrust_requirement=">= 100 kN",
            max_length="Below 900 mm",
        ),
        system_engineering_enabled=True,
    )

    assert state.project_mode is ProjectMode.GUIDED
    assert state.system_engineering_enabled is True
    assert state.module_statuses["project_setup"] is ModuleStatus.READY
    assert len(state.requirement_overlays) >= 2


def test_design_input_changes_mark_current_results_as_stale() -> None:
    state = create_project_state()
    mark_calculation_success(state)

    mark_design_inputs_changed(state)

    assert state.module_statuses["thermochemistry"] is ModuleStatus.STALE
    assert state.module_statuses["geometry"] is ModuleStatus.STALE
    assert state.module_statuses["contour"] is ModuleStatus.STALE
    assert state.module_statuses["performance"] is ModuleStatus.STALE

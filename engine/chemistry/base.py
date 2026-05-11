"""Abstract thermochemistry backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from engine.models import InputParameters, OFSweepResult, ThermochemistryResult


class ThermochemistryBackendError(RuntimeError):
    """Base error for backend failures that should be surfaced to the user."""


class ThermochemistryBackendUnavailableError(ThermochemistryBackendError):
    """Raised when a required thermochemistry backend is not installed."""


class ThermochemistryBackend(ABC):
    """Boundary that isolates the rest of the project from RocketCEA details."""

    @abstractmethod
    def calculate(self, inputs: InputParameters) -> ThermochemistryResult:
        """Run the thermochemistry backend for a validated engine input set."""

    @abstractmethod
    def estimate_ambient_matched_expansion_ratio(
        self,
        inputs: InputParameters,
    ) -> float | None:
        """Return a preliminary ambient-matched Ae/At value when the backend can provide one."""

    @abstractmethod
    def build_of_sweep(
        self,
        inputs: InputParameters,
        *,
        sample_count: int = 41,
    ) -> OFSweepResult:
        """Return a RocketCEA-backed O/F sweep for the selected propellant pair."""

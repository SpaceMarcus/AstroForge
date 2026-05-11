"""Dedicated GUI launcher for packaging the desktop application as an EXE."""

from __future__ import annotations

from app import EngineDesignApplication, build_example_inputs
from engine.chemistry import RocketCEABackend
from engine.gui import MainWindow


def main() -> int:
    """Start the Tkinter GUI without exposing the CLI code path."""

    application = EngineDesignApplication(backend=RocketCEABackend())
    window = MainWindow(
        controller=application,
        example_input_factory=build_example_inputs,
    )
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

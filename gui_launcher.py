"""Dedicated GUI launcher for packaging the desktop application as an EXE."""

from __future__ import annotations

import sys

from app import EngineDesignApplication, build_example_inputs
from engine.chemistry import RocketCEABackend
from engine.gui import MainWindow


def _configure_windows_app_identity() -> None:
    """Set a stable Windows app identity before Tk creates the first window.

    The taskbar picks up the process AppUserModelID very early. Setting it here
    avoids the generic placeholder icon that can otherwise appear even when the
    EXE already carries a custom icon resource.
    """

    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AstraForge.Desktop")
    except Exception:
        pass


def main() -> int:
    """Start the Tkinter GUI without exposing the CLI code path."""

    _configure_windows_app_identity()
    application = EngineDesignApplication(backend=RocketCEABackend())
    window = MainWindow(
        controller=application,
        example_input_factory=build_example_inputs,
    )
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

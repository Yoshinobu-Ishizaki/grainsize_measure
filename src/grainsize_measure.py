from __future__ import annotations

import os
import sys
from pathlib import Path

# uv run src/grainsize_measure.py で起動した場合に src/ 配下のモジュールを import できるようにする
sys.path.insert(0, str(Path(__file__).parent))

# On Wayland, QWindow.move() is a compositor-controlled no-op.
# Force XCB (X11/XWayland) so that explicit window positioning works.
# Skip on Windows — xcb is Linux-only; the windows plugin is used automatically.
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PyQt6.QtWidgets import QApplication
from gui.settings_dialog import SettingsDialog


def main() -> None:
    app = QApplication(sys.argv)

    # i18n MUST be initialised after QApplication and before any widget is created.
    import i18n
    i18n.setup()
    from i18n import _

    app.setApplicationName(_("Grain Size Measurement"))
    dialog = SettingsDialog()
    dialog.position_and_show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

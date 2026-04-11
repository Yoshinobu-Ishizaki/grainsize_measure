from __future__ import annotations

import sys
from pathlib import Path

# uv run src/grainsize_measure.py で起動した場合に src/ 配下のモジュールを import できるようにする
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from gui.settings_dialog import SettingsDialog


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("結晶粒サイズ測定")
    dialog = SettingsDialog()
    dialog.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

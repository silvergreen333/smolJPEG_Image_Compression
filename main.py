from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def app_dir() -> Path:
    return Path(__file__).resolve().parent


def main() -> int:
    app = QApplication(sys.argv)

    icon_path = app_dir() / "smolJPEG_icon.ico"
    icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()

    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .tooling import APP_NAME
from .worker import CompressionWorker


class MainWindow(QMainWindow):
    DEFAULT_MAX_SIZE_TEXT = "10 MB"
    DEFAULT_MODE_INDEX = 0

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(980, 730)
        self.setMinimumSize(980, 730)

        self.worker: CompressionWorker | None = None
        self._has_saved_output_in_current_run = False
        self._toast: QLabel | None = None

        self._build_ui()
        self._apply_fixed_theme()
        self._refresh_open_destination_button()
        self._append_log("Ready. Choose your folders, pick a mode, and click Compress.")

        QTimer.singleShot(0, self._sync_content_geometry)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        self.source_edit.setEnabled(enabled)
        self.dest_edit.setEnabled(enabled)
        self.size_edit.setEnabled(enabled)
        self.mode_combo.setEnabled(enabled)
        self.source_btn.setEnabled(enabled)
        self.dest_btn.setEnabled(enabled)
        self.reset_btn.setEnabled(enabled)

    def _apply_result_row_style(self, row: int, status: str) -> None:
        status_lower = status.strip().lower()

        if status_lower == "done":
            color = QColor("#BFE7C6")
        elif status_lower == "skipped":
            color = QColor("#B7C9D3")
        elif status_lower in {"cancelled", "stopped"}:
            color = QColor("#E7C27D")
        elif status_lower == "failed":
            color = QColor("#F1A7A7")
        else:
            color = QColor("#E7EEF0")

        for column in range(self.results_table.columnCount()):
            item = self.results_table.item(row, column)
            if item is not None:
                item.setForeground(color)

    def _apply_fixed_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #111E22;
                color: #E7EEF0;
            }

            QGroupBox {
                background-color: #13262B;
                color: #EAF2F4;
                border: 1px solid #3F5B63;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 10px;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #F1F7F8;
            }

            QLabel {
                color: #E7EEF0;
                background: transparent;
            }

            QLineEdit,
            QComboBox,
            QPlainTextEdit,
            QTableWidget {
                background-color: #1B3137;
                color: #E7EEF0;
                border: 0px solid #59757E;
                border-radius: 3px;
                selection-background-color: #3B6974;
                selection-color: #FFFFFF;
            }

            QLineEdit,
            QComboBox {
                min-height: 22px;
                max-height: 22px;
                padding: 0px 8px;
            }

            QComboBox {
                border: 0px solid #35525A;
            }

            QLineEdit#sizeEdit {
                padding-left: 5px;
                padding-right: 8px;
            }

            QPushButton {
                background-color: #243B42;
                color: #EAF2F4;
                border: 1px solid #59757E;
                border-radius: 6px;
                padding: 4px 10px;
            }

            QPushButton:hover {
                background-color: #2C4750;
            }

            QPushButton:disabled {
                background-color: #18282D;
                color: #8FA3A9;
                border-color: #3F555C;
            }

            QProgressBar {
                background-color: #1B3137;
                border: 0px solid #59757E;
                border-radius: 3px;
                min-height: 4px;
                max-height: 4px;
            }

            QProgressBar::chunk {
                background-color: #58C2D3;
                border-radius: 5px;
            }

            QHeaderView::section {
                background-color: #274046;
                color: #EEF5F6;
                border: 1px solid #46626A;
                padding: 4px 6px;
            }

            QTableWidget {
                gridline-color: #3E5960;
                alternate-background-color: #16292E;
            }

            QScrollBar:vertical {
                background: #111E22;
                width: 6px;
            }

            QScrollBar::handle:vertical {
                background: #4394a1;
                border-radius: 3px;
                min-height: 24px;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_content_geometry)

    def _build_ui(self) -> None:
        outer = QWidget(self)
        self.setCentralWidget(outer)

        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer_layout.addWidget(self.scroll_area)

        self.content_widget = QWidget()
        self.content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.scroll_area.setWidget(self.content_widget)

        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(16, 4, 16, 10)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        intro_widget = QGroupBox("How it works")
        intro_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        intro_layout = QVBoxLayout(intro_widget)
        intro_layout.setContentsMargins(12, 12, 12, 12)
        intro_layout.setSpacing(2)

        self.intro_label = QLabel(
            "Choose a folder with images, and smolJPEG will compress them into JPEGs that stay under your chosen max file size without changing image resolution."
        )
        self.intro_label.setWordWrap(True)
        self.intro_label.setStyleSheet("color: #D7E3E6; margin: 0px; padding: 0px;")

        self.formats_label = QLabel(
            "Supported file formats: BMP, DIB, JPG, JPEG, PNG, TIF, TIFF, and WEBP."
        )
        self.formats_label.setWordWrap(True)
        self.formats_label.setStyleSheet("color: #C2D0D4; margin: 0px; padding: 0px;")

        intro_layout.addWidget(self.intro_label)
        intro_layout.addWidget(self.formats_label)
        layout.addWidget(intro_widget)

        top_box = QGroupBox("Batch settings")
        top_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        form = QGridLayout(top_box)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        for row in range(4):
            form.setRowMinimumHeight(row, 26)

        self.source_edit = QLineEdit()
        self.dest_edit = QLineEdit()
        self.dest_edit.textChanged.connect(self._on_destination_changed)

        self.size_edit = QLineEdit(self.DEFAULT_MAX_SIZE_TEXT)
        self.size_edit.setObjectName("sizeEdit")
        self.size_edit.setPlaceholderText("10 MB")
        self.size_edit.setToolTip("Enter a file size in MB, for example: 10, 10.0, or 10.000 MB")
        self.size_edit.editingFinished.connect(self._normalize_size_text)
        self.size_edit.setValidator(QDoubleValidator(0.1, 1000.0, 3, self))

        self.mode_combo = QComboBox()
        self.mode_combo.addItem(
            "Performance (Fast) — Good for web and social media",
            "performance",
        )
        self.mode_combo.addItem(
            "Quality (Slow) — Best for archiving and reference",
            "quality",
        )
        self.mode_combo.setCurrentIndex(self.DEFAULT_MODE_INDEX)

        self.source_btn = QPushButton("Browse…")
        self.source_btn.clicked.connect(self._choose_source_dir)

        self.dest_btn = QPushButton("Browse…")
        self.dest_btn.clicked.connect(self._choose_dest_dir)

        form.addWidget(QLabel("Source folder"), 0, 0)
        form.addWidget(self.source_edit, 0, 1)
        form.addWidget(self.source_btn, 0, 2)

        form.addWidget(QLabel("Destination folder"), 1, 0)
        form.addWidget(self.dest_edit, 1, 1)
        form.addWidget(self.dest_btn, 1, 2)

        form.addWidget(QLabel("Max file size"), 2, 0)
        form.addWidget(self.size_edit, 2, 1)

        form.addWidget(QLabel("Mode"), 3, 0)
        form.addWidget(self.mode_combo, 3, 1)

        layout.addWidget(top_box)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 8, 0, 0)
        controls_layout.setSpacing(10)

        self.start_btn = QPushButton("Compress")
        self.start_btn.clicked.connect(self._start)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)

        self.open_destination_btn = QPushButton("Open destination folder")
        self.open_destination_btn.clicked.connect(self._open_destination_folder)
        self.open_destination_btn.setEnabled(False)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self._reset_batch_settings)

        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.cancel_btn)
        controls_layout.addWidget(self.open_destination_btn)
        controls_layout.addWidget(self.reset_btn)
        controls_layout.addStretch(1)
        layout.addLayout(controls_layout)

        self.progress_box = QGroupBox("Progress")
        self.progress_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        progress_layout = QVBoxLayout(self.progress_box)
        progress_layout.setContentsMargins(12, 12, 12, 12)
        progress_layout.setSpacing(8)

        summary_layout = QHBoxLayout()
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(8)

        self.activity_label = QLabel("Status: Ready")
        self.activity_label.setWordWrap(True)
        self.activity_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        summary_layout.addWidget(self.activity_label, 1)

        self.progress_summary_label = QLabel("0/0 complete")
        self.progress_summary_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        summary_layout.addWidget(self.progress_summary_label)

        progress_layout.addLayout(summary_layout)

        self.eta_label = QLabel("Time left: —")
        self.eta_label.setWordWrap(True)
        self.eta_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        progress_layout.addWidget(self.eta_label)

        self.current_image_progress_label = QLabel("Current image")
        progress_layout.addWidget(self.current_image_progress_label)

        self.current_image_progress_bar = QProgressBar()
        self.current_image_progress_bar.setRange(0, 100)
        self.current_image_progress_bar.setValue(0)
        self.current_image_progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.current_image_progress_bar)

        self.total_progress_label = QLabel("All images")
        progress_layout.addWidget(self.total_progress_label)

        self.total_progress_bar = QProgressBar()
        self.total_progress_bar.setRange(0, 100)
        self.total_progress_bar.setValue(0)
        self.total_progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.total_progress_bar)

        layout.addWidget(self.progress_box)

        self.results_box = QGroupBox("Results")
        self.results_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        results_layout = QVBoxLayout(self.results_box)
        results_layout.setContentsMargins(12, 12, 12, 12)
        results_layout.setSpacing(8)

        self.results_summary_label = QLabel("No files processed yet.")
        self.results_summary_label.setWordWrap(True)
        results_layout.addWidget(self.results_summary_label)

        self.results_table = QTableWidget(0, 6)
        self.results_table.setHorizontalHeaderLabels(
            ["File", "Status", "Time", "Size", "Image Quality", "Details"]
        )
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setMinimumHeight(10)
        self.results_table.setMaximumHeight(140)
        results_layout.addWidget(self.results_table)

        layout.addWidget(self.results_box)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.hide()

    def _show_toast(self, message: str, duration_ms: int = 3000) -> None:
        if self._toast is not None:
            self._toast.hide()
            self._toast.deleteLater()

        self._toast = QLabel(message, self)
        self._toast.setObjectName("toast")
        self._toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast.setWordWrap(True)
        self._toast.setStyleSheet("""
            QLabel#toast {
                background-color: rgba(36, 59, 66, 235);
                color: #EAF2F4;
                border: 1px solid #59757E;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        self._toast.adjustSize()

        margin = 20
        x = self.width() - self._toast.width() - margin
        y = self.height() - self._toast.height() - margin
        self._toast.move(max(margin, x), max(margin, y))
        self._toast.show()
        self._toast.raise_()

        QTimer.singleShot(duration_ms, self._hide_toast)

    def _hide_toast(self) -> None:
        if self._toast is None:
            return
        toast = self._toast
        self._toast = None
        toast.hide()
        toast.deleteLater()

    def _sync_content_geometry(self) -> None:
        layout = self.content_widget.layout()
        if layout is None:
            return
        layout.activate()
        self.content_widget.adjustSize()

    def _choose_source_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose source folder")
        if selected:
            self.source_edit.setText(selected)

    def _choose_dest_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose destination folder")
        if selected:
            self.dest_edit.setText(selected)

    def _reset_batch_settings(self) -> None:
        self.source_edit.clear()
        self.dest_edit.clear()
        self.size_edit.setText(self.DEFAULT_MAX_SIZE_TEXT)
        self.mode_combo.setCurrentIndex(self.DEFAULT_MODE_INDEX)
        self._normalize_size_text()
        self._show_toast("Batch settings reset.")

    def _normalize_size_text(self) -> None:
        text = self.size_edit.text().strip().upper().replace("MB", "").strip()
        if not text:
            self.size_edit.setText("10.000 MB")
            return
        try:
            value = float(text)
        except ValueError:
            self.size_edit.setText("10.000 MB")
            return
        if value < 0.1:
            value = 0.1
        elif value > 1000.0:
            value = 1000.0
        self.size_edit.setText(f"{value:.3f} MB")

    def _parse_size_mb(self) -> float:
        text = self.size_edit.text().strip().upper().replace("MB", "").strip()
        if not text:
            raise ValueError("Enter a max file size.")
        value = float(text)
        if value < 0.1 or value > 1000.0:
            raise ValueError("Max file size must be between 0.1 MB and 1000 MB.")
        return value

    def _on_destination_changed(self) -> None:
        self._has_saved_output_in_current_run = False
        self._refresh_open_destination_button()

    def _refresh_open_destination_button(self) -> None:
        dest_text = self.dest_edit.text().strip()
        dest_ok = bool(dest_text) and Path(dest_text).exists() and Path(dest_text).is_dir()
        self.open_destination_btn.setEnabled(dest_ok and self._has_saved_output_in_current_run)

    def _open_destination_folder(self) -> None:
        dest_text = self.dest_edit.text().strip()
        if not dest_text:
            QMessageBox.information(self, APP_NAME, "Choose a destination folder first.")
            return

        dest = Path(dest_text)
        if not dest.exists() or not dest.is_dir():
            QMessageBox.information(self, APP_NAME, "Destination folder does not exist.")
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest.resolve())))

    def _start(self) -> None:
        source = Path(self.source_edit.text().strip())
        dest = Path(self.dest_edit.text().strip())

        if not source.exists() or not source.is_dir():
            QMessageBox.warning(self, APP_NAME, "Choose a valid source folder.")
            return
        if not dest.exists() or not dest.is_dir():
            QMessageBox.warning(self, APP_NAME, "Choose a valid destination folder.")
            return

        try:
            max_size_mb = self._parse_size_mb()
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return

        self.results_summary_label.setText("Processing files...")
        self._normalize_size_text()

        self._has_saved_output_in_current_run = False
        self._refresh_open_destination_button()

        self.results_table.setRowCount(0)
        self.log_edit.clear()
        self.current_image_progress_bar.setValue(0)
        self.total_progress_bar.setValue(0)
        self.current_image_progress_label.setText("Current image")
        self.total_progress_label.setText("All images")
        self.progress_summary_label.setText("0/0 complete")
        self.activity_label.setText("Status: Getting ready…")
        self.eta_label.setText("Time left: estimating…")
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        self._set_inputs_enabled(False)

        worker = CompressionWorker(
            source_dir=source,
            destination_dir=dest,
            max_size_mb=max_size_mb,
            mode=self.mode_combo.currentData(),
        )
        worker.log.connect(self._append_log)
        worker.progress.connect(self._on_progress)
        worker.image_progress.connect(self._on_image_progress)
        worker.file_started.connect(self._on_file_started)
        worker.file_finished.connect(self._on_file_finished)
        worker.activity_changed.connect(self._on_activity_changed)
        worker.row_activity_changed.connect(self._on_row_activity_changed)
        worker.eta_changed.connect(self._on_eta_changed)
        worker.run_finished.connect(self._on_run_finished)
        worker.fatal_error.connect(self._on_fatal_error)
        self.worker = worker
        worker.start()

        QTimer.singleShot(0, self._sync_content_geometry)

    def _cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.activity_label.setText("Status: Stopping…")
            self.results_summary_label.setText("Stopping...")

    def _on_progress(self, current: int, total: int) -> None:
        if total <= 0:
            self.total_progress_bar.setValue(0)
            self.total_progress_label.setText("All images")
            self.progress_summary_label.setText("0/0 complete")
            return

        percent = int(round((current / total) * 100))
        self.total_progress_bar.setValue(percent)
        self.total_progress_label.setText(f"All images ({current}/{total})")
        self.progress_summary_label.setText(f"{current}/{total} complete")

    def _on_image_progress(self, percent: int) -> None:
        percent = max(0, min(100, percent))
        self.current_image_progress_bar.setValue(percent)
        self.current_image_progress_label.setText(f"Current image ({percent}%)")

    def _on_file_started(self, filename: str) -> None:
        self.current_image_progress_bar.setValue(0)
        self.current_image_progress_label.setText("Current image (0%)")

        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        self.results_table.setItem(row, 0, QTableWidgetItem(filename))
        self.results_table.setItem(row, 1, QTableWidgetItem("Working"))
        self.results_table.setItem(row, 2, QTableWidgetItem("-"))
        self.results_table.setItem(row, 3, QTableWidgetItem("-"))
        self.results_table.setItem(row, 4, QTableWidgetItem("-"))
        self.results_table.setItem(row, 5, QTableWidgetItem("Getting image ready"))
        self.results_table.scrollToBottom()

    def _on_file_finished(
        self,
        filename: str,
        status: str,
        duration_text: str,
        size_text: str,
        score_text: str,
        details: str,
    ) -> None:
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            status_item = self.results_table.item(row, 1)
            if item and status_item and item.text() == filename and status_item.text() == "Working":
                status_item.setText(status)
                self.results_table.item(row, 2).setText(duration_text)
                self.results_table.item(row, 3).setText(size_text)
                self.results_table.item(row, 4).setText(score_text)
                self.results_table.item(row, 5).setText(details)
                self._apply_result_row_style(row, status)
                break

        if status == "Done":
            self.current_image_progress_bar.setValue(100)
            self.current_image_progress_label.setText("Current image (100%)")
            self._has_saved_output_in_current_run = True
            self._refresh_open_destination_button()
        elif status == "Cancelled":
            self.current_image_progress_bar.setValue(0)
            self.current_image_progress_label.setText("Current image")
        else:
            self.current_image_progress_bar.setValue(100)
            self.current_image_progress_label.setText("Current image (100%)")

    def _on_activity_changed(self, text: str) -> None:
        self.activity_label.setText(text)

    def _on_row_activity_changed(self, filename: str, text: str) -> None:
        for row in range(self.results_table.rowCount()):
            file_item = self.results_table.item(row, 0)
            status_item = self.results_table.item(row, 1)
            detail_item = self.results_table.item(row, 5)
            if (
                file_item
                and status_item
                and detail_item
                and file_item.text() == filename
                and status_item.text() == "Working"
            ):
                detail_item.setText(text)
                break

    def _on_eta_changed(self, text: str) -> None:
        self.eta_label.setText(text)

    def _on_run_finished(self, summary) -> None:
        processed_count = summary.compressed_files + summary.skipped_files

        self._set_inputs_enabled(True)
        self.worker = None
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if summary.total_files and not summary.cancelled:
            self.total_progress_bar.setValue(100)

        self.progress_summary_label.setText(
            (
                f"Cancelled at {processed_count}/{summary.total_files}"
                if summary.cancelled
                else f"{processed_count}/{summary.total_files} complete"
            )
            if summary.total_files
            else "0/0 complete"
        )

        if summary.cancelled:
            self.current_image_progress_bar.setValue(0)
            self.current_image_progress_label.setText("Current image")
            self.total_progress_label.setText("All images")
            self.activity_label.setText("Status: Stopped")
            self.eta_label.setText("Time left: stopped")
            self.results_summary_label.setText(
                f"Stopped early. {summary.compressed_files} compressed, "
                f"{summary.skipped_files} skipped, {summary.failed_files} failed."
            )
            self._show_toast("Compression stopped.")
        else:
            self.current_image_progress_bar.setValue(100 if summary.total_files else 0)
            self.current_image_progress_label.setText("Current image")
            self.total_progress_label.setText("All images")
            self.activity_label.setText("Status: Ready")
            self.eta_label.setText("Time left: complete")

            if summary.failed_files:
                self.results_summary_label.setText(
                    f"Finished. {summary.compressed_files} compressed, "
                    f"{summary.skipped_files} skipped, {summary.failed_files} failed."
                )
                self._show_toast(
                    f"Finished: {summary.compressed_files} compressed, "
                    f"{summary.skipped_files} skipped, {summary.failed_files} failed."
                )
            else:
                self.results_summary_label.setText(
                    f"Finished. {summary.compressed_files} compressed, "
                    f"{summary.skipped_files} skipped."
                )
                self._show_toast(
                    f"All images finished. {summary.compressed_files} compressed, "
                    f"{summary.skipped_files} skipped."
                )

        self._append_log(
            f"Finished. Compressed: {summary.compressed_files}, "
            f"Skipped: {summary.skipped_files}, Failed: {summary.failed_files}, "
            f"Stopped early: {'Yes' if summary.cancelled else 'No'}"
        )

        QTimer.singleShot(0, self._sync_content_geometry)

    def _on_fatal_error(self, message: str) -> None:
        self._set_inputs_enabled(True)
        self.worker = None
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.current_image_progress_bar.setValue(0)
        self.total_progress_bar.setValue(0)
        self.current_image_progress_label.setText("Current image")
        self.total_progress_label.setText("All images")
        self.progress_summary_label.setText("0/0 complete")
        self.activity_label.setText("Status: Stopped")
        self.eta_label.setText("Time left: stopped")
        self.results_summary_label.setText("Could not start compression.")
        self._append_log(message)
        QMessageBox.critical(self, APP_NAME, message)

        QTimer.singleShot(0, self._sync_content_geometry)

    def _append_log(self, message: str) -> None:
        self.log_edit.appendPlainText(message)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())

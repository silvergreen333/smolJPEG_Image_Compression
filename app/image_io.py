from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage, QImageReader, QImageWriter

from .models import NormalizedImage


class ImageNormalizationError(RuntimeError):
    pass


class ImageNormalizer:
    def normalize(self, source_path: Path, temp_dir: Path) -> NormalizedImage:
        reader = QImageReader(str(source_path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            raise ImageNormalizationError(
                f"Unable to read image '{source_path.name}': {reader.errorString()}"
            )

        normalized = image.convertToFormat(QImage.Format.Format_RGB888)
        if normalized.isNull():
            raise ImageNormalizationError(f"Unable to convert '{source_path.name}' to RGB.")

        png_path = temp_dir / f"{source_path.stem}__source.png"
        bmp_path = temp_dir / f"{source_path.stem}__source.bmp"

        self._save_qimage(normalized, png_path, b"PNG")
        self._save_qimage(normalized, bmp_path, b"BMP")

        return NormalizedImage(
            source_path=source_path,
            stem=source_path.stem,
            width=normalized.width(),
            height=normalized.height(),
            png_path=png_path,
            bmp_path=bmp_path,
        )

    @staticmethod
    def _save_qimage(image: QImage, target_path: Path, fmt: bytes) -> None:
        writer = QImageWriter(str(target_path), fmt)
        if not writer.write(image):
            raise ImageNormalizationError(
                f"Unable to write temporary image '{target_path.name}': {writer.errorString()}"
            )

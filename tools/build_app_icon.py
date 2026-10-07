"""Render the editable companion SVG into its PNG and multi-size Windows ICO.

Run with the project's Python runtime, which provides PySide6 and Pillow:
    python -X utf8 tools/build_app_icon.py
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "outputs" / "companion" / "assets"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_svg(renderer: QSvgRenderer, size: int) -> QImage:
    # Supersample each requested size independently so the small ICO frames
    # retain smooth edges instead of relying on a single large raster resize.
    frame = QImage(size * 4, size * 4, QImage.Format.Format_ARGB32)
    frame.fill(Qt.GlobalColor.transparent)
    painter = QPainter(frame)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return frame.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def pillow_image(frame: QImage) -> Image.Image:
    rgba = frame.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes("RGBA", (rgba.width(), rgba.height()), rgba.bits().tobytes())


def build(preview: Path | None) -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(QByteArray((ASSETS / "app-icon.svg").read_bytes()))
    if not renderer.isValid():
        raise ValueError("app-icon.svg is not valid SVG")
    png = ASSETS / "app-icon.png"
    if not render_svg(renderer, 512).save(str(png)):
        raise RuntimeError(f"Cannot save {png}")
    frames = [pillow_image(render_svg(renderer, size)) for size in ICO_SIZES]
    ico = ASSETS / "app-icon.ico"
    frames[-1].save(
        ico,
        format="ICO",
        sizes=[(size, size) for size in ICO_SIZES],
        append_images=frames[:-1],
    )
    with Image.open(ico) as actual:
        if actual.ico.sizes() != {(size, size) for size in ICO_SIZES}:
            raise RuntimeError("The ICO is missing a required image size")
    print(f"PNG: {png} (512 x 512)")
    print(f"ICO: {ico} ({', '.join(map(str, ICO_SIZES))})")
    if preview is not None:
        preview.parent.mkdir(parents=True, exist_ok=True)
        sheet = Image.new("RGB", (1040, 300), "#ececf2")
        draw = ImageDraw.Draw(sheet)
        for index, (size, frame) in enumerate(zip(ICO_SIZES, frames)):
            x = 16 + index * 140
            draw.text((x, 18), f"{size} px", fill="#313141")
            shown = frame if size <= 128 else frame.resize((160, 160), Image.Resampling.LANCZOS)
            sheet.paste(shown, (x, 52), shown)
            if size <= 64:
                enlarged = frame.resize((96, 96), Image.Resampling.NEAREST)
                sheet.paste(enlarged, (x, 152), enlarged)
        sheet.save(preview)
        print(f"Preview: {preview}")
    # Keep the application alive through all SVG and image operations.
    del app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", type=Path, help="Optional multi-size contact sheet")
    build(parser.parse_args().preview)

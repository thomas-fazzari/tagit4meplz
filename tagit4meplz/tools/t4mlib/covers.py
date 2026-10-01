from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from t4mlib.images import JPEG, image_info
from t4mlib.proc import run_bytes

if TYPE_CHECKING:
    from pathlib import Path

    from t4mlib.style import Style


class CoverError(ValueError):
    pass


@dataclass(frozen=True)
class Cover:
    data: bytes
    mime: str
    width: int
    height: int


def prepare_cover(path: Path, style: Style) -> Cover:
    data = path.read_bytes()
    mime, width, height = image_info(data)
    if mime != JPEG or max(width, height) > style.cover_max_px:
        size = style.cover_max_px
        data = run_bytes(
            ["magick", str(path), "-resize", f"{size}x{size}>", "-strip", "-quality", str(style.cover_quality), "jpg:-"]
        )
        mime, width, height = image_info(data)
    if mime != JPEG or not width:
        message = f"{path}: conversion to JPEG failed"
        raise CoverError(message)
    return Cover(data, JPEG, width, height)

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from t4mlib.fields import NAMES

DEFAULT_STYLE = Path(__file__).resolve().parents[2] / "style.toml"


class StyleError(ValueError):
    pass


@dataclass(frozen=True)
class Style:
    compilation_albumartist: str
    featuring: Literal["title", "artist"]
    cover_max_px: int
    cover_min_px: int
    cover_quality: int
    min_lossy_kbps: int
    id3_version: Literal[3, 4]
    id3_separator: str
    required_fields: tuple[str, ...]


def load_style(path: str | Path | None = None) -> Style:
    path = Path(path or os.environ.get("T4M_STYLE") or DEFAULT_STYLE)
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        message = f"{path}: {error}"
        raise StyleError(message) from error

    featuring = _get(data, "titles", "featuring", str)
    if featuring not in ("title", "artist"):
        message = f"titles.featuring must be 'title' or 'artist', got {featuring!r}"
        raise StyleError(message)
    id3_version = _get(data, "id3", "version", int)
    if id3_version not in (3, 4):
        message = f"id3.version must be 3 or 4, got {id3_version}"
        raise StyleError(message)
    required = cast("object", data.get("required", {}).get("fields"))
    if not isinstance(required, list) or not all(
        isinstance(f, str) and f in NAMES for f in cast("list[object]", required)
    ):
        message = f"required.fields must list canonical field names: {NAMES}"
        raise StyleError(message)

    return Style(
        compilation_albumartist=_get(data, "compilation", "albumartist", str),
        featuring=featuring,
        cover_max_px=_get(data, "cover", "max_px", int),
        cover_min_px=_get(data, "cover", "min_px", int),
        cover_quality=_get(data, "cover", "quality", int),
        min_lossy_kbps=_get(data, "audio", "min_lossy_kbps", int),
        id3_version=id3_version,
        id3_separator=_get(data, "id3", "separator", str),
        required_fields=tuple(cast("list[str]", required)),
    )


def _get[T: (str, int, bool)](data: dict[str, object], section: str, key: str, kind: type[T]) -> T:
    table = data.get(section)
    value = cast("dict[str, object]", table).get(key) if isinstance(table, dict) else None
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        message = f"{section}.{key} must be a {kind.__name__}"
        raise StyleError(message)
    return value

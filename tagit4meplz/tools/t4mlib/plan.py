from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from t4mlib.fields import BY_NAME, NAMES
from t4mlib.media import is_audio

RAW_PREFIX = "raw:"
PICTURE_MODES = ("keep", "front-only", "none")

type PictureMode = Literal["keep", "front-only", "none"]


class PlanError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class FileChange:
    path: Path
    set: dict[str, list[str]]
    remove: tuple[str, ...]
    cover: Path | None
    pictures: PictureMode


def load_plan(source: Path) -> list[FileChange]:
    try:
        data = cast("object", json.loads(source.read_text()))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanError([f"{source}: {error}"]) from error
    if not isinstance(data, dict):
        raise PlanError(["plan must be a JSON object with a 'files' list"])
    plan = cast("dict[str, object]", data)
    root = Path(str(plan.get("root") or source.parent)).expanduser()
    entries = plan.get("files")
    if not isinstance(entries, list) or not entries:
        raise PlanError(["plan.files must be a non-empty list"])

    errors: list[str] = []
    changes: list[FileChange] = []
    seen: set[Path] = set()
    for index, entry in enumerate(cast("list[object]", entries)):
        where = f"files[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object")
            continue
        for change in _parse_entry(cast("dict[str, object]", entry), root, where, errors):
            if change.path in seen:
                errors.append(f"{where}: duplicate path {change.path}")
            seen.add(change.path)
            changes.append(change)
    if errors:
        raise PlanError(errors)
    return changes


def _parse_entry(entry: dict[str, object], root: Path, where: str, errors: list[str]) -> list[FileChange]:
    unknown = set(entry) - {"path", "paths", "set", "remove", "cover", "pictures"}
    if unknown:
        errors.append(f"{where}: unknown keys {sorted(unknown)}")
    paths = _parse_paths(entry, root, where, errors)

    values = _parse_set(entry.get("set", {}), where, errors)
    remove = _parse_remove(entry.get("remove", []), where, errors)
    errors.extend(f"{where}: {name} is both set and removed" for name in set(values) & set(remove))

    cover = entry.get("cover")
    cover_path = None
    if cover is not None:
        cover_path = (root / Path(str(cover)).expanduser()).resolve()
        if not cover_path.is_file():
            errors.append(f"{where}: cover {cover_path} does not exist")
    pictures = entry.get("pictures", "keep")
    if pictures not in PICTURE_MODES:
        errors.append(f"{where}: pictures must be one of {PICTURE_MODES}")
        pictures = "keep"
    if not values and not remove and cover_path is None and pictures == "keep":
        errors.append(f"{where}: no change")
    return [FileChange(path, values, remove, cover_path, pictures) for path in paths]


def _parse_paths(entry: dict[str, object], root: Path, where: str, errors: list[str]) -> list[Path]:
    raw_paths = entry.get("paths", [entry["path"]] if "path" in entry else [])
    if not isinstance(raw_paths, list) or not raw_paths or ("path" in entry and "paths" in entry):
        errors.append(f"{where}: give either path or a non-empty paths list")
        return []
    paths: list[Path] = []
    for raw_path in cast("list[object]", raw_paths):
        if not isinstance(raw_path, str) or not raw_path:
            errors.append(f"{where}: paths must be non-empty strings")
            continue
        path = (root / Path(raw_path).expanduser()).resolve()
        if not path.is_file():
            errors.append(f"{where}: {path} is not an existing file")
        elif not is_audio(path):
            errors.append(f"{where}: {path} is not a supported audio file")
        paths.append(path)
    return paths


def _parse_set(raw: object, where: str, errors: list[str]) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        errors.append(f"{where}.set: must be an object")
        return {}
    values: dict[str, list[str]] = {}
    for name, value in cast("dict[str, object]", raw).items():
        if name not in BY_NAME:
            errors.append(f"{where}.set: unknown field {name!r}. Known fields: {', '.join(NAMES)}")
            continue
        items = cast("list[object]", value) if isinstance(value, list) else [value]
        if not items or not all(isinstance(v, str | int) and not isinstance(v, bool) for v in items):
            errors.append(f"{where}.set.{name}: use a string, a number or a non-empty list of strings")
            continue
        texts = [str(v).strip() for v in items]
        if not all(texts):
            errors.append(f"{where}.set.{name}: empty value, use remove instead")
            continue
        if len(texts) > 1 and not BY_NAME[name].multi:
            errors.append(f"{where}.set.{name}: single-valued field")
            continue
        values[name] = texts
    return values


def _parse_remove(raw: object, where: str, errors: list[str]) -> tuple[str, ...]:
    if not isinstance(raw, list):
        errors.append(f"{where}.remove: must be a list")
        return ()
    names: list[str] = []
    for name in cast("list[object]", raw):
        if not isinstance(name, str) or not (
            name in BY_NAME or (name.startswith(RAW_PREFIX) and len(name) > len(RAW_PREFIX))
        ):
            errors.append(f"{where}.remove: {name!r} is neither a canonical field nor raw:<KEY>")
            continue
        names.append(name)
    return tuple(names)

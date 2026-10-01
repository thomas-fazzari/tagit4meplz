from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

from mutagen import id3
from mutagen.flac import FLAC
from mutagen.flac import Picture as FlacPicture
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, AtomDataType, MP4Cover, MP4FreeForm, MP4Tags

from t4mlib.fields import BY_NAME, PAIR_TOTALS, PAIRED, Field
from t4mlib.media import FRONT_COVER, Handle, mp4_values, open_handle
from t4mlib.plan import RAW_PREFIX

if TYPE_CHECKING:
    from collections.abc import Callable

    from mutagen.flac import VCFLACDict
    from mutagen.mp4 import MP4Value

    from t4mlib.covers import Cover
    from t4mlib.plan import FileChange
    from t4mlib.style import Style

UTF8 = 3
ID3V1_UPDATE = 1
ID3V24 = 4
COLOR_DEPTH = 24
PAIR_SEPARATOR = "/"
TRUE_VALUES = ("1", "true", "yes")

type State = dict[str, object]


class SnapshotMismatchError(ValueError):
    pass


def apply_change(path: Path, change: FileChange, cover: Cover | None, style: Style) -> None:
    handle = open_handle(path)
    if handle.tags is None:
        handle.add_tags()
    if isinstance(handle, FLAC):
        _apply_vorbis(handle, change)
    elif isinstance(handle, MP4):
        _apply_mp4(_mp4_tags(handle), change)
    else:
        _apply_id3(_id3_tags(handle), change)
    _apply_pictures(handle, change, cover)
    _save(handle, style)


def _id3_tags(handle: Handle) -> id3.ID3:
    tags = handle.tags
    if not isinstance(tags, id3.ID3):
        message = f"{handle.filename}: no id3.ID3 tag"
        raise TypeError(message)
    return tags


def _mp4_tags(handle: MP4) -> MP4Tags:
    if handle.tags is None:
        message = f"{handle.filename}: no MP4 tag"
        raise TypeError(message)
    return handle.tags


def _save(handle: Handle, style: Style, id3_version: int | None = None) -> None:
    if isinstance(handle, FLAC | MP4):
        handle.save()
    elif isinstance(handle, MP3):
        handle.save(v1=ID3V1_UPDATE, v2_version=id3_version or style.id3_version, v23_sep=style.id3_separator)
    else:
        handle.save(v2_version=id3_version or style.id3_version, v23_sep=style.id3_separator)


def _is_pair_field(name: str) -> bool:
    return name in PAIRED or name in PAIR_TOTALS


def _pair_updates(change: FileChange, key: Callable[[Field], str]) -> dict[str, dict[str, str]]:
    updates: dict[str, dict[str, str]] = {}
    changes = [*((n, v[0]) for n, v in change.set.items()), *((n, "") for n in change.remove)]
    for name, value in changes:
        if _is_pair_field(name):
            updates.setdefault(key(BY_NAME[name]), {})["number" if name in PAIRED else "total"] = value
    return updates


def _split_pair(text: str) -> tuple[str, str]:
    number, _, total = text.partition(PAIR_SEPARATOR)
    return number.strip(), total.strip()


def _apply_vorbis(handle: FLAC, change: FileChange) -> None:
    tags = handle.tags
    if tags is None:
        return
    for number_field, total_field in PAIRED.items():
        key = BY_NAME[number_field].vorbis[0]
        touched = {number_field, total_field} & {*change.set, *change.remove}
        if touched and key in tags and PAIR_SEPARATOR in tags[key][0]:
            number, total = _split_pair(tags[key][0])
            tags[key] = [number]
            total_key = BY_NAME[total_field].vorbis[0]
            if total and total_key not in tags:
                tags[total_key] = [total]
    for name, values in change.set.items():
        field = BY_NAME[name]
        _vorbis_delete(tags, field.vorbis)
        tags[field.vorbis[0]] = values
    for name in change.remove:
        keys = (name.removeprefix(RAW_PREFIX),) if name.startswith(RAW_PREFIX) else BY_NAME[name].vorbis
        _vorbis_delete(tags, keys)


def _vorbis_delete(tags: VCFLACDict, keys: tuple[str, ...]) -> None:
    for key in keys:
        if key in tags:
            del tags[key]


def _apply_id3(tags: id3.ID3, change: FileChange) -> None:
    for spec, update in _pair_updates(change, lambda f: f.id3).items():
        frame = tags.get(spec)
        number, total = _split_pair(frame.text[0]) if isinstance(frame, id3.TextFrame) and frame.text else ("", "")
        number, total = update.get("number", number), update.get("total", total)
        tags.delall(spec)
        if number:
            text = f"{number}{PAIR_SEPARATOR}{total}" if total else number
            tags.add(_text_frame(spec, [text]))
    for name, values in change.set.items():
        if not _is_pair_field(name):
            _id3_delete(tags, BY_NAME[name])
            tags.add(_id3_frame(BY_NAME[name], values))
    for name in change.remove:
        if name.startswith(RAW_PREFIX):
            key = name.removeprefix(RAW_PREFIX)
            if key in tags:
                del tags[key]
            else:
                tags.delall(key)
        elif not _is_pair_field(name):
            _id3_delete(tags, BY_NAME[name])


def _id3_delete(tags: id3.ID3, field: Field) -> None:
    spec = field.id3
    if spec.startswith("TXXX:"):
        wanted = spec.removeprefix("TXXX:").lower()
        for frame in tags.getall("TXXX"):
            if frame.desc.lower() == wanted:
                del tags[frame.HashKey]
    else:
        tags.delall(spec)


def _id3_frame(field: Field, values: list[str]) -> id3.Frame:
    spec = field.id3
    if spec.startswith("TXXX:"):
        return id3.TXXX(encoding=UTF8, desc=spec.removeprefix("TXXX:"), text=values)
    if spec.startswith("UFID:"):
        return id3.UFID(owner=spec.removeprefix("UFID:"), data=values[0].encode())
    if spec == "COMM":
        return id3.COMM(encoding=UTF8, lang="eng", desc="", text=values)
    return _text_frame(spec, values)


def _text_frame(spec: str, values: list[str]) -> id3.TextFrame:
    frame_type = id3.Frames[spec]
    if not issubclass(frame_type, id3.TextFrame):
        message = f"{spec} is not a text frame"
        raise TypeError(message)
    return frame_type(encoding=UTF8, text=values)


def _apply_mp4(tags: MP4Tags, change: FileChange) -> None:
    for atom, update in _pair_updates(change, lambda f: f.mp4).items():
        current = mp4_values(tags, atom) if atom in tags else []
        pair = current[0] if current and isinstance(current[0], tuple) else (0, 0)
        number = int(update.get("number", pair[0]) or 0)
        total = int(update.get("total", pair[1]) or 0)
        _mp4_delete(tags, atom)
        if number:
            tags[atom] = [(number, total)]
    for name, values in change.set.items():
        if not _is_pair_field(name):
            field = BY_NAME[name]
            _mp4_delete(tags, field.mp4)
            _mp4_set(tags, field.mp4, _mp4_values(field, values))
    for name in change.remove:
        if name.startswith(RAW_PREFIX):
            _mp4_delete(tags, name.removeprefix(RAW_PREFIX))
        elif not _is_pair_field(name):
            _mp4_delete(tags, BY_NAME[name].mp4)


def _mp4_set(tags: MP4Tags, atom: str, values: list[MP4Value]) -> None:
    tags[atom] = values[0] if len(values) == 1 and isinstance(values[0], bool) else values


def _mp4_delete(tags: MP4Tags, atom: str) -> None:
    for key in [k for k in tags if k.lower() == atom.lower()]:
        del tags[key]


def _mp4_values(field: Field, values: list[str]) -> list[MP4Value]:
    if field.mp4.startswith("----:"):
        return [MP4FreeForm(v.encode(), AtomDataType.UTF8) for v in values]
    if field.mp4 == "tmpo":
        return [round(float(values[0]))]
    if field.mp4 == "cpil":
        return [values[0].lower() in TRUE_VALUES]
    return list(values)


def _apply_pictures(handle: Handle, change: FileChange, cover: Cover | None) -> None:
    if cover is None and change.pictures == "keep":
        return
    if isinstance(handle, FLAC):
        flac_keep = [] if change.pictures == "none" else _front(handle.pictures, lambda p: p.type)
        handle.clear_pictures()
        for picture in flac_keep if cover is None else [_flac_cover(cover)]:
            handle.add_picture(picture)
    elif isinstance(handle, MP4):
        tags = _mp4_tags(handle)
        covers = [c for c in (mp4_values(tags, "covr") if "covr" in tags else []) if isinstance(c, MP4Cover)]
        mp4_keep: list[MP4Value] = [] if change.pictures == "none" else [*covers[:1]]
        new: list[MP4Value] = mp4_keep if cover is None else [MP4Cover(cover.data, MP4Cover.FORMAT_JPEG)]
        _mp4_delete(tags, "covr")
        if new:
            tags["covr"] = new
    else:
        tags = _id3_tags(handle)
        id3_keep = [] if change.pictures == "none" else _front(tags.getall("APIC"), lambda f: f.type)
        tags.delall("APIC")
        frames = (
            id3_keep if cover is None else [id3.APIC(encoding=UTF8, mime=cover.mime, type=FRONT_COVER, data=cover.data)]
        )
        for frame in frames:
            tags.add(frame)


def _front[T](items: list[T], kind: Callable[[T], int]) -> list[T]:
    front = [item for item in items if kind(item) == FRONT_COVER]
    return (front or items)[:1]


def _flac_cover(cover: Cover) -> FlacPicture:
    picture = FlacPicture()
    picture.type = FRONT_COVER
    picture.mime = cover.mime
    picture.width = cover.width
    picture.height = cover.height
    picture.depth = COLOR_DEPTH
    picture.data = cover.data
    return picture


def capture_state(path: Path) -> State:
    handle = open_handle(path)
    if isinstance(handle, FLAC):
        return {
            "kind": "flac",
            "tags": [list(item) for item in handle.tags] if handle.tags is not None else None,
            "pictures": [_b64(p.write()) for p in handle.pictures],
        }
    if isinstance(handle, MP4):
        tags = handle.tags
        items = [[k, [_encode_mp4(v) for v in mp4_values(tags, k)]] for k in tags] if tags is not None else None
        return {"kind": "mp4", "tags": items}
    id3_tags = handle.tags
    if id3_tags is None:
        return {"kind": "id3", "version": None, "tag": None}
    version = id3_tags.version[1] if id3_tags.version[1] in (3, 4) else ID3V24
    with tempfile.TemporaryDirectory() as tmp:
        tag_file = Path(tmp) / "tag.id3"
        tag_file.touch()
        standalone = id3.ID3()
        for frame in id3_tags.values():
            standalone.add(frame)
        standalone.save(tag_file, v1=0, v2_version=version)
        return {"kind": "id3", "version": version, "tag": _b64(tag_file.read_bytes())}


def restore_state(path: Path, state: State, style: Style) -> None:
    handle = open_handle(path)
    kind = state["kind"]
    if isinstance(handle, FLAC) and kind == "flac":
        _restore_flac(handle, state)
    elif isinstance(handle, MP4) and kind == "mp4":
        _restore_mp4(handle, state)
    elif not isinstance(handle, FLAC | MP4) and kind == "id3":
        _restore_id3(handle, state, style)
    else:
        message = f"{path}: snapshot kind {kind} does not match the file format"
        raise SnapshotMismatchError(message)


def _restore_flac(handle: FLAC, state: State) -> None:
    if handle.tags is None:
        handle.add_tags()
    tags = handle.tags
    if tags is not None:
        tags.clear()
        for key, value in cast("list[list[str]] | None", state["tags"]) or []:
            tags.append((key, value))
    handle.clear_pictures()
    for blob in cast("list[str]", state["pictures"]):
        handle.add_picture(FlacPicture(base64.b64decode(blob)))
    handle.save()


def _restore_mp4(handle: MP4, state: State) -> None:
    items = cast("list[tuple[str, list[dict[str, object]]]] | None", state["tags"])
    if items is None:
        handle.delete()
        return
    if handle.tags is None:
        handle.add_tags()
    tags = _mp4_tags(handle)
    tags.clear()
    for key, values in items:
        _mp4_set(tags, key, [_decode_mp4(v) for v in values])
    handle.save()


def _restore_id3(handle: Handle, state: State, style: Style) -> None:
    blob = cast("str | None", state["tag"])
    if blob is None:
        handle.delete()
        return
    with tempfile.TemporaryDirectory() as tmp:
        tag_file = Path(tmp) / "tag.id3"
        tag_file.write_bytes(base64.b64decode(blob))
        saved = id3.ID3(tag_file)
    if handle.tags is None:
        handle.add_tags()
    tags = _id3_tags(handle)
    tags.clear()
    for frame in saved.values():
        tags.add(frame)
    _save(handle, style, id3_version=cast("int", state["version"]))


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _encode_mp4(value: MP4Value) -> dict[str, object]:
    if isinstance(value, MP4Cover):
        return {"cover": _b64(value), "format": value.imageformat}
    if isinstance(value, MP4FreeForm):
        return {"freeform": _b64(value), "format": value.dataformat}
    if isinstance(value, bool):
        return {"bool": value}
    if isinstance(value, int):
        return {"int": value}
    if isinstance(value, tuple):
        return {"pair": list(value)}
    return {"text": value}


def _decode_mp4(value: dict[str, object]) -> MP4Value:
    if "cover" in value:
        return MP4Cover(base64.b64decode(str(value["cover"])), cast("int", value["format"]))
    if "freeform" in value:
        return MP4FreeForm(base64.b64decode(str(value["freeform"])), cast("int", value["format"]))
    if "pair" in value:
        number, total = cast("list[int]", value["pair"])
        return (number, total)
    if "bool" in value:
        return bool(value["bool"])
    if "int" in value:
        return cast("int", value["int"])
    return str(value["text"])

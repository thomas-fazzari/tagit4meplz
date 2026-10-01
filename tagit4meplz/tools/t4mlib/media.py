from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import mutagen
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import UFID, TextFrame
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE

from t4mlib.fields import FIELDS, NAMES, PAIRED, Field
from t4mlib.images import JPEG, PNG, image_info

if TYPE_CHECKING:
    from mutagen.flac import Picture as FlacPicture
    from mutagen.id3 import ID3, Frame
    from mutagen.mp4 import MP4Tags, MP4Value

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".aif", ".aiff", ".wav"}
LOSSLESS_FORMATS = {"flac", "aiff", "wav", "alac"}
FRONT_COVER = 3

type Handle = FLAC | MP3 | AIFF | WAVE | MP4
type Tags = dict[str, list[str]]


class UnsupportedFileError(Exception):
    pass


@dataclass
class Picture:
    type: int
    mime: str | None
    declared_mime: str
    description: str
    width: int
    height: int
    declared_width: int
    declared_height: int
    size: int
    sha1: str


@dataclass
class Audio:
    format: str
    lossless: bool
    duration: float
    sample_rate: int
    bits_per_sample: int | None
    channels: int
    bitrate_kbps: int


@dataclass
class Track:
    path: str
    audio: Audio
    tags: Tags
    raw: Tags
    pictures: list[Picture] = field(default_factory=list[Picture])

    def first(self, name: str) -> str:
        values = self.tags.get(name) or []
        return values[0] if values else ""


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS and not path.name.startswith(".")


def open_handle(path: Path) -> Handle:
    handle = mutagen.File(path)
    if isinstance(handle, FLAC | MP3 | AIFF | WAVE | MP4):
        return handle
    message = f"{path}: not a supported audio file"
    raise UnsupportedFileError(message)


def read_track(path: str | Path) -> Track:
    path = Path(path)
    handle = open_handle(path)
    if isinstance(handle, FLAC):
        tags, raw = _read_vorbis(handle)
        pictures = [flac_picture(p) for p in handle.pictures]
    elif isinstance(handle, MP4):
        tags, raw = _read_mp4(handle.tags)
        covers = mp4_values(handle.tags, "covr") if handle.tags is not None and "covr" in handle.tags else []
        pictures = [mp4_picture(c) for c in covers if isinstance(c, MP4Cover)]
    else:
        id3 = handle.tags
        tags, raw = _read_id3(id3)
        pictures = [make_picture(f.type, f.mime, f.desc, f.data) for f in (id3.getall("APIC") if id3 else [])]
    _split_pairs(tags)
    ordered = {name: tags[name] for name in NAMES if name in tags}
    return Track(str(path), _audio(handle), ordered, raw, pictures)


def format_of(handle: Handle) -> str:
    if isinstance(handle, FLAC):
        return "flac"
    if isinstance(handle, MP3):
        return "mp3"
    if isinstance(handle, AIFF):
        return "aiff"
    if isinstance(handle, WAVE):
        return "wav"
    return "alac" if handle.info.codec == "alac" else "aac"


def _audio(handle: Handle) -> Audio:
    info = handle.info
    fmt = format_of(handle)
    return Audio(
        format=fmt,
        lossless=fmt in LOSSLESS_FORMATS,
        duration=round(info.length or 0, 3),
        sample_rate=info.sample_rate or 0,
        bits_per_sample=None if isinstance(handle, MP3) else handle.info.bits_per_sample,
        channels=info.channels or 0,
        bitrate_kbps=(info.bitrate or 0) // 1000,
    )


def _read_vorbis(handle: FLAC) -> tuple[Tags, Tags]:
    raw: Tags = {}
    if handle.tags is not None:
        for key, value in handle.tags:
            raw.setdefault(key.upper(), []).append(value)
    tags: Tags = {}
    for f in FIELDS:
        key = next((k for k in f.vorbis if k in raw), None)
        if key:
            tags[f.name] = list(raw[key])
    return tags, raw


def _read_id3(id3: ID3 | None) -> tuple[Tags, Tags]:
    tags: Tags = {}
    raw: Tags = {}
    if id3 is None:
        return tags, raw
    for key, frame in id3.items():
        if key.startswith("APIC"):
            continue
        raw[key] = frame_text(frame)
    for f in FIELDS:
        if f.name in PAIRED.values():
            continue
        values = _id3_values(id3, f)
        if values is not None:
            tags[f.name] = values
    return tags, raw


def _id3_values(id3: ID3, f: Field) -> list[str] | None:
    spec = f.id3
    if spec.startswith("TXXX:"):
        wanted = spec[5:].lower()
        frame = next((fr for fr in id3.getall("TXXX") if fr.desc.lower() == wanted), None)
        return [str(t) for t in frame.text] if frame else None
    if spec.startswith("UFID:"):
        frame = id3.get(spec)
        return frame_text(frame) if frame else None
    if spec == "COMM":
        comments = sorted(id3.getall("COMM"), key=lambda fr: fr.desc != "")
        return [str(t) for t in comments[0].text] if comments else None
    if spec == "TCON":
        genres = [g for fr in id3.getall("TCON") for g in fr.genres]
        return genres or None
    texts = [str(t) for fr in id3.getall(spec) if isinstance(fr, TextFrame) for t in fr.text]
    return texts or None


def frame_text(frame: Frame) -> list[str]:
    if isinstance(frame, TextFrame):
        return [str(t) for t in frame.text]
    if isinstance(frame, UFID):
        return [frame.data.decode("utf-8", "replace")]
    return [str(frame)]


def _read_mp4(mp4tags: MP4Tags | None) -> tuple[Tags, Tags]:
    tags: Tags = {}
    raw: Tags = {}
    if not mp4tags:
        return tags, raw
    by_lower = {k.lower(): k for k in mp4tags}
    for key in mp4tags:
        if key != "covr":
            raw[key] = [_mp4_text(v) for v in mp4_values(mp4tags, key)]
    for f in FIELDS:
        key = by_lower.get(f.mp4.lower())
        if key is None:
            continue
        values = mp4_values(mp4tags, key)
        if f.mp4 in ("trkn", "disk"):
            pair = values[0] if values and isinstance(values[0], tuple) else (0, 0)
            value = pair[0] if f.name in PAIRED else pair[1]
            if value:
                tags[f.name] = [str(value)]
        elif f.mp4 == "cpil":
            tags[f.name] = ["1" if values and values[0] else "0"]
        else:
            tags[f.name] = [_mp4_text(v) for v in values]
    return tags, raw


def mp4_values(tags: MP4Tags, key: str) -> list[MP4Value]:
    values = tags[key]
    return values if isinstance(values, list) else [values]


def _mp4_text(value: MP4Value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, tuple):
        return f"{value[0]}/{value[1]}"
    return str(value)


def _split_pairs(tags: Tags) -> None:
    for number_field, total_field in PAIRED.items():
        values = tags.get(number_field)
        if not values:
            continue
        number, _, total = values[0].partition("/")
        tags[number_field] = [_strip_zeros(number)]
        if total and not tags.get(total_field):
            tags[total_field] = [_strip_zeros(total)]
    for total_field in PAIRED.values():
        if tags.get(total_field):
            tags[total_field] = [_strip_zeros(tags[total_field][0])]


def _strip_zeros(value: str) -> str:
    value = value.strip()
    return (value.lstrip("0") or "0") if value.isdigit() else value


def make_picture(ptype: int, mime: str, desc: str, data: bytes, declared: tuple[int, int] = (0, 0)) -> Picture:
    real_mime, width, height = image_info(data)
    return Picture(
        type=int(ptype),
        mime=real_mime,
        declared_mime=mime or "",
        description=desc or "",
        width=width,
        height=height,
        declared_width=declared[0],
        declared_height=declared[1],
        size=len(data),
        sha1=hashlib.sha1(data, usedforsecurity=False).hexdigest()[:12],
    )


def flac_picture(p: FlacPicture) -> Picture:
    return make_picture(p.type, p.mime, p.desc, p.data, (p.width, p.height))


def mp4_picture(cover: MP4Cover) -> Picture:
    mime = PNG if cover.imageformat == MP4Cover.FORMAT_PNG else JPEG
    return make_picture(FRONT_COVER, mime, "", bytes(cover))

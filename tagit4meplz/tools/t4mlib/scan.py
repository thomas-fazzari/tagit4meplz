from __future__ import annotations

import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, NotRequired, TypedDict

from mutagen import MutagenError

from t4mlib.fields import BY_NAME
from t4mlib.media import FRONT_COVER, Track, UnsupportedFileError, is_audio, read_track

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from t4mlib.style import Style

FEAT = re.compile(r"\b(feat\.?|ft\.|featuring)\s+(.+?)(?:\)|$)", re.IGNORECASE)
REPEATED_PAREN = re.compile(r"(\([^()]+\))\s*\1")
ALBUMARTIST_VARIANTS = {"various", "va", "v.a.", "various artist", "various artists"}
ALBUM_CONSISTENT_FIELDS = ("albumartist", "date", "label", "disctotal")


class Issue(TypedDict):
    code: str
    detail: NotRequired[str]


class FileReport(TypedDict):
    path: str
    issues: list[Issue]


class AlbumReport(TypedDict):
    album: str
    albumartist: str
    label: str
    date: str
    count: int
    covers: dict[str, int]
    issues: list[Issue]
    files: list[str]


class Summary(TypedDict):
    files: int
    albums: int
    issues: dict[str, int]


class ScanReport(TypedDict):
    root: str
    summary: Summary
    library_issues: list[Issue]
    albums: list[AlbumReport]
    files: list[FileReport]


def issue(code: str, detail: str = "") -> Issue:
    return Issue(code=code, detail=detail) if detail else Issue(code=code)


def collect(root: Path, *, recursive: bool = True) -> list[Path]:
    if root.is_file():
        return [root]
    candidates = root.rglob("*") if recursive else root.iterdir()
    return sorted(
        p
        for p in candidates
        if p.is_file() and is_audio(p) and not any(part.startswith(".") for part in p.relative_to(root).parts)
    )


def read_all(paths: list[Path], jobs: int = 8) -> tuple[list[Track], list[tuple[Path, str]]]:
    def read(path: Path) -> Track | tuple[Path, str]:
        try:
            return read_track(path)
        except (MutagenError, OSError, UnsupportedFileError) as error:
            return path, str(error)

    with ThreadPoolExecutor(jobs) as pool:
        results = list(pool.map(read, paths))
    return [r for r in results if isinstance(r, Track)], [r for r in results if not isinstance(r, Track)]


def file_issues(track: Track, style: Style) -> list[Issue]:
    return [*_tag_issues(track, style), *_picture_issues(track, style), *_credit_issues(track, style)]


def _tag_issues(track: Track, style: Style) -> list[Issue]:
    issues: list[Issue] = [
        issue("missing-field", name)
        for name in style.required_fields
        if not any(v.strip() for v in track.tags.get(name, []))
    ]
    for name, values in track.tags.items():
        if values and not any(v.strip() for v in values) and name not in style.required_fields:
            issues.append(issue("empty-field", name))
        if len(values) > 1 and not BY_NAME[name].multi:
            issues.append(issue("multiple-values", f"{name}={values}"))
    if not track.audio.lossless and track.audio.bitrate_kbps < style.min_lossy_kbps:
        issues.append(issue("low-bitrate", f"{track.audio.format} {track.audio.bitrate_kbps} kbps"))
    return issues


def _credit_issues(track: Track, style: Style) -> list[Issue]:
    issues: list[Issue] = []
    artist, title = track.first("artist"), track.first("title")
    if style.featuring == "title" and FEAT.search(artist):
        issues.append(issue("featuring-in-artist", artist))
    feat = FEAT.search(title)
    if feat and feat.group(2).strip().casefold() in artist.casefold():
        issues.append(issue("featured-artist-in-artist", f"{artist} / {title}"))
    if artist.endswith(" - Topic"):
        issues.append(issue("youtube-topic-artist", artist))
    if REPEATED_PAREN.search(title):
        issues.append(issue("repeated-parenthetical", title))
    albumartist = track.first("albumartist")
    if albumartist != style.compilation_albumartist and albumartist.casefold() in ALBUMARTIST_VARIANTS:
        issues.append(issue("albumartist-variant", f"{albumartist} -> {style.compilation_albumartist}"))
    return issues


def _picture_issues(track: Track, style: Style) -> list[Issue]:
    pictures = track.pictures
    if not pictures:
        return [issue("no-cover")]
    issues: list[Issue] = []
    if len(pictures) > 1:
        summary = ", ".join(f"type {p.type} {p.width}x{p.height}" for p in pictures)
        issues.append(issue("multiple-pictures", summary))
    front = next((p for p in pictures if p.type == FRONT_COVER), pictures[0])
    if min(front.width, front.height) < style.cover_min_px:
        issues.append(issue("small-cover", f"{front.width}x{front.height}"))
    declared = (front.declared_width, front.declared_height)
    if track.audio.format == "flac" and declared != (front.width, front.height):
        issues.append(issue("picture-dims-mismatch", f"declared {declared[0]}x{declared[1]}"))
    if front.mime and front.declared_mime and front.mime != front.declared_mime:
        issues.append(issue("picture-mime-mismatch", f"{front.declared_mime} is {front.mime}"))
    return issues


def album_issues(tracks: list[Track]) -> list[Issue]:
    issues: list[Issue] = []
    for name in ALBUM_CONSISTENT_FIELDS:
        values = Counter(tuple(t.tags.get(name, [])) for t in tracks)
        if len(values) > 1:
            issues.append(issue("inconsistent-field", f"{name}: {_counts(values)}"))
    covers = Counter(t.pictures[0].sha1 if t.pictures else None for t in tracks)
    if len(covers) > 1:
        issues.append(issue("inconsistent-cover", _counts(covers)))
    issues.extend(_numbering_issues(tracks))
    return issues


def _numbering_issues(tracks: list[Track]) -> list[Issue]:
    issues: list[Issue] = []
    discs: dict[str, list[Track]] = defaultdict(list)
    for t in tracks:
        discs[t.first("discnumber") or "1"].append(t)
    album_wide_total = len(discs) > 1 and {t.first("tracktotal") for t in tracks} == {str(len(tracks))}
    if album_wide_total:
        issues.append(issue("tracktotal-is-album-total", f"tracktotal={len(tracks)} on {len(discs)} discs"))
    for disc, disc_tracks in sorted(discs.items()):
        numbers = _ints(t.first("tracknumber") for t in disc_tracks)
        duplicates = sorted(n for n, c in Counter(numbers).items() if c > 1)
        if duplicates:
            issues.append(issue("duplicate-tracknumber", f"disc {disc}: {duplicates}"))
        totals = [] if album_wide_total else _ints(t.first("tracktotal") for t in disc_tracks)
        expected = max(totals + numbers, default=0)
        missing = sorted(set(range(1, expected + 1)) - set(numbers))
        if missing:
            issues.append(issue("missing-tracks", f"disc {disc}: {missing} of {expected}"))
    return issues


def naming_variants(album_names: list[str]) -> list[Issue]:
    families: dict[str, set[str]] = defaultdict(set)
    for name in album_names:
        skeleton = re.sub(r"\d+", "#", name)
        normalized = re.sub(r"\b(pt|part|vol|volume)\b\.?", "part", skeleton.casefold())
        normalized = re.sub(r"[\W_]+", " ", normalized).strip()
        families[normalized].add(skeleton)
    return [
        issue("album-naming-variants", " | ".join(sorted(skeletons)))
        for skeletons in families.values()
        if len(skeletons) > 1
    ]


def scan(root: Path, style: Style, *, recursive: bool = True, jobs: int = 8) -> ScanReport:
    tracks, failures = read_all(collect(root, recursive=recursive), jobs)
    base = root if root.is_dir() else root.parent

    def rel(path: str | Path) -> str:
        return str(Path(path).relative_to(base))

    by_album: dict[tuple[str, str], list[Track]] = defaultdict(list)
    for t in tracks:
        by_album[str(Path(t.path).parent), t.first("album").strip().casefold()].append(t)
    albums = [_album_report(key[1], album_tracks, rel) for key, album_tracks in sorted(by_album.items())]

    files = [FileReport(path=rel(t.path), issues=file_issues(t, style)) for t in sorted(tracks, key=lambda t: t.path)]
    files.extend(FileReport(path=rel(path), issues=[issue("unreadable", error)]) for path, error in failures)
    files = [f for f in files if f["issues"]]

    library_issues = naming_variants([a["album"] for a in albums if a["album"]])
    counter = Counter(i["code"] for f in files for i in f["issues"])
    counter.update(i["code"] for a in albums for i in a["issues"])
    counter.update(i["code"] for i in library_issues)
    return ScanReport(
        root=str(root),
        summary=Summary(files=len(tracks) + len(failures), albums=len(albums), issues=dict(counter.most_common())),
        library_issues=library_issues,
        albums=albums,
        files=files,
    )


def _album_report(key: str, tracks: list[Track], rel: Callable[[str], str]) -> AlbumReport:
    tracks.sort(key=lambda t: (_int(t.first("discnumber")), _int(t.first("tracknumber")), t.path))
    first = tracks[0]
    covers = Counter(f"{t.pictures[0].width}x{t.pictures[0].height}" if t.pictures else "none" for t in tracks)
    return AlbumReport(
        album=first.first("album") if key else "",
        albumartist=first.first("albumartist"),
        label=first.first("label"),
        date=first.first("date"),
        count=len(tracks),
        covers=dict(covers),
        issues=album_issues(tracks) if key else [issue("no-album")],
        files=[rel(t.path) for t in tracks],
    )


def _counts[K](counter: Counter[K]) -> str:
    return "; ".join(f"{k!r} x{c}" for k, c in counter.most_common())


def _ints(values: Iterable[str]) -> list[int]:
    return [int(v) for v in values if v.isdigit()]


def _int(value: str) -> int:
    return int(value) if value.isdigit() else 0

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from mutagen import MutagenError

from t4mlib.covers import Cover, CoverError, prepare_cover
from t4mlib.fields import NAMES
from t4mlib.media import Track, read_track
from t4mlib.native import SnapshotMismatchError, apply_change, capture_state, restore_state
from t4mlib.plan import RAW_PREFIX
from t4mlib.proc import ToolError, audio_hash, clone_file
from t4mlib.runs import (
    FieldDiff,
    FileRecord,
    Manifest,
    load_manifest,
    new_run,
    read_snapshot,
    run_dir_of,
    save_manifest,
    write_snapshot,
)

if TYPE_CHECKING:
    from t4mlib.media import Tags
    from t4mlib.plan import FileChange
    from t4mlib.style import Style

WRITE_ERRORS = (MutagenError, OSError, ToolError, SnapshotMismatchError, ValueError, TypeError)


class AudioChangedError(RuntimeError):
    pass


def preview(changes: list[FileChange], style: Style) -> list[FileRecord]:
    covers = _prepare_covers(changes, style)
    files: list[FileRecord] = []
    for change in changes:
        before = read_track(change.path)
        after_tags = _planned_tags(before.tags, change)
        diff = diff_tags(before.tags, after_tags)
        diff.extend(_raw_diff(change, before, None))
        new_pictures = _planned_pictures(before, change, covers.get(change.path))
        if new_pictures is not None and new_pictures != _pictures(before):
            diff.append(FieldDiff(field="pictures", before=_pictures(before), after=new_pictures))
        files.append(FileRecord(path=str(change.path), status="ok", diff=diff))
    return files


def apply_plan(changes: list[FileChange], style: Style, source: str) -> Manifest:
    covers = _prepare_covers(changes, style)
    manifest, run_dir = new_run("write", source)
    write_snapshot(run_dir, [(c.path, capture_state(c.path)) for c in changes])
    backup = run_dir / "backup.tmp"
    for change in changes:
        manifest["files"].append(_write_one(change, covers.get(change.path), style, backup))
        backup.unlink(missing_ok=True)
        save_manifest(run_dir, manifest)
    return manifest


def _write_one(change: FileChange, cover: Cover | None, style: Style, backup: Path) -> FileRecord:
    path = change.path
    try:
        before = read_track(path)
        before_hash = audio_hash(path)
        clone_file(path, backup)
    except WRITE_ERRORS as error:
        return FileRecord(path=str(path), status="skipped", error=str(error))
    try:
        apply_change(path, change, cover, style)
        after_hash = _same_audio(path, before_hash)
    except Exception as error:  # noqa: BLE001 - any failure must restore the original file
        backup.replace(path)
        return FileRecord(path=str(path), status="failed", error=f"{error}. File restored from backup.")
    after = read_track(path)
    diff = diff_tags(before.tags, after.tags)
    diff.extend(_raw_diff(change, before, after))
    if _pictures(before) != _pictures(after):
        diff.append(FieldDiff(field="pictures", before=_pictures(before), after=_pictures(after)))
    return FileRecord(path=str(path), status="ok", audio_hash=after_hash, diff=diff)


def _same_audio(path: Path, expected: str) -> str:
    current = audio_hash(path)
    if current != expected:
        message = "audio stream changed during the tag write"
        raise AudioChangedError(message)
    return current


def undo(run_id: str, style: Style, *, force: bool) -> Manifest:
    source_dir = run_dir_of(run_id)
    source = load_manifest(source_dir)
    if source["kind"] == "quarantine":
        return _undo_quarantine(source)
    states = read_snapshot(source_dir)
    targets = [f for f in source["files"] if f["status"] == "ok"]
    manifest, run_dir = new_run("undo", run_id)
    ready: list[tuple[Path, str]] = []
    for record in targets:
        path = Path(record["path"])
        try:
            current_hash = audio_hash(path)
        except ToolError as error:
            manifest["files"].append(FileRecord(path=str(path), status="skipped", error=str(error)))
            continue
        if not force and current_hash != record.get("audio_hash", current_hash):
            message = "audio changed since the run. Use --force to restore tags anyway"
            manifest["files"].append(FileRecord(path=str(path), status="skipped", error=message))
            continue
        ready.append((path, current_hash))
    write_snapshot(run_dir, [(path, capture_state(path)) for path, _ in ready])
    for path, current_hash in ready:
        before = read_track(path)
        try:
            restore_state(path, states[str(path)], style)
        except WRITE_ERRORS as error:
            manifest["files"].append(FileRecord(path=str(path), status="failed", error=str(error)))
            continue
        status = "ok" if audio_hash(path) == current_hash else "failed"
        diff = diff_tags(before.tags, read_track(path).tags)
        manifest["files"].append(FileRecord(path=str(path), status=status, audio_hash=current_hash, diff=diff))
    save_manifest(run_dir, manifest)
    return manifest


def quarantine(paths: list[Path], reason: str) -> Manifest:
    manifest, run_dir = new_run("quarantine", reason)
    target_dir = run_dir / "files"
    target_dir.mkdir()
    for index, path in enumerate(paths):
        target = target_dir / f"{index:04}-{path.name}"
        try:
            shutil.move(path, target)
        except OSError as error:
            manifest["files"].append(FileRecord(path=str(path), status="failed", error=str(error)))
            continue
        record = FileRecord(path=str(path), status="ok", quarantined_to=str(target), reason=reason)
        manifest["files"].append(record)
    save_manifest(run_dir, manifest)
    return manifest


def _undo_quarantine(source: Manifest) -> Manifest:
    manifest, run_dir = new_run("undo", source["id"])
    for record in source["files"]:
        moved = record.get("quarantined_to")
        if record["status"] != "ok" or moved is None:
            continue
        path = Path(record["path"])
        if path.exists():
            manifest["files"].append(FileRecord(path=str(path), status="skipped", error="original path is taken"))
            continue
        shutil.move(moved, path)
        manifest["files"].append(FileRecord(path=str(path), status="ok"))
    save_manifest(run_dir, manifest)
    return manifest


def diff_tags(before: Tags, after: Tags) -> list[FieldDiff]:
    return [
        FieldDiff(field=name, before=before.get(name, []), after=after.get(name, []))
        for name in NAMES
        if before.get(name, []) != after.get(name, [])
    ]


def _raw_diff(change: FileChange, before: Track, after: Track | None) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    for name in change.remove:
        if not name.startswith(RAW_PREFIX):
            continue
        key = name.removeprefix(RAW_PREFIX).casefold()
        old = _raw_value(before, key)
        new = _raw_value(after, key) if after else []
        if old != new:
            diffs.append(FieldDiff(field=name, before=old, after=new))
    return diffs


def _raw_value(track: Track, key: str) -> list[str]:
    for name, values in track.raw.items():
        if name.casefold() == key:
            return values
    return []


def _planned_tags(tags: Tags, change: FileChange) -> Tags:
    planned = {**tags, **change.set}
    for name in change.remove:
        planned.pop(name, None)
    return planned


def _planned_pictures(track: Track, change: FileChange, cover: Cover | None) -> list[str] | None:
    if cover is not None:
        return [f"type 3 {cover.width}x{cover.height} (new)"]
    if change.pictures == "none":
        return []
    if change.pictures == "front-only":
        return _pictures(track)[:1]
    return None


def _pictures(track: Track) -> list[str]:
    return [f"type {p.type} {p.width}x{p.height} {p.sha1}" for p in track.pictures]


def _prepare_covers(changes: list[FileChange], style: Style) -> dict[Path, Cover]:
    prepared: dict[Path, Cover] = {}
    by_source: dict[Path, Cover] = {}
    for change in changes:
        if change.cover is None:
            continue
        if change.cover not in by_source:
            try:
                by_source[change.cover] = prepare_cover(change.cover, style)
            except (CoverError, ToolError, OSError) as error:
                message = f"{change.cover}: {error}"
                raise CoverError(message) from error
        prepared[change.path] = by_source[change.cover]
    return prepared

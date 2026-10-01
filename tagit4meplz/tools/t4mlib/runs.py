from __future__ import annotations

import json
import os
import secrets
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict, cast

if TYPE_CHECKING:
    from t4mlib.native import State

SNAPSHOT = "snapshot.zip"
MANIFEST = "manifest.json"

type RunKind = Literal["write", "undo", "quarantine"]
type Status = Literal["ok", "failed", "skipped"]


class FieldDiff(TypedDict):
    field: str
    before: list[str]
    after: list[str]


class FileRecord(TypedDict):
    path: str
    status: Status
    error: NotRequired[str]
    audio_hash: NotRequired[str]
    diff: NotRequired[list[FieldDiff]]
    quarantined_to: NotRequired[str]
    reason: NotRequired[str]


class Manifest(TypedDict):
    id: str
    kind: RunKind
    created: str
    source: str
    files: list[FileRecord]


class RunSummary(TypedDict):
    id: str
    kind: RunKind
    created: str
    source: str
    files: int
    failed: int


class RunNotFoundError(LookupError):
    pass


def state_home() -> Path:
    return Path(os.environ.get("T4M_STATE") or Path.home() / ".local" / "state" / "tagit4meplz").expanduser()


def runs_home() -> Path:
    return state_home() / "runs"


def new_run(kind: RunKind, source: str) -> tuple[Manifest, Path]:
    now = datetime.now(UTC)
    run_id = f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    run_dir = runs_home() / run_id
    run_dir.mkdir(parents=True)
    manifest = Manifest(id=run_id, kind=kind, created=now.isoformat(timespec="seconds"), source=source, files=[])
    save_manifest(run_dir, manifest)
    return manifest, run_dir


def run_dir_of(run_id: str) -> Path:
    run_dir = runs_home() / run_id
    if not (run_dir / MANIFEST).is_file():
        message = f"run {run_id} not found in {runs_home()}"
        raise RunNotFoundError(message)
    return run_dir


def save_manifest(run_dir: Path, manifest: Manifest) -> None:
    tmp = run_dir / f"{MANIFEST}.tmp"
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    tmp.replace(run_dir / MANIFEST)


def load_manifest(run_dir: Path) -> Manifest:
    return cast("Manifest", json.loads((run_dir / MANIFEST).read_text()))


def write_snapshot(run_dir: Path, states: list[tuple[Path, State]]) -> None:
    with zipfile.ZipFile(run_dir / SNAPSHOT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, (path, state) in enumerate(states):
            entry = {"path": str(path), "state": state}
            archive.writestr(f"files/{index:04}.json", json.dumps(entry, ensure_ascii=False))


def read_snapshot(run_dir: Path) -> dict[str, State]:
    states: dict[str, State] = {}
    with zipfile.ZipFile(run_dir / SNAPSHOT) as archive:
        for name in archive.namelist():
            entry = cast("dict[str, object]", json.loads(archive.read(name)))
            states[str(entry["path"])] = cast("State", entry["state"])
    return states


def forget_run(run_id: str) -> Path:
    run_dir = run_dir_of(run_id)
    if load_manifest(run_dir)["kind"] == "quarantine" and any((run_dir / "files").iterdir()):
        message = f"run {run_id} still holds quarantined files. Undo it or move the files first"
        raise RunNotFoundError(message)
    shutil.rmtree(run_dir)
    return run_dir


def list_runs(limit: int) -> list[RunSummary]:
    if not runs_home().is_dir():
        return []
    summaries: list[RunSummary] = []
    for run_dir in sorted(runs_home().iterdir(), reverse=True)[:limit]:
        if (run_dir / MANIFEST).is_file():
            m = load_manifest(run_dir)
            failed = sum(1 for f in m["files"] if f["status"] == "failed")
            summaries.append(
                RunSummary(
                    id=m["id"],
                    kind=m["kind"],
                    created=m["created"],
                    source=m["source"],
                    files=len(m["files"]),
                    failed=failed,
                )
            )
    return summaries

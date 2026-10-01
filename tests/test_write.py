from __future__ import annotations

import json
from itertools import count
from typing import TYPE_CHECKING

import pytest
from t4mlib import write
from t4mlib.media import read_track
from t4mlib.plan import PlanError, load_plan
from t4mlib.write import apply_plan, preview, quarantine, undo

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import AudioFactory, ImageFactory
    from t4mlib.style import Style

TAGS = {"title": "Lale", "artist": "Butch - Topic", "album": "Lale", "track": "1"}


def plan_file(tmp_path: Path, files: list[dict[str, object]]) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"files": files}))
    return path


@pytest.mark.parametrize("ext", ["flac", "mp3", "m4a", "aiff", "wav"])
def test_write_then_undo_restores_original_metadata(
    tmp_path: Path, audio: AudioFactory, image: ImageFactory, style: Style, ext: str
) -> None:
    old_cover = image("old.jpg", 300) if ext in {"flac", "mp3", "m4a"} else None
    track = audio(f"lale.{ext}", tags=TAGS, cover=old_cover)
    original = read_track(track)
    changes = {
        "artist": "Butch",
        "artists": ["Butch", "Trikk"],
        "album": "Secret Weapons Part 12",
        "tracktotal": "15",
        "genre": ["Deep House", "Electronic"],
        "label": "Innervisions",
    }
    entry: dict[str, object] = {"path": track.name, "set": changes, "cover": str(image("new.png", 2000))}
    plan = plan_file(tmp_path, [entry])

    manifest = apply_plan(load_plan(plan), style, str(plan))
    written = read_track(track)

    assert [f["status"] for f in manifest["files"]] == ["ok"]
    assert written.first("artist") == "Butch"
    assert written.first("album") == "Secret Weapons Part 12"
    assert (written.first("tracknumber"), written.first("tracktotal")) == ("1", "15")
    assert written.tags["genre"] == ["Deep House", "Electronic"]
    assert written.tags["artists"] == ["Butch", "Trikk"]
    assert written.first("label") == "Innervisions"
    assert [(p.mime, p.width) for p in written.pictures] == [("image/jpeg", style.cover_max_px)]

    undone = undo(manifest["id"], style, force=False)
    restored = read_track(track)

    assert [f["status"] for f in undone["files"]] == ["ok"]
    assert restored.tags == original.tags
    assert [p.sha1 for p in restored.pictures] == [p.sha1 for p in original.pictures]


def test_dry_run_writes_nothing_and_bad_plans_are_rejected(tmp_path: Path, audio: AudioFactory, style: Style) -> None:
    track = audio("a.flac", tags=TAGS)
    other = audio("b.flac", tags=TAGS)
    before = track.read_bytes()

    entry: dict[str, object] = {"paths": [track.name, other.name], "set": {"title": "X"}}
    report = preview(load_plan(plan_file(tmp_path, [entry])), style)

    assert track.read_bytes() == before
    assert [r["path"] for r in report] == [str(track), str(other)]
    assert report[0].get("diff") == [{"field": "title", "before": ["Lale"], "after": ["X"]}]
    with pytest.raises(PlanError) as error:
        load_plan(
            plan_file(
                tmp_path, [{"path": "missing.flac", "set": {"title": "X"}}, {"path": track.name, "set": {"mood": "x"}}]
            )
        )
    messages = "\n".join(error.value.errors)
    assert "is not an existing file" in messages
    assert "unknown field 'mood'" in messages


def test_failed_write_restores_the_original_bytes(
    tmp_path: Path, audio: AudioFactory, style: Style, monkeypatch: pytest.MonkeyPatch
) -> None:
    track = audio("a.mp3", tags=TAGS)
    before = track.read_bytes()
    hashes = count()

    def changing_hash(_path: Path) -> str:
        return str(next(hashes))

    monkeypatch.setattr(write, "audio_hash", changing_hash)

    plan = plan_file(tmp_path, [{"path": track.name, "set": {"title": "X"}}])
    manifest = apply_plan(load_plan(plan), style, str(plan))

    assert manifest["files"][0]["status"] == "failed"
    assert track.read_bytes() == before


def test_mp4_boolean_atoms_survive_read_write_and_undo(tmp_path: Path, audio: AudioFactory, style: Style) -> None:
    track = audio("a.m4a", tags=TAGS)
    plan = plan_file(tmp_path, [{"path": track.name, "set": {"compilation": "1"}}])
    manifest = apply_plan(load_plan(plan), style, str(plan))
    assert read_track(track).first("compilation") == "1"

    plan = plan_file(tmp_path, [{"path": track.name, "set": {"compilation": "0"}}])
    apply_plan(load_plan(plan), style, str(plan))
    assert read_track(track).first("compilation") == "0"

    undo(manifest["id"], style, force=False)
    assert "compilation" not in read_track(track).tags


def test_quarantine_moves_files_and_undo_brings_them_back(audio: AudioFactory, style: Style) -> None:
    track = audio("broken.flac")

    manifest = quarantine([track], "decode error")

    assert not track.exists()
    undo(manifest["id"], style, force=False)
    assert track.exists()

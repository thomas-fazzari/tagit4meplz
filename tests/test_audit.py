from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from t4mlib.media import read_track
from t4mlib.scan import scan
from t4mlib.verify import verify_file

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import AudioFactory, ImageFactory
    from t4mlib.style import Style

TAGS = {"title": "Blind", "artist": "Davis", "album": "Secret Weapons Part 8", "track": "8/13"}


@pytest.mark.parametrize("ext", ["flac", "mp3", "m4a", "aiff", "wav"])
def test_reads_canonical_tags_and_real_cover_size_in_every_format(
    audio: AudioFactory, image: ImageFactory, ext: str
) -> None:
    cover = image("cover.jpg", 640) if ext in {"flac", "mp3", "m4a"} else None
    track = read_track(audio(f"track.{ext}", tags=TAGS, cover=cover))

    assert track.first("title") == "Blind"
    assert track.first("artist") == "Davis"
    assert track.first("album") == "Secret Weapons Part 8"
    assert (track.first("tracknumber"), track.first("tracktotal")) == ("8", "13")
    if cover:
        assert (track.pictures[0].width, track.pictures[0].height) == (640, 640)


def test_scan_reports_album_and_file_problems(tmp_path: Path, audio: AudioFactory, style: Style) -> None:
    base = {"album": "Total 7", "album_artist": "Various", "date": "2006"}
    audio("a.flac", tags={**base, "title": "Wombat", "artist": "Wighnomy Bros.", "track": "1/3"})
    feat = {"title": "Blind (feat. Cameo Culture)", "artist": "Davis feat. Cameo Culture", "track": "3/3"}
    audio("b.flac", tags={**base, **feat})
    (tmp_path / "other").mkdir()
    audio("other/c.flac", tags={**base, "title": "Wombat", "artist": "Wighnomy Bros.", "track": "1/1"})

    report = scan(tmp_path, style)
    album_codes = {i["code"] for i in report["albums"][0]["issues"]}
    file_codes = {i["code"] for f in report["files"] for i in f["issues"]}

    assert [a["count"] for a in report["albums"]] == [2, 1]
    assert "missing-tracks" in album_codes
    assert {"no-cover", "albumartist-variant", "featuring-in-artist", "featured-artist-in-artist"} <= file_codes


def test_verify_flags_corrupted_audio(audio: AudioFactory) -> None:
    clean = audio("clean.flac", seconds=10)
    broken = audio("broken.flac", seconds=10)
    data = bytearray(broken.read_bytes())
    middle = len(data) // 2
    data[middle : middle + 4096] = bytes(4096)
    broken.write_bytes(data)

    assert verify_file(clean)["ok"]
    assert not verify_file(broken)["ok"]

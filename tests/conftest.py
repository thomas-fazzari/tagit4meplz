from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Protocol

import pytest
from mutagen import id3
from mutagen.wave import WAVE
from t4mlib.style import Style, load_style

if TYPE_CHECKING:
    from pathlib import Path

FORMAT_ARGS = {
    "flac": ["-c:a", "flac"],
    "mp3": ["-c:a", "libmp3lame", "-b:a", "320k", "-id3v2_version", "3"],
    "m4a": ["-c:a", "aac", "-b:a", "256k"],
    "aiff": ["-c:a", "pcm_s16be", "-write_id3v2", "1"],
    "wav": ["-c:a", "pcm_s16le"],
}
ID3_FRAMES = {
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "track": "TRCK",
    "album_artist": "TPE2",
    "date": "TDRC",
}


class AudioFactory(Protocol):
    def __call__(
        self, name: str, *, tags: dict[str, str] | None = None, cover: Path | None = None, seconds: int = 2
    ) -> Path: ...


class ImageFactory(Protocol):
    def __call__(self, name: str, size: int) -> Path: ...


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], check=True)


def make_audio(path: Path, tags: dict[str, str] | None, cover: Path | None, seconds: int) -> Path:
    fmt = path.suffix.lstrip(".")
    args = ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    if cover:
        args += ["-i", str(cover), "-map", "0:a", "-map", "1:v", "-c:v", "copy", "-disposition:v", "attached_pic"]
    args += FORMAT_ARGS[fmt]
    for key, value in (tags or {}).items():
        args += ["-metadata", f"{key}={value}"]
    ffmpeg(*args, str(path))
    if fmt == "wav" and tags:
        wave = WAVE(path)
        wave.add_tags()
        assert wave.tags is not None
        for key, value in tags.items():
            frame_type = id3.Frames[ID3_FRAMES[key]]
            assert issubclass(frame_type, id3.TextFrame)
            wave.tags.add(frame_type(encoding=3, text=value))
        wave.save()
    return path


@pytest.fixture(autouse=True)
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "state"
    monkeypatch.setenv("T4M_STATE", str(home))
    return home


@pytest.fixture
def style() -> Style:
    return load_style()


@pytest.fixture
def audio(tmp_path: Path) -> AudioFactory:
    def factory(name: str, *, tags: dict[str, str] | None = None, cover: Path | None = None, seconds: int = 2) -> Path:
        return make_audio(tmp_path / name, tags, cover, seconds)

    return factory


@pytest.fixture
def image(tmp_path: Path) -> ImageFactory:
    def factory(name: str, size: int) -> Path:
        path = tmp_path / name
        ffmpeg("-f", "lavfi", "-i", f"color=red:s={size}x{size}", "-frames:v", "1", str(path))
        return path

    return factory

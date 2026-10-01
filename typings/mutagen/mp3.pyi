from pathlib import Path

from mutagen import FileType, StreamInfo
from mutagen.id3 import ID3

class MPEGInfo(StreamInfo):
    sample_rate: int
    channels: int

class MP3(FileType):
    tags: ID3 | None
    info: MPEGInfo
    def __init__(self, filething: str | Path) -> None: ...
    def save(
        self, filething: str | Path | None = None, v1: int = 1, v2_version: int = 4, v23_sep: str = "/"
    ) -> None: ...

from pathlib import Path

from mutagen import FileType, StreamInfo
from mutagen.id3 import ID3

class AIFFInfo(StreamInfo):
    sample_rate: int
    channels: int
    bits_per_sample: int

class AIFF(FileType):
    tags: ID3 | None
    info: AIFFInfo
    def __init__(self, filething: str | Path) -> None: ...
    def save(self, filething: str | Path | None = None, v2_version: int = 4, v23_sep: str = "/") -> None: ...

from collections.abc import MutableMapping
from pathlib import Path
from typing import Self

from mutagen import FileType, StreamInfo

class AtomDataType:
    UTF8: int
    JPEG: int
    PNG: int

class MP4Cover(bytes):
    FORMAT_JPEG: int
    FORMAT_PNG: int
    imageformat: int
    def __new__(cls, data: bytes, imageformat: int = ...) -> Self: ...

class MP4FreeForm(bytes):
    dataformat: int
    version: int
    def __new__(cls, data: bytes, dataformat: int = ..., version: int = 0) -> Self: ...

type MP4Value = str | bool | int | tuple[int, int] | MP4Cover | MP4FreeForm

class MP4Tags(MutableMapping[str, list[MP4Value] | bool]): ...

class MP4Info(StreamInfo):
    codec: str
    sample_rate: int
    channels: int
    bits_per_sample: int

class MP4(FileType):
    tags: MP4Tags | None
    info: MP4Info
    def __init__(self, filething: str | Path) -> None: ...
    def save(self, filething: str | Path | None = None) -> None: ...

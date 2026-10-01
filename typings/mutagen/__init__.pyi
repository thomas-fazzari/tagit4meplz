from pathlib import Path

version_string: str

class MutagenError(Exception): ...

class StreamInfo:
    length: float
    bitrate: int

class FileType:
    filename: str
    def add_tags(self) -> None: ...
    def delete(self, filething: str | Path | None = None) -> None: ...

def File(filething: str | Path, options: object = None, easy: bool = False) -> FileType | None: ...

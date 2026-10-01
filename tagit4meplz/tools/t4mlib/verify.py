from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, NotRequired, TypedDict

from t4mlib.proc import run_text

if TYPE_CHECKING:
    from pathlib import Path

REQUIRED_BINARIES = ("ffmpeg", "flac", "magick")
MD5_UNSET = "MD5 signature"


class VerifyResult(TypedDict):
    path: str
    ok: bool
    errors: NotRequired[list[str]]
    warnings: NotRequired[list[str]]


def doctor() -> dict[str, str | None]:
    return {b: shutil.which(b) for b in REQUIRED_BINARIES}


def verify_file(path: Path) -> VerifyResult:
    if path.suffix.lower() == ".flac":
        command = ["flac", "-s", "-t", str(path)]
    else:
        command = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a", "-f", "null", "-"]
    result = run_text(command)
    lines = [line for line in (result.stderr + result.stdout).splitlines() if line.strip()]
    errors = [line for line in lines if MD5_UNSET not in line]
    warnings = [line for line in lines if MD5_UNSET in line]
    entry = VerifyResult(path=str(path), ok=result.returncode == 0 and not errors)
    if errors:
        entry["errors"] = errors[:5]
    if warnings:
        entry["warnings"] = warnings
    return entry


def verify(paths: list[Path], jobs: int = 8) -> list[VerifyResult]:
    with ThreadPoolExecutor(jobs) as pool:
        return list(pool.map(verify_file, paths))

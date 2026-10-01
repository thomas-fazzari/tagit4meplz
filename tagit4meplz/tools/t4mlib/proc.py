from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class ToolError(RuntimeError):
    pass


def run_text(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, errors="replace", check=False)


def run_bytes(command: list[str]) -> bytes:
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        message = f"{command[0]} failed: {result.stderr.decode(errors='replace').strip()}"
        raise ToolError(message)
    return result.stdout


def audio_hash(path: Path) -> str:
    result = run_text(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a", "-c:a", "copy", "-f", "md5", "-"]
    )
    digest = result.stdout.strip().removeprefix("MD5=")
    if result.returncode != 0 or not digest:
        message = f"cannot hash audio of {path}: {result.stderr.strip()}"
        raise ToolError(message)
    return digest


def clone_file(source: Path, target: Path) -> None:
    if run_text(["cp", "-c", "-p", str(source), str(target)]).returncode != 0:
        shutil.copy2(source, target)

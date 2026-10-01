#!/usr/bin/env python3

from __future__ import annotations

import argparse
import io
import shutil
import sys
import tarfile
import tempfile
import termios
import tty
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO = "thomas-fazzari/tagit4meplz"
BRANCH = "master"
NAME = "tagit4meplz"
HOME = Path.home()
CANONICAL = HOME / ".agents" / "skills" / NAME
TOOLS = ("uv", "ffmpeg", "flac", "magick")


NATIVE = "Codex, pi and OpenCode"  # read ~/.agents/skills themselves


@dataclass(frozen=True)
class Agent:
    id: str
    label: str
    link_dir: Path
    marker: Path  # folder that shows the agent is installed


AGENTS = (
    Agent("claude", "Claude Code", HOME / ".claude" / "skills", HOME / ".claude"),
    Agent("agy", "Antigravity", HOME / ".gemini" / "config" / "skills", HOME / ".gemini"),
)

UP, DOWN, SPACE, ENTER, QUIT = "up", "down", " ", "enter", "quit"
KEYS = {"\x1b[A": UP, "k": UP, "\x1b[B": DOWN, "j": DOWN, " ": SPACE, "\r": ENTER, "\n": ENTER, "q": QUIT, "\x03": QUIT}


def checklist() -> list[Agent]:
    with Path("/dev/tty").open("r+b", buffering=0) as term:
        fd = term.fileno()
        term.write(
            f"Installing to ~/{CANONICAL.relative_to(HOME)} ({NATIVE} read it). Symlink to:\r\n\x1b[?25l".encode()
        )
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return _select(term)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            term.write(b"\x1b[?25h")


def _select(term: io.FileIO) -> list[Agent]:
    checked = [agent.marker.is_dir() for agent in AGENTS]
    cursor = 0
    while True:
        for i, agent in enumerate(AGENTS):
            pointer = ">" if i == cursor else " "
            box = "x" if checked[i] else " "
            term.write(f"\x1b[2K{pointer} [{box}] {agent.label:12} ~/{agent.link_dir.relative_to(HOME)}\r\n".encode())
        key = term.read(1).decode(errors="replace")
        if key == "\x1b":
            key += term.read(2).decode(errors="replace")
        action = KEYS.get(key)
        if action == QUIT:
            sys.exit("aborted")
        if action == ENTER:
            return [agent for agent, on in zip(AGENTS, checked, strict=True) if on]
        if action == UP:
            cursor = (cursor - 1) % len(AGENTS)
        elif action == DOWN:
            cursor = (cursor + 1) % len(AGENTS)
        elif action == SPACE:
            checked[cursor] = not checked[cursor]
        term.write(f"\x1b[{len(AGENTS)}A".encode())


def parse_agents(text: str) -> list[Agent]:
    by_id = {agent.id: agent for agent in AGENTS}
    ids = [part for part in text.split(",") if part]
    unknown = [part for part in ids if part not in by_id]
    if unknown:
        sys.exit(f"unknown agents: {', '.join(unknown)}. Choose from {', '.join(by_id)}")
    return [by_id[part] for part in ids]


def fetch_source(tmp: Path) -> Path:
    url = f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/{BRANCH}"
    with urllib.request.urlopen(url) as response:
        data = response.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        archive.extractall(tmp, filter="data")
    return tmp / f"{REPO.split('/')[1]}-{BRANCH}" / NAME


def install(source: Path, *, link: bool) -> None:
    CANONICAL.parent.mkdir(parents=True, exist_ok=True)
    remove(CANONICAL)
    if link:
        CANONICAL.symlink_to(source)
    else:
        shutil.copytree(source, CANONICAL, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
    (CANONICAL / "tools" / "t4m.py").chmod(0o755)
    print(f"Installed {NAME} at {CANONICAL}")


def link_agents(agents: list[Agent]) -> None:
    for agent in agents:
        agent.link_dir.mkdir(parents=True, exist_ok=True)
        target = agent.link_dir / NAME
        remove(target)
        target.symlink_to(CANONICAL)
        print(f"{agent.label}: linked {target}")


def remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install the tagit4meplz skill.")
    parser.add_argument("--link", action="store_true", help="symlink the clone instead of copying it")
    parser.add_argument("--agents", help="comma-separated agents to link, skips the checklist")
    args = parser.parse_args()

    script = Path(__file__).resolve() if Path(__file__).is_file() else None
    local = script.parent / NAME if script else None
    if args.link and not (local and (local / "SKILL.md").is_file()):
        sys.exit("--link needs a clone of the repository")

    if args.agents is not None:
        agents = parse_agents(args.agents)
    elif Path("/dev/tty").exists():
        try:
            agents = checklist()
        except OSError:
            sys.exit("no terminal: pass --agents")
    else:
        sys.exit("no terminal: pass --agents")

    if local and (local / "SKILL.md").is_file():
        install(local, link=args.link)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            install(fetch_source(Path(tmp)), link=False)
    link_agents(agents)

    for tool in TOOLS:
        if shutil.which(tool) is None:
            print(f"warning: {tool} not found on PATH, the skill needs it", file=sys.stderr)


if __name__ == "__main__":
    main()

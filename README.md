# tagit4meplz

Skill and tools for editing audio metadata with an LLM.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- [FFmpeg](https://ffmpeg.org/), [FLAC](https://xiph.org/flac/) and [ImageMagick](https://imagemagick.org/)

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/thomas-fazzari/tagit4meplz/master/install.py | python3
```

The skill lands in `~/.agents/skills/tagit4meplz`, which Codex, pi and OpenCode read directly. The installer then offers to symlink it into `~/.claude/skills` for Claude Code and `~/.gemini/config/skills` for Antigravity. Pass `--agents claude,agy` to skip the checklist.

> [!NOTE]
> From a clone, `./install.py --link` symlinks the clone instead of copying it, so edits apply immediately.

## Use

Ask your LLM to audit or retag music in a folder.

## Development

```sh
mise install && mise run install && mise run hooks:install
mise run check
```

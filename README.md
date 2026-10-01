# tagit4meplz

Skill and tools for editing audio metadata with an LLM.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- [FFmpeg](https://ffmpeg.org/)
- [FLAC](https://xiph.org/flac/)
- [ImageMagick](https://imagemagick.org/)

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/thomas-fazzari/tagit4meplz/master/install.py | python3
```

The skill lands in `~/.agents/skills/tagit4meplz`, which Codex, pi and OpenCode read directly.

The installer can also symlink it for Claude Code and Antigravity.

From a clone:

```sh
./install.py --link
```

## Use

Point your agent at a music folder and describe what you want.

A few examples:

```text
Audit ~/Music/Album and tell me what looks wrong.
```

```text
Check this folder for missing or inconsistent tags, bad cover art and corrupt files.
```

```text
Identify this release and fix the metadata. Show me the changes before applying them.
```

```text
Retag these files consistently and replace the cover with the correct one.
```

```text
Check my music library for albums with inconsistent metadata.
```

The skill gives the agent tools to inspect the files, compare metadata, verify audio integrity and prepare changes before writing them.

## CLI

`tools/t4m.py` outputs JSON by default. Add `--human` where supported for readable output.

| Command                                        | Use                                                 |
| ---------------------------------------------- | --------------------------------------------------- |
| `t4m.py doctor`                                | Check required external tools                       |
| `t4m.py scan <dir>`                            | Find tag, cover and album issues                    |
| `t4m.py inspect <files...>`                    | Show tags, raw keys and embedded pictures           |
| `t4m.py verify <paths...>`                     | Fully decode files and detect corruption            |
| `t4m.py write <plan.json>`                     | Preview a metadata write                            |
| `t4m.py write <plan.json> --apply`             | Apply the write                                     |
| `t4m.py undo <run-id>`                         | Restore files changed by a run                      |
| `t4m.py runs`                                  | List recent runs                                    |
| `t4m.py forget <run-ids...>`                   | Delete saved run data                               |
| `t4m.py quarantine <files...> --reason <text>` | Move files out of the library without deleting them |

Metadata conventions live in `style.toml`.

## Development

```sh
mise install
mise run install
mise run hooks:install
mise run check
```

## License

MIT

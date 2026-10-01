---
name: tagit4meplz
description: Audit and fix music library metadata (tags, cover art, integrity) for FLAC, MP3, M4A, AIFF and WAV. Use when a user asks to audit, retag, fix tags, find covers or check a music folder.
---

# tagit4meplz

Tools and guardrails for music metadata work. Pick the steps the task needs. No fixed workflow.

## CLI

`tools/t4m.py` runs through `uv` (inline script dependencies, nothing to install). Output is JSON. Add `--human` for a readable summary.

| Command                                       | Use                                                                                   |
| --------------------------------------------- | ------------------------------------------------------------------------------------- |
| `t4m.py doctor`                               | Check `ffmpeg`, `flac` and `magick`                                                   |
| `t4m.py scan <dir>`                           | Issues per file, album (one album name in one folder) and library. Skips hidden paths |
| `t4m.py inspect <files...>`                   | Every canonical tag, raw key and picture (real dimensions, sha1) of the given files   |
| `t4m.py verify <paths...>`                    | Full decode (`flac -t` or `ffmpeg`). Exit code 1 if any file is corrupt               |
| `t4m.py write <plan.json>`                    | Show the diff of a plan. Writes nothing. Plan format: `t4m.py write --help`           |
| `t4m.py write <plan.json> --apply`            | Write the plan. Prints a run id                                                       |
| `t4m.py undo <run-id> [--force]`              | Restore every file of a run. Undo runs can be undone too                              |
| `t4m.py runs`                                 | List recent runs                                                                      |
| `t4m.py forget <run-ids...>`                  | Delete run snapshots and backups. Refuses runs that still hold quarantined files      |
| `t4m.py quarantine <files...> --reason <txt>` | Move files out of the library into the run folder. `undo` moves them back             |

A plan entry takes `path` or a `paths` list when several files share the same change. Canonical field names and their Vorbis, ID3 and MP4 keys are in `tools/t4mlib/fields.py` (Picard mapping).

## Write safety

`write --apply` saves a snapshot of the tags and pictures of every file in a zip before writing. It clones each file before writing, hashes the audio stream before and after, and restores the clone if the write fails or the audio changes. Runs live in `~/.local/state/tagit4meplz/runs` (override with `T4M_STATE`).

## Style

`style.toml` holds the house conventions: compilation album artist, featuring placement, `(Original Mix)` policy, cover size, minimum lossy bitrate, ID3 version, required fields. Override with `--style` or `T4M_STYLE`.

## Guardrails

- Never rename or move audio files, except with `quarantine`. Download clients and players index paths.
- Write tags only with `t4m.py write`. Never use tag editors with directory-wide selection. See `references/pitfalls.md`.
- Run the dry run and read the diff before `--apply`.
- Never re-encode audio to fix metadata.
- Verify identity before writing: tracklist, duration and ISRC must match the release.
- Check fetched covers visually before embedding them.
- Quarantine corrupt files. Never delete them.
- Re-run `t4m.py scan` after writing and compare.
- After a successful write, ask the user whether the run snapshot can be deleted. Run `t4m.py forget` only after a yes.

## References

- `references/pitfalls.md`: traps met in real sessions.
- `references/sources.md`: metadata and cover sources, with request recipes.

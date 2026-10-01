# Pitfalls

## `metaflac --test` does not exist

Integrity checks need `flac -t file.flac` or `ffmpeg -v error -i file -f null -`. `t4m verify` wraps both. `flac -t` warns when the STREAMINFO MD5 is unset. That warning is not corruption.

## Picture blocks lie about dimensions

FLAC picture blocks often declare `0x0` or wrong sizes, and some MIME types are wrong. Read the real size from the image bytes (`t4m inspect` does). Re-embedding the cover with `t4m write` fixes the declared size.

## Vorbis keys are case-insensitive

`Label=` and `LABEL=` are the same field. Players disagree on which duplicate wins. Remove both spellings before setting a value.

## Multi-disc track totals

Some rips store the album-wide count in `TRACKTOTAL` on every disc. Per-disc totals are correct. `t4m scan` reports `tracktotal-is-album-total`.

## ID3 versions

ID3v2.3 has no multi-value fields. With `id3.version = 3`, multi values are joined with `id3.separator` and read back as one value. Keep `version = 4` unless a target player cannot read ID3v2.4.

## WAV metadata

ffmpeg writes RIFF INFO chunks in WAV, which most players and mutagen ignore. Use ID3 chunks for WAV and AIFF.

## Download client folders

Download clients such as slskd or Nicotine+ keep paths in their database. Renaming breaks their index. Edit tags in place only. In-progress downloads live in hidden folders like `.partial`. Leave them alone.

## YouTube rips

Artist ends with `- Topic`, album equals title, year is the upload year, bitrate is lossy and low. Identify the real release by searching artist and title (see `sources.md`), compare the duration to the second, and flag the file as a replacement candidate.

## Featuring placement

Store sites put featured artists in `ARTIST` (`Knowkontrol, Rowee`) with `feat.` also in the title. Keep the main artist in `ARTIST`, `feat.` in the title, and every artist in `ARTISTS`.

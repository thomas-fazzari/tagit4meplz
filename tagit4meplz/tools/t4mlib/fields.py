from __future__ import annotations

from dataclasses import dataclass

ITUNES = "----:com.apple.iTunes:"


@dataclass(frozen=True)
class Field:
    name: str
    vorbis: tuple[str, ...]
    id3: str
    mp4: str
    multi: bool = False


FIELDS: tuple[Field, ...] = (
    Field("title", ("TITLE",), "TIT2", "\xa9nam"),
    Field("artist", ("ARTIST",), "TPE1", "\xa9ART"),
    Field("artists", ("ARTISTS",), "TXXX:ARTISTS", ITUNES + "ARTISTS", multi=True),
    Field("album", ("ALBUM",), "TALB", "\xa9alb"),
    Field("albumartist", ("ALBUMARTIST", "ALBUM ARTIST"), "TPE2", "aART"),
    Field("tracknumber", ("TRACKNUMBER",), "TRCK", "trkn"),
    Field("tracktotal", ("TRACKTOTAL", "TOTALTRACKS"), "TRCK", "trkn"),
    Field("discnumber", ("DISCNUMBER",), "TPOS", "disk"),
    Field("disctotal", ("DISCTOTAL", "TOTALDISCS"), "TPOS", "disk"),
    Field("date", ("DATE", "YEAR"), "TDRC", "\xa9day"),
    Field("originaldate", ("ORIGINALDATE",), "TDOR", ITUNES + "ORIGINALDATE"),
    Field("genre", ("GENRE",), "TCON", "\xa9gen", multi=True),
    Field("label", ("LABEL", "ORGANIZATION", "PUBLISHER"), "TPUB", ITUNES + "LABEL"),
    Field("catalognumber", ("CATALOGNUMBER",), "TXXX:CATALOGNUMBER", ITUNES + "CATALOGNUMBER"),
    Field("barcode", ("BARCODE",), "TXXX:BARCODE", ITUNES + "BARCODE"),
    Field("isrc", ("ISRC",), "TSRC", ITUNES + "ISRC"),
    Field("bpm", ("BPM",), "TBPM", "tmpo"),
    Field("key", ("INITIALKEY", "KEY"), "TKEY", ITUNES + "initialkey"),
    Field("remixer", ("REMIXER",), "TPE4", ITUNES + "REMIXER"),
    Field("composer", ("COMPOSER",), "TCOM", "\xa9wrt"),
    Field("compilation", ("COMPILATION",), "TCMP", "cpil"),
    Field("comment", ("COMMENT", "DESCRIPTION"), "COMM", "\xa9cmt"),
    Field(
        "musicbrainz_albumid", ("MUSICBRAINZ_ALBUMID",), "TXXX:MusicBrainz Album Id", ITUNES + "MusicBrainz Album Id"
    ),
    Field(
        "musicbrainz_trackid",
        ("MUSICBRAINZ_RELEASETRACKID",),
        "TXXX:MusicBrainz Release Track Id",
        ITUNES + "MusicBrainz Release Track Id",
    ),
    Field(
        "musicbrainz_recordingid",
        ("MUSICBRAINZ_TRACKID",),
        "UFID:http://musicbrainz.org",
        ITUNES + "MusicBrainz Track Id",
    ),
)

BY_NAME: dict[str, Field] = {f.name: f for f in FIELDS}
NAMES: tuple[str, ...] = tuple(f.name for f in FIELDS)

PAIRED = {"tracknumber": "tracktotal", "discnumber": "disctotal"}
PAIR_TOTALS = {v: k for k, v in PAIRED.items()}

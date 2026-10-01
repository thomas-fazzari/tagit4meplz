# Sources

Prefer sources in this order for identity: MusicBrainz, iTunes, Deezer, Discogs. Beatport has the best electronic genres, BPM and key, but scraping breaks often.

## MusicBrainz

Rate limit: 1 request per second. A `User-Agent` with contact info is required.

```sh
curl -s -H "User-Agent: tagit4meplz/0.1 (you@example.com)" -G https://musicbrainz.org/ws/2/release/ \
  --data-urlencode 'query=release:"Total 4" AND label:Kompakt' --data-urlencode fmt=json
curl -s -H "User-Agent: ..." "https://musicbrainz.org/ws/2/release/<mbid>?inc=recordings+labels+isrcs+artist-credits&fmt=json"
```

Several releases share a title. Pick by format (`Digital Media`, `CD`), track count and date.

## Cover Art Archive

```sh
curl -sL https://coverartarchive.org/release/<mbid>          # JSON list, "front": true
curl -sL https://coverartarchive.org/release/<mbid>/front-1200
```

Vinyl releases often have the best scans. Digital releases are often 600 px.

## iTunes Search and Lookup

No key. Good tracklists, release dates and artwork.

```sh
curl -s -G https://itunes.apple.com/search --data-urlencode "term=Secret Weapons Part 12" \
  --data-urlencode entity=album --data-urlencode limit=10
curl -s "https://itunes.apple.com/lookup?id=<collectionId>&entity=song"
```

Replace `100x100bb.jpg` in `artworkUrl100` with `3000x3000bb.jpg` for the largest available size. The server returns the source size when it is smaller (often 600, 1400 or 2048).

## Deezer

No key. Lookup by ISRC, useful when files already carry `ISRC`.

```sh
curl -s https://api.deezer.com/track/isrc:DEEC31810053
curl -s https://api.deezer.com/album/<id>     # cover_xl is 1000 px
```

## Discogs

Token from discogs.com settings, 60 requests per minute. Best for labels, catalog numbers, vinyl-only releases and electronic styles.

```sh
curl -s -H "Authorization: Discogs token=$DISCOGS_TOKEN" -G https://api.discogs.com/database/search \
  --data-urlencode 'q=Kompakt Total 4' --data-urlencode type=release
```

## AcoustID

Needs `fpcalc` (`brew install chromaprint`) and a free application key. Use for untagged or YouTube-tagged files.

```sh
fpcalc -json file.mp3
curl -s -G https://api.acoustid.org/v2/lookup --data-urlencode client=$ACOUSTID_KEY \
  --data-urlencode meta=recordings+releases --data-urlencode duration=<s> --data-urlencode fingerprint=<fp>
```

## Covers

Build a contact sheet of the candidates and look at it before embedding:

```sh
magick a.jpg b.jpg c.jpg -resize 300x300 +append sheet.png
```

Resize to the style cap with `magick in.jpg -resize '1400x1400>' -quality 90 out.jpg`. The `>` flag never upscales.

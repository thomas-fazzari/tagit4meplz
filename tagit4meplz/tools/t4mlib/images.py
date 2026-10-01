from __future__ import annotations

import struct

JPEG = "image/jpeg"
PNG = "image/png"

PNG_SIZE_END = 24
MARKER_PREFIX = 0xFF
STANDALONE_MARKERS = {0xD8, 0x01, *range(0xD0, 0xD8)}
JPEG_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def image_info(data: bytes) -> tuple[str | None, int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= PNG_SIZE_END:
        width, height = struct.unpack(">II", data[16:24])
        return PNG, width, height
    if data.startswith(b"\xff\xd8"):
        width, height = _jpeg_size(data)
        return JPEG, width, height
    return None, 0, 0


def _jpeg_size(data: bytes) -> tuple[int, int]:
    pos = 2
    size = len(data)
    while pos + 4 <= size:
        if data[pos] != MARKER_PREFIX:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker == MARKER_PREFIX:
            pos += 1
            continue
        if marker in STANDALONE_MARKERS:
            pos += 2
            continue
        (length,) = struct.unpack(">H", data[pos + 2 : pos + 4])
        if marker in JPEG_SOF_MARKERS and pos + 9 <= size:
            height, width = struct.unpack(">HH", data[pos + 5 : pos + 9])
            return width, height
        pos += 2 + length
    return 0, 0

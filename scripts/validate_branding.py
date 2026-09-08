"""Validate the RGB/RGBA PNG used for both Flowlines branding fields."""

import struct
import zlib
from pathlib import Path


def validate_logo(path: Path) -> None:
    if path.suffix.lower() != ".png":
        raise ValueError("Flowlines branding must use a PNG file")
    if path.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("Branding image exceeds 5 MiB")
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Branding image is not a PNG")
    offset, header, compressed, ended = 8, None, bytearray(), False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("Truncated PNG chunk")
        size, kind = struct.unpack_from(">I4s", data, offset)
        end = offset + 12 + size
        if end > len(data):
            raise ValueError("Truncated PNG chunk")
        payload = data[offset + 8:end - 4]
        checksum = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + payload) != checksum:
            raise ValueError("Invalid PNG checksum")
        if header is None and kind != b"IHDR":
            raise ValueError("PNG must start with IHDR")
        if kind == b"IHDR":
            if header is not None or size != 13:
                raise ValueError("Invalid PNG header")
            header = struct.unpack(">IIBBBBB", payload)
            width, height, depth, color, compression, filtering, interlace = header
            if width != height or not 48 <= width <= 4096:
                raise ValueError("Branding image must be square and 48–4096 pixels")
            if depth != 8 or color not in (2, 6) or (compression, filtering, interlace) != (0, 0, 0):
                raise ValueError("Use an 8-bit RGB/RGBA PNG without interlacing")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            if size != 0 or end != len(data):
                raise ValueError("Invalid PNG ending")
            ended = True
        offset = end
    if header is None or not compressed or not ended:
        raise ValueError("Incomplete PNG")
    width, height, _, color, *_ = header
    stride = width * (4 if color == 6 else 3) + 1
    expected = height * stride
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(compressed, expected + 1)
    except zlib.error as error:
        raise ValueError("Cannot decode PNG pixels") from error
    if len(pixels) != expected or not decoder.eof or decoder.unused_data:
        raise ValueError("Invalid PNG pixel data")
    if any(pixels[row * stride] > 4 for row in range(height)):
        raise ValueError("Invalid PNG row filter")

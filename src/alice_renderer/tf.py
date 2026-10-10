"""Metadata-only parser for O2's STF file format, version 1.

Wire layout follows O2 Headers/DataHeader.h and TFReaderDD/SubTimeFrameFile.h.
DataHeader versions 1–3 use little-endian fixed-width fields. Unsupported
layouts are rejected. Detector payloads are skipped, never decoded here.
The independent O2-linked inspector in native/ is the reference cross-check.
"""
from __future__ import annotations

import struct
from pathlib import Path

BASE = struct.Struct('<4sIII8s8s')
BODY = struct.Struct('<16s4sI8sIIQ')
META = struct.Struct('<QQQ')
HEADER_SIZES = {1: 80, 2: 88, 3: 96}


class _Reader:
    def __init__(self, stream, size):
        self.stream, self.size, self.position = stream, size, 0

    def read(self, length, bound):
        self._check(length, bound)
        data = self.stream.read(length)
        if len(data) != length:
            raise ValueError(f'Short TF read at byte {self.position}')
        self.position += length
        return data

    def _check(self, length, bound):
        if length < 0 or not self.position <= bound <= self.size or length > bound - self.position:
            raise ValueError(f'TF block exceeds file/timeframe boundary at byte {self.position}')

    def skip(self, length, bound):
        self._check(length, bound)
        self.position += length
        self.stream.seek(self.position)

    def stack(self, bound):
        result = None
        for _ in range(16):
            magic, length, flags, version, kind, serialization = BASE.unpack(self.read(BASE.size, bound))
            if magic != b'O2O2' or not BASE.size <= length <= 65536:
                raise ValueError('Invalid O2 header magic/size')
            body = self.read(length - BASE.size, bound)
            if kind == b'DataHead':
                if result is not None:
                    raise ValueError('Multiple DataHeaders in one stack')
                if HEADER_SIZES.get(version) != length:
                    raise ValueError(f'Unsupported DataHeader version/size: {version}/{length}')
                desc, origin, parts, payload_serialization, subspec, split, payload = BODY.unpack_from(body)
                orbit = struct.unpack_from('<I', body, BODY.size)[0] if version >= 2 else 0
                counter, run = struct.unpack_from('<II', body, BODY.size + 4) if version >= 3 else (0, 0)
                result = dict(description=desc.rstrip(b'\0'), origin=origin.rstrip(b'\0').decode('ascii'),
                              payload_serialization=payload_serialization.rstrip(b'\0'), payload=payload,
                              split=split, orbit=orbit, tf_counter=counter, run=run)
            if not flags & 1:
                if result is None:
                    raise ValueError('O2 header stack lacks DataHeader')
                return result
        raise ValueError('O2 header stack exceeds 16 headers')


def inspect_tf(path: Path, *, cancelled=lambda: False) -> dict:
    """Enumerate TF records and detector origins; counts are not collisions."""
    path = Path(path)
    before = path.stat()
    if not before.st_size:
        raise ValueError('Input TF is empty')
    records = []
    with path.open('rb') as stream:
        reader = _Reader(stream, before.st_size)
        while reader.position < reader.size:
            if cancelled():
                raise InterruptedError('TF inspection cancelled')
            start = reader.position
            header = reader.stack(reader.size)
            if (header['description'], header['payload'], header['payload_serialization']) != (b'FILE_STF_META', META.size, b'NONE'):
                raise ValueError('TF metadata header mismatch')
            version, length, creation = META.unpack(reader.read(META.size, reader.size))
            if version != 1:
                raise ValueError(f'Unsupported STF file version: {version}')
            if not reader.position - start <= length <= reader.size - start:
                raise ValueError('Incomplete or invalid TF size')
            end = start + length
            record = dict(offset=start, size=length, creation_ms=creation, run=0, orbit=0,
                          tf_counter=0, origins={})
            identity = False
            if reader.position < end:
                index = reader.stack(end)
                if index['description'] != b'FILE_STF_INDEX' or index['payload'] % 48:
                    raise ValueError('Invalid TF index header')
                reader.skip(index['payload'], end)
                while reader.position < end:
                    if cancelled():
                        raise InterruptedError('TF inspection cancelled')
                    block = reader.stack(end)
                    if not identity and block['payload']:
                        for key in ('run', 'orbit', 'tf_counter'):
                            record[key] = block[key]
                        identity = True
                    origin = record['origins'].setdefault(block['origin'], dict(payload_bytes=0, blocks=0))
                    origin['payload_bytes'] += block['payload']
                    origin['blocks'] += int(block['split'] == 0)
                    reader.skip(block['payload'], end)
            records.append(record)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Input is still changing; wait for the download/copy to finish')
    return dict(schema_version=1, format='raw_tf', bytes=before.st_size,
                timeframes=len(records), records=records)

"""Blur chunk files (.model, .texture, .level...): a tree of named chunks.

    char name[]   NUL-terminated, padded with NULs to a multiple of 4
    u32  size     whole chunk including this header
    u16  count    child count for containers
    u16  kind     'C' container, 'A' data
    ...  payload  children (containers) or raw data

Some 'A' chunks hold child chunks too: a data chunk counts as nested when its
payload parses exactly as a sequence of chunks. Blur's tools store the root
container ("  CPModel") 4 bytes short, which cuts off its last child ("Coll");
the root is widened when its children fall short of its count.

Same rules as 26Viewer's src/games/blur/ChunkFile.cpp.
"""

import struct

_MAX_DEPTH = 32


class Chunk:
    __slots__ = ("name", "offset", "header_size", "size", "count", "kind", "children")

    def __init__(self, name, offset, header_size, size, count, kind):
        self.name = name
        self.offset = offset
        self.header_size = header_size
        self.size = size
        self.count = count
        self.kind = kind
        self.children = []

    @property
    def payload_offset(self):
        return self.offset + self.header_size

    @property
    def payload_size(self):
        return self.size - self.header_size

    def child(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None

    def payload(self, data):
        return data[self.payload_offset:self.offset + self.size]

    def __repr__(self):
        return f"Chunk({self.name!r} @{self.offset:#x}, {self.size} bytes, {len(self.children)} children)"


def read_header(data, offset, end=None):
    """The chunk starting at `offset`, or None."""
    end = len(data) if end is None else end
    if offset >= end:
        return None
    nul = data.find(b"\0", offset, min(end, offset + 64))
    if nul <= offset:
        return None
    raw = data[offset:nul]
    if any(c < 0x20 or c > 0x7E for c in raw):
        return None
    name = raw.decode("ascii")
    padded = (len(raw) + 1 + 3) & ~3
    if end - offset < padded + 8:
        return None
    if any(data[offset + len(raw):offset + padded]):
        # Level render files: a fixed 8-byte name field with old bytes after the NUL.
        if len(raw) >= 8 or end - offset < 16:
            return None
        padded = 8
    size, count, kind = struct.unpack_from("<IHH", data, offset + padded)
    if kind not in (0x41, 0x43) or size < padded + 8 or size > end - offset:
        return None
    return Chunk(name, offset, padded + 8, size, count, chr(kind))


def _parse_sequence(data, begin, end, out, depth):
    pos = begin
    while pos < end:
        chunk = read_header(data, pos, end)
        if chunk is None:
            break
        _parse_children(data, chunk, depth)
        if depth == 0:
            _widen_root(data, chunk, end)
        pos += chunk.size
        out.append(chunk)
    return pos


def _parse_children(data, chunk, depth):
    if depth >= _MAX_DEPTH or chunk.payload_size < 16:
        return
    kids = []
    end = chunk.offset + chunk.size
    reached = _parse_sequence(data, chunk.payload_offset, end, kids, depth + 1)
    if kids and (chunk.kind == "C" or reached == end):
        chunk.children = kids


def _widen_root(data, root, end):
    if root.kind != "C" or len(root.children) >= root.count or end - root.offset < root.size + 4:
        return
    wider = Chunk(root.name, root.offset, root.header_size, root.size + 4, root.count, root.kind)
    _parse_children(data, wider, 0)
    if len(wider.children) > len(root.children):
        root.size = wider.size
        root.children = wider.children


def parse(data):
    """The root chunk of a chunk file, with its children; None if it isn't one."""
    root = read_header(data, 0)
    if root is None:
        return None
    _parse_children(data, root, 0)
    _widen_root(data, root, len(data))
    return root

"""Blur .model files: geometry, part hierarchy, materials and textures.

A model is a chunk file:

    CPModel { Header, MdlDat { Header, StrTab, Element, ... }, Models, Constr,
              Render { Header, Scene }, Coll, MtaDbg }

Render/Scene holds an "ARCH" stream: a serialized object graph in which every
record starts with "RA" + u16 version. This reader finds the records that
describe geometry, materials and textures (the same way 26Viewer's
src/games/blur/ModelDecoder.cpp does; docs there: docs/formats/blur.md):

    vertex buffer  "RA" 00 00, u32 n, u16 element offsets[n], u32 vertex count, blob
                   (preceded by its element list: "RA" 00 00, u32 type, u32 0,
                   u32 usage, u32 usage index per element)
    index buffer   "RA" 01 00, u32 index count, u32 0, blob of u16
    draw           "RA" 00 00, u32 start, u32 count, u32 min index, u32 vertex count
                   (one per level of detail, consecutive; unused slots are empty
                   draws with min index 0x7FFFFFFF)
    streams        after a group: "RA" 00 00, u32 passes, then per pass
                   "RA" 00 00, u32 buffer number, u32 ?, u32 byte offset, u32 ?
                   and "RA" 00 00, u32 value set, u32 0
    group header   0x54 bytes before the first draw: "RA" 01 00, u32 material,
                   u32 ?, u32 ?, u32 ?, u32 element (low 16 bits)
    blob           "RA" 00 00, u32 size, u32 16, zero padding to the first 16-byte
                   boundary (counted from "ARCH") at least 5 bytes past the align
                   field, then the data

Positions are Direct3D's: left-handed, x right, y up, z forward.
"""

import bisect
import struct
from dataclasses import dataclass, field

from . import chunks

# Vertex element types (the engine's own codes)
FLOAT3, FLOAT4, HALF2, HALF4, UBYTE4, UBYTE4N = 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B
ELEMENT_SIZE = {FLOAT3: 12, FLOAT4: 16, HALF2: 4, HALF4: 8, UBYTE4: 4, UBYTE4N: 4}

# Direct3D vertex usages
POSITION, BLENDWEIGHT, BLENDINDICES, NORMAL, TEXCOORD, TANGENT, BINORMAL = 0, 1, 2, 3, 5, 6, 7

# Material input types (Blur.exe's MaterialElementType)
S8, U8, S16, U16, S32, U32, F32, TEXTURE_INDEX, MATERIAL_INDEX, DATA_INDEX, TEXTURE_PTR = range(11)
INPUT_TYPE_NAMES = ["s8", "u8", "s16", "u16", "s32", "u32", "f32", "texture", "material", "data", "texture_ptr"]

NO_INDEX = 0x7FFFFFFF


class ModelError(Exception):
    pass


@dataclass
class VertexElement:
    type: int
    usage: int
    index: int
    offset: int


@dataclass
class VertexBuffer:
    at: int                 # file position of the record
    offsets: list
    count: int
    stride: int
    start: int              # first byte of the vertex data
    size: int
    elements: list = field(default_factory=list)  # VertexElement, when the element list was found

    def element(self, usage, index=0, types=None):
        for e in self.elements:
            if e.usage == usage and e.index == index and (types is None or e.type in types):
                return e
        return None

    @property
    def position_bytes(self):
        return (self.offsets[1] if len(self.offsets) > 1 else self.stride) - self.offsets[0]


@dataclass
class Draw:
    at: int
    start: int
    count: int
    min_index: int
    vertices: int


@dataclass
class Group:
    """One part with one material: its draws at each level of detail."""
    index_buffer: int
    lods: list              # Draw, most detailed first
    slots: int              # level-of-detail slots, including empty ones
    stream_buffer: int = -1
    stream_offset: int = 0
    element: int = -1
    material: int = 0
    primitive: int = 1      # 0 triangle list, 1 triangle strip, 2 points (geometry record w[2])
    values: int = -1        # its material's value set
    pass_values: list = field(default_factory=list)
    highest_index: int = 0
    vertex_range: int = 0
    vertex_buffer: int = -1  # resolved vertex buffer
    base_vertex: int = 0     # first vertex within it
    shadow: bool = False


@dataclass
class Element:
    """A node of the part hierarchy (MdlDat/Element): e_exterior > e_door_left..."""
    name: str
    parent: int
    rotation: tuple          # 3x3, row vectors: p' = p * R + position
    position: tuple
    tag: int

    def is_identity(self):
        ident = (1, 0, 0, 0, 1, 0, 0, 0, 1)
        return all(abs(a - b) < 1e-5 for a, b in zip(self.rotation, ident)) and not any(self.position)


@dataclass
class MaterialInput:
    name: str
    type: int
    count: int


@dataclass
class RenderListEntry:
    effect: str
    inputs: list
    data_size: int


@dataclass
class ValueSet:
    """The values one render-list entry (a material pass) is drawn with."""
    entry: int
    textures: list = field(default_factory=list)   # (input name, texture index)
    constants: list = field(default_factory=list)  # (input name, [floats])
    integers: list = field(default_factory=list)   # (input name, [ints])
    data: list = field(default_factory=list)       # (input name, [(u32, u32)]) animated data
    palette: list = field(default_factory=list)
    bones: list = field(default_factory=list)


@dataclass
class StoredTexture:
    """A texture held in the model: every mip level, largest first."""
    name: str
    format: int             # D3D format code / FourCC (see dds.py)
    width: int
    height: int
    mip_count: int
    runs: list              # (offset, size, width, height) pieces of the chain in the file
    streamed: bool
    key: int = 0            # the u32 after a keyed texture's name (exporter ID)

    def pixels(self, data):
        return b"".join(bytes(data[o:o + s]) for o, s, _, _ in self.runs)


@dataclass
class Model:
    data: bytes
    arch: int
    elements: list
    vertex_buffers: list
    index_buffers: list      # lists of u16
    groups: list             # resolved groups (vertex_buffer >= 0)
    effects: list            # material number -> effect name ("veh_Paint_a.fx")
    render_list: list        # RenderListEntry
    value_sets: list         # ValueSet
    textures: list           # StoredTexture
    texture_order: list      # texture index -> position in `textures` (-1: not held)
    notes: list = field(default_factory=list)

    def texture_for(self, index):
        """The stored texture a TEXTURE_INDEX value means, or None."""
        if 0 <= index < len(self.texture_order):
            t = self.texture_order[index]
            return self.textures[t] if 0 <= t < len(self.textures) else None
        return None


# ---- scanning helpers ----------------------------------------------------------------------

class _Scanner:
    def __init__(self, data, arch):
        self.d = data
        self.n = len(data)
        self.arch = arch

    def u32(self, p):
        return struct.unpack_from("<I", self.d, p)[0]

    def i32(self, p):
        return struct.unpack_from("<i", self.d, p)[0]

    def u16(self, p):
        return struct.unpack_from("<H", self.d, p)[0]

    def f32(self, p):
        return struct.unpack_from("<f", self.d, p)[0]

    def is_ra(self, p, version):
        d = self.d
        return 0 <= p and p + 4 <= self.n and d[p] == 0x52 and d[p + 1] == 0x41 and d[p + 2] == version and d[p + 3] == 0

    def blob_at(self, p):
        """(start, size) of the blob record at p, or None."""
        if p + 12 > self.n or not self.is_ra(p, 0):
            return None
        size = self.u32(p + 4)
        if self.u32(p + 8) != 16:
            return None
        rel = p + 12 + 5 - self.arch
        start = self.arch + rel + ((16 - rel % 16) % 16)
        if start + size > self.n or any(self.d[p + 12:start]):
            return None
        return start, size

    def string_at(self, p, limit=64):
        """A length-prefixed printable string at p, or None."""
        if p + 4 > self.n:
            return None
        n = self.u32(p)
        if n > limit or p + 4 + n > self.n:
            return None
        raw = self.d[p + 4:p + 4 + n]
        if any(c < 32 or c >= 127 for c in raw):
            return None
        return raw.decode("ascii")


# ---- MdlDat: names and hierarchy -------------------------------------------------------------

def read_elements(data, root):
    """MdlDat { StrTab, Element }. Element records are 104 bytes: u32 0, f32 rotation[9],
    f32 position[3], f32 bounds[6], u32 name, u32 index, i32 parent, i32 first child,
    i32 next sibling, u32 ?, u32 render tag."""
    mdl = root.child("MdlDat") if root else None
    strtab = mdl.child("StrTab") if mdl else None
    table = mdl.child("Element") if mdl else None
    if not strtab or not table or table.payload_size % 104:
        return []
    strings = strtab.payload(data)
    if len(strings) < 4:
        return []
    count = struct.unpack_from("<I", strings, 0)[0]
    pool = 8 + 4 * count
    if pool > len(strings):
        return []

    def string(i):
        if i >= count:
            return ""
        start = pool + struct.unpack_from("<I", strings, 4 + 4 * i)[0]
        end = strings.find(b"\0", start)
        return bytes(strings[start:end if end >= 0 else len(strings)]).decode("latin-1")

    records = table.payload(data)
    total = len(records) // 104
    out = []
    for r in range(total):
        at = r * 104
        rot = struct.unpack_from("<9f", records, at + 4)
        pos = struct.unpack_from("<3f", records, at + 40)
        name_index = struct.unpack_from("<I", records, at + 76)[0]
        parent = struct.unpack_from("<i", records, at + 84)[0]
        tag = struct.unpack_from("<I", records, at + 100)[0]
        finite = all(abs(v) < 1e30 and v == v for v in rot + pos)
        out.append(Element(string(name_index), parent if 0 <= parent < total else -1,
                           rot if finite else (1, 0, 0, 0, 1, 0, 0, 0, 1),
                           pos if finite else (0.0, 0.0, 0.0), tag))
    return out


# ---- geometry records ----------------------------------------------------------------------

def _read_vertex_elements(s, p, n, vb):
    """The element list in front of the vertex buffer record at p."""
    if p < 20 * n:
        return
    for i in range(n):
        q = p - 20 * (n - i)
        if not s.is_ra(q, 0) or s.u32(q + 8) != 0:
            return
    for i in range(n):
        q = p - 20 * (n - i)
        vb.elements.append(VertexElement(s.u32(q + 4), s.u32(q + 12), s.u32(q + 16), vb.offsets[i]))


def _find_records(s):
    d = s.d
    vbs, ibs, candidates = [], [], []
    p = d.find(b"RA", s.arch)
    while 0 <= p and p + 4 <= s.n:
        if s.is_ra(p, 0) and p + 8 <= s.n:
            n = s.u32(p + 4)
            if 1 <= n <= 16 and p + 8 + 2 * n + 4 <= s.n:
                offsets = list(struct.unpack_from(f"<{n}H", d, p + 8))
                q = p + 8 + 2 * n
                count = s.u32(q)
                blob = s.blob_at(q + 4)
                if blob and count and blob[1] % count == 0 and offsets[0] == 0 and offsets == sorted(offsets):
                    stride = blob[1] // count
                    if offsets[-1] < stride and stride <= 256:
                        vb = VertexBuffer(p, offsets, count, stride, blob[0], blob[1])
                        _read_vertex_elements(s, p, n, vb)
                        vbs.append(vb)
                        p = d.find(b"RA", blob[0] + blob[1])
                        continue
            if p + 20 <= s.n:
                candidates.append(Draw(p, s.u32(p + 4), s.u32(p + 8), s.u32(p + 12), s.u32(p + 16)))
        elif s.is_ra(p, 1) and p + 12 <= s.n:
            count = s.u32(p + 4)
            blob = s.blob_at(p + 12)
            if blob and count and blob[1] == count * 2:
                ibs.append(list(struct.unpack_from(f"<{count}H", d, blob[0])))
                p = d.find(b"RA", blob[0] + blob[1])
                continue
        p = d.find(b"RA", p + 2)
    return vbs, ibs, candidates


def _tile(index_count, candidates):
    """Draws covering [0, index_count) exactly, or None."""
    by_start = {}
    for c in candidates:
        if c.count >= 3 and c.vertices > 0 and c.start + c.count <= index_count:
            by_start.setdefault(c.start, []).append(c)
    reaches = {index_count}
    nxt = {}
    for start in sorted(by_start, reverse=True):
        for c in by_start[start]:
            if c.start + c.count in reaches:
                reaches.add(c.start)
                nxt[c.start] = c
                break
    if 0 not in reaches:
        return None
    chain, pos = [], 0
    while pos < index_count:
        chain.append(nxt[pos])
        pos += chain[-1].count
    return chain


def _fits(vb, g):
    offset = g.stream_offset if g.stream_buffer >= 0 else 0
    if offset % vb.stride:
        return False
    first = offset // vb.stride
    return first + g.highest_index < vb.count and first + g.vertex_range <= vb.count


def _solve_buffers(vbs, groups):
    """Buffer number -> vertex buffer: candidates must fit every group using the number;
    a buffer taken by one number leaves the others; leftovers take the tightest fit."""
    by_number = {}
    for g in groups:
        if g.stream_buffer >= 0:
            by_number.setdefault(g.stream_buffer, []).append(g)
    candidates = {number: {i for i, vb in enumerate(vbs) if all(_fits(vb, g) for g in users)}
                  for number, users in by_number.items()}
    mapping = {}
    changed = True
    while changed:
        changed = False
        for number in sorted(candidates):
            cands = candidates[number]
            if number in mapping or len(cands) != 1:
                continue
            buffer = next(iter(cands))
            mapping[number] = buffer
            for other, other_set in candidates.items():
                if other != number:
                    other_set.discard(buffer)
            changed = True
    for number in sorted(candidates):
        cands = candidates[number]
        if number in mapping or not cands:
            continue
        needed = max(g.vertex_range for g in by_number[number])
        mapping[number] = min(sorted(cands), key=lambda i: vbs[i].count - needed)
    return mapping


def _build_groups(s, ibs, candidates):
    groups, untiled = [], 0
    for ib_index, ib in enumerate(ibs):
        chain = _tile(len(ib), candidates)
        if chain is None:
            untiled += 1
            continue
        chain.sort(key=lambda c: c.at)
        i = 0
        while i < len(chain):
            lods = [chain[i]]
            i += 1
            while i < len(chain) and chain[i].at == lods[-1].at + 20:
                lods.append(chain[i])
                i += 1
            g = Group(ib_index, lods, len(lods))
            end = lods[-1].at + 20
            while end + 20 <= s.n and s.is_ra(end, 0) and s.u32(end + 8) == 0 and s.u32(end + 12) == NO_INDEX:
                end += 20
                g.slots += 1
            if end + 28 <= s.n and s.is_ra(end, 0) and s.is_ra(end + 8, 0) and 1 <= s.u32(end + 4) <= 4:
                g.stream_buffer = s.u32(end + 12)
                g.stream_offset = s.u32(end + 20)
                for pass_ in range(s.u32(end + 4)):
                    at = end + 28 + 32 * pass_
                    if at + 12 > s.n or not s.is_ra(at, 0) or s.u32(at + 8) != 0:
                        break
                    g.pass_values.append(s.u32(at + 4))
                if g.pass_values:
                    g.values = g.pass_values[0]
            first = lods[0].at
            if first >= 0x54 and s.is_ra(first - 0x54, 1):
                g.material = s.u32(first - 0x50)
                g.primitive = s.u32(first - 0x48)
                g.element = s.u32(first - 0x40) & 0xFFFF
            for lod in lods:
                g.highest_index = max(g.highest_index, max(ib[lod.start:lod.start + lod.count]))
                g.vertex_range = max(g.vertex_range, lod.min_index + lod.vertices)
            groups.append(g)
    return groups, untiled


def _assign_buffers(vbs, groups):
    """Picks each group's vertex buffer (see ModelDecoder.cpp for the reasoning)."""
    mapping = _solve_buffers(vbs, groups)

    def exact(g, i):
        offset = g.stream_offset if g.stream_buffer >= 0 else 0
        return _fits(vbs[i], g) and vbs[i].count == offset // vbs[i].stride + g.vertex_range

    def chained(g, i):
        if g.stream_buffer < 0 or not _fits(vbs[i], g):
            return False
        end = g.stream_offset + g.vertex_range * vbs[i].stride
        return any(o is not g and o.stream_buffer == g.stream_buffer and o.stream_offset == end and _fits(vbs[i], o)
                   for o in groups)

    def line_ups(number, i):
        return sum(1 for o in groups if o.stream_buffer == number and (exact(o, i) or chained(o, i)))

    resolved = []
    for g in groups:
        buffer = None
        if g.stream_buffer >= 0 and g.stream_buffer in mapping and _fits(vbs[mapping[g.stream_buffer]], g):
            buffer = mapping[g.stream_buffer]
        if buffer is not None and not exact(g, buffer) and not chained(g, buffer):
            mapped = line_ups(g.stream_buffer, buffer)
            better = next((i for i in range(len(vbs)) if i != buffer and exact(g, i)), None)
            if better is None:
                for i in range(len(vbs)):
                    if i != buffer and chained(g, i):
                        n = line_ups(g.stream_buffer, i)
                        if n >= 2 and n > mapped:
                            better = i
                            break
            if better is not None:
                buffer = better
        if buffer is None:
            buffer = next((i for i in range(len(vbs)) if exact(g, i)), None)
            if buffer is None:
                buffer = next((i for i in range(len(vbs)) if chained(g, i)), None)
            for i in range(len(vbs)):
                if _fits(vbs[i], g) and (buffer is None or (not exact(g, buffer) and not chained(g, buffer)
                                                           and vbs[i].count < vbs[buffer].count)):
                    buffer = i
        if buffer is None or vbs[buffer].position_bytes not in (8, 12, 16):
            continue
        g.vertex_buffer = buffer
        g.base_vertex = (g.stream_offset // vbs[buffer].stride) if g.stream_buffer >= 0 else 0
        resolved.append(g)
    real = any(len(vb.offsets) > 1 for vb in vbs)
    for g in resolved:
        g.shadow = real and len(vbs[g.vertex_buffer].offsets) == 1
    return resolved


# ---- materials -----------------------------------------------------------------------------

def read_effect_names(s):
    """The material list: "RA" 00 00, u32 count, then per material an empty record and
    "RA" 00 00, u32 length, the effect name."""
    d = s.d
    fx = d.find(b".fx", s.arch)
    while fx >= 0:
        for length in range(4, min(64, fx + 3) + 1):
            name = fx + 3 - length
            if name < s.arch + 16 or not s.is_ra(name - 8, 0) or s.u32(name - 4) != length:
                continue
            first = name - 12
            if not s.is_ra(first, 0) or not s.is_ra(first - 8, 0):
                return []
            count = s.u32(first - 4)
            if not 0 < count <= 256:
                return []
            names, p = [], first
            for _ in range(count):
                if p + 12 > s.n or not s.is_ra(p, 0) or not s.is_ra(p + 4, 0):
                    break
                n = s.u32(p + 8)
                if not 0 < n <= 128 or p + 12 + n > s.n:
                    break
                names.append(bytes(d[p + 12:p + 12 + n]).decode("latin-1"))
                p += 12 + n
            return names
        fx = d.find(b".fx", fx + 1)
    return []


def _read_render_list_at(s, p):
    """A render list from its header at p ("RA" 00 00, u32 count, entries) -> (entries, end)."""
    count = s.u32(p + 4)
    p += 8
    entries = []
    for _ in range(count):
        effect = s.string_at(p + 4) if s.is_ra(p, 0) else None
        if effect is None:
            return [], p
        p += 8 + len(effect)
        if not s.is_ra(p, 0) or p + 8 > s.n:
            return [], p
        n = s.u32(p + 4)
        p += 8
        if n > 64:
            return [], p
        inputs = []
        for _ in range(n):
            name = s.string_at(p + 4) if s.is_ra(p, 0) else None
            if name is None or p + 16 + len(name) > s.n:
                return [], p
            p += 8 + len(name)
            inp = MaterialInput(name, s.u32(p), s.u32(p + 4))
            if inp.type > 10 or inp.count > 256:
                return [], p
            inputs.append(inp)
            p += 8
        if p + 16 > s.n:
            return [], p
        data_size = s.u32(p)
        p += 8
        if not s.is_ra(p, 0) or s.u32(p + 4) != n:
            return [], p
        p += 8 + 2 * n + 8
        entries.append(RenderListEntry(effect, inputs, data_size))
    return entries, p


def read_render_list(s):
    cls = s.d.find(b"RenderingData::RenderListNode_Common", s.arch)
    if cls < 0:
        return [], 0
    for p in range(cls, min(cls + 0x400, s.n - 16)):
        if s.is_ra(p, 0) and s.is_ra(p + 8, 0) and 1 <= s.u32(p + 4) <= 4096:
            name = s.string_at(p + 12)
            if name and len(name) >= 3:
                return _read_render_list_at(s, p)
    return [], 0


def _read_data_names(s, start):
    """Bone names of the animated data a DATA_INDEX names (second render list: "Element",
    then "AnimatedParam" entries whose single input is a bone)."""
    key = b"\x07\x00\x00\x00Element"
    at = s.d.find(key, start)
    while at >= 0:
        if at >= 12 and s.is_ra(at - 4, 0) and s.is_ra(at - 12, 0):
            entries, _ = _read_render_list_at(s, at - 12)
            if entries:
                return [e.inputs[0].name if e.effect == "AnimatedParam" and e.inputs else "" for e in entries]
        at = s.d.find(key, at + 1)
    return []


def _read_value_sets(s, entries, p, count, total_bytes):
    sets, total = [], 0
    for _ in range(count):
        if p + 4 > s.n or s.u32(p) >= len(entries):
            return None, p
        entry_index = s.u32(p)
        entry = entries[entry_index]
        total += entry.data_size
        p += 4
        vs = ValueSet(entry_index)
        for inp in entry.inputs:
            floats, ints, data = [], [], []
            for _ in range(inp.count):
                if inp.type == DATA_INDEX:
                    if not s.is_ra(p, 0) or p + 12 > s.n:
                        return None, p
                    data.append((s.u32(p + 4), s.u32(p + 8)))
                    if inp.name == "g_mPalette":
                        vs.palette.append(s.u32(p + 4))
                    p += 12
                    continue
                size = 1 if inp.type <= U8 else 2 if inp.type <= U16 else 4
                if p + size > s.n:
                    return None, p
                if inp.type == TEXTURE_INDEX:
                    vs.textures.append((inp.name, s.u32(p)))
                elif inp.type == F32:
                    floats.append(s.f32(p))
                else:
                    fmt = {S8: "<b", U8: "<B", S16: "<h", U16: "<H", S32: "<i"}.get(inp.type, "<I")
                    ints.append(struct.unpack_from(fmt, s.d, p)[0])
                p += size
            if floats:
                vs.constants.append((inp.name, floats))
            if ints:
                vs.integers.append((inp.name, ints))
            if data:
                vs.data.append((inp.name, data))
        sets.append(vs)
    if total != total_bytes:
        return None, p
    return sets, p


def _source_pairs(s, p):
    if p + 8 > s.n or not s.is_ra(p, 0):
        return None, p
    count = s.u32(p + 4)
    if count > 4096 or p + 8 + 8 * count > s.n:
        return None, p
    pairs = []
    for k in range(count):
        package = s.i32(p + 8 + 8 * k)
        index = s.u32(p + 12 + 8 * k)
        if package < -1 or package >= 4096 or (index >= 65536 and index != 0xFFFFFFFF):
            return None, p
        pairs.append((package, index))
    return pairs, p + 8 + 8 * count


def _read_texture_sources(s, start):
    """Three (package, index) vectors follow the material values; the third maps texture
    indices to stored textures (Blur.exe FUN_006cd820)."""
    p = s.d.find(b"RA\x00\x00", start)
    while p >= 0:
        first, second = _source_pairs(s, p)
        if first is not None:
            mid, third = _source_pairs(s, second)
            if mid is not None:
                textures, after = _source_pairs(s, third)
                if textures and after + 4 <= s.n and s.is_ra(after, 0):
                    return textures
        p = s.d.find(b"RA\x00\x00", p + 1)
    return []


def read_materials(s):
    """(render list, value sets, texture sources)."""
    entries, end = read_render_list(s)
    if not entries:
        return [], [], []
    header = b"RA\x00\x00\x00\x00\x00\x00"
    p = s.d.find(header, end)
    while p >= 0 and p + 16 <= s.n:
        count, total = s.u32(p + 8), s.u32(p + 12)
        if 0 < count <= 65536 and total <= s.n and s.u32(p + 16) < len(entries):
            sets, after = _read_value_sets(s, entries, p + 16, count, total)
            if sets is not None and len(sets) == count:
                if any(v.palette for v in sets):
                    names = _read_data_names(s, end)
                    for v in sets:
                        v.bones = [names[n] if n < len(names) else "" for n in v.palette]
                return entries, sets, _read_texture_sources(s, after)
        p = s.d.find(header, p + 1)
    return entries, [], []


# ---- textures ------------------------------------------------------------------------------

def _surface_size(fmt, w, h):
    from .dds import surface_size
    return surface_size(fmt, w, h)


def _known_format(code):
    from .dds import FORMATS
    return code in FORMATS


def find_textures(s):
    """Every texture stored in the model, in file order."""
    d = s.d
    found = []
    key = b"\x00\x00\x00\x00\x03\x00\x00\x00"  # the Data layout ends with u32 0, u32 3
    k = d.find(key, s.arch + 64 + 20)
    while k >= 0:
        f = k - 20
        k = d.find(key, k + 1)
        if f + 28 > s.n:
            continue
        w, h, depth, mips, fmt = struct.unpack_from("<5I", d, f)
        ra = f - 52 if s.is_ra(f - 52, 1) else f - 56 if s.is_ra(f - 56, 1) else 0
        next_size = not ra and s.is_ra(f - 16, 0) and s.u32(f - 8) == 1 and s.u32(f - 4) == 28
        if (not _known_format(fmt) or not 0 < w <= 4096 or not 0 < h <= 4096 or depth != 1
                or not 0 < mips <= 13 or (not ra and not next_size)):
            continue
        if s.u32(f - 4) == 28:  # streamed: the pixels follow in a blob
            blob = s.blob_at(f + 28)
            if not blob:
                continue
            pixels, size = blob
        else:
            pixels, size = f + 28, s.u32(f - 4) - 28
        if pixels + size > s.n or size < _surface_size(fmt, w, h):
            continue
        name, streamed = "", False
        if ra:
            for length in range(0, 65):
                if length + 4 > ra or s.u32(ra - length - 4) != length:
                    continue
                raw = d[ra - length:ra]
                if all(32 <= c < 127 for c in raw):
                    name = bytes(raw).decode("ascii")
                streamed = ra >= length + 16 and s.is_ra(ra - length - 16, 2)
                break
        found.append(dict(name=name, first=bool(ra), streamed=streamed, w=w, h=h, fmt=fmt,
                          pixels=pixels, size=size))

    textures = []
    for c in found:
        run = [c["pixels"], c["size"], c["w"], c["h"]]
        if c["first"]:
            textures.append(dict(name=c["name"] or f"texture {len(textures) + 1}", fmt=c["fmt"], runs=[run],
                                 streamed=c["streamed"]))
            continue
        if not textures or textures[-1]["fmt"] != c["fmt"]:
            continue
        t = textures[-1]
        same = next((r for r in t["runs"] if r[2] == c["w"] and r[3] == c["h"]), None)
        if same is not None:
            if c["size"] > same[1]:
                same[:] = run
        elif c["w"] == 2 * t["runs"][-1][2] or c["h"] == 2 * t["runs"][-1][3]:
            t["runs"].append(run)

    out = []
    for t in textures:
        runs = sorted(t["runs"], key=lambda r: r[2] * r[3], reverse=True)
        w, h = runs[0][2], runs[0][3]
        kept, mips, complete = [], 0, False
        for run in runs:
            if complete or run[2] != w or run[3] != h:
                break
            used = 0
            while not complete and run[1] - used >= _surface_size(t["fmt"], w, h):
                used += _surface_size(t["fmt"], w, h)
                mips += 1
                complete = w == 1 and h == 1
                w, h = max(1, w // 2), max(1, h // 2)
            kept.append((run[0], used, run[2], run[3]))
        if kept and mips:
            out.append(StoredTexture(t["name"], t["fmt"], kept[0][2], kept[0][3], mips, kept, t["streamed"]))
    return out


def texture_order(sources, textures):
    """Texture index -> position in `textures` (keyed entries count keyed textures,
    streamed packages hold the streamed ones in file order). Empty if it doesn't fit."""
    keyed = [i for i, t in enumerate(textures) if not t.streamed]
    in_packages = [i for i, t in enumerate(textures) if t.streamed]
    packaged = sorted({(p, i) for p, i in sources if p >= 0})
    if len(packaged) != len(in_packages):
        return []
    order = []
    for package, index in sources:
        if package < 0:
            if index >= len(keyed):
                return []
            order.append(keyed[index])
        else:
            order.append(in_packages[bisect.bisect_left(packaged, (package, index))])
    return order


# ---- the whole model -----------------------------------------------------------------------

def read(data):
    """Reads a .model file's bytes into a Model; raises ModelError."""
    data = bytes(data)
    arch = data.find(b"ARCH")
    if arch < 0:
        raise ModelError("no scene data (ARCH) in this file")
    s = _Scanner(data, arch)
    root = chunks.parse(data)

    vbs, ibs, candidates = _find_records(s)
    if not vbs or not ibs:
        raise ModelError(f"no geometry found ({len(vbs)} vertex / {len(ibs)} index buffers)")
    groups, untiled = _build_groups(s, ibs, candidates)
    resolved = _assign_buffers(vbs, groups)
    if not resolved:
        raise ModelError("no drawable parts found")

    effects = read_effect_names(s)
    render_list, value_sets, sources = read_materials(s)
    textures = find_textures(s)
    order = texture_order(sources, textures)
    if not order and not any(t.streamed for t in textures):
        order = list(range(len(textures)))  # no table: stored order

    model = Model(data, arch, read_elements(data, root), vbs, ibs, resolved, effects, render_list, value_sets,
                  textures, order)
    skipped = untiled + len(groups) - len(resolved)
    if skipped:
        model.notes.append(f"{skipped} part(s) not understood yet")
    if not order and any(t.streamed for t in textures):
        model.notes.append("the texture table wasn't found, so streamed textures aren't linked")
    return model


def triangles(model, group, lod):
    """The triangles of `group` at level of detail `lod` as (a, b, c) vertex numbers within
    its vertex buffer (a strip unstitched or a list; degenerate triangles dropped)."""
    if lod >= len(group.lods):
        return []
    draw = group.lods[lod]
    ib = model.index_buffers[group.index_buffer]
    sl = ib[draw.start:draw.start + draw.count]
    base = group.base_vertex
    out = []
    if group.primitive == 0:                # a plain list
        for i in range(0, len(sl) - 2, 3):
            a, b, c = sl[i], sl[i + 1], sl[i + 2]
            if a != b and b != c and a != c:
                out.append((base + a, base + b, base + c))
        return out
    if group.primitive != 1:                # points: nothing to draw
        return out
    for i in range(len(sl) - 2):            # a triangle strip
        a, b, c = sl[i], sl[i + 1], sl[i + 2]
        if a == b or b == c or a == c:
            continue
        out.append((base + a, base + c, base + b) if i % 2 else (base + a, base + b, base + c))
    return out

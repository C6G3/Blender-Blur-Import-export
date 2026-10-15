"""The scene stream of a Blur model (chunk Render/Scene): read it, and write it back.

The stream is "ARCH" serialization: every object or field is "RA" + u16
version followed by its fields; vectors are u32 count + items; strings u32
length + bytes; data blobs are "RA", u32 size, u32 16 (alignment) and zero
padding to the first 16-byte boundary (counted from "ARCH") at least 5 bytes
on, then the data. The field order follows Blur.exe's binary readers (the
RenderingData types at 0x6D0000-0x6F0000; their text twins name the fields).

Each type is described ONCE by a schema function `f(s, o)` that works in both
directions: with a Reader it fills the dict `o` from the stream, with a Writer
it writes `o` out. Every "RA" version is kept (keys starting with "_"), so a
model read and written again comes out byte for byte the same.

Layout of the stream:

    "ARCH", u32 1 (little-endian), u32 0
    "ARCH", u32 version, u32 1
    scene object  ("RA" + FUN_006ec040)
        "RA" u32 ?; the root CullNode; the vertex declarations; the effect
        (material) names; u32 package count; the keyed textures; the content
        (sections, blobs: empty in models); [version 1+] the scene objects
    u32 package count, then per package ("RA" + FUN_006eb940):
        "RA" u32 ?, u32 levels (10), then per level a block (FUN_006ea2a0):
        "RA" "RA" u32 2, u32 level; level 0 holds vertex buffers, index
        buffers and objects (CullNodes "Model0", "Model1", "Static" and a
        RenderListNode_Common: materials, geometry, draws...); every level
        holds texture copies (level 0 the small sizes, 1-9 one larger size each).
"""

import struct


class SceneError(Exception):
    pass


# ---- the two directions ------------------------------------------------------------------------

class Reader:
    reading = True

    def __init__(self, data, start, arch):
        self.d, self.p, self.arch = data, start, arch

    def _take(self, n):
        if self.p + n > len(self.d):
            raise SceneError(f"read past the end at {self.p:#x}")
        v = self.d[self.p:self.p + n]
        self.p += n
        return v

    def ra(self, version=None):
        if self.d[self.p:self.p + 2] != b"RA":
            raise SceneError(f"expected a record (RA) at {self.p:#x} (+{self.p - self.arch:#x})")
        v = struct.unpack_from("<H", self.d, self.p + 2)[0]
        self.p += 4
        return v

    def u8(self, x=None):
        return self._take(1)[0]

    def u16(self, x=None):
        return struct.unpack("<H", self._take(2))[0]

    def u32(self, x=None):
        return struct.unpack("<I", self._take(4))[0]

    def u64(self, x=None):
        return struct.unpack("<Q", self._take(8))[0]

    def f32s(self, x, n):
        return list(struct.unpack(f"<{n}f", self._take(4 * n)))

    def raw(self, x, n=None):
        return bytes(self._take(n))

    def string(self, x=None):
        n = self.u32()
        if n > 1 << 16:
            raise SceneError(f"string of {n} bytes at {self.p - 4:#x}")
        return self._take(n).decode("latin-1")

    def vec(self, items, fn):
        n = self.u32()
        if n > 1 << 22:
            raise SceneError(f"list of {n} items at {self.p - 4:#x}")
        return [fn(None) for _ in range(n)]

    def blob(self, x=None):
        v = self.ra()
        size, align = self.u32(), self.u32()
        rel = self.p + 5 - self.arch
        start = self.arch + rel + (16 - rel % 16) % 16
        if any(self.d[self.p:start]):
            raise SceneError(f"blob padding isn't zero at {self.p:#x}")
        self.p = start
        return {"_v": v, "align": align, "data": bytes(self._take(size))}


class Writer:
    reading = False

    def __init__(self):
        self.out = bytearray()
        self.arch = 0

    @property
    def p(self):
        return len(self.out)

    def ra(self, version):
        self.out += b"RA" + struct.pack("<H", version or 0)
        return version or 0

    def u8(self, x):
        self.out.append(x)
        return x

    def u16(self, x):
        self.out += struct.pack("<H", x)
        return x

    def u32(self, x):
        self.out += struct.pack("<I", x & 0xFFFFFFFF)
        return x

    def u64(self, x):
        self.out += struct.pack("<Q", x)
        return x

    def f32s(self, x, n):
        self.out += struct.pack(f"<{n}f", *x)
        return x

    def raw(self, x, n=None):
        self.out += x
        return x

    def string(self, x):
        b = x.encode("latin-1")
        self.u32(len(b))
        self.out += b
        return x

    def vec(self, items, fn):
        self.u32(len(items))
        return [fn(item) for item in items]

    def blob(self, x):
        self.ra(x.get("_v", 0))
        self.u32(len(x["data"]))
        self.u32(x.get("align", 16))
        rel = self.p + 5 - self.arch
        self.out += bytes(5 + (16 - rel % 16) % 16)
        self.out += x["data"]
        return x


def _o(o):
    return {} if o is None else o


# ---- RenderingData types -------------------------------------------------------------------------

def resource_index(s, o):               # ResourceIndex {Block, Index}
    o = list(o) if o is not None else [0, 0]
    return [s.u32(o[0]), s.u32(o[1])]


def node(s, o):                         # RenderingData::Node {name, SubNodes, Parent, Location}
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["name"] = s.string(o.get("name"))
    o["_vs"] = s.ra(o.get("_vs"))
    o["sub"] = s.vec(o.get("sub"), lambda x: resource_index(s, x))
    o["parent"] = resource_index(s, o.get("parent"))
    o["location"] = resource_index(s, o.get("location"))
    return o


def bounds(s, o):                       # Bounds {AabbMin, AabbMax, DistanceMin, DistanceMax}
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["box"] = s.f32s(o.get("box"), 8)
    return o


def bitvector(s, o):                    # Btl::BitVector: u32 bits, "RA" + bytes
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["bits"] = s.u32(o.get("bits"))
    o["_vb"] = s.ra(o.get("_vb"))
    o["bytes"] = s.raw(o.get("bytes"), s.u32(len(o["bytes"])) if not s.reading else s.u32())
    return o


def cull_node(s, o, version):           # CullNode {Node, Bounds, PvsBits, GroupIndex, PortalBits}
    o = _o(o)
    o["node"] = node(s, o.get("node"))
    o["bounds"] = bounds(s, o.get("bounds"))
    o["pvs"] = bitvector(s, o.get("pvs"))
    if version >= 1:
        o["group"] = s.u32(o.get("group"))
    if version >= 2:
        o["portals"] = bitvector(s, o.get("portals"))
    return o


def material_element(s, o):             # MaterialElement {name, Type, Count}
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["name"] = s.string(o.get("name"))
    o["type"] = s.u32(o.get("type"))
    o["count"] = s.u32(o.get("count"))
    return o


def material_type(s, o):                # MaterialType {Effect, MaterialElements, DataSize, MaxAlign, Offsets, ListIndex}
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["effect"] = s.string(o.get("effect"))
    o["_ve"] = s.ra(o.get("_ve"))
    o["elements"] = s.vec(o.get("elements"), lambda x: material_element(s, x))
    o["size"] = s.u32(o.get("size"))
    o["align"] = s.u32(o.get("align"))
    o["_vo"] = s.ra(o.get("_vo"))
    o["offsets"] = s.vec(o.get("offsets"), lambda x: s.u16(x))
    o["list"] = s.u32(o.get("list"))
    o["b"] = s.u32(o.get("b"))
    return o


VALUE_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 4, 10: 4}


def packed(s, o):                       # MaterialIndex / DATA_INDEX: "RA", u32, u32
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["a"] = s.u32(o.get("a"))
    o["b"] = s.u32(o.get("b"))
    return o


def value_table(s, o, types):           # FUN_006dbcb0: u32 sets, u32 bytes, sets
    o = _o(o)
    sets = o.get("sets")
    n = s.u32(len(sets) if sets is not None else None)
    o["total"] = s.u32(o.get("total"))
    out = []
    for i in range(n):
        item = sets[i] if sets is not None else {}
        item["type"] = t = s.u32(item.get("type"))
        values = item.get("values")
        got = []
        if types[t]["size"]:
            k = 0
            for el in types[t]["elements"]:
                for _ in range(el["count"]):
                    x = values[k] if values is not None else None
                    k += 1
                    if el["type"] in (8, 9):
                        got.append(packed(s, x))
                    else:
                        got.append(s.raw(x, VALUE_SIZE[el["type"]]))
        item["values"] = got
        out.append(item)
    o["sets"] = out
    return o


def material_list(s, o):                # FUN_006e8e60: types, then value table
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["_vt"] = s.ra(o.get("_vt"))
    o["types"] = s.vec(o.get("types"), lambda x: material_type(s, x))
    o["values"] = value_table(s, o.get("values"), o["types"])
    return o


def range_(s, o):                       # a draw range: start, count, min index, vertex count
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["r"] = [s.u32(x) for x in (o.get("r") or [None] * 4)]
    return o


def stream(s, o):                       # vertex stream: u32 ?, ?, byte offset, ?, buffer
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["w"] = [s.u32(x) for x in (o.get("w") or [None] * 4)]
    o["buffer"] = packed(s, o.get("buffer"))
    return o


def geometry(s, o):                     # FUN_006e5310: one draw call's geometry
    o = _o(o)
    o["_v"] = v = s.ra(o.get("_v"))
    o["w"] = [s.u32(x) for x in (o.get("w") or [None] * 5)]
    o["indices"] = packed(s, o.get("indices"))
    if v:
        o["decl"] = packed(s, o.get("decl"))
    o["_vs"] = s.ra(o.get("_vs"))
    st = o.get("states") or [None] * 6
    o["states"] = [s.u32(st[0]), s.u32(st[1]), s.u32(st[2]), s.raw(st[3], 4), s.u32(st[4]), s.u32(st[5])]
    o["_vr"] = s.ra(o.get("_vr"))
    o["ranges"] = s.vec(o.get("ranges"), lambda x: range_(s, x))
    o["_vst"] = s.ra(o.get("_vst"))
    o["streams"] = s.vec(o.get("streams"), lambda x: stream(s, x))
    return o


def _list(s, o, item):                  # "RA" + vector
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["items"] = s.vec(o.get("items"), item)
    return o


def draw(s, o):                         # FUN_006e4900
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["material"] = s.u32(o.get("material"))
    o["geometry"] = packed(s, o.get("geometry"))
    o["streams"] = _list(s, o.get("streams"), lambda x: stream(s, x))
    o["values"] = s.u32(o.get("values"))
    return o


def instanced(s, o):                    # FUN_006e8990
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["draw"] = draw(s, o.get("draw"))
    o["instance"] = stream(s, o.get("instance"))
    return o


def six(s, o):
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["w"] = [s.u32(x) for x in (o.get("w") or [None] * 6)]
    return o


def byte_vec(s, o):
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    data = o.get("data")
    o["data"] = s.raw(data, s.u32(len(data)) if not s.reading else s.u32())
    return o


def lod_list(s, o):                     # FUN_006e6130
    o = _o(o)
    o["_v"] = v = s.ra(o.get("_v"))
    o["a"] = s.u32(o.get("a"))
    if v:
        o["u16"] = _list(s, o.get("u16"), lambda x: s.u16(x))
    o["b"] = s.u32(o.get("b"))
    o["bytes"] = byte_vec(s, o.get("bytes"))
    return o


def bit_pair(s, o):                     # FUN_006e84e0
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    pairs = o.get("pairs") or [None, None]
    out = []
    for p in pairs:
        p = _o(p)
        p["_v"] = s.ra(p.get("_v"))
        p["bits"] = s.u32(p.get("bits"))
        p["bytes"] = byte_vec(s, p.get("bytes"))
        out.append(p)
    o["pairs"] = out
    return o


def entry3(s, o):
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["res"] = resource_index(s, o.get("res"))
    o["x"] = s.u32(o.get("x"))
    return o


def resource_group(s, o):
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["k"] = s.u32(o.get("k"))
    o["lists"] = [_list(s, x, lambda y: entry3(s, y)) for x in (o.get("lists") or [None] * 3)]
    return o


def tagged_bytes(s, o):                 # FUN_006e48a0: u32, "RA" + bytes
    o = _o(o)
    o["tag"] = s.u32(o.get("tag"))
    o["bytes"] = byte_vec(s, o.get("bytes"))
    return o


def render_list(s, o, version):         # RenderingData::RenderListNode_Common (FUN_006ea950)
    o = _o(o)
    o["_vc"] = cv = s.ra(o.get("_vc"))
    o["cull"] = cull_node(s, o.get("cull"), cv)
    L = lambda key, item: _list(s, o.get(key), item)
    if version < 2:
        o["six"] = L("six", lambda x: six(s, x))
        o["bounds_a"] = L("bounds_a", lambda x: bounds(s, x))
        o["bytes_a"] = L("bytes_a", lambda x: tagged_bytes(s, x))
        if version == 1:
            o["v1"] = s.u32(o.get("v1"))
            o["u32s"] = L("u32s", lambda x: s.u32(x))
            o["bitpairs"] = L("bitpairs", lambda x: bit_pair(s, x))
        o["static"] = L("static", lambda x: geometry(s, x))
        o["bounds_b"] = L("bounds_b", lambda x: bounds(s, x))
        o["bytes_b"] = L("bytes_b", lambda x: tagged_bytes(s, x))
        o["draws"] = L("draws", lambda x: draw(s, x))
        o["bounds_c"] = L("bounds_c", lambda x: bounds(s, x))
        o["bytes_c"] = L("bytes_c", lambda x: tagged_bytes(s, x))
        o["instanced"] = L("instanced", lambda x: instanced(s, x))
        o["geometry"] = L("geometry", lambda x: geometry(s, x))
        o["materials"] = material_list(s, o.get("materials"))
        o["extra"] = [material_list(s, x) for x in (o.get("extra") or [None, None])]
    else:
        o["materials"] = material_list(s, o.get("materials"))
        o["static"] = L("static", lambda x: geometry(s, x))
        o["draws"] = L("draws", lambda x: draw(s, x))
        o["instanced"] = L("instanced", lambda x: instanced(s, x))
        o["geometry"] = L("geometry", lambda x: geometry(s, x))
        o["values"] = value_table(s, o.get("values"), o["materials"]["types"])
        o["six"] = L("six", lambda x: six(s, x))
        for k in ("bounds_a", "bounds_b", "bounds_c"):
            o[k] = L(k, lambda x: bounds(s, x))
        for k in ("lod_a", "lod_b", "lod_c"):
            o[k] = lod_list(s, o.get(k))
        o["u32s"] = L("u32s", lambda x: s.u32(x))
        o["bitpairs"] = L("bitpairs", lambda x: bit_pair(s, x))
        if version == 3:
            o["extra"] = [material_list(s, x) for x in (o.get("extra") or [None, None])]
        elif version > 3:
            o["extra"] = L("extra", lambda x: material_list(s, x))
    for k in ("ib", "vb", "textures"):
        o[k] = L(k, lambda x: resource_index(s, x))
    o["groups"] = L("groups", lambda x: resource_group(s, x))
    return o


CULL = "RenderingData::CullNode"
RENDER_LIST = "RenderingData::RenderListNode_Common"


def scene_node(s, o):
    """A polymorphic pointer: u8 kind (0 none, 2 bare render list, 3 class name + object)."""
    if o is None and not s.reading:
        s.u8(0)
        return None
    o = _o(o)
    o["kind"] = kind = s.u8(o.get("kind"))
    if kind == 0:
        return None
    if kind == 3:
        o["class"] = cls = s.string(o.get("class"))
        if cls == CULL:
            o["_v"] = v = s.ra(o.get("_v"))
            o["body"] = cull_node(s, o.get("body"), v)
        elif cls == RENDER_LIST:
            o["_vp"] = s.ra(o.get("_vp"))
            o["_v"] = v = s.ra(o.get("_v"))
            o["body"] = render_list(s, o.get("body"), v)
        else:
            raise SceneError(f"unknown scene object {cls}")
        return o
    if kind == 2:
        o["_vp"] = s.ra(o.get("_vp"))
        o["materials"] = material_list(s, o.get("materials"))
        return o
    raise SceneError(f"scene object kind {kind} at {s.p - 1:#x}")


# ---- scene object and blocks ---------------------------------------------------------------------

def vertex_element(s, o):               # FUN_006d8380: a D3DVERTEXELEMENT9
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["stream"] = s.u16(o.get("stream"))
    o["offset"] = s.u16(o.get("offset"))
    o["type"] = s.u32(o.get("type"))
    o["method"] = s.u32(o.get("method"))
    o["usage"] = s.u32(o.get("usage"))
    o["index"] = s.u8(o.get("index"))
    return o


def keyed_texture(s, o):                # name, key, then "RA" + FUN_006e1510
    o = _o(o)
    o["name"] = s.string(o.get("name"))
    o["key"] = s.u32(o.get("key"))
    o["_vw"] = s.ra(o.get("_vw"))
    o["_v"] = s.ra(o.get("_v"))
    o["kind"] = s.u32(o.get("kind"))
    o["name2"] = s.string(o.get("name2"))
    o["_vs"] = sv = s.ra(o.get("_vs"))
    o["sampler"] = [s.u32(x) for x in (o.get("sampler") or [None] * (10 if sv else 9))]
    o["hash"] = s.u32(o.get("hash"))
    data = o.get("data")
    o["data"] = s.raw(data, s.u32(len(data)) if not s.reading else s.u32())
    return o


def scene_object(s, o, version):        # FUN_006ec040
    o = _o(o)
    o["_vh"] = s.ra(o.get("_vh"))
    o["head"] = s.u32(o.get("head"))
    o["_vr"] = s.ra(o.get("_vr"))
    o["root_class"] = s.string(o.get("root_class"))
    o["_vrw"] = s.ra(o.get("_vrw"))
    o["_vrc"] = rv = s.ra(o.get("_vrc"))
    o["root"] = cull_node(s, o.get("root"), rv)
    o["decls"] = _list(s, o.get("decls"),
                       lambda x: _list(s, x, lambda y: vertex_element(s, y)))
    o["effects"] = _list(s, o.get("effects"), lambda x: _effect(s, x))
    o["packages"] = s.u32(o.get("packages"))
    o["_vk"] = s.ra(o.get("_vk"))
    o["_vkh"] = s.ra(o.get("_vkh"))
    o["keyed_head"] = s.u32(o.get("keyed_head"))
    o["keyed"] = s.vec(o.get("keyed"), lambda x: keyed_texture(s, x))
    o["_vcw"] = s.ra(o.get("_vcw"))
    o["_vc"] = cv = s.ra(o.get("_vc"))
    c = _o(o.get("content"))
    c["_v1"] = s.ra(c.get("_v1"))
    c["sections"] = s.vec(c.get("sections"), lambda x: _empty(s))
    c["_v2"] = s.ra(c.get("_v2"))
    c["blobs"] = s.vec(c.get("blobs"), lambda x: _empty(s))
    if cv:
        c["bounds"] = _list(s, c.get("bounds"), lambda x: bounds(s, x))
        c["_v3"] = s.ra(c.get("_v3"))
        c["blobs2"] = s.vec(c.get("blobs2"), lambda x: _empty(s))
    if cv > 1:
        c["_v4"] = s.ra(c.get("_v4"))
        c["blobs3"] = s.vec(c.get("blobs3"), lambda x: _empty(s))
    if cv >= 3:
        c["tail"] = s.u32(c.get("tail"))
    o["content"] = c
    if version:
        o["objects"] = _list(s, o.get("objects"), lambda x: scene_node(s, x))
    return o


def _effect(s, o):
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["_vn"] = s.ra(o.get("_vn"))
    o["name"] = s.string(o.get("name"))
    return o


def _empty(s):
    raise SceneError("sections / blobs in a model's scene aren't supported (levels only)")


def vertex_buffer(s, o):
    o = _o(o)
    o["tag"] = s.u8(o.get("tag"))
    o["_vw"] = s.ra(o.get("_vw"))
    o["_v"] = s.ra(o.get("_v"))
    o["stride"] = s.u32(o.get("stride"))
    o["_ve"] = s.ra(o.get("_ve"))
    o["elements"] = s.vec(o.get("elements"), lambda x: _buffer_element(s, x))
    o["_vo"] = s.ra(o.get("_vo"))
    o["offsets"] = s.vec(o.get("offsets"), lambda x: s.u16(x))
    o["count"] = s.u32(o.get("count"))
    o["blob"] = _buffer_data(s, o, o["_vw"], o["stride"] * o["count"])
    return o


def _buffer_data(s, o, version, size):
    """Version 1+: an aligned blob. Version 0 (rare): the bytes straight away."""
    if version:
        return s.blob(o.get("blob"))
    data = o.get("blob", {}).get("data")
    return {"data": s.raw(data, size)}


def _buffer_element(s, o):              # "RA", u32 type, u32 0, u32 usage, u32 usage index
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["w"] = [s.u32(x) for x in (o.get("w") or [None] * 4)]
    return o


def index_buffer(s, o):
    o = _o(o)
    o["tag"] = s.u8(o.get("tag"))
    o["_v"] = s.ra(o.get("_v"))
    o["count"] = s.u32(o.get("count"))
    o["format"] = s.u32(o.get("format"))
    size = {0: 2, 1: 4}.get(o["format"], 0) * o["count"]   # 0: 16-bit indices, 1: 32-bit
    o["blob"] = _buffer_data(s, o, o["_v"], size)
    return o


def texture_copy(s, o):                 # u32 present; u32 28, w, h, depth, mips, format, -1, 3, blob
    if o is None and not s.reading:
        s.u32(0)
        return None
    present = s.u32(1 if o is not None else None)
    if not present:
        return None
    o = _o(o)
    o["head"] = [s.u32(x) for x in (o.get("head") or [None] * 8)]
    o["blob"] = s.blob(o.get("blob"))
    return o


def block_texture(s, o, level):         # FUN_006e1800
    o = _o(o)
    o["_v1"] = s.ra(o.get("_v1"))
    o["_v2"] = s.ra(o.get("_v2"))
    o["two"] = s.u32(o.get("two"))
    if level == 0:
        o["name"] = s.string(o.get("name"))
        o["_vs"] = sv = s.ra(o.get("_vs"))
        o["sampler"] = [s.u32(x) for x in (o.get("sampler") or [None] * (10 if sv else 9))]
        o["hash"] = s.u32(o.get("hash"))
    o["copy"] = texture_copy(s, o.get("copy"))
    return o


def block_level(s, o):                  # FUN_006ea2a0
    o = _o(o)
    o["_v1"] = s.ra(o.get("_v1"))
    o["_v2"] = s.ra(o.get("_v2"))
    o["two"] = s.u32(o.get("two"))
    o["level"] = level = s.u32(o.get("level"))
    if level == 0:
        o["vb"] = _list(s, o.get("vb"), lambda x: vertex_buffer(s, x))
        o["ib"] = _list(s, o.get("ib"), lambda x: index_buffer(s, x))
        o["objects"] = _list(s, o.get("objects"), lambda x: scene_node(s, x))
    o["textures"] = s.vec(o.get("textures"), lambda x: block_texture(s, x, level))
    return o


def package(s, o):                      # "RA" + FUN_006eb940
    o = _o(o)
    o["_v"] = s.ra(o.get("_v"))
    o["_vh"] = s.ra(o.get("_vh"))
    o["head"] = s.u32(o.get("head"))
    o["levels"] = s.vec(o.get("levels"), lambda x: block_level(s, x))
    return o


def stream_(s, o):
    """The whole ARCH stream."""
    o = _o(o)
    s.raw(b"ARCH", 4)
    o["endian"] = s.u32(o.get("endian", 1))
    o["h2"] = s.u32(o.get("h2", 0))
    s.raw(b"ARCH", 4)
    o["version"] = s.u32(o.get("version"))
    o["has_scene"] = s.u32(o.get("has_scene", 1))
    o["_vs"] = sv = s.ra(o.get("_vs"))
    o["scene"] = scene_object(s, o.get("scene"), sv)
    o["packages"] = s.vec(o.get("packages"), lambda x: package(s, x))
    return o


def read(data, start=None, end=None):
    """The scene stream starting at `start` (the "ARCH"); raises SceneError."""
    start = data.find(b"ARCH") if start is None else start
    if start < 0:
        raise SceneError("no ARCH stream")
    r = Reader(data[:end] if end is not None else data, start, start)
    if bytes(data[start:start + 4]) != b"ARCH":
        raise SceneError("no ARCH stream")
    out = stream_(r, None)
    out["_end"] = r.p
    return out


def write(scene):
    """The bytes of a scene stream (as read by read(), possibly changed)."""
    w = Writer()
    stream_(w, scene)
    return bytes(w.out)

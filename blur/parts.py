"""The drawable parts of a model's scene, and rebuilding its buffers with new geometry.

Works on the dict that blur.scene.read() returns. A *part* is one geometry record
of a render list (RenderListNode_Common "static" or "geometry"): one material
on one element, with a draw range per level of detail. Checked over every
model in the game:

    record w      [material, ?, ?, index buffer slot, element | flags << 16]
                  material = number in the scene's effect list; the slot is a
                  position in the render list's `ib` list -> (package, buffer)
    streams       one per pass: w [vertex buffer slot, ?, byte offset, ?] and a
                  MaterialIndex (value set, process type). Pass 0's slot is a
                  position in the render list's `vb` list -> (package, buffer);
                  its byte offset / stride is the part's first vertex ("base")
    ranges        per level of detail: start, count (in the index buffer; a
                  triangle strip, triangles joined by repeated indices), min
                  index and vertex count (exactly the indices used, counted
                  from the base). Unused levels: count 0, min 0x7FFFFFFF, 0
    bounds_a[i]   the box around static part i's vertices (+ draw distances)

Index buffers are always 16-bit. Vertex elements (type, 0, usage, usage index):
type 6 float3, 7 float4, 8 half2, 9 half4, 10 four bytes, 11 four bytes
mapped to -1..1 (normals) or 0..1 (colour, usage 9). Usage: 0 position,
3 normal, 5 texture coordinates (index 0/1 UV sets; 2/3 damage offsets on
cars, or bone slots/weights on characters), 9 colour (stored B, G, R, A).
"""

from dataclasses import dataclass, field

import numpy as np

NULL = 0xFFFFFFFF
EMPTY_MIN = 0x7FFFFFFF

FLOAT3, FLOAT4, HALF2, HALF4, UBYTE4, UBYTE4N = 6, 7, 8, 9, 10, 11
TYPE_SIZE = {FLOAT3: 12, FLOAT4: 16, HALF2: 4, HALF4: 8, UBYTE4: 4, UBYTE4N: 4}
POSITION, NORMAL, TEXCOORD, COLOR = 0, 3, 5, 9
COLORS = (9, 10)             # usage 10 (Direct3D's COLOR) appears in older files


class PartsError(Exception):
    pass


@dataclass
class Element:
    usage: int
    index: int
    type: int
    offset: int


@dataclass
class Part:
    key: str                 # "<render list>.<list>.<number>", stable for a given file
    rl: dict                 # the render list body
    kind: str                # "static" or "geometry"
    number: int              # position in that list
    record: dict             # the geometry record
    package: int             # package holding the render list (-1: the scene object)
    material: int
    element: int             # MdlDat element number (low 16 bits of w[4])
    flags: int               # high bits of w[4]
    ib: tuple                # (package, index buffer)
    vb: tuple                # (package, vertex buffer), or None (no vertex buffer)
    base: int                # first vertex in the vertex buffer
    lods: list = field(default_factory=list)   # [start, count, min, vertex count] per level

    @property
    def values(self):
        """The part's material value set (pass 0)."""
        return self.record["streams"][0]["buffer"]["a"]

    @property
    def span(self):
        """Vertices used from `base` on."""
        return max((m + n for s, c, m, n in self.lods if c), default=0)


# ---- finding things ------------------------------------------------------------------------------

def render_lists(scene):
    """[(package, render list body)] in file order (the scene object's first)."""
    out = []
    for o in (scene["scene"].get("objects") or {}).get("items", []):
        if o and o.get("class", "").endswith("RenderListNode_Common"):
            out.append((-1, o["body"]))
    for pi, p in enumerate(scene["packages"]):
        for o in p["levels"][0]["objects"]["items"]:
            if o and o.get("class", "").endswith("RenderListNode_Common"):
                out.append((pi, o["body"]))
    return out


def _ref(lst, slot):
    items = lst["items"]
    if slot >= len(items) or items[slot][0] == NULL:
        return None
    return tuple(items[slot])


def vertex_buffer(scene, ref):
    return scene["packages"][ref[0]]["levels"][0]["vb"]["items"][ref[1]]


def index_buffer(scene, ref):
    return scene["packages"][ref[0]]["levels"][0]["ib"]["items"][ref[1]]


def parts(scene):
    out = []
    for r, (pi, rl) in enumerate(render_lists(scene)):
        for kind in ("static", "geometry"):
            for i, g in enumerate(rl.get(kind, {}).get("items", [])):
                w, st = g["w"], g["streams"][0]["w"]
                ib = _ref(rl["ib"], w[3])
                vb = _ref(rl["vb"], st[0])
                if ib is None:
                    continue
                stride = vertex_buffer(scene, vb)["stride"] if vb else 0
                out.append(Part(f"{r}.{kind}.{i}", rl, kind, i, g, pi, w[0], w[4] & 0xFFFF, w[4] >> 16,
                                ib, vb, st[2] // stride if stride else 0,
                                [list(x["r"]) for x in g["ranges"]]))
    return out


def layout(vb):
    """The vertex elements of a vertex buffer record."""
    return [Element(e["w"][2], e["w"][3], e["w"][0], off) for e, off in zip(vb["elements"], vb["offsets"])]


def find(elements, usage, index=0):
    usages = COLORS if usage in COLORS else (usage,)
    return next((e for e in elements if e.usage in usages and e.index == index), None)


def is_shadow(elements):
    """Shadow hulls (veh_Shadow.fx) have positions only."""
    return [e.usage for e in elements] == [POSITION]


# ---- vertices ------------------------------------------------------------------------------------

def rows(vb):
    """The vertex buffer as an (n, stride) uint8 array."""
    return np.frombuffer(vb["blob"]["data"], np.uint8).reshape(vb["count"], vb["stride"])


def decode(raw, e, components=None):
    """Element `e` of every row of `raw` as floats (n, components)."""
    n = len(raw)
    if e.type in (FLOAT3, FLOAT4, HALF2, HALF4):
        dt, k = {FLOAT3: (np.float32, 3), FLOAT4: (np.float32, 4), HALF2: (np.float16, 2),
                 HALF4: (np.float16, 4)}[e.type]
        size = np.dtype(dt).itemsize * k
        v = raw[:, e.offset:e.offset + size].copy().view(dt).reshape(n, k).astype(np.float32)
    else:
        b = raw[:, e.offset:e.offset + 4].astype(np.float32)
        if e.type == UBYTE4N:
            v = b / 255.0 if e.usage in COLORS else b / 127.5 - 1.0
        else:
            v = b
    v = np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)
    return v if components is None else v[:, :components]


def encode(raw, e, values):
    """Writes float values (n, k) into element `e` of every row of `raw` (in place); components
    beyond k keep what `raw` holds."""
    values = np.asarray(values, np.float32)
    n, k = values.shape
    if e.type in (FLOAT3, FLOAT4, HALF2, HALF4):
        dt, total = {FLOAT3: (np.float32, 3), FLOAT4: (np.float32, 4), HALF2: (np.float16, 2),
                     HALF4: (np.float16, 4)}[e.type]
        size = np.dtype(dt).itemsize
        cur = raw[:, e.offset:e.offset + size * total].copy().view(dt).reshape(n, total)
        cur[:, :min(k, total)] = values[:, :total].astype(dt)
        raw[:, e.offset:e.offset + size * total] = cur.view(np.uint8).reshape(n, size * total)
    elif e.type in (UBYTE4, UBYTE4N):
        if e.type == UBYTE4N:
            b = values * 255.0 if e.usage in COLORS else (values + 1.0) * 127.5
        else:
            b = values
        raw[:, e.offset:e.offset + min(k, 4)] = np.clip(np.rint(b[:, :4]), 0, 255).astype(np.uint8)
    else:
        raise PartsError(f"vertex element type {e.type} can't be written")


# ---- triangle strips -----------------------------------------------------------------------------

def strip_triangles(indices):
    """Triangles (a, b, c) of a triangle strip; degenerate ones (the joins) dropped."""
    s = np.asarray(indices, np.int64)
    if len(s) < 3:
        return np.zeros((0, 3), np.int64)
    a, b, c = s[:-2], s[1:-1], s[2:]
    odd = (np.arange(len(a)) % 2).astype(bool)
    tri = np.stack([a, np.where(odd, c, b), np.where(odd, b, c)], axis=1)
    keep = (a != b) & (b != c) & (a != c)
    return tri[keep]


def make_strip(triangles):
    """A triangle strip drawing `triangles` (front faces as given): consecutive triangles that
    share an edge continue the strip, others are joined with repeated indices."""
    out = []
    for a, b, c in np.asarray(triangles, np.int64).tolist():
        if out:
            u, v = out[-2], out[-1]
            even = (len(out) - 2) % 2 == 0     # orientation of the next triangle
            want = (u, v) if even else (v, u)  # (first, second) of the next triangle, as wound
            for x, y, z in ((a, b, c), (b, c, a), (c, a, b)):
                if (x, y) == want:
                    out.append(z)
                    break
            else:
                out += [v, a]            # repeat the last index and the next first one
                if len(out) % 2:         # the next triangle must start at an even place
                    out.append(a)
                out += [a, b, c]
            continue
        out += [a, b, c]
    return out


# ---- rebuilding ----------------------------------------------------------------------------------

@dataclass
class Edit:
    """New geometry for a part: vertex rows in its vertex buffer's layout, and per level of
    detail the triangles (vertex numbers within `vertices`), or None to leave a level unused.
    Levels past the end of `lods` repeat the last one given."""
    vertices: np.ndarray     # (n, stride) uint8
    lods: list


def _grow(box, lo, hi):
    box[0:3] = [min(a, float(b)) for a, b in zip(box[0:3], lo)]
    box[3:6] = [max(a, float(b)) for a, b in zip(box[3:6], hi)]


def rebuild(scene, edits):
    """Rewrites the vertex and index buffers holding the parts in `edits` ({key: Edit}),
    their draw ranges and bounds. Other parts keep their geometry (moved, unchanged)."""
    all_parts = parts(scene)
    by_key = {p.key: p for p in all_parts}
    for key in edits:
        if key not in by_key:
            raise PartsError(f"no part {key}")
        if by_key[key].vb is None:
            raise PartsError(f"part {key} has no vertex buffer")
    touched_vb = {by_key[k].vb for k in edits}
    touched_ib = {by_key[k].ib for k in edits}

    # vertices: each edited part gets its own block; untouched blocks are copied once
    new_base = {}
    for ref in touched_vb:
        vb = vertex_buffer(scene, ref)
        old = rows(vb)
        users = sorted((p for p in all_parts if p.vb == ref), key=lambda p: (p.base, p.key))
        chunks, at, copied = [], 0, {}
        for p in users:
            if p.key in edits:
                v = np.asarray(edits[p.key].vertices, np.uint8)
                if v.ndim != 2 or v.shape[1] != vb["stride"]:
                    raise PartsError(f"part {p.key}: vertices must be rows of {vb['stride']} bytes")
                if len(v) > 0xFFFF:
                    raise PartsError(f"part {p.key}: {len(v)} vertices, at most 65535 fit")
                chunks.append(v)
                new_base[p.key] = at
                at += len(v)
                continue
            span = (p.base, p.span)
            if span not in copied:
                copied[span] = at
                chunks.append(old[p.base:p.base + p.span])
                at += p.span
            new_base[p.key] = copied[span]
        data = np.concatenate(chunks) if chunks else np.zeros((0, vb["stride"]), np.uint8)
        vb["count"] = len(data)
        vb["blob"]["data"] = data.tobytes()
        for p in users:
            p.record["streams"][0]["w"][2] = new_base[p.key] * vb["stride"]
            p.base = new_base[p.key]

    # indices: every part on a touched index buffer, in their old order
    for ref in touched_ib:
        ib = index_buffer(scene, ref)
        old = np.frombuffer(ib["blob"]["data"], np.uint16)
        users = sorted((p for p in all_parts if p.ib == ref),
                       key=lambda p: (min((s for s, c, m, n in p.lods if c), default=1 << 40), p.key))
        out, at = [], 0
        for p in users:
            ranges = []
            if p.key in edits:
                lods = edits[p.key].lods
                for level in range(len(p.lods)):
                    tris = lods[min(level, len(lods) - 1)] if lods else None
                    if tris is None or len(tris) == 0:
                        ranges.append([at, 0, EMPTY_MIN, 0])
                        continue
                    tris = np.asarray(tris, np.int64)
                    strip = make_strip(tris)
                    lo, hi = int(tris.min()), int(tris.max())
                    out.append(np.asarray(strip, np.uint16))
                    ranges.append([at, len(strip), lo, hi - lo + 1])
                    at += len(strip)
            else:
                for s, c, m, n in p.lods:
                    if not c:
                        ranges.append([at, 0, m, n])
                        continue
                    out.append(old[s:s + c])
                    ranges.append([at, c, m, n])
                    at += c
            p.lods = ranges
            for r, rec in zip(ranges, p.record["ranges"]):
                rec["r"] = list(r)
        data = np.concatenate(out) if out else np.zeros(0, np.uint16)
        ib["count"] = len(data)
        ib["blob"]["data"] = data.astype(np.uint16).tobytes()

    # bounds: the edited parts' boxes; their render lists and parent nodes grow to fit
    for key, edit in edits.items():
        p = by_key[key]
        el = find(layout(vertex_buffer(scene, p.vb)), POSITION)
        if el is None or p.kind != "static" or not len(edit.vertices):
            continue
        pos = decode(np.asarray(edit.vertices, np.uint8), el, 3)
        lo, hi = pos.min(0), pos.max(0)
        bounds = p.rl["bounds_a"]["items"]
        if p.number < len(bounds):
            bounds[p.number]["box"][0:6] = [float(x) for x in lo] + [float(x) for x in hi]
        _grow(p.rl["cull"]["bounds"]["box"], lo, hi)
        parent = p.rl["cull"]["node"]["parent"]
        if p.package >= 0 and parent[0] != NULL:
            objs = scene["packages"][p.package]["levels"][0]["objects"]["items"]
            if parent[1] < len(objs) and objs[parent[1]] and objs[parent[1]].get("class", "").endswith("CullNode"):
                _grow(objs[parent[1]]["body"]["bounds"]["box"], lo, hi)
        if p.kind == "static":
            show_everywhere(p.rl, p.number)       # a moved part may now be seen from anywhere


# ---- render list bookkeeping ----------------------------------------------------------------------
#
# Checked over every model:
#   six        5-6 buckets (count, first) over the static parts, consecutive, adding up to all
#              of them: the draw order (opaque first; transparent parts in bucket 3)
#   bounds_a   one per static part (its vertex box, then its draw distances)
#   lod_a      cars (record version 1): a = 512 view directions, u16[512] -> row, b = bytes per
#              row (one bit per static part, lowest bit first), the rows: which parts can be seen
#              from each direction. Props (version 0): not used (a and b hold leftover memory).
#   static w[1]   the scene's vertex declaration for the part's vertex buffer
#   static "indices" (MaterialIndex: row, list): the row of extra list (list - 1), an "Element"
#              entry whose Index value is the part's element

BIG = 8.507059173023462e+37


def _bucket(rl, number):
    for k, item in enumerate(rl["six"]["items"]):
        count, first = item["w"][0], item["w"][1]
        if first <= number < first + count:
            return k
    return 0


def _visibility(rl):
    """(rows (n, bytes) uint8 array, lod list) of a car render list, or (None, None)."""
    lod = rl.get("lod_a")
    if not lod or not lod.get("_v") or not lod.get("u16", {}).get("items"):
        return None, None
    b = lod["b"]
    data = lod["bytes"]["data"]
    if not b or len(data) % b:
        return None, None
    return np.frombuffer(data, np.uint8).reshape(-1, b).copy(), lod


def show_everywhere(rl, number):
    """Marks static part `number` visible from every view direction."""
    rows, lod = _visibility(rl)
    if rows is None:
        return
    rows[:, number // 8] |= np.uint8(1 << (number % 8))
    lod["bytes"]["data"] = rows.tobytes()


def _insert_visibility(rl, number, total):
    """A new static part at `number` (of `total` after the insert): its bit set everywhere."""
    rows, lod = _visibility(rl)
    if rows is None:
        return
    bits = np.unpackbits(rows, axis=1, bitorder="little")[:, :total - 1]
    bits = np.insert(bits, number, 1, axis=1)
    b = (total + 7) // 8
    packed = np.packbits(bits, axis=1, bitorder="little")
    if packed.shape[1] < b:
        packed = np.pad(packed, ((0, 0), (0, b - packed.shape[1])))
    lod["b"] = b
    lod["bytes"]["data"] = packed[:, :b].tobytes()


def _extra_lists(rl):
    extra = rl.get("extra")
    return extra["items"] if isinstance(extra, dict) else (extra or [])


def _element_row(rl, record, element):
    """The (row, list) of the "Element" entry naming `element`, added if missing."""
    list_no = record["indices"]["b"]
    lists = _extra_lists(rl)
    if not 0 < list_no <= len(lists):
        raise PartsError("the render list has no element table")
    table = lists[list_no - 1]
    entry = next((i for i, t in enumerate(table["types"]) if t["effect"] == "Element"), None)
    if entry is None:
        raise PartsError("the render list has no Element entry")
    sets = table["values"]["sets"]
    for i, st in enumerate(sets):
        if st["type"] == entry and st["values"] and isinstance(st["values"][0], bytes) \
                and int.from_bytes(st["values"][0], "little") == element:
            return i, list_no
    sets.append({"type": entry, "values": [element.to_bytes(4, "little")]})
    table["values"]["total"] += table["types"][entry]["size"]
    return len(sets) - 1, list_no


def _values_table(rl):
    return rl["values"] if "values" in rl else rl["materials"]["values"]


def add_part(scene, template, element, vertices, lods):
    """Adds a static part drawn like `template` (same effect, vertex format, material values
    to start from, draw bucket) on `element`, with new geometry: `vertices` rows in the
    template's vertex format and per detail level the triangles (or None). Returns its record
    (find the part with `p.record is record`: adding a part renumbers the parts drawn after it)."""
    import copy
    if template.vb is None or template.kind != "static":
        raise PartsError("a new part needs a static template part with vertices")
    vertices = np.asarray(vertices, np.uint8)
    vb = vertex_buffer(scene, template.vb)
    if vertices.ndim != 2 or vertices.shape[1] != vb["stride"]:
        raise PartsError(f"vertices must be rows of {vb['stride']} bytes")
    if len(vertices) > 0xFFFF:
        raise PartsError(f"{len(vertices)} vertices in one part, at most 65535 fit")
    rl = template.rl
    rec = copy.deepcopy(template.record)

    # vertices at the end of the template's vertex buffer, strips at the end of its index buffer
    base = vb["count"]
    vb["blob"]["data"] = bytes(vb["blob"]["data"]) + vertices.tobytes()
    vb["count"] += len(vertices)
    rec["streams"][0]["w"][2] = base * vb["stride"]
    ib = index_buffer(scene, template.ib)
    strips, at = [], ib["count"]
    for level, r in enumerate(rec["ranges"]):
        tris = lods[min(level, len(lods) - 1)] if lods else None
        if tris is None or not len(tris):
            r["r"] = [at, 0, EMPTY_MIN, 0]
            continue
        tris = np.asarray(tris, np.int64)
        strip = make_strip(tris)
        lo, hi = int(tris.min()), int(tris.max())
        r["r"] = [at, len(strip), lo, hi - lo + 1]
        strips.append(np.asarray(strip, np.uint16))
        at += len(strip)
    if strips:
        ib["blob"]["data"] = bytes(ib["blob"]["data"]) + np.concatenate(strips).tobytes()
    ib["count"] = at

    # its own material values (a copy of the template's, edited by the caller), its element
    table = _values_table(rl)
    types = rl["materials"]["types"]
    main = copy.deepcopy(table["sets"][template.values])
    table["sets"].append(main)
    table["total"] += types[main["type"]]["size"]
    rec["streams"][0]["buffer"]["a"] = len(table["sets"]) - 1
    rec["w"][4] = (element & 0xFFFF) | (template.flags << 16)
    row, list_no = _element_row(rl, rec, element)
    rec["indices"]["a"], rec["indices"]["b"] = row, list_no
    # the lighting pass of a part on the same element, if one uses the same entry
    for k, st in enumerate(rec["streams"][1:], 1):
        want = table["sets"][st["buffer"]["a"]]["type"]
        for other in rl["static"]["items"]:
            if (other["w"][4] & 0xFFFF) == element and len(other["streams"]) > k:
                cand = other["streams"][k]["buffer"]["a"]
                if table["sets"][cand]["type"] == want:
                    st["buffer"]["a"] = cand
                    break

    # into the template's draw bucket, with its box and visibility
    statics = rl["static"]["items"]
    bucket = _bucket(rl, template.number)
    six = rl["six"]["items"]
    number = six[bucket]["w"][1] + six[bucket]["w"][0] if six else len(statics)
    statics.insert(number, rec)
    for k, item in enumerate(six):
        if k == bucket:
            item["w"][0] += 1
        elif item["w"][1] >= number and k > bucket:
            item["w"][1] += 1
    box = copy.deepcopy(rl["bounds_a"]["items"][template.number])
    pos_el = find(layout(vb), POSITION)
    if pos_el is not None and len(vertices):
        pos = decode(vertices, pos_el, 3)
        lo, hi = pos.min(0), pos.max(0)
        box["box"] = [float(x) for x in lo] + [float(x) for x in hi] + [-BIG, BIG]
        _grow(rl["cull"]["bounds"]["box"], lo, hi)
        parent = rl["cull"]["node"]["parent"]
        if template.package >= 0 and parent[0] != NULL:
            objs = scene["packages"][template.package]["levels"][0]["objects"]["items"]
            if parent[1] < len(objs) and objs[parent[1]] and objs[parent[1]].get("class", "").endswith("CullNode"):
                _grow(objs[parent[1]]["body"]["bounds"]["box"], lo, hi)
    rl["bounds_a"]["items"].insert(number, box)
    _insert_visibility(rl, number, len(statics))
    return rec


def remove_part(part):
    """Stops drawing a part (every level's range emptied); its record stays."""
    for r in part.record["ranges"]:
        r["r"] = [r["r"][0], 0, EMPTY_MIN, 0]
    part.lods = [list(r["r"]) for r in part.record["ranges"]]


def templates(scene, effect):
    """Static parts drawn with `effect` (any case), best templates first: drawn up close,
    with a vertex buffer."""
    low = effect.lower()
    out = []
    for p in parts(scene):
        if p.kind != "static" or p.vb is None:
            continue
        table = _values_table(p.rl)
        if p.values >= len(table["sets"]):
            continue
        mt = p.rl["materials"]["types"][table["sets"][p.values]["type"]]
        if mt["effect"].lower() == low:
            near = p.rl["bounds_a"]["items"][p.number]["box"][6] <= 1.0 if p.number < len(p.rl["bounds_a"]["items"]) else True
            out.append((not near, p.number, p))
    return [p for _, _, p in sorted(out, key=lambda t: (t[0], t[1]))]


def effects_in(scene):
    """The effects the model's static parts are drawn with (names as stored)."""
    names = []
    for p in parts(scene):
        if p.kind != "static":
            continue
        table = _values_table(p.rl)
        if p.values < len(table["sets"]):
            name = p.rl["materials"]["types"][table["sets"][p.values]["type"]]["effect"]
            if name and name not in names:
                names.append(name)
    return names

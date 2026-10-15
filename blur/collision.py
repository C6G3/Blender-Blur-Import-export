"""Collision shapes of a model (its "Coll" chunk): Blur's physics stream.

Same layout as a level's .levelphysics streams; port of 26Viewer's
tools/research/blur_physics.py (every stream in the game parses to its end).

    "Head", u32 version (10; a few props 3, 6 or 7)
    objects until u32 type == 0x0FFFFFFF:
        u32 type, 13 common words ("base"), the shape's fields, then its placement:
        f32 position[3], f32 rotation[9] (rows; p' = p * R + position), f32 inertia[9]

    base: f32, f32, u32, u32 material (v>=2), u32 flags, u32, f32, u32 handle,
          f32 centre[3], u32, u32 (v>=7)

    0, 11  triangle mesh (11: a template that type 10 places)
    17     f32, triangle mesh, 8 words (v>=5)
    2      box: f32 half extents[3]
    3      convex hull: u32 nv, u32 nt, f32 points[nv][3], u32 corners[nt][3]
    4      sphere: f32 radius (v>=4)
    5      capsule, 6 cylinder, 15 cone: f32 height (along y), f32 radius (v>=4)
    7      body: u32 count, u32 (v>=6), count x (u32 type, fields, f32, f32 rotation[9],
           f32 position[3], f32[9]) — placed relative to the body
    10     placed copy: u32 handle of the template (v>=4)

Placement: a top-level object's space starts at position + centre (its centre of
mass); a body's shapes are placed in that space. Props then line up with their
visible geometry. A car part's body has handle 0xC00000nn: the render tag of
its MdlDat element.
Triangle meshes give every triangle a surface material (SURFACES).
"""

import struct

END = 0x0FFFFFFF

TYPE_NAMES = {0: "mesh", 11: "mesh template", 17: "mesh", 2: "box", 3: "hull", 4: "sphere", 5: "capsule",
              6: "cylinder", 15: "cone", 7: "body", 10: "copy"}

SURFACES = ["Default", "Tarmac", "Concrete", "Rock", "Dirt", "Mud", "Grass", "Gravel", "Sand", "WetSand",
            "Water", "Brick", "Vegetation", "Wood", "Metal", "Plastic", "Glass", "Rubber", "Upholstery",
            "Cardboard", "Flesh", "TrainTracks", "WaterDeep", "ConcreteFenceChain", "ConcreteFencePlastic",
            "MetalHollow", "MetalArmco", "MetalSheet", "MetalFenceChain", "MetalFenceSolid",
            "MetalFenceSlatted", "MetalSolidPost", "DirtLightRough", "DirtHeavyRough"]


class CollisionError(Exception):
    pass


def surface_name(n):
    return SURFACES[n] if 0 <= n < len(SURFACES) else f"Surface {n}"


class _Reader:
    def __init__(self, data, pos):
        self.d, self.p = data, pos

    def u32(self):
        if self.p + 4 > len(self.d):
            raise CollisionError(f"read past the end at {self.p:#x}")
        v = struct.unpack_from("<I", self.d, self.p)[0]
        self.p += 4
        return v

    def f32(self, n=1):
        if self.p + 4 * n > len(self.d):
            raise CollisionError(f"read past the end at {self.p:#x}")
        v = struct.unpack_from(f"<{n}f", self.d, self.p)
        self.p += 4 * n
        return v if n > 1 else v[0]


def _base(r, version):
    r.p += 8
    r.u32()
    material = r.u32() if version >= 2 else 0
    flags = r.u32()
    r.u32()
    r.f32()
    handle = r.u32()
    centre = r.f32(3)
    r.u32()
    if version >= 7:
        r.u32()
    return {"material": material, "flags": flags, "handle": handle, "centre": centre}


def _mesh(r, version):
    nv, nk, _, nn = r.u32(), r.u32(), r.u32(), r.u32()
    r.f32(6)
    if r.p + 12 * nv + 4 * nk + 28 * nn > len(r.d):
        raise CollisionError(f"mesh larger than the stream at {r.p:#x}")
    verts = struct.unpack_from(f"<{3 * nv}f", r.d, r.p)
    r.p += 12 * nv + 4 * nk
    leaves = []
    for k in range(nn):
        tc, off, fv, vc = struct.unpack_from("<4I", r.d, r.p + 28 * k + 12)
        if tc:
            leaves.append((off, tc, fv, vc))
    r.p += 28 * nn
    leaves.sort()
    tris, surfaces = [], []
    for off, tc, fv, vc in leaves:
        left = tc
        while left > 0:
            surface = struct.unpack_from("<H", r.d, r.p + 6)[0]
            count = r.d[r.p + 14]
            if count == 0 or count > left:
                raise CollisionError(f"bad triangle group at {r.p:#x}")
            r.p += 15
            for _ in range(count):
                a, b, c = r.d[r.p], r.d[r.p + 1], r.d[r.p + 2]
                if max(a, b, c) >= vc:
                    raise CollisionError(f"triangle corner outside its leaf at {r.p:#x}")
                tris.append((fv + a, fv + b, fv + c))
                surfaces.append(surface)
                r.p += 11
            left -= count
    if version >= 7:
        n = r.u32()
        r.p += 12 * n
    return {"vertices": [verts[i:i + 3] for i in range(0, len(verts), 3)], "triangles": tris,
            "surfaces": surfaces}


def _shape(r, t, version):
    s = {"type": t, **_base(r, version)}
    if t in (0, 11):
        s.update(_mesh(r, version))
    elif t == 17:
        r.f32()
        s.update(_mesh(r, version))
        if version >= 5:
            r.f32(8)
    elif t == 2:
        s["half"] = r.f32(3)
    elif t == 3:
        nv, nt = r.u32(), r.u32()
        if r.p + 12 * nv + 12 * nt > len(r.d):
            raise CollisionError(f"hull larger than the stream at {r.p:#x}")
        v = struct.unpack_from(f"<{3 * nv}f", r.d, r.p)
        r.p += 12 * nv
        idx = struct.unpack_from(f"<{3 * nt}I", r.d, r.p)
        r.p += 12 * nt
        s["vertices"] = [v[i:i + 3] for i in range(0, len(v), 3)]
        s["triangles"] = [idx[i:i + 3] for i in range(0, len(idx), 3)]
    elif t == 4:
        s["radius"] = r.f32() if version >= 4 else 0.0
    elif t in (5, 6, 15):
        s["height"], s["radius"] = r.f32(2) if version >= 4 else (0.0, 0.0)
    elif t == 7:
        count = r.u32()
        if version >= 6:
            r.u32()
        s["shapes"] = []
        for _ in range(count):
            child = _shape(r, r.u32(), version)
            r.f32()
            child["rotation"] = r.f32(9)
            child["position"] = r.f32(3)
            r.f32(9)
            s["shapes"].append(child)
    elif t == 10:
        s["instance_of"] = r.u32() if version >= 4 else 0
    else:
        raise CollisionError(f"unknown shape type {t} at {r.p:#x}")
    return s


def read(data, start, end=None):
    """The objects of the physics stream at `start` (the "Head")."""
    if data[start:start + 4] != b"Head":
        raise CollisionError("no physics stream (Head)")
    r = _Reader(data[:end] if end is not None else data, start + 4)
    version = r.u32()
    objects = []
    while True:
        t = r.u32()
        if t == END:
            break
        o = _shape(r, t, version)
        o["position"] = r.f32(3)
        o["rotation"] = r.f32(9)
        r.f32(9)
        objects.append(o)
    return objects

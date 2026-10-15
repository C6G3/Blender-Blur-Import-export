"""Imports a .model in a background Blender, exports it, and compares the two files.

    blender -b --factory-startup --python tools/blender_export_test.py -- <file.model> <out folder>

1. Import (all detail levels, shadow hulls) and export without changes: every part
   must draw the same triangles (positions and UVs) at every level of detail;
   prints the largest normal / colour differences (8-bit encodings: one step is
   0.0078 / 0.0039) and how many corners' normals moved more than 0.02.
2. Scale the first LOD0 mesh's vertices by 1.25 and export again: that mesh's parts
   must come out scaled, with their bounds grown to match; the result must import.
"""

import importlib.util
import os
import sys

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from blur import chunks, parts, scene  # noqa: E402


def load_addon():
    spec = importlib.util.spec_from_file_location("blur_model_tools", os.path.join(REPO, "__init__.py"),
                                                  submodule_search_locations=[REPO])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["blur_model_tools"] = mod
    spec.loader.exec_module(mod)
    mod.register()
    return mod


def read_scene(path):
    data = open(path, "rb").read()
    p = chunks.find_path(chunks.parse(data), "Scene")[-1]
    return scene.read(data, p.payload_offset, p.offset + p.size)


def corners(s, p, lod):
    """Per triangle corner: position, normal, uv0, uv1, colour as one float array (t, 3, 14),
    or None if the level isn't drawn."""
    start, count, lo, n = p.lods[lod]
    if not count:
        return None
    ib = np.frombuffer(parts.index_buffer(s, p.ib)["blob"]["data"], np.uint16)
    tris = parts.strip_triangles(ib[start:start + count]) + p.base
    raw = parts.rows(parts.vertex_buffer(s, p.vb))
    els = parts.layout(parts.vertex_buffer(s, p.vb))
    cols = []
    for usage, index, k in ((parts.POSITION, 0, 3), (parts.NORMAL, 0, 3), (parts.TEXCOORD, 0, 2),
                            (parts.TEXCOORD, 1, 2), (parts.COLOR, 0, 4)):
        e = parts.find(els, usage, index)
        cols.append(parts.decode(raw, e, k) if e is not None else np.zeros((len(raw), k), np.float32))
    return np.concatenate(cols, axis=1)[tris]


def by_shape(tris, factor=1.0):
    """{triangle key (rounded positions and UVs, rotated to a canonical start): [triangles]}."""
    out = {}
    for t in tris:
        t = t.copy()
        t[:, :3] *= factor
        keys = [tuple(np.round(np.concatenate([t[i, :3], t[i, 6:10]]), 3).tolist()) for i in range(3)]
        i = min(range(3), key=lambda j: keys[j])
        out.setdefault(tuple(keys[i:] + keys[:i]), []).append(np.roll(t, -i, axis=0))
    return out


def compare(a_path, b_path):
    """Worst differences of normals and colours between matching triangles, and problems."""
    a, b = read_scene(a_path), read_scene(b_path)
    pa = {p.key: p for p in parts.parts(a) if p.vb is not None}
    pb = {p.key: p for p in parts.parts(b) if p.vb is not None}
    worst = {"nrm": 0.0, "col": 0.0, "nrm_off": 0, "corners": 0}
    bad = []
    for key, p in pa.items():
        q = pb[key]
        for lod in range(len(p.lods)):
            x, y = corners(a, p, lod), corners(b, q, lod)
            if x is None or y is None:
                if (x is None) != (y is None):
                    bad.append(f"{key} lod {lod}: drawn in one file only")
                continue
            sx, sy = by_shape(x), by_shape(y)
            if sorted((k, len(v)) for k, v in sx.items()) != sorted((k, len(v)) for k, v in sy.items()):
                bad.append(f"{key} lod {lod}: triangles differ ({len(x)} -> {len(y)})")
                continue
            for k, tx in sx.items():
                ty = sy[k]
                # several identical shapes (two-sided parts): pair them by normals
                for t in tx:
                    d = [np.abs(t[:, 3:6] - u[:, 3:6]).max() for u in ty]
                    j = int(np.argmin(d))
                    u = ty.pop(j)
                    dn = np.abs(t[:, 3:6] - u[:, 3:6]).max(axis=1)
                    worst["nrm"] = max(worst["nrm"], float(dn.max()))
                    worst["nrm_off"] += int((dn > 0.02).sum())
                    worst["col"] = max(worst["col"], float(np.abs(t[:, 10:14] - u[:, 10:14]).max()))
                    worst["corners"] += 3
    return worst, bad


def scaled_ok(a_path, b_path, keys, factor):
    a, b = read_scene(a_path), read_scene(b_path)
    pa = {p.key: p for p in parts.parts(a)}
    pb = {p.key: p for p in parts.parts(b)}
    for key in keys:
        p, q = pa[key], pb[key]
        x, y = corners(a, p, 0), corners(b, q, 0)
        same = x is not None and y is not None and len(x) == len(y)
        if same:
            # every corner lands on a scaled old corner (half floats round: allow 0.2 %)
            want, got = x[:, :, :3].reshape(-1, 3) * factor, y[:, :, :3].reshape(-1, 3)
            gap = max(float(np.abs(want - g).max(axis=1).min()) for g in got)
            same = gap <= 0.002 * max(float(np.abs(want).max()), 1.0)
        box_a = p.rl["bounds_a"]["items"][p.number]["box"][:6] if p.kind == "static" else []
        box_b = q.rl["bounds_a"]["items"][q.number]["box"][:6] if q.kind == "static" else []
        print(f"SCALED part {key}: level 0 = old x {factor}: {same}; bounds {np.round(box_a, 3).tolist()} -> "
              f"{np.round(box_b, 3).tolist()}")


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    path, out_dir = args[0], args[1]
    os.makedirs(out_dir, exist_ok=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    load_addon()
    print("IMPORT", bpy.ops.import_scene.blur_model(filepath=path, all_lods=True, shadows=True))
    root = next(o for o in bpy.data.objects if "blur_model" in o)
    bpy.context.view_layer.objects.active = root
    root.select_set(True)

    same = os.path.join(out_dir, "unchanged.model")
    print("EXPORT", bpy.ops.export_scene.blur_model(filepath=same, source=path))
    worst, bad = compare(path, same)
    print("UNCHANGED", {k: round(v, 5) for k, v in worst.items()}, "problems", len(bad))
    for line in bad[:10]:
        print("   ", line)

    # Scale the vertices of the first LOD0 mesh (in its own space) by 1.25
    mesh_obj = next(o for o in bpy.data.objects if o.type == "MESH" and o.get("blur_lod") == 0
                    and not o.get("blur_shadow"))
    me = mesh_obj.data
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    me.vertices.foreach_set("co", co * 1.25)
    me.update()
    keys = str(mesh_obj["blur_parts"]).split(";")
    # parts drawn at lower levels from this LOD0 mesh only when no LOD mesh replaces them: here
    # every level was imported, so only level 0 of these parts is scaled.
    scaled = os.path.join(out_dir, "scaled.model")
    print("EXPORT", bpy.ops.export_scene.blur_model(filepath=scaled, source=path))
    scaled_ok(path, scaled, keys[:3], 1.25)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    print("REIMPORT", bpy.ops.import_scene.blur_model(filepath=scaled, all_lods=False))
    print("REIMPORTED MESHES", len([o for o in bpy.data.objects if o.type == "MESH"]))


main()
